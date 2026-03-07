import imaplib
import email
import email.header
import email.utils
from email.message import Message
from datetime import datetime
import os
from pathlib import Path
from dotenv import load_dotenv
from db import insert_order

# ---------- Load .env ----------
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------- Configuration ----------
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

SAVE_FOLDER = Path(__file__).resolve().parent.parent / "purchase_orders"
SUBJECT_KEYWORDS = ["Purchase Order", "Order", "Commande"]
SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
DEFAULT_ENCODING = "utf-8"

SAVE_FOLDER.mkdir(parents=True, exist_ok=True)


# ---------- Helpers ----------
def get_received_at(msg: Message) -> datetime:
    """Extract a datetime object from the email Date header."""
    return email.utils.parsedate_to_datetime(msg.get("Date"))


def decode_filename(raw_filename: str) -> str:
    """Decode a potentially encoded MIME filename."""
    part, encoding = email.header.decode_header(raw_filename)[0]
    if isinstance(part, bytes):
        return part.decode(encoding or DEFAULT_ENCODING)
    return part


def decode_subject(raw_subject: str) -> str:
    """Decode a potentially encoded email subject."""
    parts = email.header.decode_header(raw_subject)
    decoded = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(encoding or DEFAULT_ENCODING))
        else:
            decoded.append(part)
    return "".join(decoded)


def get_plain_body(msg: Message) -> str:
    """Extract plain-text body from a (possibly multipart) email."""
    if msg.is_multipart():
        for part in msg.walk():
            if (
                part.get_content_type() == "text/plain"
                and "attachment" not in str(part.get("Content-Disposition"))
            ):
                return part.get_payload(decode=True).decode(DEFAULT_ENCODING, errors="ignore")
        return ""
    return msg.get_payload(decode=True).decode(DEFAULT_ENCODING, errors="ignore")


def build_filepath(folder: Path, timestamp: str, filename: str) -> Path:
    """Build a unique file path using timestamp + original filename.
    Appends a counter suffix only if a collision occurs.
    """
    name, ext = os.path.splitext(filename)
    filepath = folder / f"{timestamp}_{name}{ext}"
    counter = 1
    while filepath.exists():
        filepath = folder / f"{timestamp}_{name}_{counter}{ext}"
        counter += 1
    return filepath

# ---------- Core logic ----------
def process_mailbox(mail: imaplib.IMAP4_SSL) -> int:
    """Search for PO-related unread emails and save attachments or body text."""
    matched_ids: set[bytes] = set()
    saved_count = 0

    for keyword in SUBJECT_KEYWORDS:
        _, messages = mail.search(None, f'(UNSEEN SUBJECT "{keyword}")')
        matched_ids.update(messages[0].split())

    print(f"  Found {len(matched_ids)} unread email(s) matching subject keywords")

    for email_id in matched_ids:
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        received_at = get_received_at(msg)
        timestamp = received_at.strftime(TIMESTAMP_FORMAT)
        sender_email = email.utils.parseaddr(msg.get("From"))[1]
        subject = decode_subject(msg.get("Subject", "no_subject"))

        # Check if email has any attachment (supported or not)
        has_attachment = any(part.get_filename() for part in msg.walk())

        # Save supported attachments
        saved_attachment = False
        for part in msg.walk():
            raw_name = part.get_filename()
            if not raw_name:
                continue
            filename = decode_filename(raw_name)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = build_filepath(SAVE_FOLDER, timestamp, filename)
            with open(filepath, "wb") as f:
                f.write(part.get_payload(decode=True))

            row_id = insert_order(
                file_path=str(filepath),
                source="email",
                sender_email=sender_email,
                subject=subject,
                received_at=received_at,
            )
            print(f"  Saved attachment: {filepath} (DB id={row_id})")
            saved_attachment = True
            saved_count += 1

        if has_attachment and not saved_attachment:
            print("  SKIPPED — attachment format not supported.")

        elif not has_attachment:
            body = get_plain_body(msg)
            if body.strip():
                subject_clean = "".join(c if c.isalnum() or c == "_" else "_" for c in subject)
                body_path = build_filepath(SAVE_FOLDER, timestamp, f"{subject_clean}.txt")
                with open(body_path, "w", encoding=DEFAULT_ENCODING) as f:
                    f.write(body)

                row_id = insert_order(
                    file_path=str(body_path),
                    source="email",
                    sender_email=sender_email,
                    subject=subject,
                    received_at=received_at,
                )
                print(f"  Saved email body: {body_path} (DB id={row_id})")
                saved_count += 1
            else:
                print("  No body text found — skipping.")

    return saved_count


# ---------- Entry point ----------
if __name__ == "__main__":
    print(f"\nConnecting to {GMAIL_EMAIL} ...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("inbox")
        total_saved = process_mailbox(mail)
        mail.logout()
        print(f"Disconnected from {GMAIL_EMAIL}")

        if total_saved > 0:
            print(f"\nDone. {total_saved} file(s) saved in: {SAVE_FOLDER}")
        else:
            print("\nNo files were saved.")

    except Exception as e:
        print(f"  ERROR: {e}")