from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from database.session import get_db
from database.models import User  

student_router = APIRouter()
templates = Jinja2Templates(directory="templates")


@student_router.get("/student/cilos", response_class=HTMLResponse, name="view_cilos_student")
def view_cilos_student(request: Request, db: Session = Depends(get_db)):
    """Render the student's static CILO overview page with dynamic user info."""

    # ✅ 1️⃣ Check if the user is logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    # ✅ 2️⃣ Get the logged-in user
    student = db.query(User).filter(User.id == user_id).first()
    if not student:
        return RedirectResponse(url="/auth/login", status_code=303)

    # ✅ 3️⃣ Render static template (only student info is dynamic for now)
    return templates.TemplateResponse(
        "student/cilos.html",
        {
            "request": request,
            "student": student,
        }
    )
