import os
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'dbname': os.getenv('PG_DB'),
    'host': os.getenv('PG_HOST'),
    'user': os.getenv('PG_USER'),
    'port': os.getenv('PG_PORT')
}

pool = ConnectionPool(
    kwargs=DB_CONFIG,
    min_size=1,
    max_size=10,
    open=False
    )
