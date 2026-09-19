from psycopg_pool import ConnectionPool
from app.db.config import DB_CONFIG


pool = ConnectionPool(
    kwargs=DB_CONFIG,
    min_size=1,
    max_size=10,
    open=False
    )
