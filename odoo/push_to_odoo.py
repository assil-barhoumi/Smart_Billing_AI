import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from odoo_client import (
    get_or_create_partner, create_quotation,
    find_product_by_name, find_partner_by_email,
)
from db.db import update_push, get_sender


def _build_lines(line_items: list) -> tuple[list, list]:
    """Returns (lines, unmatched_descriptions)."""
    lines     = []
    unmatched = []
    for item in line_items:
        description = item.get("description", "")
        quantity    = item.get("quantity") or 1
        unit_price  = item.get("unit_price") or 0
        product_id  = None

        product = find_product_by_name(description)
        if product:
            product_id = product["id"]
            if unit_price == 0:
                unit_price = product["list_price"]
        else:
            unmatched.append(description)

        lines.append({
            "description": description,
            "quantity"   : quantity,
            "unit_price" : unit_price,
            "product_id" : product_id,
        })
    return lines, unmatched


def push_informal(result: dict, file_path: str) -> None:
    data = result["data"]

    try:
        # 1. Resolve partner
        client_name = data.get("client_name")
        partner_id  = None
        is_new      = False

        if client_name:
            partner_id, is_new = get_or_create_partner(
                name  = client_name,
                email = data.get("client_email"),
                phone = data.get("client_phone"),
            )
        else:
            sender = get_sender(file_path)
            if sender:
                partner = find_partner_by_email(sender)
                if partner:
                    partner_id = partner["id"]
                else:
                    partner_id, is_new = get_or_create_partner(
                        name  = sender,
                        email = sender,
                    )
            else:
                update_push(file_path, "push_failed",
                            error_message="No client name and no sender email")
                print("  ❌ No client name and no sender email")
                return

        # 2. Build lines
        lines, unmatched = _build_lines(data.get("line_items", []))

        # 3. Create draft quotation
        order_id = create_quotation(partner_id, data.get("date"), lines)

        # 4. Flag if new client or unmatched products
        reasons = []
        if is_new:    reasons.append("new_client")
        if unmatched: reasons.append(f"unmatched_products: {', '.join(unmatched)}")

        if reasons:
            update_push(file_path, "needs_review", odoo_order_id=order_id,
                        needs_review=True, error_message=", ".join(reasons))
            print(f"  ⚠️ Draft created, flagged: {', '.join(reasons)} (order {order_id})")
        else:
            update_push(file_path, "pushed", odoo_order_id=order_id)
            print(f"  ✅ Draft quotation created: order {order_id}")

    except Exception as e:
        update_push(file_path, "push_failed", error_message=str(e))
        print(f"  ❌ Push failed: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python push_to_odoo.py <result_json>")
        sys.exit(1)

    result_path = Path(sys.argv[1])
    result      = json.loads(result_path.read_text(encoding="utf-8"))

    if not result.get("is_valid"):
        print(f"[SKIP] Invalid extraction: {result_path.name}")
        sys.exit(0)

    ROOT      = Path(__file__).resolve().parent.parent
    file_name = result["file"]
    file_path = str(ROOT / "orders" / "informal_orders" / file_name)

    push_informal(result, file_path)