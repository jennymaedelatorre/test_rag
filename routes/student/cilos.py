from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from database.session import get_db
from database.models import User, StudentQuizAttempt, StudentAnswer, GeneratedQuestion, Topic, Course, CILO, StudentCourseProgress
from sqlalchemy import Integer, func
from utils.co_progress import compute_co_progress


student_cilos_router = APIRouter()
templates = Jinja2Templates(directory="templates")

low_co_threshold = 60 


# Used for recommendations
def get_topic_co_distribution(db: Session, course_id: int):
    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    distribution = {}

    for topic in topics:
        questions = db.query(GeneratedQuestion).filter(
            GeneratedQuestion.topic_id == topic.id
        ).all()

        if not questions:
            continue

        co_counts = {}
        total = len(questions)

        # Count questions per CO tag
        for q in questions:
            co = q.co_tag
            co_counts[co] = co_counts.get(co, 0) + 1

        # Convert counts to percentages
        distribution[topic.id] = {
            co: round((count / total) * 100)
            for co, count in co_counts.items()
        }

    return distribution



# STUDENT CILOS PAGE (WITH RECOMMENDATIONS)
@student_cilos_router.get("/student/cilos", response_class=HTMLResponse)
def view_cilos_student(request: Request, db: Session = Depends(get_db), page: int = 1):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    courses = db.query(Course).all()
    total_courses = len(courses)
    page = max(1, min(page, total_courses))
    course = courses[page - 1]

    cilos = db.query(CILO).filter(CILO.course_id == course.id).order_by(CILO.cilo_code).all()
    co_progress_dict = compute_co_progress(db, student.id, course.id)

    total_topics = course.total_topics or 10
    completed_topics_count = db.query(StudentCourseProgress).join(StudentCourseProgress.topic)\
        .filter(StudentCourseProgress.student_id == student.id)\
        .filter(StudentCourseProgress.topic.has(course_id=course.id))\
        .filter(StudentCourseProgress.completed == True).count()

    course_progress = round((completed_topics_count / total_topics) * 100) if total_topics else 0
    show_low_co_card = completed_topics_count >= 6

    low_cos = []
    co_recommendations = {}
    if show_low_co_card:
        topic_distribution = get_topic_co_distribution(db, course.id)
        for c in cilos:
            progress = co_progress_dict.get(c.cilo_code, 0)
            if progress < low_co_threshold:
                low_cos.append({
                    "cilo_code": c.cilo_code,
                    "description": c.description,
                    "progress": progress
                })
                primary = []
                fallback = []
                for topic in course.topics:
                    dist = topic_distribution.get(topic.id, {})
                    percent = dist.get(c.cilo_code, 0)
                    topic_data = {"topic_title": topic.title, "percent": percent}
                    if percent >= 40:
                        primary.append(topic_data)
                    elif percent > 0:
                        fallback.append(topic_data)
                co_recommendations[c.cilo_code] = primary if primary else fallback

    cilo_progress_list = [
        {"cilo_code": c.cilo_code, "description": c.description, "progress": co_progress_dict.get(c.cilo_code, 0)}
        for c in cilos
    ]

    return templates.TemplateResponse(
        "student/cilos.html",
        {
            "request": request,
            "user_full_name": student.full_name,
            "course": {
                "course_title": course.title,
                "cilos": cilo_progress_list,
                "low_cos": low_cos,
                "course_progress": course_progress,
                "recommendations": co_recommendations
            },
            "current_page": page,
            "total_pages": total_courses,
            "has_prev": page > 1,
            "has_next": page < total_courses,
            "low_co_threshold": low_co_threshold
        }
    )