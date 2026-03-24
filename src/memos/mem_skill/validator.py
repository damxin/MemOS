"""
Skill validator - validates skill quality and structure.
"""

import re
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass

from .types import ValidationResult


@dataclass
class ValidationRule:
    """A single validation rule"""
    name: str
    check_fn: Callable[[str], bool]
    error_msg: str
    warning_msg: str
    weight: float = 1.0


class SkillValidator:
    """
    Validates skill structure and quality.
    
    Checks:
    - Frontmatter format
    - Required sections
    - Content length
    - Code quality
    - Trigger descriptions
    """
    
    def __init__(
        self,
        llm_call_fn: Optional[Callable[[str], str]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.llm_call = llm_call_fn
        self.config = config or {}
        
        # Define validation rules
        self.rules: List[ValidationRule] = [
            ValidationRule(
                name="frontmatter",
                check_fn=self._check_frontmatter,
                error_msg="Missing or invalid frontmatter",
                warning_msg="Frontmatter could be improved"
            ),
            ValidationRule(
                name="name_field",
                check_fn=lambda c: bool(re.search(r'^name:\s*["\']?[\w-]+["\']?', c, re.MULTILINE)),
                error_msg="Missing 'name' in frontmatter",
                warning_msg=""
            ),
            ValidationRule(
                name="description_field",
                check_fn=lambda c: bool(re.search(r'description:\s*["\'].+["\']', c, re.DOTALL)),
                error_msg="Missing 'description' in frontmatter",
                warning_msg="Description could be more detailed"
            ),
            ValidationRule(
                name="title",
                check_fn=lambda c: bool(re.search(r'^#\s+.+', c, re.MULTILINE)),
                error_msg="Missing title (H1 heading)",
                warning_msg=""
            ),
            ValidationRule(
                name="steps_section",
                check_fn=lambda c: bool(re.search(r'^##\s+.*step', c, re.MULTILINE | re.IGNORECASE)),
                error_msg="Missing '## Steps' section",
                warning_msg=""
            ),
            ValidationRule(
                name="content_length",
                check_fn=lambda c: len(c) >= 500,
                error_msg="Content too short (less than 500 chars)",
                warning_msg="Content could be more detailed"
            ),
            ValidationRule(
                name="trigger_description",
                check_fn=self._check_trigger_quality,
                error_msg="",
                warning_msg="Trigger description could be more specific"
            ),
        ]
    
    def validate(self, skill_content: str) -> ValidationResult:
        """
        Validate skill content.
        
        Args:
            skill_content: SKILL.md content
        
        Returns:
            ValidationResult with errors, warnings, and score
        """
        result = ValidationResult(quality_score=None)
        
        # Run all rules
        for rule in self.rules:
            passed = rule.check_fn(skill_content)
            
            if not passed:
                if rule.error_msg:
                    result.add_error(f"[{rule.name}] {rule.error_msg}")
                elif rule.warning_msg:
                    result.add_warning(f"[{rule.name}] {rule.warning_msg}")
        
        # Calculate quality score
        base_score = self._calculate_base_score(skill_content)
        result.quality_score = min(base_score, 10.0)
        
        return result
    
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate skill file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.validate(content)
        except Exception as e:
            result = ValidationResult(quality_score=0.0)
            result.add_error(f"Could not read file: {e}")
            return result
    
    def _check_frontmatter(self, content: str) -> bool:
        """Check if frontmatter is valid"""
        if not content.startswith('---'):
            return False
        
        # Find closing ---
        lines = content.split('\n')
        fm_end = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                fm_end = i
                break
        
        if fm_end < 0:
            return False
        
        # Check for essential frontmatter fields
        fm_content = '\n'.join(lines[:fm_end + 1])
        return bool(re.search(r'name:\s*', fm_content))
    
    def _check_trigger_quality(self, content: str) -> bool:
        """Check if trigger description is specific enough"""
        # Look for "when to use" or similar sections
        trigger_patterns = [
            r'when to use',
            r'use when',
            r'适用场景',
            r'trigger',
        ]
        
        for pattern in trigger_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def _calculate_base_score(self, content: str) -> float:
        """Calculate base quality score"""
        score = 5.0
        
        # Length bonus
        if len(content) > 1000:
            score += 1.0
        if len(content) > 2000:
            score += 0.5
        
        # Structure bonuses
        if '```' in content:  # Has code blocks
            score += 0.5
        if re.search(r'^##\s+.*pitfall', content, re.MULTILINE | re.IGNORECASE):
            score += 0.5
        if re.search(r'^##\s+.*when to use', content, re.MULTILINE | re.IGNORECASE):
            score += 0.5
        if re.search(r'^##\s+.*companion', content, re.MULTILINE | re.IGNORECASE):
            score += 0.3
        if re.search(r'^##\s+.*environment', content, re.MULTILINE | re.IGNORECASE):
            score += 0.3
        
        # Language detection (bonus for proper language matching)
        if self._check_trigger_quality(content):
            score += 0.5
        
        return score


class SkillContentAnalyzer:
    """
    Analyzes skill content for insights.
    """
    
    def analyze(self, content: str) -> Dict[str, Any]:
        """
        Analyze skill content.
        
        Returns:
            Dict with analysis results
        """
        # Extract frontmatter
        frontmatter = self._extract_frontmatter(content)
        
        # Count sections
        sections = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
        
        # Count code blocks
        code_blocks = re.findall(r'```[\s\S]*?```', content)
        
        # Count lines
        lines = content.split('\n')
        
        # Extract description
        description = ""
        if frontmatter:
            match = re.search(r'description:\s*["\'](.+?)["\']', frontmatter, re.DOTALL)
            if match:
                description = match.group(1)
        
        return {
            'frontmatter': frontmatter,
            'description': description,
            'sections': sections,
            'section_count': len(sections),
            'code_blocks': len(code_blocks),
            'total_lines': len(lines),
            'total_chars': len(content),
            'has_scripts': 'scripts/' in content,
            'has_evals': 'evals/' in content or 'evals.json' in content,
        }
    
    def _extract_frontmatter(self, content: str) -> Optional[str]:
        """Extract frontmatter from content"""
        if not content.startswith('---'):
            return None
        
        lines = content.split('\n')
        fm_end = -1
        
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                fm_end = i
                break
        
        if fm_end < 0:
            return None
        
        return '\n'.join(lines[:fm_end + 1])
    
    def get_summary(self, content: str) -> str:
        """Get a brief summary of the skill"""
        analysis = self.analyze(content)
        
        parts = [
            f"Sections: {analysis['section_count']}",
            f"Code blocks: {analysis['code_blocks']}",
            f"Length: {analysis['total_chars']} chars",
        ]
        
        if analysis['has_scripts']:
            parts.append("Has scripts")
        if analysis['has_evals']:
            parts.append("Has tests")
        
        return " | ".join(parts)
