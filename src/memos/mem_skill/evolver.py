"""
Skill evolution - evolves skills based on usage patterns and feedback.
"""

import re
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime

from .base import Skill, SkillVersion, UpgradeType
from .types import UpgradeEvalResult, ValidationResult


class SkillEvolver:
    """
    Evolves skills based on:
    - Usage patterns
    - Task completions that match the skill
    - Feedback signals
    - Quality improvements
    """
    
    def __init__(
        self,
        llm_call_fn: Callable[[str], str],
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_call = llm_call_fn
        self.config = config or {}
    
    def should_evolve(
        self,
        skill: Skill,
        new_task_title: str,
        new_task_summary: str
    ) -> UpgradeEvalResult:
        """
        Determine if a skill should evolve based on a new task.
        
        Args:
            skill: Existing skill
            new_task_title: Title of new task
            new_task_summary: Summary of new task
        
        Returns:
            UpgradeEvalResult with evolution decision
        """
        # Quick heuristics
        if not self._is_related(skill, new_task_title, new_task_summary):
            return UpgradeEvalResult(
                should_upgrade=False,
                upgrade_type="refine",
                dimensions=[],
                reason="Task appears unrelated to existing skill",
                merge_strategy="",
                confidence=0.0
            )
        
        # Use LLM for detailed evaluation
        try:
            prompt = self._build_evolution_prompt(skill, new_task_title, new_task_summary)
            response = self.llm_call(prompt)
            return self._parse_evolution_response(response)
        except Exception:
            return UpgradeEvalResult(
                should_upgrade=False,
                upgrade_type="refine",
                dimensions=[],
                reason="Evolution evaluation failed",
                merge_strategy="",
                confidence=0.0
            )
    
    def evolve(
        self,
        skill: Skill,
        current_content: str,
        new_task_content: str,
        evolution_type: str,
        merge_strategy: str
    ) -> str:
        """
        Evolve skill content based on new task.
        
        Args:
            skill: Existing skill
            current_content: Current SKILL.md content
            new_task_content: New task's conversation/summary
            evolution_type: 'refine', 'extend', or 'fix'
            merge_strategy: How to merge the new knowledge
        
        Returns:
            Evolved SKILL.md content
        """
        prompt = self._build_merge_prompt(
            skill, current_content, new_task_content, evolution_type, merge_strategy
        )
        
        try:
            evolved_content = self.llm_call(prompt)
            return evolved_content
        except Exception:
            return current_content
    
    def _is_related(
        self,
        skill: Skill,
        task_title: str,
        task_summary: str
    ) -> bool:
        """Check if task is related to skill"""
        # Check name/tags overlap
        skill_keywords = set(
            skill.name.replace('-', ' ').lower().split() +
            [t.lower() for t in skill.tags]
        )
        
        task_text = f"{task_title} {task_summary}".lower()
        
        matches = sum(1 for kw in skill_keywords if kw in task_text)
        return matches >= 1
    
    def _build_evolution_prompt(
        self,
        skill: Skill,
        task_title: str,
        task_summary: str
    ) -> str:
        """Build prompt for evolution evaluation"""
        return f'''Evaluate if this new task should improve an existing skill.

Existing skill (v{skill.version}):
Name: {skill.name}
Description: {skill.description}

New task:
Title: {task_title}
Summary: {task_summary[:1000]}

Should the skill be upgraded? Consider:
1. Faster — shorter/better path discovered
2. More elegant — cleaner approach
3. More accurate — corrects wrong info
4. More robust — adds edge cases
5. New scenario — covers new variant

Reply JSON:
{{
  "shouldUpgrade": boolean,
  "upgradeType": "refine|extend|fix",
  "dimensions": ["list of improvement types"],
  "reason": "brief explanation",
  "mergeStrategy": "how to merge",
  "confidence": 0.0-1.0
}}'''
    
    def _build_merge_prompt(
        self,
        skill: Skill,
        current_content: str,
        new_task_content: str,
        evolution_type: str,
        merge_strategy: str
    ) -> str:
        """Build prompt for merging new knowledge"""
        return f'''Evolve this skill based on new execution experience.

Current skill:
---
{current_content}
---

New task experience:
---
{new_task_content[:3000]}
---

Evolution type: {evolution_type}
Merge strategy: {merge_strategy}

Instructions:
- Keep the progressive disclosure structure (frontmatter, body under 400 lines)
- Add new steps/insights from the new task
- Update any outdated information
- Add new pitfalls discovered
- If new scripts were created, add to companion files

Output ONLY the complete updated SKILL.md.'''
    
    def _parse_evolution_response(self, response: str) -> UpgradeEvalResult:
        """Parse LLM response for evolution decision"""
        import json
        
        try:
            data = self._extract_json(response)
            
            return UpgradeEvalResult(
                should_upgrade=data.get('shouldUpgrade', False),
                upgrade_type=data.get('upgradeType', 'refine'),
                dimensions=data.get('dimensions', []),
                reason=data.get('reason', ''),
                merge_strategy=data.get('mergeStrategy', ''),
                confidence=data.get('confidence', 0.5)
            )
        except Exception:
            return UpgradeEvalResult(
                should_upgrade=False,
                upgrade_type="refine",
                dimensions=[],
                reason="Failed to parse evolution response",
                merge_strategy="",
                confidence=0.0
            )
    
    def _extract_json(self, response: str) -> Dict[str, Any]:
        """Extract JSON from response"""
        import json
        
        try:
            return json.loads(response)
        except:
            pass
        
        # Try to find JSON in response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except:
                pass
        
        return {}


class UsageTracker:
    """
    Tracks skill usage patterns for evolution decisions.
    """
    
    def __init__(self):
        self.usage_counts: Dict[str, int] = {}
        self.success_counts: Dict[str, int] = {}
        self.last_used: Dict[str, float] = {}
    
    def record_usage(
        self,
        skill_name: str,
        success: bool = True
    ) -> None:
        """Record a skill usage"""
        self.usage_counts[skill_name] = self.usage_counts.get(skill_name, 0) + 1
        
        if success:
            self.success_counts[skill_name] = self.success_counts.get(skill_name, 0) + 1
        
        self.last_used[skill_name] = datetime.now().timestamp()
    
    def get_stats(self, skill_name: str) -> Dict[str, Any]:
        """Get usage statistics for a skill"""
        total = self.usage_counts.get(skill_name, 0)
        success = self.success_counts.get(skill_name, 0)
        last = self.last_used.get(skill_name, 0)
        
        return {
            'total_uses': total,
            'successful_uses': success,
            'success_rate': success / total if total > 0 else 0.0,
            'last_used': last,
            'days_since_last_use': (
                (datetime.now().timestamp() - last) / 86400
                if last > 0 else None
            )
        }
    
    def should_deprecate(self, skill_name: str, max_days: int = 90) -> bool:
        """Check if skill should be deprecated"""
        stats = self.get_stats(skill_name)
        
        if stats['days_since_last_use'] is None:
            return False
        
        return (
            stats['days_since_last_use'] > max_days and
            stats['total_uses'] < 3
        )
