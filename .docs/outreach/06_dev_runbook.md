# Outreach — Dev Runbook

## Starting the server locally

```powershell
Start-Process -FilePath 'C:\Users\loumk\humtech-platform\.venv\Scripts\python.exe' `
  -ArgumentList '-m','uvicorn','app.main:app','--port','8000' `
  -WorkingDirectory 'C:\Users\loumk\humtech-platform' `
  -WindowStyle Hidden
```

Review UI: http://localhost:8000/outreach/review

Stop server:
```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
```

---

## Required env vars (add to .env)

```
# Outreach pipeline
APOLLO_API_KEY=
PROXYCURL_API_KEY=
ANTHROPIC_API_KEY=
INSTANTLY_API_KEY=
INSTANTLY_CAMPAIGN_ID=
```

---

## Running the pipeline manually (from VS Code terminal)

```bash
curl -X POST http://localhost:8000/outreach/pipeline/run
```

Or from Python:
```python
import httpx, asyncio
async def run():
    async with httpx.AsyncClient() as c:
        r = await c.post("http://localhost:8000/outreach/pipeline/run", timeout=300)
        print(r.json())
asyncio.run(run())
```

Returns: `{ok, stats: {sourced, skipped, enriched, auto_send, needs_review, blocked, errors}}`

---

## Running a migration

```python
python -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv()
async def run():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    sql = open('scripts/migrations/NNN_name.sql').read()
    await conn.execute(sql)
    await conn.close()
    print('done')
asyncio.run(run())
"
```

---

## Adding a suppression manually

```bash
curl -X POST http://localhost:8000/outreach/suppress \
  -H "Content-Type: application/json" \
  -d '{"email": "person@company.com", "reason": "client"}'
```

Or by domain:
```bash
curl -X POST http://localhost:8000/outreach/suppress \
  -H "Content-Type: application/json" \
  -d '{"domain": "company.com", "reason": "competitor"}'
```

---

## What's built vs pending

### Built
- DB schema (migration 003)
- Lead sourcing via Apollo API (`pipeline.py:source_leads`)
- LinkedIn enrichment via Proxycurl (`pipeline.py:_enrich_linkedin`)
- Website analysis via Claude Haiku (`pipeline.py:_analyse_website`)
- Personalisation engine via Claude Sonnet (`pipeline.py:_generate_personalisation`)
- Rung 1–5 quality gate (`pipeline.py:_determine_review_status`)
- Review UI for Chris (`routes.py`, `templates/review.html`)
- Instantly sender (`sender.py`)
- Suppression endpoint (for n8n)
- Event logging to `outreach.events`

### Pending (needs API keys)
- Apollo API key → pipeline runs
- Proxycurl key → LinkedIn enrichment
- Anthropic key → personalisation and website analysis
- Instantly key + campaign ID → sending

### Not yet built
- Meta Ad Library signal (stubbed — add to `_enrich_*` when ready)
- n8n reply handling workflow (spec in `05_reply_handling.md`)
- Metabase outreach dashboard
- Deployment to droplet + outreach.resg.uk subdomain
- Cron schedule for daily pipeline run

---

## Prompt versioning

Current: `PROMPT_VERSION = "v1.0"` in `pipeline.py`

When changing the personalisation prompt:
1. Increment `PROMPT_VERSION`
2. Note the change in this doc
3. After 2–3 days compare confidence scores and reply rates in Metabase between versions

---

## Known issues

- `strftime("%b")` on Python 3.14 on Windows — date formatting uses ISO string fallback in routes.py
