# Sending — Instantly.ai Integration (v1)

## Overview

Approved leads are pushed to Instantly via API. Instantly handles the sequence, sending schedule, and per-domain throttling.

---

## Setup Requirements (one-time)

- Instantly account created and API key obtained → `INSTANTLY_API_KEY` in `.env`
- Sending domains warmed (3–5 domains, 2–4 weeks warmup before full volume)
- Each domain: SPF, DKIM, DMARC configured
- Campaign created in Instantly UI with:
  - Email sequence (stub body for v1, updated when Chris's template arrives)
  - Daily sending limit per account
  - Per-domain cap: max 5 sends/day to same company domain
  - Unsubscribe link included

Campaign ID stored as `INSTANTLY_CAMPAIGN_ID` in `.env`.

---

## API Integration

### Add Lead to Campaign

```
POST https://api.instantly.ai/api/v1/lead/add
Headers: Content-Type: application/json
Body:
{
  "api_key": "...",
  "campaign_id": "...",
  "skip_if_in_workspace": true,
  "leads": [
    {
      "email": "james@buildco.co.uk",
      "first_name": "James",
      "last_name": "Reid",
      "company_name": "BuildCo",
      "personalization": "Saw you're hiring a Head of Sales — that usually means the current process is at capacity.",
      "website": "buildco.co.uk"
    }
  ]
}
```

`personalization` maps to the `{{personalization}}` variable in Chris's template. This is the AI-generated opener.

### Response Handling

- `200` — lead added, log as `status=queued`
- `4xx` — invalid lead data, log as `status=failed` with reason
- `5xx` — Instantly error, retry once, then log as `status=failed`

---

## Email Sequence Structure (v1 stub)

Sequence is defined in Instantly UI, not in code.

```
Email 1 (day 0):
  Subject: [TBD — Chris to provide]
  Body: {{personalization}} [Chris's template body]

Follow-up 1 (day 3):
  Subject: Re: [original subject]
  Body: [Chris's follow-up — TBD]

Follow-up 2 (day 7 — breakup):
  Subject: Re: [original subject]
  Body: [Chris's breakup — TBD]
```

Template body is a placeholder until Chris's email arrives. The `{{personalization}}` variable is always the AI-generated first line.

---

## Deliverability Controls

Managed in Instantly UI (not in code):
- Daily sending cap per account
- Per-domain gap (don't send to same company domain more than once per week)
- Warmup enabled on all sending accounts
- Bounce handling: Instantly auto-suppresses hard bounces

Suppression list (managed in DB):
- Existing clients (by domain)
- Unsubscribes (synced via n8n reply webhook)
- Previous bounces (synced from Instantly webhook)

---

## Event Logging

Every send attempt logged to `outreach_events` table:

```
lead_id | event_type    | timestamp           | meta
--------|---------------|---------------------|--------------------------------
uuid    | queued        | 2026-02-19 08:01:00 | {"instantly_lead_id": "..."}
uuid    | sent          | 2026-02-19 08:04:00 | {"email": 1, "sequence": "v1"}
uuid    | failed        | 2026-02-19 08:01:00 | {"reason": "invalid email"}
```
