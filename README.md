# HumTech Platform

FastAPI monorepo for HumTech's AI revenue infrastructure.

## Modules

| Module | Path | Status |
|---|---|---|
| Booking chatbot | `app/bot/` | Live |
| Revenue engine | `app/engine/` | Live |
| Cold outreach | `app/outreach/` | Built — pending API keys |

## Stack

- Python + FastAPI
- PostgreSQL (DigitalOcean managed)
- asyncpg
- Anthropic Claude API
- Jinja2 templates (review UI)

## Running locally

```bash
# Install deps
python -m pip install -r requirements.txt

# Start server
python -m uvicorn app.main:app --port 8000 --reload
```

Or via PowerShell (persistent, no terminal needed):
```powershell
Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--port','8000' -WorkingDirectory (Get-Location) -WindowStyle Hidden
```

## Key URLs (local)

- Health: http://localhost:8000/health
- Outreach review: http://localhost:8000/outreach/review
- Trigger pipeline: POST http://localhost:8000/outreach/pipeline/run

## Migrations

SQL migration files in `scripts/migrations/`. Run against the DO database:

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

## Docs

Full technical docs in `.docs/`. See `.CLAUDE.md` for index.
