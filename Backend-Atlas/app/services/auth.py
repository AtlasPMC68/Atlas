import random
from sqlalchemy.orm import Session
from ..models.user import User

def generate_username(db:Session):
    for _ in range(10): # Attempt to generate a unique username 10 times
        # Constraints
        minimum_digits = 3 
        minimum_special_characters = 1
        special_characters = ['!', '-', '_', '$', '%', '*']
        minimum_characters = 3

        # Variable to store the generated username
        username = "AtlasUser"

        temp_list = []
        # Generate random digits
        for _ in range(minimum_digits):
            digit = str(random.randint(0, 9))
            temp_list.append(digit)
        
        # Generate random special characters
        for _ in range(minimum_special_characters):
            special_character = random.choice(special_characters)
            temp_list.append(special_character)
        
        # Generate random characters
        for _ in range(minimum_characters):
            character = chr(random.randint(97, 122))  # a-z
            temp_list.append(character)

        # Shuffle the list to mix characters, digits, and special characters
        random.shuffle(temp_list)

        # Join the list to form the final username
        username += ''.join(temp_list)

        # Check if the username is unique in the database
        if not db.query(User).filter(User.username == username).first():
            return username
    return None  # Return None if a unique username could not be generated after 10 attempts
