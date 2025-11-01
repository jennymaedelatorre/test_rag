import os
import tempfile
import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

# --- Local Imports ---
from core.processing import load_and_chunk, get_or_create_vector_store, calculate_file_hash
from core.langchain_chain import build_chain
from database.session import initialize_database
from database.document_db import save_document, retrieve_all_documents_metadata
from routes.auth import auth_router
from utils.flash import get_flashed_messages
from routes.faculty import dashboard, courses, cilos as faculty_cilos
from routes.faculty.upload_topic import faculty_upload_router
from routes.student import student_dashboard_router, student_courses_router, cilos as student_cilos
from routes.student.topics import student_router

# ----------------------------
# 🔧 Basic Setup & Config
# ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="MCQ Generator API")
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-must-be-long-and-secure")
API_KEY = os.getenv("API_KEY")

if not API_KEY:
    raise SystemExit("❌ Gemini API key missing in .env file!")

genai.configure(api_key=API_KEY)

# Directories
CACHE_DIR = Path("./faiss_cache")
CACHE_DIR.mkdir(exist_ok=True)
TEMP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "mcq_uploads"
TEMP_UPLOAD_DIR.mkdir(exist_ok=True)

# ----------------------------
# ⚙️ Middleware and Templates
# ----------------------------
initialize_database()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="rag_session")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------------------
# 🔌 Routers
# ----------------------------

# Auth router (common for both)
app.include_router(auth_router)

# ---- Faculty Routes ----
faculty_routers = [
    dashboard.faculty_router,
    courses.faculty_router,
    faculty_upload_router,
    faculty_cilos.faculty_router
]

for router in faculty_routers:
    app.include_router(router)

# ---- Student Routes ----
student_routers = [
    student_dashboard_router,
    student_courses_router,
    student_router,
    student_cilos.student_router
]

for router in student_routers:
    app.include_router(router)


# ----------------------------
# 🌐 Root Endpoint
# ----------------------------
@app.get("/")
def root():
    """Redirects the base URL to the login page."""
    return RedirectResponse(url="/auth/login")

# ----------------------------
# 🧠 Generate MCQ Endpoint
# ----------------------------

@app.get("/faculty/generate_quiz", response_class=HTMLResponse)
def faculty_mcq_form_alt(request: Request):
    return templates.TemplateResponse("faculty/generate_quiz.html", {"request": request})


@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)) -> JSONResponse:
    """
    Uploads a PDF file, processes or loads it from cache, stores metadata,
    and returns a unique identifier (file hash).

    This is the INDEXING step of the RAG process.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    
    # --- File Saving and Hashing ---
    original_filename = file.filename
    unique_filename = f"{uuid.uuid4()}-{original_filename}"
    temp_file_path = TEMP_UPLOAD_DIR / unique_filename

    try:
        # Read file content and save temporarily
        file_content = await file.read()
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)
        
        # Calculate a unique content-based hash (used for caching)
        file_hash = calculate_file_hash(str(temp_file_path))
        if not file_hash:
            raise HTTPException(status_code=500, detail="Could not calculate file hash.")

        # --- Indexing Logic ---
        index_path = CACHE_DIR / file_hash
        document_uuid = str(uuid.uuid4())
        faiss_action_status = ""

        # Check if the FAISS index (vector store) already exists in the cache
        if index_path.exists():
            logging.info("📦 Cache hit — FAISS index already exists.")
            faiss_action_status = "loaded_from_cache"
        else:
            logging.info("🆕 Cache miss — creating new FAISS index.")
            # Load PDF, split into chunks/documents
            docs = load_and_chunk(str(temp_file_path), document_id=document_uuid)
            if not docs:
                raise HTTPException(status_code=500, detail="No readable content found in PDF.")
            
            # Create embedding, build FAISS index, and save it to index_path
            _, faiss_action_status = get_or_create_vector_store(str(index_path), docs=docs)

            # --- Database Storage  ---
            try:
                # Store the original filename, hash/path, and document_uuid in postgre
                save_document(
                    original_filename, 
                    file_hash,
                    str(index_path), 
                    document_uuid 
                )
                logging.info(f"✅ DB: Document '{original_filename}' saved successfully.")
            except Exception as db_e:
                logging.error(f"DB FAILURE: Could not save document metadata. Error: {db_e}")
                raise HTTPException(status_code=500, detail=f"Failed to record document in database: {db_e}")

        # --- Final Response ---
        return JSONResponse({
            "status": "success",
            "file_name": original_filename,
            "file_hash": file_hash,
            "document_uuid": document_uuid,
            "faiss_action": faiss_action_status
        })

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ An unhandled error occurred in /upload-pdf/: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
    finally:
        # Cleanup temp file
        if temp_file_path.exists():
            os.remove(temp_file_path)
            logging.info(f"🧹 Temporary file removed: {temp_file_path}")


@app.post("/generate-question/")
async def generate_question(
    pdf_hash_id: str = Form(..., description="The unique hash ID returned by /upload-pdf/"),
    topics: str = Form(..., description="Comma-separated list of topics to generate questions on"),
    num_questions: int = Form(..., description="Number of questions to generate (1-10)")
) -> JSONResponse:
    """
    Generates multiple-choice questions for given topics using an existing indexed document.
    This is the RETRIEVAL and GENERATION step of the RAG process.
    """
    # --- Input Validation ---
    if num_questions <= 0 or num_questions > 10:
        raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 10.")
    
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    if not topic_list:
        raise HTTPException(status_code=400, detail="No valid topics provided.")
    
    # --- Vector Store Loading ---
    index_path = CACHE_DIR / pdf_hash_id
    if not index_path.exists():
        raise HTTPException(status_code=404, detail=f"Document index not found for hash ID: {pdf_hash_id}. Please upload the document first.")
    
    # Load the retriever from the existing index
    retriever, _ = get_or_create_vector_store(str(index_path))

    # --- Retrieval and Generation Logic ---
    all_retrieved_chunks = []
    
    # Retrieve content for each requested topic
    for topic in topic_list:
        # Retrieve relevant documents/chunks for the topic (limiting to 2 per topic)
        retrieved = retriever.get_relevant_documents(topic)[:2]
        all_retrieved_chunks.extend(retrieved)


    # Combine the content of all retrieved chunks into a single string for the LLM context
    merged_context = "\n\n".join([doc.page_content for doc in all_retrieved_chunks])

    # --- Prepare the list of chunk texts to return ---
    # Extract the 'page_content' from each retrieved document object
    retrieved_chunk_texts = [doc.page_content for doc in all_retrieved_chunks]

    if not merged_context.strip():
        raise HTTPException(status_code=400, detail="No relevant content found for the given topics.")

    # --- Chain Execution ---
    chain = build_chain()
    # Run the chain with the retrieved context and user inputs
    response_text = chain.run(topic_list, merged_context, num_questions=num_questions)

    return JSONResponse({
        "status": "success",
        "pdf_hash_id": pdf_hash_id,
        "topics": topic_list,
        "generated_mcqs": response_text.strip(),
        "retrieved_chunks_count": len(all_retrieved_chunks),
        "retrieved_chunk_texts": retrieved_chunk_texts
    })


@app.get("/get-documents/")
async def get_documents() -> JSONResponse:
    """
    Retrieves a list of all documents from the database.
    Returns the document name and hash_id (or document UUID).
    """
    try:
        # Query the PostgreSQL table for document data
        document_list = retrieve_all_documents_metadata() 
        
        return JSONResponse({
            "status": "success",
            "documents": document_list
        })
    except Exception as e:
        logging.error(f"DB FAILURE: Could not retrieve document list. Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document list: {e}")
    
# run: uvicorn main:app --reload
