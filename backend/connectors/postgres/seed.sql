-- ─────────────────────────────────────────────────────────────────────────────
-- Knowledge Graph Lattice — Contract Intelligence Seed Data
-- Idempotent: safe to run multiple times
-- ─────────────────────────────────────────────────────────────────────────────

-- Parties (companies / individuals involved in contracts)
CREATE TABLE IF NOT EXISTS parties (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    type             TEXT NOT NULL,  -- 'vendor', 'client', 'partner', 'employee'
    jurisdiction     TEXT,
    incorporated_in  DATE,
    contact_email    TEXT
);

-- Contracts
CREATE TABLE IF NOT EXISTS contracts (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    type            TEXT NOT NULL,   -- 'MSA', 'NDA', 'SaaS', 'Employment', 'SOW'
    status          TEXT NOT NULL,   -- 'active', 'expired', 'terminated', 'draft'
    effective_date  DATE,
    expiry_date     DATE,
    auto_renew      BOOLEAN DEFAULT FALSE,
    governing_law   TEXT,
    total_value     NUMERIC(15,2),
    currency        TEXT DEFAULT 'USD',
    signed_by_us    TEXT,
    notes           TEXT
);

-- Which parties appear on which contracts (and in what role)
CREATE TABLE IF NOT EXISTS contract_parties (
    contract_id    INT REFERENCES contracts(id),
    party_id       INT REFERENCES parties(id),
    role           TEXT NOT NULL,   -- 'counterparty', 'guarantor', 'signatory'
    signed_date    DATE,
    signatory_name TEXT,
    PRIMARY KEY (contract_id, party_id)
);

-- Individual clauses extracted from contracts
CREATE TABLE IF NOT EXISTS clauses (
    id           SERIAL PRIMARY KEY,
    contract_id  INT REFERENCES contracts(id),
    clause_type  TEXT NOT NULL,  -- 'termination','liability','IP','NDA','payment','renewal','breach'
    title        TEXT,
    content      TEXT NOT NULL,
    risk_level   TEXT            -- 'low', 'medium', 'high'
);

-- Specific obligations one party must fulfil
CREATE TABLE IF NOT EXISTS obligations (
    id               SERIAL PRIMARY KEY,
    contract_id      INT REFERENCES contracts(id),
    obligated_party  INT REFERENCES parties(id),
    description      TEXT NOT NULL,
    due_date         DATE,
    recurring        BOOLEAN DEFAULT FALSE,
    recurrence       TEXT,        -- 'monthly', 'annually', 'quarterly'
    status           TEXT DEFAULT 'pending'  -- 'pending', 'fulfilled', 'breached'
);

-- Regulatory references embedded in contracts
CREATE TABLE IF NOT EXISTS regulations (
    id           SERIAL PRIMARY KEY,
    contract_id  INT REFERENCES contracts(id),
    regulation   TEXT NOT NULL,  -- 'GDPR', 'CCPA', 'HIPAA', 'SOX', 'SOC2'
    requirement  TEXT
);

-- ─── SEED (skip if already populated) ────────────────────────────────────────

DO $$ BEGIN
  IF (SELECT COUNT(*) FROM parties) > 0 THEN
    RAISE NOTICE 'Data already seeded — skipping.';
    RETURN;
  END IF;

  -- Parties
  INSERT INTO parties (name, type, jurisdiction, contact_email) VALUES
    ('Acme Corp',           'vendor',   'Delaware, USA',     'legal@acme.com'),
    ('Stripe Inc',          'vendor',   'Delaware, USA',     'contracts@stripe.com'),
    ('IBM Corporation',     'vendor',   'New York, USA',     'legal@ibm.com'),
    ('DataSafe GmbH',       'vendor',   'Berlin, Germany',   'legal@datasafe.de'),
    ('LexTech Solutions',   'partner',  'California, USA',   'legal@lextech.com'),
    ('Our Company Inc',     'client',   'California, USA',   'legal@ourcompany.com'),
    ('Sarah Mitchell',      'employee', 'California, USA',   's.mitchell@ourcompany.com'),
    ('James Okafor',        'employee', 'New York, USA',     'j.okafor@ourcompany.com');

  -- Contracts
  INSERT INTO contracts (title, type, status, effective_date, expiry_date, auto_renew, governing_law, total_value, signed_by_us, notes) VALUES
    ('Master Services Agreement — Acme Corp',      'MSA',        'active',  '2022-03-01', '2025-03-01', TRUE,  'California, USA',   120000.00, 'CEO', 'Covers all SOWs with Acme'),
    ('NDA — Stripe Inc',                           'NDA',        'active',  '2023-01-15', '2026-01-15', FALSE, 'Delaware, USA',          NULL, 'CLO', '2-year mutual NDA'),
    ('SaaS Subscription — IBM Watson',             'SaaS',       'active',  '2023-06-01', '2024-06-01', TRUE,  'New York, USA',      84000.00, 'CTO', 'Auto-renews unless 60-day notice'),
    ('Data Processing Agreement — DataSafe GmbH',  'MSA',        'active',  '2023-09-01', '2025-09-01', FALSE, 'German Law / GDPR',  36000.00, 'CLO', 'GDPR-compliant DPA'),
    ('Partnership Agreement — LexTech Solutions',  'MSA',        'active',  '2024-01-01', '2027-01-01', TRUE,  'California, USA',   200000.00, 'CEO', 'Revenue share arrangement'),
    ('Employment Contract — Sarah Mitchell',        'Employment', 'active',  '2021-07-01', NULL,         FALSE, 'California, USA',        NULL, 'HR',  'VP Engineering, includes IP assignment'),
    ('Employment Contract — James Okafor',          'Employment', 'active',  '2022-11-01', NULL,         FALSE, 'New York, USA',          NULL, 'HR',  'Senior Counsel, non-compete clause'),
    ('Statement of Work #3 — Acme Corp',           'SOW',        'expired', '2023-01-01', '2023-12-31', FALSE, 'California, USA',    45000.00, 'CTO', 'Phase 3 integration work');

  -- Contract ↔ Party relationships
  INSERT INTO contract_parties (contract_id, party_id, role, signed_date, signatory_name) VALUES
    (1, 1, 'counterparty', '2022-03-01', 'David Acme'),
    (1, 6, 'counterparty', '2022-03-01', 'Jane CEO'),
    (2, 2, 'counterparty', '2023-01-15', 'Stripe Legal'),
    (2, 6, 'counterparty', '2023-01-15', 'Jane CEO'),
    (3, 3, 'counterparty', '2023-06-01', 'IBM Sales'),
    (3, 6, 'counterparty', '2023-06-01', 'Bob CTO'),
    (4, 4, 'counterparty', '2023-09-01', 'Klaus Müller'),
    (4, 6, 'counterparty', '2023-09-01', 'Jane CEO'),
    (5, 5, 'counterparty', '2024-01-01', 'LexTech CEO'),
    (5, 6, 'counterparty', '2024-01-01', 'Jane CEO'),
    (6, 7, 'signatory',    '2021-07-01', 'Sarah Mitchell'),
    (7, 8, 'signatory',    '2022-11-01', 'James Okafor'),
    (8, 1, 'counterparty', '2023-01-01', 'David Acme'),
    (8, 6, 'counterparty', '2023-01-01', 'Bob CTO');

  -- Clauses
  INSERT INTO clauses (contract_id, clause_type, title, content, risk_level) VALUES
    (1, 'termination', 'Termination for Convenience',   'Either party may terminate this Agreement upon 30 days written notice.', 'low'),
    (1, 'liability',   'Limitation of Liability',        'In no event shall either party be liable for indirect or consequential damages. Total liability capped at fees paid in the prior 12 months.', 'medium'),
    (1, 'payment',     'Payment Terms',                  'Invoices due within 30 days of receipt. Late payments accrue interest at 1.5% per month.', 'low'),
    (2, 'NDA',         'Confidentiality Obligations',    'Each party agrees to keep confidential all non-public information disclosed. Obligations survive termination for 3 years.', 'medium'),
    (3, 'renewal',     'Auto-Renewal',                   'This agreement auto-renews annually unless either party provides 60 days written notice of non-renewal prior to expiry.', 'high'),
    (3, 'termination', 'Termination for Breach',         'Either party may terminate immediately upon material breach if breach is not cured within 15 days of written notice.', 'medium'),
    (4, 'IP',          'Data Ownership',                 'All personal data processed under this agreement remains the exclusive property of the Controller. Processor acquires no rights to the data.', 'high'),
    (5, 'liability',   'Unlimited Liability — Indemnity','Each party shall indemnify the other against all claims arising from gross negligence or willful misconduct. Indemnity obligations are unlimited.', 'high'),
    (6, 'IP',          'IP Assignment',                  'Employee hereby assigns to the Company all inventions, works, and developments created during employment or using Company resources.', 'medium'),
    (7, 'NDA',         'Non-Compete',                    'Employee agrees not to engage with any competing firm within the legal sector for 12 months following termination of employment.', 'high'),
    (8, 'payment',     'Milestone Payments',             'Payment of $15,000 due upon completion of each of three milestones as defined in Schedule A.', 'low');

  -- Obligations
  INSERT INTO obligations (contract_id, obligated_party, description, due_date, recurring, recurrence, status) VALUES
    (1, 1, 'Deliver monthly status reports on all active SOWs',                  NULL,         TRUE,  'monthly',   'pending'),
    (1, 6, 'Pay monthly retainer of $10,000 by the 1st of each month',          NULL,         TRUE,  'monthly',   'pending'),
    (3, 6, 'Provide 60 days written notice before expiry to prevent auto-renewal','2024-04-01', FALSE, NULL,        'pending'),
    (4, 4, 'Submit annual GDPR compliance audit report',                         '2024-09-01', TRUE,  'annually',  'pending'),
    (4, 6, 'Notify DataSafe within 72 hours of any personal data breach',        NULL,         FALSE, NULL,        'pending'),
    (5, 5, 'Refer minimum 3 qualified leads per quarter',                        NULL,         TRUE,  'quarterly', 'pending'),
    (5, 6, 'Pay 15% revenue share on all referred deals within 30 days',         NULL,         TRUE,  'monthly',   'pending');

  -- Regulations
  INSERT INTO regulations (contract_id, regulation, requirement) VALUES
    (4, 'GDPR',  'Data processing must comply with GDPR Art. 28. DPA required. 72-hour breach notification.'),
    (4, 'GDPR',  'Data subject access requests must be fulfilled within 30 days.'),
    (3, 'SOC2',  'Vendor must maintain SOC2 Type II certification throughout the term.'),
    (5, 'CCPA',  'Both parties must comply with CCPA consumer data rights obligations.');

END $$;
