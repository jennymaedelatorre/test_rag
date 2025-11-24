from fastapi import APIRouter, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
from pathlib import Path
import json

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
    
    print("User ID in session:", request.session.get("user_id"))

    # Fetch the faculty user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/auth/login", status_code=303)
    
    user_full_name = user.full_name

    topics = db.query(Topic).filter(Topic.uploaded_by == user_id).all()
    flashed = get_flashed_messages(request)


    return templates.TemplateResponse("faculty/generate_quiz.html", {
        "request": request,
        "topics": topics,
        "flashed": flashed,
        "user_full_name": user.full_name
    })


# ---------------------------------
# POST: Generate MCQs (AI)
# ---------------------------------
@faculty_quiz_router.post("/generate_quiz/", response_class=JSONResponse)
async def generate_question(
    request: Request,
    topic_id: int = Form(..., description="The selected topic ID"),
    topics: str = Form(..., description="Comma-separated list of topics"),
    num_questions: int = Form(..., description="Number of questions (1-20)"),
    co_tags: str = Form(..., description="Comma-separated CO tags (e.g., CO1,CO2)"),
    db: Session = Depends(get_db)
):
    """
    Generate MCQs from a topic’s indexed PDF content.
    """

    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Validate question count
    if not 1 <= num_questions <= 20:
        raise HTTPException(status_code=400, detail="Number of questions must be between 1 and 20.")

    # Parse topics and CO tags
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    co_tag_list = [t.strip().upper() for t in co_tags.split(",") if t.strip()]

    if not topic_list:
        raise HTTPException(status_code=400, detail="No valid topics provided.")
    if not co_tag_list:
        raise HTTPException(status_code=400, detail="No valid CO tags provided.")

    #  Fetch topic from DB
    topic_record = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic_record:
        raise HTTPException(status_code=404, detail="Topic not found.")
    
    # Check if quiz already generated
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

    file_hash = topic_record.file_hash
    index_path = CACHE_DIR / file_hash

    #  Ensure FAISS index exists
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Document index not found. Upload PDF first.")

    retriever, _ = get_or_create_vector_store(str(index_path))

    #  Retrieve relevant content
    all_retrieved_chunks = []
    for t in topic_list:
        docs = retriever.get_relevant_documents(t)[:2]
        all_retrieved_chunks.extend(docs)

    if not all_retrieved_chunks:
        raise HTTPException(status_code=400, detail="No relevant content found for the given topics.")

    # merge it
    merged_context = "\n\n".join([d.page_content for d in all_retrieved_chunks])

    #  Generate questions using LLM
    chain = build_chain()
    try:
        generated_data = chain.run(
            topics=topic_list,
            context=merged_context,
            num_questions=num_questions,
            co_tags=co_tag_list
        )

        questions_list = generated_data.get("questions", [])
        if not questions_list:
            raise HTTPException(status_code=500, detail="No questions generated.")
    except Exception as e:
        logging.error(f"Chain error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="AI failed to generate questions")
    
    cache_key = f"quiz_cache_{topic_id}"
    request.session[cache_key] = questions_list

    #  Return JSON 
    return {
        "status": "success",
        "topic_id": topic_id,
        "topic_title": topic_record.title,
        "generated_mcqs": questions_list,
        "retrieved_chunks_count": len(all_retrieved_chunks),
    }


# ---------------------------------
# POST: Save MCQs (DB)
# ---------------------------------
@faculty_quiz_router.post("/save_questions/")
async def save_generated_questions_route(
    request: Request,
    db: Session = Depends(get_db)
):
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
    
    #  Get the secure, original question data from the cache
    cached_questions = request.session.get(cache_key) 
    
    #  Get the user's final CO tag selections from the client payload
    client_questions = data.get("questions", [])
    
    if not cached_questions:
        # Fallback if cache is empty, but rely on client data only if necessary
        if client_questions:
            logging.warning("Cache empty. Relying solely on client data for save operation.")
            questions_to_save = client_questions
        else:
            flash(request, "Quiz data not found. Please re-generate the quiz.", category="danger", title="Data Missing")
            return JSONResponse({"status": "error", "redirect": True})
    
    # MERGE LOGIC: If both exist, merge the CO tag from the client into the cache data
    else:
        questions_to_save = []
        # Create a map of question text -> CO tag from the client data for quick lookup
        client_co_map = {q.get('question', '').strip(): q.get('co_tag', 'CO1') for q in client_questions}
        
        for q_cache in cached_questions:
            # Match question text (using strip for safety)
            question_text_key = q_cache.get('question', '').strip()
            
            # Get the user's final CO tag, or stick with the original if no match is found
            final_co_tag = client_co_map.get(question_text_key, q_cache.get('co_tag', 'CO1'))
            
            # Create the final, clean structure for saving
            questions_to_save.append({
                "question": q_cache.get('question'),
                "options": q_cache.get('options'),
                "correct_answer": q_cache.get('correct_answer'),
                # Use the user's selected CO tag
                "co_tag": final_co_tag, 
            })


    if not questions_to_save:
        flash(request, "No valid questions to save after processing.", category="danger", title="Data Error")
        return JSONResponse({"status": "error", "redirect": True})

    try:
        saved_count, status = save_generated_questions(
            db=db,
            questions_list=questions_to_save,
            topic_id=topic_id_int,
            user_id=user_id
        )
        
        if status != "success":
             flash(
                 request, 
                 f"Could not save questions: {status}", 
                 category="danger", 
                 title="Save Failed"
             )
             return JSONResponse({"status": "error", "redirect": True})

        # SUCCESS cleanup and flash
        if cache_key in request.session:
             del request.session[cache_key]
             
        flash(
            request, 
            f"{saved_count} questions generated and saved successfully.", 
            category="success", 
            title="Success!"
        )
        return JSONResponse({"status": "success", "redirect": True})

    except Exception as e:
        logging.error(f"Save operation failed: {e}", exc_info=True)
        flash(request, "An unexpected internal server error occurred.", category="danger", title="System Error")
        return JSONResponse({"status": "error", "redirect": True, "message": "Internal Server Error"})