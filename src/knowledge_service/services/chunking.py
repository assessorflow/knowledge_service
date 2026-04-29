"""Text chunking service — production-ready using LangChain RecursiveCharacterTextSplitter.

Uses hierarchical splitting (headers → paragraphs → sentences → characters)
with chunk overlap for better context preservation at chunk boundaries.
"""

from __future__ import annotations

import hashlib

from langchain_text_splitters import RecursiveCharacterTextSplitter

from knowledge_service import config

# Separators ordered by strength — strongest boundaries split first
_SEPARATORS = [
    "\n## ",  # Markdown H2 headers
    "\n### ",  # Markdown H3 headers
    "\n#### ",  # Markdown H4 headers
    "\n\n",  # Paragraph boundaries
    "\n",  # Line breaks
    ". ",  # Sentence boundaries
    "? ",
    "! ",
    "; ",
    ", ",
    " ",  # Word boundaries (last resort)
]

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_TARGET_SIZE,
    chunk_overlap=100,
    separators=_SEPARATORS,
    length_function=len,
    strip_whitespace=True,
)


def split_text_into_chunks(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    """Split text into semantically meaningful chunks with overlap.

    Uses LangChain RecursiveCharacterTextSplitter which:
    1. Tries to split on the strongest separator first (headers)
    2. Falls back to weaker separators (paragraphs → sentences → words)
    3. Adds overlap between adjacent chunks for context preservation
    """
    if not text or not text.strip():
        return []

    if chunk_size or chunk_overlap:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size or config.CHUNK_TARGET_SIZE,
            chunk_overlap=chunk_overlap or 100,
            separators=_SEPARATORS,
            length_function=len,
            strip_whitespace=True,
        )
        return splitter.split_text(text)

    return _splitter.split_text(text)


def compute_content_hash(content: str) -> str:
    """SHA-256 hash of normalized chunk content for deduplication."""
    import re

    normalized = re.sub(r"\s+", " ", content).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_file_hash(content: str) -> str:
    """SHA-256 hash of entire file content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
