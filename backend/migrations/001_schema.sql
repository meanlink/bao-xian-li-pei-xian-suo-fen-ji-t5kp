CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('intake_agent','investigator','risk_manager')),
  display_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS claims (
  id SERIAL PRIMARY KEY,
  claim_no TEXT UNIQUE NOT NULL,
  policy_no TEXT NOT NULL,
  customer_name TEXT NOT NULL,
  incident_type TEXT NOT NULL,
  incident_date DATE NOT NULL,
  loss_amount NUMERIC(12,2) NOT NULL CHECK (loss_amount >= 0),
  region TEXT NOT NULL,
  claimant_phone TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'intake',
  documents_status TEXT NOT NULL DEFAULT 'pending',
  required_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
  received_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
  missing_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_score NUMERIC(8,5),
  model_threshold NUMERIC(8,5),
  risk_level TEXT,
  verified_fraud BOOLEAN,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_clues (
  id SERIAL PRIMARY KEY,
  claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  clue_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
  description TEXT NOT NULL,
  evidence TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','confirmed','dismissed')),
  created_by INTEGER REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investigation_tasks (
  id SERIAL PRIMARY KEY,
  claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  assignee TEXT NOT NULL,
  priority TEXT NOT NULL CHECK (priority IN ('normal','high','urgent')),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','assigned','in_progress','completed','cancelled')),
  due_date DATE NOT NULL,
  scope TEXT NOT NULL,
  findings TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  claim_id INTEGER REFERENCES claims(id) ON DELETE SET NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
