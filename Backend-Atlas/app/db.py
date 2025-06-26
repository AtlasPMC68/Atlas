import os
import psycopg2
from dotenv import load_dotenv

# Charge les variables d'environnement depuis .env.dev
load_dotenv(dotenv_path=".env.dev")

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)