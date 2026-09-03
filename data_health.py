# data_health.py

import os

"""
-----  Parameters  -----
"""

# Thresholds of permissible null values
FIELD_BLANK_LIMITS = {
    "name": 0.20,
    "breed": 0.05,
    "age": 0.20,
    "gender": 0.20,
    "size": 0.20,
    "description": 0.35, # Some shelters write nothing, so this is not a great test
    "euthanasia_date": 0.05,
    "euthanasia_reason": 0.10,
    "shelter_given_id": 0.05,
    "image_urls": 0.10,
}

# Makes sure that too few datapoints don't create a failure
HEALTH_MIN_SAMPLE = 25

# Permissible amount of dogs that were completely skipped (0.25 is already pretty generous)
SKIP_RATE_LIMIT = 0.25

"""
-----  Health Check  -----
"""

def check_field_health(stats):
    scraped = stats["scraped"]
    skipped = stats["skipped"]
    blank = stats["blank"]
    attempted = scraped + skipped
    problems = []

    lines = ["", "----- Field completeness -----"]

    if scraped < HEALTH_MIN_SAMPLE:
        lines.append(
            f"Only {scraped} dogs scraped, below the {HEALTH_MIN_SAMPLE} needed "
            "to judge completeness. Skipping the check."
        )
        print("\n".join(lines))
        return problems

    for field, limit in FIELD_BLANK_LIMITS.items():
        count = blank.get(field, 0)
        rate = count / scraped
        status = "ok"
        if rate > limit:
            status = "FAIL"
            problems.append(
                f"{field}: {rate:.0%} blank ({count}/{scraped}), limit {limit:.0%}"
            )
        lines.append(
            f"  {field:<18} {count:>5}/{scraped} blank  {rate:>6.1%}  "
            f"(limit {limit:.0%})  {status}"
        )

    if attempted:
        skip_rate = skipped / attempted
        status = "ok"
        if skip_rate > SKIP_RATE_LIMIT:
            status = "FAIL"
            problems.append(
                f"skipped: {skip_rate:.0%} of dogs ({skipped}/{attempted}), "
                f"limit {SKIP_RATE_LIMIT:.0%}"
            )
        lines.append(
            f"  {'(skipped dogs)':<18} {skipped:>5}/{attempted} failed  "
            f"{skip_rate:>6.1%}  (limit {SKIP_RATE_LIMIT:.0%})  {status}"
        )

    if problems:
        lines.append("")
        lines.append("The checks below are outside their limits. The usual")
        lines.append("cause is a changed selector or a renamed label on the")
        lines.append("source page. Everything scraped is already saved, so")
        lines.append("this run failed only to raise the alert.")
        for problem in problems:
            lines.append(f"  - {problem}")

    report = "\n".join(lines)
    print(report)

    # Surface the same table on the Actions run page, not only in the log.
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(f"```\n{report}\n```\n")
        except OSError as e:
            print(f"[WARN] could not write step summary: {e}")

    return problems

"""
-----  Helper  -----
"""

def is_blank(value):
    if isinstance(value, list):
        return not value
    return not str(value or "").strip()