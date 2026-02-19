from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.db import get_pool
from app.outreach import models
from app.outreach.pipeline import run_pipeline
from app.outreach.sender import push_to_instantly

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["outreach"])

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


# ---------------------------------------------------------------------------
# Review UI
# ---------------------------------------------------------------------------

@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, batch_date: Optional[str] = None):
    today = date.fromisoformat(batch_date) if batch_date else date.today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        leads = await models.get_batch(conn, today)
        counts = await models.get_batch_counts(conn, today)

    needs_review = [l for l in leads if l["review_status"] == "needs_review"]
    auto_send = [l for l in leads if l["review_status"] == "auto_send"]
    blocked = [l for l in leads if l["review_status"] == "blocked"]

    return templates.TemplateResponse("review.html", {
        "request": request,
        "batch_date": today.strftime("%d %b %Y").lstrip("0"),
        "batch_date_iso": today.isoformat(),
        "counts": counts,
        "needs_review": needs_review,
        "auto_send": auto_send,
        "blocked": blocked,
    })


# ---------------------------------------------------------------------------
# Lead actions (called via JS fetch — no page reload)
# ---------------------------------------------------------------------------

class EditOpenerRequest(BaseModel):
    opener: str


@router.post("/lead/{personalisation_id}/edit")
async def edit_opener(personalisation_id: str, body: EditOpenerRequest):
    if not body.opener.strip():
        raise HTTPException(status_code=400, detail="Opener cannot be empty")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await models.update_opener(
            conn,
            personalisation_id=personalisation_id,
            opener=body.opener.strip(),
        )
    return {"ok": True}


@router.post("/lead/{personalisation_id}/remove")
async def remove_lead(personalisation_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await models.remove_lead(conn, personalisation_id=personalisation_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Send batch
# ---------------------------------------------------------------------------

@router.post("/send")
async def send_batch(batch_date: Optional[str] = None):
    today = date.fromisoformat(batch_date) if batch_date else date.today()
    pool = await get_pool()

    async with pool.acquire() as conn:
        leads = await models.get_sendable_leads(conn, today)

    if not leads:
        return {"ok": True, "sent": 0, "failed": 0, "message": "No sendable leads for this date"}

    result = await push_to_instantly(leads)

    async with pool.acquire() as conn:
        for lead in leads:
            if result["failed"] == 0:
                await models.mark_lead_sent(conn, lead["lead_id"])
                await models.log_event(conn, lead_id=lead["lead_id"], event_type="sent")
            else:
                await models.mark_lead_failed(conn, lead["lead_id"])
                await models.log_event(conn, lead_id=lead["lead_id"], event_type="failed")

    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Pipeline trigger (for cron / n8n / manual run from VS Code)
# ---------------------------------------------------------------------------

@router.post("/pipeline/run")
async def trigger_pipeline(batch_date: Optional[str] = None):
    today = date.fromisoformat(batch_date) if batch_date else date.today()
    stats = await run_pipeline(batch_date=today)
    return {"ok": True, "stats": stats}


# ---------------------------------------------------------------------------
# Suppression (called by n8n on unsubscribe/negative reply)
# ---------------------------------------------------------------------------

class SuppressRequest(BaseModel):
    email: Optional[str] = None
    domain: Optional[str] = None
    reason: str = "unsubscribe"


@router.post("/suppress")
async def suppress(body: SuppressRequest):
    if not body.email and not body.domain:
        raise HTTPException(status_code=400, detail="email or domain required")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await models.insert_suppression(
            conn,
            email=body.email,
            domain=body.domain,
            reason=body.reason,
        )
    return {"ok": True}
