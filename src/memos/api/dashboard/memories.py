"""
Dashboard API - Memories endpoints.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime


class MemoriesAPI:
    """
    API for memory operations.
    
    Endpoints:
    - GET /api/memories - List memories
    - GET /api/memories/:id - Get memory
    - POST /api/memories - Create memory
    - PUT /api/memories/:id - Update memory
    - DELETE /api/memories/:id - Delete memory
    """
    
    def __init__(self, storage):
        self.storage = storage
    
    def list_memories(
        self,
        owner: Optional[str] = None,
        session_key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List memories with filters"""
        memories = self.storage.get_memories(
            owner=owner,
            session_key=session_key,
            tags=tags,
            limit=limit,
            offset=offset
        )
        return [self._format_memory(m) for m in memories]
    
    def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory"""
        memory = self.storage.get_memory(memory_id)
        if not memory:
            return None
        return self._format_memory(memory)
    
    def create_memory(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new memory"""
        memory_id = self.storage.insert_memory(data)
        memory = self.storage.get_memory(memory_id)
        return self._format_memory(memory)
    
    def update_memory(
        self,
        memory_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a memory"""
        self.storage.update_memory(memory_id, updates)
        memory = self.storage.get_memory(memory_id)
        if not memory:
            return None
        return self._format_memory(memory)
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory"""
        return self.storage.delete_memory(memory_id)
    
    def search_memories(
        self,
        query: str,
        owner: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search memories by content"""
        memories = self.storage.search_memories(
            query=query,
            owner=owner,
            limit=limit
        )
        return [self._format_memory(m) for m in memories]
    
    def _format_memory(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Format memory for API response"""
        return {
            'id': memory.get('id'),
            'owner': memory.get('owner'),
            'session_key': memory.get('session_key'),
            'role': memory.get('role'),
            'content': memory.get('content'),
            'embedding': memory.get('embedding'),
            'kind': memory.get('kind', 'paragraph'),
            'summary': memory.get('summary'),
            'task_id': memory.get('task_id'),
            'tags': memory.get('tags', []),
            'metadata': memory.get('metadata', {}),
            'created_at': memory.get('created_at'),
            'updated_at': memory.get('updated_at')
        }
