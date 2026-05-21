import json
import xmlrpc.client
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_HOST     = os.getenv("ODOO_HOST",     "http://localhost")
_PORT     = os.getenv("ODOO_PORT",     "8040")
_DB       = os.getenv("ODOO_DATABASE", "sales_odoo")
_USER     = os.getenv("ODOO_USERNAME", "")
_PASSWORD = os.getenv("ODOO_PASSWORD", "")

_URL = f"{_HOST}:{_PORT}"


def _connect():
    common = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/common")
    uid    = common.authenticate(_DB, _USER, _PASSWORD, {})
    if not uid:
        raise RuntimeError(f"[OdooBridge] Odoo authentication failed for user {_USER!r}")
    models = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/object")
    return uid, models


def send_invoice(file_path: str, result: dict) -> int | None:
    try:
        uid, models = _connect()

        extracted = result.get("extracted") or {}

        audit_data = {
            "file_name"      : Path(file_path).name,
            "file_path"      : str(file_path),
            "supplier_name"  : extracted.get("supplier_name", ""),
            "invoice_number" : extracted.get("invoice_number", ""),
            "invoice_date"   : str(extracted.get("invoice_date") or extracted.get("date") or ""),
            "total_ht"       : float(extracted.get("total_ht")    or 0.0),
            "vat_amount"     : float(extracted.get("vat_amount")  or 0.0),
            "total_ttc"      : float(extracted.get("total_ttc")   or 0.0),
            "currency_code"  : str(extracted.get("currency", "") or ""),
            "confidence"     : float(extracted.get("confidence")  or 0.0),
            "pipeline_status": result.get("status", "extracted"),
            "flags"          : ", ".join(result.get("flags") or []),
            "extracted_json" : json.dumps(extracted, default=str),
        }

        record_id = models.execute_kw(
            _DB, uid, _PASSWORD,
            "smart.billing.invoice", "receive_audit_result",
            [audit_data],
        )
        print(f"[OdooBridge] Invoice sent → smart_billing record ID: {record_id}")
        return record_id

    except Exception as e:
        print(f"[OdooBridge] Warning: could not send invoice to Odoo: {e}")
        return None

