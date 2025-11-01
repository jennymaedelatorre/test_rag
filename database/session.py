import os
import logging 
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
import logging 


load_dotenv()

# Configure logging to ensure visibility of DB actions
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# PostgreSQL connection details from .env
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create the engine
engine = create_engine(DATABASE_URL)

# Create a configured "Session" class
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def initialize_database():
    """Creates database tables if they don't exist."""
    logging.info("Initializing database tables...")
    try:
        Base.metadata.create_all(engine)
        logging.info("Database initialization complete.")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")


def get_db():
    db = SessionLocal()  # open a new database connection
    try:
        yield db          # let the calling code use it
    finally:
        db.close()         # automatically close it when done
