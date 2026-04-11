import json
import base64
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from utils import safe_float, strip_json_fences

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"


PROMPT = """You are an expert financial document extraction assistant specialized in invoices.

Analyze this invoice image carefully. The document may be in French, Arabic, English or a mix.
Extract information based on meaning and context, not exact wording.

FIELD RULES:
- supplier_name: the company or person ISSUING the invoice (selling) — NOT "Bill To", NOT "Ship To"
- invoice_number: look for "Facture N°", "N° Facture", "Invoice No", "Réf", "رقم الفاتورة"
- date: invoice date, return as YYYY-MM-DD always
- currency: ISO code — DZD, MAD, TND, EUR, USD (DA→DZD, DH→MAD, DT→TND, €→EUR, $→USD). If no symbol, detect from country in address.
- total_ht: subtotal BEFORE tax (HT, Hors Taxe, Montant HT)
- vat_amount: tax amount (TVA, VAT, Tax)
- total_ttc: FINAL total INCLUDING tax (TTC, Total, المجموع)
- Return null for any field that is missing or unclear

NUMERIC RULES — return as plain floats using dot as decimal:
  "6.000,00" → 6000.00
  "1,000.50" → 1000.50
  "1 500,00" → 1500.00
  Remove all currency symbols and spaces from numbers

LINE ITEMS RULES:
- Extract ALL rows from the table
- IGNORE summary rows (Total, TVA, HT, Remise, Discount)
- If quantity is missing use 1.0
- If unit_price is missing but total is present, use total

Return ONLY this valid JSON, no explanation, no markdown:
{
  "supplier_name": null,
  "supplier_address": null,
  "invoice_number": null,
  "date": null,
  "line_items": [
    {
      "description": null,
      "quantity": null,
      "unit_price": null,
      "total_line": null
    }
  ],
  "total_ht": null,
  "vat_amount": null,
  "total_ttc": null,
  "currency": null,
  "confidence": 0.0
}

confidence rules:
- 0.9-1.0: all fields clear and certain
- 0.7-0.9: most fields clear, minor uncertainty
- 0.4-0.7: partial or ambiguous document
- below 0.4: unreadable or too incomplete"""

OLLAMA_MODEL = "qwen2.5vl:3b"


def _to_image_path(file_path: str) -> str:
    """Convert PDF to image if needed. Returns path to image file."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
            import tempfile
            doc = fitz.open(str(path))
            tmp_path = os.path.join(tempfile.gettempdir(), f"{path.stem}_tmp.png")
            doc[0].get_pixmap(dpi=200).save(tmp_path)
            doc.close()
            return tmp_path
        except Exception as e:
            raise RuntimeError(f"PDF to image conversion failed: {e}. Install pymupdf: pip install pymupdf")
    return str(path)


def _clean_result(result: dict) -> dict:
    """Normalize numeric fields to floats."""
    for field in ["total_ht", "vat_amount", "total_ttc"]:
        result[field] = safe_float(result.get(field))
    for item in result.get("line_items") or []:
        item["quantity"]   = safe_float(item.get("quantity"))
        item["unit_price"] = safe_float(item.get("unit_price"))
        item["total_line"] = safe_float(item.get("total_line"))
    return result


def call_groq_invoice(file_path: str) -> dict:
    """Extract invoice data using Groq API (Llama 4 Scout vision)."""
    from groq import Groq

    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
    }

    # Convert PDF to image first
    if ext == ".pdf":
        file_path = _to_image_path(file_path)
        ext = ".png"

    mime_type = mime_map.get(ext)
    if not mime_type:
        raise ValueError(f"Unsupported file type: {ext}")

    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{data}"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        temperature=0.0,
        max_tokens=8192,
    )

    raw = response.choices[0].message.content
    raw = strip_json_fences(raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Groq returned invalid JSON: {e}\nRaw: {raw[:300]}")

    return _clean_result(result)


def call_ollama_invoice(file_path: str) -> dict:
    """Extract invoice data using Qwen2.5-VL via Ollama."""
    if not OLLAMA_AVAILABLE:
        raise RuntimeError("ollama package not installed. Run: pip install ollama")

    image_path = _to_image_path(file_path)

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{
            "role":    "user",
            "content": PROMPT,
            "images":  [image_path]
        }],
        options={
            "temperature": 0.0,
            "num_predict": 512
        },
        keep_alive="60m"
    )

    raw = response["message"]["content"]
    raw = strip_json_fences(raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ollama returned invalid JSON: {e}\nRaw: {raw[:300]}")

    return _clean_result(result)
