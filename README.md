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