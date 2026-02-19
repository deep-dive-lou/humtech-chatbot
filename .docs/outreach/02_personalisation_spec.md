# Personalisation Spec (v1)

## Objective

Generate a first line that signals relevance and competence without pretending familiarity. Every claim must be true or explicitly general. Felt personalisation — not manufactured intimacy.

---

## Inputs to Personalisation Engine

Required:
- `first_name`, `company`, `title`
- `signals` JSON (from enrichment — may be empty)
- `template_context` — short description of what Chris's email delivers (stub for v1, updated when template arrives)

---

## Output Schema (structured JSON)

```json
{
  "opener_first_line": "string (max 22 words)",
  "micro_insight": "string (1 sentence) | null",
  "angle_tag": "speed_to_lead | cac_leak | attribution_gap | sales_ops | conversion_rate",
  "confidence_score": 0.0,
  "evidence_used": [
    {"signal_key": "hiring", "source_url": "https://..."}
  ],
  "risk_flags": [],
  "rung": 1
}
```

The opener is inserted as the first line of Chris's email. `micro_insight` is optional — used as a PS line or bridge sentence if present.

---

## Personalisation Rung Ladder

Always choose the highest achievable rung based on available evidence.

| Rung | Description | Example |
|---|---|---|
| 5 | Specific + evidence-backed | "Saw you're hiring a Head of Sales — that usually means the current process is hitting capacity." |
| 4 | Specific but light | "You're running ads to your quote page — curious how that's converting." |
| 3 | Industry-specific pattern | "Most MD's in construction tell us their sales process is built around one or two key people." |
| 2 | Role-based empathy | "As MD, you're usually the one who knows where revenue is leaking — even if it's hard to prove." |
| 1 | Human neutral | "Came across BuildCo while looking at companies doing interesting things in construction." |

Never fabricate rung 5. If the evidence isn't in `signals`, don't claim it.

---

## Signal Priority (best to worst)

1. Hiring for sales/revenue roles — strongest signal, maps directly to HumTech's offer
2. Running paid ads — acquisition spend without conversion infrastructure is HumTech's entry
3. Tech stack — CRM type / absence of booking flow signals systems gap
4. Recent content / posts — only if genuinely specific, not generic
5. Company growth announcements — funding, expansion, new office

---

## Truth Rules (non-negotiable)

1. No invented facts. If a signal doesn't exist in `evidence_used`, don't reference it.
2. Every personalised claim must cite a `source_url`.
3. Inferences must be framed as observations, not facts ("usually means", "suggests", not "you are struggling with").
4. If `risk_flags` contains `hallucination_risk` — BLOCK, do not send.

---

## Anti-Patterns

- "Loved your post about X" — only valid if post is in signals with source_url
- "I noticed you're struggling with..." — too accusatory
- "I saw you're using HubSpot" — only if CRM is confirmed in tech_stack
- Complimenting the company without basis ("What you're building is impressive")
- Repeating what Chris's template body already says

---

## Risk Flags

| Flag | Meaning | Action |
|---|---|---|
| `hallucination_risk` | Claim made without evidence_used entry | BLOCK |
| `privacy_risk` | Personal info beyond public business context | BLOCK |
| `tone_risk` | Too familiar, too salesy, guilt/pressure | NEEDS_REVIEW |
| `duplication_risk` | Opener repeats the template's main claim | NEEDS_REVIEW |

---

## Review Routing

| Condition | Route |
|---|---|
| confidence >= 0.7, evidence present, no flags | AUTO_SEND |
| confidence 0.4–0.69, or weak signals | NEEDS_REVIEW |
| any BLOCK flag, or confidence < 0.4 | BLOCK |
| missing required fields (email, name) | BLOCK |

Chris sees all NEEDS_REVIEW in the UI. BLOCK leads are logged but not shown unless he filters for them.

---

## UK Tone Rules

- Calm, direct, not salesy
- No hype: "game-changing", "revolutionary", "guaranteed"
- No pressure or guilt tactics
- Don't lead with AI unless prospect is clearly tech-forward
- Write as a human would — contractions fine, not overly formal

---

## Prompt Versioning

Every personalisation call stores:
- `prompt_version` (e.g. "v1.0")
- `model` (e.g. "claude-sonnet-4-6")
- `timestamp`

This allows A/B comparison in Metabase when the prompt is updated.
