import imaplib
import email
import email.header
import email.utils
from email.message import Message
from datetime import datetime
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from acquisition.common import (
    SAVE_PO, SAVE_INFORMAL, SAVE_INVOICES,
    PO_KEYWORDS, INFORMAL_KEYWORDS, INVOICE_KEYWORDS,
    SUPPORTED_EXTENSIONS, INVOICE_EXTENSIONS, TIMESTAMP_FORMAT,
    build_filepath, save_attachment, save_body,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GMAIL_EMAIL    = os.getenv("GMAIL_EMAIL")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
IMAP_SERVER    = "imap.gmail.com"
IMAP_PORT      = 993
DEFAULT_ENCODING = "utf-8"


def get_received_at(msg: Message) -> datetime:
    return email.utils.parsedate_to_datetime(msg.get("Date"))


def decode_filename(raw_filename: str) -> str:
    part, encoding = email.header.decode_header(raw_filename)[0]
    if isinstance(part, bytes):
        return part.decode(encoding or DEFAULT_ENCODING)
    return part


def decode_subject(raw_subject: str) -> str:
    parts = email.header.decode_header(raw_subject)
    decoded = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(encoding or DEFAULT_ENCODING))
        else:
            decoded.append(part)
    return "".join(decoded)


def get_plain_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if (
                part.get_content_type() == "text/plain"
                and "attachment" not in str(part.get("Content-Disposition"))
            ):
                return part.get_payload(decode=True).decode(DEFAULT_ENCODING, errors="ignore")
        return ""
    return msg.get_payload(decode=True).decode(DEFAULT_ENCODING, errors="ignore")


def process_mailbox(mail: imaplib.IMAP4_SSL) -> int:
    routing: dict[bytes, tuple[Path, str]] = {}

    for keyword in INFORMAL_KEYWORDS:
        _, messages = mail.search(None, f'(UNSEEN SUBJECT "{keyword}")')
        for eid in messages[0].split():
            routing[eid] = (SAVE_INFORMAL, "informal_order")

    for keyword in INVOICE_KEYWORDS:
        _, messages = mail.search(None, f'(UNSEEN SUBJECT "{keyword}")')
        for eid in messages[0].split():
            routing[eid] = (SAVE_INVOICES, "invoice")

    for keyword in PO_KEYWORDS:
        _, messages = mail.search(None, f'(UNSEEN SUBJECT "{keyword}")')
        for eid in messages[0].split():
            routing[eid] = (SAVE_PO, "purchase_order")

    print(f"  Found {len(routing)} unread email(s) matching subject keywords")
    saved_count = 0

    for email_id, (save_folder, doc_type) in routing.items():
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        received_at = get_received_at(msg)
        timestamp = received_at.strftime(TIMESTAMP_FORMAT)
        sender_email = email.utils.parseaddr(msg.get("From"))[1]
        subject = decode_subject(msg.get("Subject", "no_subject"))

        has_attachment = any(part.get_filename() for part in msg.walk())
        saved_attachment = False

        for part in msg.walk():
            raw_name = part.get_filename()
            if not raw_name:
                continue
            filename = decode_filename(raw_name)
            ext = os.path.splitext(filename)[1].lower()

            allowed = INVOICE_EXTENSIONS if doc_type == "invoice" else SUPPORTED_EXTENSIONS
            if ext not in allowed:
                continue

            filepath = build_filepath(save_folder, timestamp, filename)
            row_id = save_attachment(
                filepath, "email", sender_email, subject, received_at, doc_type,
                data=part.get_payload(decode=True),
            )
            if row_id is not None:
                saved_attachment = True
                saved_count += 1

        if has_attachment and not saved_attachment:
            print("  SKIPPED — attachment format not supported.")
        elif not has_attachment:
            if doc_type == "invoice":
                print("  SKIPPED — invoice email has no attachment, ignored.")
            else:
                body = get_plain_body(msg)
                if body.strip():
                    row_id = save_body(
                        body, save_folder, timestamp, subject,
                        "email", sender_email, received_at, doc_type,
                    )
                    if row_id is not None:
                        saved_count += 1
                else:
                    print("  No body text found — skipping.")

    return saved_count


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
            print(f"\nDone. {total_saved} file(s) saved.")
        else:
            print("\nNo files were saved.")
    except Exception as e:
        print(f"  ERROR: {e}")
