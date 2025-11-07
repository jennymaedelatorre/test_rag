from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User, DownloadHistory

router = APIRouter(prefix="/student", tags=["Student Courses"])
templates = Jinja2Templates(directory="templates")

@router.get("/courses", response_class=HTMLResponse)
def student_courses(request: Request, db: Session = Depends(get_db)):
    """Display the list of all available courses for the student."""
    user_id = request.session.get("user_id")

    # Ensure user is logged in
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch logged-in student
    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        return RedirectResponse(url="/auth/login", status_code=303)

    # show all courses
    courses = db.query(Course).all()

     # Get recent downloads
    downloads = (
        db.query(DownloadHistory)
        .filter(DownloadHistory.user_id == user_id)
        .order_by(DownloadHistory.downloaded_at.desc())
        .limit(10)
        .all()
    )


    return templates.TemplateResponse(
        "student/courses.html",
        {
            "request": request,
            "student": student,
            "courses": courses,
            "session": request.session,
            "downloads": downloads
        }
    )
