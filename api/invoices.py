import sys
from pathlib import Path
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.db import get_invoice, get_invoices, validate_invoice, reject_invoice, update_invoice_odoo_id

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ---------- Schemas ----------
class ValidateRequest(BaseModel):
    supplier_name:  Optional[str]   = None
    invoice_number: Optional[str]   = None
    invoice_date:   Optional[date]  = None
    due_date:       Optional[date]  = None
    total_ht:       Optional[float] = None
    vat_amount:     Optional[float] = None
    total_ttc:      Optional[float] = None
    currency:       Optional[str]   = None


# ---------- Endpoints ----------
@router.get("/")
def list_invoices(status: Optional[str] = None):
    """List all invoices, optionally filtered by status."""
    return get_invoices(status=status)


@router.get("/{invoice_id}")
def get_one_invoice(invoice_id: int):
    """Get a single invoice by ID."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.put("/{invoice_id}/validate")
def validate(invoice_id: int, body: ValidateRequest = None):
    """Validate an invoice, optionally correcting extracted fields."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice["status"] not in ("extracted",):
        raise HTTPException(status_code=400, detail=f"Cannot validate invoice with status '{invoice['status']}'")

    corrections = body.model_dump(exclude_none=True) if body else {}
    validate_invoice(invoice_id, corrections)
    return {"message": "Invoice validated successfully", "id": invoice_id}


@router.put("/{invoice_id}/reject")
def reject(invoice_id: int):
    """Reject an invoice."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice["status"] not in ("extracted",):
        raise HTTPException(status_code=400, detail=f"Cannot reject invoice with status '{invoice['status']}'")

    reject_invoice(invoice_id)
    return {"message": "Invoice rejected", "id": invoice_id}


@router.post("/{invoice_id}/push-odoo")
def push_to_odoo(invoice_id: int):
    """Push a validated invoice to Odoo as a vendor bill."""
    from odoo.push_invoice_to_odoo import push_invoice

    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice["status"] != "validated":
        raise HTTPException(status_code=400, detail="Only validated invoices can be pushed to Odoo")
    if invoice["odoo_invoice_id"]:
        raise HTTPException(status_code=400, detail=f"Already pushed to Odoo (id={invoice['odoo_invoice_id']})")

    try:
        odoo_id = push_invoice(invoice)
        update_invoice_odoo_id(invoice_id, odoo_id)
        return {"message": "Invoice pushed to Odoo successfully", "odoo_invoice_id": odoo_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Odoo push failed: {str(e)}")
