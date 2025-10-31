import os
import uuid
import logging 
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Document 
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


def save_document(document_name: str, file_path: str, document_uuid: str):
    """Saves the document to the database."""
    session = SessionLocal()
    try:
        new_doc = Document(
            file_name=document_name, 
            file_path=file_path,
            document_uuid=document_uuid
            )
        session.add(new_doc)
        session.commit()
        logging.info(f"✅ DB SUCCESS: Saved metadata for: {document_name} at {file_path}")
    except Exception as e:
        session.rollback()
        logging.error(f"❌ DB FAILURE: Failed to save metadata for {document_name}. Error: {e}")
        raise 
    finally:
        session.close()
