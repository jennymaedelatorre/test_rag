from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from starlette.templating import Jinja2Templates
import os
from datetime import datetime
import traceback
import logging


from database.session import get_db
from database.models import Topic, Course, DownloadHistory, GeneratedQuestion, User, StudentQuizAttempt, StudentCourseProgress


logger = logging.getLogger("uvicorn.error")
student_topic_router = APIRouter(prefix="/student", tags=["Student"])
templates = Jinja2Templates(directory="templates")

# Configuration (Used for file viewing/downloading)
UPLOAD_DIR = "uploads/topics"
os.makedirs(UPLOAD_DIR, exist_ok=True) 
ABSOLUTE_UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)


# ==============================
#  GET: Student Course List
# ==============================
@student_topic_router.get("/courses", response_class=HTMLResponse, name="student_courses")
def student_course_list_placeholder(request: Request):
    """Placeholder for the student's main course list/dashboard view."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)
    
    return templates.TemplateResponse("student/courses.html", {
        "request": request,
        "courses": [], 
    })


# ==============================
#  GET: Topic List
# ==============================
@student_topic_router.get(
    "/course/{course_id}/topics", 
    response_class=HTMLResponse, 
    name="view_course_topics_student" 
)
def view_course_topics_student(
    course_id: int, 
    request: Request, 
    db: Session = Depends(get_db)
):
    """
    Renders the list of topics for a specific course, including the count 
    of generated questions for each topic and student's attempts.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch Course Details
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")
    
    # count generated questions per topic
    questions_count_subquery = db.query(
        GeneratedQuestion.topic_id, 
        func.count(GeneratedQuestion.question_id).label('question_count')
    ).group_by(GeneratedQuestion.topic_id).subquery()

    # Fetch Topics, LEFT JOIN with the question count
    results = db.query(
        Topic, 
        questions_count_subquery.c.question_count
    ).filter(
        Topic.course_id == course_id
    ).outerjoin(
        questions_count_subquery,
        Topic.id == questions_count_subquery.c.topic_id
    ).order_by(Topic.topic_no).all()
    
    # Process results to attach question_count 
    topics_with_count = []
    for topic, count in results:
        topic.question_count = count if count is not None else 0
        topics_with_count.append(topic)

    # Count attempts per topic for each student
    student_attempts = {}
    for topic in topics_with_count:
        attempts_count = db.query(StudentQuizAttempt).filter_by(
            student_id=user.id, 
            topic_id=topic.id
        ).count()
        student_attempts[topic.id] = attempts_count

    # Render the Template 
    return templates.TemplateResponse("student/topics.html", {
        "request": request,
        "course": course,
        "topics": topics_with_count,
        "student_attempts": student_attempts  
    })


# ==============================
# GET: View File 
# ==============================

@student_topic_router.get("/topic/{topic_id}/view", name="topic_file_view")
def topic_file_view(topic_id: int, request: Request, db: Session = Depends(get_db)):

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/auth/login", status_code=303)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic or not topic.file_path:
        raise HTTPException(404, "File not found")

    
    file_path = os.path.join(UPLOAD_DIR, topic.file_path)
    
    
    absolute_file_path = os.path.abspath(file_path)
    if not absolute_file_path.startswith(ABSOLUTE_UPLOAD_DIR):
        logger.error(f"Path Traversal attempt blocked for user {user_id}: {file_path}")
        raise HTTPException(400, "Invalid file path.")

    return FileResponse(
        path=absolute_file_path,
        filename=os.path.basename(absolute_file_path),
        media_type="application/pdf" 
    )

# ==============================
# GET: Download File 
# ==============================
@student_topic_router.get("/topic/{topic_id}/download", name="download_topic_file")
def download_topic_file(topic_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=307)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic or not topic.file_path:
        raise HTTPException(status_code=404, detail="Topic or file not found.")

    
    file_path = os.path.join(UPLOAD_DIR, topic.file_path)
    absolute_file_path = os.path.abspath(file_path)
    if not absolute_file_path.startswith(ABSOLUTE_UPLOAD_DIR):
        raise HTTPException(400, "Invalid file path.")
    if not os.path.exists(absolute_file_path):
        raise HTTPException(404, "File not found on server.")

    filename = os.path.basename(absolute_file_path)
    file_size = os.path.getsize(absolute_file_path)

   
    existing = db.query(DownloadHistory).filter_by(user_id=user_id, topic_id=topic_id).first()
    if existing:
        existing.downloaded_at = datetime.utcnow()
        db.commit()
    else:
        new_download = DownloadHistory(
            user_id=user_id,
            topic_id=topic_id,
            filename=filename,
            file_size=file_size,
            downloaded_at=datetime.utcnow()
        )
        db.add(new_download)
        db.commit()

    return FileResponse(
        path=absolute_file_path,
        filename=filename,
        media_type="application/octet-stream"
    )
