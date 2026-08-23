## Petbound Webscraper

This scraper collects dog records from dogsindanger.com and writes parsed dog/shelter data to Supabase.

## Bug: no dog IDs returned

### What was wrong

The ID scraper was tied to an exact inline `style` string for each dog card.  
The site changed that markup (`position:relative;margin-bottom:9px;` became `position:static;margin-bottom:15px;`), so this selector stopped matching any cards. As a result, `scrape_dog_ids()` returned an empty list.

### Runtime evidence

- Pages still loaded successfully (`status=200`) and were not empty.
- The old style selector found `0` cards.
- Dog links were still present on the same pages (for example 20 unique `/dog/<id>-...` links on page 1 in multiple states).

### Fix

Instead of depending on one brittle style string, IDs are now extracted from all anchors whose `href` matches:

```regex
/dog/(\d+)-
```

Collected IDs are deduplicated per page before appending.

## Bug: fields silently emptied by a site redesign (August 2026)

### What was wrong

Same root cause as the ID bug above, in three more places. `name` and
`description` were selected by comparing the whole inline `style` attribute for
equality. The site appended properties to those attributes
(`display:inline-block;flex-flow: column;` on the name div), the selectors
stopped matching, and both parsers fell through to `""`.

Separately, the `Age:` / `Gender:` / `Size:` labels were replaced by a single
`Profile:` block reading `X-Large  size young adult`, which nothing parsed.

The description parser also had a long-standing bug of its own: the block is
`<br>`-separated lines, but it kept only the first text node. Fulton County dogs
stored `Teddy` out of 42 characters; Fort Worth stored a microchip number out of
381.

### Impact

Nothing failed. Every run reported success while writing empty strings. By the
time it was noticed, 98.9% of that week's records had no name, and age, gender,
size and description were 100% empty on live pets. The website rendered hundreds
of pages with an empty `<title>`.

### Fix

- Match a stable fragment of the style attribute instead of the whole string
  (`find_by_style`).
- Pick the description block by what it does *not* contain, since two divs now
  share `font-size:1.2em` (`find_description_div`).
- Join every direct text node in the description, not just the first.
- Parse the `Profile:` block for size / age / gender (`parse_profile`).

## Health check

The scrape stays quiet on individual failures: a dog that will not parse is
skipped and the run continues, so a partial outage still refreshes most of the
site instead of leaving it stale. That silence is exactly how the bug above
survived five weeks.

So completeness is measured across the run and checked once at the end, **after
every record is saved**. If a field is blank far more often than `FIELD_BLANK_LIMITS`
allows, or too many dogs fail outright, the process exits non-zero. Nothing is
rolled back. The only effect is a failed GitHub Actions run, which sends the
notification email.

Runs of fewer than `HEALTH_MIN_SAMPLE` (25) dogs never fail the check, because
percentages on a handful of records are noise.

To retune, edit `FIELD_BLANK_LIMITS`. Limits sit well above normal noise so
ordinary gaps stay quiet, and well below a real breakage, which yields ~100%.

## How to run

Install dependencies:

```bash
pip3 install -r requirements.txt
```

Quick ID scrape test:

```bash
python3 -c "from scraper import test_scrape_dog_ids; test_scrape_dog_ids()"
```

Full scrape to DB (requires `SUPABASE_URL` and `SUPABASE_KEY`):

```bash
python3 scraper.py
```