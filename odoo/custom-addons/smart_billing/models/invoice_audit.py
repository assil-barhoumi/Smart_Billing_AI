import json
import logging
import psycopg2
import psycopg2.extras
from pathlib import Path

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

_PG = dict(host='host.docker.internal', port=5433, dbname='smart_billing',
           user='postgres', password='postgres')

ADMIN_STATUSES = [
    ('pending',  'Pending Review'),
    ('pushed',   'Pushed to Odoo'),
    ('rejected', 'Rejected'),
]
TERMINAL = {'pushed', 'rejected'}


def _pg_connect():
    return psycopg2.connect(**_PG)


class SmartBillingInvoice(models.Model):
    _name        = 'smart.billing.invoice'
    _description = 'Smart Billing – Invoice Review'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'create_date desc'

    pipeline_invoice_id = fields.Integer(string='Pipeline ID', readonly=True, index=True)

    file_name      = fields.Char(readonly=True)
    file_path      = fields.Char(readonly=True)
    supplier_name  = fields.Char()
    invoice_number = fields.Char()
    invoice_date   = fields.Date()
    total_ht       = fields.Float(digits=(16, 4))
    vat_amount     = fields.Float(digits=(16, 4))
    total_ttc      = fields.Float(digits=(16, 4))
    currency_code  = fields.Char(size=10)
    confidence     = fields.Float(digits=(4, 3), readonly=True)
    extracted_json = fields.Text(readonly=True)
    invoice_image     = fields.Binary(readonly=True, string='Invoice Preview', attachment=True)
    has_invoice_image = fields.Boolean(readonly=True, default=False)

    check_supplier = fields.Boolean(string='Supplier Known', readonly=True)
    check_amounts  = fields.Boolean(string='Amounts Valid',  readonly=True)
    check_rules    = fields.Boolean(string='Rules Passed',   readonly=True)

    pipeline_status = fields.Selection(ADMIN_STATUSES, default='pending', index=True, tracking=True)
    odoo_invoice_id = fields.Integer(readonly=True)

    def _derive_checks(self, supplier, total_ht, vat, total_ttc, confidence):
        partner_exists = bool(
            supplier and supplier != 'Unknown' and
            self.env['res.partner'].search([('name', 'ilike', supplier)], limit=1)
        )
        amounts_ok = total_ttc > 0 and abs(round(total_ht + vat, 2) - round(total_ttc, 2)) < 0.01
        return {
            'check_supplier': partner_exists,
            'check_amounts' : amounts_ok,
            'check_rules'   : confidence >= 0.7,
        }

    @api.model
    def _upsert_from_row(self, row):
        existing = self.search([('pipeline_invoice_id', '=', row['id'])], limit=1)
        if existing and existing.pipeline_status in TERMINAL:
            return existing.id

        file_path  = row.get('file_path') or ''
        supplier   = row.get('supplier_name') or 'Unknown'
        total_ht   = float(row.get('total_ht')        or 0)
        vat        = float(row.get('vat_amount')       or 0)
        total_ttc  = float(row.get('total_ttc')        or 0)
        confidence = float(row.get('confidence_score') or 0)

        vals = {
            'pipeline_invoice_id': row['id'],
            'file_path'          : file_path,
            'file_name'          : Path(file_path).name if file_path else '',
            'supplier_name'      : supplier,
            'invoice_number'     : row.get('invoice_number') or '',
            'total_ht'           : total_ht,
            'vat_amount'         : vat,
            'total_ttc'          : total_ttc,
            'currency_code'      : row.get('currency')       or '',
            'confidence'         : confidence,
            'extracted_json'     : json.dumps(row.get('extracted_json') or {}),
            **self._derive_checks(supplier, total_ht, vat, total_ttc, confidence),
        }
        if row.get('invoice_date'):
            vals['invoice_date'] = row['invoice_date']

        if existing:
            existing.write(vals)
            return existing.id
        vals['pipeline_status'] = 'pending'
        return self.create(vals).id

    @api.model
    def sync_from_pipeline(self):
        try:
            conn = _pg_connect()
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("""
                    SELECT id, file_path,
                           supplier_name, invoice_number, invoice_date,
                           total_ht, vat_amount, total_ttc, currency,
                           confidence_score, extracted_json
                    FROM   invoices
                    WHERE  status NOT IN ('pending', 'pushed')
                    ORDER  BY id DESC
                    LIMIT  500
                """)
                rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:
            _logger.warning('SmartBilling sync: %s', e)
            return 0

        synced = sum(1 for row in rows if self._upsert_from_row(dict(row)))
        _logger.info('SmartBilling: synced %d invoice(s)', synced)
        return synced

    def _pg_update_status(self, pg_id, status, odoo_invoice_id=None):
        if not pg_id:
            return
        try:
            conn = _pg_connect()
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE invoices SET status=%s, odoo_invoice_id=COALESCE(%s, odoo_invoice_id) WHERE id=%s",
                    (status, odoo_invoice_id, pg_id),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            _logger.warning('SmartBilling write-back: %s', e)

    def action_reject(self):
        for rec in self.filtered(lambda r: r.pipeline_status not in TERMINAL):
            rec.write({'pipeline_status': 'rejected'})
            self._pg_update_status(rec.pipeline_invoice_id, 'rejected')

    def action_push_to_odoo(self):
        pushed = self.env['account.move']
        for rec in self.filtered(lambda r: r.pipeline_status == 'pending'):
            partner = self._get_or_create_partner(rec.supplier_name)
            move = self.env['account.move'].create({
                'move_type'       : 'in_invoice',
                'partner_id'      : partner.id,
                'ref'             : rec.invoice_number,
                'invoice_date'    : rec.invoice_date,
                'invoice_line_ids': self._build_invoice_lines(rec),
                'narration'       : f'Smart Billing | {rec.file_name}',
            })
            rec.write({'pipeline_status': 'pushed', 'odoo_invoice_id': move.id})
            self._pg_update_status(rec.pipeline_invoice_id, 'pushed', move.id)
            pushed |= move

        if pushed:
            return {
                'type'     : 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_ids'  : pushed.ids,
                'view_mode': 'list,form',
                'target'   : 'current',
            }

    @api.model
    def receive_audit_result(self, audit_data):
        file_path = audit_data.get('file_path', '')
        if not file_path:
            return 0

        try:
            conn = _pg_connect()
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("""
                    SELECT id, file_path,
                           supplier_name, invoice_number, invoice_date,
                           total_ht, vat_amount, total_ttc, currency,
                           confidence_score, extracted_json
                    FROM   invoices
                    WHERE  file_path = %s
                    LIMIT  1
                """, (file_path,))
                row = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:
            _logger.warning('SmartBilling bridge: %s', e)
            return 0

        if not row:
            return 0

        record_id = self._upsert_from_row(dict(row))
        if record_id:
            image = audit_data.get('image_data') or False
            self.browse(record_id).write({
                'invoice_image'   : image,
                'has_invoice_image': bool(image),
            })
        return record_id

    def _get_or_create_partner(self, name):
        partner = self.env['res.partner'].search([('name', 'ilike', name)], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({'name': name, 'supplier_rank': 1})
        return partner

    def _build_invoice_lines(self, rec):
        account = self.env['account.account'].search(
            [('account_type', 'in', ['expense', 'expense_direct_cost'])], limit=1
        )
        account_id = account.id if account else False

        def make_line(name, qty=1.0, price=0.0):
            line = {'name': name, 'quantity': qty, 'price_unit': price}
            if account_id:
                line['account_id'] = account_id
            return (0, 0, line)

        try:
            items = json.loads(rec.extracted_json or '{}').get('line_items', [])
            lines = [make_line(
                item.get('description', 'Item'),
                float(item.get('quantity',   1.0)),
                float(item.get('unit_price', 0.0)),
            ) for item in items]
        except (json.JSONDecodeError, TypeError, KeyError):
            lines = []

        return lines or [make_line(
            f'Invoice {rec.invoice_number or ""}',
            price=rec.total_ht or rec.total_ttc,
        )]
