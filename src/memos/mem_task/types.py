"""
Task-specific type definitions.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum


class SkipReason(Enum):
    """Reasons why a task summary might be skipped"""
    NO_CHUNKS = "no_chunks"
    TOO_FEW_CHUNKS = "too_few_chunks"
    TOO_FEW_CONVERSATION_TURNS = "too_few_conversation_turns"
    NO_USER_MESSAGES = "no_user_messages"
    CONTENT_TOO_SHORT = "content_too_short"
    TRIVIAL_USER_CONTENT = "trivial_user_content"
    TRIVIAL_CONVERSATION = "trivial_conversation"
    DOMINATED_BY_TOOL_RESULTS = "dominated_by_tool_results"
    HIGH_CONTENT_REPETITION = "high_content_repetition"
    NONE = None


@dataclass
class TaskSummaryResult:
    """Result of task summarization"""
    title: str
    summary: str
    skipped: bool = False
    skip_reason: Optional[SkipReason] = None
    skip_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'summary': self.summary,
            'skipped': self.skipped,
            'skip_reason': self.skip_reason.value if self.skip_reason else None,
            'skip_message': self.skip_message
        }


@dataclass
class TopicJudgmentResult:
    """Result of LLM topic judgment"""
    is_new_topic: Optional[bool]  # None = fallback (same topic)
    confidence: float = 1.0
    reason: str = ""
    
    @property
    def is_same_topic(self) -> bool:
        """Returns True if same topic (None counts as same)"""
        return self.is_new_topic is False or self.is_new_topic is None
    
    @property
    def is_new_topic_detected(self) -> bool:
        """Returns True if new topic detected"""
        return self.is_new_topic is True


@dataclass
class TaskProcessorConfig:
    """Configuration for TaskProcessor"""
    # Time gap threshold in ms (default 2 hours)
    task_idle_timeout_ms: float = 2 * 60 * 60 * 1000
    
    # Trivial patterns to detect test/simple content
    trivial_patterns: List[str] = field(default_factory=lambda: [
        r"^(test|testing|hello|hi|hey|ok|okay|yes|no|yeah|nope|sure|thanks|thank you|thx|ping|pong|哈哈|好的|嗯|是的|不是|谢谢|你好|测试)\s*[.!?。！？]*$",
        r"^(aaa+|bbb+|xxx+|zzz+|123+|asdf+|qwer+|haha+|lol+|hmm+)\s*$",
        r"^[\s\p{P}\p{S}]*$",
    ])
    
    # Summary skip thresholds
    min_chunks_for_summary: int = 4
    min_conversation_turns: int = 2
    min_content_length: int = 200
    min_content_length_cjk: int = 80
    
    # Tool content threshold
    max_tool_ratio: float = 0.7
    max_tool_count_with_min_user: int = 1
    
    # Repetition threshold
    min_unique_ratio: float = 0.4


@dataclass
class TaskQuery:
    """Query parameters for task search"""
    session_key: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None  # 'active', 'completed', 'skipped'
    limit: int = 100
    offset: int = 0


@dataclass 
class TaskStats:
    """Statistics about tasks"""
    total_tasks: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    skipped_tasks: int = 0
    avg_duration_ms: float = 0
    total_chunks: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_tasks': self.total_tasks,
            'active_tasks': self.active_tasks,
            'completed_tasks': self.completed_tasks,
            'skipped_tasks': self.skipped_tasks,
            'avg_duration_ms': self.avg_duration_ms,
            'total_chunks': self.total_chunks
        }


class TaskEvent(Enum):
    """Task lifecycle events"""
    CREATED = "task_created"
    UPDATED = "task_updated"
    COMPLETED = "task_completed"
    SKIPPED = "task_skipped"


@dataclass
class TaskEventData:
    """Data associated with a task event"""
    event: TaskEvent
    task_id: str
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
