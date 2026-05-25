from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates
from database.session import get_db
from database.models import Course, User, CILO, GeneratedQuestion
from fastapi import Form, Request
from utils.flash import get_flashed_messages, flash

faculty_course_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")

# =========================
# GET: Faculty Course
# =========================
@faculty_course_router.get("/courses", response_class=HTMLResponse)
def faculty_courses(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    user_full_name = user.full_name

    # Fetch only courses that this faculty handles
    courses = db.query(Course).filter(Course.instructor_id == user_id).all()

    return templates.TemplateResponse(
        "faculty/courses.html",
        {
            "request": request,
            "courses": courses,
            "session": request.session,
            "get_flashed_messages": get_flashed_messages,
            "user_full_name": user_full_name,
        }
    )


# =========================
# CREATE CILO
# =========================
@faculty_course_router.post("/courses/{course_id}/cilos/add")
def add_cilo(
    request: Request,
    course_id: int,
    cilo_code: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        new_cilo = CILO(course_id=course_id, cilo_code=cilo_code, description=description)
        db.add(new_cilo)
        db.commit()
        flash(request, "Course Outcome added successfully!", "success") 
    except Exception as e:
        db.rollback()
        flash(request, f"Error adding Course Outcome: {str(e)}", "danger")
    return RedirectResponse(url="/faculty/courses", status_code=303)

# =========================
# UPDATE CILO
# =========================
@faculty_course_router.post("/cilos/{cilo_id}/edit")
def edit_cilo(
    request: Request,
    cilo_id: int,
    cilo_code: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        cilo = db.query(CILO).filter(CILO.id == cilo_id).first()
        if not cilo:
            flash(request, "Course Outcome not found.", "danger")
            return RedirectResponse(url="/faculty/courses", status_code=303)

        # Check if any generated questions are mapped to this CO
        mapped_questions = db.query(GeneratedQuestion).join(GeneratedQuestion.source_topic).filter(
            GeneratedQuestion.co_tag == cilo.cilo_code,
            GeneratedQuestion.source_topic.has(course_id=cilo.course_id)
        ).count()

        if mapped_questions > 0:
            flash(
                request,
                f"Cannot update '{cilo.cilo_code}' because {mapped_questions} question(s) are already mapped to it.",
                "warning"
            )
            return RedirectResponse(url="/faculty/courses", status_code=303)

        # Safe to update
        cilo.cilo_code = cilo_code
        cilo.description = description
        db.commit()
        flash(request, "Course Outcome updated successfully!", "success")

    except Exception as e:
        db.rollback()
        flash(request, f"Error updating CO: {str(e)}", "danger")

    return RedirectResponse(url="/faculty/courses", status_code=303)


# =========================
# DELETE CILO
# =========================
@faculty_course_router.post("/cilos/{cilo_id}/delete")
def delete_cilo(
    request: Request,
    cilo_id: int,
    db: Session = Depends(get_db)
):
    try:
        cilo = db.query(CILO).filter(CILO.id == cilo_id).first()
        if not cilo:
            flash(request, "Course Outcome not found.", "danger")
            return RedirectResponse(url="/faculty/courses", status_code=303)

        # Check if any generated questions are mapped to this CO
        mapped_questions = db.query(GeneratedQuestion).join(GeneratedQuestion.source_topic).filter(
            GeneratedQuestion.co_tag == cilo.cilo_code,
            GeneratedQuestion.source_topic.has(course_id=cilo.course_id)
        ).count()


        if mapped_questions > 0:
            flash(
                request,
                f"Cannot delete '{cilo.cilo_code}' because {mapped_questions} question(s) are already mapped to it.",
                "warning"
            )
            return RedirectResponse(url="/faculty/courses", status_code=303)

        # Safe to delete
        db.delete(cilo)
        db.commit()
        flash(request, "Course Outcome deleted successfully!", "success")

    except Exception as e:
        db.rollback()
        flash(request, f"Error deleting CO: {str(e)}", "danger")

    return RedirectResponse(url="/faculty/courses", status_code=303)