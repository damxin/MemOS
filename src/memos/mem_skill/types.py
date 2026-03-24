"""
Skill-specific type definitions.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum


class SkillEvaluationDimension(Enum):
    """Dimensions for skill quality evaluation"""
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    CLARITY = "clarity"
    REUSABILITY = "reusability"
    TRIGGER_QUALITY = "trigger_quality"


@dataclass
class CreateEvalResult:
    """
    Result of evaluating whether to generate a skill from a task.
    """
    should_generate: bool
    reason: str
    suggested_name: str
    suggested_tags: List[str]
    confidence: float  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'should_generate': self.should_generate,
            'reason': self.reason,
            'suggested_name': self.suggested_name,
            'suggested_tags': self.suggested_tags,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreateEvalResult':
        return cls(
            should_generate=data.get('should_generate', False),
            reason=data.get('reason', ''),
            suggested_name=data.get('suggested_name', ''),
            suggested_tags=data.get('suggested_tags', []),
            confidence=data.get('confidence', 0.0)
        )


@dataclass
class UpgradeEvalResult:
    """
    Result of evaluating whether to upgrade an existing skill.
    """
    should_upgrade: bool
    upgrade_type: str  # 'refine', 'extend', 'fix'
    dimensions: List[str]
    reason: str
    merge_strategy: str
    confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'should_upgrade': self.should_upgrade,
            'upgrade_type': self.upgrade_type,
            'dimensions': self.dimensions,
            'reason': self.reason,
            'merge_strategy': self.merge_strategy,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UpgradeEvalResult':
        return cls(
            should_upgrade=data.get('should_upgrade', False),
            upgrade_type=data.get('upgrade_type', 'refine'),
            dimensions=data.get('dimensions', []),
            reason=data.get('reason', ''),
            merge_strategy=data.get('merge_strategy', ''),
            confidence=data.get('confidence', 0.0)
        )


@dataclass
class ValidationResult:
    """
    Result of skill validation.
    """
    quality_score: Optional[float]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    is_valid: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'quality_score': self.quality_score,
            'errors': self.errors,
            'warnings': self.warnings,
            'suggestions': self.suggestions,
            'is_valid': self.is_valid
        }
    
    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)
    
    def add_suggestion(self, suggestion: str) -> None:
        self.suggestions.append(suggestion)


@dataclass
class EvalVerificationResult:
    """
    Result of verifying eval test cases.
    """
    hit_count: int
    total_count: int
    hits: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.hit_count / self.total_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'hit_count': self.hit_count,
            'total_count': self.total_count,
            'pass_rate': self.pass_rate,
            'hits': self.hits
        }


@dataclass
class SkillGenerateConfig:
    """Configuration for skill generation"""
    # LLM model to use
    model: str = "gpt-4"
    # Temperature for generation
    temperature: float = 0.7
    # Max tokens for SKILL.md content
    max_skill_content_tokens: int = 4000
    # Min quality score to be active (below = draft)
    min_quality_score_for_active: float = 6.0
    # Quality score threshold for warnings
    quality_score_warning_threshold: float = 7.0


@dataclass
class SkillQuery:
    """Query parameters for skill search"""
    owner: Optional[str] = None
    status: Optional[str] = None  # 'active', 'draft', 'deprecated'
    visibility: Optional[str] = None  # 'private', 'shared', 'public'
    tags: Optional[List[str]] = None
    search: Optional[str] = None  # text search in name/description
    limit: int = 100
    offset: int = 0


@dataclass
class SkillStats:
    """Statistics about skills"""
    total_skills: int = 0
    active_skills: int = 0
    draft_skills: int = 0
    deprecated_skills: int = 0
    avg_quality_score: float = 0.0
    total_versions: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_skills': self.total_skills,
            'active_skills': self.active_skills,
            'draft_skills': self.draft_skills,
            'deprecated_skills': self.deprecated_skills,
            'avg_quality_score': self.avg_quality_score,
            'total_versions': self.total_versions
        }


class SkillEvent(Enum):
    """Skill lifecycle events"""
    CREATED = "skill_created"
    UPDATED = "skill_updated"
    UPGRADED = "skill_upgraded"
    INSTALLED = "skill_installed"
    UNINSTALLED = "skill_uninstalled"
    DEPRECATED = "skill_deprecated"


@dataclass
class SkillEventData:
    """Data associated with a skill event"""
    event: SkillEvent
    skill_id: str
    skill_name: str
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
