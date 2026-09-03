# data_health.py

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

"""
-----  Health Check  -----
"""

def check_field_health(stats):
    """Which fields came back blank more often than they should have.

    Returns a list of descriptions, one per field over its limit. An empty list
    means the scrape looks full enough.
    """
    scraped = stats["scraped"]
    blank = stats["blank"]

    # A blank rate out of a handful of dogs says nothing
    if scraped < HEALTH_MIN_SAMPLE:
        return []

    problems = []

    for field, limit in FIELD_BLANK_LIMITS.items():
        rate = blank.get(field, 0) / scraped
        if rate > limit:
            problems.append(f"{field}: {rate:.0%} blank ({blank[field]}/{scraped}), limit {limit:.0%}")

    return problems

"""
-----  Helper  -----
"""

def is_blank(value):
    if isinstance(value, list):
        return not value
    return not str(value or "").strip()
