import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction.llm_invoice import call_groq_invoice
from invoices_pipeline.odoo_bridge import send_invoice
from db.db import get_invoice_status, insert_invoice, update_invoice_extraction, find_supplier

INVOICE_DIR = Path(__file__).resolve().parent.parent / "invoices"
ORDER_DIR   = Path(__file__).resolve().parent.parent / "orders" / "informal_orders"

TERMINAL_STATUSES = {"pushed", "rejected"}


def _detect_type(file_path: str) -> str:
    path = Path(file_path).resolve()
    if INVOICE_DIR in path.parents or path.parent == INVOICE_DIR:
        return "invoice"
    if ORDER_DIR in path.parents or path.parent == ORDER_DIR:
        return "order"
    return "unknown"


def _register_invoice(abs_path: str) -> str | None:
    status = get_invoice_status(abs_path)
    if status in TERMINAL_STATUSES:
        return status
    if status is None:
        insert_invoice(
            file_path   = abs_path,
            source      = "manual",
            sender      = None,
            subject     = None,
            received_at = datetime.now(),
        )
    return None


def _cross_validate(extracted: dict) -> list:
    """Return list of price mismatch issues."""
    issues    = []
    total_ht  = extracted.get("total_ht")
    vat       = extracted.get("vat_amount")
    total_ttc = extracted.get("total_ttc")

    if total_ht is not None and vat is not None and total_ttc is not None:
        if round(total_ht + vat, 2) != round(total_ttc, 2):
            issues.append("price mismatch")

    return issues


def process_invoice(file_path: str) -> dict:
    """Extract and validate a single invoice file. Returns extracted data with flags."""
    print(f"\n[InvoiceProcessor] Processing: {Path(file_path).name}")

    extracted  = call_groq_invoice(file_path)
    confidence = extracted.get("confidence") or 0.0
    flags      = []

    print(f"  ← confidence: {confidence}, supplier: {extracted.get('supplier_name')}")

    if confidence < 0.4:
        flags.append("low confidence")
    else:
        if not find_supplier(extracted.get("supplier_name")):
            flags.append("unknown supplier")

        for issue in _cross_validate(extracted):
            flags.append(f"price mismatch: {issue}")

    print(f"[InvoiceProcessor] Done — {len(flags)} flag(s)")
    return {"status": "extracted", "flags": flags, "extracted": extracted}


def route(file_path: str, doc_type: str = None) -> dict:
    if not doc_type:
        doc_type = _detect_type(file_path)

    abs_path = str(Path(file_path).resolve())
    print(f"\n[Processor] {Path(file_path).name} → {doc_type} pipeline")

    if doc_type == "invoice":
        terminal = _register_invoice(abs_path)
        if terminal:
            print(f"[Processor] Skipping — already {terminal}")
            return {"status": terminal, "message": "already processed, skipped"}

        result    = process_invoice(abs_path)
        extracted = result.get("extracted") or {}

        update_invoice_extraction(
            file_path      = abs_path,
            extracted_json = extracted,
            confidence     = float(extracted.get("confidence") or 0),
            supplier_name  = extracted.get("supplier_name"),
            invoice_number = extracted.get("invoice_number"),
            invoice_date   = extracted.get("date") or extracted.get("invoice_date"),
            total_ht       = float(extracted.get("total_ht")   or 0),
            vat_amount     = float(extracted.get("vat_amount") or 0),
            total_ttc      = float(extracted.get("total_ttc")  or 0),
            currency       = extracted.get("currency"),
        )

        send_invoice(abs_path, result)
        return result

    elif doc_type == "order":
        return {"status": "not_implemented", "message": "order processing not yet implemented"}

    return {"status": "error", "message": f"cannot detect document type for {file_path}"}
