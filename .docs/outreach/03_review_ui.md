# Review UI Spec (v1)

## Purpose

Chris's daily interface. He reviews the generated batch, edits any openers he's not happy with, removes leads that don't feel right, then approves and sends.

No login required (v1 — internal tool on private subdomain). No React. Plain HTML + Jinja2.

---

## Routes

```
GET  /outreach/review          → today's batch
POST /outreach/lead/{id}/edit  → update opener text
POST /outreach/lead/{id}/remove → remove from today's batch
POST /outreach/send            → approve all remaining + push to Instantly
GET  /outreach/review?date=... → historical batch (read-only)
```

---

## Review Page Layout

```
┌─────────────────────────────────────────────────────┐
│  Today's Batch — 19 Feb 2026                        │
│  103 ready  |  4 needs review  |  12 blocked        │
│                                          [Send 103 →]│
├─────────────────────────────────────────────────────┤
│  ⚠ NEEDS REVIEW (4)                                 │
│  ─────────────────────────────────────────────────  │
│  James Reid · Managing Director · BuildCo           │
│  "Saw you're scaling — wanted to reach out."        │
│  Rung 2 · Confidence 0.48 · weak signals            │
│  [Edit opener]  [Remove]                            │
├─────────────────────────────────────────────────────┤
│  ✓ AUTO-SEND (103)                                  │
│  ─────────────────────────────────────────────────  │
│  Sarah Jones · CEO · Acme Roofing                   │
│  "Noticed you're hiring a Head of Sales — that      │
│   usually means the current process is at limit."   │
│  Rung 5 · Confidence 0.91 · hiring signal           │
│  [Edit opener]  [Remove]                            │
│                                                     │
│  ... (collapsible list)                             │
├─────────────────────────────────────────────────────┤
│  ✗ BLOCKED (12) — [Show blocked]                    │
└─────────────────────────────────────────────────────┘
```

---

## Per-Lead Display

Each card shows:
- Full name, title, company
- Generated opener (editable inline on click)
- Rung level + confidence score
- Signal that was used (e.g. "hiring signal", "ads signal")
- Actions: Edit opener, Remove

Editing opener: click text → inline textarea → Save / Cancel. No page reload (vanilla JS fetch).

---

## Send Action

`[Send 103 →]` button:
- Confirms count ("Send 103 emails?")
- POSTs to `/outreach/send`
- Shows spinner while Instantly API call runs
- On success: "103 emails queued in Instantly" + timestamp
- On failure: error message with which leads failed

After send, page becomes read-only for the day.

---

## Blocked Leads View

Hidden by default. Chris can expand to see why leads were blocked:
- Missing email
- Hallucination risk flagged
- Low confidence (below 0.4)

No action available on blocked leads in v1 (Lou reviews these via logs).

---

## Hosting

URL: `https://outreach.resg.uk` (to be configured at deploy time — Nginx reverse proxy on existing droplet)
