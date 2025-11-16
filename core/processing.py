import os
import hashlib
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS

def calculate_file_hash(file_path, block_size=65536):
    """Compute SHA256 hash of a file in chunks."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                hasher.update(block)
        return hasher.hexdigest()
    except FileNotFoundError:
        return None

def load_and_chunk(file_path, chunk_size=500, overlap=90, document_id=None):
    """Load PDF, split into chunks, attach optional document ID."""
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    
    if document_id:
        for doc in documents:
            doc.metadata['document_uuid'] = str(document_id)  # Add custom ID

    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    docs = text_splitter.split_documents(documents)  # Split text into smaller chunks
    return docs

def get_or_create_vector_store(index_path, docs=None):
    """Load existing FAISS index or create a new one with embeddings."""
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    if os.path.exists(index_path):
        print(f"Cache hit: Loading FAISS index from {index_path}")
        db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        status_message = "FAISS INDEX RELOADED from cache."
    else:
        if docs is None:
            raise ValueError("No documents provided to build FAISS index!")
        print(f"Cache miss: Creating new FAISS index at {index_path}")
        db = FAISS.from_documents(docs, embeddings)
        db.save_local(index_path) 
        status_message = "FAISS INDEX CREATED and saved to cache."

    return db.as_retriever(), status_message  # Return retriever for queries
