import os
import re
import requests
from pathlib import Path
from fastapi import FastAPI, Form
from dotenv import load_dotenv
from db import insert_order
from datetime import datetime

# ---------- Load .env ----------
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------- Configuration ----------
SAVE_FOLDER = Path(__file__).resolve().parent.parent / "purchase_orders" / "whatsapp"
SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
DEFAULT_ENCODING = "utf-8"

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

SAVE_FOLDER.mkdir(parents=True, exist_ok=True)

app = FastAPI()


# ---------- Helpers ----------
def build_filepath(folder: Path, filename: str) -> Path:
    """Build a unique file path. Appends a counter suffix only if a collision occurs."""
    name, ext = os.path.splitext(filename)
    filepath = folder / filename
    counter = 1
    while filepath.exists():
        filepath = folder / f"{name}_{counter}{ext}"
        counter += 1
    return filepath


def normalize_extension(content_type: str) -> str:
    """Normalize MIME content type to file extension."""
    mapping = {
        "application/pdf"                                                          : ".pdf",
        "image/jpeg"                                                               : ".jpg",
        "image/jpg"                                                                : ".jpg",
        "image/png"                                                                : ".png",
        "text/plain"                                                               : ".txt",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"       : ".xlsx",
        "application/msword"                                                       : ".doc",
        "application/vnd.ms-excel"                                                 : ".xls",
        "text/csv"                                                                 : ".csv",
    }
    return mapping.get(content_type, None)


def download_media(media_url: str, filepath: Path) -> None:
    """Download media file from Twilio and save to disk."""
    response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    with open(filepath, "wb") as f:
        f.write(response.content)


def is_filename(text: str) -> bool:
    """Check if text looks like a filename (e.g. 'Needs analysis.pdf')."""
    return bool(re.match(r'^[\w\s\-]+\.\w{2,5}$', text.strip()))


# ---------- Webhook ----------
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None),
):
    sender_phone = From.replace("whatsapp:", "")
    received_at = datetime.now()
    timestamp = received_at.strftime(TIMESTAMP_FORMAT)

    print(f"\n  Received WhatsApp message from {sender_phone}")

    # ---------- Handle media attachment ----------
    if NumMedia > 0 and MediaUrl0:
        ext = normalize_extension(MediaContentType0)

        if ext not in SUPPORTED_EXTENSIONS:
            print(f"  SKIPPED — attachment format not supported ({MediaContentType0})")
            return {"status": "skipped", "reason": "unsupported format"}

        filepath = build_filepath(SAVE_FOLDER, f"{timestamp}{ext}")
        download_media(MediaUrl0, filepath)

        row_id = insert_order(
            file_path=str(filepath),
            source="whatsapp",
            sender=sender_phone,
            subject=None if is_filename(Body) else Body.strip() or None,
            received_at=received_at,
        )
        print(f"  Saved attachment: {filepath} (DB id={row_id})")
        return {"status": "saved", "db_id": row_id}

    # ---------- Handle text body only ----------
    else:
        filepath = build_filepath(SAVE_FOLDER, f"{timestamp}.txt")
        with open(filepath, "w", encoding=DEFAULT_ENCODING) as f:
            f.write(Body)

        row_id = insert_order(
            file_path=str(filepath),
            source="whatsapp",
            sender=sender_phone,
            subject=None,
            received_at=received_at,
        )
        print(f"  Saved text message: {filepath} (DB id={row_id})")
        return {"status": "saved", "db_id": row_id}