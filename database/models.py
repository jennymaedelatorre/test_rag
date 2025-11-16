import uuid
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy import Integer, Column, String, DateTime, Text, ForeignKey, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)

    # Hash a password
    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)

    # Set hashed password
    def set_password(self, password):
        self.hashed_password = self.get_password_hash(password)

    # Verify password
    def check_password(self, password):
        return pwd_context.verify(password, self.hashed_password)

    # Relationships
    courses = relationship("Course", back_populates="instructor")
    downloads = relationship("DownloadHistory", back_populates="user", cascade="all, delete")
    generated_questions = relationship(
        "GeneratedQuestion",
        back_populates="generator",
        cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    # Relationships
    instructor = relationship("User", back_populates="courses")
    cilos = relationship("CILO", back_populates="course", cascade="all, delete-orphan")
    topics = relationship("Topic", back_populates="course", cascade="all, delete")
    total_topics = Column(Integer, default=10)


class CILO(Base):
    __tablename__ = "cilos"

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    cilo_code = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    course = relationship("Course", back_populates="cilos")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    topic_no = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    subtitle = Column(Text)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False)
    document_uuid = Column(UUID(as_uuid=True), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    course = relationship("Course", back_populates="topics")
    generated_questions = relationship(
        "GeneratedQuestion",
        back_populates="source_topic",
        lazy="dynamic"
    )
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

    # Relationships
    user = relationship("User", back_populates="downloads")
    topic = relationship("Topic", back_populates="downloads")


class GeneratedQuestion(Base):
    __tablename__ = "generated_questions"

    question_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(Integer, ForeignKey("topics.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    question_text = Column(String, nullable=False)
    options_json = Column(String, nullable=False)
    correct_answer = Column(String, nullable=False)
    co_tag = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_topic = relationship("Topic", back_populates="generated_questions")
    generator = relationship("User", back_populates="generated_questions")


class StudentQuizAttempt(Base):
    __tablename__ = "student_quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    submitted = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    attempt_number = Column(Integer, default=1)

    # Set the end time based on duration
    def set_end_time(self, duration_minutes=15):
        if not self.start_time:
            self.start_time = datetime.utcnow()
        self.end_time = self.start_time + timedelta(minutes=duration_minutes)

    answers = relationship("StudentAnswer", back_populates="attempt", cascade="all, delete-orphan")


class StudentAnswer(Base):
    __tablename__ = "student_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("student_quiz_attempts.id", ondelete="CASCADE"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("generated_questions.question_id", ondelete="CASCADE"))
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    student_answer = Column(String, nullable=True)
    co_tag = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships (optional)
    attempt = relationship(
        "StudentQuizAttempt",
        back_populates="answers"
    )
    
    question = relationship("GeneratedQuestion")

class StudentCOPerformance(Base):
    __tablename__ = "student_co_performance"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"))
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("student_quiz_attempts.id", ondelete="CASCADE"))
    co_tag = Column(String, nullable=False)
    total_questions = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    student = relationship("User")
    topic = relationship("Topic")
    attempt = relationship("StudentQuizAttempt")



class StudentCourseProgress(Base):
    __tablename__ = "student_course_progress"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)

    viewed = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)

    viewed_at = Column(DateTime)
    completed_at = Column(DateTime)

    student = relationship("User")
    topic = relationship("Topic")