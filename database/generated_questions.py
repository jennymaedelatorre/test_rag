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
    Saves generated MCQ, True/False, Identification questions safely.
    Correctly handles options and alternative answers based on question type.
    """

    saved_count = 0
    questions_to_add = []

    try:
        for q_data in questions_list:

            # Extract main fields
            question_text = (q_data.get("question") or "").strip()
            
            q_type = (
                q_data.get("type")
                or q_data.get("question_type")
                or ""
            ).strip().lower()


            # default types ONLY if invalid
            if q_type not in ["mcq", "true_false", "identification"]:
                q_type = "mcq"

            correct_answer = (q_data.get("correct_answer") or "").strip()
            co_tag = (q_data.get("co_tag") or "CO1").strip()

            # Validation 1 — must have text + answer
            if not question_text or not correct_answer:
                logging.warning("Skipping question due to missing text or correct_answer: %s", q_data)
                continue

            # ----------------------------
            # MCQ VALIDATION & OPTIONS
            # ----------------------------
            if q_type in ["mcq", "true_false"]:
                options = q_data.get("options", [])
                
                # For True/False, provide defaults options
                if q_type == "true_false" and not options:
                    options = ["True", "False"]

                options_clean = [str(opt).strip() for opt in options if str(opt).strip()]

                if q_type == "mcq" and len(options_clean) < 4:
                    logging.warning("Skipping MCQ due to insufficient options: %s", q_data)
                    continue

                options_json = json.dumps(options_clean, ensure_ascii=False)
            else:
                options_json = None

            
            # IDENTIFICATION — alternative answers
            if q_type == "identification":
                alt_raw = q_data.get("alternative_answers", [])
                alternatives_clean = [str(a).strip() for a in alt_raw if str(a).strip()]

                alternatives_json = (
                    json.dumps(alternatives_clean, ensure_ascii=False)
                    if alternatives_clean else None
                )
            else:
                alternatives_json = None

            
            # Create Question DB Object
           
            new_question = GeneratedQuestion(
                question_id=uuid.uuid4(),
                topic_id=topic_id,
                user_id=user_id,
                question_text=question_text,
                question_type=q_type,
                options_json=options_json,
                correct_answer=correct_answer,
                alternative_answers_json=alternatives_json,
                co_tag=co_tag,
                created_at=datetime.utcnow()
            )

            questions_to_add.append(new_question)
            saved_count += 1

        # Save 
        if questions_to_add:
            db.add_all(questions_to_add)
            db.commit()

        return saved_count, "success"

    except Exception as e:
        db.rollback()
        logging.error("Database save error: %s", e, exc_info=True)
        return 0, "Database error during save."
