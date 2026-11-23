CREATE TABLE IF NOT EXISTS clue_reviews (
    clue_id INTEGER PRIMARY KEY REFERENCES risk_clues(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'returned', 'resolved')),
    evidence_source TEXT NOT NULL CHECK (evidence_source IN ('official_record', 'original_media', 'issuer_confirmation')),
    evidence_reference TEXT NOT NULL CHECK (char_length(btrim(evidence_reference)) BETWEEN 3 AND 120),
    finding TEXT NOT NULL CHECK (char_length(btrim(finding)) BETWEEN 10 AND 1000),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('confirmed', 'dismissed')),
    submitted_by INTEGER NOT NULL REFERENCES users(id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    review_note TEXT CHECK (char_length(btrim(review_note)) BETWEEN 6 AND 500),
    CHECK (
        (status = 'pending' AND reviewed_by IS NULL AND reviewed_at IS NULL AND review_note IS NULL)
        OR
        (status IN ('returned', 'resolved') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND review_note IS NOT NULL)
    ),
    CHECK (submitted_by <> reviewed_by)
);

CREATE INDEX IF NOT EXISTS risk_clues_claim_idx ON risk_clues(claim_id);
