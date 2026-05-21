"""
Invoice Pipeline — Entry Point

Usage:
  # Single file:
  python invoices_pipeline/pipeline.py invoices/facture.pdf

  # Process all invoices:
  python invoices_pipeline/pipeline.py --all
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoices_pipeline.processor import route, INVOICE_DIR

INVOICE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


def process(file_path: str) -> dict:
    """Process a single invoice file."""
    path = Path(file_path)
    if not path.exists():
        print(f"[Pipeline] Error: file not found: {file_path}")
        return {"status": "error", "message": f"file not found: {file_path}"}

    result = route(str(path.resolve()), doc_type="invoice")

    print("\n" + "=" * 50)
    print("PIPELINE RESULT:")
    print(json.dumps(result, default=str, indent=2))
    print("=" * 50)

    return result


def process_all() -> list[dict]:
    """Process all invoice files in invoices/."""
    files = []
    for ext in INVOICE_EXTENSIONS:
        files += [p for p in INVOICE_DIR.glob(f"*{ext}")]

    if not files:
        print("[Pipeline] No invoice files found.")
        return []

    print(f"\n[Pipeline] Found {len(files)} invoice(s) to process.\n")

    results = []
    for i, path in enumerate(files, 1):
        print(f"\n[Pipeline] ── File {i}/{len(files)}: {path.name}")
        try:
            result = route(str(path.resolve()), doc_type="invoice")
        except Exception as e:
            print(f"  [Pipeline] ERROR: {e}")
            result = {"status": "error", "message": str(e)}
        results.append({"file": path.name, **result})
        if i < len(files):
            time.sleep(3)

        print("  Result:", json.dumps(
            {k: v for k, v in result.items() if k != "extracted"},
            default=str, indent=4
        ))

    print("\n" + "=" * 50)
    print(f"BATCH SUMMARY — {len(results)} invoice(s) processed:")
    for r in results:
        print(f"  {r['file']:40s} → {r.get('status', '?')}")
    print("=" * 50)

    return results


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if "--all" in args:
        process_all()
    else:
        process(args[0])
