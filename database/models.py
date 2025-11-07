import uuid
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
from sqlalchemy import Integer, Column, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base


from passlib.context import CryptContext

# Define the hashing context
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    username = Column(String, unique=True, index=True)
    # Store the hashed password
    hashed_password = Column(String) 
    role = Column(String) # e.g., "student", "faculty"


    # Static method to get the hash of a password
    @staticmethod
    def get_password_hash(password):
        """Hashes a password using the SHA256-based context."""
        return pwd_context.hash(password)

    # Instance method to set the password
    def set_password(self, password):
        """Sets the hashed password attribute for the user object."""
        self.hashed_password = self.get_password_hash(password)

    # Instance method to check a password
    def check_password(self, password):
        """Verifies a password against the stored hash."""
        return pwd_context.verify(password, self.hashed_password)
    
    # Relationship to courses (for faculty)
    courses = relationship("Course", back_populates="instructor")

    downloads = relationship("DownloadHistory", back_populates="user", cascade="all, delete")

    # 🌟 NEW RELATIONSHIPS 🌟
    # 1. Links User to Documents they uploaded
    documents = relationship(
        "Document", 
        back_populates="uploader", 
        cascade="all, delete-orphan" # Optional: Deletes docs if user is deleted
    )

    # 2. Links User to Questions they generated
    generated_questions = relationship(
        "GeneratedQuestion", 
        back_populates="generator", 
        cascade="all, delete-orphan" # Optional: Deletes questions if user is deleted
    )
    

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

     # Relationship to faculty
    instructor = relationship("User", back_populates="courses")

    # Relationship to CILOs
    cilos = relationship("CILO", back_populates="course", cascade="all, delete-orphan")

    topics = relationship("Topic", back_populates="course", cascade="all, delete")


class CILO(Base):
    __tablename__ = "cilos"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    cilo_code = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    course = relationship("Course", back_populates="cilos")


class Topic(Base):
    """
    Represents a learning material topic uploaded by faculty.
    """
    __tablename__ = "topics"

  
    id = Column(Integer, primary_key=True, index=True)
    topic_no = Column(Integer, nullable=False, index=True) 
    title = Column(String(255), nullable=False)
    subtitle = Column(String(500), default="", nullable=True) 

    # File Data
    file_path = Column(String(500), nullable=True) # Stores the path to the uploaded file

    # Relationships 
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = relationship("Course", back_populates="topics") 

    downloads = relationship("DownloadHistory", back_populates="topic", cascade="all, delete")

    def __repr__(self):
        return f"<Topic(id={self.id}, title='{self.title}', topic_no={self.topic_no})>"
    
    
    

class DownloadHistory(Base):
    __tablename__ = "download_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    topic_id = Column(Integer, ForeignKey("topics.id"))
    filename = Column(String, nullable=False)
    file_size = Column(Float, nullable=True) 
    downloaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="downloads")
    topic = relationship("Topic", back_populates="downloads")

    
# ... Document class ...
class Document(Base):
    __tablename__ = "documents"
    
    document_uuid = Column(String, primary_key=True, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    file_hash = Column(String, unique=True, index=True, nullable=False)
    index_path = Column(String, nullable=False) 
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    uploader = relationship("User", back_populates="documents") 

    generated_questions = relationship(
        "GeneratedQuestion",
        # This links to the 'source_document' relationship in the GeneratedQuestion model
        back_populates="source_document", 
        # Specifies how to handle cascading deletes/orphans
        cascade="all, delete-orphan" 
    )

    def to_dict(self):
        return {
            "document_uuid": str(self.document_uuid),
            "file_name": self.filename,
            "file_hash": self.file_hash,
            "uploaded_by_user_id": self.uploaded_by_user_id,
            "created_at": self.created_at.isoformat()
        }
    

class GeneratedQuestion(Base):
    __tablename__ = "generated_questions"
    
    # Primary Key
    question_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Keys / Document Metadata
    pdf_hash_id = Column(String, ForeignKey("documents.file_hash")) # Link to the indexed document
    # Link to the User table using the numerical Primary Key (best practice)
    user_id = Column(Integer, ForeignKey("users.id")) 
    
    # Question Data
    question_text = Column(String, nullable=False)
    options_json = Column(String, nullable=False) # Store the list of options as a JSON string
    correct_answer = Column(String, nullable=False) # Store the correct answer text
    co_tag = Column(String, nullable=False) # Store the Course Outcome tag (e.g., CO1)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    source_document = relationship("Document", back_populates="generated_questions") 
    generator = relationship("User", back_populates="generated_questions")

    