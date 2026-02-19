# Reply Handling (v1)

## Overview

```
Instantly reply webhook → n8n → classify → GHL / suppression / log
```

All reply processing happens in n8n. No code changes needed to handle new reply types — update the n8n workflow.

---

## Instantly Webhook Setup

In Instantly UI: Settings → Webhooks → Add webhook
- Event: `reply_received`
- URL: `https://n8n.resg.uk/webhook/outreach-reply`
- Payload includes: `lead_email`, `reply_text`, `campaign_id`, `sequence_step`

---

## n8n Workflow — `outreach-reply`

```
Webhook trigger (POST /webhook/outreach-reply)
  → Extract: email, reply_text, campaign_id
  → Claude: classify reply
      → positive | neutral | negative | unsubscribe
  → Switch on classification:
      positive  → Create GHL contact + opportunity
      neutral   → Log only (Chris may want to follow up manually)
      negative  → Suppress lead in DB, log
      unsubscribe → Suppress lead in DB, log, notify Instantly to stop sequence
```

---

## Reply Classification

Claude prompt classifies reply into one of four categories:

- `positive` — interest expressed, asks for more info, wants a call, responds to the angle
- `neutral` — not now, maybe later, forwarding to someone else
- `negative` — not interested, wrong person, strong rejection
- `unsubscribe` — unsubscribe request, remove me, stop emailing

Borderline cases (e.g. "not now but maybe Q3") → `neutral`.

---

## GHL Handoff (positive replies)

Create contact + opportunity via GHL API:

```
Contact fields:
  - first_name, last_name (from lead DB by email)
  - email
  - company_name
  - tags: ["cold-outreach", "v1"]

Opportunity fields:
  - pipeline: "Sales Pipeline" (existing)
  - stage: "Cold Outreach Reply"
  - name: "{company} — cold outreach"
  - custom fields:
      - original_opener (the personalised first line sent)
      - reply_snippet (first 200 chars of reply)
      - outreach_date
```

---

## Suppression Handling

On `negative` or `unsubscribe`:
- POST to `https://humtech-platform/outreach/suppress` with `email`
- Platform DB marks lead as suppressed
- Future pipeline runs skip suppressed emails at Apollo dedupe stage

On `unsubscribe`:
- Also call Instantly API to remove lead from all active sequences

---

## Event Logging

```
lead_id | event_type           | timestamp | meta
--------|----------------------|-----------|-------------------------------
uuid    | replied              | ...       | {"classification": "positive"}
uuid    | ghl_lead_created     | ...       | {"ghl_contact_id": "..."}
uuid    | suppressed           | ...       | {"reason": "unsubscribe"}
```

---

## Notifications (v1)

On `positive` reply: n8n sends notification to Chris.
Method: email to Chris's address (via Instantly or Gmail node in n8n).
Content: name, company, reply snippet, link to GHL opportunity.

Slack integration is a v1.5 addition.
