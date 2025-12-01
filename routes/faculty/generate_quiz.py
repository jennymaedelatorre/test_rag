from fastapi import APIRouter, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
from pathlib import Path
import json
import re

from database.session import get_db
from database.models import Topic, User, GeneratedQuestion
from core.processing import get_or_create_vector_store
from core.mcq_chain import build_chain
from utils.flash import flash, get_flashed_messages
from database.generated_questions import save_generated_questions

faculty_quiz_router = APIRouter(prefix="/faculty", tags=["Faculty"])
templates = Jinja2Templates(directory="templates")
CACHE_DIR = Path("./faiss_cache")


# ---------------------------------
# GET: Generate Questions Page
# ---------------------------------
@faculty_quiz_router.get("/generate_quiz", response_class=HTMLResponse)
def generate_question_page(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/auth/login", status_code=303)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)

    topics = db.query(Topic).filter(Topic.uploaded_by == user_id).all()
    flashed = get_flashed_messages(request)

    return templates.TemplateResponse(
        "faculty/generate_quiz.html",
        {
            "request": request,
            "topics": topics,
            "flashed": flashed,
            "user_full_name": user.full_name
        }
    )


@faculty_quiz_router.post("/generate_quiz", response_class=JSONResponse)
async def generate_question(
    request: Request,
    topic_id: int = Form(...),
    topics: str = Form(...),
    question_type: str = Form("mcq"), 
    num_questions: int = Form(...),
    co_tags: str = Form(...),
    db: Session = Depends(get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    if not 1 <= num_questions <= 20:
        raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 20.")

    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    co_tag_list = [t.strip().upper() for t in co_tags.split(",") if t.strip()]

    if question_type not in ["mcq", "true_false", "identification"]:
        raise HTTPException(status_code=400, detail="Invalid question type selected.")

    if not topic_list or not co_tag_list:
        raise HTTPException(status_code=400, detail="Invalid topics or CO tags.")

    # Fetch Topic Record
    topic_record = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic_record:
        raise HTTPException(status_code=404, detail="Topic not found.")

    # Check existing questions
    existing_questions_count = db.query(GeneratedQuestion).filter(
        GeneratedQuestion.topic_id == topic_id
    ).count()
    if existing_questions_count > 0:
        msg = f"A quiz has already been generated for '{topic_record.title}'. Clear existing questions to re-generate."
        return JSONResponse({
            "status": "error",
            "redirect": True,
            "flash": {"message": msg, "category": "warning", "title": "Quiz Already Generated"}
        })

    # FAISS index (RAG Retrieval)
    file_hash = topic_record.file_hash
    index_path = CACHE_DIR / file_hash
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Document index not found. Upload PDF first.")

    retriever, _ = get_or_create_vector_store(str(index_path))

    all_retrieved_chunks = []
    for t in topic_list:
        docs = retriever.get_relevant_documents(t)[:4]
        all_retrieved_chunks.extend(docs)
    if not all_retrieved_chunks:
        raise HTTPException(status_code=400, detail="No relevant content found.")

    merged_context = "\n\n".join([d.page_content for d in all_retrieved_chunks])

    # Generate questions with LLM
    chain = build_chain()
    try:
        generated_data = chain.run(
            topics=topic_list,
            context=merged_context,
            num_questions=num_questions,
            co_tags=co_tag_list,
            question_type=question_type
        )

        if not isinstance(generated_data, dict):
            raise HTTPException(status_code=500, detail="AI returned invalid data format")

        questions_list = generated_data.get("questions", [])
        if not questions_list:
            raise HTTPException(status_code=500, detail="No questions generated.")

    except Exception as e:
        logging.error(f"Chain error: {e}", exc_info=True)
        error_detail = str(e) if not isinstance(e, HTTPException) else e.detail
        raise HTTPException(status_code=500, detail=f"AI failed to generate questions: {error_detail}")

    # --- POST-GENERATION CLEANUP AND PREPARATION ---
    for q in questions_list:
        q["question_type"] = q.pop("type", "mcq") 
        
        if q["question_type"] == "true_false":
            q["options"] = ["True", "False"]
        elif q["question_type"] == "identification":
            q["options"] = []
            
        # Clean up the alternative_answers field for non-identification types 
        if q["question_type"] != "identification":
            q.pop("alternative_answers", None)

   
    saved_count = len(questions_list)
    
    
    # Store in session cache for the next step (review/edit)
    cache_key = f"quiz_cache_{topic_id}"
    request.session[cache_key] = questions_list

    return JSONResponse({
        "status": "success",
        "topic_id": topic_id,
        "topic_title": topic_record.title,
        "generated_questions": questions_list,
        "retrieved_chunks_count": len(all_retrieved_chunks)
    })


# ---------------------------------
# POST: Save Generated Questions
# ---------------------------------
@faculty_quiz_router.post("/save_questions/", response_class=JSONResponse)
async def save_generated_questions_route(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    data = await request.json()
    topic_id = data.get("topic_id")
    if not topic_id:
        flash(request, "Missing Topic ID.", category="danger", title="Input Error")
        return JSONResponse({"status": "error", "redirect": True})

    try:
        topic_id_int = int(topic_id)
    except ValueError:
        flash(request, "Invalid Topic ID format.", category="danger", title="Input Error")
        return JSONResponse({"status": "error", "redirect": True})

    cache_key = f"quiz_cache_{topic_id_int}"
    cached_questions = request.session.get(cache_key)
    client_questions = data.get("questions", [])

    
    if not cached_questions:
        questions_to_save = client_questions if client_questions else []
    else:
        questions_to_save = []
        client_co_map = {q.get('question', '').strip(): q.get('co_tag', 'CO1') for q in client_questions}
        
        for q_cache in cached_questions:
            question_text_key = q_cache.get('question', '').strip()
            
            # Use the CO tag from the client if available, otherwise use the cached one
            final_co_tag = client_co_map.get(question_text_key, q_cache.get('co_tag', 'CO1'))
            
            question_data = {
                "question": q_cache.get('question'),
                "options": q_cache.get('options', []),
                "correct_answer": q_cache.get('correct_answer'),
                "co_tag": final_co_tag,
                "type": q_cache.get('question_type', 'mcq') 
            }

            
            if q_cache.get('alternative_answers') is not None:
                question_data["alternative_answers"] = q_cache['alternative_answers']
            
            questions_to_save.append(question_data)
   

    if not questions_to_save:
        flash(request, "No valid questions to save.", category="danger", title="Data Error")
        return JSONResponse({"status": "error", "redirect": True})

    try:
        saved_count, status = save_generated_questions(
            db=db,
            questions_list=questions_to_save,
            topic_id=topic_id_int,
            user_id=user_id
        )
        if status != "success":
            flash(request, f"Could not save questions: {status}", category="danger", title="Save Failed")
            return JSONResponse({"status": "error", "redirect": True})

        # Clear cache after successful save
        if cache_key in request.session:
            del request.session[cache_key]

        flash(request, f"{saved_count} questions saved successfully.", category="success", title="Success!")
        return JSONResponse({"status": "success", "redirect": True, "redirect_url": "/faculty/generate_quiz/"})
    except Exception as e:
        logging.error(f"Save operation failed: {e}", exc_info=True)
        flash(request, "An unexpected error occurred. Check server logs.", category="danger", title="System Error")
        return JSONResponse({"status": "error", "redirect": True})