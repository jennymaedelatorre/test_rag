import google.generativeai as genai
from langchain.llms.base import LLM

class GeminiLLM(LLM):
    """Custom LangChain wrapper for the Gemini API."""
    

    def _call(self, prompt: str, stop=None) -> str:
        """Call the Gemini 2.0 Flash model."""
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text

    @property
    def _identifying_params(self):
        return {"model_name": "gemini-2.0-flash"}

    @property
    def _llm_type(self):
        return "gemini"