from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User

faculty_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

@faculty_router.get("/courses", response_class=HTMLResponse)
def faculty_courses(request: Request, db: Session = Depends(get_db)):
    # 🔑 STEP A: AUTHENTICATION AND ID RETRIEVAL
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # 🔑 STEP B: FETCH USER OBJECT
    # Query the User model to get the full_name
    user = db.query(User).filter(User.id == user_id).first()
    
    # Handle user not found (security check)
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    # 🔑 STEP C: RETRIEVE FULL NAME
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
