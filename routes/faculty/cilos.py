from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates


from database.session import get_db
from database.models import User, Course, CILO, StudentAnswer, Topic, StudentQuizAttempt, StudentCourseProgress

faculty_cilos_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

def get_course_and_student_co_progress(db: Session, course_id: int):
    """
    Returns:
      - per-student CO percentages
      - course-average CO percentages
    Assumes each student has only one attempt per topic.
    """
    # Get all topics in the course
    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    topic_ids = [t.id for t in topics]

    if not topic_ids:
        return {}, {}

    # Get all answers for these topics (only single attempt per student)
    answers = (
        db.query(StudentAnswer)
        .join(StudentQuizAttempt, StudentAnswer.attempt_id == StudentQuizAttempt.id)
        .filter(StudentQuizAttempt.topic_id.in_(topic_ids))
        .all()
    )

    if not answers:
        return {}, {}

    # Organize answers by student
    student_answers = {}
    for ans in answers:
        student_answers.setdefault(ans.attempt.student_id, []).append(ans)

    # Calculate per-student CO progress
    per_student_co = {}
    all_co_totals = {}   # For course-average calculation
    all_co_corrects = {}

    for student_id, ans_list in student_answers.items():
        co_counts = {}
        co_corrects = {}

        for ans in ans_list:
            co = ans.co_tag
            if not co:
                continue
            co_counts[co] = co_counts.get(co, 0) + 1
            if ans.student_answer and ans.student_answer.strip().lower() == ans.correct_answer.strip().lower():
                co_corrects[co] = co_corrects.get(co, 0) + 1

            # Aggregate for course-average
            all_co_totals[co] = all_co_totals.get(co, 0) + 1
            all_co_corrects[co] = all_co_corrects.get(co, 0) + (1 if ans.student_answer and ans.student_answer.strip().lower() == ans.correct_answer.strip().lower() else 0)

        # Compute % for this student
        per_student_co[student_id] = {co: round((co_corrects.get(co, 0) / co_counts[co]) * 100) for co in co_counts}

    # Compute course-average % per CO
    course_co_avg = {co: round((all_co_corrects.get(co, 0) / all_co_totals[co]) * 100) for co in all_co_totals}

    return per_student_co, course_co_avg


@faculty_cilos_router.get("/cilos", response_class=HTMLResponse)
def view_cilos_faculty(request: Request, db: Session = Depends(get_db)):
    # LOGIN CHECK
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    faculty = db.query(User).filter(User.id == user_id).first()
    if not faculty or faculty.role != "faculty":
        return RedirectResponse(url="/auth/login", status_code=303)

    courses = db.query(Course).filter(Course.instructor_id == faculty.id).all()
    students = db.query(User).filter(User.role == "student").all()
    
    courses_data = []

    for course in courses:
        per_student_co, course_co_avg = get_course_and_student_co_progress(db, course.id)

        # Intervention logic
        intervention_students = []
        total_topics = getattr(course, "total_topics", 10)  

        for student in students:
            completed_topics = (
                db.query(StudentCourseProgress)
                .join(StudentCourseProgress.topic)
                .filter(StudentCourseProgress.student_id == student.id)
                .filter(StudentCourseProgress.topic.has(course_id=course.id))
                .filter(StudentCourseProgress.completed == True)
                .count()
            )
            course_progress = round((completed_topics / total_topics) * 100)

            student_cos = per_student_co.get(student.id, {})
            low_cos = [co for co, val in student_cos.items() if val < 60]

            # Only include students with low COs
            if low_cos:
                intervention_students.append({
                    "student": student,
                    "course_progress": course_progress,
                    "low_cos": low_cos
                })

        courses_data.append({
            "course": course,
            "cilos": course.cilos,
            "co_avg": course_co_avg,
            "per_student_co": per_student_co,
            "intervention_students": intervention_students
        })

    return templates.TemplateResponse(
        "faculty/cilos.html",
        {
            "request": request,
            "faculty": faculty,
            "courses_data": courses_data, 
            "students": students,
        }
    )