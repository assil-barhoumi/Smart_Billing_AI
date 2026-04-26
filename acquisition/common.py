import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import insert_order, insert_invoice

ROOT              = Path(__file__).resolve().parent.parent
SAVE_PO           = ROOT / "orders" / "purchase_orders"
SAVE_INFORMAL     = ROOT / "orders" / "informal_orders"
SAVE_INVOICES     = ROOT / "invoices"

PO_KEYWORDS       = ["Purchase Order", "Bon de commande"]
INFORMAL_KEYWORDS = ["Order", "commande", "Request", "Demande"]
INVOICE_KEYWORDS  = ["Facture", "Invoice"]

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".xlsx", ".xls"}
INVOICE_EXTENSIONS   = {".pdf", ".png", ".jpg", ".jpeg"}
TIMESTAMP_FORMAT     = "%Y%m%d_%H%M%S"

SAVE_PO.mkdir(parents=True, exist_ok=True)
SAVE_INFORMAL.mkdir(parents=True, exist_ok=True)
SAVE_INVOICES.mkdir(parents=True, exist_ok=True)


def classify_subject(subject: str) -> tuple[Path, str] | None:
    s = subject.lower()
    for kw in PO_KEYWORDS:
        if kw.lower() in s:
            return SAVE_PO, "purchase_order"
    for kw in INVOICE_KEYWORDS:
        if kw.lower() in s:
            return SAVE_INVOICES, "invoice"
    for kw in INFORMAL_KEYWORDS:
        if kw.lower() in s:
            return SAVE_INFORMAL, "informal_order"
    return None


def build_filepath(folder: Path, timestamp: str, filename: str) -> Path:
    name, ext = os.path.splitext(filename)
    filepath = folder / f"{timestamp}_{name}{ext}"
    counter = 1
    while filepath.exists():
        filepath = folder / f"{timestamp}_{name}_{counter}{ext}"
        counter += 1
    return filepath


def sanitize(text: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in text)


def save_attachment(filepath: Path, source: str, sender: str,
                    subject: str, received_at: datetime, doc_type: str,
                    data: bytes = None) -> int | None:
    if data is not None:
        filepath.write_bytes(data)
    if doc_type == "invoice":
        row_id = insert_invoice(
            file_path=str(filepath), source=source, sender=sender,
            subject=subject, received_at=received_at,
        )
    else:
        row_id = insert_order(
            file_path=str(filepath), source=source, sender=sender,
            subject=subject, received_at=received_at, doc_type=doc_type,
        )
    if row_id is None:
        filepath.unlink()
        print(f"  DUPLICATE — skipped: {filepath.name}")
    else:
        print(f"  Saved attachment: {filepath} (DB id={row_id})")
    return row_id


def save_body(body: str, folder: Path, timestamp: str, subject: str,
              source: str, sender: str, received_at: datetime, doc_type: str) -> int | None:
    body_path = build_filepath(folder, timestamp, f"{sanitize(subject)}.txt")
    body_path.write_text(body, encoding="utf-8")
    row_id = insert_order(
        file_path=str(body_path), source=source, sender=sender,
        subject=subject, received_at=received_at, doc_type=doc_type,
    )
    if row_id is None:
        body_path.unlink()
        print("  DUPLICATE — body already exists, skipped.")
    else:
        print(f"  Saved email body: {body_path} (DB id={row_id})")
    return row_id
