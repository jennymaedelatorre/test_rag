from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.models import Topic, GeneratedQuestion, StudentQuizAttempt, StudentAnswer, Course
from database.session import get_db
from utils.flash import flash, get_flashed_messages
from sqlalchemy import func, distinct, cast, Float
from collections import defaultdict
import os


faculty_topics_view_router  = APIRouter(prefix="/faculty/upload", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

# Register custom filter
import json
def from_json(value):
    try:
        return json.loads(value)
    except Exception:
        return {}

templates.env.filters["from_json"] = from_json


# ---------------------------------
# GET: View Uploaded Topics 
# ---------------------------------
@faculty_topics_view_router .get("/course/{course_id}/view-topics", response_class=HTMLResponse, name="view_uploaded_topics")
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

# ==============================
# GEt: View Generated Quiz Route 
# ==================================
@faculty_topics_view_router.get(
    "/topic/{topic_id}/view-quiz", 
    response_class=HTMLResponse, 
    name="view_generated_quiz"
)
def view_generated_quiz(topic_id: int, request: Request, db: Session = Depends(get_db)):
    """Displays all generated questions associated with a specific topic."""
    
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    # Fetch all generated questions for this topic, ordered by question type
    questions = db.query(GeneratedQuestion).filter(
        GeneratedQuestion.topic_id == topic_id
    ).order_by(GeneratedQuestion.question_type).all()


    questions_by_type = defaultdict(list)
    for q in questions:
        type_name = q.question_type.replace('_', ' ').upper()
        questions_by_type[type_name].append(q)
    

    flashed = get_flashed_messages(request)
    
    return templates.TemplateResponse("faculty/topic_quiz_details.html", {
        "request": request,
        "topic": topic,
        "questions_by_type": dict(questions_by_type),
        "questions": questions,
        "flashed": flashed,
    })


# ---  View Students Score Route ---
@faculty_topics_view_router.get(
    "/topic/{topic_id}/view-scores", 
    response_class=HTMLResponse, 
    name="view_students_score"
)
def view_students_score(topic_id: int, request: Request, db: Session = Depends(get_db)):
    """Displays score summaries and attempts for students on a specific topic."""

    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    # Fetch all quiz attempts for this topic
    attempts = db.query(StudentQuizAttempt).filter(
        StudentQuizAttempt.topic_id == topic_id,
        StudentQuizAttempt.submitted == True
    ).all()


    flashed = get_flashed_messages(request)

    return templates.TemplateResponse("faculty/topic_score_summary.html", {
        "request": request,
        "topic": topic,
        "attempts": attempts, 
        "total_attempts": len(attempts),
        "flashed": flashed,
    })

# ---------------------------------
# POST: Delete Topic
# ---------------------------------
@faculty_topics_view_router.post("/delete-topics/{topic_id}", name="delete_topics")
def delete_topic(topic_id: int, request: Request, db: Session = Depends(get_db)):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/auth/login", status_code=303)

    
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
        url=f"/faculty/course/{course_id}/view-topics",
        status_code=303
    )
