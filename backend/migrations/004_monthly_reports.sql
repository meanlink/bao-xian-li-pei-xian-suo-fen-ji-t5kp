CREATE TABLE IF NOT EXISTS settlement_records (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
    settled_on DATE NOT NULL,
    loss_amount NUMERIC(12,2) NOT NULL CHECK (loss_amount >= 0),
    recorded_by INTEGER REFERENCES users(id),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS settlement_records_month_idx ON settlement_records (settled_on);

CREATE TABLE IF NOT EXISTS monthly_reports (
    id SERIAL PRIMARY KEY,
    report_month DATE NOT NULL UNIQUE CHECK (date_trunc('month', report_month)::date = report_month),
    closed_count INTEGER NOT NULL CHECK (closed_count >= 0),
    loss_total NUMERIC(14,2) NOT NULL CHECK (loss_total >= 0),
    carry_count INTEGER NOT NULL DEFAULT 0 CHECK (carry_count >= 0),
    carry_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (carry_total >= 0),
    frozen_by INTEGER REFERENCES users(id),
    frozen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each settlement record is accounted at most once across all frozen reports:
-- the UNIQUE constraint on settlement_record_id is the idempotency guarantee
-- that freeze retries can neither double-count nor silently drop an entry.
CREATE TABLE IF NOT EXISTS monthly_report_entries (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES monthly_reports(id) ON DELETE CASCADE,
    settlement_record_id INTEGER NOT NULL UNIQUE REFERENCES settlement_records(id) ON DELETE CASCADE,
    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    entry_kind TEXT NOT NULL CHECK (entry_kind IN ('current', 'carry')),
    attribution_month DATE NOT NULL CHECK (date_trunc('month', attribution_month)::date = attribution_month),
    loss_amount NUMERIC(12,2) NOT NULL CHECK (loss_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS monthly_report_entries_report_idx ON monthly_report_entries (report_id, id);
