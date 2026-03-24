"""
Skill upgrader - handles skill version upgrades.
"""

import os
import re
import json
from typing import List, Optional, Callable, Dict, Any, Tuple
from datetime import datetime

from .base import Skill, SkillVersion, UpgradeType
from .types import UpgradeEvalResult, ValidationResult
from .evolver import SkillEvolver


class SkillUpgrader:
    """
    Handles upgrading skills to new versions.
    
    Upgrade flow:
    1. Evaluate if upgrade is needed
    2. Generate evolved content
    3. Validate new version
    4. Create version record
    """
    
    def __init__(
        self,
        llm_call_fn: Callable[[str], str],
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_call = llm_call_fn
        self.evolver = SkillEvolver(llm_call_fn, config)
        self.config = config or {}
    
    def should_upgrade(
        self,
        skill: Skill,
        skill_content: str,
        new_task_title: str,
        new_task_summary: str
    ) -> UpgradeEvalResult:
        """
        Determine if skill should be upgraded.
        
        Args:
            skill: Existing skill
            skill_content: Current skill content
            new_task_title: New task title
            new_task_summary: New task summary
        
        Returns:
            UpgradeEvalResult with upgrade decision
        """
        return self.evolver.should_evolve(
            skill, new_task_title, new_task_summary
        )
    
    def upgrade(
        self,
        skill: Skill,
        current_version: SkillVersion,
        new_task_content: str,
        upgrade_result: UpgradeEvalResult
    ) -> Tuple[Skill, SkillVersion, ValidationResult]:
        """
        Perform skill upgrade.
        
        Args:
            skill: Existing skill
            current_version: Current version
            new_task_content: New task content for merging
            upgrade_result: Result from should_upgrade
        
        Returns:
            Tuple of (updated_skill, new_version, validation_result)
        """
        import uuid
        
        # Generate evolved content
        evolved_content = self.evolver.evolve(
            skill=skill,
            current_content=current_version.content,
            new_task_content=new_task_content,
            evolution_type=upgrade_result.upgrade_type,
            merge_strategy=upgrade_result.merge_strategy
        )
        
        # Validate new content
        validation = self._validate_upgrade(
            evolved_content, current_version.content
        )
        
        # Create new version
        new_version_num = skill.version + 1
        now = datetime.now().timestamp() * 1000
        
        changelog = self._generate_changelog(
            current_version, new_task_content, upgrade_result
        )
        
        new_version = SkillVersion(
            id=str(uuid.uuid4()),
            skill_id=skill.id,
            version=new_version_num,
            content=evolved_content,
            changelog=changelog,
            change_summary=upgrade_result.reason,
            upgrade_type=UpgradeType(upgrade_result.upgrade_type),
            metrics={
                'dimensions': upgrade_result.dimensions,
                'confidence': upgrade_result.confidence,
                'merge_strategy': upgrade_result.merge_strategy,
                'validation': validation.to_dict()
            },
            quality_score=validation.quality_score,
            created_at=now
        )
        
        # Update skill
        skill.version = new_version_num
        skill.updated_at = now
        skill.quality_score = validation.quality_score
        
        # Update status if quality improved
        if validation.quality_score and validation.quality_score >= 7.0:
            from .base import SkillStatus
            skill.status = SkillStatus.ACTIVE
        
        # Write to file
        skill_md_path = os.path.join(skill.dir_path, "SKILL.md")
        with open(skill_md_path, 'w', encoding='utf-8') as f:
            f.write(evolved_content)
        
        return skill, new_version, validation
    
    def _validate_upgrade(
        self,
        new_content: str,
        old_content: str
    ) -> ValidationResult:
        """Validate upgraded skill content"""
        result = ValidationResult(quality_score=None)
        
        # Basic checks
        if len(new_content) < 100:
            result.add_error("Upgraded content too short")
            return result
        
        # Check for frontmatter
        if not new_content.startswith('---'):
            result.add_warning("Missing frontmatter")
        
        # Check that content actually changed
        if new_content.strip() == old_content.strip():
            result.add_warning("No actual changes made")
        
        # Quality scoring
        score = 5.0
        
        if len(new_content) > len(old_content):
            score += 1.0  # Content was added
        
        if '## Pitfall' in new_content or '## 陷阱' in new_content:
            score += 1.0
        
        if '## When to use' in new_content or '## 使用场景' in new_content:
            score += 0.5
        
        if '```' in new_content:
            score += 0.5
        
        # Check for improved structure
        if new_content.count('\n##') > old_content.count('\n##'):
            score += 0.5
        
        result.quality_score = min(score, 10.0)
        
        return result
    
    def _generate_changelog(
        self,
        old_version: SkillVersion,
        new_task_content: str,
        upgrade_result: UpgradeEvalResult
    ) -> str:
        """Generate changelog entry"""
        lines = [
            f"v{old_version.version + 1} ({datetime.now().strftime('%Y-%m-%d')})",
            f"Upgrade type: {upgrade_result.upgrade_type}",
            f"Dimensions: {', '.join(upgrade_result.dimensions)}",
            "",
            "Changes:",
        ]
        
        # Extract key changes from new task
        if len(new_task_content) > 500:
            summary_line = new_task_content[:500]
        else:
            summary_line = new_task_content
        
        lines.append(f"- Merged new experience: {summary_line}")
        
        if upgrade_result.reason:
            lines.append(f"- Reason: {upgrade_result.reason}")
        
        return '\n'.join(lines)


class VersionComparator:
    """
    Compares skill versions to understand evolution.
    """
    
    def compare(
        self,
        old_content: str,
        new_content: str
    ) -> Dict[str, Any]:
        """
        Compare two skill versions.
        
        Returns:
            Dict with comparison results
        """
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')
        
        # Simple diff tracking
        added_sections = []
        removed_sections = []
        
        old_sections = set(self._extract_sections(old_content))
        new_sections = set(self._extract_sections(new_content))
        
        added_sections = list(new_sections - old_sections)
        removed_sections = list(old_sections - new_sections)
        
        return {
            'length_change': len(new_content) - len(old_content),
            'line_change': len(new_lines) - len(old_lines),
            'added_sections': added_sections,
            'removed_sections': removed_sections,
            'content_unchanged': old_content.strip() == new_content.strip()
        }
    
    def _extract_sections(self, content: str) -> List[str]:
        """Extract section headers from content"""
        return re.findall(r'^##?\s+(.+)$', content, re.MULTILINE)
