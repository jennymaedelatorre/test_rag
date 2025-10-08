# =======================
# 📘 MCQ Generator using Gemini + LangChain + FAISS
# =======================

# --- Import necessary libraries ---
from dotenv import load_dotenv            # Loads environment variables from a .env file
import os                                # Used for file path handling and environment variable access
import google.generativeai as genai       # Google Gemini (Generative AI) SDK
from langchain.document_loaders import PyPDFLoader  # To read PDF files as documents
from langchain.text_splitter import CharacterTextSplitter  # For chunking text into manageable parts
from langchain.embeddings import HuggingFaceEmbeddings     # For generating embeddings using HuggingFace models
from langchain.vectorstores import FAISS                   # FAISS for fast vector-based search/retrieval
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)                                                           # For creating prompt templates
from langchain.chains import RetrievalQA                    # Retrieval-augmented QA chain
from langchain.llms.base import LLM                         # Base class for custom LLM wrappers


# =======================
# 1️⃣ Configure Gemini API
# =======================

load_dotenv()                        # Load environment variables from the .env file
API_KEY = os.getenv("API_KEY")       # Fetch your Gemini API key from environment variables
genai.configure(api_key=API_KEY)     # Initialize Gemini client with the API key


# =======================
# 2️⃣ Define a Gemini Wrapper for LangChain
# =======================

# LangChain expects any LLM to follow a consistent interface (methods, properties)
# This custom class wraps Google Gemini inside that interface.

class GeminiLLM(LLM):
    # The main function LangChain calls to get the model’s output
    def _call(self, prompt, stop=None):
        model = genai.GenerativeModel("gemini-2.0-flash")  # Load Gemini model
        response = model.generate_content(prompt)           # Generate text from the input prompt
        return response.text                                # Return the generated text

    # Return identifying parameters (metadata about the LLM)
    @property
    def _identifying_params(self):
        return {"model_name": "gemini-2.0-flash"}

    # Return the LLM type (used internally by LangChain)
    @property
    def _llm_type(self):
        return "gemini"


# =======================
# 3️⃣ Function: Load and Chunk PDF Documents
# =======================

def load_and_chunk(file_path, chunk_size=500, overlap=90):
    """
    Loads a PDF file, extracts its text, and splits it into smaller overlapping chunks.
    This helps the model handle large documents efficiently while maintaining context.
    """
    loader = PyPDFLoader(file_path)                    # Load the PDF file
    documents = loader.load()                          # Extract text content into Document objects
    text_splitter = CharacterTextSplitter(             # Initialize text splitter
        chunk_size=chunk_size,                         # Maximum characters per chunk
        chunk_overlap=overlap                          # Overlapping region between consecutive chunks
    )
    docs = text_splitter.split_documents(documents)    # Split text into chunks
    return docs                                        # Return list of chunked documents


# =======================
# 4️⃣ Function: Create or Load FAISS Vector Store
# =======================

def get_or_create_vector_store(index_path="faiss_index", docs=None):
    """
    Loads an existing FAISS index (if present) or creates a new one from the given documents.
    The FAISS index enables efficient semantic search across the text chunks.
    """
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")  # Load embedding model

    # If FAISS index already exists, load it from disk
    if os.path.exists(index_path):
        print("🟢 Loading existing FAISS index...")
        db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    else:
        # Otherwise, create a new index from documents
        if docs is None:
            raise ValueError("❌ No documents provided to build FAISS index!")
        print("🟡 Creating new FAISS index...")
        db = FAISS.from_documents(docs, embeddings)  # Create FAISS index from document embeddings
        db.save_local(index_path)                    # Save the index for reuse

    # Return a retriever object that can fetch relevant chunks for a given query
    return db.as_retriever()


# =======================
# 5️⃣ Define Prompt Templates
# =======================

# The "system" prompt defines the role and rules for the AI assistant.
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

# The "user" prompt will include the topic and retrieved study material.
user_template = """
Topic: {question}

Study Material:
{context}
"""

# Combine both templates into a structured conversation format
system_prompt = SystemMessagePromptTemplate.from_template(system_template)
user_prompt = HumanMessagePromptTemplate.from_template(user_template)
prompt_template = ChatPromptTemplate.from_messages([system_prompt, user_prompt])


# =======================
# 6️⃣ Function: Build the RetrievalQA Chain
# =======================

def build_chain(retriever):
    """
    Combines the Gemini LLM with the retriever and the prompt template
    to form a RetrievalQA pipeline — a system that retrieves relevant
    information and generates context-aware answers.
    """
    llm = GeminiLLM()  # Use our custom Gemini wrapper
    chain = RetrievalQA.from_chain_type(
        llm=llm,                                 # The language model
        retriever=retriever,                     # The FAISS retriever
        chain_type="stuff",                      # Stuff = combine retrieved docs into one prompt
        chain_type_kwargs={"prompt": prompt_template},  # Use our custom prompt template
        return_source_documents=False            # We only want the generated answer, not the retrieved docs
    )
    return chain


# =======================
# 7️⃣ Main Program Execution
# =======================

if __name__ == "__main__":
    index_path = "faiss_index"       # Define where the FAISS index will be stored

    docs = None                      # Initialize document variable
    if not os.path.exists(index_path):
        # If no FAISS index exists, load and chunk the PDF first
        docs = load_and_chunk("data/sample.pdf")

    # Load or create the vector store (retriever)
    retriever = get_or_create_vector_store(index_path, docs)

    # Build the question-generation chain
    chain = build_chain(retriever)

    # Ask user for topic and number of questions
    topic = input("🎯 Enter the topic or concept for which you want to generate MCQs: ")
    num_questions = int(input("🔢 Enter the number of MCQs to generate: "))

    # Generate MCQs using Retrieval + LLM chain
    response = chain.invoke({"query": f"Generate {num_questions} MCQs about {topic}"})

    # Print final output
    print("\n📘 Generated MCQs:\n")
    print(response["result"].strip())
