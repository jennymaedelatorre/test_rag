from database.session import SessionLocal
import logging 
from database.models import Document 
import logging 
from sqlalchemy import select


def save_document(document_name: str, file_hash: str, index_path: str, document_uuid: str):
    """
    Saves the document metadata (including the file hash) to the database.
    
    Args:
        document_name: The user-friendly name of the file 
        file_hash: The cryptographic hash used for caching and retrieval
        index_path: The path to the created FAISS index on the server 
        document_uuid: The unique ID associated with the document.
    """
    session = SessionLocal()
    try:
        # Check if the hash already exists before insertion
        existing_doc = session.query(Document).filter(Document.file_hash == file_hash).first()
        if existing_doc:
            logging.info(f"Metadata for hash {file_hash} already exists. Skipping insert.")
            return existing_doc # Return the existing document

        # Create new document instance with all required fields
        new_doc = Document(
            filename=document_name, 
            file_hash=file_hash,
            index_path=index_path,
            document_uuid=document_uuid
            )
        session.add(new_doc)
        session.commit()
        logging.info(f"✅ DB SUCCESS: Saved metadata for: {document_name} with hash: {file_hash}")
        return new_doc
    except Exception as e:
        session.rollback()
        logging.error(f"❌ DB FAILURE: Failed to save metadata for {document_name}. Error: {e}")
        # Re-raise the exception for the calling FastAPI endpoint to handle
        raise 
    finally:
        session.close()


def retrieve_all_documents_metadata() -> list[dict]:
    """
    Retrieves the name, hash_id, and UUID for all indexed documents 
    from the database, ordered by creation date descending.
    
    This function is used by the /get-documents/ FastAPI endpoint.
    """
    session = SessionLocal()
    try:
        # Select all documents, ordered by creation date descending
        documents = session.execute(
            select(Document)
            .order_by(Document.created_at.desc())
        ).scalars().all()

        # Convert ORM objects to list of dictionaries using the to_dict method
        document_list = [doc.to_dict() for doc in documents]
        
        logging.info(f"DB: Retrieved {len(document_list)} document records.")
        return document_list
    except Exception as e:
        logging.error(f"❌ DB FAILURE: Failed to retrieve document list. Error: {e}")
        # Raise the exception for the calling FastAPI endpoint to handle
        raise 
    finally:
        session.close()
