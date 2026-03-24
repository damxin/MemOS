"""
Dashboard API - Tasks endpoints.
"""

from typing import List, Optional, Dict, Any


class TasksAPI:
    """
    API for task operations.
    
    Endpoints:
    - GET /api/tasks - List tasks
    - GET /api/tasks/:id - Get task
    - POST /api/tasks - Create task
    - PUT /api/tasks/:id - Update task
    - DELETE /api/tasks/:id - Delete task
    """
    
    def __init__(self, storage):
        self.storage = storage
    
    def list_tasks(
        self,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List tasks with filters"""
        tasks = self.storage.get_tasks(
            owner=owner,
            status=status,
            limit=limit,
            offset=offset
        )
        return [self._format_task(t) for t in tasks]
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a single task"""
        task = self.storage.get_task(task_id)
        if not task:
            return None
        return self._format_task(task)
    
    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task"""
        task_id = self.storage.insert_task(data)
        task = self.storage.get_task(task_id)
        return self._format_task(task)
    
    def update_task(
        self,
        task_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a task"""
        self.storage.update_task(task_id, updates)
        task = self.storage.get_task(task_id)
        if not task:
            return None
        return self._format_task(task)
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        return self.storage.delete_task(task_id)
    
    def complete_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Mark task as completed"""
        return self.update_task(task_id, {'status': 'completed'})
    
    def get_task_stats(self, owner: Optional[str] = None) -> Dict[str, Any]:
        """Get task statistics"""
        tasks = self.storage.get_tasks(owner=owner)
        
        active = sum(1 for t in tasks if t.get('status') == 'active')
        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        skipped = sum(1 for t in tasks if t.get('status') == 'skipped')
        
        return {
            'total': len(tasks),
            'active': active,
            'completed': completed,
            'skipped': skipped
        }
    
    def _format_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Format task for API response"""
        return {
            'id': task.get('id'),
            'session_key': task.get('session_key'),
            'title': task.get('title'),
            'summary': task.get('summary'),
            'status': task.get('status'),
            'owner': task.get('owner'),
            'started_at': task.get('started_at'),
            'ended_at': task.get('ended_at'),
            'updated_at': task.get('updated_at'),
            'metadata': task.get('metadata', {})
        }
