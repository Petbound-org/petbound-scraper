# scraper.py

import re # regular expressions
import time
import requests
from bs4 import BeautifulSoup

from schemas import Dog, Shelter

# Conversion from website text to cleaner versions
SIZE_TEXT_CONVERSION = {
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
    "x-large": "X-Large",
    "xlarge": "X-Large",
    "extra large": "X-Large",
}
AGE_TEXT_CONVERSION = {
    "under 6 months": "Under 6 months",
    "young adult": "Young adult",
    "adult": "Adult",
    "senior": "Senior",
}
GENDER_TEXT_CONVERSION = {
    "male": "Male",
    "female": "Female",
}

"""
-----  Scrape All Dog IDs  -----
"""

def scrape_dog_ids():
    """
    Getting all dog_ids on the dogsindanger.com website.

    Each dog's page can be accessed by:
    dogsindanger.com/dog/<dog_id>
    """
    BASE = "https://www.dogsindanger.com/searchReturn_desktop.jsp?BREED=&t=90&startId={start_index}&zip=&radius=100.0&state={state}&Transport=0"
    states = [
        'AZ', 'CA', 'FL', 'GA', 'IL', 'KS', 'MD', 'NC',
        'NM', 'NV', 'NY', 'OH', 'OK', 'PA', 'TX',
    ]
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

"""
-----  Scrape Dog Info Given ID  -----
"""

def scrape_dog(id):
    """
    Scrapes the data of a dog given its ID.
    Each dog's page: https://www.dogsindanger.com/dog/<ID>
    """
    url = f"https://www.dogsindanger.com/dog/{id}"
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

    soup = BeautifulSoup(response.text, 'lxml')
    container = soup.find('div', attrs={'id': 'doggie'})

    # Edge case: no dog details at all
    if not container:
        print(f"[PARSE ERROR] dog_id={id} url={url} -> missing #doggie container")
        return None

    dog = Dog()
    shelter = Shelter()

    # Name
    name_div = container.find('div', style=re.compile(r'font-size:\s*24pt'))
    if name_div:
        dog.name = name_div.get_text(strip=True).title()

    # Image
    img = container.find('img', attrs={'id': 'mainImageX'})
    dog.image_urls = [img.get('src')] if (img and img.get('src')) else []

    # Description 
    description_div = _get_description_div(container)
    if description_div:
        parts = []
        for text_node in description_div.find_all(string=True, recursive=False):
            text = text_node.strip()
            if text:
                parts.append(text)

        description = "\n".join(parts)

        dog.description = description.lstrip(":").strip()


    # Euthanasia date + reason
    dog.euthanasia_date, dog.euthanasia_reason = _parse_euthanasia_info(container)

    # Breed
    dog.breed = _get_labelled_value(container, 'Breed:')

    # Shelter's dog ID
    dog.shelter_given_id = (
        _get_labelled_value(container, 'Dog ID:')
        or _get_labelled_value(container, 'Shelter dog ID:')
    )

    # Size + age + gender
    dog.size, dog.age, dog.gender = _parse_profile(container)

    # Shelter name + street + city + state
    shelter.name, shelter.address, shelter.city, shelter.state = _parse_shelter_location(container)

    # Shelter contact info
    shelter.phone_number = _get_labelled_value(container, 'Phone:')
    shelter.email = _get_labelled_value(container, 'email:')

    return dog, shelter

"""
-----  Helpers  -----
"""

def _get_description_div(page):
    """ Helper to find description div on a dog page. """
    avoid_labels = {'Breed', 'Profile'}

    # Should be 2 matches for the find all
    for div in page.find_all('div', style=re.compile(r'font-size:\s*1\.2em')):
        labels = set()
        for partition in div.find_all('strong'):
            text = partition.get_text().strip().rstrip(":")
            labels.add(text)

        # overlap signals that this is the wrong block
        if labels & avoid_labels:
            continue

        return div

def _find_label(page, label):
    """ Finds labels. Assumes they're wrapped in strong tags. """
    return page.find('strong', string=re.compile(rf'^\s*{re.escape(label)}\s*$'))

def _get_labelled_value(page, label):
    """ Gets the text following a label """
    strong = _find_label(page, label)
    if not strong:
        return ""

    text = strong.parent.get_text("\n", strip=True)
    return text.removeprefix(label).strip()

def _parse_shelter_location(page):
    """ Parses the "Shelter Information" block to find name, address, city, state. """
    strong = _find_label(page, 'Shelter Information:')
    if not strong:
        return "", "", "", ""

    block = strong.find_next_sibling('div')
    if not block:
        return "", "", "", ""

    lines = block.get_text("\n", strip=True).split("\n")
    name = lines[0] if len(lines) > 0 else ""
    address = lines[1] if len(lines) > 1 else ""
    city_state = lines[2] if len(lines) > 2 else ""

    city, _, state = city_state.rpartition(',')

    return name, address, city.strip(), state.strip()

def _parse_euthanasia_info(page):
    """ Parses the "At Risk To Be Killed:" banner to find euthanasia date + reason. """
    div = page.find('div', style=re.compile(r'font-size:\s*10pt'))
    if not div:
        return "", ""

    text = re.sub(r'\s+', ' ', div.get_text(" ", strip=True)).strip()

    match = re.search(r'At Risk To Be Killed:\s*(?:TODAY!\s*)?(.*?)\s*(?:Reason:\s*(.*))?$', text)
    if not match:
        return "", ""

    return match.group(1).strip(), (match.group(2) or "").strip()

def _parse_profile(page):
    """ Parses the "Profile" block to find age, breed, and gender. """
    text = _get_labelled_value(page, 'Profile:')
    if not text:
        return "", "", ""

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    descriptor = lines[0] if len(lines) > 0 else ""
    gender = lines[1] if len(lines) > 1 else ""

    match = re.match(r'(?i)^(.*?)\s+size\s+(.+)$', descriptor)
    size = match.group(1) if match else ""
    age = match.group(2) if match else ""

    return (
        _normalize(size, SIZE_TEXT_CONVERSION),
        _normalize(age, AGE_TEXT_CONVERSION),
        _normalize(gender, GENDER_TEXT_CONVERSION),
    )

def _normalize(value, mapping):
    """ Reformats to camelcase """
    if not value:
        return ""

    key = re.sub(r'\s+', ' ', value).strip().lower()
    return mapping.get(key, key.title())

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

def test_scrape_dog():
    # 1758257073360 - Nacie
    # 1761092968039 - Peabody
    # 1785642130505 - Mj (strange description)
    dog_ids = [1758257073360, 1785642130505, 1785642130505]

    for dog_id in dog_ids:
        result = scrape_dog(dog_id)
        if result is None:
            print(f"\n[FAIL] scrape_dog({dog_id}) returned None\n")
            continue

        dog, shelter = result
        print(f"\n----- {dog_id} -----")
        print(f"Dog: {dog}\n")
        print(f"Shelter: {shelter}\n")