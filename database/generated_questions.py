import json
import logging
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from database.models import GeneratedQuestion
import uuid
from datetime import datetime

def save_generated_questions(
    db: Session,
    questions_list: List[Dict],
    topic_id: int,
    user_id: int
) -> Tuple[int, str]:
    """
    Save generated MCQs to the database safely.
    Uses TEXT columns for question content, preserving all special characters.
    """

    saved_count = 0
    questions_to_add = []

    try:
        for q_data in questions_list:
            # All content is now safe to be long strings (TEXT type in DB)
            question_text = str(q_data.get("question") or "").strip()
            
            options_raw = q_data.get("options", [])
            options_clean = [str(opt).strip() for opt in options_raw if str(opt).strip()]
            
            correct_answer = str(q_data.get("correct_answer") or "").strip()
            co_tag = str(q_data.get("co_tag") or "CO1").strip()

            if not question_text or not options_clean:
                logging.warning("Skipping question due to missing text/options: %s", q_data)
                continue

            if not correct_answer and options_clean:
                correct_answer = options_clean[0]

            # Create DB object
            new_question = GeneratedQuestion(
                question_id=uuid.uuid4(),
                topic_id=topic_id,
                user_id=user_id,
                question_text=question_text,
                options_json=json.dumps(options_clean, ensure_ascii=False), 
                correct_answer=correct_answer,
                co_tag=co_tag,
                created_at=datetime.utcnow()
            )

            questions_to_add.append(new_question)
            saved_count += 1

        if questions_to_add:
            db.add_all(questions_to_add)
            db.commit()

        return saved_count, "success"

    except Exception as e:
        db.rollback()
        logging.error("Database save error during question batch: %s", e, exc_info=True) 
        return 0, "Database error during save."