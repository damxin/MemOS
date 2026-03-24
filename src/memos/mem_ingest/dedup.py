"""
Smart deduplication using embeddings and LLM judgment.
"""

import hashlib
from typing import List, Optional, Tuple, Callable, Dict, Any

from .types import DedupResult, DedupCandidate


class Deduplicator:
    """
    Smart deduplication for memory chunks.
    
    Uses a two-phase approach:
    1. Vector similarity search (fast candidate retrieval)
    2. LLM judgment (accurate dedup decision)
    
    Reference: Local Plugin src/ingest/dedup.ts
    """
    
    def __init__(
        self,
        embedder: Callable[[str], List[float]],
        llm_call_fn: Optional[Callable[[str], str]] = None,
        vector_threshold: float = 0.92,
        llm_threshold: float = 0.85,
        top_n: int = 5
    ):
        """
        Args:
            embedder: Function that generates embeddings for text
            llm_call_fn: Optional LLM call for detailed judgment
            vector_threshold: Cosine similarity threshold for candidates
            llm_threshold: LLM judgment threshold for duplicate
            top_n: Number of top candidates to retrieve
        """
        self.embedder = embedder
        self.llm_call = llm_call_fn
        self.vector_threshold = vector_threshold
        self.llm_threshold = llm_threshold
        self.top_n = top_n
    
    def check_duplicate(
        self,
        new_text: str,
        existing_chunks: List[Dict[str, Any]],
        use_llm: bool = True
    ) -> DedupResult:
        """
        Check if new text is a duplicate of existing chunks.
        
        Args:
            new_text: New text to check
            existing_chunks: List of existing chunks with 'id' and 'content'
            use_llm: Whether to use LLM judgment for final decision
        
        Returns:
            DedupResult with decision
        """
        if not existing_chunks:
            return DedupResult(
                is_duplicate=False,
                duplicate_id=None,
                decision="new",
                confidence=1.0
            )
        
        # Phase 1: Vector similarity search
        candidates = self._find_similar_chunks(new_text, existing_chunks)
        
        if not candidates:
            return DedupResult(
                is_duplicate=False,
                duplicate_id=None,
                decision="new",
                confidence=1.0
            )
        
        # Phase 2: LLM judgment (if enabled)
        if use_llm and self.llm_call:
            return self._llm_judge(new_text, candidates)
        
        # Fallback: Use best similarity score
        best = candidates[0]
        is_dup = best['score'] >= self.vector_threshold
        
        return DedupResult(
            is_duplicate=is_dup,
            duplicate_id=best['chunk_id'] if is_dup else None,
            decision="duplicate" if is_dup else "new",
            confidence=best['score']
        )
    
    def _find_similar_chunks(
        self,
        new_text: str,
        existing_chunks: List[Dict[str, Any]]
    ) -> List[DedupCandidate]:
        """Find similar chunks using vector embeddings"""
        try:
            new_embedding = self.embedder(new_text[:1000])  # Truncate for embedding
        except Exception:
            return []
        
        scored = []
        for chunk in existing_chunks:
            chunk_text = chunk.get('content', '')
            chunk_id = chunk.get('id', chunk.get('chunk_id', ''))
            
            if not chunk_id or not chunk_text:
                continue
            
            # Try to get existing embedding
            chunk_embedding = chunk.get('embedding')
            if not chunk_embedding:
                try:
                    chunk_embedding = self.embedder(chunk_text[:1000])
                except Exception:
                    continue
            
            score = cosine_similarity(new_embedding, chunk_embedding)
            
            if score >= self.vector_threshold:
                scored.append({
                    'chunk_id': chunk_id,
                    'score': score,
                    'content': chunk_text[:500],  # Truncate for LLM
                    'embedding': chunk_embedding
                })
        
        # Sort by score descending
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:self.top_n]
    
    def _llm_judge(
        self,
        new_text: str,
        candidates: List[DedupCandidate]
    ) -> DedupResult:
        """Use LLM to judge if new text is a duplicate"""
        if not self.llm_call:
            best = candidates[0]
            return DedupResult(
                is_duplicate=False,
                duplicate_id=None,
                decision="error",
                confidence=0.0
            )
        
        prompt = self._build_judge_prompt(new_text, candidates)
        
        try:
            response = self.llm_call(prompt)
            return self._parse_judge_response(response, candidates)
        except Exception:
            best = candidates[0]
            return DedupResult(
                is_duplicate=False,
                duplicate_id=None,
                decision="error",
                confidence=0.0
            )
    
    def _build_judge_prompt(
        self,
        new_text: str,
        candidates: List[DedupCandidate]
    ) -> str:
        """Build LLM judgment prompt"""
        candidate_texts = "\n\n".join([
            f"Candidate {i+1} (similarity={c['score']:.2f}):\n{c['content']}"
            for i, c in enumerate(candidates)
        ])
        
        return f"""判断新文本是否与已有文本重复。

新文本:
{new_text[:1000]}

已有相似文本:
{candidate_texts}

判断规则:
- DUPLICATE: 新文本与已有文本核心内容相同，只是表达方式略有不同
- UPDATE: 新文本是已有文本的更新版本
- NEW: 新文本与已有文本讨论的是不同主题

请用JSON格式回答:
{{
  "decision": "duplicate|update|new",
  "duplicate_id": "如果decision是duplicate或update，提供已有文本的chunk_id",
  "reasoning": "简短的原因说明"
}}"""
    
    def _parse_judge_response(
        self,
        response: str,
        candidates: List[DedupCandidate]
    ) -> DedupResult:
        """Parse LLM judgment response"""
        import json
        import re
        
        try:
            # Try to extract JSON
            data = self._extract_json(response)
            
            decision = data.get('decision', 'new').lower()
            dup_id = data.get('duplicate_id')
            
            # Map decision to result
            if decision == 'duplicate':
                return DedupResult(
                    is_duplicate=True,
                    duplicate_id=dup_id,
                    decision="duplicate",
                    confidence=0.9
                )
            elif decision == 'update':
                return DedupResult(
                    is_duplicate=True,
                    duplicate_id=dup_id,
                    decision="update",
                    confidence=0.85
                )
            else:
                return DedupResult(
                    is_duplicate=False,
                    duplicate_id=None,
                    decision="new",
                    confidence=0.95
                )
        except Exception:
            # Fallback to best candidate
            best = candidates[0]
            return DedupResult(
                is_duplicate=False,
                duplicate_id=None,
                decision="new",
                confidence=0.8
            )
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from text"""
        import json
        
        try:
            return json.loads(text)
        except:
            pass
        
        # Try to find JSON in text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                pass
        
        return {}


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if len(a) != len(b):
        return 0.0
    
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def hash_content(content: str) -> str:
    """Generate hash for content-based dedup"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def simple_dedup_check(
    new_content: str,
    existing_contents: List[str],
    min_similarity: float = 0.8
) -> Tuple[bool, Optional[int]]:
    """
    Simple content-based deduplication without embeddings.
    
    Returns:
        Tuple of (is_duplicate, existing_index)
    """
    new_lower = new_content.lower()
    new_words = set(new_lower.split())
    
    best_score = 0.0
    best_idx = None
    
    for i, existing in enumerate(existing_contents):
        existing_lower = existing.lower()
        existing_words = set(existing_lower.split())
        
        if not existing_words:
            continue
        
        # Jaccard similarity
        intersection = len(new_words & existing_words)
        union = len(new_words | existing_words)
        
        if union > 0:
            score = intersection / union
        
        if score > best_score:
            best_score = score
            best_idx = i
    
    if best_score >= min_similarity and best_idx is not None:
        return True, best_idx
    
    return False, None
