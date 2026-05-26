# test_db_connection.py (run from project root)

from config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.DB_URL)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Connected. Database is reachable.")
except Exception as e:
    print(f"Connection failed: {e}")
