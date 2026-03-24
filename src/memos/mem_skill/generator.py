"""
Skill generator - generates SKILL.md from completed tasks.
"""

import os
import re
import json
from typing import List, Optional, Callable, Dict, Any, Tuple
from dataclasses import dataclass

from .base import Skill, SkillVersion, EvalResult, CompanionFile, SkillStatus, UpgradeType
from .types import CreateEvalResult, EvalVerificationResult, ValidationResult


# Prompts for skill generation
STEP1_SKILL_MD_PROMPT = '''You are a Skill creation expert. Your job is to distill a completed task's execution record into a reusable SKILL.md file.

## Core principles

### Progressive disclosure
- The frontmatter description (~100 words) is ALWAYS in the agent's context — it must be self-sufficient for deciding whether to use this skill.
- The SKILL.md body loads when triggered — keep it under 400 lines, focused, no fluff.
- If the task involved large configs/scripts, mention them but DON'T inline everything.

### Description as trigger mechanism
Write it "proactively":
- List the situations, keywords, and phrasings that should trigger it.
- Bad: "How to deploy Node.js to Docker"
- Good: "How to containerize and deploy a Node.js application using Docker. Use when the user mentions Docker deployment, Dockerfile writing, container builds..."

### Writing style
- Use imperative form
- Explain WHY for each step
- Generalize from the specific task

## Output format

---
name: "{name}"
description: "{description}"
---

# Title

{content}

## Task record
Title: {title}
Summary: {summary}
Conversation: {conversation}'''

STEP2_SCRIPTS_PROMPT = '''Based on the following SKILL.md and task record, extract reusable automation scripts.

Reply with JSON only:
[
  {{ "filename": "deploy.sh", "content": "#!/bin/bash..." }}
]

If no scripts, reply with: []'''

STEP3_EVALS_PROMPT = '''Based on the following skill, generate realistic test prompts.

Reply with JSON only:
[
  {{
    "id": 1,
    "prompt": "A realistic user message",
    "expectations": ["Expected behavior 1"],
    "trigger_confidence": "high"
  }}
]'''


@dataclass
class SkillGenerateOutput:
    """Output from skill generation"""
    skill: Skill
    version: SkillVersion
    scripts: List[CompanionFile]
    references: List[CompanionFile]
    evals: List[EvalResult]
    validation: ValidationResult


class SkillGenerator:
    """
    Generates SKILL.md and companion files from completed tasks.
    """
    
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
    
    def generate(
        self,
        task_title: str,
        task_summary: str,
        conversation_text: str,
        eval_result: CreateEvalResult,
        skills_store_dir: str
    ) -> SkillGenerateOutput:
        """
        Generate a skill from a completed task.
        
        Args:
            task_title: Title of the completed task
            task_summary: Summary of the task
            conversation_text: Full conversation text
            eval_result: Evaluation result suggesting skill creation
            skills_store_dir: Directory to store skill files
        
        Returns:
            SkillGenerateOutput with generated skill and metadata
        """
        import uuid
        from datetime import datetime
        
        # Create skill directory
        dir_path = os.path.join(skills_store_dir, eval_result.suggested_name)
        os.makedirs(dir_path, exist_ok=True)
        
        # Step 1: Generate SKILL.md
        skill_md_content = self._generate_skill_md(
            task_title,
            task_summary,
            conversation_text,
            eval_result
        )
        
        skill_md_path = os.path.join(dir_path, "SKILL.md")
        with open(skill_md_path, 'w', encoding='utf-8') as f:
            f.write(skill_md_content)
        
        # Step 2: Extract scripts
        scripts = self._extract_scripts(skill_md_content, conversation_text)
        if scripts:
            scripts_dir = os.path.join(dir_path, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            for script in scripts:
                with open(os.path.join(scripts_dir, script.filename), 'w', encoding='utf-8') as f:
                    f.write(script.content)
        
        # Step 2b: Extract references
        references = self._extract_references(skill_md_content, conversation_text)
        if references:
            refs_dir = os.path.join(dir_path, "references")
            os.makedirs(refs_dir, exist_ok=True)
            for ref in references:
                with open(os.path.join(refs_dir, ref.filename), 'w', encoding='utf-8') as f:
                    f.write(ref.content)
        
        # Step 3: Generate evals
        evals = self._generate_evals(skill_md_content)
        if evals:
            evals_dir = os.path.join(dir_path, "evals")
            os.makedirs(evals_dir, exist_ok=True)
            with open(os.path.join(evals_dir, "evals.json"), 'w', encoding='utf-8') as f:
                json.dump({
                    'skill_name': eval_result.suggested_name,
                    'evals': [e.to_dict() for e in evals]
                }, f, indent=2, ensure_ascii=False)
        
        # Step 4: Validate
        validation = self._validate_skill(dir_path, skill_md_content)
        
        # Create skill object
        now = datetime.now().timestamp() * 1000
        skill_id = str(uuid.uuid4())
        
        status = SkillStatus.ACTIVE if (
            validation.quality_score is not None and 
            validation.quality_score >= 6.0
        ) else SkillStatus.DRAFT
        
        skill = Skill(
            id=skill_id,
            name=eval_result.suggested_name,
            description=self._parse_description(skill_md_content),
            version=1,
            status=status,
            tags=eval_result.suggested_tags,
            source_type="task",
            dir_path=dir_path,
            installed=0,
            owner="agent:main",
            quality_score=validation.quality_score,
            created_at=now,
            updated_at=now
        )
        
        # Create version object
        version = SkillVersion(
            id=str(uuid.uuid4()),
            skill_id=skill_id,
            version=1,
            content=skill_md_content,
            changelog=f"Initial generation from task \"{task_title}\"",
            change_summary=self._generate_change_summary(
                task_title, eval_result, scripts, evals
            ),
            upgrade_type=UpgradeType.CREATE,
            source_task_id=None,  # Would be set if we have task ID
            metrics={
                'dimensions': [],
                'confidence': eval_result.confidence,
                'scripts': [s.filename for s in scripts],
                'references': [r.filename for r in references],
                'eval_count': len(evals),
                'validation': validation.to_dict()
            },
            quality_score=validation.quality_score,
            created_at=now
        )
        
        return SkillGenerateOutput(
            skill=skill,
            version=version,
            scripts=scripts,
            references=references,
            evals=evals,
            validation=validation
        )
    
    def _generate_skill_md(
        self,
        task_title: str,
        task_summary: str,
        conversation_text: str,
        eval_result: CreateEvalResult
    ) -> str:
        """Generate SKILL.md content"""
        # Detect language
        lang = self._detect_language(conversation_text)
        
        prompt = f'''Generate a SKILL.md for this task:

Title: {task_title}
Summary: {task_summary}
Conversation: {conversation_text[:3000]}
Suggested name: {eval_result.suggested_name}
Language: {lang}

Output ONLY the complete SKILL.md content in {lang}.'''
        
        content = self.llm_call(prompt)
        
        # Ensure frontmatter exists
        if not content.startswith('---'):
            content = f'''---
name: "{eval_result.suggested_name}"
description: "{eval_result.reason[:200]}"
---

{content}'''
        
        return content
    
    def _extract_scripts(
        self,
        skill_md_content: str,
        conversation_text: str
    ) -> List[CompanionFile]:
        """Extract automation scripts from task"""
        try:
            prompt = STEP2_SCRIPTS_PROMPT.format(
                skill_content=skill_md_content[:2000],
                conversation=conversation_text[:2000]
            )
            response = self.llm_call(prompt)
            
            data = self._extract_json(response)
            if not data:
                return []
            
            return [CompanionFile(
                filename=item['filename'],
                content=item['content'],
                file_type='script'
            ) for item in data]
        except Exception:
            return []
    
    def _extract_references(
        self,
        skill_md_content: str,
        conversation_text: str
    ) -> List[CompanionFile]:
        """Extract reference documentation"""
        try:
            prompt = f'''Based on the SKILL.md and task record, extract reference documentation.

SKILL.md:
{skill_md_content[:2000]}

Conversation:
{conversation_text[:2000]}

Reply with JSON only:
[
  {{ "filename": "api-notes.md", "content": "# API Reference..." }}
]

If nothing worth extracting, reply: []'''
            
            response = self.llm_call(prompt)
            data = self._extract_json(response)
            
            if not data:
                return []
            
            return [CompanionFile(
                filename=item['filename'],
                content=item['content'],
                file_type='reference'
            ) for item in data]
        except Exception:
            return []
    
    def _generate_evals(self, skill_md_content: str) -> List[EvalResult]:
        """Generate test cases for the skill"""
        try:
            prompt = STEP3_EVALS_PROMPT.format(skill_content=skill_md_content[:3000])
            response = self.llm_call(prompt)
            
            data = self._extract_json(response)
            if not data:
                return []
            
            return [EvalResult(
                id=item['id'],
                prompt=item['prompt'],
                expectations=item.get('expectations', []),
                trigger_confidence=item.get('trigger_confidence', 'medium')
            ) for item in data]
        except Exception:
            return []
    
    def _validate_skill(
        self,
        dir_path: str,
        skill_md_content: str
    ) -> ValidationResult:
        """Validate skill quality"""
        result = ValidationResult(quality_score=None)
        
        # Basic validation
        if len(skill_md_content) < 100:
            result.add_error("Skill content too short")
            return result
        
        # Check for required sections
        required_sections = ['## Steps', '# ']
        for section in required_sections:
            if section not in skill_md_content:
                result.add_warning(f"Missing recommended section: {section}")
        
        # Estimate quality score (0-10)
        score = 5.0
        
        if len(skill_md_content) > 500:
            score += 1.0
        if '```' in skill_md_content:  # Has code blocks
            score += 1.0
        if '## When to use' in skill_md_content or '## 使用场景' in skill_md_content:
            score += 1.0
        if '## Pitfall' in skill_md_content or '## 陷阱' in skill_md_content:
            score += 1.0
        if '## Companion' in skill_md_content or '## 附属' in skill_md_content:
            score += 0.5
        
        result.quality_score = min(score, 10.0)
        
        if score < 6:
            result.add_warning("Quality score below 6 - skill will be set as draft")
        
        return result
    
    def _detect_language(self, text: str) -> str:
        """Detect language of text"""
        cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))
        total = len(text.replace(/\s+/g, '')) or 1
        
        if cjk_count / total > 0.15:
            return "Chinese"
        return "English"
    
    def _parse_description(self, skill_md_content: str) -> str:
        """Parse description from frontmatter"""
        match = re.search(r'description:\s*["\'](.+?)["\']', skill_md_content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _generate_change_summary(
        self,
        task_title: str,
        eval_result: CreateEvalResult,
        scripts: List[CompanionFile],
        evals: List[EvalResult]
    ) -> str:
        """Generate change summary for version"""
        parts = [f'From task "{task_title}"']
        
        if eval_result.reason:
            parts.append(f'Reason: {eval_result.reason[:100]}')
        
        if scripts:
            parts.append(f'{len(scripts)} scripts extracted')
        
        if evals:
            parts.append(f'{len(evals)} test cases generated')
        
        return '. '.join(parts)
    
    def _extract_json(self, response: str) -> Any:
        """Extract JSON from LLM response"""
        try:
            import json
            return json.loads(response)
        except:
            pass
        
        # Try to find JSON array
        start = response.find('[')
        end = response.rfind(']') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except:
                pass
        
        # Try to find JSON object
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except:
                pass
        
        return None
