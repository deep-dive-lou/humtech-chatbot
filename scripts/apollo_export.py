"""
Apollo Lead Export
==================
Two modes:

  MODE 1 — Apollo UI export (free plan)
  --------------------------------------
  1. Go to app.apollo.io → People search → filter by title/location/industry
  2. Tick the leads you want → Export → CSV
  3. Drop the downloaded CSV next to this script (or pass the path as an arg)
  4. Run: python scripts/apollo_export.py path/to/apollo_export.csv
  Outputs a clean CSV to exports/ with: name, company, email, website, linkedin

  MODE 2 — Apollo API (paid plan required)
  -----------------------------------------
  Edit the CONFIG block below, then run with no arguments:
      python scripts/apollo_export.py
  Requires Basic plan ($49/month) or above.
  Outputs same clean CSV to exports/.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# CONFIG (Mode 2 — API only) — edit to change search criteria
# ---------------------------------------------------------------------------

TITLES = [
    "CEO", "MD", "Managing Director", "Founder", "Co-Founder",
    "Owner", "Director", "Commercial Director", "Head of Sales", "Sales Director",
]
SENIORITIES = ["owner", "founder", "c_suite", "director"]
LOCATIONS: list[str] = ["United Kingdom"]       # [] = any
INDUSTRIES: list[str] = []                       # [] = any
EMPLOYEE_RANGE = "51,200"                        # company headcount band
LIMIT = 50

# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

EXPORTS_DIR = Path(__file__).parent.parent / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

OUTPUT_FIELDS = ["first_name", "last_name", "title", "company", "email", "website", "linkedin", "city"]


def _save_csv(rows: list[dict], label: str = "") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    out_path = EXPORTS_DIR / f"leads{suffix}_{timestamp}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def _summary(rows: list[dict]) -> None:
    with_email = sum(1 for r in rows if r.get("email"))
    print(f"  {with_email}/{len(rows)} have an email address")
    if with_email < len(rows):
        print(f"  {len(rows) - with_email} without email (Apollo credit limit or not found)")


# ---------------------------------------------------------------------------
# Mode 1: process an Apollo UI CSV export
# ---------------------------------------------------------------------------

# Apollo exports use verbose column headers — map them to our schema
_APOLLO_COLUMN_MAP = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Title": "title",
    "Company": "company",
    "Email": "email",
    "Website": "website",
    "LinkedIn URL": "linkedin",
    "City": "city",
    # fallbacks for alternative header formats
    "Person Linkedin Url": "linkedin",
    "Company Website": "website",
}


def process_apollo_csv(input_path: Path) -> None:
    print(f"Reading Apollo export: {input_path}")
    rows: list[dict] = []

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        col_map = {h: _APOLLO_COLUMN_MAP[h] for h in headers if h in _APOLLO_COLUMN_MAP}

        if not col_map:
            print(f"ERROR: Could not map any columns. Found: {headers}")
            print("Expected headers like: First Name, Last Name, Email, Company, Website, LinkedIn URL")
            sys.exit(1)

        for raw in reader:
            row: dict = {v: "" for v in OUTPUT_FIELDS}
            for src_col, dest_col in col_map.items():
                row[dest_col] = (raw.get(src_col) or "").strip()
            # ensure website has a scheme
            if row["website"] and not row["website"].startswith("http"):
                row["website"] = "https://" + row["website"]
            rows.append(row)

    print(f"Processed {len(rows)} leads")
    _summary(rows)
    out_path = _save_csv(rows, label="from_apollo_ui")
    print(f"\nSaved: {out_path}")
    print("Import to Google Sheets: File > Import > Upload > Replace spreadsheet")


# ---------------------------------------------------------------------------
# Mode 2: call Apollo API directly (paid plan)
# ---------------------------------------------------------------------------

def search_apollo_api() -> list[dict]:
    if not APOLLO_API_KEY:
        print("ERROR: APOLLO_API_KEY not set in .env")
        sys.exit(1)

    payload: dict = {
        "person_titles": TITLES,
        "person_seniorities": SENIORITIES,
        "contact_email_status_v2": ["verified", "likely to engage"],
        "per_page": min(LIMIT, 100),
        "page": 1,
    }
    if LOCATIONS:
        payload["organization_locations"] = LOCATIONS
    if INDUSTRIES:
        payload["organization_industry_tag_ids"] = INDUSTRIES
    if EMPLOYEE_RANGE:
        payload["organization_num_employees_ranges"] = [EMPLOYEE_RANGE]

    print(f"Searching Apollo API... (limit={LIMIT}, locations={LOCATIONS or 'any'})")

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://api.apollo.io/api/v1/mixed_people/search",
            json=payload,
            headers={"Content-Type": "application/json", "X-Api-Key": APOLLO_API_KEY},
        )

    if resp.status_code == 403:
        print("ERROR: Apollo API returned 403 — People Search requires a paid plan.")
        print("Upgrade at https://app.apollo.io/ or use Mode 1 (UI export CSV).")
        print("\nTo use Mode 1: export a CSV from the Apollo UI and run:")
        print("  python scripts/apollo_export.py path/to/your_apollo_export.csv")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: Apollo returned {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)

    people = resp.json().get("people", [])
    print(f"Apollo returned {len(people)} people")
    return people


def _parse_api_person(p: dict) -> dict:
    org = p.get("organization") or {}
    domain = org.get("primary_domain") or p.get("organization_domain", "")
    website = f"https://{domain}" if domain and not domain.startswith("http") else domain
    return {
        "first_name": p.get("first_name", ""),
        "last_name": p.get("last_name", ""),
        "title": p.get("title", ""),
        "company": org.get("name") or p.get("organization_name", ""),
        "email": p.get("email", ""),
        "website": website,
        "linkedin": p.get("linkedin_url", ""),
        "city": p.get("city", ""),
    }


def run_api_mode() -> None:
    people = search_apollo_api()
    if not people:
        print("No results returned.")
        return
    rows = [_parse_api_person(p) for p in people]
    _summary(rows)
    out_path = _save_csv(rows, label="from_api")
    print(f"\nSaved: {out_path}")
    print("Import to Google Sheets: File > Import > Upload > Replace spreadsheet")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) > 1:
        # Mode 1: CSV path passed as argument
        input_path = Path(sys.argv[1])
        if not input_path.exists():
            print(f"ERROR: File not found: {input_path}")
            sys.exit(1)
        process_apollo_csv(input_path)
    else:
        # Mode 2: API search
        run_api_mode()


if __name__ == "__main__":
    main()
