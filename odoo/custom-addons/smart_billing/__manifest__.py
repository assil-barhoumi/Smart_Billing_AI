{
    'name': 'Smart Billing',
    'author': 'Assil',
    'version': '1.0',
    'summary': 'Invoice pipeline audit — review, validate and push to Odoo',
    'category': 'Accounting',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/invoice_audit_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_billing/static/src/css/smart_billing.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
