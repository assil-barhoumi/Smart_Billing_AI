import os
import json
import base64
from pathlib import Path
from utils import safe_float, call_gemini, strip_json_fences


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


def _file_to_parts(file_path: str) -> list:
    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".pdf":  "application/pdf",
    }
    mime_type = mime_map.get(ext)
    if mime_type is None:
        raise ValueError(f"Unsupported file type: {ext}")
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return [{"inline_data": {"mime_type": mime_type, "data": data}}, {"text": PROMPT}]


def call_gemini_po(file_path: str) -> dict:
    parts    = _file_to_parts(file_path)
    raw_text = call_gemini(parts)
    raw_text = strip_json_fences(raw_text)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON: {e}\nRaw: {raw_text[:300]}")

    result["order_number"] = _fix_order_number(result.get("order_number"))

    for field in ["amount_ht", "vat_amount", "amount_total"]:
        result[field] = safe_float(result.get(field))
    for item in result.get("line_items") or []:
        item["quantity"]   = safe_float(item.get("quantity"))
        item["unit_price"] = safe_float(item.get("unit_price"))
        item["total_line"] = safe_float(item.get("total_line"))

    return result