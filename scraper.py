# scraper.py

# imports
import os
import requests
import time
import re # regular expressions
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from supabase import create_client, Client
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# Setting up a requests session with retries
# This makes it so it doesent all fail on occasional errors
SESSION = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
SESSION.mount("https://", HTTPAdapter(max_retries=retries))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (PetBound scraper; GitHub Actions)",
}
# Constants --- these are for CSV
PET_CSV = "pet_data.csv"
SHELTER_CSV = "shelter_data.csv"
PET_HEADER = [
    'name', 'breed', 'age', 'gender', 'size', 
    'description', 'euthanasia_date', 'image_urls', 
    'shelter_given_id', 'euthanasia_reason'
]
SHELTER_HEADER = [
    'name', 'address', 'city', 'state', 
    'phone_number', 'email'
]

"""
-----  Scrape Methods  -----
"""

def scrape_dog_ids():
    """
    Getting all dog_ids on the dogsindanger website.
    Scraper en

    Each dog's page can be accessed by:
    dogsindanger.com/dog/<dog_id>
    """
    BASE = "https://www.dogsindanger.com/searchReturn_desktop.jsp?BREED=&t=90&startId={start_index}&zip=&radius=100.0&state={state}&Transport=0"
    states = ['AZ', 'CA', 'FL', 'GA', 'NC', 'OH', 'OK', 'TX']
    dogs_ids = []

    # Repeating for each state
    for state in states:
        start_index = 0
        
        # Looping through start_indicies
        while True:
            # Fetching a response
            url = BASE.format(start_index=start_index, state=state)
            # time.sleep(0.5) # *** UNCOMMENT AS A POSSIBLE FIX FOR UNEXPECTED ERRORS ***
            response = requests.get(url)
            
            # Ensure Page Exists (CRITICAL ERROR IF FAILS)
            try: 
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"HTTP ERROR: {e}")
                return None
            except requests.exceptions.RequestException as e:
                print(f"NON-HTTP ERROR (e.g network issue): {e}")
                return None

            # END condition, start_index is too high, scraping for state complete
            if "There are no dogs matching your search criteria." in response.text:
                break # the break here is used responsibly (I hope)
            
            # HTML parsing
            soup = BeautifulSoup(response.text, 'html.parser')
            dog_divs = soup.find_all('div', attrs={'style': 'border-radius:5px;border:2px solid #999;background-color:white;box-shadow:0px 0px 10px #888;position:relative;margin-bottom:9px;'})
            for div in dog_divs:
                href_val = div.find_all('a')[0]['href']
                id = re.search(r'/dog/(\d+)-', href_val).group(1) # may have AttributeError if link is unexpected, theoretically should not happen
                dogs_ids.append(id)

            # Increment
            start_index += 20
    
        print(f"State complete: {state}")

    return dogs_ids

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
    name_div = container.find('div', attrs={'style': 'font-size:24pt;text-transform:capitalize;line-height:1.0;margin-bottom:7px;'})
    dog['name'] = name_div.get_text(strip=True).title() if name_div else ""

    # Dog image
    img = container.find('img', attrs={'id': 'mainImageX'})
    dog['image_urls'] = [img.get('src')] if (img and img.get('src')) else []

    # Dog description
    description_div = container.find('div', attrs={'style': 'font-size:1.2em'})
    if description_div:
        raw_desc = description_div.find(string=True, recursive=False)
        dog['description'] = raw_desc.strip().lstrip(': ') if raw_desc else ""
    else:
        dog['description'] = ""

    # Euthanasia date + reason (defensive)
    dog['euthanasia_date'] = ""
    dog['euthanasia_reason'] = ""
    euthanasia_div = container.find('div', attrs={'style': 'font-size:10pt;'})
    if euthanasia_div:
        strip_strs = [l for l in euthanasia_div.stripped_strings]

        # date: try span last 12 chars, else fallback to list parsing
        span = euthanasia_div.find('span')
        if span:
            dog['euthanasia_date'] = span.get_text(strip=True)[-12:]
        elif len(strip_strs) >= 2:
            dog['euthanasia_date'] = strip_strs[-2][-12:]

        # reason: best effort
        if strip_strs:
            last = strip_strs[-1]
            dog['euthanasia_reason'] = last[8:] if len(last) > 8 else last

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

        if lines[i] == 'Age:' and i+1 < n:
            dog['age'] = lines[i+1]; i += 2; continue

        if lines[i] == 'Gender:' and i+1 < n:
            dog['gender'] = lines[i+1]; i += 2; continue

        if lines[i] == 'Size:' and i+1 < n:
            dog['size'] = lines[i+1]; i += 2; continue

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

        if lines[i] == 'Shelter dog ID:' and i+1 < n:
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

            if counter % 20 == 0:
                print(f"Scraped {counter} pets so far. (skipped={skipped})")

        except Exception as e:
            skipped += 1
            print(f"[SKIP] id={id} crashed: {type(e).__name__}: {e}")
            continue

    print(f"\nScraped {counter} pets total. Skipped {skipped}.\n")




"""
-----  Execution / Test  -----
"""

if __name__ == '__main__':
    start = time.time()
    scrape_to_db()
    end = time.time()
    print("\nScraping Complete!")
    print(f"Duration: {(end - start) / 60:.0f} minutes.\n")