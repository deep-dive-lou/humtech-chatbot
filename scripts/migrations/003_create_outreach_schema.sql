-- 003_create_outreach_schema.sql
-- Cold outreach pipeline tables
-- Independent schema — no FK references to engine or bot schemas.

CREATE SCHEMA IF NOT EXISTS outreach;

-- ============================================================
-- outreach.leads
-- One row per prospect. Deduped by email.
-- ============================================================
CREATE TABLE outreach.leads (
    lead_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    first_name      TEXT NOT NULL,
    last_name       TEXT,
    title           TEXT,
    company         TEXT,
    company_domain  TEXT,
    linkedin_url    TEXT,
    industry        TEXT,
    employee_count  INT,
    city            TEXT,
    apollo_id       TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
    -- new | enriched | personalised | queued | sent | failed | suppressed | blocked
    batch_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_outreach_leads_email UNIQUE (email)
);

CREATE INDEX idx_outreach_leads_status     ON outreach.leads (status);
CREATE INDEX idx_outreach_leads_batch_date ON outreach.leads (batch_date);

-- ============================================================
-- outreach.enrichment
-- Signal JSON from Proxycurl, Meta Ad Library, website analysis.
-- ============================================================
CREATE TABLE outreach.enrichment (
    enrichment_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID NOT NULL REFERENCES outreach.leads(lead_id),
    signals         JSONB NOT NULL DEFAULT '{}',
    enriched_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outreach_enrichment_lead ON outreach.enrichment (lead_id);

-- ============================================================
-- outreach.personalisation
-- Claude output per lead. edited_opener is Chris's override (null = use opener_first_line).
-- ============================================================
CREATE TABLE outreach.personalisation (
    personalisation_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID NOT NULL REFERENCES outreach.leads(lead_id),
    opener_first_line   TEXT NOT NULL,
    micro_insight       TEXT,
    angle_tag           TEXT,
    confidence_score    NUMERIC(3,2),
    evidence_used       JSONB NOT NULL DEFAULT '[]',
    risk_flags          JSONB NOT NULL DEFAULT '[]',
    rung                INT,
    review_status       TEXT NOT NULL DEFAULT 'auto_send',
    -- auto_send | needs_review | blocked
    prompt_version      TEXT NOT NULL DEFAULT 'v1.0',
    model               TEXT,
    edited_opener       TEXT,
    removed             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outreach_pers_lead   ON outreach.personalisation (lead_id);
CREATE INDEX idx_outreach_pers_review ON outreach.personalisation (review_status, removed)
    WHERE removed = FALSE;
CREATE INDEX idx_outreach_pers_date   ON outreach.personalisation (created_at);

-- ============================================================
-- outreach.events
-- Append-only event log for Metabase reporting.
-- ============================================================
CREATE TABLE outreach.events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID NOT NULL REFERENCES outreach.leads(lead_id),
    event_type      TEXT NOT NULL,
    -- imported | enriched | personalised | queued | sent | failed
    -- replied | classified | suppressed | ghl_created
    meta            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outreach_events_lead ON outreach.events (lead_id);
CREATE INDEX idx_outreach_events_type ON outreach.events (event_type, created_at);

-- ============================================================
-- outreach.suppressions
-- Permanent block list. Checked before enrichment.
-- ============================================================
CREATE TABLE outreach.suppressions (
    suppression_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT,
    domain          TEXT,
    reason          TEXT NOT NULL,
    -- unsubscribe | bounce | client | competitor | negative_reply
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_outreach_suppressions_email UNIQUE (email)
);

CREATE INDEX idx_outreach_suppressions_domain ON outreach.suppressions (domain)
    WHERE domain IS NOT NULL;
