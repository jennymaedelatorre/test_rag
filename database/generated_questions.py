import json
from uuid import uuid4
from sqlalchemy.orm import Session
from database.models import GeneratedQuestion
import logging

def save_generated_questions(
    db: Session,
    questions_list: list[dict],
    topic_id: int, 
    user_id: int
) -> tuple[int, str]:
    """
    Save generated MCQs to the database.
    Returns the number of saved questions and a status message.
    """
    
    questions_to_add = []

    try:
        # Loop through all questions
        for q_data in questions_list:
            question_text = q_data.get("question", "").strip()
            options = q_data.get("options", [])

            # Skip questions with missing text or options
            if not question_text or not options:
                continue

            # Create a new question record
            new_question = GeneratedQuestion(
                question_id=str(uuid4()),
                topic_id=topic_id,
                user_id=user_id,
                question_text=question_text,
                options_json=json.dumps(options, ensure_ascii=False),
                correct_answer=q_data.get("correct_answer", "").strip(),
                co_tag=q_data.get("co_tag", "CO1").strip()
            )

            questions_to_add.append(new_question)
        
        # Add all questions to the database at once
        db.add_all(questions_to_add)
        db.commit()
        
        return len(questions_to_add), "success"
    
    except Exception as e:
        # Rollback in case of any error
        db.rollback()
        logging.error(f"Database save error: {e}", exc_info=True)
        return 0, "Database error during save."
