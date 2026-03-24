"""
Hybrid Search Implementation

Combines FTS, vector search, and pattern search with RRF fusion,
MMR re-ranking, and time decay.

Reference: Local Plugin src/recall/engine.ts
"""

from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .rrf import rrf_fuse, rank_fused_scores, RRFFuser
from .mmr import MMRReranker, cosine_similarity
from .recency import RecencyScorer, apply_recency_decay, normalize_scores


class SearchSource(Enum):
    """Available search sources"""
    FTS = "fts"
    VECTOR = "vector"
    PATTERN = "pattern"
    HUB_MEMORY = "hub_memory"


@dataclass
class SearchConfig:
    """Configuration for hybrid search"""
    # RRF parameters
    rrf_k: int = 60
    
    # MMR parameters
    mmr_lambda: float = 0.7
    
    # Recency parameters
    recency_half_life_days: float = 14
    recency_alpha: float = 0.3
    
    # Search limits
    max_results_default: int = 6
    max_results_max: int = 50
    min_score_default: float = 0.45
    
    # Vector search
    vector_search_max_chunks: Optional[int] = None
    
    # Pattern search threshold (min chars)
    pattern_min_chars: int = 2


@dataclass
class SearchCandidate:
    """A search candidate with metadata"""
    id: str
    score: float
    source: SearchSource
    created_at: float = 0
    role: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'score': self.score,
            'source': self.source.value,
            'created_at': self.created_at,
            'role': self.role,
            'summary': self.summary,
            'content': self.content,
            **self.metadata
        }


@dataclass
class SearchHit:
    """A search result hit"""
    id: str
    score: float
    summary: str
    original_excerpt: str
    source: SearchSource
    created_at: float
    role: Optional[str] = None
    owner: Optional[str] = None
    origin: str = "local"
    task_id: Optional[str] = None
    skill_id: Optional[str] = None
    ref: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'score': self.score,
            'summary': self.summary,
            'original_excerpt': self.original_excerpt,
            'source': self.source.value,
            'created_at': self.created_at,
            'role': self.role,
            'owner': self.owner,
            'origin': self.origin,
            'task_id': self.task_id,
            'skill_id': self.skill_id,
            'ref': self.ref
        }


@dataclass
class SearchResult:
    """Complete search result"""
    hits: List[SearchHit]
    meta: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'hits': [h.to_dict() for h in self.hits],
            'meta': self.meta
        }


class HybridSearchEngine:
    """
    Hybrid search engine combining multiple retrieval methods.
    
    Pipeline:
    1. Gather candidates from FTS, vector, pattern search
    2. RRF fusion to combine rankings
    3. MMR re-ranking for diversity
    4. Time decay for recency
    5. Apply thresholds and normalize
    """
    
    def __init__(
        self,
        config: Optional[SearchConfig] = None,
        fts_search_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
        vector_search_fn: Optional[Callable[[List[float], int], List[Tuple[str, float]]]] = None,
        pattern_search_fn: Optional[Callable[[List[str], int], List[Dict[str, Any]]]] = None,
        get_embedding_fn: Optional[Callable[[str], Optional[List[float]]]] = None,
        get_chunk_fn: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        get_timestamp_fn: Optional[Callable[[str], float]] = None
    ):
        """
        Args:
            config: Search configuration
            fts_search_fn: Function(query, limit) -> List[{id, score}]
            vector_search_fn: Function(query_embedding, limit) -> List[(id, score)]
            pattern_search_fn: Function(terms, limit) -> List[{id, score}]
            get_embedding_fn: Function(item_id) -> embedding or None
            get_chunk_fn: Function(chunk_id) -> chunk data or None
            get_timestamp_fn: Function(item_id) -> timestamp_ms
        """
        self.config = config or SearchConfig()
        
        # Search functions
        self.fts_search = fts_search_fn
        self.vector_search = vector_search_fn
        self.pattern_search = pattern_search_fn
        
        # Utility functions
        self.get_embedding = get_embedding_fn or (lambda x: None)
        self.get_chunk = get_chunk_fn or (lambda x: None)
        self.get_timestamp = get_timestamp_fn or (lambda x: 0)
        
        # Components
        self.rrf_fuser = RRFFuser(k=self.config.rrf_k)
        self.mmr_reranker = MMRReranker(lambda_param=self.config.mmr_lambda)
        self.recency_scorer = RecencyScorer(
            half_life_days=self.config.recency_half_life_days,
            alpha=self.config.recency_alpha
        )
    
    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        min_score: Optional[float] = None,
        role_filter: Optional[str] = None,
        owner_filter: Optional[List[str]] = None,
        embedder_fn: Optional[Callable[[str], List[float]]] = None
    ) -> SearchResult:
        """
        Execute hybrid search.
        
        Args:
            query: Search query string
            max_results: Max results to return (default from config)
            min_score: Minimum score threshold (default from config)
            role_filter: Filter by role (e.g., 'user', 'assistant')
            owner_filter: Filter by owner
            embedder_fn: Function to embed query (required for vector search)
        
        Returns:
            SearchResult with hits and metadata
        """
        max_results = min(
            max_results or self.config.max_results_default,
            self.config.max_results_max
        )
        min_score = min_score or self.config.min_score_default
        
        # Expand query for pattern search (extract 2-char terms)
        pattern_terms = self._extract_pattern_terms(query)
        
        # Step 1: Gather candidates from all sources
        fts_candidates = self._search_fts(query, max_results * 5, owner_filter)
        vec_candidates = self._search_vector(query, embedder_fn, max_results * 5, owner_filter)
        pattern_candidates = self._search_pattern(pattern_terms, max_results * 5)
        
        # Convert to ranked lists for RRF
        fts_ranked = [{'id': c['id'], 'score': c['score']} for c in fts_candidates]
        vec_ranked = [{'id': c[0], 'score': c[1]} for c in vec_candidates]
        pattern_ranked = [{'id': c['id'], 'score': c['score']} for c in pattern_candidates]
        
        # Check for repeats
        repeat_note = self.rrf_fuser.check_repeat(query, max_results, min_score)
        
        # Step 2: RRF fusion
        all_lists = [fts_ranked, vec_ranked, pattern_ranked]
        rrf_scores = rrf_fuse(all_lists, k=self.config.rrf_k)
        
        if not rrf_scores:
            return SearchResult(
                hits=[],
                meta={
                    'used_min_score': min_score,
                    'used_max_results': max_results,
                    'total_candidates': 0,
                    'note': repeat_note or "No candidates found for the given query."
                }
            )
        
        # Step 3: MMR re-ranking
        rrf_list = [
            {'id': item_id, 'score': score}
            for item_id, score in rrf_scores.items()
        ]
        rrf_list.sort(key=lambda x: x['score'], reverse=True)
        
        # MMR needs embeddings, so we need to provide a getter
        def get_emb(item_id: str) -> Optional[List[float]]:
            chunk = self.get_chunk(item_id)
            if chunk and 'embedding' in chunk:
                return chunk['embedding']
            return self.get_embedding(item_id)
        
        mmr_results = self.mmr_reranker.rerank(
            rrf_list[:max_results * 2],
            get_emb,
            top_k=max_results * 2
        )
        
        # Step 4: Time decay
        candidates_with_ts = [
            {
                'id': r['id'],
                'score': r['score'],
                'created_at': self.get_timestamp(r['id'])
            }
            for r in mmr_results
        ]
        decayed = apply_recency_decay(
            candidates_with_ts,
            half_life_days=self.config.recency_half_life_days,
            alpha=self.config.recency_alpha
        )
        
        # Step 5: Apply threshold
        sorted_candidates = sorted(decayed, key=lambda x: x['score'], reverse=True)
        top_score = sorted_candidates[0]['score'] if sorted_candidates else 0
        absolute_floor = top_score * min_score * 0.3
        
        # Pre-filter with larger pool for role filter
        pre_limit = max_results * 5 if role_filter else max_results
        filtered = [
            c for c in sorted_candidates
            if c['score'] >= absolute_floor
        ][:pre_limit]
        
        # Step 6: Normalize
        if filtered:
            max_filtered = filtered[0]['score']
            if max_filtered > 0:
                for c in filtered:
                    c['score'] = c['score'] / max_filtered
        
        # Step 7: Build hits
        hits = []
        for candidate in filtered:
            if len(hits) >= max_results:
                break
            
            chunk = self.get_chunk(candidate['id'])
            if not chunk:
                continue
            
            if role_filter and chunk.get('role') != role_filter:
                continue
            
            excerpt = self._make_excerpt(chunk.get('content', ''))
            summary = chunk.get('summary') or excerpt
            
            hits.append(SearchHit(
                id=candidate['id'],
                score=round(candidate['score'], 3),
                summary=summary,
                original_excerpt=excerpt,
                source=SearchSource.FTS,  # TODO: track actual source
                created_at=candidate.get('created_at', 0),
                role=chunk.get('role'),
                origin='local',
                task_id=chunk.get('task_id'),
                skill_id=chunk.get('skill_id'),
                ref={
                    'session_key': chunk.get('session_key', ''),
                    'chunk_id': chunk.get('id', ''),
                    'turn_id': chunk.get('turn_id', ''),
                    'seq': chunk.get('seq', 0)
                }
            ))
        
        return SearchResult(
            hits=hits,
            meta={
                'used_min_score': min_score,
                'used_max_results': max_results,
                'total_candidates': len(rrf_scores),
                'note': repeat_note
            }
        )
    
    def _search_fts(
        self,
        query: str,
        limit: int,
        owner_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Execute FTS search"""
        if not query or not self.fts_search:
            return []
        
        try:
            return self.fts_search(query, limit)
        except Exception:
            return []
    
    def _search_vector(
        self,
        query: str,
        embedder_fn: Optional[Callable[[str], List[float]]],
        limit: int,
        owner_filter: Optional[List[str]] = None
    ) -> List[Tuple[str, float]]:
        """Execute vector search"""
        if not query or not self.vector_search or not embedder_fn:
            return []
        
        try:
            query_embedding = embedder_fn(query)
            return self.vector_search(query_embedding, limit)
        except Exception:
            return []
    
    def _search_pattern(
        self,
        terms: List[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Execute pattern search for short terms"""
        if not terms or not self.pattern_search:
            return []
        
        try:
            return self.pattern_search(terms, limit)
        except Exception:
            return []
    
    def _extract_pattern_terms(self, query: str) -> List[str]:
        """Extract 2-character terms for pattern search"""
        # Remove punctuation and split
        cleaned = query.replace(
            '."""(){}[]*:/^~!@#$%&\\/<>,;\'`?？。，！、：""''（）【】《》',
            ' '
        )
        words = cleaned.split()
        
        # Filter 2-character terms
        return [w for w in words if len(w) == 2]
    
    def _make_excerpt(self, content: str, max_len: int = 200) -> str:
        """Create excerpt from content"""
        if not content:
            return ''
        if len(content) <= max_len:
            return content
        return content[:max_len] + '...'


class SkillSearchEngine:
    """
    Hybrid search engine for skills.
    
    Combines FTS and vector search with RRF fusion.
    """
    
    def __init__(
        self,
        rrf_k: int = 60,
        skill_fts_search_fn: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
        skill_vector_search_fn: Optional[Callable[[str, List[float]], List[Tuple[str, float]]]] = None,
        get_skill_fn: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        get_skill_embedding_fn: Optional[Callable[[str], Optional[List[float]]]] = None
    ):
        self.rrf_k = rrf_k
        self.rrf_fuser = RRFFuser(k=rrf_k)
        
        self.fts_search = skill_fts_search_fn
        self.vector_search = skill_vector_search_fn
        self.get_skill = get_skill_fn or (lambda x: None)
        self.get_embedding = get_skill_embedding_fn or (lambda x: None)
    
    def search(
        self,
        query: str,
        scope: str = "mix",
        current_owner: str = "",
        top_k: int = 20,
        embedder_fn: Optional[Callable[[str], List[float]]] = None,
        judge_fn: Optional[Callable[[str, List[Dict[str, Any]]], List[int]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for skills.
        
        Args:
            query: Search query
            scope: Search scope ('mix', 'self', 'public')
            current_owner: Current user ID
            top_k: Number of results
            embedder_fn: Function to embed query
            judge_fn: Optional LLM judge function
        
        Returns:
            List of skill hits with scores
        """
        top_candidates = min(top_k * 2, 20)
        
        # FTS search
        fts_candidates = []
        if self.fts_search:
            try:
                fts_candidates = self.fts_search(query, top_candidates, scope, current_owner)
            except Exception:
                pass
        
        # Vector search
        vec_candidates = []
        if self.vector_search and embedder_fn:
            try:
                query_embedding = embedder_fn(query)
                vec_candidates = self.vector_search(query, query_embedding)
            except Exception:
                pass
        
        # RRF fusion
        fts_ranked = [{'id': c.get('skill_id', c.get('id')), 'score': c.get('score', 0)} for c in fts_candidates]
        vec_ranked = [{'id': c[0], 'score': c[1]} for c in vec_candidates]
        
        rrf_scores = rrf_fuse([fts_ranked, vec_ranked], k=self.rrf_k)
        
        if not rrf_scores:
            return []
        
        # Sort and limit
        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        # Build skill hits
        hits = []
        for skill_id, rrf_score in sorted_results:
            skill = self.get_skill(skill_id)
            if not skill:
                continue
            
            hits.append({
                'skill_id': skill['id'],
                'name': skill.get('name', ''),
                'description': skill.get('description', ''),
                'owner': skill.get('owner', ''),
                'visibility': skill.get('visibility', 'private'),
                'score': rrf_score,
                'reason': 'relevant'
            })
        
        return hits
