from dotenv import load_dotenv
import os
import google.generativeai as genai
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import RetrievalQA
from langchain.llms.base import LLM

# 1. Configure Gemini 
load_dotenv()
API_KEY = os.getenv("API_KEY")
genai.configure(api_key=API_KEY)

# --- Gemini Wrapper for LangChain ---
class GeminiLLM(LLM):
    def _call(self, prompt, stop=None):
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text

    @property
    def _identifying_params(self):
        return {"model_name": "gemini-2.0-flash"}

    @property
    def _llm_type(self):
        return "gemini"


# 2. Load & Chunk 
def load_and_chunk(file_path, chunk_size=500, overlap=90):
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    docs = text_splitter.split_documents(documents)
    return docs


# 3. Create or Load FAISS Index
def get_or_create_vector_store(index_path="faiss_index", docs=None):
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    if os.path.exists(index_path):
        print(" Loading existing FAISS index...")
        db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    else:
        if docs is None:
            raise ValueError("No documents provided to build FAISS index!")
        print(" Creating new FAISS index...")
        db = FAISS.from_documents(docs, embeddings)
        db.save_local(index_path)
    return db.as_retriever()


# 4. Define system + user prompts 
system_template = """
You are an expert exam question creator. 
Your task is to generate multiple-choice questions (MCQs)
STRICTLY based on the provided study material.

Each question must:
- Have 4 options (A, B, C, D)
- Mark the correct answer with an asterisk (*)
- Avoid numbering answers with asterisks unless it's the correct one
- Keep questions concise and relevant to the topic
"""
user_template = """
Topic: {question}

Study Material:
{context}
"""

system_prompt = SystemMessagePromptTemplate.from_template(system_template)
user_prompt = HumanMessagePromptTemplate.from_template(user_template)
prompt_template = ChatPromptTemplate.from_messages([system_prompt, user_prompt])


# 5. Build a RetrievalQA Chain using Gemini
def build_chain(retriever):
    llm = GeminiLLM() 
    chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt_template},
        return_source_documents=False
    )
    return chain


# 6. Main Program
if __name__ == "__main__":
    index_path = "faiss_index"

    docs = None
    if not os.path.exists(index_path):
        docs = load_and_chunk("data/sample.pdf")

    retriever = get_or_create_vector_store(index_path, docs)
    chain = build_chain(retriever)

    # Ask instructor for input
    topic = input("Enter the topic or concept for which you want to generate MCQs: ")
    num_questions = int(input("Enter the number of MCQs to generate: "))

    # Run the chain — retrieval + LLM + prompt happen automatically
    response = chain.invoke({"query": f"Generate {num_questions} MCQs about {topic}"})

    print("\n📘 Generated MCQs:\n")
    print(response["result"].strip())




