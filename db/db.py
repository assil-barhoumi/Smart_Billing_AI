import psycopg2
import hashlib
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_CONFIG = {
    "host"    : os.getenv("DB_HOST"),
    "port"    : os.getenv("DB_PORT"),
    "dbname"  : os.getenv("DB_NAME"),
    "user"    : os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# Acquisition

def insert_order(file_path: str, source: str, sender: str, subject: str,
                 received_at, doc_type: str = None) -> int | None:
    """
    Insert a new order at acquisition time. Returns the row id.
    Returns None if the file content already exists (duplicate hash).
    """
    file_hash = sha256(file_path)
    sql = """
        INSERT INTO orders (file_path, source, sender, subject, received_at, file_hash, doc_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_hash) DO NOTHING
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path, source, sender, subject, received_at, file_hash, doc_type))
            row = cur.fetchone()
            return row[0] if row else None

# Push

def update_push(file_path: str, status: str, odoo_order_id: int = None,
                needs_review: bool = False, error_message: str = None) -> None:
    """Update order row after Odoo push attempt."""
    sql = """
        UPDATE orders
        SET status        = %s,
            odoo_order_id = %s,
            needs_review  = %s,
            error_message = %s
        WHERE file_path = %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, odoo_order_id, needs_review, error_message, file_path))


def get_status(file_path: str) -> str | None:
    """Get current status for a given file path."""
    sql = "SELECT status FROM orders WHERE file_path = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path,))
            row = cur.fetchone()
            return row[0] if row else None


def get_sender(file_path: str) -> str | None:
    """Get sender email/phone for a given file path."""
    sql = "SELECT sender FROM orders WHERE file_path = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path,))
            row = cur.fetchone()
            return row[0] if row else None


# Invoice acquisition

def insert_invoice(file_path: str, source: str, sender: str, subject: str,
                   received_at) -> int | None:
    """
    Insert a new invoice at acquisition time. Returns the row id.
    Returns None if the file content already exists (duplicate hash).
    """
    file_hash = sha256(file_path)
    sql = """
        INSERT INTO invoices (file_path, source, sender, subject, received_at, file_hash)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_hash) DO NOTHING
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path, source, sender, subject, received_at, file_hash))
            row = cur.fetchone()
            return row[0] if row else None


def update_invoice_extraction(file_path: str, extracted_json: dict,
                               confidence: float, supplier_name: str = None,
                               invoice_number: str = None, invoice_date=None,
                               due_date=None, total_ht: float = None,
                               vat_amount: float = None, total_ttc: float = None,
                               currency: str = None) -> None:
    """Store extraction result and update invoice fields."""
    sql = """
        UPDATE invoices
        SET extracted_json   = %s,
            confidence_score = %s,
            supplier_name    = %s,
            invoice_number   = %s,
            invoice_date     = %s,
            due_date         = %s,
            total_ht         = %s,
            vat_amount       = %s,
            total_ttc        = %s,
            currency         = %s,
            status           = 'pending'
        WHERE file_path = %s;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                json.dumps(extracted_json, ensure_ascii=False),
                confidence,
                supplier_name,
                invoice_number,
                invoice_date,
                due_date,
                total_ht,
                vat_amount,
                total_ttc,
                currency,
                file_path,
            ))


# Extraction

def update_extraction(file_path: str, doc_type: str, extracted_json: dict,
                      is_valid: bool, confidence: float = None) -> None:
    """Store LLM extraction result and move status to valid/invalid."""
    sql = """
        UPDATE orders
        SET doc_type         = %s,
            extracted_json   = %s,
            confidence_score = %s,
            status           = %s
        WHERE file_path = %s;
    """
    status = "valid" if is_valid else "invalid"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                doc_type,
                json.dumps(extracted_json, ensure_ascii=False),
                confidence,
                status,
                file_path,
            ))
