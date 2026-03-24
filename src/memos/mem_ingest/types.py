"""
Types and data structures for the ingest module.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
from datetime import datetime


class ProcessingStatus(Enum):
    """Status of processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


class ContentType(Enum):
    """Type of content"""
    TECHNICAL = "technical"
    CONVERSATIONAL = "conversational"
    INFORMATIONAL = "informational"
    PROCEDURAL = "procedural"


@dataclass
class IngestMessage:
    """
    A message to be ingested.
    
    Represents a single unit of content to process.
    """
    id: str = ""
    owner: str = "agent:main"
    session_key: str = ""
    role: str = "user"  # 'user', 'assistant', 'system', 'tool'
    content: str = ""
    timestamp: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())
        if self.timestamp == 0:
            self.timestamp = datetime.now().timestamp() * 1000


@dataclass
class IngestChunk:
    """
    A processed chunk ready for storage.
    """
    id: str
    owner: str
    session_key: str
    role: str
    content: str
    embedding: List[float]
    kind: str = "paragraph"  # 'paragraph', 'code_block', 'error_stack', 'list', 'command'
    summary: str = ""
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0
    updated_at: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'owner': self.owner,
            'session_key': self.session_key,
            'role': self.role,
            'content': self.content,
            'embedding': self.embedding,
            'kind': self.kind,
            'summary': self.summary,
            'task_id': self.task_id,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class DedupResult:
    """Result of deduplication check"""
    is_duplicate: bool
    duplicate_id: Optional[str]
    decision: str  # 'new', 'duplicate', 'update'
    confidence: float


@dataclass
class DedupCandidate:
    """A candidate for deduplication"""
    chunk_id: str
    score: float
    content: str = ""
    embedding: Optional[List[float]] = None


@dataclass
class LLMJudgeResult:
    """Result of LLM judgment"""
    decision: str  # 'new', 'duplicate', 'update'
    confidence: float
    reasoning: str = ""


@dataclass
class IngestResult:
    """Result of processing a message"""
    status: ProcessingStatus
    chunks_created: int = 0
    duplicates_skipped: int = 0
    error: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class IngestConfig:
    """Configuration for the ingest pipeline"""
    # Chunking settings
    max_chunk_chars: int = 3000
    min_chunk_chars: int = 40
    embedding_max_chars: int = 1000
    
    # Deduplication settings
    dedup_threshold: float = 0.92
    dedup_top_n: int = 5
    use_llm_judgment: bool = True
    
    # Processing settings
    batch_size: int = 10
    max_workers: int = 4
    
    # Quality settings
    skip_trivial: bool = True
    skip_too_short: bool = True
    min_content_length: int = 50


@dataclass
class IngestStats:
    """Statistics for ingest operations"""
    messages_processed: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'messages_processed': self.messages_processed,
            'chunks_created': self.chunks_created,
            'chunks_updated': self.chunks_updated,
            'duplicates_skipped': self.duplicates_skipped,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }
