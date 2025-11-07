from fastapi import APIRouter, Form, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

# Local Imports
from database.models import User
from database.session import get_db

from utils.flash import flash, get_flashed_messages

# Templates setup
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
def register_page(request: Request):
    """Show register page or redirect if already logged in."""
    if request.session.get("user_id"):
        return RedirectResponse(url=get_dashboard_redirect(request.session.get("role", "student")), status_code=303)
    
    flashed = get_flashed_messages(request)
    return templates.TemplateResponse("register.html", {"request": request, "flashed": flashed})

# ----------------- POST Routes -----------------
@auth_router.post("/register")
def register(
    request: Request,
    fullname: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle user registration."""
    if password != confirm_password:
        flash(request, "Passwords do not match.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)
    
    if role not in ["student", "faculty"]:
        flash(request, "Invalid role selected.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)
    
    if db.query(User).filter(User.username == username).first():
        flash(request, f"Username '{username}' already exists.", "danger")
        return RedirectResponse(url="/auth/register", status_code=303)
    
    new_user = User(full_name=fullname, username=username, role=role)
    new_user.set_password(password)  
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
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
    
    # Set session
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
