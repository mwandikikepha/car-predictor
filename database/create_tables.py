from database.connection import engine
from database.models import Base


def create_all_tables():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    create_all_tables()
    print("Tables created successfully.")