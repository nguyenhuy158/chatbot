"""RAG (Retrieval-Augmented Generation) module."""
from app.rag.citation import Citation
from app.rag.ingestion import ingest_file, reindex_document
from app.rag.retriever import RagResult, retrieve
from app.rag.vector_store import RetrievedChunk, vector_store

__all__ = [
    "Citation",
    "RagResult",
    "RetrievedChunk",
    "ingest_file",
    "reindex_document",
    "retrieve",
    "vector_store",
]
