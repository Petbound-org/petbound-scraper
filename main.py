import time

import scraper

print("\n*** Starting scrape for all dog ids.\n")

dog_ids = scraper.scrape_dog_ids()

print("\n*** Dog id scraping complete.")
print("Summary:")
print(f"Found {} dog listings.")
print(f"Completed in {}:{}.")


print(len(dog_ids))