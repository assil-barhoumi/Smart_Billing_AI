import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm          import call_gemini_po
from llm_informal import call_gemini_informal
from llm_invoice  import call_groq_invoice as call_invoice    # switch to call_ollama_invoice in production
from checker      import validate_purchase_order
from db.db        import update_extraction, update_invoice_extraction, get_status

ROOT                = Path(__file__).resolve().parent.parent
SUPPORTED_PO        = {".jpg", ".jpeg", ".png", ".pdf"}
SUPPORTED_INFORMAL  = {".txt", ".csv", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".pdf"}
SUPPORTED_INVOICE   = {".jpg", ".jpeg", ".png", ".pdf"}
PURCHASE_ORDERS_DIR = ROOT / "orders" / "purchase_orders"
INFORMAL_ORDERS_DIR = ROOT / "orders" / "informal_orders"
INVOICES_DIR        = ROOT / "invoices"
RESULTS_PO          = ROOT / "results" / "purchase_order"
RESULTS_INFORMAL    = ROOT / "results" / "informal_order"
RESULTS_INVOICE     = ROOT / "results" / "invoice"


# ---------- Helpers ----------
def process(file_path: Path, llm_fn, doc_type: str) -> dict:
    file_path = file_path.resolve()
    print(f"  [LLM] Sending {file_path.name} to Gemini...")
    extracted  = llm_fn(str(file_path))
    confidence = extracted.pop("confidence", None)
    is_valid, issues = validate_purchase_order(extracted)
    update_extraction(str(file_path), doc_type, extracted, is_valid, confidence)
    return {
        "file":       file_path.name,
        "is_valid":   is_valid,
        "confidence": confidence,
        "issues":     issues,
        "data":       extracted,
    }


def save_result(result: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(results: list[dict], mode: str):
    valid   = [r for r in results if r["is_valid"]]
    invalid = [r for r in results if not r["is_valid"]]

    print("\n" + "=" * 50)
    print(f"SUMMARY [{mode}]: {len(results)} file(s) processed")
    print(f"  ✅ Valid:   {len(valid)}")
    print(f"  ❌ Invalid: {len(invalid)}")

    if invalid:
        print("\nInvalid orders:")
        for r in invalid:
            print(f"  • {r['file']}")
            for issue in r["issues"]:
                print(f"      - {issue}")

    print("\nConfidence scores:")
    for r in results:
        conf = r.get("confidence")
        flag = " ⚠️ LOW" if conf is not None and conf < 0.8 else ""
        print(f"  • {r['file']}: {conf}{flag}")
    print("=" * 50)


# ---------- Invoice process ----------
def process_invoice(file_path: Path) -> dict:
    file_path = file_path.resolve()
    print(f"  [LLM] Sending {file_path.name} to Groq...")
    extracted  = call_invoice(str(file_path))
    confidence = extracted.pop("confidence", None)

    update_invoice_extraction(
        file_path      = str(file_path),
        extracted_json = extracted,
        confidence     = confidence,
        supplier_name  = extracted.get("supplier_name"),
        invoice_number = extracted.get("invoice_number"),
        invoice_date   = extracted.get("date"),
        total_ht       = extracted.get("total_ht"),
        vat_amount     = extracted.get("vat_amount"),
        total_ttc      = extracted.get("total_ttc"),
        currency       = extracted.get("currency"),
    )
    return {
        "file":       file_path.name,
        "confidence": confidence,
        "data":       extracted,
    }


# ---------- Runners ----------
def run_invoice_batch():
    from db.db import get_invoice_status, insert_invoice
    from datetime import datetime

    all_files = sorted(
        f for f in INVOICES_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED_INVOICE
        and f.name != ".gitkeep"
    )

    files = []
    for f in all_files:
        status = get_invoice_status(str(f.resolve()))
        if status is None:
            row_id = insert_invoice(str(f.resolve()), source="manual",
                                    sender=None, subject=None, received_at=datetime.now())
            if row_id is None:
                print(f"  DUPLICATE — skipped: {f.name}")
                continue
            files.append(f)
        elif status == "pending":
            files.append(f)

    if not files:
        print(f"No new invoices to process in '{INVOICES_DIR}/'")
        sys.exit(0)

    print(f"\n[Invoice batch] Found {len(files)} file(s) in '{INVOICES_DIR}/'")
    results = []
    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        try:
            result = process_invoice(file_path)
        except Exception as e:
            print(f"  [ERROR] {e}")
            result = {"file": file_path.name, "confidence": None, "data": {}}
        out_path = RESULTS_INVOICE / f"{file_path.stem}.json"
        save_result(result, out_path)
        print(f"  Confidence : {result.get('confidence')}")
        print(f"  Supplier   : {result['data'].get('supplier_name')}")
        print(f"  Invoice No.: {result['data'].get('invoice_number')}")
        print(f"  Total TTC  : {result['data'].get('total_ttc')}")
        print(f"  [Saved] {out_path}")
        results.append(result)

    print(f"\n{'='*50}")
    print(f"SUMMARY [invoice]: {len(results)} file(s) processed")
    for r in results:
        print(f"  • {r['file']}: confidence={r.get('confidence')}")
    print("=" * 50)


def run_batch(mode: str):
    if mode == "po":
        input_dir   = PURCHASE_ORDERS_DIR
        results_dir = RESULTS_PO
        supported   = SUPPORTED_PO
        process_fn  = lambda f: process(f, call_gemini_po, "purchase_order")
    else:
        input_dir   = INFORMAL_ORDERS_DIR
        results_dir = RESULTS_INFORMAL
        supported   = SUPPORTED_INFORMAL
        process_fn  = lambda f: process(f, call_gemini_informal, "informal_order")

    if not input_dir.exists():
        print(f"Error: '{input_dir}' folder not found.")
        sys.exit(1)

    files = sorted(
        f for f in input_dir.iterdir()
        if f.suffix.lower() in supported
        and get_status(str(f.resolve())) not in ("valid", "invalid", "pushed", "needs_review")
    )

    if not files:
        print(f"No new files to process in '{input_dir}/'")
        sys.exit(0)

    print(f"\n[Batch mode — {mode}] Found {len(files)} new file(s) in '{input_dir}/'")

    results = []
    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        try:
            result = process_fn(file_path)
        except Exception as e:
            print(f"  [ERROR] {e}")
            result = {
                "file":     file_path.name,
                "is_valid": False,
                "issues":   [f"Processing error: {str(e)}"],
                "data":     {},
            }
        out_path = results_dir / f"{file_path.stem}.json"
        save_result(result, out_path)
        print(f"  [Saved] {out_path}")
        results.append(result)

    print_summary(results, mode)


def run_single(file_path: str, mode: str):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    supported   = SUPPORTED_PO   if mode == "po" else SUPPORTED_INFORMAL
    results_dir = RESULTS_PO     if mode == "po" else RESULTS_INFORMAL
    process_fn  = (lambda f: process(f, call_gemini_po, "purchase_order")) if mode == "po" else (lambda f: process(f, call_gemini_informal, "informal_order"))

    if path.suffix.lower() not in supported:
        print(f"Error: Unsupported format '{path.suffix}' for mode '{mode}'.")
        sys.exit(1)

    print(f"\n[Single mode — {mode}] Processing: {path.name}")
    result   = process_fn(path)
    out_path = results_dir / f"{path.stem}.json"
    save_result(result, out_path)
    print(f"  [Saved] {out_path}")
    print_summary([result], mode)


# ---------- Entry point ----------
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python main.py po                  # batch all purchase orders")
        print("  python main.py informal            # batch all informal orders")
        print("  python main.py invoice             # batch all invoices")
        print("  python main.py po <file>           # single purchase order")
        print("  python main.py informal <file>     # single informal order")
        sys.exit(0)

    mode = args[0]
    if mode not in {"po", "informal", "invoice"}:
        print(f"Error: Unknown mode '{mode}'. Use 'po', 'informal', or 'invoice'.")
        sys.exit(1)

    if mode == "invoice":
        run_invoice_batch()
    elif len(args) == 2:
        run_single(args[1], mode)
    else:
        run_batch(mode)