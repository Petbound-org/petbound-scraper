# scraper.py

# imports
import os
import requests
import time
import csv
import re # regular expressions
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from supabase import create_client, Client
from dotenv import load_dotenv

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
            response = requests.get(url)
            # time.sleep(0.5) # *** UNCOMMENT AS A POSSIBLE FIX FOR UNEXPECTED ERRORS ***
            
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
    
    Each dog's page can be accessed by:
    dogsindanger.com/dog/<ID>
    """
    url = f"https://www.dogsindanger.com/dog/{id}"
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
    
    soup = BeautifulSoup(response.text, 'lxml')
    container = soup.find('div', attrs={'id': 'doggie'})

    dog = {} # all dog data goes here
    shelter = {} # all shelter data goes here

    # Dog name
    name_div = container.find('div', attrs={'style': 'font-size:24pt;text-transform:capitalize;line-height:1.0;margin-bottom:7px;'})
    dog['name'] = name_div.get_text(strip=True).title()

    # Dog image (only one)
    dog['image_urls'] = [container.find('img', attrs={'id': 'mainImageX'})['src']]

    # Dog descriptions (using text didn't work consistently)
    description_div = container.find('div', attrs={'style': 'font-size:1.2em'})
    dog['description'] = description_div.find(string=True, recursive=False).strip().lstrip(': ')

    # Euthanasia date + reason
    euthanasia_div = container.find('div', attrs={'style': 'font-size:10pt;'})
    strip_strs = [l for l in euthanasia_div.stripped_strings]
    dog['euthanasia_date'] = strip_strs[-2][-12:] # ALT: euthanasia_div.find('span').get_text(strip=True)[-12:]
    dog['euthanasia_reason'] = strip_strs[-1][8:]
    
    # Finding data in raw text
    text = container.get_text(strip=True, separator="\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    n = len(lines)

    while i < n:
        if lines[i] == 'Breed:':
            dog['breed'] = lines[i+1]
            i += 2
            continue
        
        if lines[i] == 'Age:':
            dog['age'] = lines[i+1]
            i += 2
            continue
        
        if lines[i] == 'Gender:':
            dog['gender'] = lines[i+1]
            i += 2
            continue
        
        if lines[i] == 'Size:':
            dog['size'] = lines[i+1]
            i += 2
            continue
        
        if lines[i] == 'Shelter Information:':
            shelter['name'] = lines[i+1]
            shelter['address'] = lines[i+2]
            shelter['city'] = lines[i+3][:-4]
            shelter['state'] = lines[i+3][-2:]
            i += 4
            continue
        
        if lines[i] == 'Shelter dog ID:':
            dog['shelter_given_id'] = lines[i+1]
            i += 2
            continue
        
        if lines[i] == 'Contact:':
            shelter['phone_number'] = lines[i+2]
            shelter['email'] = lines[i+6]
            i += 7
            continue
        
        i += 1 # general increment
    
    return dog, shelter # complete

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
    # Database Connection
    load_dotenv()
    supabase: Client = create_client(
        os.environ['SUPABASE_URL'],
        os.environ['SUPABASE_KEY']
    )

    # Scrape all ids
    dog_ids = scrape_dog_ids()

    # Scrape and update dogs
    counter = 0
    for id in dog_ids:
        dog, shelter = scrape_dog(id)
        update_db(supabase, dog, shelter)
        
        counter += 1 

        if counter % 20 == 0:
            print(f"Scraped {counter} pets so far.")
    
    print(f"Scraped {counter} pets total.")

"""
-----  Execution / Test  -----
"""

if __name__ == '__main__':
    start = time.time()
    scrape_to_db()
    end = time.time()
    print("\nScraping Complete!")
    print(f"Duration: {(end - start) / 60:.0f} minutes.\n")

"""
Gave up on this method because it seems useless.

Downloading data from DB is probably better.

def scrape_to_csv(write_to):
    # Database Connection
    load_dotenv()
    supabase: Client = create_client(
        os.environ['SUPABASE_URL'],
        os.environ['SUPABASE_KEY']
    )
    
    # Scrape all ids
    dog_ids = scrape_dog_ids()

    # Write header to csv
    with open(PET_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(PET_HEADER)
    with open(SHELTER_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(SHELTER_HEADER)

    # Scrape and update dogs
    for id in dog_ids:
        dog, shelter = scrape_dog(id)
        
        # append to CSV (organize obj by _HEADER)

"""