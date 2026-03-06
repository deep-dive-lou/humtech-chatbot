"""Exploratory Apollo org search -- test different filter combos to find the bottleneck."""

import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("APOLLO_API_KEY")
URL = "https://api.apollo.io/api/v1/mixed_companies/search"
HEADERS = {"Content-Type": "application/json", "X-Api-Key": API_KEY}

CURRENT_KEYWORDS = [
    "debt management", "debt consolidation", "debt advice", "debt solutions",
    "IVA", "debt recovery", "insolvency", "credit repair", "debt counselling",
    "DMP", "debt relief", "individual voluntary arrangement", "trust deed",
    "bankruptcy advice",
]

TESTS = {
    "A: keywords, no employee filter": {
        "q_organization_keyword_tags": CURRENT_KEYWORDS,
        "organization_locations": ["United Kingdom"],
    },
    "B: keywords + 11-500 employees (CURRENT)": {
        "q_organization_keyword_tags": CURRENT_KEYWORDS,
        "organization_locations": ["United Kingdom"],
        "organization_num_employees_ranges": ["11,500"],
    },
    "C: keywords + 1-10 employees (micro)": {
        "q_organization_keyword_tags": CURRENT_KEYWORDS,
        "organization_locations": ["United Kingdom"],
        "organization_num_employees_ranges": ["1,10"],
    },
    "D: keywords + 1-10000 (full range)": {
        "q_organization_keyword_tags": CURRENT_KEYWORDS,
        "organization_locations": ["United Kingdom"],
        "organization_num_employees_ranges": ["1,10000"],
    },
    "E: financial services industry only (no keywords)": {
        "organization_locations": ["United Kingdom"],
        "organization_industry_tag_ids": ["financial services"],
    },
    "F: keywords + financial services industry": {
        "q_organization_keyword_tags": CURRENT_KEYWORDS,
        "organization_locations": ["United Kingdom"],
        "organization_industry_tag_ids": ["financial services"],
    },
}


async def quick_count(name: str, filters: dict) -> tuple[int, int]:
    """Hit page 1 with per_page=1 just to read total_entries from pagination."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {**filters, "per_page": 1, "page": 1}
        resp = await client.post(URL, json=payload, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        pagination = data.get("pagination", {})
        total = pagination.get("total_entries", 0)
        pages = pagination.get("total_pages", 0)
        return total, pages


async def main():
    print("=" * 70)
    print("Apollo Org Search -- Filter Exploration")
    print("=" * 70)
    print()

    for name, filters in TESTS.items():
        try:
            total, pages = await quick_count(name, filters)
            print(f"  {name}")
            print(f"    -> {total:,} total orgs ({pages:,} pages)")
        except Exception as e:
            print(f"  {name}")
            print(f"    -> ERROR: {e}")
        print()
        await asyncio.sleep(1)

    print("=" * 70)
    print("Done.")


asyncio.run(main())
