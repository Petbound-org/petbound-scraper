# schemas.py

from pydantic import BaseModel, Field

class Shelter(BaseModel):
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    phone_number: str = ""
    email: str = ""

class Dog(BaseModel):
    name: str = ""
    breed: str = ""
    age: str = ""
    gender: str = ""
    size: str = ""
    description: str = ""
    euthanasia_date: str = ""
    euthanasia_reason: str = ""
    shelter_given_id: str = ""
    image_urls: list[str] = Field(default_factory=list)