"""
vector_store.py — Enterprise Vector Store Service using Pinecone Serverless & Multi-Tenant RAG

Level 4 Implementation for Glitch HR AI:
- Official Pinecone Inference Embedding Engine: multilingual-e5-large (1024 dimensions).
- Asymmetric embedding generation:
    - input_type="passage" for document child chunks (ingestion).
    - input_type="query" for user queries (search).
- Strict multi-tenant isolation: namespace = company_id.
- Lean metadata schema (< 40KB) storing: parent_id, company_id, policy_code, access_role, chunk_index, doc_id.
- Vector Lifecycle Management: deterministic purge by policy_code / doc_id prior to re-upserting.
- Exponential backoff and jitter honoring Pinecone 100 req/s rate limits.
"""

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_pinecone_client = None
_pinecone_index = None


def get_pinecone_client():
    """Get or initialize singleton Pinecone client."""
    global _pinecone_client
    if _pinecone_client is not None:
        return _pinecone_client

    if not settings.is_pinecone_configured:
        logger.warning("PINECONE_API_KEY is not configured in backend/.env")
        return None

    try:
        from pinecone import Pinecone
        _pinecone_client = Pinecone(api_key=settings.PINECONE_API_KEY)
        logger.info("Pinecone client initialized successfully.")
        return _pinecone_client
    except Exception as exc:
        logger.error(f"Failed to initialize Pinecone client: {exc}")
        return None


def get_pinecone_index():
    """Get or connect to the configured Pinecone vector index."""
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index

    pc = get_pinecone_client()
    if not pc:
        return None

    try:
        index_name = settings.PINECONE_INDEX_NAME
        _pinecone_index = pc.Index(index_name)
        logger.info(f"Connected to Pinecone index: '{index_name}'")
        return _pinecone_index
    except Exception as exc:
        logger.error(f"Failed to connect to Pinecone index '{settings.PINECONE_INDEX_NAME}': {exc}")
        return None


async def _embed_with_backoff(pc, model_name: str, inputs: List[str], input_type: str, max_retries: int = 4) -> List[List[float]]:
    """Generate embeddings with exponential backoff and jitter for rate-limiting protection."""
    for attempt in range(max_retries):
        try:
            res = pc.inference.embed(
                model=model_name,
                inputs=inputs,
                parameters={"input_type": input_type, "truncate": "END"},
            )
            return [item.values for item in res]
        except Exception as exc:
            if attempt == max_retries - 1:
                logger.error(f"Pinecone embedding generation failed after {max_retries} attempts: {exc}")
                raise
            sleep_time = (0.2 * (2 ** attempt)) + random.uniform(0.05, 0.25)
            logger.warning(f"Pinecone embed rate-limit/transient error ({exc}), backing off for {sleep_time:.2f}s...")
            await asyncio.sleep(sleep_time)
    return []


def generate_embeddings(
    texts: List[str],
    input_type: str = "passage",
    batch_size: int = 96,
) -> List[List[float]]:
    """
    Synchronous embedding generator using multilingual-e5-large via Pinecone Inference.
    - Max batch size: 96 sequences.
    - input_type: 'passage' or 'query'.
    """
    pc = get_pinecone_client()
    if not pc or not texts:
        return []

    model_name = settings.PINECONE_EMBEDDING_MODEL
    all_vectors: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            res = pc.inference.embed(
                model=model_name,
                inputs=batch,
                parameters={"input_type": input_type, "truncate": "END"},
            )
            for item in res:
                all_vectors.append(item.values)
        except Exception as exc:
            logger.error(f"Pinecone Inference embedding generation failed: {exc}")
            raise

    return all_vectors


async def upsert_child_chunks_to_pinecone(
    company_id: str,
    policy_code: str,
    doc_id: str,
    child_chunks: List[Dict[str, Any]],
) -> int:
    """
    Level 4 Vector Store Ingestion:
    - Small-to-big child vector upsert under namespace=company_id.
    - Asymmetric input_type="passage" embedding generation.
    - Lean metadata schema (< 40KB): parent_id, company_id, policy_code, doc_id, access_role, chunk_index.
    - Deterministic lifecycle update: purges prior vectors for this policy_code / doc_id.
    """
    idx = get_pinecone_index()
    pc = get_pinecone_client()
    if not idx or not pc or not child_chunks:
        logger.warning(f"Pinecone upsert skipped for doc_id={doc_id} (not configured or empty chunks)")
        return 0

    try:
        # Step 1: Vector Lifecycle Management — purge prior vectors for this policy_code / doc_id
        try:
            delete_document_from_pinecone(company_id=company_id, doc_id=doc_id)
        except Exception as del_err:
            logger.debug(f"Pre-upsert purge notice: {del_err}")

        # Step 2: Batch embed child chunks (max batch size = 96)
        texts = [c["text"] for c in child_chunks]
        batch_size = 96
        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            emb_batch = await _embed_with_backoff(
                pc=pc,
                model_name=settings.PINECONE_EMBEDDING_MODEL,
                inputs=batch_texts,
                input_type="passage",
            )
            all_embeddings.extend(emb_batch)

        if len(all_embeddings) != len(child_chunks):
            logger.error(f"Mismatch: {len(child_chunks)} chunks vs {len(all_embeddings)} embeddings")
            return 0

        # Step 3: Construct lean vector records (< 40KB limit compliant)
        records = []
        for c_data, emb in zip(child_chunks, all_embeddings):
            records.append({
                "id": c_data["id"],
                "values": emb,
                "metadata": {
                    "parent_id": c_data["parent_id"],
                    "company_id": company_id,
                    "policy_code": policy_code,
                    "doc_id": doc_id,
                    "filename": c_data.get("filename", ""),
                    "chunk_index": c_data.get("chunk_index", 0),
                    "access_role": c_data.get("access_role", ["Employee"]),
                    "effective_date": c_data.get("effective_date", ""),
                    "text_snippet": c_data["text"][:300],  # Lean text preview
                },
            })

        # Step 4: Batch upsert into tenant namespace
        upsert_batch_size = 100
        total_upserted = 0
        for i in range(0, len(records), upsert_batch_size):
            batch = records[i : i + upsert_batch_size]
            idx.upsert(vectors=batch, namespace=company_id)
            total_upserted += len(batch)

        logger.info(
            f"Successfully upserted {total_upserted} child vectors for policy '{policy_code}' "
            f"(doc_id={doc_id}) into Pinecone namespace '{company_id}'"
        )
        return total_upserted

    except Exception as exc:
        logger.error(f"Failed to upsert child vectors to Pinecone: {exc}")
        return 0


def semantic_search_pinecone(
    company_id: str,
    query: str,
    top_k: int = 10,
    min_score: float = 0.50,
) -> List[Dict[str, Any]]:
    """
    Level 5: Asymmetric Dense Semantic Retrieval in Pinecone Serverless.
    - Generates query vector with input_type="query".
    - Evaluates Cosine Similarity strictly within namespace=company_id.
    - Returns matches with parent_id references for downstream MongoDB compaction.
    """
    idx = get_pinecone_index()
    if not idx:
        return []

    try:
        # Asymmetric query embedding
        q_vectors = generate_embeddings([query], input_type="query")
        if not q_vectors:
            return []
        q_vec = q_vectors[0]

        # Query Pinecone namespace
        results = idx.query(
            vector=q_vec,
            namespace=company_id,
            top_k=top_k,
            include_metadata=True,
        )

        matches = []
        for m in getattr(results, "matches", []):
            score = float(m.score or 0.0)
            if score >= min_score:
                meta = m.metadata or {}
                matches.append({
                    "id": m.id,
                    "score": score,
                    "parent_id": meta.get("parent_id", ""),
                    "policy_code": meta.get("policy_code", ""),
                    "source": meta.get("filename", "Policy Document"),
                    "text_snippet": meta.get("text_snippet", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "access_role": meta.get("access_role", ["Employee"]),
                })

        logger.info(
            f"Pinecone dense search returned {len(matches)} matches (top score: "
            f"{matches[0]['score'] if matches else 0:.4f}) for namespace={company_id}"
        )
        return matches

    except Exception as exc:
        logger.error(f"Pinecone semantic search error: {exc}")
        return []


def delete_document_from_pinecone(company_id: str, doc_id: str, chunk_count: int = 500) -> None:
    """Deterministic soft-delete/purge of document vectors from tenant namespace."""
    idx = get_pinecone_index()
    if not idx:
        return

    try:
        # Delete by chunk ID range (child_doc_id_0..N and doc_id_0..N)
        ids_to_delete = (
            [f"child_{doc_id}_{i}" for i in range(chunk_count)] +
            [f"{doc_id}_{i}" for i in range(chunk_count)]
        )
        idx.delete(ids=ids_to_delete, namespace=company_id)
        logger.info(f"Deleted vector chunks for doc_id={doc_id} from Pinecone (namespace={company_id})")
    except Exception as exc:
        logger.warning(f"Error deleting vectors from Pinecone for doc_id={doc_id}: {exc}")


def upsert_document_chunks_to_pinecone(
    company_id: str,
    doc_id: str,
    filename: str,
    chunks: List[str],
) -> int:
    """Legacy helper for backward compatibility."""
    child_records = [
        {
            "id": f"child_{doc_id}_{idx}",
            "parent_id": f"parent_{doc_id}_0",
            "text": chunk,
            "filename": filename,
            "chunk_index": idx,
        }
        for idx, chunk in enumerate(chunks)
    ]
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Schedule or run synchronously
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                upsert_child_chunks_to_pinecone(company_id, f"POL-{doc_id}", doc_id, child_records)
            ).result()
    else:
        return asyncio.run(
            upsert_child_chunks_to_pinecone(company_id, f"POL-{doc_id}", doc_id, child_records)
        )
