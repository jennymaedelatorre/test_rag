from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User

faculty_course_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

@faculty_course_router.get("/courses", response_class=HTMLResponse)
def faculty_courses(request: Request, db: Session = Depends(get_db)):
    # authentication 
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Query the User model to get the full_name
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    user_full_name = user.full_name
    
    # Fetch all courses 
    courses = db.query(Course).all()

    return templates.TemplateResponse(
        "faculty/courses.html",
        {
            "request": request,
            "courses": courses,
            "session": request.session,
            "user_full_name": user_full_name,
        }
    )
