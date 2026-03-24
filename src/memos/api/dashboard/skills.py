"""
Dashboard API - Skills endpoints.
"""

from typing import List, Optional, Dict, Any


class SkillsAPI:
    """
    API for skill operations.
    
    Endpoints:
    - GET /api/skills - List skills
    - GET /api/skills/:id - Get skill
    - POST /api/skills - Create skill
    - PUT /api/skills/:id - Update skill
    - DELETE /api/skills/:id - Delete skill
    - POST /api/skills/:id/install - Install skill
    - POST /api/skills/:id/uninstall - Uninstall skill
    """
    
    def __init__(self, storage):
        self.storage = storage
    
    def list_skills(
        self,
        owner: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List skills with filters"""
        skills = self.storage.get_skills(
            owner=owner,
            status=status,
            tags=tags,
            limit=limit,
            offset=offset
        )
        return [self._format_skill(s) for s in skills]
    
    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a single skill"""
        skill = self.storage.get_skill(skill_id)
        if not skill:
            return None
        return self._format_skill(skill)
    
    def create_skill(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new skill"""
        skill_id = self.storage.insert_skill(data)
        skill = self.storage.get_skill(skill_id)
        return self._format_skill(skill)
    
    def update_skill(
        self,
        skill_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a skill"""
        self.storage.update_skill(skill_id, updates)
        skill = self.storage.get_skill(skill_id)
        if not skill:
            return None
        return self._format_skill(skill)
    
    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill"""
        return self.storage.delete_skill(skill_id)
    
    def publish_skill(self, skill_id: str, visibility: str = "team") -> Optional[Dict[str, Any]]:
        """Publish a skill"""
        return self.update_skill(skill_id, {'visibility': visibility})
    
    def deprecate_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Deprecate a skill"""
        return self.update_skill(skill_id, {'status': 'deprecated'})
    
    def get_skill_stats(self, owner: Optional[str] = None) -> Dict[str, Any]:
        """Get skill statistics"""
        skills = self.storage.get_skills(owner=owner)
        
        active = sum(1 for s in skills if s.get('status') == 'active')
        draft = sum(1 for s in skills if s.get('status') == 'draft')
        deprecated = sum(1 for s in skills if s.get('status') == 'deprecated')
        
        scores = [s.get('quality_score', 0) for s in skills if s.get('quality_score')]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            'total': len(skills),
            'active': active,
            'draft': draft,
            'deprecated': deprecated,
            'avg_quality_score': avg_score
        }
    
    def _format_skill(self, skill: Dict[str, Any]) -> Dict[str, Any]:
        """Format skill for API response"""
        return {
            'id': skill.get('id'),
            'name': skill.get('name'),
            'description': skill.get('description'),
            'content': skill.get('content'),
            'version': skill.get('version'),
            'status': skill.get('status'),
            'visibility': skill.get('visibility'),
            'owner': skill.get('owner'),
            'quality_score': skill.get('quality_score'),
            'tags': skill.get('tags', []),
            'metadata': skill.get('metadata', {}),
            'created_at': skill.get('created_at'),
            'updated_at': skill.get('updated_at')
        }
