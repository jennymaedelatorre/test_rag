from fastapi import APIRouter, Form, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from database.models import User, Course
from database.session import get_db

from utils.flash import flash, get_flashed_messages


templates = Jinja2Templates(directory="templates")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])

# ----------------- Dashboard Redirect Helper -----------------
def get_dashboard_redirect(role: str) -> str:
    """Return the appropriate dashboard URL based on role."""
    return "/faculty/dashboard" if role == "faculty" else "/student/dashboard"

# ----------------- GET Routes -----------------
@auth_router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Show login page or redirect if already logged in."""
    if request.session.get("user_id"):
        return RedirectResponse(url=get_dashboard_redirect(request.session.get("role", "student")), status_code=303)
    
    flashed = get_flashed_messages(request)
    return templates.TemplateResponse("login.html", {"request": request, "flashed": flashed})

@auth_router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse(
            url=get_dashboard_redirect(request.session.get("role", "student")),
            status_code=303
        )

    flashed = get_flashed_messages(request)
    courses = db.query(Course).all()  # For faculty dropdown

    return templates.TemplateResponse(
        "register.html",
        {"request": request, "flashed": flashed, "courses": courses}
    )


# ----------------- POST ROUTES -----------------
@auth_router.post("/register")
def register(
    request: Request,
    fullname: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    course_id: int = Form(None),  
    course_key: str = Form(None),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        flash(request, "Passwords do not match.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)

    if role not in ["student", "faculty"]:
        flash(request, "Invalid role selected.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)


    if db.query(User).filter(User.username == username).first():
        flash(request, f"Username '{username}' already exists.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)

    # ----------------- FACULTY COURSE VALIDATION -----------------
    if role == "faculty":
        if not course_id or not course_key:
            flash(request, "Faculty must select a course and enter the course key.", "danger")
            return RedirectResponse(url="/auth/register", status_code=303)

        course = db.query(Course).filter(Course.id == course_id).first()
        if not course:
            flash(request, "Selected course does not exist.", "danger")
            return RedirectResponse(url="/auth/register", status_code=303)

        # Case-sensitive check for course key
        if course_key.strip() != course.course_key.strip():
            flash(request, "Invalid course key. Please enter the correct code.", "danger")
            return RedirectResponse(url="/auth/register", status_code=303)

        if course.instructor_id is not None:
            flash(request, "This course already has an instructor.", "danger")
            return RedirectResponse(url="/auth/register", status_code=303)
        
    # ----------------- CREATE USER -----------------
    new_user = User(full_name=fullname, username=username, role=role)
    new_user.set_password(password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ----------------- ASSIGN INSTRUCTOR TO COURSE -----------------
    if role == "faculty":
        course.instructor_id = new_user.id
        db.commit()

    # Set session
    request.session["user_id"] = new_user.id
    request.session["user"] = new_user.username
    request.session["role"] = new_user.role

    flash(request, "Registration successful. You are now logged in.", "success")
    return RedirectResponse(url=get_dashboard_redirect(new_user.role), status_code=303)


@auth_router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle user login."""
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not user.check_password(password):
        flash(request, "Invalid username or password.", "danger")
        return RedirectResponse(url="/auth/login", status_code=303)
    
    if user.role != role:
        flash(request, f"Invalid role selected for user '{username}'.", "danger")
        return RedirectResponse(url="/auth/login", status_code=303)
    
    request.session["user_id"] = user.id
    request.session["user"] = user.username
    request.session["role"] = user.role
    
    flash(request, f"Welcome back, {user.full_name}!", "success")
    return RedirectResponse(url=get_dashboard_redirect(user.role), status_code=303)

@auth_router.get("/logout")
def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    flash(request, "You have been logged out.", "info")
    return RedirectResponse(url="/auth/login", status_code=303)
