# api/dependencies.py

from database.connection import engine
from sqlalchemy.orm import Session


def get_db():
    """Yield a database session for dependency injection."""
    with Session(engine) as session:
        yield session