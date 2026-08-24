# BACKLOG: petbound-scraper

Work that is worth doing but deliberately not being done yet. Each item says why
it matters, so a future reader can judge whether it still does.

## Record when a euthanasia date changes

**Status:** not started. Deferred on purpose.

**What.** Add a column that captures the euthanasia date a listing carried the
*first* time we saw it, written only on insert and never updated. A history
table (one row per observed change) would be richer, but a single
`first_euthanasia_date` column is enough for the question below and costs
almost nothing.

**Why it matters.** `update_db` upserts on `(shelter_given_id, shelter_id)`, so
`euthanasia_date` always holds the most recent date the source published. The
earlier value is overwritten and gone. `updated_at` cannot help: the scraper
never writes it and there is no trigger, so it is byte-identical to
`created_at` on every row.

The practical consequence is that one of the most interesting things in this
dataset is currently unprovable. Roughly 29% of currently-listed pets carry a
date more than 14 days after we first recorded them. That is consistent with
shelters pushing deadlines back, which would be a genuinely useful and widely
misunderstood finding. It is equally consistent with those listings having
simply appeared with a distant date. Nothing in the data distinguishes the two.

`petbound-web` needs this. `lib/seo/research-summary.ts` currently states the
gap as "a listed date is not always final" rather than as evidence of
extension, precisely because the stronger claim is not supported. With a
first-seen date recorded, it becomes a direct measurement.

**Note on timing.** This only accrues going forward. Every day it is not done is
a day of extension history that cannot be recovered, which is the argument for
doing it sooner rather than when the analysis is wanted.

**Rough shape.**
1. Add the column in Supabase, nullable, no default.
2. In `update_db`, set it only on the insert branch, never on the update branch.
3. Backfill existing rows to their current `euthanasia_date`. This is wrong for
   any listing already extended, so mark the backfill date and treat rows older
   than it as unusable for this question.
4. Add it to `PET_HEADER` and to `FIELD_BLANK_LIMITS`, or it can break silently.

## Add a health check to the data-health workflow for stale code

**Status:** idea only.

`data-health` catches blank fields and missing rows, but not "the workflow is
running old code". A cheap version: have `daily-scrape` write the commit SHA it
ran into a small table or a step summary, and have `data-health` compare it
against the tip of `main`. This is what would have caught both the six-week
stale-branch outage and the re-run that replayed it.

## Investigate the April 2026 collection gap

**Status:** unexplained.

The `pets` table has zero rows with a `created_at` in April 2026. Collection
stopped for a month and nothing alerted, because the health check only runs
inside a scrape and a scrape that never happens produces no check. The
`data-health` workflow closes the alerting hole going forward, but the cause of
the original outage was never established. Actions history for that period would
say whether the workflow was disabled, failing, or simply not firing.
