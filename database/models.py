import uuid
from datetime import datetime
from sqlalchemy import Integer, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

# Define the base class for declarative class definitions
Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)    
    document_uuid = Column(String, unique=True, index=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    