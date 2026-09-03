# main.py

import sys
import time

from data_health import check_field_health, is_blank, FIELD_BLANK_LIMITS
from database import get_client, update_db
from scraper import scrape_dog_ids, scrape_dog

"""
-----  Main Scraper Routine  -----
"""

def scrape_to_db():
    supabase = get_client()

    print("Scraping all dog ids...")
    dog_ids = scrape_dog_ids()

    if not dog_ids:
        raise RuntimeError("scrape_dog_ids() failed or returned no ids.")

    print("Dog ID scraping complete")
    print("Scraping each dog's data and updating db...")

    counter = 0
    skipped = 0
    blank = {field: 0 for field in FIELD_BLANK_LIMITS}

    for id in dog_ids:
        try:
            result = scrape_dog(id)
            if result is None:
                skipped += 1
                print(f"[SKIP] scrape_dog failed for id={id}")
                continue

            dog, shelter = result

            if not dog.shelter_given_id:
                skipped += 1
                print(f"[SKIP] missing shelter_given_id for id={id}")
                continue

            update_db(supabase, dog, shelter)
            counter += 1

            for field in blank:
                if is_blank(getattr(dog, field, None)):
                    blank[field] += 1

            if counter % 50 == 0:
                print(f"Scraped {counter} pets so far. (skipped={skipped})")

        except Exception as e:
            skipped += 1
            print(f"[SKIP] id={id} crashed: {type(e).__name__}: {e}")
            continue

    print(f"\nScraped {counter} pets total. Skipped {skipped}.\n")

    return {"scraped": counter, "skipped": skipped, "blank": blank}

"""
-----  Execution  -----
"""

if __name__ == "__main__":
    start = time.time()
    stats = scrape_to_db()
    end = time.time()

    print("\nScraping Complete")
    print(f"Duration: {(end - start) / 60:.0f} minutes.\n")

    # Fail here so that GitHub actions fails and sends me an email about issues
    problems = check_field_health(stats)
    if problems:
        sys.exit(1)
