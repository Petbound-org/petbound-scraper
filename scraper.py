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

# Database Connection
load_dotenv()
supabase: Client = create_client(
    os.environ['SUPABASE_URL'],
    os.environ['SUPABASE_KEY']
)

def get_dog_ids():
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

def test_get_dog_ids():
    start = time.time()
    ids = get_dog_ids()
    end = time.time()

    print(f"\nScraped {len(ids)} dogs")
    print(f"All ids are unique: {len(set(ids)) == len(ids)}")
    print(f"Total duration: {(end - start):.2f}s")
    print(f"Page scraping duration (avg, upper estim): {20 * ((end - start) / len(ids)):.3f}\n") # keep >0.5s, use time.sleep() if necessary

def scrape_dog(id):
    """
    Scrapes the data of a dog given its ID.
    
    Each dog's page can be accessed by:
    dogsindanger.com/dog/<ID>
    """
    url = f"dogsindanger.com/dog/{id}"
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
    
    soup = BeautifulSoup(response.text, 'html.parser')
    container = soup.find('div', attrs={'class': 'purplebox'})
    img_url = container.find('img', attrs={'id': 'mainImageX'})['src']

    # Discuss good ways to target an get elements
    # Consider getting all the text inside container and processing that
    # Using the elements right after <strong> might also work (this is what was used last time)


def scrape():
    """
    Master function that needs to be called in 
    """
    pass

if __name__ == '__main__':
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