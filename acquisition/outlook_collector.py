import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from acquisition.common import (
    SUPPORTED_EXTENSIONS, INVOICE_EXTENSIONS, TIMESTAMP_FORMAT,
    classify_subject, build_filepath, save_attachment, save_body,
)

try:
    import win32com.client
except ImportError:
    print("ERROR: pywin32 is not installed. Run: pip install pywin32")
    sys.exit(1)


def process_outlook_inbox() -> int:
    outlook = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook.GetNamespace("MAPI")
    inbox = namespace.GetDefaultFolder(6)

    namespace.SendAndReceive(False)
    time.sleep(5)
    unread_items = inbox.Items.Restrict("[UnRead] = True")
    items_list = list(unread_items)
    print(f"  Found {len(items_list)} unread Outlook message(s)")

    saved_count = 0

    for item in items_list:
        subject = item.Subject or "no_subject"
        route = classify_subject(subject)
        if route is None:
            continue

        save_folder, doc_type = route

        received_at = item.ReceivedTime
        received_at = datetime(
            received_at.year, received_at.month, received_at.day,
            received_at.hour, received_at.minute, received_at.second,
        )
        timestamp = received_at.strftime(TIMESTAMP_FORMAT)
        sender = item.SenderEmailAddress or "unknown"

        attachments = item.Attachments
        has_attachment = attachments.Count > 0
        processed_attachment = False

        for i in range(1, attachments.Count + 1):
            att = attachments.Item(i)
            filename = att.FileName
            ext = os.path.splitext(filename)[1].lower()

            allowed = INVOICE_EXTENSIONS if doc_type == "invoice" else SUPPORTED_EXTENSIONS
            if ext not in allowed:
                continue

            processed_attachment = True
            filepath = build_filepath(save_folder, timestamp, filename)
            att.SaveAsFile(str(filepath))

            row_id = save_attachment(
                filepath, "outlook", sender, subject, received_at, doc_type,
            )
            if row_id is not None:
                saved_count += 1

        if has_attachment and not processed_attachment:
            print("  SKIPPED — attachment format not supported.")
        elif not has_attachment:
            if doc_type == "invoice":
                print("  SKIPPED — invoice email has no attachment, ignored.")
            else:
                body = item.Body or ""
                row_id = save_body(
                    body, save_folder, timestamp, subject,
                    "outlook", sender, received_at, doc_type,
                )
                if row_id is not None:
                    saved_count += 1

        item.UnRead = False
        item.Save()

    return saved_count


if __name__ == "__main__":
    print("\nConnecting to Outlook...")
    total_saved = process_outlook_inbox()
    if total_saved > 0:
        print(f"\nDone. {total_saved} file(s) saved from Outlook.")
    else:
        print("\nNo files were saved from Outlook.")
