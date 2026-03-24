"""
Skill evaluator - determines if a task should generate a skill.
"""

import re
from typing import Optional, Callable, Dict, Any, List

from .base import Skill
from .types import CreateEvalResult, UpgradeEvalResult


# Prompts for LLM-based evaluation
CREATE_EVAL_PROMPT = '''You are a strict experience evaluation expert. Based on the completed task record below, decide whether this task contains **reusable, transferable** experience worth distilling into a "skill".

A skill is a reusable guide that helps an AI agent handle **the same type of task** better in the future. The key question is: "Will someone likely need to do this exact type of thing again?"

STRICT criteria — must meet ALL of:
1. **Repeatable**: The task type is likely to recur (not a one-off personal conversation)
2. **Transferable**: The approach/solution would help others facing the same problem
3. **Technical depth**: Contains non-trivial steps, commands, code, configs, or diagnostic reasoning

Worth distilling (must meet criteria above AND at least ONE below):
- Solves a recurring technical problem with a specific approach/workflow
- Went through trial-and-error (wrong approach then corrected) — the learning is valuable
- Involves non-obvious usage of specific tools, APIs, or frameworks
- Contains debugging/troubleshooting with diagnostic reasoning
- Shows how to combine multiple tools/services to accomplish a technical goal
- Contains deployment, configuration, or infrastructure setup steps
- Demonstrates a reusable data processing or automation pipeline

NOT worth distilling (if ANY matches, return shouldGenerate=false):
- Pure factual Q&A with no process ("what is TCP", "what's the capital of France")
- Single-turn simple answers with no workflow
- Conversation too fragmented or incoherent to extract a clear process
- One-off personal tasks: identity confirmation, preference setting, self-introduction
- Casual chat, opinion discussion, news commentary, brainstorming without actionable output
- Simple information lookup or summarization (e.g. "summarize this article", "explain X concept")
- Organizing/listing personal information (work history, resume, contacts)
- Generic product/system overviews without specific operational steps
- Tasks where the "steps" are just the AI answering questions (no real workflow)

Task title: {title}
Task summary:
{summary}

Reply in JSON only, no extra text:
{{
  "shouldGenerate": boolean,
  "reason": "brief explanation",
  "suggestedName": "kebab-case-name",
  "suggestedTags": ["tag1", "tag2"],
  "confidence": 0.0-1.0
}}'''


UPGRADE_EVAL_PROMPT = '''You are a skill upgrade evaluation expert.

Existing skill (v{version}):
Name: {skill_name}
Content:
{skill_content}

Newly completed task:
Title: {title}
Summary:
{summary}

Does the new task bring substantive improvements to the existing skill?

Worth upgrading (any one qualifies):
1. Faster — shorter path discovered
2. More elegant — cleaner, follows best practices better
3. More convenient — fewer dependencies or complexity
4. Fewer tokens — less exploration/trial-and-error needed
5. More accurate — corrects wrong parameters/steps in old skill
6. More robust — adds edge cases, error handling
7. New scenario — covers a variant the old skill didn't
8. Fixes outdated info — old skill has stale information

NOT worth upgrading:
- New task is identical to existing skill
- New task's approach is worse than existing skill
- Differences are trivial

Reply in JSON only, no extra text:
{{
  "shouldUpgrade": boolean,
  "upgradeType": "refine" | "extend" | "fix",
  "dimensions": ["dimension1", "dimension2"],
  "reason": "brief explanation",
  "mergeStrategy": "how to merge the new knowledge",
  "confidence": 0.0-1.0
}}'''


class SkillEvaluator:
    """
    Evaluates whether a task should generate a skill or
    whether an existing skill should be upgraded.
    """
    
    # Patterns that indicate non-generatable tasks
    TRIVIAL_PATTERNS = [
        re.compile(r"^(test|testing|hello|hi|hey|ok|okay|yes|no|yeah|nope)\s*[.!?]*$", re.IGNORECASE),
        re.compile(r"^(哈哈|好的|嗯|是的|不是|谢谢|你好)\s*[.!?]*$"),
    ]
    
    # Patterns that indicate technical depth worth extracting
    TECHNICAL_PATTERNS = [
        re.compile(r"(docker|git|kubernetes|aws|azure|gcp|linux|shell|bash|python|javascript|typescript|api|server|database|sql|nosql|deployment|ci/cd|pipeline)"),
        re.compile(r"(error|bug|fix|debug|issue|problem|solution|approach|steps|commands|code|script|config|setup|install|configure)"),
        re.compile(r"(deploy|build|test|run|execute|install|setup|configure|create|generate)"),
    ]
    
    def __init__(
        self,
        llm_call_fn: Callable[[str], str],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            llm_call_fn: Function that takes a prompt and returns LLM response
            config: Configuration options
        """
        self.llm_call = llm_call_fn
        self.config = config or {}
    
    def evaluate_create(
        self,
        title: str,
        summary: str
    ) -> CreateEvalResult:
        """
        Evaluate whether a task should generate a skill.
        
        Args:
            title: Task title
            summary: Task summary
        
        Returns:
            CreateEvalResult with decision
        """
        # Quick heuristics check first
        if self._is_trivial_task(title, summary):
            return CreateEvalResult(
                should_generate=False,
                reason="Task appears to be trivial or personal - not worth extracting as a reusable skill.",
                suggested_name="",
                suggested_tags=[],
                confidence=0.95
            )
        
        if not self._has_technical_depth(summary):
            return CreateEvalResult(
                should_generate=False,
                reason="Task lacks technical depth or reusable workflow patterns.",
                suggested_name="",
                suggested_tags=[],
                confidence=0.8
            )
        
        # Use LLM for detailed evaluation
        try:
            prompt = CREATE_EVAL_PROMPT.format(
                title=title[:500],
                summary=summary[:2000]
            )
            response = self.llm_call(prompt)
            return self._parse_create_eval_response(response)
        except Exception as e:
            # Fallback to heuristics
            return self._fallback_create_eval(title, summary)
    
    def evaluate_upgrade(
        self,
        skill: Skill,
        skill_content: str,
        new_title: str,
        new_summary: str
    ) -> UpgradeEvalResult:
        """
        Evaluate whether an existing skill should be upgraded.
        
        Args:
            skill: Existing skill
            skill_content: Current skill content
            new_title: New task title
            new_summary: New task summary
        
        Returns:
            UpgradeEvalResult with decision
        """
        try:
            prompt = UPGRADE_EVAL_PROMPT.format(
                version=skill.version,
                skill_name=skill.name,
                skill_content=skill_content[:3000],
                title=new_title[:500],
                summary=new_summary[:2000]
            )
            response = self.llm_call(prompt)
            return self._parse_upgrade_eval_response(response)
        except Exception:
            return UpgradeEvalResult(
                should_upgrade=False,
                upgrade_type="refine",
                dimensions=[],
                reason="LLM evaluation failed - skipping upgrade",
                merge_strategy="",
                confidence=0.0
            )
    
    def _is_trivial_task(self, title: str, summary: str) -> bool:
        """Check if task appears trivial"""
        combined = f"{title} {summary}".lower()
        
        trivial_count = 0
        for pattern in self.TRIVIAL_PATTERNS:
            if pattern.search(combined):
                trivial_count += 1
        
        # If multiple trivial patterns match, likely trivial
        if trivial_count >= 2:
            return True
        
        # Check for very short content
        if len(summary.strip()) < 50:
            return True
        
        return False
    
    def _has_technical_depth(self, summary: str) -> bool:
        """Check if summary has technical depth"""
        technical_count = 0
        for pattern in self.TECHNICAL_PATTERNS:
            if pattern.search(summary.lower()):
                technical_count += 1
        
        return technical_count >= 1
    
    def _parse_create_eval_response(self, response: str) -> CreateEvalResult:
        """Parse LLM response for create evaluation"""
        import json
        
        try:
            # Try to extract JSON from response
            data = self._extract_json(response)
            
            return CreateEvalResult(
                should_generate=data.get('shouldGenerate', False),
                reason=data.get('reason', ''),
                suggested_name=data.get('suggestedName', ''),
                suggested_tags=data.get('suggestedTags', []),
                confidence=data.get('confidence', 0.5)
            )
        except Exception:
            return CreateEvalResult(
                should_generate=False,
                reason="Failed to parse LLM response",
                suggested_name="",
                suggested_tags=[],
                confidence=0.0
            )
    
    def _parse_upgrade_eval_response(self, response: str) -> UpgradeEvalResult:
        """Parse LLM response for upgrade evaluation"""
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
                reason="Failed to parse LLM response",
                merge_strategy="",
                confidence=0.0
            )
    
    def _extract_json(self, response: str) -> Dict[str, Any]:
        """Extract JSON from LLM response"""
        import json
        
        # Try direct parse
        try:
            return json.loads(response)
        except:
            pass
        
        # Try to find JSON in code blocks
        import re
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        # Try to extract from response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except:
                pass
        
        raise ValueError("Could not extract JSON from response")
    
    def _fallback_create_eval(
        self,
        title: str,
        summary: str
    ) -> CreateEvalResult:
        """Fallback evaluation using heuristics"""
        if not self._has_technical_depth(summary):
            return CreateEvalResult(
                should_generate=False,
                reason="No technical depth detected",
                suggested_name="",
                suggested_tags=[],
                confidence=0.6
            )
        
        # Generate name from title
        name = self._generate_name_from_title(title)
        tags = self._extract_tags(summary)
        
        return CreateEvalResult(
            should_generate=True,
            reason="Technical task with reusable patterns detected",
            suggested_name=name,
            suggested_tags=tags,
            confidence=0.5
        )
    
    def _generate_name_from_title(self, title: str) -> str:
        """Generate kebab-case name from title"""
        import re
        
        # Remove special characters, keep letters/numbers/spaces
        name = re.sub(r'[^\w\s-]', '', title.lower())
        # Replace spaces with hyphens
        name = re.sub(r'[\s_]+', '-', name)
        # Remove multiple hyphens
        name = re.sub(r'-+', '-', name)
        # Take first 50 chars
        name = name[:50].strip('-')
        
        return name or "unnamed-skill"
    
    def _extract_tags(self, summary: str) -> List[str]:
        """Extract tags from summary"""
        import re
        
        # Common technical tags
        tag_patterns = [
            'docker', 'kubernetes', 'git', 'python', 'javascript', 'typescript',
            'api', 'database', 'sql', 'linux', 'shell', 'bash', 'aws', 'gcp',
            'azure', 'deployment', 'testing', 'debugging', 'security',
            'performance', 'monitoring', 'logging', 'ci/cd', 'devops'
        ]
        
        summary_lower = summary.lower()
        found_tags = []
        
        for tag in tag_patterns:
            if tag in summary_lower:
                found_tags.append(tag)
        
        return found_tags[:5]  # Max 5 tags
