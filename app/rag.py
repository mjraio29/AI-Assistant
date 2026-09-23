"""
Optional retrieval-augmented generation. Disabled by default (RAG_ENABLED=false)
so the core assistant works with zero extra dependencies. Turn it on once you
want the assistant grounded in your own documents (notes, resume, docs, etc).

Uses chromadb's built-in embedding function so there's no separate embedding
API call to wire up -- good enough to start, swap for a hosted embedding
model later if retrieval quality needs to improve.
"""
from pathlib import Path

from app.config import settings

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError(
            "RAG is enabled but chromadb isn't installed. Run: pip install chromadb"
        ) from e

    Path(settings.rag_collection_dir).mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=settings.rag_collection_dir)
    _collection = _client.get_or_create_collection("assistant_docs")
    return _collection


def ingest_documents(directory: str) -> int:
    """Chunk and store every .txt/.md file in `directory`. Returns count added.
    Simple fixed-size chunking -- swap for a smarter splitter if documents
    have meaningful structure (headings, sections) worth preserving."""
    collection = _get_collection()
    chunk_size = 1000
    ids, docs, metadatas = [], [], []
    for path in Path(directory).rglob("*"):
        if path.suffix.lower() not in (".txt", ".md"):
            continue
        text = path.read_text(errors="ignore")
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size].strip()
            if not chunk:
                continue
            ids.append(f"{path.name}:{i}")
            docs.append(chunk)
            metadatas.append({"source": str(path)})
    if docs:
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
    return len(docs)


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Return the top_k most relevant chunks for `query`, each with its source."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(query_texts=[query], n_results=top_k or settings.rag_top_k)
    hits = []
    for doc, meta in zip(result["documents"][0], result["metadatas"][0]):
        hits.append({"text": doc, "source": meta.get("source", "unknown")})
    return hits
