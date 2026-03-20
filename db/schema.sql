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
                    CHECK (status IN ('pending', 'valid', 'invalid', 'pushed', 'push_failed')),
    doc_type        CHARACTER VARYING,                  -- 'purchase_order' | 'informal_order'
    extracted_json  JSONB,
    confidence_score NUMERIC(3,2)                       -- Gemini extraction confidence (between 0 and 1)

);

CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_source      ON orders (source);
CREATE INDEX IF NOT EXISTS idx_orders_received_at ON orders (received_at DESC);
