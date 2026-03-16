def validate_purchase_order(data: dict) -> tuple[bool, list[str]]:
    issues = []

    # Without client → can't create Sale Order in Odoo
    if not data.get('client_name'):
        issues.append("Missing client_name")

    # Without line_items → nothing to put in the Sale Order
    line_items = data.get('line_items')
    if not line_items or len(line_items) == 0:
        issues.append("line_items is empty")

    return len(issues) == 0, issues