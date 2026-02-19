# Revenue Event Engine — Schema Design

## Purpose

This is the data layer for the Revenue Growth Engine. It stores the canonical lifecycle of every lead across every tenant, tracks every meaningful event (stage changes, bookings, wins, payments), and provides the data Metabase needs to show pipeline performance and prove uplift.

The engine schema has **zero dependencies on the bot schema**. It references external systems through `(tenant_id, provider, external_id)` tuples. Events from the bot and events from CRM webhooks land in the same tables in the same format.

---

## Schema: `engine`

Lives in the same DigitalOcean managed Postgres database as `core` and `bot`.

```
core   — tenant config, credentials (exists)
bot    — conversations, messages, contacts (exists)
engine — leads, lead events, stage mappings, baselines (this doc)
```

---

## Tables

### engine.leads

The lead is the central entity. It represents one revenue opportunity moving through the pipeline. One contact can have multiple leads (e.g. repeat customer, separate jobs).

```sql
CREATE SCHEMA IF NOT EXISTS engine;

CREATE TABLE engine.leads (
    lead_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES core.tenants(tenant_id),

    -- External identity (provider-agnostic)
    provider            TEXT NOT NULL,           -- 'ghl', 'hubspot', 'bot', 'manual'
    external_id         TEXT NOT NULL,           -- lead/opportunity ID in the source system

    -- Contact reference (NOT a FK to bot.contacts)
    contact_provider    TEXT,                    -- 'ghl', 'hubspot', etc.
    contact_external_id TEXT,                    -- contact ID in the source system

    -- Lead data
    name                TEXT,
    pipeline_name       TEXT,                    -- raw pipeline name from CRM
    current_stage       TEXT NOT NULL DEFAULT 'lead_created',   -- canonical stage
    raw_stage           TEXT,                    -- raw stage name from CRM before mapping
    source              TEXT,                    -- 'inbound_sms', 'web_form', 'referral', 'manual'
    lead_value          NUMERIC(12,2),           -- monetary value if known
    currency            TEXT DEFAULT 'GBP',

    -- Lifecycle
    is_open             BOOLEAN NOT NULL DEFAULT TRUE,
    won_at              TIMESTAMPTZ,
    lost_at             TIMESTAMPTZ,
    closed_reason       TEXT,                    -- 'won', 'lost', 'abandoned'

    -- Metadata
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_leads_tenant_provider_ext UNIQUE (tenant_id, provider, external_id)
);

CREATE INDEX idx_leads_tenant           ON engine.leads (tenant_id);
CREATE INDEX idx_leads_tenant_contact   ON engine.leads (tenant_id, contact_provider, contact_external_id);
CREATE INDEX idx_leads_tenant_stage     ON engine.leads (tenant_id, current_stage);
CREATE INDEX idx_leads_tenant_open      ON engine.leads (tenant_id, is_open) WHERE is_open = TRUE;
CREATE INDEX idx_leads_created_at       ON engine.leads (tenant_id, created_at);
```

**Design notes:**

- `UNIQUE (tenant_id, provider, external_id)` — the upsert key. `INSERT ... ON CONFLICT DO UPDATE` makes lead creation idempotent.
- `current_stage` always holds the **canonical** stage name. `raw_stage` preserves the CRM's original name for audit.
- `contact_provider` + `contact_external_id` are soft references, not foreign keys. The bridge to `bot.contacts` happens at query time if needed, by matching the CRM contact ID.
- No unique constraint on contact fields — supports multiple leads per contact.
- `metadata` JSONB holds provider-specific data (GHL pipeline ID, custom fields, tags).

---

### engine.lead_events

Append-only event log. Every meaningful thing that happens to a lead is a row. This is the core data source for all metrics. Never updated, never deleted.

```sql
CREATE TABLE engine.lead_events (
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES core.tenants(tenant_id),
    lead_id             UUID NOT NULL REFERENCES engine.leads(lead_id),

    -- Event classification
    event_type          TEXT NOT NULL,           -- see event types below
    canonical_stage     TEXT,                    -- canonical stage this event moves the lead to (NULL for non-stage events)

    -- Stage transition (populated for stage_changed events only)
    from_stage          TEXT,                    -- canonical stage before
    to_stage            TEXT,                    -- canonical stage after

    -- Event source
    source              TEXT NOT NULL,           -- 'bot', 'crm_webhook', 'manual'
    source_event_id     TEXT,                    -- idempotency key from the source system
    actor               TEXT,                    -- who/what caused this: 'bot', 'webhook:ghl', 'user:jane'

    -- Financial data (populated for cash_collected, lead_won, value_changed)
    amount              NUMERIC(12,2),
    currency            TEXT,

    -- Event payload
    payload             JSONB NOT NULL DEFAULT '{}',

    -- Timestamps
    occurred_at         TIMESTAMPTZ NOT NULL,    -- when this actually happened
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when we recorded it

    -- Idempotency
    CONSTRAINT uq_lead_events_idempotent UNIQUE (tenant_id, lead_id, source, source_event_id)
);

CREATE INDEX idx_lead_events_lead       ON engine.lead_events (lead_id, occurred_at);
CREATE INDEX idx_lead_events_tenant     ON engine.lead_events (tenant_id);
CREATE INDEX idx_lead_events_type       ON engine.lead_events (tenant_id, event_type);
CREATE INDEX idx_lead_events_occurred   ON engine.lead_events (tenant_id, occurred_at);
CREATE INDEX idx_lead_events_source     ON engine.lead_events (tenant_id, source);
```

**Event types:**

| event_type | When it fires | Key payload fields |
|------------|---------------|-------------------|
| lead_created | New lead enters the system | source, initial stage |
| stage_changed | Lead moves pipeline stages | from_stage, to_stage |
| appointment_booked | Appointment scheduled | slot_start, slot_end, calendar_id |
| appointment_completed | Appointment happened | — |
| appointment_no_show | Lead didn't show up | — |
| proposal_sent | Quote/proposal sent | proposal_value |
| lead_won | Lead converted to customer | final_value |
| lead_lost | Lead dropped out | lost_reason |
| cash_collected | Payment received | amount, invoice_id |
| value_changed | Lead value updated | old_value, new_value |
| first_contact | First outbound message sent | response_time_seconds |

**Design notes:**

- `occurred_at` vs `recorded_at`: Two timestamps. `occurred_at` = when the event happened in reality. `recorded_at` = when our system wrote it. Critical for backfills, late webhooks, and accurate time-in-stage calculations.
- `source_event_id`: Idempotency key from the source. For a GHL webhook = delivery ID. For the bot = message_id or generated UUID. The UNIQUE constraint prevents duplicate events.
- `payload` JSONB holds event-specific data. Keeps the table schema stable while supporting different event shapes.
- Corrections are new events, not updates to existing rows.

---

### engine.stage_mappings

Per-tenant mapping from raw CRM stage names to canonical stages. This is what makes the system provider-agnostic.

```sql
CREATE TABLE engine.stage_mappings (
    mapping_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES core.tenants(tenant_id),

    -- Source identification
    provider            TEXT NOT NULL,           -- 'ghl', 'hubspot', etc.
    pipeline_id         TEXT,                    -- optional: specific pipeline in the CRM
    pipeline_name       TEXT,                    -- human-readable

    -- Mapping
    raw_stage           TEXT NOT NULL,           -- stage name as it appears in the CRM
    canonical_stage     TEXT NOT NULL,           -- our canonical stage name
    stage_order         INT NOT NULL,            -- position in pipeline (1, 2, 3...)

    -- Control
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_stage_mapping UNIQUE (tenant_id, provider, pipeline_id, raw_stage)
);

CREATE INDEX idx_stage_mappings_lookup ON engine.stage_mappings (tenant_id, provider, raw_stage) WHERE is_active = TRUE;
```

**Canonical stages (V1):**

| Order | Canonical Stage | Meaning |
|-------|----------------|---------|
| 1 | lead_created | New lead entered the system |
| 2 | lead_qualified | Lead meets basic criteria |
| 3 | appointment_booked | Appointment scheduled |
| 4 | appointment_completed | Appointment happened |
| 5 | proposal_sent | Quote/proposal delivered |
| 6 | lead_won | Lead converted, job secured |
| 7 | revenue_collected | Payment received |
| — | lead_lost | Terminal state (from any stage) |

**Design notes:**

- Canonical stages are string constants in application code, NOT a Postgres ENUM. Adding a new stage doesn't require a migration.
- `pipeline_id` is nullable. Some CRMs have one pipeline, others have many. When populated, the UNIQUE constraint ensures one mapping per raw stage per pipeline.
- `is_active` allows soft-disabling a mapping without deleting it.
- `stage_order` enables forward/backward movement detection and ordering in Metabase charts.

**Example mapping for a GHL client:**

| raw_stage | canonical_stage | stage_order |
|-----------|----------------|-------------|
| New Lead | lead_created | 1 |
| Contacted | lead_qualified | 2 |
| Appointment Set | appointment_booked | 3 |
| Appointment Complete | appointment_completed | 4 |
| Proposal Sent | proposal_sent | 5 |
| Closed Won | lead_won | 6 |
| Payment Received | revenue_collected | 7 |
| Closed Lost | lead_lost | 99 |

---

### engine.baselines

Frozen metric snapshots for before/after comparison. A baseline is a point-in-time measurement, not a live query.

```sql
CREATE TABLE engine.baselines (
    baseline_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES core.tenants(tenant_id),

    -- Baseline definition
    label               TEXT NOT NULL,           -- 'pre_deployment', 'q1_2026', etc.
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,

    -- Metrics snapshot
    metrics             JSONB NOT NULL,

    -- Control
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_baseline_label UNIQUE (tenant_id, label)
);

CREATE INDEX idx_baselines_tenant ON engine.baselines (tenant_id) WHERE is_active = TRUE;
```

**Example metrics JSONB:**

```json
{
    "lead_to_qualified_rate": 0.45,
    "qualified_to_booked_rate": 0.30,
    "booked_to_completed_rate": 0.80,
    "completed_to_won_rate": 0.25,
    "avg_sales_cycle_days": 14.2,
    "revenue_per_lead": 320.00,
    "total_leads": 120,
    "total_revenue": 38400.00
}
```

---

## How Things Connect

### Data flow

```
CRM (GHL/HubSpot/etc.)
  │
  │ webhook fires on lead/stage change
  │
  ▼
FastAPI (POST /engine/webhooks/{provider})
  │
  │ normalise + resolve stage mapping + write
  ▼
┌─────────────────────────────────────────┐
│           engine schema                 │
│  leads │ lead_events │ stage_mappings   │
└─────────────────────────────────────────┘
  ▲                           │
  │                           │ direct SQL read
  │                           ▼
Bot (processor.py)        Metabase
  after booking confirmed     (read-only user)
```

CRM webhooks go directly to the FastAPI app. No n8n in the engine path. n8n remains in use for the bot's inbound SMS flow (it works, don't touch it), but all engine ingestion is handled in application code where auth, validation, mapping, and error handling are controlled properly.

### Bot → Engine (internal path)

When the bot successfully books an appointment, inside `processor.py`:

1. Get the contact's CRM ID (from inbound event payload or `bot.contacts` metadata)
2. Call `resolve_or_create_lead(tenant_id, contact_provider, contact_external_id)`
   - Queries `engine.leads` for an open lead matching that contact
   - If found → returns `lead_id`
   - If not found → creates a new lead with `provider = 'bot'`, returns `lead_id`
3. Call `write_lead_event(lead_id, event_type='appointment_booked', source='bot', ...)`

Both functions live in a new module: `app/engine/events.py`. The bot imports and calls them. No adapter restructuring needed.

**Lead resolution query:**

```sql
SELECT lead_id FROM engine.leads
WHERE tenant_id = $1
  AND contact_provider = $2
  AND contact_external_id = $3
  AND is_open = TRUE
ORDER BY created_at DESC
LIMIT 1;
```

### CRM → Engine (webhook endpoint, no n8n)

CRM webhooks hit the FastAPI app directly at `POST /engine/webhooks/{provider}`. The endpoint handles normalisation, stage mapping, and writing — all in application code.

1. CRM fires a webhook when a lead is created or changes stage
2. FastAPI receives the raw provider payload at `/engine/webhooks/ghl` (or `/engine/webhooks/hubspot`, etc.)
3. A provider-specific parser extracts the relevant fields into a standard internal shape:

```python
# Internal event shape (after parsing)
{
    "tenant_id": "...",
    "provider": "ghl",
    "lead_external_id": "opp_abc123",
    "contact_external_id": "contact_xyz789",
    "event_type": "stage_changed",
    "raw_stage": "Proposal Sent",
    "lead_value": 15000.00,
    "occurred_at": "2026-02-16T14:30:00Z",
    "source_event_id": "webhook_delivery_12345",
    "raw_payload": { ... }
}
```

4. The endpoint resolves `raw_stage` → `canonical_stage` via `engine.stage_mappings`
5. Upserts the lead in `engine.leads`
6. Inserts the event in `engine.lead_events`

If no stage mapping exists, the event is still written with `canonical_stage = NULL` and a warning is logged. No data is lost.

**Why not n8n?** n8n adds a hop, a second system to debug, and opaque error handling. The webhook parsing is simple — extract fields, resolve mapping, write. That's 50 lines of Python with full control over auth, validation, and logging. n8n remains in use for the bot's SMS ingestion (it works, changing it is unnecessary churn), but new engine work stays in the codebase.

### Engine → Metabase (read path)

Metabase connects directly to Postgres with a read-only user. No API layer in between.

```sql
CREATE ROLE metabase_reader WITH LOGIN PASSWORD '...';
GRANT USAGE ON SCHEMA engine TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA engine TO metabase_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA engine GRANT SELECT ON TABLES TO metabase_reader;

-- For tenant name lookups in dashboards
GRANT USAGE ON SCHEMA core TO metabase_reader;
GRANT SELECT ON core.tenants TO metabase_reader;
```

---

## Lead Resolution — The Edge Case

### Normal flow (most cases)

1. Lead fills form → CRM creates contact + opportunity → CRM webhook fires → FastAPI writes to engine (lead exists with CRM external_id)
2. Lead sends SMS → bot processes → bot looks up open lead by contact_external_id → **finds it** → writes `appointment_booked` event

### Edge case: bot runs before CRM webhook

If the bot processes a message before the CRM webhook arrives:

1. Bot looks up open lead by contact → **not found**
2. Bot creates a lead with `provider = 'bot'` and a generated external_id
3. CRM webhook arrives → creates a second lead with `provider = 'ghl'` and the real CRM external_id
4. Two rows for the same real-world lead, linked by `contact_external_id`

**V1 decision:** Accept this. The shared `contact_external_id` allows Metabase queries to aggregate when needed. Reconciliation is Phase 2.

**Mitigation:** CRM opportunity creation typically happens before SMS engagement. The webhook fires first.

---

## What Metabase Can Track

### Pipeline metrics
- **Pipeline funnel** — leads reaching each canonical stage (bar chart)
- **Stage conversion rates** — % of leads moving from stage A to stage B (table)
- **Active pipeline** — leads by current stage with total value (bar chart)
- **Lead volume over time** — new leads per week/month (line chart)

### Time metrics
- **Time in each stage** — avg and median days (bar chart)
- **Sales cycle length** — lead_created to lead_won, avg and median (number)
- **Speed to first contact** — time from lead_created to first_contact event (number)

### Revenue metrics
- **Revenue per lead** — total won value / total leads created (number)
- **Revenue per won lead** — average value of won leads (number)
- **Pipeline value** — sum of lead_value for open leads (number)
- **Cash collected over time** — monthly cash_collected events (line chart)

### Bot attribution
- **Bookings by source** — bot vs crm_webhook vs manual (pie chart)
- **Bot booking show rate** — appointment_completed / appointment_booked where source = bot (number)
- **Bot first-contact speed** — time from lead_created to first_contact where source = bot (number)

### Uplift
- **Baseline vs current** — side-by-side comparison of all key metrics against the active baseline (table)

### Data quality
- **Unmapped stages** — events with NULL canonical_stage (table)
- **Stale leads** — open leads with no events in 30+ days (table)

---

## Adapter Decision

**Don't restructure adapters now.**

The existing bot adapters are outbound — they call CRM APIs (fetch slots, send messages). The engine ingestion is inbound — it receives CRM webhooks directly. Different data flow directions, different patterns.

What gets built instead:

- `app/engine/events.py` — thin module with `resolve_or_create_lead()` and `write_lead_event()` functions
- Both the bot's `processor.py` and the new FastAPI endpoint call the same functions
- No adapter changes, no import path changes

When to revisit: when outbound CRM operations are needed (e.g. backfilling historical data from GHL API, creating CRM records programmatically).

---

## V1 Constraints (Known, Accepted)

| Constraint | Why it's OK for V1 |
|------------|-------------------|
| Bot-created leads and CRM-created leads are separate rows | Linked by contact_external_id, reconciliation is Phase 2 |
| Stage mappings are manually inserted | One client, one pipeline — config UI is Phase 2 |
| Baselines are manually computed and stored | Automated baseline calculation is Phase 2 |
| No real-time notifications on events | LISTEN/NOTIFY is Phase 2 |
| No gross margin tracking | Requires cost data, which is Phase 2 |
| Canonical stages are not enforced at DB level | Enforced in application code, more flexible |
