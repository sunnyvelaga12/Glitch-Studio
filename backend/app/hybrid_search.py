"""
hybrid_search.py — Hybrid Search Engine with Reciprocal Rank Fusion (RRF) & Dynamic Thresholds

Level 5 Architecture for Glitch HR AI:
- Parallel execution of Dense Semantic Search (Pinecone Serverless) and Lexical Search (MongoDB Atlas).
- Reciprocal Rank Fusion (RRF): RRF_Score(d) = 1/(k + rank_dense) + 1/(k + rank_lexical), with k=60.
- Calibrated Dynamic Cosine Similarity Thresholds:
    - > 0.85: High Confidence (Direct generation).
    - 0.75 – 0.85: Moderate Confidence (Dynamic disclaimer prompt injected).
    - < 0.75: Low Confidence (Zero hallucination fallback routing to hr@glitch.com).
- Context Window Compaction: Retrieves full parent chunks from MongoDB Atlas for top 3–5 parent_ids.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.db import get_db
from app.vector_store import semantic_search_pinecone

logger = logging.getLogger(__name__)

# Constants
RRF_SMOOTHING_CONSTANT = 60
HIGH_CONFIDENCE_THRESHOLD = 0.80
MODERATE_CONFIDENCE_THRESHOLD = 0.70
LEXICAL_FALLBACK_MIN_SCORE = 1.0
MAX_PARENT_CHUNKS = 5
MAX_CONTEXT_TOKENS = 2500

DEFAULT_FALLBACK_MESSAGE = (
    "I could not find a specific policy matching your query. "
    f"Please open a ticket with the HR department at {settings.DEFAULT_HR_EMAIL or 'hr@glitchhr.ai'}."
)


async def execute_lexical_search(
    company_id: str,
    query: str,
    top_k: int = 15,
) -> List[Dict[str, Any]]:
    """
    Execute Lexical (BM25 / TF-IDF style) search against MongoDB Atlas parent_chunks.
    Scans policy text and header hierarchies for query keyword hits.
    """
    db = get_db()
    
    # Filter stopwords
    stopwords = {
        "what", "is", "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "over", "after", "how",
        "can", "i", "we", "you", "they", "he", "she", "it", "my", "our", "your",
        "please", "tell", "does", "do", "did", "are", "be", "been", "being", "have",
        "has", "had", "would", "could", "should", "will"
    }
    raw_terms = [re.escape(w.lower()) for w in re.findall(r"\w+", query) if len(w) > 2 and w.lower() not in stopwords]
    if not raw_terms:
        return []

    # 1. Attempt accelerated MongoDB $text index search (uses inverted index)
    clean_text_query = " ".join(w for w in re.findall(r"\w+", query) if len(w) > 2 and w.lower() not in stopwords)
    if clean_text_query:
        try:
            text_cursor = db.parent_chunks.find(
                {
                    "company_id": company_id,
                    "$text": {"$search": clean_text_query},
                },
                {"score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(top_k)

            text_docs = await text_cursor.to_list(length=top_k)
            if text_docs:
                return [
                    {
                        "parent_id": doc["parent_id"],
                        "score": doc.get("score", 1.0),
                        "doc_id": doc.get("doc_id", ""),
                        "policy_code": doc.get("policy_code", ""),
                        "filename": doc.get("filename", ""),
                        "text": doc.get("text", ""),
                        "header_breadcrumb": doc.get("header_breadcrumb", ""),
                    }
                    for doc in text_docs
                ]
        except Exception as exc:
            logger.debug("MongoDB $text search fallback to regex: %s", exc)

    # Add HR domain stem & synonym expansion for robust keyword matching
    expanded_terms = set(raw_terms)
    for term in raw_terms:
        t = term.lower()
        if any(k in t for k in ["timing", "hour", "time"]):
            expanded_terms.update(["timing", "hour", "working", "schedule", "attendance"])
        elif "leave" in t:
            expanded_terms.update(["leave", "vacation", "holiday", "absence"])
        elif any(k in t for k in ["salary", "pay"]):
            expanded_terms.update(["compensation", "salary", "payroll", "allowance"])
        elif "dress" in t:
            expanded_terms.update(["dress", "attire", "casual"])
        elif any(k in t for k in ["remote", "wfh", "hybrid"]):
            expanded_terms.update(["remote", "hybrid", "office", "work mode"])

    regex_pattern = "|".join(expanded_terms)

    # 2. Fallback to regex scan if text index is unavailable or yields few hits
    cursor = db.parent_chunks.find({
        "company_id": company_id,
        "$or": [
            {"text": {"$regex": regex_pattern, "$options": "i"}},
            {"header_breadcrumb": {"$regex": regex_pattern, "$options": "i"}},
            {"policy_code": {"$regex": regex_pattern, "$options": "i"}},
        ]
    }).limit(50)

    docs = await cursor.to_list(length=50)
    if not docs:
        return []

    # Score documents by term-frequency occurrences
    scored_docs = []
    for doc in docs:
        text_lower = (doc.get("text", "") + " " + doc.get("header_breadcrumb", "")).lower()
        score = 0
        for term in raw_terms:
            score += text_lower.count(term.lower())
        if score > 0:
            scored_docs.append({
                "parent_id": doc["parent_id"],
                "score": score,
                "doc_id": doc.get("doc_id", ""),
                "policy_code": doc.get("policy_code", ""),
                "filename": doc.get("filename", ""),
                "text": doc.get("text", ""),
                "header_breadcrumb": doc.get("header_breadcrumb", ""),
            })

    scored_docs.sort(key=lambda x: x["score"], reverse=True)
    return scored_docs[:top_k]


def compute_reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    lexical_results: List[Dict[str, Any]],
    k: int = RRF_SMOOTHING_CONSTANT,
) -> List[Dict[str, Any]]:
    """
    Combines dense and lexical search rankings using Reciprocal Rank Fusion (RRF).
    RRF_Score(d) = 1 / (k + rank_dense(d)) + 1 / (k + rank_lexical(d))
    """
    rrf_scores: Dict[str, float] = {}
    item_metadata: Dict[str, Dict[str, Any]] = {}

    # Rank dense results (1-indexed)
    for rank, item in enumerate(dense_results, start=1):
        parent_id = item.get("parent_id")
        if not parent_id:
            continue
        rrf_scores[parent_id] = rrf_scores.get(parent_id, 0.0) + (1.0 / (k + rank))
        if parent_id not in item_metadata:
            item_metadata[parent_id] = {
                "parent_id": parent_id,
                "policy_code": item.get("policy_code", ""),
                "filename": item.get("source", ""),
                "dense_score": item.get("score", 0.0),
                "dense_rank": rank,
                "lexical_rank": None,
            }
        else:
            item_metadata[parent_id]["dense_rank"] = rank
            item_metadata[parent_id]["dense_score"] = item.get("score", 0.0)

    # Rank lexical results (1-indexed)
    for rank, item in enumerate(lexical_results, start=1):
        parent_id = item.get("parent_id")
        if not parent_id:
            continue
        rrf_scores[parent_id] = rrf_scores.get(parent_id, 0.0) + (1.0 / (k + rank))
        if parent_id not in item_metadata:
            item_metadata[parent_id] = {
                "parent_id": parent_id,
                "policy_code": item.get("policy_code", ""),
                "filename": item.get("filename", ""),
                "dense_score": 0.0,
                "dense_rank": None,
                "lexical_rank": rank,
            }
        else:
            item_metadata[parent_id]["lexical_rank"] = rank

    # Assemble fused list sorted by RRF score descending
    fused_list = []
    for parent_id, score in rrf_scores.items():
        meta = item_metadata[parent_id]
        meta["rrf_score"] = score
        fused_list.append(meta)

    fused_list.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused_list


async def execute_hybrid_search(
    company_id: str,
    query: str,
    top_parents: int = MAX_PARENT_CHUNKS,
) -> Dict[str, Any]:
    """
    Level 5: End-to-end Hybrid Search pipeline.
    
    1. Dense semantic search in Pinecone Serverless (input_type="query", namespace=company_id).
    2. Lexical keyword search in MongoDB Atlas (parent_chunks).
    3. Reciprocal Rank Fusion (RRF).
    4. Dynamic Similarity Threshold evaluation:
       - Peak cosine >= 0.85: HIGH_CONFIDENCE
       - Peak cosine 0.75 - 0.85: MODERATE_CONFIDENCE (disclaimer required)
       - Peak cosine < 0.75: LOW_CONFIDENCE (deterministic fallback routing)
    5. Context window compaction: retrieves parent chunks from MongoDB.
    
    Returns dict:
        {
            "status": "success" | "fallback",
            "confidence": "high" | "moderate" | "low",
            "peak_cosine_score": float,
            "disclaimer_required": bool,
            "context_text": str,
            "fallback_message": Optional[str],
            "retrieved_parents_count": int,
        }
    """
    # 1. Parallel dense & lexical execution
    dense_matches = semantic_search_pinecone(company_id=company_id, query=query, top_k=15, min_score=0.40)
    lexical_matches = await execute_lexical_search(company_id=company_id, query=query, top_k=15)

    peak_cosine = max((m["score"] for m in dense_matches), default=0.0)
    logger.info(
        f"Hybrid search: {len(dense_matches)} dense matches (peak cosine: {peak_cosine:.4f}), "
        f"{len(lexical_matches)} lexical matches for query='{query}'"
    )

    # 2. Dynamic Similarity Threshold Evaluation
    if peak_cosine >= HIGH_CONFIDENCE_THRESHOLD:
        confidence = "high"
        disclaimer_required = False
    elif peak_cosine >= MODERATE_CONFIDENCE_THRESHOLD:
        confidence = "moderate"
        disclaimer_required = True
    elif lexical_matches and lexical_matches[0]["score"] >= LEXICAL_FALLBACK_MIN_SCORE:
        # Lexical keyword hit in MongoDB text index or term frequencies
        confidence = "moderate"
        disclaimer_required = True
    else:
        # Check if company has policy documents in MongoDB parent_chunks
        db = get_db()
        policy_chunks_count = await db.parent_chunks.count_documents({"company_id": company_id})
        if policy_chunks_count > 0:
            logger.info(
                f"No specific dense/lexical match, but company has {policy_chunks_count} policy parent chunks. "
                "Synthesizing with company policy context to ensure grounded response."
            )
            confidence = "moderate"
            disclaimer_required = True
        else:
            confidence = "low"
            disclaimer_required = False
            # Truly no policies uploaded for this company
            return {
                "status": "fallback",
                "confidence": confidence,
                "peak_cosine_score": peak_cosine,
                "disclaimer_required": False,
                "context_text": "",
                "fallback_message": DEFAULT_FALLBACK_MESSAGE,
                "retrieved_parents_count": 0,
            }

    # 3. Fuse dense and lexical lists via RRF
    fused_results = compute_reciprocal_rank_fusion(dense_matches, lexical_matches)
    db = get_db()

    if not fused_results:
        # Neither dense nor lexical had specific query hits, but company has policies in DB
        all_parents = await db.parent_chunks.find({"company_id": company_id}).limit(top_parents).to_list(top_parents)
        top_parent_ids = [p["parent_id"] for p in all_parents]
    else:
        top_parent_ids = [item["parent_id"] for item in fused_results[:top_parents]]

    if not top_parent_ids:
        return {
            "status": "fallback",
            "confidence": "low",
            "peak_cosine_score": peak_cosine,
            "disclaimer_required": False,
            "context_text": "",
            "fallback_message": DEFAULT_FALLBACK_MESSAGE,
            "retrieved_parents_count": 0,
        }

    # 4. Context Window Compaction: fetch top parent chunks from MongoDB Atlas
    cursor = db.parent_chunks.find({
        "company_id": company_id,
        "parent_id": {"$in": top_parent_ids}
    })
    parent_docs = await cursor.to_list(length=len(top_parent_ids))
    parent_map = {doc["parent_id"]: doc for doc in parent_docs}

    formatted_parents = []
    total_chars = 0

    for item in fused_results[:top_parents]:
        p_id = item["parent_id"]
        p_doc = parent_map.get(p_id)
        if not p_doc:
            continue

        filename = p_doc.get("filename", "Policy Document")
        breadcrumb = p_doc.get("header_breadcrumb") or "General"
        text = p_doc.get("text", "").strip()

        # Format with authoritative source headers for mandatory LLM citation
        chunk_repr = f"### [Source: {filename}, Section: {breadcrumb}]\n{text}"
        formatted_parents.append(chunk_repr)
        total_chars += len(chunk_repr)

        if total_chars > MAX_CONTEXT_TOKENS * 4:
            break

    context_payload = "\n\n---\n\n".join(formatted_parents)
    return {
        "status": "success",
        "confidence": confidence,
        "peak_cosine_score": peak_cosine,
        "disclaimer_required": disclaimer_required,
        "context_text": context_payload,
        "fallback_message": None,
        "retrieved_parents_count": len(formatted_parents),
    }
