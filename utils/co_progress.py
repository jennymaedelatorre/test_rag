from sqlalchemy.orm import Session
from database.models import StudentQuizAttempt, StudentAnswer, Topic


def compute_co_progress(db: Session, student_id: int, course_id: int):
    """
    Computes CO mastery for a student in a given course.
    Reused by dashboard + cilos pages.
    """

    topics = db.query(Topic).filter(Topic.course_id == course_id).all()
    if not topics:
        return {}

    answers = (
        db.query(StudentAnswer)
        .join(StudentQuizAttempt, StudentAnswer.attempt_id == StudentQuizAttempt.id)
        .filter(StudentQuizAttempt.student_id == student_id)
        .filter(StudentQuizAttempt.topic_id.in_([t.id for t in topics]))
        .all()
    )

    if not answers:
        return {}

    co_scores = {}
    co_counts = {}

    for ans in answers:
        co = ans.co_tag or "Unknown"
        co_counts[co] = co_counts.get(co, 0) + 1

        # Correctness check (case-insensitive)
        if ans.student_answer.strip().lower() == ans.correct_answer.strip().lower():
            co_scores[co] = co_scores.get(co, 0) + 1

    # Convert to percentages
    return {
        co: round((co_scores.get(co, 0) / total) * 100)
        for co, total in co_counts.items()
    }
