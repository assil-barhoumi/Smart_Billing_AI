# AutomatingSales — Order Extraction Pipeline

Automated pipeline for acquiring, extracting, and pushing customer orders to Odoo.

---

## Overview

The system collects order documents from Gmail, extracts structured data using an LLM (Gemini), validates the result, and creates draft quotations in Odoo.

type of orders :
- **Informal Orders** — emails, spreadsheets, text files, images

---

## Pipeline

```
Gmail Inbox
    │
    ▼
EmailCollector (acquisition/email_collector.py)
    │  Reads unread emails matching subject keywords
    │  Saves attachments to orders/purchase_orders/ or orders/informal_orders/
    │  Inserts row in DB (status = pending)
    │
    ▼
LLM Extraction (extraction/main.py)
    │  Sends document to Gemini Vision API
    │  Extracts: client, date, order number, line items, totals, currency
    │  Validates extracted data (checker.py)
    │  Updates DB (status = valid / invalid)
    │  Saves result JSON to results/
    │
    ▼
Odoo Push (odoo/push_to_odoo.py)
    │  Finds or creates client partner in Odoo
    │  Matches products by name
    │  Creates draft quotation (sale.order)
    │  Updates DB (status = pushed / needs_review / push_failed)
    │
    ▼
Odoo Draft Quotation
```

---

## Supported File Formats

Supported formats for informal orders : `.pdf`, `.jpg`, `.jpeg`, `.png`, `.txt`, `.csv`, `.xlsx`, `.xls`

---

## Email Keywords

Emails are routed by subject keywords:

| Keywords |
|---|
| `Order`, `commande`, `Request`, `Demande` |

---

## Setup

### 1. Environment variables

Create a `.env` file at the project root:

```env
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_db_name
DB_USER=your_username
DB_PASSWORD=your_password

# Gmail
GMAIL_EMAIL=your@gmail.com
GMAIL_PASSWORD=your_app_password

# Gemini API
GEMINI_API_KEY=your_gemini_key

# Odoo
ODOO_URL=your_odoo_url
ODOO_DB=your_odoo_db
ODOO_USER=your_odoo_user
ODOO_PASSWORD=your_odoo_password
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create database tables

Run `db/schema.sql` in pgAdmin or psql.

---

## Usage

### Run full pipeline (recommended)

Runs all steps automatically: collect emails → extract → push to Odoo.

```bash
python run_pipeline.py
```

### Run steps individually

```bash
# 1. Collect emails
python acquisition/email_collector.py

# 2. Extract orders (batch)
python extraction/main.py informal

# 2. Extract single file
python extraction/main.py informal path/to/file.txt

# 3. Push to Odoo
python odoo/push_to_odoo.py results/informal_order/filename.json
```

---

## Order Statuses

| Status | Meaning |
|---|---|
| `pending` | Acquired, not yet extracted |
| `valid` | Extracted and passed validation |
| `invalid` | Extracted but failed validation |
| `pushed` | Successfully pushed to Odoo |
| `needs_review` | Pushed but flagged (new client or unmatched products) |
| `push_failed` | Odoo push failed |

---

## LLM — Gemini

- Model: `gemini-2.0-flash` (Vision)
- Handles French, Arabic, English documents
- Returns structured JSON with confidence score

