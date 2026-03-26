import os
import xmlrpc.client
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL      = f"{os.getenv('ODOO_HOST')}:{os.getenv('ODOO_PORT')}"
DB       = os.getenv("ODOO_DATABASE")
USERNAME = os.getenv("ODOO_USERNAME")
PASSWORD = os.getenv("ODOO_PASSWORD")


def connect():
    """Return (uid, models) for XML-RPC calls."""
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid    = common.authenticate(DB, USERNAME, PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")
    if not uid:
        raise ConnectionError(f"Odoo authentication failed for user '{USERNAME}'")
    return uid, models