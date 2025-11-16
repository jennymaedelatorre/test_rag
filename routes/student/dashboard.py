from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User, StudentAnswer, StudentQuizAttempt, StudentCourseProgress
from utils.flash import get_flashed_messages


student_dashboard_router = APIRouter(prefix="/student", tags=["Student"])
templates = Jinja2Templates(directory="templates")

def compute_student_co_progress(db, student_id: int):
    """
    Returns:
        labels: list of CO names, e.g. ["CO1", "CO2"...]
        values: list of mastery percentages, e.g. [80, 65, 92...]
    """

    from sqlalchemy import func, Integer

    results = (
        db.query(
            StudentAnswer.co_tag,
            func.count(StudentAnswer.id).label("total"),
            func.sum(
                (StudentAnswer.student_answer == StudentAnswer.correct_answer).cast(Integer)
            ).label("correct")
        )
        .join(StudentQuizAttempt, StudentAnswer.attempt_id == StudentQuizAttempt.id)
        .filter(StudentQuizAttempt.student_id == student_id)
        .group_by(StudentAnswer.co_tag)
        .all()
    )

    labels = []
    values = []

    for r in results:
        if r.co_tag:
            labels.append(r.co_tag)
            percentage = round((r.correct / r.total) * 100) if r.total else 0
            values.append(percentage)

    return labels, values


@student_dashboard_router.get("/dashboard", response_class=HTMLResponse)
def student_dashboard(request: Request, db: Session = Depends(get_db)):
    """Display the student dashboard with real CO performance."""
    
    # LOGIN CHECK
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        return RedirectResponse(url="/auth/login", status_code=303)

    courses = db.query(Course).all()
    course_count = len(courses)

    completed_quizzes = (
        db.query(StudentQuizAttempt)
        .filter(StudentQuizAttempt.student_id == user_id)
        .filter(StudentQuizAttempt.submitted == True)
        .count()
    )

    # Count completed topics for this student
    course_progress_data = []

    for course in courses:
        completed_topics = (
            db.query(StudentCourseProgress)
            .filter(StudentCourseProgress.student_id == student.id)
            .join(StudentCourseProgress.topic)
            .filter(StudentCourseProgress.completed == True)
            .filter(StudentCourseProgress.topic.has(course_id=course.id))
            .count()
        )

        overall_progress = round((completed_topics / course.total_topics) * 100) if course.total_topics else 0

        course_progress_data.append({
            "course": course,
            "progress": overall_progress
        })

    flashed = get_flashed_messages(request)

    # CO PROGRESS
    co_labels, co_values = compute_student_co_progress(db, student.id)

    return templates.TemplateResponse(
        "student/dashboard.html",
        {
            "request": request,
            "flashed": flashed,
            "student": student,
            "courses": courses,
            "course_count": course_count,
            "co_labels": co_labels,
            "co_values": co_values,
            "completed_quizzes": completed_quizzes,
            "course_progress_data": course_progress_data,
            "session": request.session
        }
    )