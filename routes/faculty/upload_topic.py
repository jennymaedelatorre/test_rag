from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
import os
import shutil
from typing import Optional
import mimetypes
from pathlib import Path

from database.session import get_db
from database.models import Topic, Course, User
from utils.flash import flash, get_flashed_messages

faculty_upload_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")
templates.env.globals["get_flashed_messages"] = get_flashed_messages

UPLOAD_DIR = "uploads/topics"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------------------
# Helper: User Dependency
# ----------------------------
def get_current_faculty(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
       
        return RedirectResponse(url="/auth/login", status_code=303) 
    
    # Query the user 
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != 'faculty':
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)
        
    return user

# ---------------------------------
# GET: Display Upload Page
# ---------------------------------
@faculty_upload_router.get("/course/{course_id}/upload_topic", response_class=HTMLResponse, name="upload_topic_page")
def upload_topic_page(course_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # 🔑 STEP 1: FETCH USER 
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user_full_name = user.full_name # Get the full name

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail=f"Course ID {course_id} not found.")

    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.topic_no).all()

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse("faculty/upload_topic.html", {
        "request": request,
        "course_id": course_id,
        "topics": topics,
        "user_full_name": user_full_name,
         "flashed": flashed,
    })
# ---------------------------------
# POST: Upload Topic
# ---------------------------------
BASE_UPLOAD_DIR = Path("uploads/topics") 
BASE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@faculty_upload_router.post("/course/{course_id}/upload_topic", name="upload_topic")
async def upload_topic(
    course_id: int,
    request: Request,
    title: str = Form(...),
    topic_no: int = Form(...),
    subtitle: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    # Prepare file path
    original_filename = Path(file.filename).name
    server_file_path = BASE_UPLOAD_DIR / original_filename

    print(f"DEBUG CHECKING PATH: {server_file_path.resolve()}")

    # Check if file already exists
    existing_topic = db.query(Topic).filter(
        Topic.course_id == course_id,
        Topic.file_path.like(f"%{original_filename}%")
    ).first()

    if existing_topic:
        flash(
            request,
            f"Upload failed: Topic '{existing_topic.title}' (Topic No. {existing_topic.topic_no}) already exists with file '{original_filename}'.",
            category="warning"
        )
        return RedirectResponse(
            url=f"/faculty/course/{course_id}/upload_topic",
            status_code=303
        )

    # Save file to disk
    try:
        with open(server_file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        print(f"File I/O Error: {e}")
        raise HTTPException(status_code=500, detail="Could not save file to the server due to an I/O error.")

    # Save topic to database
    try:
        new_topic = Topic(
            topic_no=topic_no,
            title=title,
            subtitle=subtitle,
            file_path=str(server_file_path),
            course_id=course_id
        )
        db.add(new_topic)
        db.commit()
        db.refresh(new_topic)
    except Exception as e:
        db.rollback()
        # Remove file if DB save fails
        if server_file_path.exists():
            os.remove(server_file_path)
        print(f"Database save error: {e}")
        raise HTTPException(status_code=500, detail="Database error. Topic could not be saved.")

    flash(request, f"Topic '{title}' uploaded successfully!", category="success")
    return RedirectResponse(
        url=f"/faculty/course/{course_id}/upload_topic",
        status_code=303
    )

# ---------------------------------
# POST: Update Topic
# ---------------------------------
@faculty_upload_router.post("/update_topic/{topic_id}", name="update_topic")
async def update_topic(
    topic_id: int,
    request: Request,
    title: str = Form(...),
    subtitle: str = Form(""),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic.title = title
    topic.subtitle = subtitle

    if file and file.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        
        if topic.file_path and os.path.exists(topic.file_path):
            os.remove(topic.file_path)

        # Save new file
        file_location = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_location, "wb") as f:
            shutil.copyfileobj(file.file, f)
        topic.file_path = file_location

    db.commit()
    db.refresh(topic)

    flash(request, f"Topic '{title}' updated successfully!", "info")

    return RedirectResponse(
        url=f"/faculty/course/{topic.course_id}/upload_topic",
        status_code=303
    )

# ---------------------------------
# POST: Delete Topic
# ---------------------------------
@faculty_upload_router.post("/delete-topic/{topic_id}", name="delete_topic")
def delete_topic(topic_id: int, request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch the topic first
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        
        return RedirectResponse(url="/faculty/upload_topic", status_code=303)

    course_id = topic.course_id
    topic_title = topic.title  

    # Delete file if exists
    if topic.file_path and os.path.exists(topic.file_path):
        try:
            os.remove(topic.file_path)
        except Exception as e:
            print(f"Warning: Could not delete file {topic.file_path}: {e}")

    # Delete from DB
    db.delete(topic)
    db.commit()

    # Flash message
    flash(request, f"Topic '{topic.title}' deleted successfully!", "success")

    return RedirectResponse(
        url=f"/faculty/course/{course_id}/upload_topic",
        status_code=303
    )


# ---------------------------------
# GET: View Topic File
# ---------------------------------

@faculty_upload_router.get("/topic/view/{topic_id}", name="view_topic_file")
def view_topic_file(topic_id: int, request: Request, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic or not topic.file_path or not os.path.exists(topic.file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    mime_type, _ = mimetypes.guess_type(topic.file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

   
    return FileResponse(
        path=topic.file_path,
        media_type=mime_type
    )


# ---------------------------------
# GET: View Uploaded Topics (Read-Only)
# ---------------------------------
@faculty_upload_router.get("/course/{course_id}/view-topics", response_class=HTMLResponse, name="view_uploaded_topics")
def view_uploaded_topics(course_id: int, request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.topic_no).all()

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse("faculty/topics.html", {
        "request": request,
        "course": course,
        "topics": topics,
        "flashed": flashed,
    })
