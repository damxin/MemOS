"""
mem_task module - Task management for MemOS.

Provides task detection, boundary handling, and summarization.

Reference: Local Plugin src/ingest/task-processor.ts
"""

# Core data structures
from .base import (
    Task,
    TaskChunk,
    ChunkRef,
    TaskStatus,
)

# Type definitions
from .types import (
    SkipReason,
    TaskSummaryResult,
    TopicJudgmentResult,
    TaskProcessorConfig,
    TaskQuery,
    TaskStats,
    TaskEvent,
    TaskEventData,
)

# Storage layer
from .storage import (
    BaseTaskStorage,
    SQLiteTaskStorage,
    InMemoryTaskStorage,
    create_task_storage,
)

# Summarizer
from .summarizer import (
    TaskSummarizer,
    SkipChecker,
    build_conversation_text,
    parse_title_from_summary,
    extract_title_fallback,
)

# Factory
from .factory import TaskProcessor

__all__ = [
    # Base
    "Task",
    "TaskChunk",
    "ChunkRef",
    "TaskStatus",
    # Types
    "SkipReason",
    "TaskSummaryResult",
    "TopicJudgmentResult",
    "TaskProcessorConfig",
    "TaskQuery",
    "TaskStats",
    "TaskEvent",
    "TaskEventData",
    # Storage
    "BaseTaskStorage",
    "SQLiteTaskStorage",
    "InMemoryTaskStorage",
    "create_task_storage",
    # Summarizer
    "TaskSummarizer",
    "SkipChecker",
    "build_conversation_text",
    "parse_title_from_summary",
    "extract_title_fallback",
    # Factory
    "TaskProcessor",
]
