"""
Hub Client SDK for connecting agents to the Hub.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class HubClientConfig:
    """Configuration for Hub client"""
    hub_url: str = "http://localhost:18799"
    client_id: str = ""
    user_id: str = ""
    token: str = ""
    timeout: int = 30
    retry_count: int = 3


class HubClient:
    """
    Client for connecting to Hub server.
    
    Provides:
    - Memory sharing
    - Memory recall
    - Skill discovery
    - Skill installation
    - Team memory access
    """
    
    def __init__(self, config: HubClientConfig):
        self.config = config
        self._connected = False
    
    def connect(self) -> bool:
        """Connect to Hub"""
        # In a real implementation, this would make an HTTP request
        # For now, just mark as connected
        self._connected = True
        return True
    
    def disconnect(self) -> bool:
        """Disconnect from Hub"""
        self._connected = False
        return True
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
    
    # === Memory Operations ===
    
    def share_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        visibility: str = "team"
    ) -> Optional[str]:
        """
        Share a memory to the Hub.
        
        Returns memory_id if successful.
        """
        if not self._connected:
            return None
        
        memory_data = {
            'content': content,
            'metadata': metadata or {},
            'visibility': visibility
        }
        
        # In real implementation, would POST to hub
        # For now, return a placeholder ID
        import uuid
        return str(uuid.uuid4())
    
    def recall(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recall relevant memories from Hub.
        
        Returns list of memory hits.
        """
        if not self._connected:
            return []
        
        # In real implementation, would POST to hub /recall endpoint
        # For now, return empty
        return []
    
    def get_shared_memories(
        self,
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get shared memories with filters"""
        if not self._connected:
            return []
        
        # In real implementation, would GET from hub
        return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a shared memory"""
        if not self._connected:
            return False
        
        # Would DELETE to hub
        return True
    
    # === Skill Operations ===
    
    def publish_skill(
        self,
        skill_content: str,
        name: str,
        description: str,
        tags: List[str],
        visibility: str = "team"
    ) -> Optional[str]:
        """
        Publish a skill to the Hub.
        
        Returns skill_id if successful.
        """
        if not self._connected:
            return None
        
        import uuid
        skill_id = str(uuid.uuid4())
        
        # Would POST to hub
        return skill_id
    
    def discover_skills(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Discover skills in Hub"""
        if not self._connected:
            return []
        
        # Would GET from hub
        return []
    
    def install_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Install a skill from Hub"""
        if not self._connected:
            return None
        
        # Would GET and install
        return None
    
    # === Sync Operations ===
    
    def sync(self, since: Optional[float] = None) -> Dict[str, Any]:
        """Sync memories with Hub"""
        if not self._connected:
            return {'memories': [], 'tasks': [], 'skills': []}
        
        # Would POST to sync endpoint
        return {
            'memories': [],
            'tasks': [],
            'skills': [],
            'sync_time': datetime.now().timestamp()
        }
    
    # === Utility ===
    
    def get_hub_stats(self) -> Dict[str, Any]:
        """Get Hub statistics"""
        if not self._connected:
            return {}
        
        # Would GET from hub
        return {
            'clients': 0,
            'shared_memories': 0,
            'published_skills': 0
        }
    
    def ping(self) -> bool:
        """Ping the Hub"""
        if not self._connected:
            return False
        
        # Would make a lightweight request
        return True


class LocalHubClient(HubClient):
    """
    A HubClient that works with local Hub (in-process).
    
    Useful for testing or when Hub runs in the same process.
    """
    
    def __init__(self, config: HubClientConfig, hub_server=None):
        super().__init__(config)
        self._hub = hub_server
    
    def connect(self) -> bool:
        """Connect to local Hub"""
        if self._hub:
            self._hub.register_client(
                self.config.client_id,
                self.config.user_id
            )
            self._connected = True
            return True
        return False
    
    def disconnect(self) -> bool:
        """Disconnect from local Hub"""
        if self._hub and self._connected:
            self._hub.unregister_client(self.config.client_id)
        self._connected = False
        return True
    
    def share_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        visibility: str = "team"
    ) -> Optional[str]:
        """Share memory to local Hub"""
        if not self._hub or not self._connected:
            return None
        
        import uuid
        memory_id = str(uuid.uuid4())
        
        self._hub.share_memory(
            client_id=self.config.client_id,
            memory_id=memory_id,
            memory_data={'content': content, 'metadata': metadata or {}},
            visibility=visibility
        )
        
        return memory_id
    
    def recall(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Recall from local Hub"""
        import asyncio
        
        if not self._hub or not self._connected:
            return []
        
        # Run async handler synchronously
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                self._hub.handle_recall(
                    client_id=self.config.client_id,
                    query=query,
                    conversation_id=conversation_id,
                    limit=limit
                )
            )
            return result.get('hits', [])
        finally:
            loop.close()
