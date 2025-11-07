from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from database.session import get_db
from database.models import Course, User, Topic 
from utils.flash import get_flashed_messages
   

faculty_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

@faculty_router.get("/dashboard", response_class=HTMLResponse)
def faculty_dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    user_full_name = user.full_name
    
    # Get all courses handled by this faculty
    courses = db.query(Course).filter(Course.instructor_id == user_id).all()
    course_count = len(courses)

    # ✅ Count all uploaded topics for this faculty
    topic_count = (
        db.query(Topic)
        .join(Course, Course.id == Topic.course_id)
        .filter(Course.instructor_id == user_id)
        .count()
    )

    # ✅ Count all registered students
    student_count = db.query(User).filter(User.role == "student").count()

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse(
        "faculty/dashboard.html",
        {
            "request": request,
            "flashed": flashed,
            "courses": courses,
            "user_full_name": user_full_name,
            "course_count": course_count,
            "student_count": student_count,
            "topic_count": topic_count,
            "session": request.session,
        }
    )

    
