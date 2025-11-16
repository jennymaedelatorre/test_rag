from sqlalchemy.orm import Session
from database.models import StudentTopicProgress, Topic, Course, User

def get_student_course_progress(db: Session, course_id: int, student_id: int, total_topics: int = 10):
    """
    Returns the student's progress for a given course in percentage.
    Progress is calculated based on how many topics are completed or viewed.
    If a topic is completed or viewed, it counts toward progress.
    """
    # Get all topic progress for this student in this course
    topics_progress = (
        db.query(StudentTopicProgress)
        .join(Topic, StudentTopicProgress.topic_id == Topic.id)
        .filter(Topic.course_id == course_id, StudentTopicProgress.student_id == student_id)
        .all()
    )

    completed = sum(1 for t in topics_progress if t.completed)
    viewed = sum(1 for t in topics_progress if t.viewed)

    # If no progress record yet, viewed/completed counts are 0
    progress_percentage = ((completed + viewed) / total_topics) * 100
    progress_percentage = min(progress_percentage, 100)  # cap at 100%

    return {
        "progress_percentage": round(progress_percentage, 2),
        "completed_topics": completed,
        "viewed_topics": viewed,
        "total_topics": total_topics
    }


def get_course_overall_progress(db: Session, course_id: int, total_topics: int = 10):
    """
    Returns average course progress across all students in a course.
    """
    # Get all students who have any progress record in this course
    student_ids = (
        db.query(StudentTopicProgress.student_id)
        .join(Topic, StudentTopicProgress.topic_id == Topic.id)
        .filter(Topic.course_id == course_id)
        .distinct()
        .all()
    )
    student_ids = [s[0] for s in student_ids]

    if not student_ids:
        return {"average_progress": 0, "total_students": 0}

    total_progress = 0
    for student_id in student_ids:
        student_progress = get_student_course_progress(db, course_id, student_id, total_topics)
        total_progress += student_progress["progress_percentage"]

    average_progress = total_progress / len(student_ids)

    return {
        "average_progress": round(average_progress, 2),
        "total_students": len(student_ids)
    }
