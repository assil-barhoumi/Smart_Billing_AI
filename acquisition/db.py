import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------- Configuration ----------
DB_CONFIG = {
    "host"    : os.getenv("DB_HOST"),
    "port"    : os.getenv("DB_PORT"),
    "dbname"  : os.getenv("DB_NAME"),
    "user"    : os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def get_connection():
    """Create and return a new database connection."""
    return psycopg2.connect(**DB_CONFIG)


def insert_order(file_path: str, source: str, sender_email: str, subject: str, received_at) -> int:
    """
    Insert a new order record into the orders table.
    Returns the inserted row id.
    """
    sql = """
        INSERT INTO orders (file_path, source, sender_email, subject, received_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (file_path, source, sender_email, subject, received_at))
            row_id = cur.fetchone()[0]
    return row_id