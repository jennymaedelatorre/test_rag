from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from database.session import get_db
from database.models import User, StudentQuizAttempt, StudentAnswer, GeneratedQuestion, Topic, Course, CILO, StudentCourseProgress
from sqlalchemy import Integer, func

student_cilos_router = APIRouter()
templates = Jinja2Templates(directory="templates")

low_co_threshold = 60 


# -----------------------------------------------------------
# TOPIC CO DISTRIBUTION BASED ON QUIZ QUESTIONS
# -----------------------------------------------------------
# Used for recommendations.
def get_topic_co_distribution(db: Session, course_id: int):
    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    distribution = {}

    for topic in topics:
        # Get all questions for the topic
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


# -----------------------------------------------------------
# CO PROGRESS PER STUDENT BASED ON QUIZ ANSWERS
# -----------------------------------------------------------
# Calculates the student's mastery percentage for each CILO (CO)
def get_co_progress_single_attempt(db: Session, student_id: int, course_id: int):

    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    if not topics:
        return {}

    # Query all student answers for the course
    answers = (
        db.query(StudentAnswer)
        .join(StudentQuizAttempt, StudentAnswer.attempt_id == StudentQuizAttempt.id)
        .filter(StudentQuizAttempt.student_id == student_id)
        .filter(StudentQuizAttempt.topic_id.in_([t.id for t in topics]))
        .all()
    )

    if not answers:
        return {}

    co_scores = {}  # Correct answers count
    co_counts = {}  # Total attempts count

    for ans in answers:
        co = ans.co_tag
        co_counts[co] = co_counts.get(co, 0) + 1

        # Check for correctness
        if ans.student_answer and ans.student_answer.strip().lower() == ans.correct_answer.strip().lower():
            co_scores[co] = co_scores.get(co, 0) + 1

    # Calculate percentage progress for each CO
    return {co: round((co_scores.get(co, 0) / co_counts[co]) * 100) for co in co_counts}


# -----------------------------------------------------------
# STUDENT CILOS PAGE (WITH RECOMMENDATIONS)
# -----------------------------------------------------------
# display student CILO progress and topic recommendations.
@student_cilos_router.get("/student/cilos", response_class=HTMLResponse)
def view_cilos_student(request: Request, db: Session = Depends(get_db)):
    # Authentication check
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    courses = db.query(Course).all()
    courses_data = []

    for course in courses:

        cilos = db.query(CILO).filter(CILO.course_id == course.id).all()
        # Student CO mastery percentages
        co_progress_dict = get_co_progress_single_attempt(
            db, student_id=student.id, course_id=course.id
        )

        # CO distribution in topics for recommendation logic
        topic_distribution = get_topic_co_distribution(db, course.id)

        low_cos = []
        co_recommendations = {}

        for c in cilos:
            progress = co_progress_dict.get(c.cilo_code, 0)

            if progress < low_co_threshold:

                # Identify CILOs with low progress
                low_cos.append({
                    "cilo_code": c.cilo_code,
                    "description": c.description,
                    "progress": progress
                })

                # BUILD RECOMMENDATIONS (Find relevant topics for this low CO)
                recommended_topics = []
                for topic in course.topics:
                    dist = topic_distribution.get(topic.id, {})
                    co_percent = dist.get(c.cilo_code, 0)

                    # Recommend topic if it contains >= 40% questions related to the low CO
                    if co_percent >= 40:
                        recommended_topics.append({
                            "topic_title": topic.title,
                            "percent": co_percent
                        })

                co_recommendations[c.cilo_code] = recommended_topics

        # Calculate student's overall course completion progress
        total_topics = getattr(course, "total_topics", 10)
        completed_topics = (
            db.query(StudentCourseProgress)
            .join(StudentCourseProgress.topic)
            .filter(StudentCourseProgress.student_id == student.id)
            .filter(StudentCourseProgress.topic.has(course_id=course.id))
            .filter(StudentCourseProgress.completed == True)
            .count()
        )
        course_progress = round((completed_topics / total_topics) * 100)

        # Prepare CILO list for UI
        cilo_progress_list = [
            {
                "cilo_code": c.cilo_code,
                "description": c.description,
                "progress": co_progress_dict.get(c.cilo_code, 0)
            }
            for c in cilos
        ]

        # Aggregate course data
        courses_data.append({
            "course_title": course.title,
            "cilos": cilo_progress_list,
            "low_cos": low_cos,
            "course_progress": course_progress,
            "recommendations": co_recommendations,
        })

    # Render the HTML response
    return templates.TemplateResponse(
        "student/cilos.html",
        {
            "request": request,
            "user_full_name": student.full_name,
            "courses_data": courses_data,
            "low_co_threshold": low_co_threshold
        }
    )