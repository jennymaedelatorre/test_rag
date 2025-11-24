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
@student_quiz_router.get("/quiz/results/{topic_id}", response_class=HTMLResponse, name="quiz_results")
def quiz_results(request: Request, topic_id: int, attempt_id: str = None, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    # --- Fetch Topic ---
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
         raise HTTPException(status_code=404, detail="Topic not found.")

    # --- Fetch Attempt ---
    attempt_query = db.query(StudentQuizAttempt).filter_by(student_id=user_id, topic_id=topic_id)

    if attempt_id:
        attempt = attempt_query.filter_by(id=attempt_id).first()
    else:
        # Fetch the latest attempt (submitted or not)
        attempt = attempt_query.order_by(StudentQuizAttempt.start_time.desc()).first()

    if not attempt:
        raise HTTPException(status_code=404, detail="No quiz attempt found.")

    # --- Determine score and total questions ---
    if not attempt.submitted:
        # User hasn't submitted → show 0/N
        total_questions_count = db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).count()
        score = 0
    else:
        # Submitted → use stored values
        total_questions_count = attempt.total_questions or db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).count()
        score = attempt.score or 0

    # --- Fetch Detailed Answers for Review ---
    answers_data = db.query(StudentAnswer).filter_by(attempt_id=attempt.id).all()
    review_data = []

    for answer in answers_data:
        question = db.query(GeneratedQuestion).filter_by(question_id=answer.question_id).first()
        if not question: 
            continue

        try:
            options = json.loads(question.options_json)
        except json.JSONDecodeError:
            options = []

        user_answer_text = answer.student_answer
        if str(user_answer_text).isdigit() and options:
            try:
                user_index = int(user_answer_text) - 1
                if 0 <= user_index < len(options):
                    user_answer_text = options[user_index]
            except ValueError:
                pass

        review_data.append({
            "question_text": question.question_text,
            "options": options,
            "correct_answer": question.correct_answer,
            "user_answer": user_answer_text,
            "is_correct": (user_answer_text == question.correct_answer),
            "co_tag": question.co_tag
        })

    # --- CO progress & Time ---
    average_co = cilos.get_co_progress_single_attempt(db, user_id, topic.course_id)
    start_time_ph = get_ph_time_from_utc(attempt.start_time)
    end_time_ph = get_ph_time_from_utc(attempt.end_time)

    return templates.TemplateResponse(
        "student/quiz_result.html",
        {
            "request": request,
            "user_full_name": user.full_name,
            "topic": topic,
            "score": score,
            "total": total_questions_count,
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "start_time_ph": start_time_ph,
            "end_time_ph": end_time_ph,
            "average_co": average_co,
            "review_data": review_data
        }
    )


# ==============================
# GET: Review Quiz
# ==============================
@student_quiz_router.get("/quiz/review/{attempt_id}", response_class=HTMLResponse, name="review_quiz")
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
    
    topic = db.query(Topic).filter(Topic.id == attempt.topic_id).first()
    if not topic:
         raise HTTPException(status_code=404, detail="Topic not found.")

    questions = db.query(GeneratedQuestion).filter_by(topic_id=attempt.topic_id).all()
    saved_answers = {str(a.question_id): a for a in attempt.answers}

    review_data = []
    for q in questions:
        answer_record = saved_answers.get(str(q.question_id))
        user_answer_raw = answer_record.student_answer if answer_record else None
        
        try:
            options = json.loads(q.options_json)
        except json.JSONDecodeError:
            options = []

        # Convert numeric answers to text
        user_answer_text = None
        if user_answer_raw:
            if str(user_answer_raw).isdigit() and options:
                try:
                    user_index = int(user_answer_raw) - 1
                    if 0 <= user_index < len(options):
                        user_answer_text = options[user_index]
                except ValueError:
                    user_answer_text = str(user_answer_raw)
            else:
                user_answer_text = str(user_answer_raw)
        
        # Default to "No Answer" if user didn't answer
        if not user_answer_text:
            user_answer_text = "No Answer"

        is_correct = (user_answer_text == q.correct_answer)

        review_data.append({
            "question_text": q.question_text,
            "options": options,
            "correct_answer": q.correct_answer,
            "user_answer": user_answer_text,
            "is_correct": is_correct,
            "co_tag": q.co_tag
        })

    # Always calculate total questions
    total_questions_count = len(questions)
    score = attempt.score if attempt.submitted else 0

    print(review_data)


    return templates.TemplateResponse(
        "student/quiz_review.html",
        {
            "request": request,
            "user_full_name": user.full_name,
            "topic": topic,
            "review_data": review_data,
            "score": score,
            "total": total_questions_count,
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
