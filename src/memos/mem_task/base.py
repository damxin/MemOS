"""
Task data structures and base classes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TaskStatus(Enum):
    """Task status enumeration"""
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """
    Represents a unit of work or conversation topic.
    
    A Task is created when a conversation session starts or when
    the LLM judges that a new topic has begun. Tasks group related
    chunks together and are summarized when they end.
    """
    id: str
    session_key: str
    title: str = ""
    summary: str = ""
    status: TaskStatus = TaskStatus.ACTIVE
    owner: str = "agent:main"
    started_at: float = 0
    ended_at: Optional[float] = None
    updated_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
        if self.started_at == 0:
            self.started_at = datetime.now().timestamp() * 1000
        if self.updated_at == 0:
            self.updated_at = datetime.now().timestamp() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'session_key': self.session_key,
            'title': self.title,
            'summary': self.summary,
            'status': self.status.value,
            'owner': self.owner,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'updated_at': self.updated_at,
            **self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create from dictionary"""
        return cls(
            id=data['id'],
            session_key=data['session_key'],
            title=data.get('title', ''),
            summary=data.get('summary', ''),
            status=TaskStatus(data.get('status', 'active')),
            owner=data.get('owner', 'agent:main'),
            started_at=data.get('started_at', 0),
            ended_at=data.get('ended_at'),
            updated_at=data.get('updated_at', 0),
            metadata={k: v for k, v in data.items() 
                     if k not in ('id', 'session_key', 'title', 'summary', 
                                 'status', 'owner', 'started_at', 'ended_at', 'updated_at')}
        )
    
    def is_active(self) -> bool:
        """Check if task is active"""
        return self.status == TaskStatus.ACTIVE
    
    def is_completed(self) -> bool:
        """Check if task is completed"""
        return self.status == TaskStatus.COMPLETED
    
    def duration_ms(self) -> float:
        """Get task duration in milliseconds"""
        end = self.ended_at if self.ended_at else datetime.now().timestamp() * 1000
        return end - self.started_at
    
    def duration_minutes(self) -> float:
        """Get task duration in minutes"""
        return self.duration_ms() / (1000 * 60)


@dataclass
class ChunkRef:
    """Reference to a chunk within a task"""
    session_key: str
    chunk_id: str
    turn_id: str = ""
    seq: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_key': self.session_key,
            'chunk_id': self.chunk_id,
            'turn_id': self.turn_id,
            'seq': self.seq
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkRef':
        return cls(
            session_key=data.get('session_key', ''),
            chunk_id=data.get('chunk_id', ''),
            turn_id=data.get('turn_id', ''),
            seq=data.get('seq', 0)
        )


@dataclass
class TaskChunk:
    """
    A chunk associated with a task.
    
    Chunks are individual pieces of conversation (user/assistant/tool messages)
    that belong to a task.
    """
    id: str
    task_id: Optional[str] = None
    session_key: str = ""
    role: str = ""  # 'user', 'assistant', 'tool'
    content: str = ""
    summary: str = ""
    turn_id: str = ""
    seq: int = 0
    created_at: float = 0
    merge_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = datetime.now().timestamp() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'task_id': self.task_id,
            'session_key': self.session_key,
            'role': self.role,
            'content': self.content,
            'summary': self.summary,
            'turn_id': self.turn_id,
            'seq': self.seq,
            'created_at': self.created_at,
            'merge_count': self.merge_count,
            **self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskChunk':
        return cls(
            id=data['id'],
            task_id=data.get('task_id'),
            session_key=data.get('session_key', ''),
            role=data.get('role', ''),
            content=data.get('content', ''),
            summary=data.get('summary', ''),
            turn_id=data.get('turn_id', ''),
            seq=data.get('seq', 0),
            created_at=data.get('created_at', 0),
            merge_count=data.get('merge_count', 0),
            metadata={k: v for k, v in data.items()
                     if k not in ('id', 'task_id', 'session_key', 'role',
                                 'content', 'summary', 'turn_id', 'seq',
                                 'created_at', 'merge_count')}
        )
    
    def is_user_message(self) -> bool:
        """Check if this is a user message"""
        return self.role == 'user'
    
    def is_assistant_message(self) -> bool:
        """Check if this is an assistant message"""
        return self.role == 'assistant'
    
    def is_tool_message(self) -> bool:
        """Check if this is a tool message"""
        return self.role == 'tool'
