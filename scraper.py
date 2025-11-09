# scraper.py

# imports
import requests
from bs4 import BeautifulSoup
import time
import re # regular expressions
from selenium import webdriver
from selenium.webdriver.common.by import By
import csv

# Params
states = ['AZ', 'CA', 'FL', 'GA', 'NC', 'OH', 'OK', 'TX']
BASE = "https://www.dogsindanger.com/searchReturn_desktop.jsp?BREED=&t=90&startId={start_index}&zip=&radius=100.0&state={state}&Transport=0"

def get_dog_ids():
    """
    Getting all dog_ids on the dogsindanger website.

    Each dog's page can be accessed by:
    dogsindanger.com/dog/<dog_id>
    """
    dogs_ids = []

    # Repeating for each state
    for state in states:
        # Accounting for index and end page
        start_index = 0
        complete = False
        
        # Looping through start_indicies
        while True:
            # Fetching a response
            url = BASE.format(start_index=start_index, state=state)
            response = requests.get(url)
            time.sleep(0.5) # for the sake of the server (DO NOT REMOVE, BAD THINGS MAY HAPPEN)
            
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
                break
            
            # HTML parsing
            soup = BeautifulSoup(response.text, 'html.parser')
            dog_divs = soup.find_all('div', attrs={'style': 'border-radius:5px;border:2px solid #999;background-color:white;box-shadow:0px 0px 10px #888;position:relative;margin-bottom:9px;'})
            for div in dog_divs:
                href_val = div.find_all('a')[0]['href']
                id = re.search(r'/dog/(\d+)-', href_val).group(1) # extracting id using regular expressions
                dogs_ids.append(id)

            # Increment
            start_index += 20
    
        print(f"State complete: {state}")

    return dogs_ids

if __name__ == '__main__':
    start = time.time()
    ids = get_dog_ids()
    end = time.time()

    print(f"\nScraped {len(ids)} dogs.")
    print(f"All ids are unique: {len(set(ids)) == len(ids)}.")
    print(f"Total duration: {(end - start):.2f}s.\n")