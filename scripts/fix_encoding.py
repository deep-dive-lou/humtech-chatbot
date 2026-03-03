"""One-off: replace Unicode punctuation in existing personalisations with ASCII equivalents."""
import asyncio
import os
import asyncpg

REPLACEMENTS = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote
    "\u201c": '"',   # left double quote
    "\u201d": '"',   # right double quote
    "\u2026": "...", # ellipsis
}


def sanitize(text: str) -> str:
    for char, replacement in REPLACEMENTS.items():
        text = text.replace(char, replacement)
    return text


async def main():
    url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(url)
    rows = await conn.fetch(
        "SELECT personalisation_id, opener_first_line, COALESCE(edited_opener, '') as edited "
        "FROM outreach.personalisation"
    )
    fixed = 0
    for row in rows:
        opener = row["opener_first_line"] or ""
        edited = row["edited"] or ""
        new_opener = sanitize(opener)
        new_edited = sanitize(edited) if edited else edited
        if new_opener != opener or new_edited != edited:
            await conn.execute(
                "UPDATE outreach.personalisation SET opener_first_line = $1, edited_opener = NULLIF($2, '') WHERE personalisation_id = $3",
                new_opener, new_edited, row["personalisation_id"],
            )
            fixed += 1
    print(f"Fixed {fixed}/{len(rows)} personalisations")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())