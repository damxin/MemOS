"""
LLM-based judgment for deduplication and content analysis.
"""

import re
from typing import List, Optional, Callable, Dict, Any

from .types import LLMJudgeResult, ContentType


# Prompt for deduplication judgment
DEDUP_JUDGE_PROMPT = '''判断新文本是否与已有文本重复或更新。

新文本:
{new_text}

已有文本 #{chunk_id}:
{existing_text}

判断:
1. DUPLICATE - 新文本与已有文本核心内容相同，只是表达方式略有不同
2. UPDATE - 新文本是已有文本的更新版本，提供了更新的信息
3. NEW - 新文本与已有文本讨论的是不同主题

JSON格式回答:
{{
  "decision": "duplicate|update|new",
  "confidence": 0.0-1.0,
  "reasoning": "简短原因"
}}'''


# Prompt for content type classification
CONTENT_TYPE_PROMPT = '''分析以下文本的内容类型。

文本:
{text}

类型选项:
- technical: 技术内容（代码、配置、错误堆栈等）
- conversational: 对话内容（问答、交流）
- informational: 信息内容（解释、说明）
- procedural: 步骤内容（教程、指南）

JSON格式回答:
{{
  "type": "technical|conversational|informational|procedural",
  "confidence": 0.0-1.0,
  "keywords": ["关键词1", "关键词2"]
}}'''


class LLMJudge:
    """
    LLM-based judgment for various decisions in the ingest pipeline.
    
    Uses structured prompts to make judgments about:
    - Deduplication decisions
    - Content type classification
    - Quality assessment
    """
    
    def __init__(self, llm_call_fn: Callable[[str], str]):
        """
        Args:
            llm_call_fn: Function that takes a prompt and returns LLM response
        """
        self.llm_call = llm_call_fn
    
    def judge_duplicate(
        self,
        new_text: str,
        existing_text: str,
        chunk_id: str = "unknown"
    ) -> LLMJudgeResult:
        """
        Judge if new text is a duplicate of existing text.
        
        Args:
            new_text: New text to check
            existing_text: Existing text to compare against
            chunk_id: ID of existing chunk for reference
        
        Returns:
            LLMJudgeResult with decision
        """
        prompt = DEDUP_JUDGE_PROMPT.format(
            new_text=new_text[:2000],
            existing_text=existing_text[:2000],
            chunk_id=chunk_id
        )
        
        try:
            response = self.llm_call(prompt)
            return self._parse_judge_response(response)
        except Exception:
            return LLMJudgeResult(
                decision="new",
                confidence=0.0,
                reasoning="LLM call failed"
            )
    
    def classify_content_type(self, text: str) -> ContentType:
        """
        Classify the type of content.
        
        Args:
            text: Text to classify
        
        Returns:
            ContentType enum value
        """
        prompt = CONTENT_TYPE_PROMPT.format(text=text[:1000])
        
        try:
            response = self.llm_call(prompt)
            return self._parse_type_response(response)
        except Exception:
            return ContentType.INFORMATIONAL
    
    def assess_quality(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Assess content quality.
        
        Args:
            text: Text to assess
            context: Optional context for assessment
        
        Returns:
            Dict with quality metrics
        """
        quality_prompt = f'''评估以下文本的质量。

文本:
{text[:1500]}

评估维度:
1. clarity - 清晰度
2. completeness - 完整性
3. usefulness - 有用性
4. actionability - 可操作性

JSON格式回答:
{{
  "scores": {{
    "clarity": 1-10,
    "completeness": 1-10,
    "usefulness": 1-10,
    "actionability": 1-10
  }},
  "overall_score": 1-10,
  "strengths": ["优点1", "优点2"],
  "issues": ["问题1", "问题2"]
}}'''
        
        try:
            response = self.llm_call(quality_prompt)
            return self._parse_quality_response(response)
        except Exception:
            return {
                'scores': {'clarity': 5, 'completeness': 5, 'usefulness': 5, 'actionability': 5},
                'overall_score': 5.0,
                'strengths': [],
                'issues': ['Quality assessment failed']
            }
    
    def _parse_judge_response(self, response: str) -> LLMJudgeResult:
        """Parse LLM judgment response"""
        import json
        
        try:
            data = self._extract_json(response)
            
            return LLMJudgeResult(
                decision=data.get('decision', 'new').lower(),
                confidence=data.get('confidence', 0.5),
                reasoning=data.get('reasoning', '')
            )
        except Exception:
            return LLMJudgeResult(
                decision="new",
                confidence=0.0,
                reasoning="Failed to parse response"
            )
    
    def _parse_type_response(self, response: str) -> ContentType:
        """Parse content type response"""
        from .types import ContentType
        
        try:
            data = self._extract_json(response)
            type_str = data.get('type', 'informational').lower()
            
            type_map = {
                'technical': ContentType.TECHNICAL,
                'conversational': ContentType.CONVERSATIONAL,
                'informational': ContentType.INFORMATIONAL,
                'procedural': ContentType.PROCEDURAL,
            }
            
            return type_map.get(type_str, ContentType.INFORMATIONAL)
        except Exception:
            return ContentType.INFORMATIONAL
    
    def _parse_quality_response(self, response: str) -> Dict[str, Any]:
        """Parse quality assessment response"""
        try:
            data = self._extract_json(response)
            return {
                'scores': data.get('scores', {}),
                'overall_score': data.get('overall_score', 5.0),
                'strengths': data.get('strengths', []),
                'issues': data.get('issues', [])
            }
        except Exception:
            return {
                'scores': {},
                'overall_score': 5.0,
                'strengths': [],
                'issues': ['Parse failed']
            }
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text"""
        import json
        
        try:
            return json.loads(text)
        except:
            pass
        
        # Find JSON in text
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                pass
        
        return {}


class SimpleJudge:
    """
    Simple rule-based judgment without LLM.
    
    Useful for fast filtering before LLM judgment.
    """
    
    @staticmethod
    def is_trivial_content(text: str) -> bool:
        """Check if content is trivial/test data"""
        text_lower = text.lower().strip()
        
        trivial_patterns = [
            r'^(test|testing|hello|hi|hey|ok|okay|yes|no|yeah|nope)\s*[.!?]*$',
            r'^(哈哈|好的|嗯|是的|不是|谢谢|你好)\s*[.!?]*$',
            r'^[\s\p{P}]*$',
        ]
        
        for pattern in trivial_patterns:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return True
        
        return False
    
    @staticmethod
    def is_too_short(text: str, min_chars: int = 50) -> bool:
        """Check if content is too short"""
        return len(text.strip()) < min_chars
    
    @staticmethod
    def has_high_repetition(text: str, max_ratio: float = 0.6) -> bool:
        """Check if content has high word repetition"""
        words = text.lower().split()
        if len(words) < 5:
            return False
        
        unique_words = len(set(words))
        ratio = unique_words / len(words)
        
        return ratio < max_ratio
    
    @staticmethod
    def is_dominated_by_code(text: str, max_code_ratio: float = 0.8) -> bool:
        """Check if content is mostly code blocks"""
        code_markers = ['```', '    ', '\t', 'function', 'def ', 'class ', 'import ']
        code_lines = sum(1 for line in text.split('\n') if any(m in line for m in code_markers))
        
        if code_lines == 0:
            return False
        
        total_lines = len(text.split('\n'))
        return code_lines / total_lines > max_code_ratio
