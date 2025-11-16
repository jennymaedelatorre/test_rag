from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from sqlalchemy import func

from database.session import get_db
from database.models import Course, User, Topic , GeneratedQuestion  
from utils.flash import get_flashed_messages
from routes.faculty.cilos import get_course_and_student_co_progress
   

faculty_dashboard_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

@faculty_dashboard_router.get("/dashboard", response_class=HTMLResponse)
def faculty_dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)
    user_id = int(user_id)

    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)
    user_full_name = user.full_name

    # Courses handled by this faculty
    courses = db.query(Course).filter(Course.instructor_id == user_id).all()
    course_count = len(courses)

    # Topics uploaded by this faculty
    topics = db.query(Topic).join(Course, Course.id == Topic.course_id)\
                .filter(Course.instructor_id == user_id)\
                .order_by(Topic.created_at.desc()).all()
    topic_count = len(topics)
    topic_ids = [t.id for t in topics]

    # Count generated questions per topic
    questions_count = dict(
        db.query(GeneratedQuestion.topic_id, func.count(GeneratedQuestion.question_id))
        .filter(GeneratedQuestion.topic_id.in_(topic_ids))
        .group_by(GeneratedQuestion.topic_id)
        .all()
    )


    # Prepare topics data for template
    topics_data = []
    for t in topics:
        topics_data.append({
            "id": t.id,
            "title": t.title,
            "topic_no": t.topic_no,
            "uploaded_at": t.created_at,
            "questions_count": questions_count.get(t.id, 0),
            "course": t.course.title
        })

    # CO progress per course
    dashboard_course_data = []
    for course in courses:
        per_student_co, course_co_avg = get_course_and_student_co_progress(db, course.id)
        dashboard_course_data.append({
            "course": course,
            "co_avg": course_co_avg
        })

    # Recent activity: uploaded topics + generated questions
    recent_activities = []

    for t in topics:
        recent_activities.append({
            "type": "upload_topic",
            "message": f"Uploaded topic '{t.title}' for Course '{t.course.title}'",
            "timestamp": t.created_at
        })

    generated_questions = db.query(GeneratedQuestion)\
                            .filter(GeneratedQuestion.user_id == user.id)\
                            .order_by(GeneratedQuestion.created_at.desc())\
                            .limit(10).all()
    for q in generated_questions:
        recent_activities.append({
            "type": "create_question",
            "message": f"Generated question for topic '{q.source_topic.title}'",
            "timestamp": q.created_at
        })

    # Sort recent activities by timestamp descending
    recent_activities = sorted(recent_activities, key=lambda x: x["timestamp"], reverse=True)

    recent_activities = recent_activities[:10]

    # Count all registered students
    student_count = db.query(User).filter(User.role == "student").count()

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse(
        "faculty/dashboard.html",
        {
            "request": request,
            "flashed": flashed,
            "courses": courses,
            "user_full_name": user_full_name,
            "course_count": course_count,
            "student_count": student_count,
            "topic_count": topic_count,
            "dashboard_course_data": dashboard_course_data,
            "topics_data": topics_data,
            "recent_activities": recent_activities,
            "session": request.session
        }
    )