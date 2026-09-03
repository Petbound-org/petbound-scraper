# petbound-scraper

The scraper behind petbound.org

Pulls dogs listed as at-risk on dogsindanger.com and keeps them in sync with
the Supabase database the site reads from. Runs daily from GitHub Actions.

## How it works

It collects every dog ID from the state search pages, scrapes each dog's page
for its details and its shelter, and upserts both. At the end it checks how
many fields came back empty and fails the run if too many did, since it's designed
to leave fields empty if some specific parsing goes wrong (rather than just failing completely).

## Layout

| | |
|---|---|
| `main.py` | run the whole pipeline |
| `scraper.py` | fetching and parsing from dogsindanger.com |
| `database.py` | Supabase connection and writing to db |
| `schemas.py` | the Dog and Shelter data models |
| `data_health.py` | checks for missing fields in db |

## Running it

Needs `SUPABASE_URL` and `SUPABASE_KEY`, from a local `.env` or Actions secrets.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
