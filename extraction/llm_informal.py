import os
import re
import json
import base64
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

PROMPT = """You are an expert document data extraction assistant.

Extract structured data from this informal order. The document may be in any language.

Rules:
- client_name: buyer name if present, otherwise null.
- currency: ISO code (MAD, EUR, USD, TND) if detected, else null.
- line_items: extract ALL products/services mentioned. Never skip a product even if quantity or price is missing — return null for missing fields.
- notes: any additional instructions or context.

Numeric rules — return as floats using '.' as decimal:
  6.000,00 → 6000.00
  1,000.50 → 1000.50
  1 500,00 → 1500.00

Return ONLY this JSON:
{
  "doc_type": "informal_order",
  "client_name": string or null,
  "currency": string or null,
  "notes": string or null,
  "line_items": [
    {"description": string, "quantity": float or null, "unit_price": float or null}
  ]
}"""


# ---------- Helpers ----------
def _extract_date_from_filename(file_path: str) -> str:
    filename = Path(file_path).name
    match = re.match(r'^(\d{8})_\d{6}', filename)
    if match:
        date_str = match.group(1)
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            value = re.sub(r'[^\d,.]', '', value)
            if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', value):
                value = value.replace('.', '').replace(',', '.')
            elif re.match(r'^\d{1,3}(,\d{3})+(\.\d+)?$', value):
                value = value.replace(',', '')
            else:
                value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return None


def _call_gemini(parts: list) -> str:
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    response = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def _validate(result: dict) -> dict:
    """Ensure all expected keys exist with correct types. Never raises — fills missing keys with safe defaults."""
    result.setdefault("doc_type", "informal_order")
    result.setdefault("client_name", None)
    result.setdefault("currency", None)
    result.setdefault("notes", None)

    line_items = result.get("line_items")
    if not isinstance(line_items, list):
        result["line_items"] = []
    else:
        cleaned = []
        for item in line_items:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "description": item.get("description") or "",
                "quantity":    _safe_float(item.get("quantity")),
                "unit_price":  _safe_float(item.get("unit_price")),
            })
        result["line_items"] = cleaned

    return result


# ---------- Main ----------
def call_gemini_informal(file_path: str) -> dict:
    ext = Path(file_path).suffix.lower()

    if ext in {".txt", ".csv"}:
        text  = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        parts = [{"text": f"{PROMPT}\n\nDOCUMENT TEXT:\n{text}"}]
    
    elif ext in {".xlsx", ".xls"}:
        df    = pd.read_excel(file_path, dtype=str)
        text  = df.fillna("").to_csv(index=False)
        parts = [{"text": f"{PROMPT}\n\nDOCUMENT TEXT:\n{text}"}]

    else:
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png",  ".pdf": "application/pdf",
        }
        mime_type = mime_map.get(ext)
        if mime_type is None:
            raise ValueError(f"Unsupported file type: {ext}")
        data  = base64.b64encode(Path(file_path).read_bytes()).decode("utf-8")
        parts = [{"inline_data": {"mime_type": mime_type, "data": data}}, {"text": PROMPT}]

    raw_text = _call_gemini(parts)
    raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
    raw_text = re.sub(r'\s*```$',          '', raw_text.strip())

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON: {e}\nRaw: {raw_text[:300]}")

    result["date"] = _extract_date_from_filename(file_path)
    return _validate(result)