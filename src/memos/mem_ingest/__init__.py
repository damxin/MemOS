"""
mem_ingest module - Ingest pipeline for MemOS.

Provides:
- Smart deduplication
- LLM-based judgment
- Semantic text chunking
- Ingest pipeline

Reference: Local Plugin src/ingest/
"""

# Types
from .types import (
    ProcessingStatus,
    ContentType,
    IngestMessage,
    IngestChunk,
    DedupResult,
    DedupCandidate,
    LLMJudgeResult,
    IngestResult,
    IngestConfig,
    IngestStats,
)

# Deduplication
from .dedup import (
    Deduplicator,
    cosine_similarity,
    hash_content,
    simple_dedup_check,
)

# LLM Judgment
from .llm_judge import (
    LLMJudge,
    SimpleJudge,
)

# Chunker
from .chunker import (
    TextChunker,
    ChunkKind,
    chunk_by_characters,
    chunk_by_paragraphs,
)

# Pipeline
from .pipeline import (
    IngestPipeline,
    IngestWorker,
)


__all__ = [
    # Types
    "ProcessingStatus",
    "ContentType",
    "IngestMessage",
    "IngestChunk",
    "DedupResult",
    "DedupCandidate",
    "LLMJudgeResult",
    "IngestResult",
    "IngestConfig",
    "IngestStats",
    # Deduplication
    "Deduplicator",
    "cosine_similarity",
    "hash_content",
    "simple_dedup_check",
    # LLM Judgment
    "LLMJudge",
    "SimpleJudge",
    # Chunker
    "TextChunker",
    "ChunkKind",
    "chunk_by_characters",
    "chunk_by_paragraphs",
    # Pipeline
    "IngestPipeline",
    "IngestWorker",
]
