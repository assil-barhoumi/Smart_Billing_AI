-- AutomatingSales Pipeline Database Schema

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL                      PRIMARY KEY,
    file_path       TEXT                        NOT NULL,
    source          CHARACTER VARYING           NOT NULL,   -- 'email' | 'whatsapp' | 'manual'
    sender          CHARACTER VARYING,
    subject         TEXT,
    received_at     TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    file_hash       TEXT                        UNIQUE,     -- SHA-256
    status          CHARACTER VARYING           NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'valid', 'invalid', 'pushed', 'push_failed', 'needs_review')),
    doc_type        CHARACTER VARYING,                  -- 'purchase_order' | 'informal_order'
    extracted_json  JSONB,
    confidence_score NUMERIC(3,2),                      -- Gemini extraction confidence (between 0 and 1)
    needs_review    BOOLEAN                 NOT NULL DEFAULT FALSE,
    odoo_order_id   INTEGER,                            -- sale.order ID in Odoo
    error_message   TEXT                                -- push error or review reason
);

CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_source      ON orders (source);
CREATE INDEX IF NOT EXISTS idx_orders_received_at ON orders (received_at DESC);

-- Supplier invoices table
CREATE TABLE IF NOT EXISTS invoices (
    id               SERIAL PRIMARY KEY,
    file_path        TEXT NOT NULL,
    source           VARCHAR NOT NULL DEFAULT 'email',
    sender           VARCHAR,
    subject          TEXT,
    received_at      TIMESTAMP NOT NULL,
    file_hash        TEXT UNIQUE,
    status           VARCHAR NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'validated', 'rejected', 'paid')),
    extracted_json   JSONB,
    confidence_score NUMERIC(3,2),
    supplier_name    VARCHAR,
    invoice_number   VARCHAR,
    invoice_date     DATE,
    due_date         DATE,
    total_ht         NUMERIC(12,2),
    vat_amount       NUMERIC(12,2),
    total_ttc        NUMERIC(12,2),
    currency         VARCHAR(3),
    payment_status   VARCHAR NOT NULL DEFAULT 'unpaid'
                     CHECK (payment_status IN ('unpaid', 'paid', 'partial')),
    validated_at     TIMESTAMP,
    odoo_invoice_id  INTEGER,
    error_message    TEXT
);

CREATE INDEX IF NOT EXISTS idx_invoices_status         ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices (payment_status);
CREATE INDEX IF NOT EXISTS idx_invoices_received_at    ON invoices (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date       ON invoices (due_date);
