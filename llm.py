import os
import json
import re
import base64
import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

PROMPT = """You are an expert document data extraction assistant. Analyze this formal purchase order carefully.

The document may be written in any language (French, English, Arabic, Spanish, or other).
Identify and extract fields based on their meaning and context, not their exact wording.
The document is a formal purchase order.

EXTRACTION RULES:
- client_name: the company or person who is BUYING — who sent this purchase order
- date: the date of the purchase order, return as YYYY-MM-DD always
- order_number: the purchase order reference number. Look for "BC N°", "PO N°", "Bon de Commande N°", "Order N°", "Réf:". Return null if not found.
- currency: return ISO 4217 code — DH/Dhs/Dirham → MAD, € → EUR, $ → USD, DT → TND
- amount_ht: subtotal before VAT/TVA
- vat_amount: VAT/TVA amount
- amount_total: final total
- line_items: extract ALL product/service rows. IGNORE summary rows (Total, TVA, HT, Sous-total, Remise, Discount or equivalents)
- Return null for any field that is missing or unclear

NUMERIC FORMATTING RULES:
- Return all numbers as plain floats with '.' as decimal separator
- Remove currency symbols and spaces
- Detect thousand separator by context:
  "6.000,00" → 6000.00  (European: dot=thousand, comma=decimal)
  "1,000.50" → 1000.50  (English: comma=thousand, dot=decimal)
  "1 500,00" → 1500.00  (space=thousand, comma=decimal)

Return ONLY a valid JSON object with these exact fields:
{
  "order_number": string or null,
  "date": string (YYYY-MM-DD) or null,
  "client_name": string or null,
  "client_address": string or null,
  "client_city": string or null,
  "client_zip": string or null,
  "client_country": string or null,
  "client_phone": string or null,
  "client_email": string or null,
  "amount_ht": float or null,
  "vat_amount": float or null,
  "amount_total": float or null,
  "currency": string or null,
  "line_items": [
    {
      "description": string,
      "quantity": float or null,
      "unit_price": float or null,
      "total_line": float or null
    }
  ]
}

Return ONLY the JSON, no markdown, no explanation."""


def _fix_order_number(ref: str | None) -> str | None:
    if not ref:
        return None
    return ref.replace('O', '0').replace('o', '0')


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            value = re.sub(r'[^\d,.]', '', value)
            if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', value):
                # European: 6.000,00
                value = value.replace('.', '').replace(',', '.')
            elif re.match(r'^\d{1,3}(,\d{3})+(\.\d+)?$', value):
                # English: 1,000.50
                value = value.replace(',', '')
            else:
                # Simple: 1900,00 or 1900.00
                value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return None


def _file_to_base64(file_path: str) -> tuple[str, str]:
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".pdf":  "application/pdf",
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, mime_type


def _send_file_to_gemini(file_path: str) -> str:
    """Send image or PDF to Gemini as base64 inline_data."""
    file_data, mime_type = _file_to_base64(file_path)
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": file_data,
                        }
                    },
                    {"text": PROMPT},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        },
    }
    response = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_gemini(file_path: str) -> dict:
    raw_text = _send_file_to_gemini(file_path)

    raw_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_text.strip()).strip()

    result = json.loads(raw_text)
    result["order_number"] = _fix_order_number(result.get("order_number"))

    for field in ["amount_ht", "vat_amount", "amount_total"]:
        result[field] = _safe_float(result.get(field))
    for item in result.get("line_items") or []:
        item["quantity"]   = _safe_float(item.get("quantity"))
        item["unit_price"] = _safe_float(item.get("unit_price"))
        item["total_line"] = _safe_float(item.get("total_line"))

    return result