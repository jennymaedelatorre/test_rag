from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.session import get_db
from database.models import User, Topic, GeneratedQuestion, StudentQuizAttempt, StudentAnswer, StudentCOPerformance, StudentCourseProgress
import json
from datetime import datetime
from utils.time import get_ph_time_from_utc
from collections import defaultdict
from routes.student import cilos

student_quiz_router = APIRouter(prefix="/student", tags=['student'])
templates = Jinja2Templates(directory="templates")

MAX_ATTEMPTS = 1  # Only 1 attempt per student per topic

# ==============================
# GET: Quiz page
# ==============================
@student_quiz_router.get("/quiz/topic/{topic_id}", response_class=HTMLResponse)
def get_quiz_for_student(request: Request, topic_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Quiz Topic not found.")

    # Check if student already has an attempt
    attempt = db.query(StudentQuizAttempt).filter_by(student_id=user_id, topic_id=topic_id).first()

    if attempt:
        # Already attempted, redirect to results
        return RedirectResponse(url=f"/student/quiz/results/{topic_id}?attempt_id={attempt.id}")

    # Create new attempt
    attempt = StudentQuizAttempt(student_id=user_id, topic_id=topic_id, attempt_number=1)
    attempt.set_end_time(15) 
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # Convert end time to PH time
    end_time_ph = get_ph_time_from_utc(attempt.end_time)

    # Fetch questions
    questions = db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).all()
    quiz_data = []
    for q in questions:
        try:
            options_list = json.loads(q.options_json)
        except json.JSONDecodeError:
            options_list = []
        quiz_data.append({
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "options": options_list,
        })

    return templates.TemplateResponse(
        "student/quiz_view.html",
        {
            "request": request,
            "topic_title": topic.title,
            "topic_subtitle": topic.subtitle,
            "questions": quiz_data,
            "topic_id": topic_id,
            "attempt_id": attempt.id,
            "end_time": attempt.end_time.isoformat() + "Z",
            "end_time_ph": end_time_ph.isoformat()
        }
    )


# ==============================
# POST: Quiz submission
# ==============================
@student_quiz_router.post("/quiz/submit")
async def submit_quiz(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    payload = await request.json()
    topic_id = payload.get("topic_id")
    attempt_id = payload.get("attempt_id")
    answers = payload.get("answers")

    if not topic_id or not answers or not attempt_id:
        return JSONResponse({"status": "error", "detail": "Missing required data"}, status_code=400)

    # Get the single attempt
    attempt = db.query(StudentQuizAttempt).filter_by(id=attempt_id, student_id=user_id, topic_id=topic_id).first()
    if not attempt:
        raise HTTPException(status_code=403, detail="No active quiz attempt found.")

    # Check time limit
    if datetime.utcnow() > attempt.end_time:
        raise HTTPException(status_code=403, detail="Time expired. You cannot submit.")

    # Clear existing answers if any
    db.query(StudentAnswer).filter_by(attempt_id=attempt_id).delete()
    db.commit()

    # Fetch questions
    questions = db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).all()
    total = len(questions)
    score = 0

    # Save answers and calculate score
    for q in questions:
        user_answer = answers.get(str(q.question_id), "").strip()
        answer_record = StudentAnswer(
            attempt_id=attempt_id,
            question_id=q.question_id,
            question_text=q.question_text,
            student_answer=user_answer,
            correct_answer=q.correct_answer.strip(),
            co_tag=q.co_tag
        )
        db.add(answer_record)
        if user_answer.lower() == q.correct_answer.strip().lower():
            score += 1

    attempt.score = score
    attempt.total_questions = total
    attempt.submitted = True
    db.commit()

    # -----------------------------
    # Mark Topic as Completed
    # -----------------------------
    progress = db.query(StudentCourseProgress).filter_by(student_id=user_id, topic_id=topic_id).first()
    if not progress:
        progress = StudentCourseProgress(
            student_id=user_id,
            topic_id=topic_id,
            viewed=True,  
            viewed_at=datetime.utcnow(),
            completed=True,  # mark completed after submitting quiz
            completed_at=datetime.utcnow()
        )
        db.add(progress)
    else:
        progress.completed = True
        progress.completed_at = datetime.utcnow()
        if not progress.viewed:
            progress.viewed = True
            progress.viewed_at = datetime.utcnow()
    db.commit()

    # Save CO performance
    db.query(StudentCOPerformance).filter_by(attempt_id=attempt_id).delete()
    co_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for q in questions:
        co = q.co_tag
        co_stats[co]["total"] += 1
        user_answer = answers.get(str(q.question_id), "").strip()
        if user_answer.lower() == q.correct_answer.strip().lower():
            co_stats[co]["correct"] += 1

    for co_tag, stats in co_stats.items():
        percentage = (stats["correct"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        co_perf = StudentCOPerformance(
            student_id=user_id,
            topic_id=topic_id,
            attempt_id=attempt_id,
            co_tag=co_tag,
            total_questions=stats["total"],
            correct_answers=stats["correct"],
            percentage=percentage
        )
        db.add(co_perf)

    db.commit()
    return {"status": "success", "score": score, "total": total}


# ==============================
# GET: Quiz results page
# ==============================
@student_quiz_router.get("/quiz/results/{topic_id}", response_class=HTMLResponse)
def quiz_results(request: Request, topic_id: int, attempt_id: str = None, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch the single attempt
    attempt = None
    if attempt_id:
        attempt = db.query(StudentQuizAttempt).filter_by(id=attempt_id, student_id=user_id, topic_id=topic_id).first()
    if not attempt:
        attempt = db.query(StudentQuizAttempt).filter_by(student_id=user_id, topic_id=topic_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="No quiz attempt found.")

    # CO progress
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    average_co = cilos.get_co_progress_single_attempt(db, user_id, topic.course_id)

    start_time_ph = get_ph_time_from_utc(attempt.start_time)
    end_time_ph = get_ph_time_from_utc(attempt.end_time)

    return templates.TemplateResponse(
        "student/quiz_result.html",
        {
            "request": request,
            "user_full_name": user.full_name,
            "topic_id": topic_id,
            "score": attempt.score,
            "total": attempt.total_questions,
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "start_time_ph": start_time_ph,
            "end_time_ph": end_time_ph,
            "average_co": average_co
        }
    )


# ==============================
# GET: Review Quiz
# ==============================
@student_quiz_router.get("/quiz/review/{attempt_id}", response_class=HTMLResponse)
def review_quiz(request: Request, attempt_id: str, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    attempt = db.query(StudentQuizAttempt).filter_by(id=attempt_id, student_id=user_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    questions = db.query(GeneratedQuestion).filter_by(topic_id=attempt.topic_id).all()
    saved_answers = {str(a.question_id): a.student_answer for a in attempt.answers}

    review_data = []
    for q in questions:
        review_data.append({
            "question_text": q.question_text,
            "options": json.loads(q.options_json),
            "correct_answer": q.correct_answer,
            "user_answer": saved_answers.get(str(q.question_id), "No Answer"),
            "co_tag": q.co_tag
        })

    return templates.TemplateResponse(
        "student/quiz_review.html",
        {
            "request": request,
            "user_full_name": user.full_name,
            "review_data": review_data,
            "score": attempt.score,
            "total": attempt.total_questions,
        }
    )

# GET : Quiz attemp limit 
@student_quiz_router.get("/quiz/attempts/{topic_id}", response_class=HTMLResponse)
def quiz_attempts_page(request: Request, topic_id: int, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    # Fetch all attempts for this student for this topic
    attempts = db.query(StudentQuizAttempt).filter_by(student_id=user_id, topic_id=topic_id).order_by(StudentQuizAttempt.attempt_number).all()

    if not attempts:
        # No attempts yet, redirect to start quiz
        return RedirectResponse(url=f"/student/quiz/topic/{topic_id}")

    # Convert start times to PH timezone
    for attempt in attempts:
        attempt.start_time_ph = get_ph_time_from_utc(attempt.start_time)

    return templates.TemplateResponse(
        "student/quiz_attempt_limit.html",
        {
            "request": request,
            "user_full_name": student.full_name,
            "topic": topic,
            "attempts": attempts,
            "max_attempts": MAX_ATTEMPTS,
            "attempt_id": attempts[-1].id  
        }
    )
