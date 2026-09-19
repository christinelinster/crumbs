import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'dbname': os.getenv('PG_DB'),
    'host': os.getenv('PG_HOST'),
    'user': os.getenv('PG_USER'),
    'port': os.getenv('PG_PORT')
}
