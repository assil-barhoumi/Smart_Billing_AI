from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from po_collector import build_filepath, SAVE_FOLDER

def test_collision():
    print("Running collision test...")

    path1 = build_filepath(SAVE_FOLDER, "20260306_203922", "invoice.pdf")
    path1.touch()
    print(f"  File 1: {path1.name}")

    path2 = build_filepath(SAVE_FOLDER, "20260306_203922", "invoice.pdf")
    path2.touch()
    print(f"  File 2: {path2.name}")

    path3 = build_filepath(SAVE_FOLDER, "20260306_203922", "invoice.pdf")
    path3.touch()
    print(f"  File 3: {path3.name}")

    path1.unlink()
    path2.unlink()
    path3.unlink()
    print("Collision test passed ✅")


if __name__ == "__main__":
    test_collision()