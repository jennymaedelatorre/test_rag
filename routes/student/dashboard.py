from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User
from utils.flash import get_flashed_messages

# Router for student dashboard
router = APIRouter(prefix="/student", tags=["Student"])
templates = Jinja2Templates(directory="templates")

@router.get("/dashboard", response_class=HTMLResponse)
def student_dashboard(request: Request, db: Session = Depends(get_db)):
    """Display the student dashboard."""
    user_id = request.session.get("user_id")

    # Check if user is logged in
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch user info
    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        return RedirectResponse(url="/auth/login", status_code=303)


    courses = db.query(Course).all()

     # ✅ Count available courses (or enrolled once you add enrollment feature)
    course_count = db.query(Course).count()

    flashed = get_flashed_messages(request)

    return templates.TemplateResponse(
        "student/dashboard.html",
        {
            "request": request,
            "flashed": flashed,
            "student": student,
            "courses": courses,
            "course_count": course_count,
            "session": request.session
        }
    )
