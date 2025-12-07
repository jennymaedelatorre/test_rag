from sqlalchemy.orm import Session
from database.models import StudentQuizAttempt, StudentAnswer, Topic, GeneratedQuestion

def compute_co_progress(db: Session, student_id: int, course_id: int):
    
    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    if not topics:
        return {}

    topic_ids = [t.id for t in topics]

    answers = (
        db.query(StudentAnswer)
        .join(StudentQuizAttempt, StudentAnswer.attempt_id == StudentQuizAttempt.id)
        .filter(StudentQuizAttempt.student_id == student_id)
        .filter(
            StudentAnswer.question.has(GeneratedQuestion.topic_id.in_(topic_ids))
        )
        .all()
    )

    if not answers:
        return {}

    co_scores = {}
    co_counts = {}

    for ans in answers:
        co = ans.co_tag or "Unknown"
        co_counts[co] = co_counts.get(co, 0) + 1

        if ans.student_answer.strip().lower() == ans.question.correct_answer.strip().lower():
            co_scores[co] = co_scores.get(co, 0) + 1

    return {co: round((co_scores.get(co, 0) / total) * 100) for co, total in co_counts.items()}
