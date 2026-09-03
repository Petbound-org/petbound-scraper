import time

import scraper

print("\n*** Starting scrape for all dog ids.\n")

start = time.time()
dog_ids = scraper.scrape_dog_ids()
end = time.time()

print("\n*** Dog id scraping complete.")
print("Summary:")
print(f"Found {len(dog_ids)} dog listings.")
print(f"Completed in {}:{}.")


print(len(dog_ids))