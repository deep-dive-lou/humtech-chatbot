# Outreach Module — System Overview (v1)

## What this is

A cold outreach pipeline that sources, enriches, personalises, and sends 100 emails/day to HumTech's ICP. Lives in `app/outreach/` within the humtech-platform FastAPI app.

Non-goals (v1): LinkedIn automation, multi-channel sequencing, CRM pipeline management.

---

## How it fits into the platform

```
humtech-platform FastAPI app
  app/bot/        ← booking chatbot (existing)
  app/engine/     ← revenue engine events (existing)
  app/outreach/   ← this module
    pipeline.py   lead sourcing + enrichment + personalisation
    models.py     DB schemas
    routes.py     review UI + approve/send endpoints
    sender.py     Instantly API client
```

Shares: FastAPI app instance, SQLite DB, GHL adapter, config/env pattern.

---

## Component Map

```
Apollo API
  → 150 ICP-matched prospects/day
  → stored as leads (status=new)

Enrichment layer (per lead)
  → Proxycurl: LinkedIn profile, recent posts, hiring signals
  → Meta Ad Library API: is prospect running ads?
  → Claude scrapes website: booking flow, CRM pixels, tech stack
  → stored as enrichment JSON (status=enriched)

Personalisation engine (Claude API)
  → rung selection based on available signals
  → returns structured JSON: opener, confidence, evidence_used, risk_flags
  → quality gate: AUTO_SEND / NEEDS_REVIEW / BLOCK
  → stored with prompt_version, model, timestamp

Review UI (Chris)
  → GET /outreach/review → today's batch
  → edit openers inline, remove leads
  → POST /outreach/send → triggers Instantly

Instantly.ai
  → sends approved batch
  → webhook on reply → n8n

n8n
  → classifies reply (positive/neutral/negative/unsub)
  → positive → GHL "Cold Outreach" pipeline stage
  → unsub → suppression list in DB
```

---

## Key Dependencies

| Dependency | Purpose | Config key |
|---|---|---|
| Apollo API | Lead sourcing | `APOLLO_API_KEY` |
| Proxycurl API | LinkedIn enrichment | `PROXYCURL_API_KEY` |
| Meta Ad Library API | Ad signal | no key required (public) |
| Anthropic API | Personalisation + website scraping | `ANTHROPIC_API_KEY` |
| Instantly API | Email sending | `INSTANTLY_API_KEY` |
| GHL API | CRM handoff | `GHL_API_KEY` (existing) |

---

## Data Flow Summary

```
new → enriched → personalised → [queued | needs_review | blocked] → sent
                                                                  → replied
                                                                  → classified
```

Status transitions are logged as events for Metabase reporting.
