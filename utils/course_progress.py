from sqlalchemy.orm import Session
from database.models import StudentCourseProgress, Topic, Course, User


def get_student_course_progress(db: Session, student_id: int, course_id: int):
    """
    Returns the student's progress for a given course in percentage.
    """

    courses = db.query(Course).all()
    # Get total topics in the course
    total_topics = courses.total_topics or 0
    if total_topics == 0:
        return {
            "progress_percentage": 0,
            "completed_topics": 0,
            "total_topics": 0
        }


    # Get completed topics for student
    completed_topics = (
        db.query(StudentCourseProgress)
        .join(Topic, StudentCourseProgress.topic_id == Topic.id)
        .filter(StudentCourseProgress.student_id == student_id)
        .filter(Topic.course_id == course_id)
        .filter(StudentCourseProgress.completed == True)
        .count()
    )

    progress_percentage = round((completed_topics / total_topics) * 100)

    return {
        "progress_percentage": progress_percentage,
        "completed_topics": completed_topics,
        "total_topics": total_topics
    }



