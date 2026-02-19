from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

import httpx
from anthropic import AsyncAnthropic

from app.config import settings
from app.db import get_pool
from app.outreach.models import (
    insert_enrichment,
    insert_lead,
    insert_personalisation,
    insert_suppression,
    is_suppressed,
    log_event,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0"
PERSONALISATION_MODEL = "claude-sonnet-4-6"
ENRICHMENT_MODEL = "claude-haiku-4-5-20251001"

TEMPLATE_CONTEXT = (
    "HumTech offers a done-for-you AI Revenue Engine — AI booking bot, "
    "speed-to-lead automation, sales process improvement, and full ad management. "
    "They only get paid when revenue goes up. The email introduces this and asks for a call."
)

# ICP filters for Apollo
APOLLO_TITLES = [
    "CEO", "MD", "Managing Director", "Founder", "Co-Founder",
    "COO", "Commercial Director", "Head of Sales", "Sales Director",
    "VP Sales", "Director of Sales",
]
APOLLO_SENIORITIES = ["owner", "founder", "c_suite", "vp", "director"]

# ---------------------------------------------------------------------------
# Lead sourcing — Apollo
# ---------------------------------------------------------------------------

async def source_leads(limit: int = 150) -> list[dict[str, Any]]:
    """Pull ICP-matched prospects from Apollo People Search."""
    if not settings.apollo_api_key:
        logger.warning("APOLLO_API_KEY not set — returning empty list")
        return []

    payload = {
        "api_key": settings.apollo_api_key,
        "person_titles": APOLLO_TITLES,
        "person_seniorities": APOLLO_SENIORITIES,
        "contact_email_status_v2": ["verified", "likely to engage"],
        "organization_locations": ["United Kingdom"],
        "organization_num_employees_ranges": ["50,500"],
        "per_page": min(limit, 100),
        "page": 1,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.post(
                "https://api.apollo.io/api/v1/mixed_people/search",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            people = data.get("people", [])
            logger.info("Apollo returned %d prospects", len(people))
            return people
        except Exception as e:
            logger.error("Apollo sourcing failed: %s", e)
            return []


def _parse_apollo_person(person: dict[str, Any]) -> dict[str, Any]:
    """Normalise an Apollo person record into our lead schema."""
    org = person.get("organization") or {}
    domain = org.get("primary_domain") or person.get("organization_domain", "")
    return {
        "email": person.get("email", ""),
        "first_name": person.get("first_name", ""),
        "last_name": person.get("last_name"),
        "title": person.get("title"),
        "company": org.get("name") or person.get("organization_name"),
        "company_domain": domain,
        "linkedin_url": person.get("linkedin_url"),
        "industry": org.get("industry"),
        "employee_count": org.get("estimated_num_employees"),
        "city": person.get("city"),
        "apollo_id": person.get("id"),
    }


# ---------------------------------------------------------------------------
# Enrichment — Proxycurl
# ---------------------------------------------------------------------------

async def _enrich_linkedin(linkedin_url: str) -> dict[str, Any]:
    """Pull LinkedIn profile via Proxycurl."""
    if not settings.proxycurl_api_key or not linkedin_url:
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://nubela.co/proxycurl/api/v2/linkedin",
                headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
                params={"url": linkedin_url, "activities": "include"},
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Proxycurl %s for %s", resp.status_code, linkedin_url)
        except Exception as e:
            logger.warning("Proxycurl failed for %s: %s", linkedin_url, e)
    return {}


def _parse_linkedin_signals(profile: dict[str, Any]) -> dict[str, Any]:
    """Extract actionable signals from a Proxycurl profile."""
    if not profile:
        return {}

    signals: dict[str, Any] = {}

    # Recent activity / posts
    activities = profile.get("activities") or []
    if activities:
        latest = activities[0]
        signals["content"] = {
            "recent_post_summary": latest.get("title", "")[:150],
            "source_url": latest.get("link", ""),
        }

    return signals


# ---------------------------------------------------------------------------
# Enrichment — Website analysis (Claude)
# ---------------------------------------------------------------------------

async def _analyse_website(domain: str) -> dict[str, Any]:
    """Fetch company homepage and extract signals using Claude Haiku."""
    if not domain or not settings.anthropic_api_key:
        return {}

    url = f"https://{domain}"
    html = ""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text[:6000]
    except Exception as e:
        logger.warning("Website fetch failed for %s: %s", domain, e)
        return {}

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=ENRICHMENT_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    f"Analyse this website HTML and return JSON with these fields:\n"
                    f"- has_booking_flow: boolean (is there a book demo/call/meeting CTA?)\n"
                    f"- crm_detected: string or null (HubSpot, Salesforce etc based on scripts)\n"
                    f"- tech_stack: list of strings (detected tools)\n"
                    f"- growth_language: boolean (scaling, growth, expansion language?)\n\n"
                    f"HTML: {html}\n\nReturn ONLY valid JSON, no explanation."
                ),
            }],
        )
        return json.loads(msg.content[0].text)
    except Exception as e:
        logger.warning("Website analysis failed for %s: %s", domain, e)
        return {}


# ---------------------------------------------------------------------------
# Personalisation — Claude
# ---------------------------------------------------------------------------

def _determine_review_status(result: dict[str, Any]) -> str:
    flags = result.get("risk_flags", [])
    confidence = result.get("confidence_score", 0.0)

    if "hallucination_risk" in flags or "privacy_risk" in flags:
        return "blocked"
    if confidence < 0.4 or not result.get("opener_first_line"):
        return "blocked"
    if confidence < 0.7 or "tone_risk" in flags or "duplication_risk" in flags:
        return "needs_review"
    if not result.get("evidence_used"):
        return "needs_review"
    return "auto_send"


async def _generate_personalisation(
    lead: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    """Run Claude personalisation engine. Returns structured output dict."""
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""You are writing a personalised opening line for a cold email on behalf of HumTech.

HumTech context: {TEMPLATE_CONTEXT}

Prospect:
- Name: {lead['first_name']} {lead.get('last_name', '')}
- Title: {lead.get('title', 'unknown')}
- Company: {lead.get('company', 'unknown')}
- Industry: {lead.get('industry', 'unknown')}
- Domain: {lead.get('company_domain', '')}

Available signals (use ONLY what is here — never invent):
{json.dumps(signals, indent=2)}

Rung system (choose highest achievable):
- Rung 5: Specific + evidence-backed (cite real signal with source_url)
- Rung 4: Specific but light (category observation with some basis)
- Rung 3: Industry-specific pattern (no personal claim about this company)
- Rung 2: Role-based empathy (title-based, non-assumptive)
- Rung 1: Human neutral (no signals available)

UK tone: calm, direct, not salesy. Max 22 words for opener_first_line.
Do not repeat the HumTech offer — the template body does that.

Return ONLY valid JSON:
{{
  "opener_first_line": "string (max 22 words)",
  "micro_insight": "string or null",
  "angle_tag": "speed_to_lead|cac_leak|attribution_gap|sales_ops|conversion_rate",
  "confidence_score": 0.0,
  "evidence_used": [{{"signal_key": "string", "source_url": "string"}}],
  "risk_flags": [],
  "rung": 1
}}

Truth rules — non-negotiable:
1. Only reference signals present in the signals JSON above.
2. Every specific claim needs a source_url in evidence_used.
3. If you reference something without evidence, add "hallucination_risk" to risk_flags.
4. Frame inferences as observations ("usually means", "suggests") not facts."""

    fallback = {
        "opener_first_line": f"Came across {lead.get('company', 'your company')} and wanted to reach out.",
        "micro_insight": None,
        "angle_tag": "sales_ops",
        "confidence_score": 0.3,
        "evidence_used": [],
        "risk_flags": [],
        "rung": 1,
    }

    try:
        msg = await client.messages.create(
            model=PERSONALISATION_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(msg.content[0].text)
        result.setdefault("evidence_used", [])
        result.setdefault("risk_flags", [])
        result.setdefault("rung", 1)
        return result
    except Exception as e:
        logger.warning("Personalisation failed for %s: %s", lead.get("email"), e)
        return fallback


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

async def run_pipeline(batch_date: Optional[date] = None) -> dict[str, Any]:
    """
    Full pipeline: source → enrich → personalise → store.
    Returns summary stats.
    """
    today = batch_date or date.today()
    stats = {
        "batch_date": today.isoformat(),
        "sourced": 0,
        "skipped_suppressed": 0,
        "skipped_duplicate": 0,
        "enriched": 0,
        "auto_send": 0,
        "needs_review": 0,
        "blocked": 0,
        "errors": 0,
    }

    prospects = await source_leads(limit=150)
    stats["sourced"] = len(prospects)

    if not prospects:
        logger.warning("Pipeline: no prospects sourced")
        return stats

    pool = await get_pool()

    for person in prospects:
        lead = _parse_apollo_person(person)

        if not lead["email"] or not lead["first_name"]:
            stats["errors"] += 1
            continue

        domain = lead.get("company_domain")

        async with pool.acquire() as conn:
            # Suppression check
            if await is_suppressed(conn, lead["email"], domain):
                stats["skipped_suppressed"] += 1
                continue

            # Insert lead (skip if email already exists)
            lead_id = await insert_lead(
                conn,
                batch_date=today,
                **{k: lead[k] for k in lead},
            )
            if not lead_id:
                stats["skipped_duplicate"] += 1
                continue

            await log_event(conn, lead_id=lead_id, event_type="imported")

        # --- Enrichment (outside transaction — slow network calls) ---
        signals: dict[str, Any] = {}

        li_profile = await _enrich_linkedin(lead.get("linkedin_url", ""))
        li_signals = _parse_linkedin_signals(li_profile)
        signals.update(li_signals)

        if domain:
            website_signals = await _analyse_website(domain)
            if website_signals:
                signals["website"] = website_signals

        async with pool.acquire() as conn:
            await insert_enrichment(conn, lead_id=lead_id, signals=signals)
            await log_event(conn, lead_id=lead_id, event_type="enriched")
            stats["enriched"] += 1

        # --- Personalisation ---
        p = await _generate_personalisation(lead, signals)
        review_status = _determine_review_status(p)

        async with pool.acquire() as conn:
            await insert_personalisation(
                conn,
                lead_id=lead_id,
                opener_first_line=p.get("opener_first_line", ""),
                micro_insight=p.get("micro_insight"),
                angle_tag=p.get("angle_tag"),
                confidence_score=float(p.get("confidence_score", 0.0)),
                evidence_used=p.get("evidence_used", []),
                risk_flags=p.get("risk_flags", []),
                rung=int(p.get("rung", 1)),
                review_status=review_status,
                prompt_version=PROMPT_VERSION,
                model=PERSONALISATION_MODEL,
            )
            await conn.execute(
                "UPDATE outreach.leads SET status = 'personalised', updated_at = now() WHERE lead_id = $1::uuid",
                lead_id,
            )
            await log_event(
                conn,
                lead_id=lead_id,
                event_type="personalised",
                meta={"review_status": review_status, "rung": p.get("rung"), "confidence": p.get("confidence_score")},
            )

        stats[review_status] += 1

    logger.info("Pipeline complete: %s", stats)
    return stats
