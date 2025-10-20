import os
import hashlib
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS

def calculate_file_hash(file_path, block_size=65536):
    """
    Calculates the SHA256 hash of a file's content in chunks 
    to handle large files efficiently.
    """
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                hasher.update(block)
        return hasher.hexdigest()
    except FileNotFoundError:
        return None

def load_and_chunk(file_path, chunk_size=500, overlap=90, document_id=None): # 👈 Accept the ID
    """Loads a PDF and splits it into smaller documents, attaching a custom ID."""
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    
    # 🟢 Inject the unique ID into the metadata of all initial documents
    if document_id:
        for doc in documents:
            # Set the 'document_uuid' field in the LangChain Document metadata
            doc.metadata['document_uuid'] = str(document_id) # 👈 Inject the UUID

    text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    # The splitter will automatically carry over the custom 'document_uuid' to all final chunks
    docs = text_splitter.split_documents(documents)
    return docs

def get_or_create_vector_store(index_path, docs=None):
    """
    Loads an existing FAISS index from 'index_path' or creates a new one.
    
    index_path is now based on the file's hash, enabling content-based caching.
    """
    # Use the same embedding model consistently
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    if os.path.exists(index_path):
        status_message = "FAISS INDEX RELOADED from cache."
        print(f"🟢 CACHE HIT: Loading existing FAISS index from: {index_path}")
        # The allow_dangerous_deserialization=True flag is necessary for loading FAISS indices
        db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        
    else:
        if docs is None:
            raise ValueError("❌ No documents provided to build FAISS index!")
        status_message = "FAISS INDEX CREATED and saved to cache."
        print(f"🟡 CACHE MISS: Creating NEW FAISS index at: {index_path}")
        
        db = FAISS.from_documents(docs, embeddings)
        
        # Save the new index for future use
        db.save_local(index_path) 

    # Return a retriever object for the chain
    return db.as_retriever(), status_message 