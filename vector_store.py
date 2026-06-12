"""
vector_store.py  ─  Week 3-4 Enhanced
In-memory FAISS vector store with:
  • Subject / chapter metadata tagging
  • Cross-document search for synthesis
  • Chapter-aware filtered retrieval
"""

import os
import numpy as np
import faiss
import google.generativeai as genai
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv(override=True)
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))

# ── In-memory stores ──────────────────────────────────────────────────────────
chunks_store   = []   # raw text of each chunk
metadata_store = []   # source, content_type, subject, chapter per chunk
faiss_index    = None

# ── Subject keyword map ───────────────────────────────────────────────────────
_SUBJECT_MAP = {
    "Computer Science": [
        "computer", "programming", "data structure", "algorithm", "dbms",
        "database", "operating system", "network", "software", "python",
        "java", "c++", "web", "compiler", "automata", "machine learning",
        "artificial intelligence", "cloud", "cybersecurity",
    ],
    "Mathematics": [
        "math", "calculus", "algebra", "statistics", "probability",
        "discrete", "linear", "differential", "integral", "matrix",
    ],
    "Physics": [
        "physics", "mechanics", "optics", "electro", "thermodynamics",
        "quantum", "wave", "relativity", "nuclear",
    ],
    "Chemistry": [
        "chemistry", "organic", "inorganic", "reaction", "compound",
        "periodic", "bond", "molecule",
    ],
    "Biology": [
        "biology", "bio", "anatomy", "genetics", "cell", "organism",
        "evolution", "ecosystem",
    ],
    "Economics": [
        "economics", "finance", "accounting", "micro", "macro", "market",
        "gdp", "inflation", "fiscal",
    ],
}


def _detect_subject(filename: str, text_sample: str = "") -> str:
    combined = (filename + " " + text_sample[:600]).lower()
    scores = {subj: 0 for subj in _SUBJECT_MAP}
    for subj, keywords in _SUBJECT_MAP.items():
        for kw in keywords:
            if kw in combined:
                scores[subj] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"


# ── Embedding ─────────────────────────────────────────────────────────────────
def embed_text(text: str, api_key: str = None) -> list:
    raw_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
    keys = [k.strip() for k in raw_key.split(",") if k.strip()]
    if not keys:
        raise Exception("No Google API Key configured.")
        
    last_err = None
    for key in keys:
        try:
            genai.configure(api_key=key)
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text,
            )
            return result["embedding"]
        except Exception as e:
            err_msg = str(e).lower()
            if any(word in err_msg for word in ["quota", "exhausted", "429", "rate_limit", "resource_exhausted", "limit"]):
                last_err = e
                print(f"Embedding API Key starting with '{key[:8]}' exhausted. Attempting next key...")
                continue
            else:
                raise e
    if last_err:
        raise last_err
    raise Exception("All API keys in the pool were exhausted during embedding.")


# ── Indexing ──────────────────────────────────────────────────────────────────
def add_documents(processed_docs: list, api_key: str = None) -> None:
    """Embed all chunks from processed document dicts and add to FAISS."""
    global faiss_index

    new_chunks, new_meta = [], []

    for doc in processed_docs:
        subject = doc.get("subject") or _detect_subject(
            doc["filename"], doc.get("raw_text", "")[:600]
        )

        for chunk in doc["chunks"]:
            if isinstance(chunk, dict):
                chunk_text = chunk.get("text", "")
                chapter    = chunk.get("chapter", "General")
            else:
                chunk_text = str(chunk)
                chapter    = "General"

            if not chunk_text.strip():
                continue

            new_chunks.append(chunk_text)
            new_meta.append({
                "source":       doc["filename"],
                "content_type": doc["content_type"],
                "subject":      subject,
                "chapter":      chapter,
            })

    if not new_chunks:
        print("No chunks to add!")
        return

    print(f"Embedding {len(new_chunks)} chunks…")
    vectors = [embed_text(c, api_key=api_key) for c in new_chunks]
    matrix  = np.array(vectors, dtype="float32")

    if faiss_index is None:
        faiss_index = faiss.IndexFlatL2(matrix.shape[1])

    faiss_index.add(matrix)
    chunks_store.extend(new_chunks)
    metadata_store.extend(new_meta)
    print(f"✅ Total chunks indexed: {len(chunks_store)}")


# ── Standard search ───────────────────────────────────────────────────────────
def search(query: str, k: int = 5,
           subject: str = None, chapter: str = None, api_key: str = None) -> list:
    """Semantic search with optional subject/chapter filtering."""
    if faiss_index is None or not chunks_store:
        return []

    qv       = np.array([embed_text(query, api_key=api_key)], dtype="float32")
    fetch_k  = min(k * 5 if (subject or chapter) else k, len(chunks_store))
    distances, indices = faiss_index.search(qv, fetch_k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        meta = metadata_store[idx]
        if subject and meta.get("subject") != subject:
            continue
        if chapter and meta.get("chapter") != chapter:
            continue
        results.append({
            "text":         chunks_store[idx],
            "source":       meta["source"],
            "content_type": meta["content_type"],
            "subject":      meta.get("subject", "General"),
            "chapter":      meta.get("chapter", "General"),
            "score":        float(dist),
        })
        if len(results) >= k:
            break

    return results


# ── Cross-document search (for synthesis) ────────────────────────────────────
def search_cross_document(query: str, k_per_doc: int = 2, api_key: str = None) -> list:
    """
    Retrieve top-k chunks from EACH indexed document independently.
    Used for cross-document synthesis to ensure all sources are represented.
    """
    if faiss_index is None or not chunks_store:
        return []

    qv     = np.array([embed_text(query, api_key=api_key)], dtype="float32")
    all_k  = min(60, len(chunks_store))
    distances, indices = faiss_index.search(qv, all_k)

    per_doc: dict[str, list] = defaultdict(list)
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        src = metadata_store[idx]["source"]
        if len(per_doc[src]) < k_per_doc:
            per_doc[src].append({
                "text":         chunks_store[idx],
                "source":       src,
                "content_type": metadata_store[idx]["content_type"],
                "subject":      metadata_store[idx].get("subject", "General"),
                "chapter":      metadata_store[idx].get("chapter", "General"),
                "score":        float(dist),
            })

    return [chunk for chunks in per_doc.values() for chunk in chunks]


# ── Sample chunks for KG building ────────────────────────────────────────────
def get_all_chunks_sample(max_per_doc: int = 6) -> list:
    """Return a representative sample of chunks from each document."""
    if not chunks_store:
        return []
    per_doc: dict[str, list] = defaultdict(list)
    for i, meta in enumerate(metadata_store):
        src = meta["source"]
        if len(per_doc[src]) < max_per_doc:
            per_doc[src].append(chunks_store[i])
    return [c for chunks in per_doc.values() for c in chunks]


# ── Stats ─────────────────────────────────────────────────────────────────────
def get_stats() -> dict:
    sources  = list({m["source"]               for m in metadata_store})
    subjects = sorted({m.get("subject", "General") for m in metadata_store})
    cbs: dict[str, set] = defaultdict(set)
    for m in metadata_store:
        cbs[m.get("subject", "General")].add(m.get("chapter", "General"))
    return {
        "documents":           len(sources),
        "chunks":              len(chunks_store),
        "sources":             sources,
        "subjects":            subjects,
        "chapters_by_subject": {k: sorted(v) for k, v in cbs.items()},
    }


# ── User-specific Vector Store management ─────────────────────────────────────
def load_user_vector_store(chunks: list, metadata: list, faiss_index_filepath: str | None) -> None:
    """Load user's vector store into memory from the provided lists and index path."""
    global chunks_store, metadata_store, faiss_index
    chunks_store = chunks
    metadata_store = metadata
    if faiss_index_filepath and os.path.exists(faiss_index_filepath):
        try:
            faiss_index = faiss.read_index(faiss_index_filepath)
        except Exception as e:
            print(f"Error reading FAISS index: {e}")
            faiss_index = None
    else:
        faiss_index = None

def clear_vector_store() -> None:
    """Resets the vector store in-memory variables."""
    global chunks_store, metadata_store, faiss_index
    chunks_store = []
    metadata_store = []
    faiss_index = None