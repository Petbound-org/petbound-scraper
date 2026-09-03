# database.py

import os
from dotenv import load_dotenv
from supabase import create_client, Client

from schemas import Dog, Shelter

"""
-----  Connection  -----
"""

def get_client() -> Client:
    """ Connects to supabase and returns the supabase client. """
    load_dotenv()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url:
        raise EnvironmentError("SUPABASE_URL environment variable not set. Check GitHub Actions secrets.")
    if not supabase_key:
        raise EnvironmentError("SUPABASE_KEY environment variable not set. Check GitHub Actions secrets.")

    return create_client(supabase_url, supabase_key)

"""
-----  Write  -----
"""

def update_db(supabase: Client, dog: Dog, shelter: Shelter):
    """Upserts one dog and its shelter.

    Models are converted to plain dicts here, because this is the boundary where
    they stop being our objects and become JSON for the API.
    """
    dog_data = dog.model_dump()
    shelter_data = shelter.model_dump()

    # Check if shelter exists in data
    response = (
        supabase.table('shelters')
        .select('id')
        .filter('name', 'eq', shelter_data['name'])
        .filter('address', 'eq', shelter_data['address'])
        .execute()
        .data
    )

    # Setting shelter ID or adding shelter then setting ID
    if response:
        dog_data['shelter_id'] = response[0]['id']
    else:
        response = supabase.table('shelters').insert(shelter_data).execute().data
        dog_data['shelter_id'] = response[0]['id']

    # Check if dog exists in DB (matching shelter + shelter given ID)
    response = (
        supabase.table('pets')
        .select('id')
        .filter('shelter_given_id', 'eq', dog_data['shelter_given_id'])
        .filter('shelter_id', 'eq', dog_data['shelter_id'])
        .execute()
        .data
    )

    # Updating dog data if exists, else creating a new dog
    if response:
        supabase.table('pets').update(dog_data).filter('id', 'eq', response[0]['id']).execute()
    else:
        supabase.table('pets').insert(dog_data).execute()

"""
-----  Tests  -----
"""

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

    print(test_pet)
    print(test_shelter)
