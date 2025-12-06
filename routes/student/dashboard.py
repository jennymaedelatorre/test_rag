from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User, StudentAnswer, StudentQuizAttempt, StudentCourseProgress, Topic
from utils.flash import get_flashed_messages
from sqlalchemy.sql.expression import func
import random
from utils.co_progress import compute_co_progress


student_dashboard_router = APIRouter(prefix="/student", tags=["Student"])
templates = Jinja2Templates(directory="templates")


@student_dashboard_router.get("/dashboard", response_class=HTMLResponse)
def student_dashboard(request: Request, db: Session = Depends(get_db)):
    # Login check
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        return RedirectResponse(url="/auth/login", status_code=303)

    # All courses
    courses = db.query(Course).all()
    course_count = len(courses)

    # Pick a random course
    if courses:
        selected_course = random.choice(courses)
    else:
        selected_course = None

    # Quizzes completed by student
    completed_quizzes = (
        db.query(StudentQuizAttempt)
        .filter(StudentQuizAttempt.student_id == student.id)
        .filter(StudentQuizAttempt.submitted == True)
        .count()
    )

    if selected_course:
        total_topics = selected_course.total_topics or 0

        completed_topics = (
            db.query(StudentCourseProgress)
            .join(StudentCourseProgress.topic)
            .filter(StudentCourseProgress.student_id == student.id)
            .filter(Topic.course_id == selected_course.id)
            .filter(StudentCourseProgress.completed == True)
            .count()
        )

        course_progress = round((completed_topics / total_topics) * 100) if total_topics else 0
    else:
        course_progress = 0

    # Pending quizzes
    total_quizzes = sum(course.total_topics for course in courses)
    pending_quizzes = total_quizzes - completed_quizzes

    # Compute CO mastery for selected course
    if selected_course:
        co_progress_dict = compute_co_progress(db, student.id, selected_course.id)
        co_labels = list(co_progress_dict.keys())
        co_values = list(co_progress_dict.values())
    else:
        co_labels, co_values = [], []

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse(
        "student/dashboard.html",
        {
            "request": request,
            "flashed": flashed,
            "student": student,
            "selected_course": selected_course, 
            "course_count": course_count,
            "co_labels": co_labels,
            "co_values": co_values,
            "completed_quizzes": completed_quizzes,
            "course_progress": course_progress,
            "pending_quizzes": pending_quizzes,
            "session": request.session
        }
    )
