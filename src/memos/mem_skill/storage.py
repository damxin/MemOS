"""
Skill storage layer.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime

from .base import Skill, SkillVersion, SkillStatus, SkillVisibility
from .types import SkillQuery, SkillStats


class BaseSkillStorage(ABC):
    """Abstract base class for skill storage"""
    
    @abstractmethod
    def insert_skill(self, skill: Skill) -> Skill:
        """Insert a new skill"""
        pass
    
    @abstractmethod
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get a skill by ID"""
        pass
    
    @abstractmethod
    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        pass
    
    @abstractmethod
    def update_skill(self, skill_id: str, updates: Dict[str, Any]) -> Optional[Skill]:
        """Update a skill"""
        pass
    
    @abstractmethod
    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill"""
        pass
    
    @abstractmethod
    def query_skills(self, query: SkillQuery) -> List[Skill]:
        """Query skills"""
        pass
    
    @abstractmethod
    def insert_skill_version(self, version: SkillVersion) -> SkillVersion:
        """Insert a skill version"""
        pass
    
    @abstractmethod
    def get_skill_versions(self, skill_id: str) -> List[SkillVersion]:
        """Get all versions of a skill"""
        pass
    
    @abstractmethod
    def get_skill_stats(self, owner: Optional[str] = None) -> SkillStats:
        """Get skill statistics"""
        pass


class InMemorySkillStorage(BaseSkillStorage):
    """
    In-memory skill storage for testing and lightweight usage.
    """
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self.versions: Dict[str, List[SkillVersion]] = {}
    
    def insert_skill(self, skill: Skill) -> Skill:
        self.skills[skill.id] = skill
        self.versions[skill.id] = []
        return skill
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.skills.get(skill_id)
    
    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        for skill in self.skills.values():
            if skill.name == name:
                return skill
        return None
    
    def update_skill(self, skill_id: str, updates: Dict[str, Any]) -> Optional[Skill]:
        skill = self.skills.get(skill_id)
        if not skill:
            return None
        
        # Apply updates
        if 'version' in updates:
            skill.version = updates['version']
        if 'status' in updates:
            skill.status = SkillStatus(updates['status'])
        if 'quality_score' in updates:
            skill.quality_score = updates['quality_score']
        if 'description' in updates:
            skill.description = updates['description']
        if 'tags' in updates:
            skill.tags = updates['tags']
        
        skill.updated_at = datetime.now().timestamp() * 1000
        
        return skill
    
    def delete_skill(self, skill_id: str) -> bool:
        if skill_id not in self.skills:
            return False
        del self.skills[skill_id]
        if skill_id in self.versions:
            del self.versions[skill_id]
        return True
    
    def query_skills(self, query: SkillQuery) -> List[Skill]:
        results = list(self.skills.values())
        
        if query.owner:
            results = [s for s in results if s.owner == query.owner]
        
        if query.status:
            results = [s for s in results if s.status.value == query.status]
        
        if query.visibility:
            results = [s for s in results if s.visibility.value == query.visibility]
        
        if query.search:
            search = query.search.lower()
            results = [
                s for s in results
                if search in s.name.lower() or search in s.description.lower()
            ]
        
        if query.tags:
            results = [
                s for s in results
                if any(t in s.tags for t in query.tags)
            ]
        
        # Apply pagination
        return results[query.offset:query.offset + query.limit]
    
    def insert_skill_version(self, version: SkillVersion) -> SkillVersion:
        if version.skill_id not in self.versions:
            self.versions[version.skill_id] = []
        self.versions[version.skill_id].append(version)
        return version
    
    def get_skill_versions(self, skill_id: str) -> List[SkillVersion]:
        return sorted(
            self.versions.get(skill_id, []),
            key=lambda v: v.version,
            reverse=True
        )
    
    def get_task_stats(self, owner: Optional[str] = None) -> SkillStats:
        skills = list(self.skills.values())
        if owner:
            skills = [s for s in skills if s.owner == owner]
        
        active = [s for s in skills if s.status == SkillStatus.ACTIVE]
        draft = [s for s in skills if s.status == SkillStatus.DRAFT]
        deprecated = [s for s in skills if s.status == SkillStatus.DEPRECATED]
        
        scores = [s.quality_score for s in skills if s.quality_score is not None]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        total_versions = sum(len(self.versions.get(s.id, [])) for s in skills)
        
        return SkillStats(
            total_skills=len(skills),
            active_skills=len(active),
            draft_skills=len(draft),
            deprecated_skills=len(deprecated),
            avg_quality_score=avg_score,
            total_versions=total_versions
        )


class SQLiteSkillStorage(BaseSkillStorage):
    """
    SQLite implementation of skill storage.
    
    Uses the existing SqliteStore from the Local Plugin.
    """
    
    def __init__(self, store):
        """
        Args:
            store: SqliteStore instance from memos-local-openclaw
        """
        self.store = store
    
    def insert_skill(self, skill: Skill) -> Skill:
        skill_dict = skill.to_dict()
        self.store.insertSkill(skill_dict)
        return skill
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        skill_dict = self.store.getSkill(skill_id)
        if not skill_dict:
            return None
        return Skill.from_dict(skill_dict)
    
    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        # This would need a custom query method
        # For now, return None
        return None
    
    def update_skill(self, skill_id: str, updates: Dict[str, Any]) -> Optional[Skill]:
        updates['updated_at'] = datetime.now().timestamp() * 1000
        self.store.updateSkill(skill_id, updates)
        return self.get_skill(skill_id)
    
    def delete_skill(self, skill_id: str) -> bool:
        return self.store.deleteSkill(skill_id)
    
    def query_skills(self, query: SkillQuery) -> List[Skill]:
        filters = {}
        if query.owner:
            filters['owner'] = query.owner
        if query.status:
            filters['status'] = query.status
        if query.visibility:
            filters['visibility'] = query.visibility
        
        skill_dicts = self.store.getSkills(filters, limit=query.limit, offset=query.offset)
        return [Skill.from_dict(s) for s in skill_dicts]
    
    def insert_skill_version(self, version: SkillVersion) -> SkillVersion:
        version_dict = version.to_dict()
        self.store.insertSkillVersion(version_dict)
        return version
    
    def get_skill_versions(self, skill_id: str) -> List[SkillVersion]:
        version_dicts = self.store.getSkillVersions(skill_id)
        return [SkillVersion.from_dict(v) for v in version_dicts]
    
    def get_task_stats(self, owner: Optional[str] = None) -> SkillStats:
        # This would need a custom query
        return SkillStats()


def create_skill_storage(
    backend: str = "memory",
    **kwargs
) -> BaseSkillStorage:
    """
    Factory function to create skill storage.
    
    Args:
        backend: 'memory', 'sqlite', or 'postgres'
        **kwargs: Backend-specific arguments
    
    Returns:
        BaseSkillStorage implementation
    """
    if backend == "memory":
        return InMemorySkillStorage()
    elif backend == "sqlite":
        return SQLiteSkillStorage(kwargs.get('store'))
    elif backend == "postgres":
        # Would need PostgreSQL implementation
        raise NotImplementedError("PostgreSQL skill storage not yet implemented")
    else:
        raise ValueError(f"Unknown backend: {backend}")
