"""
Task storage layer.

Provides abstract interface for task persistence, with implementations
for SQLite and PostgreSQL backends.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
import json
import uuid

from .base import Task, TaskChunk, TaskStatus, ChunkRef
from .types import TaskQuery, TaskStats


class BaseTaskStorage(ABC):
    """Abstract base class for task storage"""
    
    @abstractmethod
    def create_task(self, task: Task) -> Task:
        """Create a new task"""
        pass
    
    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        pass
    
    @abstractmethod
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
        """Update a task"""
        pass
    
    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        pass
    
    @abstractmethod
    def get_tasks(self, query: TaskQuery) -> List[Task]:
        """Query tasks"""
        pass
    
    @abstractmethod
    def get_active_tasks(self, owner: str) -> List[Task]:
        """Get all active tasks for an owner"""
        pass
    
    @abstractmethod
    def get_active_task(self, session_key: str, owner: str) -> Optional[Task]:
        """Get active task for a session"""
        pass
    
    @abstractmethod
    def set_chunk_task_id(self, chunk_id: str, task_id: str) -> None:
        """Assign a chunk to a task"""
        pass
    
    @abstractmethod
    def get_chunks_by_task(self, task_id: str) -> List[TaskChunk]:
        """Get all chunks for a task"""
        pass
    
    @abstractmethod
    def get_unassigned_chunks(self, session_key: str) -> List[TaskChunk]:
        """Get chunks not assigned to any task"""
        pass
    
    @abstractmethod
    def get_task_stats(self, owner: Optional[str] = None) -> TaskStats:
        """Get task statistics"""
        pass


class SQLiteTaskStorage(BaseTaskStorage):
    """
    SQLite implementation of task storage.
    
    Uses the existing SqliteStore from the Local Plugin.
    """
    
    def __init__(self, store):
        """
        Args:
            store: SqliteStore instance from memos-local-openclaw
        """
        self.store = store
    
    def create_task(self, task: Task) -> Task:
        """Create a new task"""
        task_dict = task.to_dict()
        # Convert status enum to string
        if hasattr(task.status, 'value'):
            task_dict['status'] = task.status.value
        self.store.insert_task(task_dict)
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        task_dict = self.store.get_task(task_id)
        if not task_dict:
            return None
        return Task.from_dict(task_dict)
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
        """Update a task"""
        # Add updated_at timestamp
        updates['updated_at'] = datetime.now().timestamp() * 1000
        self.store.update_task(task_id, updates)
        return self.get_task(task_id)
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        return self.store.delete_task(task_id)
    
    def get_tasks(self, query: TaskQuery) -> List[Task]:
        """Query tasks"""
        filters = {}
        if query.session_key:
            filters['session_key'] = query.session_key
        if query.owner:
            filters['owner'] = query.owner
        if query.status:
            filters['status'] = query.status
        
        task_dicts = self.store.get_tasks(filters, limit=query.limit, offset=query.offset)
        return [Task.from_dict(t) for t in task_dicts]
    
    def get_active_tasks(self, owner: str) -> List[Task]:
        """Get all active tasks for an owner"""
        task_dicts = self.store.get_tasks({
            'owner': owner,
            'status': TaskStatus.ACTIVE.value
        })
        return [Task.from_dict(t) for t in task_dicts]
    
    def get_active_task(self, session_key: str, owner: str) -> Optional[Task]:
        """Get active task for a session"""
        task_dict = self.store.getActiveTask(session_key, owner)
        if not task_dict:
            return None
        return Task.from_dict(task_dict)
    
    def set_chunk_task_id(self, chunk_id: str, task_id: str) -> None:
        """Assign a chunk to a task"""
        self.store.setChunkTaskId(chunk_id, task_id)
    
    def get_chunks_by_task(self, task_id: str) -> List[TaskChunk]:
        """Get all chunks for a task"""
        chunk_dicts = self.store.getChunksByTask(task_id)
        return [TaskChunk.from_dict(c) for c in chunk_dicts]
    
    def get_unassigned_chunks(self, session_key: str) -> List[TaskChunk]:
        """Get chunks not assigned to any task"""
        chunk_dicts = self.store.getUnassignedChunks(session_key)
        return [TaskChunk.from_dict(c) for c in chunk_dicts]
    
    def get_task_stats(self, owner: Optional[str] = None) -> TaskStats:
        """Get task statistics"""
        filters = {'owner': owner} if owner else {}
        
        all_tasks = self.store.get_tasks(filters, limit=10000)
        active_tasks = [t for t in all_tasks if t.get('status') == TaskStatus.ACTIVE.value]
        completed_tasks = [t for t in all_tasks if t.get('status') == TaskStatus.COMPLETED.value]
        skipped_tasks = [t for t in all_tasks if t.get('status') == TaskStatus.SKIPPED.value]
        
        # Calculate average duration for completed tasks
        durations = []
        for t in completed_tasks:
            started = t.get('started_at', 0)
            ended = t.get('ended_at')
            if started and ended:
                durations.append(ended - started)
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Count total chunks
        total_chunks = sum(
            len(self.store.getChunksByTask(t['id']))
            for t in all_tasks
        )
        
        return TaskStats(
            total_tasks=len(all_tasks),
            active_tasks=len(active_tasks),
            completed_tasks=len(completed_tasks),
            skipped_tasks=len(skipped_tasks),
            avg_duration_ms=avg_duration,
            total_chunks=total_chunks
        )


class InMemoryTaskStorage(BaseTaskStorage):
    """
    In-memory task storage for testing and lightweight usage.
    """
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.chunks: Dict[str, TaskChunk] = {}
        self.chunk_to_task: Dict[str, str] = {}
    
    def create_task(self, task: Task) -> Task:
        self.tasks[task.id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        task_dict = task.to_dict()
        task_dict.update(updates)
        updated_task = Task.from_dict(task_dict)
        self.tasks[task_id] = updated_task
        return updated_task
    
    def delete_task(self, task_id: str) -> bool:
        if task_id not in self.tasks:
            return False
        del self.tasks[task_id]
        # Unassign chunks
        for chunk_id, t_id in list(self.chunk_to_task.items()):
            if t_id == task_id:
                del self.chunk_to_task[chunk_id]
        return True
    
    def get_tasks(self, query: TaskQuery) -> List[Task]:
        results = list(self.tasks.values())
        
        if query.owner:
            results = [t for t in results if t.owner == query.owner]
        if query.session_key:
            results = [t for t in results if t.session_key == query.session_key]
        if query.status:
            status = TaskStatus(query.status)
            results = [t for t in results if t.status == status]
        
        return results[query.offset:query.offset + query.limit]
    
    def get_active_tasks(self, owner: str) -> List[Task]:
        return [
            t for t in self.tasks.values()
            if t.owner == owner and t.status == TaskStatus.ACTIVE
        ]
    
    def get_active_task(self, session_key: str, owner: str) -> Optional[Task]:
        for task in self.tasks.values():
            if (task.session_key == session_key and 
                task.owner == owner and 
                task.status == TaskStatus.ACTIVE):
                return task
        return None
    
    def set_chunk_task_id(self, chunk_id: str, task_id: str) -> None:
        self.chunk_to_task[chunk_id] = task_id
        if chunk_id in self.chunks:
            self.chunks[chunk_id].task_id = task_id
    
    def get_chunks_by_task(self, task_id: str) -> List[TaskChunk]:
        return [
            c for c in self.chunks.values()
            if self.chunk_to_task.get(c.id) == task_id
        ]
    
    def get_unassigned_chunks(self, session_key: str) -> List[TaskChunk]:
        return [
            c for c in self.chunks.values()
            if c.session_key == session_key and c.id not in self.chunk_to_task
        ]
    
    def get_task_stats(self, owner: Optional[str] = None) -> TaskStats:
        tasks = list(self.tasks.values())
        if owner:
            tasks = [t for t in tasks if t.owner == owner]
        
        active = [t for t in tasks if t.status == TaskStatus.ACTIVE]
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        skipped = [t for t in tasks if t.status == TaskStatus.SKIPPED]
        
        durations = [t.duration_ms() for t in completed if t.ended_at]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        total_chunks = sum(len(self.get_chunks_by_task(t.id)) for t in tasks)
        
        return TaskStats(
            total_tasks=len(tasks),
            active_tasks=len(active),
            completed_tasks=len(completed),
            skipped_tasks=len(skipped),
            avg_duration_ms=avg_duration,
            total_chunks=total_chunks
        )
    
    # Additional methods for testing
    def add_chunk(self, chunk: TaskChunk) -> None:
        """Add a chunk to storage"""
        self.chunks[chunk.id] = chunk
    
    def get_chunk(self, chunk_id: str) -> Optional[TaskChunk]:
        """Get a chunk by ID"""
        return self.chunks.get(chunk_id)


def create_task_storage(
    backend: str = "memory",
    **kwargs
) -> BaseTaskStorage:
    """
    Factory function to create task storage.
    
    Args:
        backend: 'memory', 'sqlite', or 'postgres'
        **kwargs: Backend-specific arguments
    
    Returns:
        BaseTaskStorage implementation
    """
    if backend == "memory":
        return InMemoryTaskStorage()
    elif backend == "sqlite":
        return SQLiteTaskStorage(kwargs.get('store'))
    elif backend == "postgres":
        # Would need PostgreSQL implementation
        raise NotImplementedError("PostgreSQL task storage not yet implemented")
    else:
        raise ValueError(f"Unknown backend: {backend}")
