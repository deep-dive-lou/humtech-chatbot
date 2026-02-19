from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

INSTANTLY_ADD_LEADS_URL = "https://api.instantly.ai/api/v1/lead/add"


async def push_to_instantly(leads: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Push a list of approved leads to the Instantly campaign.

    Each lead dict must have: email, first_name, last_name, company, opener.
    Returns summary: {sent: int, failed: int, errors: list}
    """
    if not settings.instantly_api_key:
        raise RuntimeError("INSTANTLY_API_KEY not configured")
    if not settings.instantly_campaign_id:
        raise RuntimeError("INSTANTLY_CAMPAIGN_ID not configured")

    instantly_leads = [
        {
            "email": lead["email"],
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "company_name": lead.get("company", ""),
            "website": lead.get("company_domain", ""),
            "personalization": lead["opener"],
        }
        for lead in leads
    ]

    payload = {
        "api_key": settings.instantly_api_key,
        "campaign_id": settings.instantly_campaign_id,
        "skip_if_in_workspace": True,
        "leads": instantly_leads,
    }

    sent = 0
    failed = 0
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(INSTANTLY_ADD_LEADS_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            sent = len(instantly_leads)
            logger.info("Instantly: queued %d leads", sent)
        except httpx.HTTPStatusError as e:
            logger.error("Instantly API error: %s — %s", e.response.status_code, e.response.text)
            failed = len(instantly_leads)
            errors.append({"status": e.response.status_code, "detail": e.response.text[:200]})
        except Exception as e:
            logger.error("Instantly request failed: %s", e)
            failed = len(instantly_leads)
            errors.append({"detail": str(e)})

    return {"sent": sent, "failed": failed, "errors": errors}
