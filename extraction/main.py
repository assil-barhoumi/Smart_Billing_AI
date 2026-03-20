import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm          import call_gemini_po
from llm_informal import call_gemini_informal
from checker      import validate_purchase_order
from db.db        import update_extraction

ROOT                = Path(__file__).resolve().parent.parent
SUPPORTED_PO        = {".jpg", ".jpeg", ".png", ".pdf"}
SUPPORTED_INFORMAL  = {".txt", ".csv", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".pdf"}
PURCHASE_ORDERS_DIR = ROOT / "orders" / "purchase_orders"
INFORMAL_ORDERS_DIR = ROOT / "orders" / "informal_orders"
RESULTS_PO          = ROOT / "results" / "purchase_order"
RESULTS_INFORMAL    = ROOT / "results" / "informal_order"


# ---------- Helpers ----------
def process(file_path: Path, llm_fn, doc_type: str) -> dict:
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


# ---------- Runners ----------
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

    files = sorted(f for f in input_dir.iterdir() if f.suffix.lower() in supported)

    if not files:
        print(f"No supported files found in '{input_dir}/'")
        sys.exit(0)

    print(f"\n[Batch mode — {mode}] Found {len(files)} file(s) in '{input_dir}/'")

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
        print("  python main.py po <file>           # single purchase order")
        print("  python main.py informal <file>     # single informal order")
        sys.exit(0)

    mode = args[0]
    if mode not in {"po", "informal"}:
        print(f"Error: Unknown mode '{mode}'. Use 'po' or 'informal'.")
        sys.exit(1)

    if len(args) == 2:
        run_single(args[1], mode)
    else:
        run_batch(mode)