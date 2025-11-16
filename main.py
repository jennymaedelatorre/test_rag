import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


from database.session import initialize_database
from routes.auth import auth_router
from routes.faculty import dashboard, courses, cilos as faculty_cilos
from routes.faculty.upload_topic import faculty_upload_router
from routes.faculty.generate_quiz import faculty_quiz_router
from routes.student.dashboard import student_dashboard_router
from routes.student.courses import student_courses_router
from routes.student.cilos import student_cilos_router
from routes.student.topics import student_topic_router
from routes.student.quiz import student_quiz_router

# ----------------------------
# Basic Setup & Configuration
# ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="MCQ Generator API")

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
API_KEY = os.getenv("API_KEY")

if not API_KEY:
    raise SystemExit("Gemini API key missing in .env file!")

genai.configure(api_key=API_KEY)

# ----------------------------
# Middleware and Templates
# ----------------------------
initialize_database()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="rag_session")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------------------
# Routers
# ----------------------------
app.include_router(auth_router)

faculty_routers = [
    dashboard.faculty_dashboard_router,
    courses.faculty_course_router,
    faculty_upload_router,
    faculty_cilos.faculty_cilos_router,
    faculty_quiz_router
]
for router in faculty_routers:
    app.include_router(router)

student_routers = [
    student_dashboard_router,
    student_courses_router,
    student_topic_router,
    student_cilos_router,
    student_quiz_router
]
for router in student_routers:
    app.include_router(router)

# ----------------------------
# Root Endpoint
# ----------------------------
@app.get("/")
def root():
    """Redirect to the login page."""
    return RedirectResponse(url="/auth/login")


# ----------------------------
# Retrieve Documents
# ----------------------------
# @app.get("/get-documents/")
# async def get_documents() -> JSONResponse:
#     """Retrieve list of documents from the database."""
#     try:
#         document_list = retrieve_all_documents_metadata()
#         return JSONResponse({
#             "status": "success",
#             "documents": document_list
#         })
#     except Exception as e:
#         logging.error(f"DB retrieval error: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to retrieve document list: {e}")

# Run command: uvicorn main:app --reload
