"""
Reciprocal Rank Fusion (RRF) Implementation

Merges ranked lists from different retrieval sources (FTS, vector)
into a single ranking. Handles score scale mismatch between BM25
and cosine similarity.

RRF(d) = Σ 1 / (k + rank_i(d))
where k is a constant (default 60) and rank_i is the rank in list i.

Reference: Local Plugin src/recall/rrf.ts
"""

from typing import List, Dict, Any
from collections import defaultdict


class RankedItem:
    """Represents an item with its rank and score"""
    
    def __init__(self, item_id: str, score: float, rank: int = 0):
        self.id = item_id
        self.score = score
        self.rank = rank
    
    def __repr__(self):
        return f"RankedItem(id={self.id}, score={self.score}, rank={self.rank})"


def rrf_fuse(
    lists: List[List[Dict[str, Any]]],
    k: int = 60
) -> Dict[str, float]:
    """
    Fuses multiple ranked lists using Reciprocal Rank Fusion.
    
    Args:
        lists: List of ranked lists, each item is a dict with 'id' and 'score' keys
        k: Constant for RRF formula (default 60). Higher values reduce 
           the impact of ranks (make all sources more equal)
    
    Returns:
        Dict mapping item_id to fused RRF score
    
    Example:
        >>> fts_list = [{'id': 'doc1', 'score': 0.9}, {'id': 'doc2', 'score': 0.8}]
        >>> vec_list = [{'id': 'doc2', 'score': 0.95}, {'id': 'doc3', 'score': 0.85}]
        >>> scores = rrf_fuse([fts_list, vec_list], k=60)
        >>> # doc2 appears in both lists, will have highest score
    """
    scores: Dict[str, float] = defaultdict(float)
    
    for ranked_list in lists:
        for rank, item in enumerate(ranked_list):
            item_id = item.get('id') if isinstance(item, dict) else item.id if hasattr(item, 'id') else str(item)
            # RRF formula: 1 / (k + rank + 1)
            # rank is 0-indexed, so we add 1 for 1-indexed
            rrf_score = 1.0 / (k + rank + 1)
            scores[item_id] += rrf_score
    
    return dict(scores)


def rrf_fuse_with_scores(
    lists: List[List[Dict[str, Any]]],
    k: int = 60,
    use_score_weighting: bool = False
) -> Dict[str, float]:
    """
    Advanced RRF fusion with optional score weighting.
    
    Args:
        lists: List of ranked lists
        k: RRF constant
        use_score_weighting: If True, multiply RRF score by original score
    
    Returns:
        Dict mapping item_id to fused score
    """
    scores: Dict[str, float] = defaultdict(float)
    max_scores: Dict[str, float] = defaultdict(float)
    
    for ranked_list in lists:
        for rank, item in enumerate(ranked_list):
            if isinstance(item, dict):
                item_id = item.get('id')
                original_score = item.get('score', 1.0)
            else:
                item_id = item.id
                original_score = getattr(item, 'score', 1.0)
            
            rrf_score = 1.0 / (k + rank + 1)
            
            if use_score_weighting:
                rrf_score *= original_score
            
            scores[item_id] += rrf_score
            max_scores[item_id] = max(max_scores[item_id], original_score)
    
    return dict(scores)


def rank_fused_scores(
    fused_scores: Dict[str, float],
    top_k: int = None
) -> List[Dict[str, Any]]:
    """
    Convert fused scores to a ranked list.
    
    Args:
        fused_scores: Dict of item_id -> fused score
        top_k: Return only top K results (None for all)
    
    Returns:
        List of dicts with 'id', 'score', and 'rank' keys
    """
    sorted_items = sorted(
        fused_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    if top_k:
        sorted_items = sorted_items[:top_k]
    
    result = []
    for rank, (item_id, score) in enumerate(sorted_items):
        result.append({
            'id': item_id,
            'score': score,
            'rank': rank + 1
        })
    
    return result


class RRFFuser:
    """
    State-aware RRF fuser for multiple queries.
    Tracks recent queries to detect repeats.
    """
    
    def __init__(self, k: int = 60, max_recent_queries: int = 20):
        self.k = k
        self.max_recent_queries = max_recent_queries
        self.recent_queries: List[Dict[str, Any]] = []
    
    def fuse(
        self,
        lists: List[List[Dict[str, Any]]],
        query: str = None,
        max_results: int = None,
        min_score: float = None
    ) -> List[Dict[str, Any]]:
        """
        Fuse ranked lists and track query history.
        
        Returns:
            List of fused results with id, score, rank
        """
        fused = rrf_fuse(lists, self.k)
        ranked = rank_fused_scores(fused)
        
        if query:
            self._record_query(query, max_results, min_score, len(ranked))
        
        return ranked
    
    def check_repeat(
        self,
        query: str,
        max_results: int = None,
        min_score: float = None
    ) -> str:
        """
        Check if this exact query was already executed.
        
        Returns:
            Warning message if repeated, None otherwise
        """
        normalized = query.lower().strip()
        if not normalized:
            return None
        
        for recent in self.recent_queries:
            if (recent['query'] == normalized and 
                recent['max_results'] == max_results and 
                recent['min_score'] == min_score):
                
                if recent['hit_count'] == 0:
                    return (
                        "This exact query with the same parameters was already tried "
                        "and returned 0 results. Try rephrasing with different keywords, "
                        "or adjust max_results/min_score."
                    )
                else:
                    return (
                        "This exact query with the same parameters was already executed. "
                        "Consider varying the query or expanding parameters."
                    )
        
        return None
    
    def _record_query(
        self,
        query: str,
        max_results: int,
        min_score: float,
        hit_count: int
    ):
        """Record a query for repeat detection"""
        normalized = query.lower().strip()
        if not normalized:
            return
        
        # Remove duplicates
        self.recent_queries = [
            q for q in self.recent_queries
            if not (q['query'] == normalized and 
                   q['max_results'] == max_results and 
                   q['min_score'] == min_score)
        ]
        
        # Add new query
        self.recent_queries.append({
            'query': normalized,
            'max_results': max_results,
            'min_score': min_score,
            'hit_count': hit_count
        })
        
        # Trim to max size
        if len(self.recent_queries) > self.max_recent_queries:
            self.recent_queries = self.recent_queries[-self.max_recent_queries:]
