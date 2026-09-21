"""
rag_chunking.py — Document Hierarchy-Aware & Parent-Document (Small-to-Big) Chunking Pipeline

Level 2 & Level 3 RAG Implementation for Glitch HR AI:
- Unicode NFKC normalization and administrative noise reduction.
- Document Hierarchy-Aware chunking preserving Markdown structural boundaries (#, ##, ###).
- Header context recursive inheritance into child chunks to prevent semantic drift.
- Decoupled Parent-Document Retrieval:
    - Parent chunks: 600–800 tokens (persisted in MongoDB Atlas for expansive LLM context).
    - Child chunks: 150–200 tokens with 15–20% token overlap (vectorized in Pinecone for dense search).
- Hard token boundary enforcement <= 510 tokens (multilingual-e5-large context window limit: 512).
"""

import logging
from pathlib import Path
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Target token parameters
MAX_TOKEN_CEILING = 510  # Hard limit for multilingual-e5-large
PARENT_TARGET_TOKENS = 700  # Parent chunk size target (600-800 tokens)
CHILD_TARGET_TOKENS = 180   # Child chunk size target (150-200 tokens)
CHILD_OVERLAP_TOKENS = 35   # ~18% overlap

# Tokenizer singleton cache
_tokenizer = None
_tokenizer_failed = False


def get_tokenizer():
    """Load and cache xlm-roberta-large / multilingual-e5-large tokenizer."""
    global _tokenizer, _tokenizer_failed
    if _tokenizer is not None:
        return _tokenizer
    if _tokenizer_failed:
        return None

    try:
        from transformers import AutoTokenizer
        try:
            _tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large", local_files_only=True)
        except Exception:
            _tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
        logger.info("Successfully loaded multilingual-e5-large tokenizer for boundary enforcement.")
        return _tokenizer
    except Exception as exc:
        logger.warning(f"Could not load AutoTokenizer from Hugging Face: {exc}. Using sub-word token counter fallback.")
        _tokenizer_failed = True
        return None


def count_tokens(text: str) -> int:
    """Accurately count tokens using E5 tokenizer or calibrated sub-word estimation."""
    if not text:
        return 0
    tok = get_tokenizer()
    if tok:
        try:
            return len(tok.encode(text, add_special_tokens=False))
        except Exception:
            pass
    # Fallback: multilingual sub-word tokenization heuristic (~3.5 chars per token for English/multilingual)
    words = text.split()
    return max(1, int(len(words) * 1.35))


# Precompiled regex patterns for high-throughput normalization
BOILERPLATE_COMBINED_REGEX = re.compile(
    r"(?i)(?:"
    r"\bconfidential\s*[-–—]\s*(?:internal\s*use\s*only|strictly\s*private)\b|"
    r"\bstrictly\s+private\s+and\s+confidential\b|"
    r"\bpage\s+\d+\s+of\s+\d+\b|"
    r"\bpage\s+\d+\b(?=\s*\n)|"
    r"\ball\s+rights\s+reserved\b|"
    r"\bcompany\s+confidential\b|"
    r"\[\s*confidential\s*\]"
    r")"
)
HR_RULE_REGEX = re.compile(r"[=_]{4,}")
BLANK_LINES_REGEX = re.compile(r"\n{3,}")


def clean_and_normalize_text(text: str) -> str:
    """
    Level 3: Noise reduction and Unicode normalization.
    - Applies Unicode Normalization Form KC (NFKC).
    - Strips administrative boilerplate (Confidentiality notices, page numbers, repetitive signatures).
    - Retains structural punctuation in bulleted lists and tables.
    """
    if not text:
        return ""

    # 1. Unicode NFKC Normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Targeted precompiled regex to remove administrative boilerplate in single pass
    text = BOILERPLATE_COMBINED_REGEX.sub("", text)

    # 3. Normalize horizontal rules and excessive blank lines
    text = HR_RULE_REGEX.sub("---", text)
    text = BLANK_LINES_REGEX.sub("\n\n", text)

    # 4. Standardize straight quotes and clean spacing
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _split_markdown_sections(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Split Markdown into hierarchical sections based on H1, H2, H3, H4 headers.
    Returns list of dicts with headers path and section content.
    """
    lines = markdown_text.split("\n")
    sections = []
    
    current_headers = {"h1": "", "h2": "", "h3": "", "h4": ""}
    current_content = []

    header_regex = re.compile(r"^(#{1,4})\s+(.+)$")

    def save_section():
        if current_content:
            raw_text = "\n".join(current_content).strip()
            if raw_text:
                hierarchy = [
                    current_headers[k] for k in ["h1", "h2", "h3", "h4"]
                    if current_headers[k]
                ]
                sections.append({
                    "headers": hierarchy,
                    "text": raw_text
                })

    for line in lines:
        match = header_regex.match(line.strip())
        if match:
            save_section()
            current_content = [line]
            level = len(match.group(1))
            title = match.group(2).strip()

            if level == 1:
                current_headers = {"h1": title, "h2": "", "h3": "", "h4": ""}
            elif level == 2:
                current_headers["h2"] = title
                current_headers["h3"] = ""
                current_headers["h4"] = ""
            elif level == 3:
                current_headers["h3"] = title
                current_headers["h4"] = ""
            elif level == 4:
                current_headers["h4"] = title
        else:
            current_content.append(line)

    save_section()
    return sections


def _subdivide_tokens(text: str, target_tokens: int, overlap_tokens: int) -> List[str]:
    """Subdivide a block of text into chunks by token boundaries with specified overlap."""
    tok = get_tokenizer()
    words = text.split()
    if not words:
        return []

    # If tokenizer is available, encode and slice token IDs directly
    if tok:
        try:
            token_ids = tok.encode(text, add_special_tokens=False)
            if len(token_ids) <= target_tokens:
                return [text]

            chunks = []
            step = max(1, target_tokens - overlap_tokens)
            for i in range(0, len(token_ids), step):
                chunk_ids = token_ids[i : i + target_tokens]
                if not chunk_ids:
                    break
                decoded = tok.decode(chunk_ids, skip_special_tokens=True).strip()
                if decoded:
                    chunks.append(decoded)
                if i + target_tokens >= len(token_ids):
                    break
            return chunks
        except Exception:
            pass

    # Heuristic word-based fallback
    approx_words_per_token = 0.75
    target_words = max(10, int(target_tokens * approx_words_per_token))
    overlap_words = max(2, int(overlap_tokens * approx_words_per_token))
    step = max(1, target_words - overlap_words)

    chunks = []
    for i in range(0, len(words), step):
        chunk_words = words[i : i + target_words]
        if not chunk_words:
            break
        chunks.append(" ".join(chunk_words))
        if i + target_words >= len(words):
            break
    return chunks


def process_small_to_big_chunking(
    markdown_text: str,
    company_id: str,
    doc_id: str,
    policy_code: str,
    filename: str,
    access_role: Optional[List[str]] = None,
    effective_date: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Core Small-to-Big (Parent-Document Retrieval) Chunking Algorithm.
    
    1. Cleans and normalizes text (NFKC + regex boilerplate purge).
    2. Builds document hierarchy (H1, H2, H3).
    3. Forms cohesive Parent Chunks (600–800 tokens) stored in MongoDB Atlas.
    4. Generates Child Chunks (150–200 tokens, 15–20% overlap) linked by parent_id.
    5. Recursively prepends parent header hierarchy to child chunks.
    6. Strictly verifies that each child chunk token count <= 510 tokens.
    
    Returns:
        (parent_chunks, child_chunks)
    """
    clean_text = clean_and_normalize_text(markdown_text)
    sections = _split_markdown_sections(clean_text)
    if not sections:
        sections = [{"headers": [Path(filename).stem], "text": clean_text}]

    now_iso = datetime.now(timezone.utc).isoformat()
    eff_date = effective_date or now_iso
    roles = access_role or ["Employee", "Manager", "HR Admin"]

    parent_chunks: List[Dict[str, Any]] = []
    child_chunks: List[Dict[str, Any]] = []

    global_child_index = 0

    for s_idx, sec in enumerate(sections):
        headers = sec["headers"]
        section_text = sec["text"]
        header_breadcrumb = " > ".join(headers) if headers else Path(filename).stem

        # Split section into parent chunks (600–800 tokens)
        parent_texts = _subdivide_tokens(section_text, PARENT_TARGET_TOKENS, overlap_tokens=60)

        for p_idx, p_text in enumerate(parent_texts):
            parent_id = f"parent_{doc_id}_{s_idx}_{p_idx}"
            p_token_count = count_tokens(p_text)

            # Assemble parent record (Stored in MongoDB Atlas)
            parent_chunk_doc = {
                "_id": parent_id,
                "parent_id": parent_id,
                "doc_id": doc_id,
                "company_id": company_id,
                "policy_code": policy_code,
                "filename": filename,
                "header_hierarchy": headers,
                "header_breadcrumb": header_breadcrumb,
                "text": p_text,
                "token_count": p_token_count,
                "effective_date": eff_date,
                "access_role": roles,
                "createdAt": now_iso,
            }
            parent_chunks.append(parent_chunk_doc)

            # Subdivide parent chunk into small child chunks (150–200 tokens)
            sub_children = _subdivide_tokens(p_text, CHILD_TARGET_TOKENS, CHILD_OVERLAP_TOKENS)

            for c_text in sub_children:
                # Recursively prepend header hierarchy to preserve semantic context
                prefix = f"[{header_breadcrumb}]\n" if header_breadcrumb else ""
                full_child_text = f"{prefix}{c_text}".strip()

                # Level 3: Strict 510 Token Boundary Enforcement
                c_tokens = count_tokens(full_child_text)
                if c_tokens > MAX_TOKEN_CEILING:
                    # Truncate at word boundary to strictly stay <= 510 tokens
                    words = full_child_text.split()
                    while words and count_tokens(" ".join(words)) > MAX_TOKEN_CEILING:
                        words.pop()
                    full_child_text = " ".join(words)
                    c_tokens = count_tokens(full_child_text)

                child_id = f"child_{doc_id}_{global_child_index}"
                child_chunk_doc = {
                    "id": child_id,
                    "parent_id": parent_id,
                    "doc_id": doc_id,
                    "company_id": company_id,
                    "policy_code": policy_code,
                    "filename": filename,
                    "chunk_index": global_child_index,
                    "access_role": roles,
                    "effective_date": eff_date,
                    "text": full_child_text,
                    "token_count": c_tokens,
                }
                child_chunks.append(child_chunk_doc)
                global_child_index += 1

    logger.info(
        f"Chunking complete for {filename}: {len(parent_chunks)} parents (MongoDB) and "
        f"{len(child_chunks)} children (Pinecone). All child tokens <= {MAX_TOKEN_CEILING}."
    )
    return parent_chunks, child_chunks
