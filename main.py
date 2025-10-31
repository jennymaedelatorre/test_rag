import os
import tempfile
import uuid
import logging
from pathlib import Path
from typing import Dict
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import google.generativeai as genai

# Import custom modules
from core.processing import load_and_chunk, get_or_create_vector_store, calculate_file_hash
from database.session import save_document, initialize_database
from core.langchain_chain import build_chain

# ----------------------------
# 🔧 Basic Setup & Config
# ----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(title="MCQ Generator API")
load_dotenv()

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise SystemExit("❌ Gemini API key missing in .env file!")

genai.configure(api_key=API_KEY)

# Directories
CACHE_DIR = Path("./faiss_cache")
CACHE_DIR.mkdir(exist_ok=True)
TEMP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "mcq_uploads"
TEMP_UPLOAD_DIR.mkdir(exist_ok=True)

initialize_database()


# ----------------------------
# 🏠 Root Endpoint
# ----------------------------
@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "✅ Server is running! Use the /generate-mcq/ endpoint with a POST request."}


# ----------------------------
# 🧠 Generate MCQ Endpoint
# ----------------------------
@app.post("/generate-mcq/")
async def generate_mcq(
    file: UploadFile = File(...),
    topics: str = Form(...),
    num_questions: int = Form(...)
) -> JSONResponse:
    """
    Uploads a PDF, processes or loads it from cache, retrieves topic-relevant chunks,
    and generates multiple-choice questions.
    """

    # ✅ Basic Validations
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if num_questions <= 0 or num_questions > 10:
        raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 10.")

    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    if not topic_list:
        raise HTTPException(status_code=400, detail="No valid topics provided.")

    original_filename = file.filename
    unique_filename = f"{uuid.uuid4()}-{original_filename}"
    temp_file_path = TEMP_UPLOAD_DIR / unique_filename

    # ----------------------------
    # 🧾 Save Uploaded File Temporarily
    # ----------------------------
    try:
        file_content = await file.read()
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)

        # 1️⃣ Calculate File Hash
        file_hash = calculate_file_hash(str(temp_file_path))
        if not file_hash:
            raise HTTPException(status_code=500, detail="Could not calculate file hash.")

        index_path = CACHE_DIR / file_hash
        faiss_action_status = ""
        retriever = None
        document_uuid = str(uuid.uuid4())

        # ----------------------------
        # 💾 Check Cache / DB
        # ----------------------------
        if index_path.exists():
            logging.info("📦 Cache hit — loading FAISS index.")
            retriever, faiss_action_status = get_or_create_vector_store(str(index_path))
        else:
            logging.info("🆕 Cache miss — creating new FAISS index.")

            # ✅ Load and chunk PDF
            docs = load_and_chunk(str(temp_file_path), document_id=document_uuid)
            if not docs:
                raise HTTPException(status_code=500, detail="No readable content found in PDF.")

            # ✅ Create FAISS Vector Store
            retriever, faiss_action_status = get_or_create_vector_store(str(index_path), docs=docs)

            # ✅ Save metadata only after successful index creation
            try:
                    save_document(original_filename, str(index_path), document_uuid)

                    logging.info(f"✅ DB: Document '{original_filename}' saved successfully.")
            except Exception as db_e:
                logging.error(f"DB FAILURE: Could not save document metadata. Error: {db_e}")
                raise HTTPException(status_code=500, detail=f"Failed to record document in database: {db_e}")

        # ----------------------------
        # 🔍 Retrieve Chunks by Topic
        # ----------------------------
        all_retrieved_chunks = []
        per_topic_chunks = []

        for topic in topic_list:
            retrieved = retriever.get_relevant_documents(topic)[:2]
            all_retrieved_chunks.extend(retrieved)
            per_topic_chunks.append({
                "query": topic,
                "document_uuid": document_uuid, 
                "chunks": [doc.page_content for doc in retrieved]
            })

        merged_context = "\n\n".join([doc.page_content for doc in all_retrieved_chunks])

        if not merged_context.strip():
            raise HTTPException(status_code=400, detail="No relevant content found for the given topics.")

        # ----------------------------
        # 🤖 Run LLM Chain (Gemini)
        # ----------------------------
        chain = build_chain()
        response_text = chain.run(topic_list, merged_context, num_questions=num_questions)

        # ----------------------------
        # 📤 Return JSON Response
        # ----------------------------
        return JSONResponse({
            "status": "success",
            "file_name": original_filename,
            "file_hash": file_hash,
            "faiss_action": faiss_action_status,
            "topics": topic_list,
            "generated_mcqs": response_text.strip(),
            "retrieved_chunks": per_topic_chunks
        })

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ An unhandled error occurred in /generate-mcq/: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

    finally:
        # 🧹 Cleanup temp file
        if temp_file_path.exists():
            os.remove(temp_file_path)
            logging.info(f"🧹 Temporary file removed: {temp_file_path}")


# run: uvicorn main:app --reload