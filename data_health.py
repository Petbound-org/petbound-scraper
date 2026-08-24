# data_health.py
#
# Watches the database, not the scrape.
#
# scraper.py already checks completeness at the end of a run, but that check can
# only run when a run happens. Two failures slip past it:
#
#   1. The scrape does not run at all. April 2026 has zero rows in the database
#      and nothing alerted, because no run means no health check.
#   2. The scrape runs from stale code. Every scheduled run between 10 Jul and
#      23 Aug 2026 executed the 10 Jul commit, reported success, and wrote empty
#      strings for five fields. The fix existed on a branch the whole time.
#
# Both are invisible from inside a run and obvious from outside it. This script
# looks at what actually landed and exits non-zero when it looks wrong, which
# fails the Actions run and sends the notification email.
#
# It shares FIELD_BLANK_LIMITS and is_blank() with scraper.py rather than
# restating the numbers, so tuning one tunes both.

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import Client, create_client

from scraper import FIELD_BLANK_LIMITS, is_blank

# Fields worth checking on stored rows. `image_urls` and `shelter_given_id` are
# in FIELD_BLANK_LIMITS but are write-time concerns, not storage ones.
WATCHED_FIELDS = [
    "name",
    "breed",
    "age",
    "gender",
    "size",
    "description",
    "euthanasia_date",
    "euthanasia_reason",
]

# The scrape is daily, so a healthy database gains rows well inside this window.
# 36 hours rather than 24 leaves headroom for a late start or a slow run without
# letting a genuinely missed day pass unnoticed.
FRESHNESS_WINDOW_HOURS = 36

# Below this, the source itself is likely down or the ID scrape is broken. Real
# days add 60 to 170 new listings.
MIN_NEW_ROWS = 20

# Rows already gone from the source keep their blank fields permanently, so the
# live set never reaches 100% complete. Measured at ~8% after a clean repair.
MIN_LIVE_ROWS_TO_JUDGE = 100


def fetch_all(supabase: Client, table: str, columns: str, **filters):
    """Page through a table, because PostgREST caps a response at 1000 rows."""
    rows = []
    page = 1000
    start = 0
    while True:
        query = supabase.table(table).select(columns)
        for op, args in filters.items():
            query = getattr(query, op)(*args)
        data = query.order("id").range(start, start + page - 1).execute().data
        rows.extend(data or [])
        if not data or len(data) < page:
            return rows
        start += page


def check_freshness(supabase: Client):
    """Did the scrape run recently, and did it write anything?"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_WINDOW_HOURS)
    cutoff_iso = cutoff.isoformat()

    rows = (
        supabase.table("pets")
        .select("id", count="exact")
        .gte("created_at", cutoff_iso)
        .limit(1)
        .execute()
    )
    count = rows.count or 0

    print(f"\n----- Freshness -----")
    print(f"  new rows in the last {FRESHNESS_WINDOW_HOURS}h: {count} (minimum {MIN_NEW_ROWS})")

    if count < MIN_NEW_ROWS:
        return [
            f"only {count} rows created in the last {FRESHNESS_WINDOW_HOURS}h, "
            f"expected at least {MIN_NEW_ROWS}. The scrape may not be running, "
            f"or the ID scrape is returning nothing."
        ]
    return []


def check_live_completeness(supabase: Client):
    """Are the pets we are currently showing actually populated?"""
    today = datetime.now(timezone.utc).date().isoformat()
    rows = fetch_all(
        supabase,
        "pets",
        ",".join(["id"] + WATCHED_FIELDS),
        gte=("euthanasia_date", today),
    )

    print(f"\n----- Live-record completeness -----")
    if len(rows) < MIN_LIVE_ROWS_TO_JUDGE:
        print(
            f"  only {len(rows)} live rows, below the {MIN_LIVE_ROWS_TO_JUDGE} "
            "needed to judge. Skipping."
        )
        return []

    problems = []
    for field in WATCHED_FIELDS:
        limit = FIELD_BLANK_LIMITS.get(field)
        if limit is None:
            continue
        blank = sum(1 for row in rows if is_blank(row.get(field)))
        rate = blank / len(rows)
        status = "ok"
        if rate > limit:
            status = "FAIL"
            problems.append(
                f"{field}: {rate:.0%} of live records blank ({blank}/{len(rows)}), "
                f"limit {limit:.0%}"
            )
        print(
            f"  {field:<18} {blank:>5}/{len(rows)} blank  {rate:>6.1%}  "
            f"(limit {limit:.0%})  {status}"
        )

    return problems


def main():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_KEY must be set. Check the Actions secrets."
        )

    supabase: Client = create_client(url, key)

    problems = check_freshness(supabase) + check_live_completeness(supabase)

    report = ["", "----- Result -----"]
    if problems:
        report.append("The database does not look right. Usual causes:")
        report.append("  - the scheduled workflow stopped running")
        report.append("  - a fix is sitting on a branch and main is still stale")
        report.append("  - a selector stopped matching after a source redesign")
        report.append("")
        for problem in problems:
            report.append(f"  - {problem}")
    else:
        report.append("Database looks healthy.")

    text = "\n".join(report)
    print(text)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(f"```\n{text}\n```\n")
        except OSError as e:
            print(f"[WARN] could not write step summary: {e}")

    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
