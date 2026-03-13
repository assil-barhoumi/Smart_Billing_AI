import os
import sys
import json
from pathlib import Path

from llm import call_gemini
from checker import validate_purchase_order

PURCHASE_ORDERS_DIR = Path("purchase_orders")
RESULTS_DIR         = Path("results")
SUPPORTED_FORMATS   = {".jpg", ".jpeg", ".png", ".pdf"}


def process_file(file_path: Path) -> dict:
    print(f"  [LLM] Sending {file_path.name} to Gemini...")
    extracted = call_gemini(str(file_path))
    is_valid, issues = validate_purchase_order(extracted)
    return {
        "file":     file_path.name,
        "is_valid": is_valid,
        "issues":   issues,
        "data":     extracted,
    }


def save_result(result: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def print_summary(results: list[dict]):
    valid   = [r for r in results if r["is_valid"]]
    invalid = [r for r in results if not r["is_valid"]]

    print("\n" + "=" * 50)
    print(f"SUMMARY: {len(results)} purchase order(s) processed")
    print(f"  ✅ Valid:   {len(valid)}")
    print(f"  ❌ Invalid: {len(invalid)}")

    if invalid:
        print("\nInvalid purchase orders:")
        for r in invalid:
            print(f"  • {r['file']}")
            for issue in r["issues"]:
                print(f"      - {issue}")
    print("=" * 50)


def run_single(file_path: str):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        print(f"Error: Unsupported format '{path.suffix}'. Supported: {SUPPORTED_FORMATS}")
        sys.exit(1)

    print(f"\n[Single mode] Processing: {path.name}")
    result = process_file(path)
    output_path = RESULTS_DIR / f"{path.stem}.json"
    save_result(result, output_path)
    print(f"  [Saved] {output_path}")
    print_summary([result])


def run_batch():
    if not PURCHASE_ORDERS_DIR.exists():
        print(f"Error: '{PURCHASE_ORDERS_DIR}' folder not found.")
        sys.exit(1)

    files = sorted(
        f for f in PURCHASE_ORDERS_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED_FORMATS
    )

    if not files:
        print(f"No supported files found in '{PURCHASE_ORDERS_DIR}/'")
        sys.exit(0)

    print(f"\n[Batch mode] Found {len(files)} purchase order(s) in '{PURCHASE_ORDERS_DIR}/'")

    results = []
    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        try:
            result = process_file(file_path)
        except Exception as e:
            print(f"  [ERROR] {e}")
            result = {
                "file":     file_path.name,
                "is_valid": False,
                "issues":   [f"Processing error: {str(e)}"],
                "data":     {},
            }
        output_path = RESULTS_DIR / f"{file_path.stem}.json"
        save_result(result, output_path)
        print(f"  [Saved] {output_path}")
        results.append(result)

    print_summary(results)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run_single(sys.argv[1])
    else:
        run_batch()