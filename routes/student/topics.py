from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
import os
from datetime import datetime


from database.session import get_db
from database.models import Topic, Course, DownloadHistory


# --- Setup ---
student_router = APIRouter(prefix="/student", tags=["Student"])
templates = Jinja2Templates(directory="templates")

# Configuration (Used for file viewing/downloading)
UPLOAD_DIR = "uploads/topics"
os.makedirs(UPLOAD_DIR, exist_ok=True) 


# --- Routes ---

## 📚 GET: Student Course List (Target for the 'Back' button)
@student_router.get("/courses", response_class=HTMLResponse, name="student_courses")
def student_course_list_placeholder(request: Request):
    """Placeholder for the student's main course list/dashboard view."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)
    
    # Renders a simple course list page 
    return templates.TemplateResponse("student/courses.html", {
        "request": request,
        "courses": [], 
    })


## 👁️ GET: Student Topic View (The Topic List)

@student_router.get(
    "/course/{course_id}/topics", 
    response_class=HTMLResponse, 
    name="view_course_topics_student" 
)
def view_course_topics_student(
    course_id: int, 
    request: Request, 
    db: Session = Depends(get_db)
):
    """Renders the list of topics for a specific course for the student to view."""
    # 1. Authentication Check
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    # 2. Fetch Course Details
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    # 3. Fetch Topics filtered by the Course ID
    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.topic_no).all()

    # 4. Render the Template 
    return templates.TemplateResponse("student/topics.html", {
        "request": request,
        "course": course,
        "topics": topics,
    })


## ⬇️ GET: Download File (For Topic Materials)
@student_router.get("/topic/{topic_id}/download", name="download_topic_file")
def download_topic_file(topic_id: int, request: Request, db: Session = Depends(get_db)):
    """Allows a student to download or view the file associated with a topic and record the event."""

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=307)

    # find the topic
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")
    
    # Check if the path exists in the database
    if not topic.file_path:
        raise HTTPException(status_code=404, detail="No file found for this topic in the database.")

    # The database saves the RELATIVE path 
    relative_db_path = topic.file_path
    
    file_path = relative_db_path 
    filename = os.path.basename(file_path)

    if not os.path.exists(file_path):
        print(f"DEBUG: File not found at path: {os.path.abspath(file_path)}")
        raise HTTPException(status_code=404, detail="File not found on server.")

    # 3. Record Download History
    file_size = os.path.getsize(file_path) 
    existing = db.query(DownloadHistory).filter_by(user_id=user_id, topic_id=topic_id).first()

    if not existing:
        new_download = DownloadHistory(
            user_id=user_id,
            topic_id=topic_id,
            filename=filename, 
            file_size=file_size,
            downloaded_at=datetime.utcnow()
        )
        db.add(new_download)
        db.commit()
        db.refresh(new_download)

    # Serve file
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


## ❓ GET: Take Quiz Page (Placeholder for the static link)
@student_router.get("/quiz/{quiz_id}", response_class=HTMLResponse, name="take_quiz_page")
def take_quiz_page(quiz_id: int, request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)
        
    # Renders a simple quiz page 
    return templates.TemplateResponse("student/quiz.html", {
        "request": request,
        "quiz_id": quiz_id,
    })