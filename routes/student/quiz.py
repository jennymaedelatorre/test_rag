from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.session import get_db
from database.models import (
    User,
    Topic,
    GeneratedQuestion,
    StudentQuizAttempt,
    StudentAnswer,
    StudentCOPerformance,
    StudentCourseProgress
)
import json
from datetime import datetime, timedelta
from utils.time import get_ph_time_from_utc
from collections import defaultdict
from routes.student import cilos
import logging
from utils.co_progress import compute_co_progress

student_quiz_router = APIRouter(prefix="/student", tags=['student'])
templates = Jinja2Templates(directory="templates")

MAX_ATTEMPTS = 1 


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
        if attempt.submitted:
            return RedirectResponse(url=f"/student/quiz/results/{topic_id}?attempt_id={attempt.id}")
        return RedirectResponse(url=f"/student/quiz/resume/{topic_id}?attempt_id={attempt.id}")


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

    
    # Define which types require options to be rendered (MCQ, True/False)
    OPTION_BASED_TYPES = {"mcq", "true_false"} 

    for q in questions:
        q_type = q.question_type.lower() if q.question_type else 'mcq'
        
        try:
            options_list = json.loads(q.options_json)
        except (json.JSONDecodeError, TypeError):
            options_list = []
            
        quiz_data.append({
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "question_type": q_type,
            "options": options_list if q_type in OPTION_BASED_TYPES else [],
        })

        # Check if the quiz contains any identification questions
        has_identification = any(q['question_type'] == 'identification' for q in quiz_data)

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
            "end_time_ph": end_time_ph.isoformat(),
            "has_identification": has_identification
        }
    )


# ==============================
# POST: Quiz SUBMISSION
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

    attempt = db.query(StudentQuizAttempt).filter_by(id=attempt_id, student_id=user_id, topic_id=topic_id).first()
    if not attempt:
        raise HTTPException(status_code=403, detail="No active quiz attempt found.")

    if datetime.utcnow() > attempt.end_time:
        raise HTTPException(status_code=403, detail="Time expired. You cannot submit.")

    # Clear existing answers
    db.query(StudentAnswer).filter_by(attempt_id=attempt_id).delete()
    db.commit()

    # Fetch questions
    questions = db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).all()
    total = len(questions)
    score = 0
    
    
    AUTOGRADED_TYPES = ["mcq", "true_false", "identification"]

    # Save answers 
    for q in questions:
        q_type = q.question_type.lower() if q.question_type else 'mcq' 
        correct_answer_normalized = q.correct_answer.strip().lower() if q.correct_answer else ""  
        user_answer = answers.get(str(q.question_id), "").strip() 
        user_answer_normalized = user_answer.lower()
        
        is_correct = False

        if q_type in AUTOGRADED_TYPES:   
            if user_answer_normalized == correct_answer_normalized:
                is_correct = True
            
            # --- check Alternatives for Identification ---
            elif q_type == "identification" and q.alternative_answers_json:
                try:
                    # Load and normalize the alternatives list
                    alternatives = json.loads(q.alternative_answers_json)
                    alternatives_normalized = [a.strip().lower() for a in alternatives]
                    
                    if user_answer_normalized in alternatives_normalized:
                        is_correct = True
                except json.JSONDecodeError:
                    logging.warning(f"Malformated alternative_answers_json for QID: {q.question_id}")
            
        
        # Record the student's attempt
        answer_record = StudentAnswer(
            attempt_id=attempt_id,
            question_id=q.question_id,
            question_type=q_type,
            question_text=q.question_text,
            student_answer=user_answer,
            correct_answer=q.correct_answer.strip() if q.correct_answer else "",
            co_tag=q.co_tag
        )
        db.add(answer_record)
        
        if is_correct:
            score += 1

    # Update the overall attempt score
    attempt.score = score
    attempt.total_questions = total
    attempt.submitted = True
    db.commit()

    # Mark topic as completed 
    progress = db.query(StudentCourseProgress).filter_by(student_id=user_id, topic_id=topic_id).first()
    if not progress:
        progress = StudentCourseProgress(
            student_id=user_id,
            topic_id=topic_id,
            viewed=True,
            viewed_at=datetime.utcnow(),
            completed=True,
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
        user_answer_normalized = user_answer.lower()
        correct_answer_normalized = q.correct_answer.strip().lower() if q.correct_answer else ""
        q_type = q.question_type.lower() if q.question_type else 'mcq'
        
        
        is_correct_for_co = False
        if q_type in AUTOGRADED_TYPES:
            
            # --- Base Check ---
            if user_answer_normalized == correct_answer_normalized:
                is_correct_for_co = True
            
            # --- Check Alternatives for Identification  ---
            elif q_type == "identification" and q.alternative_answers_json:
                try:
                    alternatives = json.loads(q.alternative_answers_json)
                    alternatives_normalized = [a.strip().lower() for a in alternatives]
                    
                    if user_answer_normalized in alternatives_normalized:
                        is_correct_for_co = True
                except json.JSONDecodeError:
                    pass 
            

        if is_correct_for_co:
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

    return JSONResponse({"status": "success", "score": score, "total": total})

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

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    attempt_query = db.query(StudentQuizAttempt).filter_by(student_id=user_id, topic_id=topic_id)
    attempt = attempt_query.filter_by(id=attempt_id).first() if attempt_id else attempt_query.order_by(StudentQuizAttempt.start_time.desc()).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="No quiz attempt found.")

    total_questions_count = attempt.total_questions or db.query(GeneratedQuestion).filter(GeneratedQuestion.topic_id == topic_id).count()
    score = attempt.score or 0

    # Fetch detailed answers
    answers_data = db.query(StudentAnswer).filter_by(attempt_id=attempt.id).all()
    review_data = []
    for answer in answers_data:
        question = db.query(GeneratedQuestion).filter_by(question_id=answer.question_id).first()
        if not question:
            continue
        try:
            options = json.loads(question.options_json)
        except (json.JSONDecodeError, TypeError):
            options = []

        user_answer_text = answer.student_answer or "No Answer"
        if str(user_answer_text).isdigit() and options:
            try:
                idx = int(user_answer_text) - 1
                if 0 <= idx < len(options):
                    user_answer_text = options[idx]
            except ValueError:
                pass

        review_data.append({
            "question_text": question.question_text,
            "question_type": question.question_type,
            "options": options if question.question_type == "mcq" else [],
            "correct_answer": question.correct_answer,
            "user_answer": user_answer_text,
            "is_correct": (user_answer_text.lower() == question.correct_answer.lower()),
            "co_tag": question.co_tag
        })

    average_co = cilos.compute_co_progress(db, user_id, topic.course_id)
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
@student_quiz_router.get("/quiz/review/{attempt_id}", response_class=HTMLResponse)
def review_quiz(request: Request, attempt_id: str, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    attempt = db.query(StudentQuizAttempt).filter_by(id=attempt_id, student_id=user_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    topic = db.query(Topic).filter_by(id=attempt.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")

    # Fetch original questions and student answers
    questions = db.query(GeneratedQuestion).filter_by(topic_id=attempt.topic_id).all()
    saved_answers = {str(a.question_id): a for a in attempt.answers}

    
    OPTION_BASED_TYPES = {"mcq", "true_false"}
    review_data = []

    for q in questions:
        q_type = q.question_type.lower()
        answer_record = saved_answers.get(str(q.question_id))
        
        user_answer_raw = "No Answer"
        is_correct = False
        
        if answer_record:
            user_answer_raw = answer_record.student_answer.strip() if answer_record.student_answer else "No Answer"

        if user_answer_raw != "No Answer":
            user_normalized = user_answer_raw.lower()
            correct_normalized = q.correct_answer.strip().lower() if q.correct_answer else ""

            # Base check
            is_correct = (user_normalized == correct_normalized)

            # Alternative answers check
            if not is_correct and q.question_type.lower() == "identification" and q.alternative_answers_json:
                try:
                    alternatives = json.loads(q.alternative_answers_json)
                    alternatives_normalized = [a.strip().lower() for a in alternatives]

                    if user_normalized in alternatives_normalized:
                        is_correct = True

                except json.JSONDecodeError:
                    pass

        try:
            options = json.loads(q.options_json)
        except (json.JSONDecodeError, TypeError):
            options = []

        review_data.append({
            "question_text": q.question_text,
            "question_type": q_type,
            "options": options if q_type in OPTION_BASED_TYPES else [],
            "correct_answer": q.correct_answer.strip() if q.correct_answer else "",
            "user_answer": user_answer_raw,
            "is_correct": is_correct,
            "co_tag": q.co_tag
        })

    total_questions_count = len(questions)
    score = attempt.score if attempt.submitted else 0

    return templates.TemplateResponse(
        "student/quiz_review.html",
        {
            "request": request,
            "user_full_name": attempt.student.full_name,
            "topic": topic,
            "review_data": review_data,
            "score": score,
            "total": total_questions_count,
        }
    )