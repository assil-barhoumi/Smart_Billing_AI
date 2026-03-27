import sys
import subprocess
from pathlib import Path

ROOT         = Path(__file__).resolve().parent
INFORMAL_DIR = ROOT / "orders" / "informal_orders"
RESULTS_DIR  = ROOT / "results" / "informal_order"
SUPPORTED    = {".txt", ".csv", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".pdf"}


def pending_files() -> list:
    return [
        f for f in INFORMAL_DIR.iterdir()
        if f.suffix.lower() in SUPPORTED
        and not (RESULTS_DIR / f"{f.stem}.json").exists()
    ]


if __name__ == "__main__":
    # 1. Collect emails
    before = set(INFORMAL_DIR.iterdir()) if INFORMAL_DIR.exists() else set()
    print("[1] Collecting emails...")
    try:
        subprocess.run([sys.executable, str(ROOT / "acquisition" / "email_collector.py")], check=True)
    except Exception as e:
        print(f"  ❌ Email collection failed: {e}")
    after = set(INFORMAL_DIR.iterdir()) if INFORMAL_DIR.exists() else set()

    new_files = after - before
    if not new_files:
        print("\nNo new files — pipeline done.")
        sys.exit(0)

    print("\n[2] Extracting...")
    try:
        subprocess.run([sys.executable, str(ROOT / "extraction" / "main.py"), "informal"], check=True)
    except Exception as e:
        print(f"  ❌ Extraction failed: {e}")
        sys.exit(1)

    # 3. Push only newly collected files
    print("\n[3] Pushing to Odoo...")
    for f in sorted(new_files):
        if f.suffix.lower() not in SUPPORTED:
            continue
        result_file = RESULTS_DIR / f"{f.stem}.json"
        if not result_file.exists():
            continue
        try:
            subprocess.run([sys.executable, str(ROOT / "odoo" / "push_to_odoo.py"), str(result_file)], check=True)
        except Exception as e:
            print(f"  ❌ Push failed for {result_file.name}: {e}")

    print("\n[Pipeline] Done.")
