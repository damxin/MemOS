"""
Skill installer - handles skill installation and lifecycle.
"""

import os
import shutil
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
import json

from .base import Skill, SkillVisibility, SkillStatus


class SkillInstaller:
    """
    Handles skill installation, activation, and deactivation.
    
    Installation flow:
    1. Validate skill package
    2. Copy to skills directory
    3. Register with storage
    4. Generate embeddings
    """
    
    def __init__(
        self,
        skills_dir: str,
        llm_call_fn: Optional[Callable[[str], str]] = None,
        embedder_fn: Optional[Callable[[str], List[float]]] = None
    ):
        """
        Args:
            skills_dir: Base directory for installed skills
            llm_call_fn: Optional LLM call function for embedding generation
            embedder_fn: Optional function to generate embeddings
        """
        self.skills_dir = skills_dir
        self.llm_call = llm_call_fn
        self.embedder_fn = embedder_fn
    
    def install(
        self,
        skill: Skill,
        force: bool = False
    ) -> Skill:
        """
        Install a skill.
        
        Args:
            skill: Skill to install
            force: Overwrite existing installation
        
        Returns:
            Updated skill with installed=1
        """
        if skill.installed and not force:
            return skill
        
        # Create skills directory
        target_dir = os.path.join(self.skills_dir, skill.name)
        
        if os.path.exists(target_dir) and not force:
            raise ValueError(f"Skill '{skill.name}' already installed. Use force=True to overwrite.")
        
        # Copy skill files
        if os.path.exists(skill.dir_path):
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(skill.dir_path, target_dir)
        
        # Update skill
        skill.installed = 1
        skill.dir_path = target_dir
        skill.updated_at = datetime.now().timestamp() * 1000
        
        return skill
    
    def uninstall(self, skill: Skill) -> Skill:
        """
        Uninstall a skill.
        
        Args:
            skill: Skill to uninstall
        
        Returns:
            Updated skill with installed=0
        """
        if not skill.installed:
            return skill
        
        # Remove installed files
        if os.path.exists(skill.dir_path):
            shutil.rmtree(skill.dir_path)
        
        skill.installed = 0
        skill.updated_at = datetime.now().timestamp() * 1000
        
        return skill
    
    def activate(self, skill: Skill) -> Skill:
        """
        Activate a skill (set status to active).
        
        Args:
            skill: Skill to activate
        
        Returns:
            Updated skill
        """
        skill.status = SkillStatus.ACTIVE
        skill.updated_at = datetime.now().timestamp() * 1000
        return skill
    
    def deactivate(self, skill: Skill) -> Skill:
        """
        Deactivate a skill (set status to draft).
        
        Args:
            skill: Skill to deactivate
        
        Returns:
            Updated skill
        """
        skill.status = SkillStatus.DRAFT
        skill.updated_at = datetime.now().timestamp() * 1000
        return skill
    
    def deprecate(self, skill: Skill, reason: str = "") -> Skill:
        """
        Deprecate a skill.
        
        Args:
            skill: Skill to deprecate
            reason: Reason for deprecation
        
        Returns:
            Updated skill
        """
        skill.status = SkillStatus.DEPRECATED
        skill.updated_at = datetime.now().timestamp() * 1000
        
        # Add deprecation notice to metadata
        skill.metadata['deprecated_at'] = datetime.now().timestamp() * 1000
        skill.metadata['deprecated_reason'] = reason
        
        return skill
    
    def validate_package(self, package_path: str) -> Dict[str, Any]:
        """
        Validate a skill package before installation.
        
        Args:
            package_path: Path to skill package directory
        
        Returns:
            Validation result dict
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'has_skill_md': False,
            'has_evals': False,
            'has_scripts': False
        }
        
        # Check SKILL.md exists
        skill_md_path = os.path.join(package_path, "SKILL.md")
        if os.path.exists(skill_md_path):
            result['has_skill_md'] = True
            
            # Validate frontmatter
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.startswith('---'):
                result['warnings'].append("SKILL.md should start with frontmatter")
            
            if 'name:' not in content:
                result['errors'].append("SKILL.md missing 'name' in frontmatter")
        else:
            result['valid'] = False
            result['errors'].append("SKILL.md not found")
        
        # Check for companion files
        scripts_dir = os.path.join(package_path, "scripts")
        if os.path.exists(scripts_dir) and os.listdir(scripts_dir):
            result['has_scripts'] = True
        
        evals_dir = os.path.join(package_path, "evals")
        if os.path.exists(evals_dir) and os.listdir(evals_dir):
            result['has_evals'] = True
            # Validate evals.json
            evals_file = os.path.join(evals_dir, "evals.json")
            if os.path.exists(evals_file):
                try:
                    with open(evals_file, 'r', encoding='utf-8') as f:
                        evals_data = json.load(f)
                    if 'evals' not in evals_data:
                        result['warnings'].append("evals.json missing 'evals' key")
                except Exception as e:
                    result['warnings'].append(f"Could not parse evals.json: {e}")
        
        return result


class SkillRegistry:
    """
    Registry of installed and available skills.
    """
    
    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir
    
    def list_installed(self) -> List[str]:
        """List all installed skill names"""
        if not os.path.exists(self.skills_dir):
            return []
        
        return [
            name for name in os.listdir(self.skills_dir)
            if os.path.isdir(os.path.join(self.skills_dir, name))
            and os.path.exists(os.path.join(self.skills_dir, name, "SKILL.md"))
        ]
    
    def get_skill_path(self, skill_name: str) -> Optional[str]:
        """Get path to installed skill"""
        path = os.path.join(self.skills_dir, skill_name, "SKILL.md")
        return path if os.path.exists(path) else None
    
    def load_skill_content(self, skill_name: str) -> Optional[str]:
        """Load SKILL.md content for a skill"""
        path = self.get_skill_path(skill_name)
        if not path:
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def get_all_skills_with_content(self) -> List[Dict[str, Any]]:
        """Get all installed skills with their content"""
        skills = []
        
        for name in self.list_installed():
            content = self.load_skill_content(name)
            if content:
                skills.append({
                    'name': name,
                    'content': content,
                    'path': self.get_skill_path(name)
                })
        
        return skills
