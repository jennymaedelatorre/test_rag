from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)
from core.gemini_llm import GeminiLLM


class MCQGeneratorChain:
    """Encapsulates the LLM and prompt logic for generating multiple-choice questions (MCQs)."""

    def __init__(self):
        # 🧠 System-level instruction for the LLM
        system_template = """
You are an expert exam question creator.
Your task is to generate multiple-choice questions (MCQs)
STRICTLY based on the provided study material.

Rules:
- Generate exactly {num_questions} MCQs.
- You **MUST** ensure that every question directly relates to one of the following topics: {topics}.
- **CRITICAL:** Ignore any facts, definitions, or sections in the 'Study Material' that are not explicitly relevant to the listed topics, even if those facts are physically present in the text chunks.
- Each question must have:
  - 4 answer options labeled (A), (B), (C), (D)
  - The correct answer marked clearly with an asterisk (*) after it.
- Keep all questions concise, clear, and relevant to the topic.
- If you cannot find the answer, clearly say:
  "No valid question could be created for this topic."
"""
        
        user_template = """
Topics: {topics}
Number of Questions: {num_questions}

Study Material:
{context}
"""
        
        # Create prompt templates
        system_prompt = SystemMessagePromptTemplate.from_template(system_template)
        user_prompt = HumanMessagePromptTemplate.from_template(user_template)
        self.prompt = ChatPromptTemplate.from_messages([system_prompt, user_prompt])

        # ✅ Initialize Gemini model 
        self.llm = GeminiLLM()

    def run(self, topics, context, num_questions):
        """
        Builds a formatted prompt and calls the Gemini model to generate MCQs.
        Args:
            topics (list[str]): List of topics provided by the user.
            context (str): Extracted study material text.
            num_questions (int): Number of MCQs to generate.
        Returns:
            str: Generated MCQs text.
        """

        if not isinstance(topics, list):
            raise ValueError("Expected 'topics' to be a list of strings.")

        formatted_prompt = self.prompt.format_prompt(
            topics=", ".join(topics),
            context=context,
            num_questions=num_questions
        ).to_string()

        try:
            # ✅ Call Gemini safely (public method)
            response = self.llm.invoke(formatted_prompt)
            return response.strip() if isinstance(response, str) else str(response)
        except Exception as e:
            raise RuntimeError(f"Failed to generate MCQs: {e}")


def build_chain():
    """Factory function that returns a ready-to-use MCQ generator chain."""
    return MCQGeneratorChain()
