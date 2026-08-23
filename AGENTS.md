# AGENTS.md: petbound-scraper

Context for agents working in this repo. Read the "recurring failure mode"
section before touching any selector.

## What this is

A single-file Python scraper (`scraper.py`) that collects at-risk dog listings
from dogsindanger.com and upserts them into Supabase. It runs daily via GitHub
Actions (`.github/workflows/daily-scrape.yaml`, cron `0 8 * * *`) **from `main`**.

Code that is not merged to `main` never runs. A fix sitting on a local branch has
no effect, which is exactly how one bug below survived for weeks.

## Sibling repo

`../petbound-web` (github.com/Petbound-org/petbound-web) reads what this writes.
Empty fields here become empty pages there. That repo has its own AGENTS.md.

## The recurring failure mode: exact style matching

**This has broken three separate times.** dogsindanger.com styles elements with
inline `style` attributes and edits them without warning. Any selector written as

```python
container.find('div', attrs={'style': 'font-size:24pt;...'})
```

does an **exact string comparison**. When the site appends one property, the
selector matches nothing, the parser falls through to `""`, and the run still
reports success. The failure is completely silent.

History:
1. Dog ID cards: card `style` changed, `scrape_dog_ids()` returned an empty list.
2. August 2026: the name div gained `display:inline-block;flex-flow: column;`.
   `name` went blank. Same period, `Age:` / `Gender:` / `Size:` labels were
   replaced by one `Profile:` block, and the description div changed too. Result:
   98.9% of that week's records had no name; age, gender, size and description
   were 100% empty on live pets.
3. The description parser separately kept only the *first* of N `<br>`-separated
   text nodes, storing `Teddy` out of 42 characters and a microchip number out of
   381.

**Rule: never compare a whole `style` attribute.** Use `find_by_style()`, which
matches a stable fragment by regex. Where two elements share a fragment,
disambiguate by content, as `find_description_div()` does (it picks the block that
does *not* contain the `Breed:` / `Profile:` labels).

Prefer label-based or semantic anchors over styling wherever the page offers one.
`parse_profile()` targets `<strong>Profile:</strong>` directly for this reason.

## Health check

The scrape is deliberately quiet per dog: one that will not parse is skipped and
the run continues, so a partial outage still refreshes most of the site rather
than leaving it stale. That silence is what hid the bug above.

So completeness is tallied across the run and checked once at the end, **after
every record is already saved**. If a field is blank more often than
`FIELD_BLANK_LIMITS` allows, or too many dogs fail outright (`SKIP_RATE_LIMIT`),
the process exits non-zero. Nothing is rolled back. The only effect is a failed
Actions run, which sends the notification email.

- Runs under `HEALTH_MIN_SAMPLE` (25) dogs never fail, because percentages on a
  handful of records are noise.
- Limits sit well above ordinary gaps and well below a real breakage, which
  yields ~100%. `description` is looser (35%) because some shelters write nothing.
- The report also writes to `$GITHUB_STEP_SUMMARY` so it renders on the run page.

**If you add a field to `PET_HEADER`, add it to `FIELD_BLANK_LIMITS` too**, or it
will be able to break silently.

Do not "fix" a failing run by loosening a limit without first checking the source
page. A limit breach almost always means a selector stopped matching.

## Database behaviour worth knowing

- **Upsert key is `(shelter_given_id, shelter_id)`** (`update_db`). Re-scraping a
  dog updates its row in place, including `euthanasia_date`. This is why dates
  appear to be "extended" and why a re-run repairs previously-blank records for
  dogs still listed at the source.
- **Nothing is ever deleted.** The table is append-only history, ~16.5k rows
  against ~875 live on a given day.
- **`updated_at` is never written** by the scraper and has no trigger, so it
  always equals `created_at`. It is useless as a "last seen" signal. Do not build
  logic on it.
- Shelters are matched on `(name, address)` and inserted when absent.
- A backfill is just a normal run: it repairs currently-listed dogs in place.
  Dogs already gone from the source keep their blank fields permanently.

## Source site quirks

- Listing pages: `searchReturn_desktop.jsp?...&state=XX&startId=N`, paged by 20,
  over 8 states (AZ, CA, FL, GA, NC, OH, OK, TX). End condition is the literal
  string "There are no dogs matching your search criteria."
- Detail pages: `/dog/<id>`, content inside `div#doggie`.
- Dog IDs are extracted from `/dog/(\d+)-` hrefs, not from card markup.
- The euthanasia block reads `At Risk To Be Killed: [TODAY! ]<date> Reason: <r>`.
- The `Dog ID:` label was previously `Shelter dog ID:`; both are still accepted.
- `Profile:` reads like `X-Large  size young adult` on one line with gender on the
  next. `SIZE_MAP` / `AGE_MAP` / `GENDER_MAP` normalize these into the buckets the
  web app filters on, falling back to title case so unknown terms are not lost.

## Testing a change safely

Scrape real dogs **without** calling `update_db`, so nothing is written:

```python
import scraper as S
dog, shelter = S.scrape_dog(<id>)   # network only, no DB write
```

Sample across several states before trusting a selector fix. Shelters format
their listings very differently (Fulton County writes four short lines, Fort Worth
writes fifteen labelled fields), and a parser can look correct on one and fail on
another. `scrape_to_db()` is the only function that writes.
