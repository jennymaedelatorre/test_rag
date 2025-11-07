import json
import uuid
from sqlalchemy.orm import Session
from database.models import GeneratedQuestion

def save_generated_questions(
    db: Session, 
    questions_list: list[dict], 
    pdf_hash_id: str, 
    user_id: int
) -> tuple[int, str]:
    """
    Parses a list of generated question dictionaries and persists them to the database.
    
    Returns: A tuple containing the count of questions saved and a status message.
    """
    
    new_questions = []
    saved_count = 0
    
    for q_data in questions_list:
        # Skip incomplete data
        if not q_data.get("question") or not q_data.get("correct_answer"):
            continue 

        new_q = GeneratedQuestion(
            question_id=uuid.uuid4(),
            pdf_hash_id=pdf_hash_id,
            user_id=user_id,
            question_text=q_data.get("question", ""),
            options_json=json.dumps(q_data.get("options", [])), 
            correct_answer=q_data.get("correct_answer", ""),
            co_tag=q_data.get("co_tag", "UNKNOWN")
        )
        new_questions.append(new_q)
        db.add(new_q)
        saved_count += 1

    try:
        db.commit()
        # Refresh is only needed if you plan to immediately use generated data with ORM
        # db.refresh(new_questions[0]) 
        return saved_count, "success"
    except Exception as db_e:
        db.rollback()
        # Log the full error here if necessary
        return 0, f"failed: {str(db_e)}"