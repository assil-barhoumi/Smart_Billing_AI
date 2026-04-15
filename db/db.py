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
            status           = 'extracted'
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


def get_invoice_status(file_path: str) -> str | None:
    """Get current status for a given invoice file path."""
    sql = "SELECT status FROM invoices WHERE file_path = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path,))
            row = cur.fetchone()
            return row[0] if row else None


# Supplier registry

def find_supplier(name: str) -> dict | None:
    """Find supplier by case-insensitive name. Returns supplier dict or None."""
    sql = "SELECT * FROM suppliers WHERE LOWER(name) = LOWER(%s);"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name.strip(),))
            row = cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))


def insert_supplier(name: str, street: str = None, country: str = None,
                    email: str = None, odoo_partner_id: int = None) -> int:
    """Insert a new supplier into the registry. Returns supplier ID."""
    sql = """
        INSERT INTO suppliers (name, street, country, email, odoo_partner_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE
            SET last_seen     = NOW(),
                invoice_count = suppliers.invoice_count + 1
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name.strip(), street, country,
                              email, odoo_partner_id))
            return cur.fetchone()[0]


def update_supplier_odoo_id(name: str, odoo_partner_id: int) -> None:
    """Save Odoo partner ID to supplier registry."""
    sql = "UPDATE suppliers SET odoo_partner_id = %s WHERE LOWER(name) = LOWER(%s);"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (odoo_partner_id, name.strip()))


# Invoice validation

def get_invoice(invoice_id: int) -> dict | None:
    """Get a single invoice by ID."""
    sql = "SELECT * FROM invoices WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (invoice_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))


def get_invoices(status: str = None) -> list[dict]:
    """Get all invoices, optionally filtered by status."""
    sql = "SELECT * FROM invoices"
    params = []
    if status:
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY received_at DESC;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def validate_invoice(invoice_id: int, corrections: dict = None) -> None:
    """Mark invoice as validated, optionally applying field corrections.
    Also saves/updates the supplier in the registry."""
    from datetime import datetime
    fields = {
        "status": "validated",
        "validated_at": datetime.now(),
    }
    if corrections:
        allowed = {"supplier_name", "invoice_number", "invoice_date", "due_date",
                   "total_ht", "vat_amount", "total_ttc", "currency"}
        for k, v in corrections.items():
            if k in allowed:
                fields[k] = v

    set_clause = ", ".join(f"{k} = %s" for k in fields)
    sql = f"UPDATE invoices SET {set_clause} WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (*fields.values(), invoice_id))

    # Save supplier to registry after validation
    invoice = get_invoice(invoice_id)
    supplier_name = fields.get("supplier_name") or invoice.get("supplier_name")
    if supplier_name:
        extracted = invoice.get("extracted_json") or {}
        insert_supplier(
            name    = supplier_name,
            street  = extracted.get("supplier_street"),
            country = extracted.get("supplier_country"),
        )


def reject_invoice(invoice_id: int) -> None:
    """Mark invoice as rejected."""
    sql = "UPDATE invoices SET status = 'rejected' WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (invoice_id,))


def update_invoice_odoo_id(invoice_id: int, odoo_invoice_id: int) -> None:
    """Save Odoo vendor bill ID after successful push."""
    sql = "UPDATE invoices SET odoo_invoice_id = %s WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (odoo_invoice_id, invoice_id))


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
