# Outreach Pipeline (v1)

## Overview

```
Apollo API → Proxycurl → Meta Ad Library → Claude website scrape → personalisation input
```

Runs daily (scheduled or triggered). Targets ~150 leads to produce ~100 sendable messages after quality gating.

---

## Stage 1 — Lead Sourcing (Apollo API)

Endpoint: `POST /people/search`

ICP filter criteria:
- Location: United Kingdom
- Employee count: 50–500 (proxy for £5M–£50M revenue)
- Seniority: owner, founder, c_suite, vp, director
- Titles (include): CEO, MD, Managing Director, Founder, COO, Commercial Director, Head of Sales, Sales Director
- Exclude: existing clients (by domain), competitors, previous bounces

Fields to pull per lead:
- `first_name`, `last_name`, `email` (verified preferred)
- `title`, `company_name`, `company_domain`
- `linkedin_url`
- `industry`, `employee_count`
- `city`

Output: lead stored with `status=new`. Dedupe by email — skip if email already exists in DB.

Daily volume target: 150 leads pulled → expect ~100 to pass quality gate.

---

## Stage 2 — Enrichment

### 2a. Proxycurl — LinkedIn Profile

Endpoint: `GET /proxycurl/api/v2/linkedin`
Input: `linkedin_url`
Cost: ~$0.01 per profile

Extract:
- `headline` — current role description
- `summary` — about section
- `experiences[0]` — current company + title + start date (tenure signal)
- `activities[-3:]` — last 3 posts (content signal)
- `recommendations_count` — credibility signal (secondary)

Fallback: if no LinkedIn URL from Apollo, skip Proxycurl, drop to rung ≤3.

### 2b. Meta Ad Library API — Paid Ads Signal

Endpoint: `GET https://www.facebook.com/ads/library/` (public, no auth)
Input: company domain / name search
Extract:
- Is the company running active ads? (boolean)
- Landing page URL if detectable
- Ad count (proxy for spend level)

Store as: `ads_active: bool`, `ads_landing_page: str | null`

### 2c. Claude — Website Analysis

Input: `company_domain`
Task: fetch homepage, analyse for:
- Booking/demo flow present? (strong signal — they're trying to convert)
- CRM or tracking pixels visible? (HubSpot, Salesforce, GA4, Meta Pixel)
- Pricing page? (signals sales-led vs product-led)
- Language around growth, scale, hiring?

Output: structured dict — `has_booking_flow`, `crm_detected`, `tech_stack[]`, `growth_language: bool`

This is done via Claude with web fetch — no external API cost beyond Anthropic token usage.

---

## Stage 3 — Enrichment Output Schema

What a fully enriched lead looks like before personalisation:

```json
{
  "lead_id": "uuid",
  "first_name": "James",
  "last_name": "Reid",
  "email": "james@buildco.co.uk",
  "title": "Managing Director",
  "company": "BuildCo",
  "company_domain": "buildco.co.uk",
  "linkedin_url": "https://linkedin.com/in/jamesreid",
  "industry": "Construction",
  "employee_count": 120,
  "signals": {
    "hiring": {
      "active": true,
      "roles": ["Head of Sales", "BDM"],
      "source_url": "https://linkedin.com/jobs/..."
    },
    "ads": {
      "active": true,
      "landing_page": "https://buildco.co.uk/get-a-quote",
      "source_url": "https://facebook.com/ads/library/..."
    },
    "tech_stack": {
      "crm": "HubSpot",
      "booking": null,
      "analytics": ["GA4", "Meta Pixel"],
      "source_url": "buildco.co.uk"
    },
    "content": {
      "recent_post_summary": "Post about scaling their estimating team",
      "source_url": "https://linkedin.com/posts/..."
    }
  },
  "status": "enriched"
}
```

---

## Notes

- If Proxycurl fails (rate limit, profile not found), log and continue — don't block the lead
- If website fetch fails, log and continue
- Missing signals reduce the rung level, not the lead itself
- All source_urls must be stored — required by personalisation truth rules
