import json
import logging
from typing import List, Dict, Optional
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)
from core.gemini_llm import GeminiLLM


def format_co_definitions(co_dict: Dict[str, str]) -> str:
    formatted = "\n"
    for tag, definition in co_dict.items():
        formatted += f"- {tag}: {definition}\n"
    return formatted.strip()

# ================================================================
# 2. SYSTEM PROMPT
# ================================================================
SYSTEM_BASE_TEMPLATE = """
You are an expert Computer Science Exam Creator.

Your task is to generate exactly {num_questions} assessment questions based on the provided text.

{question_type_instruction}

You must distribute questions across the allowed CO Tags: [{co_tags}].

==========================================================
STRICT RULES PER QUESTION TYPE
==========================================================

1. MULTIPLE-CHOICE (type="mcq")
    - Provide 4 options only (A, B, C, D).
    - Provide "correct_answer" as the FULL TEXT of the correct option.
    - Only include "options" for MCQs.

2. TRUE/FALSE (type="true_false")
    - Provide one statement only.
    - "correct_answer" must be "True" or "False".

3. IDENTIFICATION (type="identification")
    - Begin with “Identify”, “Name”, or “State”.
    - "correct_answer" must be a single best answer.
    - MUST include "alternative_answers": [ ... ]
    - No "options" included.

==========================================================
STRICT RULES PER CO TAG
==========================================================

CO1 – Fundamentals  
CO2 – Recent Developments  
CO3 – Analyze Solutions (MCQ only, scenario-based)

==========================================================
CONTEXT DEFINITIONS:
{co_definitions}

==========================================================
RETURN VALID JSON ONLY:

{{
  "questions": [
    {{
      "type": "mcq" | "true_false" | "identification",
      "question": "text",
      "options": ["A","B","C","D"],
      "correct_answer": "text",
      "alternative_answers": [],
      "co_tag": "CO1"
    }}
  ]
}}
"""



# ================================================================
# 3. USER PROMPT
# ================================================================
USER_BASE_TEMPLATE = """
Topics to Cover: {topics}
Number of Questions: {num_questions}

Study Material:
{context}
"""

# ================================================================
# 4. GENERATOR CHAIN 
# ================================================================
class MCQGeneratorChain:
    def __init__(self):
        self.llm = GeminiLLM()

    def run(
        self,
        topics: List[str],
        context: str,
        num_questions: int,
        course_outcomes: Dict[str, str],  
        co_tags: List[str],
        question_type: Optional[str] = None,
    ) -> Dict:

        if not co_tags:
            raise ValueError("CO tags cannot be empty.")

        filtered_cos = {tag: course_outcomes[tag] for tag in co_tags if tag in course_outcomes}
        co_defs = format_co_definitions(filtered_cos)

        # Determine instruction for question type
        if question_type in ["mcq", "true_false", "identification"]:
            qtype_instr = f"ONLY generate questions of type: {question_type}."
        else:
            qtype_instr = "You may generate a mix of question types: mcq, true_false, identification."

        # Create prompt templates
        system_prompt = SystemMessagePromptTemplate.from_template(SYSTEM_BASE_TEMPLATE)
        user_prompt = HumanMessagePromptTemplate.from_template(USER_BASE_TEMPLATE)
        prompt = ChatPromptTemplate.from_messages([system_prompt, user_prompt])

        # Format prompt
        formatted_prompt = prompt.format_prompt(
            num_questions=num_questions,
            question_type_instruction=qtype_instr,
            co_tags=", ".join(co_tags),
            co_definitions=co_defs,
            topics=", ".join(topics),
            context=context
        ).to_string()


        try:
            # Call LLM
            response = self.llm.invoke(formatted_prompt)

            print("=== LLM RAW OUTPUT ===")
            print(response)

            print("=== COURSE OUTCOMES USED ===")
            for code, desc in course_outcomes.items():
                print(code, "→", desc)

            if isinstance(response, dict):
                data = response
            else:
                clean = response.strip()
                for prefix in ["```json", "```"]:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix):].strip()
                if clean.endswith("```"):
                    clean = clean[:-3].strip()
                data = json.loads(clean)

            # Validate output
            if "questions" not in data:
                raise RuntimeError("Output missing 'questions' field.")

            for q in data["questions"]:
                if "type" not in q:
                    raise RuntimeError("Each question must have a 'type' field.")
                qtype = q["type"]

                if qtype == "mcq":
                    if "options" not in q or len(q["options"]) != 4:
                        raise RuntimeError("MCQ must include exactly 4 options.")
                elif qtype in ["true_false", "identification"]:
                    q.pop("options", None)
                else:
                    raise RuntimeError(f"Unknown question type: {qtype}")

            return data

        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error: {e}")
            raise RuntimeError("AI returned invalid JSON.")
        except Exception as e:
            logging.error(f"Chain Execution Error: {e}")
            raise RuntimeError(f"Failed to generate questions: {e}")

# ================================================================
# 5. FACTORY FUNCTION
# ================================================================
def build_chain() -> MCQGeneratorChain:
    return MCQGeneratorChain()
