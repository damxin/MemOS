"""
Hub Server - Central server for team memory sharing.

Provides:
- Memory sharing across OpenClaw instances
- User management
- API endpoints for recall/add operations
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

from ..mem_task.base import Task, TaskStatus
from ..mem_skill.base import Skill, SkillStatus
from .user_manager import UserManager
from .auth import AuthHandler, TokenManager


@dataclass
class HubConfig:
    """Hub server configuration"""
    host: str = "0.0.0.0"
    port: int = 18799
    max_clients: int = 100
    client_timeout: int = 3600  # seconds
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])


@dataclass
class ClientConnection:
    """Represents a connected client"""
    client_id: str
    user_id: str
    connected_at: float
    last_seen: float
    is_hub: bool = False  # Is this client a hub or agent?


class HubServer:
    """
    Central Hub for team memory sharing.
    
    Manages:
    - Client connections
    - Shared memories
    - Skill publishing/discovery
    - Memory synchronization
    """
    
    def __init__(self, config: Optional[HubConfig] = None):
        self.config = config or HubConfig()
        self.user_manager = UserManager()
        self.auth_handler = AuthHandler(self.user_manager)
        self.token_manager = TokenManager()
        
        self._clients: Dict[str, ClientConnection] = {}
        self._shared_memories: Dict[str, Any] = {}
        self._published_skills: Dict[str, Skill] = {}
        
        self._running = False
    
    # === Client Management ===
    
    def register_client(self, client_id: str, user_id: str, is_hub: bool = False) -> str:
        """Register a new client connection"""
        conn = ClientConnection(
            client_id=client_id,
            user_id=user_id,
            connected_at=datetime.now().timestamp(),
            last_seen=datetime.now().timestamp(),
            is_hub=is_hub
        )
        self._clients[client_id] = conn
        return client_id
    
    def unregister_client(self, client_id: str) -> bool:
        """Unregister a client"""
        if client_id in self._clients:
            del self._clients[client_id]
            return True
        return False
    
    def get_clients(self, user_id: Optional[str] = None) -> List[ClientConnection]:
        """Get all connected clients, optionally filtered by user"""
        if user_id:
            return [c for c in self._clients.values() if c.user_id == user_id]
        return list(self._clients.values())
    
    def update_client_heartbeat(self, client_id: str) -> bool:
        """Update client's last seen timestamp"""
        if client_id in self._clients:
            self._clients[client_id].last_seen = datetime.now().timestamp()
            return True
        return False
    
    # === Memory Sharing ===
    
    def share_memory(
        self,
        client_id: str,
        memory_id: str,
        memory_data: Dict[str, Any],
        visibility: str = "team"
    ) -> bool:
        """
        Share a memory to the hub.
        
        Args:
            client_id: ID of sharing client
            memory_id: Unique memory ID
            memory_data: Memory content and metadata
            visibility: 'team', 'public', 'private'
        
        Returns:
            True if shared successfully
        """
        if client_id not in self._clients:
            return False
        
        client = self._clients[client_id]
        
        self._shared_memories[memory_id] = {
            'id': memory_id,
            'owner': client.user_id,
            'data': memory_data,
            'visibility': visibility,
            'shared_at': datetime.now().timestamp(),
            'shared_by': client_id
        }
        
        return True
    
    def get_shared_memories(
        self,
        client_id: str,
        visibility: Optional[str] = None,
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get shared memories.
        
        Filters:
        - visibility: Filter by visibility level
        - owner: Filter by owner
        - tags: Filter by tags
        """
        if client_id not in self._clients:
            return []
        
        client = self._clients[client_id]
        results = []
        
        for memory in self._shared_memories.values():
            # Check visibility
            if visibility and memory['visibility'] != visibility:
                continue
            
            # Check owner filter
            if owner and memory['owner'] != owner:
                continue
            
            # Check tags
            if tags:
                memory_tags = memory['data'].get('tags', [])
                if not any(t in memory_tags for t in tags):
                    continue
            
            # Check permissions
            if memory['visibility'] == 'private' and memory['owner'] != client.user_id:
                continue
            
            results.append(memory)
        
        return results
    
    def delete_shared_memory(self, client_id: str, memory_id: str) -> bool:
        """Delete a shared memory"""
        if client_id not in self._clients:
            return False
        
        client = self._clients[client_id]
        memory = self._shared_memories.get(memory_id)
        
        if not memory:
            return False
        
        # Only owner can delete
        if memory['owner'] != client.user_id:
            return False
        
        del self._shared_memories[memory_id]
        return True
    
    # === Skill Publishing ===
    
    def publish_skill(
        self,
        client_id: str,
        skill: Skill,
        visibility: str = "team"
    ) -> bool:
        """Publish a skill to the hub"""
        if client_id not in self._clients:
            return False
        
        skill.visibility = visibility
        self._published_skills[skill.id] = skill
        return True
    
    def discover_skills(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        owner: Optional[str] = None,
        visibility: Optional[str] = "team"
    ) -> List[Skill]:
        """Discover published skills"""
        results = []
        
        for skill in self._published_skills.values():
            if skill.visibility != visibility and visibility != "all":
                continue
            
            if owner and skill.owner != owner:
                continue
            
            if tags and not any(t in skill.tags for t in tags):
                continue
            
            results.append(skill)
        
        return results
    
    def install_skill(
        self,
        client_id: str,
        skill_id: str
    ) -> Optional[Skill]:
        """Install a skill from the hub"""
        if client_id not in self._clients:
            return None
        
        return self._published_skills.get(skill_id)
    
    # === Memory Sync ===
    
    def sync_memories(
        self,
        client_id: str,
        since: Optional[float] = None
    ) -> Dict[str, Any]:
        """Get memories modified since timestamp for sync"""
        if client_id not in self._clients:
            return {'memories': [], 'tasks': [], 'skills': []}
        
        client = self._clients[client_id]
        memories = []
        tasks = []
        
        for memory in self._shared_memories.values():
            if memory['owner'] == client.user_id:
                if since is None or memory.get('shared_at', 0) > since:
                    memories.append(memory)
        
        return {
            'memories': memories,
            'tasks': tasks,
            'sync_time': datetime.now().timestamp()
        }
    
    # === API Handlers ===
    
    async def handle_recall(
        self,
        client_id: str,
        query: str,
        conversation_id: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Handle recall request from a client.
        
        Returns relevant shared memories.
        """
        if client_id not in self._clients:
            return {'hits': [], 'error': 'Client not registered'}
        
        # Search shared memories
        memories = self.get_shared_memories(
            client_id=client_id,
            visibility='team'
        )
        
        # Simple keyword matching for now
        hits = []
        query_lower = query.lower()
        
        for memory in memories:
            content = memory['data'].get('content', '')
            if query_lower in content.lower():
                hits.append({
                    'id': memory['id'],
                    'content': content,
                    'score': 1.0,
                    'metadata': memory['data'].get('metadata', {})
                })
        
        return {'hits': hits[:limit]}
    
    async def handle_add(
        self,
        client_id: str,
        memory_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle add memory request from a client.
        """
        if client_id not in self._clients:
            return {'success': False, 'error': 'Client not registered'}
        
        import uuid
        memory_id = str(uuid.uuid4())
        
        success = self.share_memory(
            client_id=client_id,
            memory_id=memory_id,
            memory_data=memory_data,
            visibility='team'
        )
        
        return {
            'success': success,
            'memory_id': memory_id if success else None
        }
    
    # === Server Lifecycle ===
    
    def start(self):
        """Start the hub server"""
        self._running = True
        # In a real implementation, this would start an async server
    
    def stop(self):
        """Stop the hub server"""
        self._running = False
        self._clients.clear()
    
    def is_running(self) -> bool:
        """Check if server is running"""
        return self._running
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hub statistics"""
        return {
            'clients': len(self._clients),
            'shared_memories': len(self._shared_memories),
            'published_skills': len(self._published_skills),
            'uptime': datetime.now().timestamp(),
            'running': self._running
        }


# === Factory ===

def create_hub(config: Optional[Dict[str, Any]] = None) -> HubServer:
    """Create a HubServer instance"""
    hub_config = HubConfig(**config) if config else HubConfig()
    return HubServer(hub_config)
