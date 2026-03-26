import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_config import connect, DB, PASSWORD

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


# --- Partner ---

def find_partner_by_name(name: str) -> dict | None:
    return _search('res.partner', [['name', '=', name], ['customer_rank', '>', 0]], ['id', 'name', 'email'])


def find_partner_by_email(email: str) -> dict | None:
    return _search('res.partner', [['email', '=', email]], ['id', 'name', 'email'])


def get_or_create_partner(name: str, email=None, phone=None) -> tuple[int, bool]:
    """Returns (partner_id, is_new)."""
    partner = find_partner_by_name(name)
    if partner:
        return partner['id'], False

    tag = _search('res.partner.category', [['name', '=', 'New Client - Pending Verification']], ['id'])
    tag_id = tag['id'] if tag else _create('res.partner.category', {'name': 'New Client - Pending Verification'})

    partner_id = _create('res.partner', {
        'name'         : _v(name),
        'email'        : _v(email),
        'phone'        : _v(phone),
        'customer_rank': 1,
        'comment'      : 'Auto-created — pending verification',
        'category_id'  : [(4, tag_id)],
    })
    return partner_id, True


# --- Product ---

def find_product_by_name(description: str) -> dict | None:
    return _search('product.product',
                   [['name', 'ilike', description], ['sale_ok', '=', True]],
                   ['id', 'name', 'list_price'])


# --- Quotation ---

def create_quotation(partner_id: int, date: str, lines: list) -> int:
    """Create a draft sale.order with line items."""
    order_lines = []
    for line in lines:
        order_lines.append((0, 0, {
            'product_id'     : line.get('product_id') or False,
            'name'           : _v(line['description']),
            'product_uom_qty': _v(line['quantity']),
            'price_unit'     : _v(line['unit_price']),
        }))
    return _create('sale.order', {
        'partner_id': partner_id,
        'date_order': _v(date),
        'order_line': order_lines,
    })