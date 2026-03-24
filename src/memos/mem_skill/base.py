"""
Skill data structures and base classes.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class SkillStatus(Enum):
    """Skill status enumeration"""
    ACTIVE = "active"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class SkillVisibility(Enum):
    """Skill visibility enumeration"""
    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class UpgradeType(Enum):
    """Skill upgrade type"""
    CREATE = "create"
    REFINE = "refine"
    EXTEND = "extend"
    FIX = "fix"


@dataclass
class Skill:
    """
    Represents a reusable skill extracted from task execution.
    
    A Skill contains:
    - name: unique identifier (kebab-case)
    - description: trigger description for agent activation
    - version: current version number
    - status: active/draft/deprecated
    - visibility: private/shared/public
    - quality_score: evaluation score
    - dir_path: path to skill files
    """
    id: str
    name: str
    description: str = ""
    version: int = 1
    status: SkillStatus = SkillStatus.ACTIVE
    visibility: SkillVisibility = SkillVisibility.PRIVATE
    tags: List[str] = field(default_factory=list)
    source_type: str = "task"  # 'task' or 'manual'
    dir_path: str = ""
    installed: int = 0  # 0 = not installed, 1 = installed
    owner: str = "agent:main"
    quality_score: Optional[float] = None
    created_at: float = 0
    updated_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = SkillStatus(self.status)
        if isinstance(self.visibility, str):
            self.visibility = SkillVisibility(self.visibility)
        if isinstance(self.tags, str):
            self.tags = self.tags.split(',') if self.tags else []
        if self.created_at == 0:
            self.created_at = datetime.now().timestamp() * 1000
        if self.updated_at == 0:
            self.updated_at = datetime.now().timestamp() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'status': self.status.value,
            'visibility': self.visibility.value,
            'tags': ','.join(self.tags) if isinstance(self.tags, list) else self.tags,
            'source_type': self.source_type,
            'dir_path': self.dir_path,
            'installed': self.installed,
            'owner': self.owner,
            'quality_score': self.quality_score,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            **self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Skill':
        """Create from dictionary"""
        tags = data.get('tags', '')
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',') if t.strip()]
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            version=data.get('version', 1),
            status=SkillStatus(data.get('status', 'active')),
            visibility=SkillVisibility(data.get('visibility', 'private')),
            tags=tags,
            source_type=data.get('source_type', 'task'),
            dir_path=data.get('dir_path', ''),
            installed=data.get('installed', 0),
            owner=data.get('owner', 'agent:main'),
            quality_score=data.get('quality_score'),
            created_at=data.get('created_at', 0),
            updated_at=data.get('updated_at', 0),
            metadata={k: v for k, v in data.items()
                     if k not in ('id', 'name', 'description', 'version', 'status',
                                 'visibility', 'tags', 'source_type', 'dir_path',
                                 'installed', 'owner', 'quality_score', 'created_at', 'updated_at')}
        )
    
    def is_active(self) -> bool:
        """Check if skill is active"""
        return self.status == SkillStatus.ACTIVE
    
    def is_draft(self) -> bool:
        """Check if skill is draft"""
        return self.status == SkillStatus.DRAFT
    
    def is_public(self) -> bool:
        """Check if skill is public"""
        return self.visibility == SkillVisibility.PUBLIC
    
    def is_shared(self) -> bool:
        """Check if skill is shared"""
        return self.visibility == SkillVisibility.SHARED


@dataclass
class SkillVersion:
    """
    A version of a skill.
    
    Contains the SKILL.md content and metadata about what changed.
    """
    id: str
    skill_id: str
    version: int
    content: str = ""
    changelog: str = ""
    change_summary: str = ""
    upgrade_type: UpgradeType = UpgradeType.CREATE
    source_task_id: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    quality_score: Optional[float] = None
    created_at: float = 0
    
    def __post_init__(self):
        if isinstance(self.upgrade_type, str):
            self.upgrade_type = UpgradeType(self.upgrade_type)
        if self.created_at == 0:
            self.created_at = datetime.now().timestamp() * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'skill_id': self.skill_id,
            'version': self.version,
            'content': self.content,
            'changelog': self.changelog,
            'change_summary': self.change_summary,
            'upgrade_type': self.upgrade_type.value,
            'source_task_id': self.source_task_id,
            'metrics': self.metrics if isinstance(self.metrics, str) else str(self.metrics),
            'quality_score': self.quality_score,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillVersion':
        metrics = data.get('metrics', '{}')
        if isinstance(metrics, str):
            import json
            try:
                metrics = json.loads(metrics)
            except:
                metrics = {}
        
        return cls(
            id=data['id'],
            skill_id=data['skill_id'],
            version=data.get('version', 1),
            content=data.get('content', ''),
            changelog=data.get('changelog', ''),
            change_summary=data.get('change_summary', ''),
            upgrade_type=UpgradeType(data.get('upgrade_type', 'create')),
            source_task_id=data.get('source_task_id'),
            metrics=metrics,
            quality_score=data.get('quality_score'),
            created_at=data.get('created_at', 0)
        )


@dataclass
class EvalResult:
    """
    Evaluation result for a skill test case.
    """
    id: int
    prompt: str
    expectations: List[str]
    trigger_confidence: str = "medium"  # 'high' or 'medium'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'prompt': self.prompt,
            'expectations': self.expectations,
            'trigger_confidence': self.trigger_confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EvalResult':
        return cls(
            id=data['id'],
            prompt=data['prompt'],
            expectations=data.get('expectations', []),
            trigger_confidence=data.get('trigger_confidence', 'medium')
        )


@dataclass
class CompanionFile:
    """
    A companion file (script or reference) for a skill.
    """
    filename: str
    content: str = ""
    file_type: str = "script"  # 'script' or 'reference'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'filename': self.filename,
            'content': self.content,
            'type': self.file_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompanionFile':
        return cls(
            filename=data['filename'],
            content=data.get('content', ''),
            file_type=data.get('type', 'script')
        )
