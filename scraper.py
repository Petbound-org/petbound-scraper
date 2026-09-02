# scraper.py

# imports
import os
import requests
import sys
import time
import re # regular expressions
from bs4 import BeautifulSoup
from supabase import create_client, Client
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# CSV file locations
PET_CSV = "pet_data.csv"
SHELTER_CSV = "shelter_data.csv"

# Fields
PET_FIELDS = [
    'name', 'breed', 'age', 'gender', 'size', 
    'description', 'euthanasia_date', 'image_urls', 
    'shelter_given_id', 'euthanasia_reason'
]
SHELTER_FIELDS = [
    'name', 'address', 'city', 'state', 
    'phone_number', 'email'
]

"""
-----  Scrape Methods  -----
"""

def scrape_dog_ids():
    """
    Getting all dog_ids on the dogsindanger.com website.

    Each dog's page can be accessed by:
    dogsindanger.com/dog/<dog_id>
    """
    BASE = "https://www.dogsindanger.com/searchReturn_desktop.jsp?BREED=&t=90&startId={start_index}&zip=&radius=100.0&state={state}&Transport=0"
    states = ['AZ', 'CA', 'FL', 'GA', 'NC', 'OH', 'OK', 'TX']
    dog_ids = set()

    for state in states:
        start_index = 0
        prev_size = len(dog_ids)
        
        # Loop until page says "There are no dogs matching your search criteria."
        while True:
            # Fetching a response
            url = BASE.format(start_index=start_index, state=state)
            response = requests.get(url)

            # time.sleep(0.5) # *** UNCOMMENT AS A POSSIBLE FIX FOR UNEXPECTED ERRORS ***
            
            # Connection check (CRITICAL ERROR IF IT FAILS)
            try: 
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP ERROR: {e}")
                return None
            except requests.exceptions.RequestException as e:
                print(f"NON-HTTP ERROR (like a network issue): {e}")
                return None

            # No more dogs left for this state (end condition)
            if "There are no dogs matching your search criteria." in response.text:
                break # the break here is used responsibly (I hope)
            
            # Parse the page for ids
            soup = BeautifulSoup(response.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                id = re.search(r'/dog/(\d+)-', a['href'])
                if id:
                    dog_ids.add(int(id.group(1)))

            # Increment (by 20 b/c it shows 20 dogs a page)
            start_index += 20
    
        print(f"Completed scraping {state}, found {len(dog_ids) - prev_size} listings.")

    return sorted(list(dog_ids))

def scrape_dog(id):
    """
    Scrapes the data of a dog given its ID.
    Each dog's page: https://www.dogsindanger.com/dog/<ID>
    """
    url = f"https://www.dogsindanger.com/dog/{id}"

    # USE SESSION + headers + timeout (so retries apply)
    try:
        response = SESSION.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[HTTP ERROR] dog_id={id} url={url} -> {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[NETWORK ERROR] dog_id={id} url={url} -> {e}")
        return None

    soup = BeautifulSoup(response.text, 'lxml')
    container = soup.find('div', attrs={'id': 'doggie'})

    # If the page structure is not what we expect, skip
    if not container:
        print(f"[PARSE ERROR] dog_id={id} url={url} -> missing #doggie container")
        return None

    dog = {}
    shelter = {}

    # Dog name
    name_div = find_by_style(container, r'font-size:\s*24pt')
    dog['name'] = name_div.get_text(strip=True).title() if name_div else ""

    # Dog image
    img = container.find('img', attrs={'id': 'mainImageX'})
    dog['image_urls'] = [img.get('src')] if (img and img.get('src')) else []

    # Dog description. The block is <br>-separated lines, so take every direct
    # text node rather than only the first: shelters that list one field per
    # line (microchip, sex, colour, intake date) were being reduced to their
    # opening line, e.g. 34 characters kept out of 381. Stays non-recursive so
    # nested markup does not leak in.
    description_div = find_description_div(container)
    if description_div:
        parts = [
            t.strip()
            for t in description_div.find_all(string=True, recursive=False)
            if t.strip()
        ]
        dog['description'] = "\n".join(parts).lstrip(': ').strip()
    else:
        dog['description'] = ""

    # Euthanasia date + reason (defensive, label-based)
    # The div reads: "At Risk To Be Killed: [TODAY! ]<date> Reason: <reason>"
    dog['euthanasia_date'] = ""
    dog['euthanasia_reason'] = ""
    # Still matching today, but hardened for the same reason as the others: the
    # whole pipeline is worthless without a date.
    euthanasia_div = find_by_style(container, r'font-size:\s*10pt')
    if euthanasia_div:
        full = euthanasia_div.get_text(" ", strip=True)

        # reason: everything after "Reason:"; strip it off before parsing date
        reason_m = re.search(r'Reason:\s*(.*)$', full)
        if reason_m:
            dog['euthanasia_reason'] = reason_m.group(1).strip()
            full = full[:reason_m.start()]

        # date: what's left after removing the label and optional "TODAY!"
        full = re.sub(r'^\s*At Risk To Be Killed:\s*', '', full)
        full = re.sub(r'^\s*TODAY!\s*', '', full)
        dog['euthanasia_date'] = full.strip()

    # Raw text parsing
    text = container.get_text(strip=True, separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    n = len(lines)

    email_re = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
    phone_re = re.compile(r"(\+?1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")

    while i < n:
        if lines[i] == 'Breed:' and i+1 < n:
            dog['breed'] = lines[i+1]; i += 2; continue

        # Age / gender / size no longer have their own labels — they live in the
        # "Profile:" block, parsed separately below via parse_profile().

        if lines[i] == 'Shelter Information:' and i+3 < n:
            shelter['name'] = lines[i+1]
            shelter['address'] = lines[i+2]

            city_state = lines[i+3]
            # defensive parse
            if len(city_state) >= 2:
                shelter['state'] = city_state[-2:]
                shelter['city'] = city_state[:-4] if len(city_state) > 4 else ""
            else:
                shelter['city'] = ""
                shelter['state'] = ""

            i += 4
            continue

        # Site renamed this label from 'Shelter dog ID:' to 'Dog ID:'.
        if lines[i] in ('Dog ID:', 'Shelter dog ID:') and i+1 < n:
            dog['shelter_given_id'] = lines[i+1]
            i += 2
            continue

        # NEW: no fixed offsets — scan forward for phone/email
        if lines[i] == 'Contact:':
            found_phone = ""
            found_email = ""
            j = i

            while j < n and (not found_phone or not found_email):
                if not found_email:
                    m = email_re.search(lines[j])
                    if m:
                        found_email = m.group(0)

                if not found_phone:
                    m = phone_re.search(lines[j])
                    if m:
                        found_phone = m.group(0)

                j += 1

            shelter['phone_number'] = found_phone
            shelter['email'] = found_email
            i = j
            continue

        i += 1

    # Age / size / gender come from the free-text "Profile:" block.
    p_size, p_age, p_gender = parse_profile(container)
    if p_size:
        dog['size'] = p_size
    if p_age:
        dog['age'] = p_age
    if p_gender:
        dog['gender'] = p_gender

    # Ensure keys exist (prevents KeyError later)
    for k in ['breed', 'age', 'gender', 'size', 'shelter_given_id']:
        dog.setdefault(k, "")
    for k in ['name', 'address', 'city', 'state', 'phone_number', 'email']:
        shelter.setdefault(k, "")

    return dog, shelter

"""
-----  Tests  -----
"""

def test_scrape_dog_ids():
    start = time.time()
    ids = scrape_dog_ids()
    end = time.time()

    print(f"\nScraped {len(ids)} dogs")
    print(f"All ids are unique: {len(set(ids)) == len(ids)}")
    print(f"Total duration: {(end - start):.2f}s")
    print(f"Page scraping duration (avg, upper estim): {20 * ((end - start) / len(ids)):.3f}\n") # keep >0.5s, use time.sleep() if necessary

def test_db_read(supabase: Client):
    test_pet = (
        supabase.table('pets')
        .select('*')
        .eq('id', 1)
        .execute()
        .data
    )

    test_shelter = (
        supabase.table('shelters')
        .select('*')
        .eq('id', 1)
        .execute()
        .data
    )

    print(test_shelter)

def test_scrape_dog():
    # 1758257073360 - Nacie 
    # 1761092968039 - Peabody
    dog, shelter = scrape_dog(1758257073360) 

    print(f"\nDog: {dog}\n")
    print(f"Shelter: {shelter}\n")

"""
-----  Database or CSV Data Storage  -----
"""

def update_db(supabase: Client, dog, shelter):
    # Check if shelter exists in data
    response = (
        supabase.table('shelters')
        .select('id')
        .filter('name', 'eq', shelter['name'])
        .filter('address', 'eq', shelter['address'])
        .execute()
        .data
    )

    # Setting shelter ID or adding shelter then setting ID
    if response: 
        dog['shelter_id'] = response[0]['id']
    else:
        response = supabase.table('shelters').insert(shelter).execute().data
        dog['shelter_id'] = response[0]['id']

    # Check if dog exists in DB (matching shelter + shelter given ID)
    response = (
        supabase.table('pets')
        .select('id')
        .filter('shelter_given_id', 'eq', dog['shelter_given_id'])
        .filter('shelter_id', 'eq', dog['shelter_id'])
        .execute()
        .data
    )

    # Updating dog data if exists, else creating a new dog
    if response:
        supabase.table('pets').update(dog).filter('id', 'eq', response[0]['id']).execute()
    else:
        supabase.table('pets').insert(dog).execute()

def update_csv():
    pass

"""
-----  Post-scrape health check  -----

The scrape itself stays quiet: a dog that fails to parse is skipped and the run
carries on, so a partial outage still refreshes most of the site rather than
leaving it stale. The cost of that is silence, and silence is how the August
2026 breakage went unnoticed for five weeks. dogsindanger.com had appended
properties to an inline style attribute, the exact-match selectors stopped
matching, and name / age / gender / size / description were written as empty
strings on every new record while the run kept reporting success.

So completeness is measured across the whole run and checked once at the end,
after every record is already saved. If a field is blank far more often than it
should be, the process exits non-zero. Nothing is rolled back; the only effect is
a failed GitHub Actions run, which sends the notification email.

Limits are the share of scraped dogs allowed to have a blank value. They sit well
above normal noise so ordinary gaps stay quiet, and well below a real breakage
(a broken selector yields ~100%).
"""

FIELD_BLANK_LIMITS = {
    "name": 0.20,
    "breed": 0.05,
    "age": 0.20,
    "gender": 0.20,
    "size": 0.20,
    # Some shelters genuinely write nothing, so this one runs looser.
    "description": 0.35,
    "euthanasia_date": 0.05,
    "euthanasia_reason": 0.10,
    "shelter_given_id": 0.05,
    "image_urls": 0.10,
}

# Percentages are meaningless on a handful of records, so small runs never fail.
HEALTH_MIN_SAMPLE = 25

# Dogs that could not be scraped at all. A high rate means the page or the ID
# search changed shape, which the per-field limits would not necessarily catch.
SKIP_RATE_LIMIT = 0.25


def is_blank(value):
    """True when a scraped field holds nothing useful.

    Blank fields arrive as empty strings rather than None, because the parsers
    fall back to "" when a selector misses.
    """
    if isinstance(value, list):
        return not value
    return not str(value or "").strip()


def check_field_health(stats):
    """Report completeness and return a list of problems, empty when healthy."""
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
-----  Main Scraper  -----
"""

def scrape_to_db():
    # Database Connection (made for github actions)
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url:
        raise EnvironmentError("SUPABASE_URL environment variable not set. Please check your GitHub Actions secrets.")
    if not supabase_key:
        raise EnvironmentError("SUPABASE_KEY environment variable not set. Please check your GitHub Actions secrets.")

    supabase: Client = create_client(supabase_url, supabase_key)

    print("Scraping all dog ids...")
    dog_ids = scrape_dog_ids()

    if not dog_ids:
        raise RuntimeError("scrape_dog_ids() failed or returned no ids.")

    print("Dog ID scraping complete ✅")
    print("Scraping each dog's data and updating db...")

    counter = 0
    skipped = 0
    blank = {field: 0 for field in FIELD_BLANK_LIMITS}

    for id in dog_ids:
        print(f"Dog id: {id}")

        try:
            result = scrape_dog(id)
            if result is None:
                skipped += 1
                print(f"[SKIP] scrape_dog failed for id={id}")
                continue

            dog, shelter = result

            if not dog.get("shelter_given_id"):
                skipped += 1
                print(f"[SKIP] missing shelter_given_id for id={id}")
                continue

            update_db(supabase, dog, shelter)
            counter += 1

            # Tally completeness after the write, so the check never gates
            # saving. A degraded run still refreshes the site.
            for field in blank:
                if is_blank(dog.get(field)):
                    blank[field] += 1

            if counter % 20 == 0:
                print(f"Scraped {counter} pets so far. (skipped={skipped})")

        except Exception as e:
            skipped += 1
            print(f"[SKIP] id={id} crashed: {type(e).__name__}: {e}")
            continue

    print(f"\nScraped {counter} pets total. Skipped {skipped}.\n")

    return {"scraped": counter, "skipped": skipped, "blank": blank}


"""
-----  Execution / Test  -----
"""

if __name__ == '__main__':
    start = time.time()
    stats = scrape_to_db()
    end = time.time()
    print("\nScraping Complete!")
    print(f"Duration: {(end - start) / 60:.0f} minutes.\n")

    # Everything scraped is already in the database. Exiting non-zero here only
    # fails the Actions run so the notification email goes out.
    problems = check_field_health(stats)
    if problems:
        print(f"\nFailing the run: {len(problems)} field(s) look broken.")
        sys.exit(1)










# SIZE_MAP = {
#     "small": "Small",
#     "medium": "Medium",
#     "large": "Large",
#     "x-large": "X-Large",
#     "xlarge": "X-Large",
#     "extra large": "X-Large",
# }

# AGE_MAP = {
#     "under 6 months": "Under 6 months",
#     "young adult": "Young adult",
#     "adult": "Adult",
#     "senior": "Senior",
# }

# GENDER_MAP = {
#     "male": "Male",
#     "female": "Female",
# }