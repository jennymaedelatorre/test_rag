# core/mcq_chain.py

import json
import logging
from typing import List, Dict
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)
from core.gemini_llm import GeminiLLM

COURSE_OUTCOMES: Dict[str, str] = {
    "CO1": "Explain fundamental principles, concepts and evolution of computing systems as they relate to different fields.",
    "CO2": "Expound in the recent developments in the different computing knowledge areas.",
    "CO3": "Analyze solutions employed by organizations to address different computing issues."
}

def format_co_definitions(co_dict: Dict[str, str]) -> str:
    formatted = "\n"
    for tag, definition in co_dict.items():
        formatted += f"- {tag}: {definition}\n"
    return formatted.strip()

# ✅ ESCAPED CURLY BRACES in JSON example
SYSTEM_BASE_TEMPLATE = """
You are an expert exam question creator.
Your task is to generate exactly {num_questions} multiple-choice questions (MCQs)
strictly based on the provided study material and topics.

Rules:
- Every question must relate directly to one of the provided topics.
- Exactly 4 answer options per question.
- Only one correct answer which MUST match one of the options.
- No invented facts; questions must be based only on given context.

CO TAGGING RULES:
- Each question MUST include a 'co_tag'
- Allowed tags: {co_tags}
- Use the definitions below:

{co_definitions}

--- OUTPUT FORMAT ---
Return ONLY valid JSON. No markdown, no code fences, no explanations.

Output format:

{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "string",
      "co_tag": "CO1|CO2|CO3"
    }}
  ]
}}
"""

USER_BASE_TEMPLATE = """
Topics to Cover: {topics}
Number of Questions: {num_questions}

Study Material:
{context}
"""

class MCQGeneratorChain:
    def __init__(self):
        self.llm = GeminiLLM()

    def run(self, topics: List[str], context: str, num_questions: int, co_tags: List[str]) -> List[Dict]:
        if not co_tags:
            raise ValueError("CO tags cannot be empty.")

        filtered_cos = {tag: COURSE_OUTCOMES[tag] for tag in co_tags if tag in COURSE_OUTCOMES}
        co_defs = format_co_definitions(filtered_cos)

        system_prompt = SystemMessagePromptTemplate.from_template(SYSTEM_BASE_TEMPLATE)
        user_prompt = HumanMessagePromptTemplate.from_template(USER_BASE_TEMPLATE)
        prompt = ChatPromptTemplate.from_messages([system_prompt, user_prompt])

        formatted_prompt = prompt.format_prompt(
            co_tags=", ".join(co_tags),
            co_definitions=co_defs,
            topics=", ".join(topics),
            context=context,
            num_questions=num_questions
        ).to_string()

        try:
            response = self.llm.invoke(formatted_prompt)

            # If Gemini returns a dict already, just return it
            if isinstance(response, dict):
                logging.error(f"RAW LLM OUTPUT:\n{json.dumps(response, indent=2)}")
                return response

            # Otherwise, treat as text
            raw = response.strip()

            logging.error(f"RAW LLM OUTPUT:\n{raw}")

            clean = raw

            # Remove ```json fences if present
            if clean.startswith("```json"):
                clean = clean.removeprefix("```json").strip()
            if clean.startswith("```"):
                clean = clean.removeprefix("```").strip()
            if clean.endswith("```"):
                clean = clean.removesuffix("```").strip()

            logging.error(f"CLEANED OUTPUT:\n{clean}")

            return json.loads(clean)
            

        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error: {e}")
            raise RuntimeError("AI returned invalid JSON.")
        except Exception as e:
            logging.error(f"Chain Execution Error: {e}")
            raise RuntimeError(f"Failed to generate MCQs: {e}")

def build_chain() -> MCQGeneratorChain:
    return MCQGeneratorChain()
