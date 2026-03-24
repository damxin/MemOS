"""
mem_skill module - Skill management for MemOS.

Provides skill generation, evolution, upgrade, and validation.

Reference: Local Plugin src/skill/
"""

# Core data structures
from .base import (
    Skill,
    SkillVersion,
    SkillStatus,
    SkillVisibility,
    UpgradeType,
    EvalResult,
    CompanionFile,
)

# Type definitions
from .types import (
    CreateEvalResult,
    UpgradeEvalResult,
    ValidationResult,
    EvalVerificationResult,
    SkillEvaluationDimension,
    SkillGenerateConfig,
    SkillQuery,
    SkillStats,
    SkillEvent,
    SkillEventData,
)

# Storage layer
from .storage import (
    BaseSkillStorage,
    InMemorySkillStorage,
    SQLiteSkillStorage,
    create_skill_storage,
)

# Core functionality
from .evaluator import SkillEvaluator
from .generator import SkillGenerator, SkillGenerateOutput
from .evolver import SkillEvolver, UsageTracker
from .upgrader import SkillUpgrader, VersionComparator
from .installer import SkillInstaller, SkillRegistry
from .validator import SkillValidator, SkillContentAnalyzer


__all__ = [
    # Base
    "Skill",
    "SkillVersion",
    "SkillStatus",
    "SkillVisibility",
    "UpgradeType",
    "EvalResult",
    "CompanionFile",
    # Types
    "CreateEvalResult",
    "UpgradeEvalResult",
    "ValidationResult",
    "EvalVerificationResult",
    "SkillEvaluationDimension",
    "SkillGenerateConfig",
    "SkillQuery",
    "SkillStats",
    "SkillEvent",
    "SkillEventData",
    # Storage
    "BaseSkillStorage",
    "InMemorySkillStorage",
    "SQLiteSkillStorage",
    "create_skill_storage",
    # Core
    "SkillEvaluator",
    "SkillGenerator",
    "SkillGenerateOutput",
    "SkillEvolver",
    "UsageTracker",
    "SkillUpgrader",
    "VersionComparator",
    "SkillInstaller",
    "SkillRegistry",
    "SkillValidator",
    "SkillContentAnalyzer",
]
