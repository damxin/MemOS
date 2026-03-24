"""
Dashboard API - Analytics endpoints.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class AnalyticsAPI:
    """
    API for analytics and statistics.
    
    Provides:
    - Memory statistics
    - Task statistics  
    - Skill statistics
    - Usage trends
    - Embedding usage
    """
    
    def __init__(self, storage):
        self.storage = storage
    
    def get_overview(self, owner: Optional[str] = None) -> Dict[str, Any]:
        """
        Get overview statistics.
        
        Returns combined stats from memories, tasks, and skills.
        """
        memories = self.storage.get_memories(owner=owner)
        tasks = self.storage.get_tasks(owner=owner)
        skills = self.storage.get_skills(owner=owner)
        
        return {
            'memories': {
                'total': len(memories),
                'by_role': self._count_by_role(memories),
                'by_kind': self._count_by_kind(memories)
            },
            'tasks': {
                'total': len(tasks),
                'active': sum(1 for t in tasks if t.get('status') == 'active'),
                'completed': sum(1 for t in tasks if t.get('status') == 'completed'),
                'skipped': sum(1 for t in tasks if t.get('status') == 'skipped')
            },
            'skills': {
                'total': len(skills),
                'active': sum(1 for s in skills if s.get('status') == 'active'),
                'draft': sum(1 for s in skills if s.get('status') == 'draft'),
                'avg_quality_score': self._avg([s.get('quality_score') for s in skills if s.get('quality_score')])
            },
            'generated_at': datetime.now().timestamp()
        }
    
    def get_memory_trends(
        self,
        owner: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get memory creation trends over time.
        
        Returns daily counts for the specified number of days.
        """
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        memories = self.storage.get_memories(owner=owner)
        
        # Filter by date
        recent = [m for m in memories if m.get('created_at', 0) > cutoff]
        
        # Group by day
        daily = {}
        for memory in recent:
            created = memory.get('created_at', 0)
            if created:
                day = datetime.fromtimestamp(created).strftime('%Y-%m-%d')
                daily[day] = daily.get(day, 0) + 1
        
        return {
            'daily_counts': daily,
            'total': len(recent),
            'days': days
        }
    
    def get_usage_by_role(
        self,
        owner: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get memory usage breakdown by role"""
        memories = self.storage.get_memories(owner=owner)
        by_role = self._count_by_role(memories)
        
        total_chars = sum(len(m.get('content', '')) for m in memories)
        
        return {
            'by_role': by_role,
            'total_memories': len(memories),
            'total_chars': total_chars,
            'avg_chars_per_memory': total_chars / len(memories) if memories else 0
        }
    
    def get_task_efficiency(
        self,
        owner: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get task completion efficiency metrics"""
        tasks = self.storage.get_tasks(owner=owner)
        
        completed = [t for t in tasks if t.get('status') == 'completed']
        skipped = [t for t in tasks if t.get('status') == 'skipped']
        
        # Calculate avg task duration
        durations = []
        for task in completed:
            started = task.get('started_at', 0)
            ended = task.get('ended_at', 0)
            if started and ended:
                durations.append(ended - started)
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            'total_tasks': len(tasks),
            'completed': len(completed),
            'skipped': len(skipped),
            'completion_rate': len(completed) / len(tasks) if tasks else 0,
            'avg_task_duration_seconds': avg_duration
        }
    
    def get_skill_quality(
        self,
        owner: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get skill quality distribution"""
        skills = self.storage.get_skills(owner=owner)
        
        scores = [s.get('quality_score', 0) for s in skills if s.get('quality_score')]
        
        if not scores:
            return {
                'avg_quality': 0,
                'min_quality': 0,
                'max_quality': 0,
                'distribution': {}
            }
        
        # Quality distribution
        dist = {
            'excellent': sum(1 for s in scores if s >= 8),
            'good': sum(1 for s in scores if 6 <= s < 8),
            'fair': sum(1 for s in scores if 4 <= s < 6),
            'poor': sum(1 for s in scores if s < 4)
        }
        
        return {
            'avg_quality': sum(scores) / len(scores),
            'min_quality': min(scores),
            'max_quality': max(scores),
            'distribution': dist
        }
    
    def _count_by_role(self, memories: list) -> Dict[str, int]:
        """Count memories by role"""
        counts = {}
        for m in memories:
            role = m.get('role', 'unknown')
            counts[role] = counts.get(role, 0) + 1
        return counts
    
    def _count_by_kind(self, memories: list) -> Dict[str, int]:
        """Count memories by kind"""
        counts = {}
        for m in memories:
            kind = m.get('kind', 'paragraph')
            counts[kind] = counts.get(kind, 0) + 1
        return counts
    
    def _avg(self, values: list) -> float:
        """Calculate average"""
        return sum(values) / len(values) if values else 0
