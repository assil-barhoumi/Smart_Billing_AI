import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odoo_config import connect, DB, PASSWORD
from db.db import update_supplier_odoo_id

uid, models = connect()


def _v(val):
    return val if val is not None else False


def _search(model, domain, fields, limit=1):
    ids = models.execute_kw(DB, uid, PASSWORD, model, 'search', [domain], {'limit': limit})
    if not ids:
        return None
    records = models.execute_kw(DB, uid, PASSWORD, model, 'read', [ids], {'fields': fields})
    return records[0] if limit == 1 else records


def _create(model, vals):
    return models.execute_kw(DB, uid, PASSWORD, model, 'create', [vals])


def get_or_create_supplier(name: str, street: str = None, country: str = None) -> int:
    """Find existing supplier or create a new one. Returns partner_id."""
    partner = _search('res.partner', [['name', 'ilike', name], ['supplier_rank', '>', 0]], ['id', 'name'])
    if partner:
        return partner['id']

    vals = {
        'name'         : name,
        'supplier_rank': 1,
        'comment'      : 'Auto-created by AutomatingSales',
    }
    if street:  vals['street']  = street
    if country: vals['country'] = country

    return _create('res.partner', vals)


def get_or_create_product(description: str, item_type: str = 'consu') -> int:
    """Find existing product or create a generic one. Returns product_id."""
    product = _search('product.product',
                      [['name', 'ilike', description]],
                      ['id', 'name'])
    if product:
        return product['id']

    product_id = _create('product.product', {
        'name'       : description,
        'type'       : item_type,
        'purchase_ok': True,
    })
    return product_id


def push_invoice(invoice: dict) -> int:
    """
    Push a validated invoice to Odoo as a vendor bill.
    Returns the Odoo account.move ID.
    """
    supplier_name = invoice.get('supplier_name') or 'Unknown Supplier'
    extracted     = invoice.get('extracted_json') or {}
    partner_id    = get_or_create_supplier(
        name    = supplier_name,
        street  = extracted.get('supplier_street'),
        country = extracted.get('supplier_country'),
    )
    update_supplier_odoo_id(supplier_name, partner_id)

    # Build invoice lines
    line_items = []
    for item in extracted.get('line_items') or []:
        description = item.get('description') or 'Service'
        raw_type  = item.get('item_type') or 'service'
        item_type = 'consu' if raw_type == 'product' else 'service'
        product_id  = get_or_create_product(description, item_type)
        line_items.append((0, 0, {
            'product_id' : product_id,
            'name'       : _v(description),
            'quantity'   : _v(item.get('quantity')) or 1.0,
            'price_unit' : _v(item.get('unit_price')) or _v(invoice.get('total_ht')) or 0.0,
        }))

    # Fallback: if no line items, create one generic line
    if not line_items:
        line_items.append((0, 0, {
            'name'      : supplier_name,
            'quantity'  : 1.0,
            'price_unit': _v(invoice.get('total_ht')) or 0.0,
        }))

    odoo_id = _create('account.move', {
        'move_type'      : 'in_invoice',
        'partner_id'     : partner_id,
        'invoice_date'   : _v(str(invoice['invoice_date']) if invoice.get('invoice_date') else None),
        'invoice_date_due': _v(str(invoice['due_date']) if invoice.get('due_date') else None),
        'ref'            : _v(invoice.get('invoice_number')),
        'invoice_line_ids': line_items,
    })

    return odoo_id
