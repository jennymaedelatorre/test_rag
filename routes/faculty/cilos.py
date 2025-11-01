from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates


from database.session import get_db
from database.models import User, Course, CILO 

faculty_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

@faculty_router.get("/cilos", response_class=HTMLResponse)
def view_cilos_faculty(request: Request, db: Session = Depends(get_db)):
    """Render the faculty CILO overview page with dynamic instructor, courses, CILOs, and students."""
    
    # 1️⃣ Check login
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # 2️⃣ Get logged-in faculty
    faculty = db.query(User).filter(User.id == user_id).first()
    if not faculty or faculty.role != "faculty":
        return RedirectResponse(url="/auth/login", status_code=303)

    # 3️⃣ Get courses 
    courses = db.query(Course).filter(Course.instructor_id == faculty.id).all()

    # 4️⃣ Get students (simplified: all users with role="student")
    students = db.query(User).filter(User.role == "student").all()
    
    # 5️⃣ Get CILOs 
    course_data = []
    
    for course in courses:
        cilos_list = db.query(CILO).filter(CILO.course_id == course.id).all()
        
        course_data.append({
            "id": course.id,      
            "title": course.title,
            "cilos": cilos_list         
        })

    return templates.TemplateResponse(
        "faculty/cilos.html",
        {
            "request": request,
            "faculty": faculty,
            "courses": course_data, 
            "students": students,
        }
    )