from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import uuid
import logging
import tempfile
import mimetypes
from pathlib import Path
import shutil
from typing import Optional

from database.session import get_db
from database.models import Topic, Course, User
from utils.flash import flash, get_flashed_messages
from core.processing import load_and_chunk, get_or_create_vector_store, calculate_file_hash
from database.check_user_role import check_user_role

# ----------------------------
# Router Setup
# ----------------------------
faculty_upload_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")
templates.env.globals["get_flashed_messages"] = get_flashed_messages

# ----------------------------
# Directories
# ----------------------------
UPLOAD_DIR = Path("uploads/topics")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = Path("./faiss_cache")
CACHE_DIR.mkdir(exist_ok=True)

TEMP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "mcq_uploads"
TEMP_UPLOAD_DIR.mkdir(exist_ok=True)

# ----------------------------
# Helper: User Dependency
# ----------------------------
def get_current_faculty(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

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

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail=f"Course ID {course_id} not found.")

    topics = db.query(Topic).filter(Topic.course_id == course_id).order_by(Topic.topic_no).all()
    flashed = get_flashed_messages(request)

    return templates.TemplateResponse("faculty/upload_topic.html", {
        "request": request,
        "course_id": course_id,
        "topics": topics,
        "user_full_name": user.full_name,
        "flashed": flashed,
    })

# ---------------------------------
# POST: Upload Topic
# ---------------------------------
@faculty_upload_router.post("/course/{course_id}/upload_topic", name="upload_topic")
async def upload_topic(
    course_id: int,
    request: Request,
    title: str = Form(...),
    topic_no: int = Form(...),
    subtitle: str = Form(""),
    file: UploadFile = File(...),
    user_id: int = Depends(check_user_role),
    db: Session = Depends(get_db)
):
    """Handles topic creation + PDF indexing"""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    temp_file_path = None  

    try:
        # Validate file type
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

        # Prepare paths
        original_filename = Path(file.filename).name
        server_file_path = UPLOAD_DIR / original_filename

        # Count existing topics for this course
        topic_count = db.query(Topic).filter(Topic.course_id == course_id).count()
        if topic_count >= 10:
            flash(
                request,
                f"Upload failed: This course has reached the maximum limit of 10 topics. You cannot add more.",
                category="warning"
            )
            return RedirectResponse(
                url=f"/faculty/course/{course_id}/upload_topic",
                status_code=303
            )


        # Check for duplicates (topic_no or file_name)
        existing_topic = db.query(Topic).filter(
            Topic.course_id == course_id,
            ((Topic.topic_no == topic_no) | (Topic.file_name == original_filename))
        ).first()

        if existing_topic:
            reason = []
            if existing_topic.topic_no == topic_no:
                reason.append(f"Topic No. {topic_no}")
            if existing_topic.file_name == original_filename:
                reason.append(f"file '{original_filename}'")

            flash(
                request,
                f"Upload failed: You already uploaded {', and '.join(reason)}.",
                category="warning"
            )
            return RedirectResponse(
                url=f"/faculty/course/{course_id}/upload_topic",
                status_code=303
            )

        # Save file temporarily for indexing
        temp_file_path = TEMP_UPLOAD_DIR / f"{uuid.uuid4()}-{original_filename}"
        file_content = await file.read()
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)

        # Generate file hash and FAISS index
        file_hash = calculate_file_hash(str(temp_file_path))
        document_uuid = str(uuid.uuid4())
        index_path = CACHE_DIR / file_hash

        if not index_path.exists():
            docs = load_and_chunk(str(temp_file_path), document_id=document_uuid)
            _, faiss_action = get_or_create_vector_store(str(index_path), docs=docs)
        else:
            faiss_action = "loaded_from_cache"

        # Move file from temp to permanent storage
        shutil.move(temp_file_path, server_file_path)

        # Save to database
        new_topic = Topic(
            course_id=course_id,
            topic_no=topic_no,
            title=title,
            subtitle=subtitle,
            file_name=original_filename,
            file_path=str(server_file_path),
            file_hash=file_hash,
            document_uuid=document_uuid,
            uploaded_by=user_id
        )
        db.add(new_topic)
        db.commit()
        db.refresh(new_topic)

        flash(
            request,
            f"Topic '{title}' uploaded and indexed successfully! ({faiss_action})",
            category="success"
        )

        return RedirectResponse(
            url=f"/faculty/course/{course_id}/upload_topic",
            status_code=303
        )

    except Exception as e:
        db.rollback()
        logging.error(f"❌ Upload topic failed: {e}", exc_info=True)
        flash(request, f"Upload failed: {str(e)}", category="danger")
        return RedirectResponse(
            url=f"/faculty/course/{course_id}/upload_topic",
            status_code=303
        )

    finally:
        if temp_file_path and temp_file_path.exists():
            os.remove(temp_file_path)



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
# GET: View Uploaded Topics 
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
