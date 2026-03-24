"""
Time Decay Scoring Implementation

Applies exponential decay based on document age, biasing towards
more recent memories. Uses configurable half-life (default 14 days).

decay(t) = 0.5 ^ (age_days / half_life)
final_score = base_score * (alpha + (1-alpha) * decay)

alpha=0.3 ensures old but highly relevant results are not zeroed out.

Reference: Local Plugin src/recall/recency.ts
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import math


# Default half-life in days
DEFAULT_HALF_LIFE_DAYS = 14

# Alpha parameter - ensures old but relevant results aren't zeroed out
DEFAULT_ALPHA = 0.3


def calculate_decay(
    age_ms: float,
    half_life_ms: float
) -> float:
    """
    Calculate exponential decay factor.
    
    Args:
        age_ms: Age in milliseconds
        half_life_ms: Half-life in milliseconds
    
    Returns:
        Decay factor between 0 and 1
    """
    if age_ms <= 0:
        return 1.0
    
    return math.pow(0.5, age_ms / half_life_ms)


def apply_recency_decay(
    candidates: List[Dict[str, Any]],
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    alpha: float = DEFAULT_ALPHA,
    now_ms: Optional[float] = None,
    timestamp_field: str = 'created_at'
) -> List[Dict[str, Any]]:
    """
    Apply time decay to candidate scores.
    
    Args:
        candidates: List of candidates with 'id', 'score', and timestamp
        half_life_days: Days until score is halved (default 14)
        alpha: Weight for base score (0.3 means 30% base, 70% decay)
        now_ms: Current timestamp in ms (default: now)
        timestamp_field: Field name containing timestamp
    
    Returns:
        Candidates with adjusted scores
    
    Example:
        >>> candidates = [
        ...     {'id': 'doc1', 'score': 0.9, 'created_at': 1700000000000},
        ...     {'id': 'doc2', 'score': 0.8, 'created_at': 1710000000000}
        ... ]
        >>> decayed = apply_recency_decay(candidates, half_life_days=7)
    """
    if not candidates:
        return candidates
    
    current_time = now_ms if now_ms is not None else _get_current_time_ms()
    half_life_ms = half_life_days * 24 * 60 * 60 * 1000
    
    result = []
    for c in candidates:
        # Get timestamp from candidate
        ts = c.get(timestamp_field) or c.get('createdAt', 0)
        
        # Calculate age
        age_ms = max(0, current_time - ts)
        
        # Calculate decay factor
        decay = calculate_decay(age_ms, half_life_ms)
        
        # Apply decay: score * (alpha + (1-alpha) * decay)
        base_score = c.get('score', 0.0)
        adjusted_score = base_score * (alpha + (1 - alpha) * decay)
        
        result.append({
            'id': c['id'],
            'score': adjusted_score,
            'original_score': base_score,
            'decay': decay,
            'age_ms': age_ms,
            timestamp_field: ts
        })
    
    return result


def apply_recency_decay_simple(
    scores: Dict[str, float],
    timestamps: Dict[str, float],
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    now_ms: Optional[float] = None
) -> Dict[str, float]:
    """
    Apply time decay to a dictionary of scores.
    
    Simpler API when you have separate score and timestamp dicts.
    
    Args:
        scores: Dict of item_id -> score
        timestamps: Dict of item_id -> timestamp_ms
        half_life_days: Half-life in days
        now_ms: Current time in ms
    
    Returns:
        Dict of item_id -> adjusted score
    """
    current_time = now_ms if now_ms is not None else _get_current_time_ms()
    half_life_ms = half_life_days * 24 * 60 * 60 * 1000
    alpha = DEFAULT_ALPHA
    
    result = {}
    for item_id, base_score in scores.items():
        ts = timestamps.get(item_id, 0)
        age_ms = max(0, current_time - ts)
        decay = calculate_decay(age_ms, half_life_ms)
        result[item_id] = base_score * (alpha + (1 - alpha) * decay)
    
    return result


def _get_current_time_ms() -> float:
    """Get current time in milliseconds"""
    return datetime.now(timezone.utc).timestamp() * 1000


class RecencyScorer:
    """
    State-aware recency scorer with configurable parameters.
    """
    
    def __init__(
        self,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        alpha: float = DEFAULT_ALPHA,
        timestamp_field: str = 'created_at'
    ):
        self.half_life_days = half_life_days
        self.alpha = alpha
        self.timestamp_field = timestamp_field
        self.half_life_ms = half_life_days * 24 * 60 * 60 * 1000
    
    def decay(self, age_ms: float) -> float:
        """Calculate decay for a given age"""
        return calculate_decay(age_ms, self.half_life_ms)
    
    def score(self, candidate: Dict[str, Any]) -> float:
        """Apply recency decay to a single candidate"""
        ts = candidate.get(self.timestamp_field) or candidate.get('createdAt', 0)
        age_ms = max(0, _get_current_time_ms() - ts)
        decay = self.decay(age_ms)
        base_score = candidate.get('score', 0.0)
        return base_score * (self.alpha + (1 - self.alpha) * decay)
    
    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Apply recency decay and sort by adjusted score.
        
        Args:
            candidates: List of candidates
            top_k: Return only top K results
        
        Returns:
            Sorted list with adjusted scores
        """
        scored = [
            {**c, 'adjusted_score': self.score(c)}
            for c in candidates
        ]
        
        scored.sort(key=lambda x: x['adjusted_score'], reverse=True)
        
        if top_k:
            scored = scored[:top_k]
        
        return scored


class AdaptiveRecencyScorer(RecencyScorer):
    """
    Adaptive recency scorer that adjusts parameters based on query context.
    
    For short-term focused queries, uses shorter half-life.
    For long-term queries, uses longer half-life or no decay.
    """
    
    def __init__(
        self,
        short_term_half_life_days: float = 7,
        long_term_half_life_days: float = 30,
        neutral_half_life_days: float = 14,
        **kwargs
    ):
        super().__init__(half_life_days=neutral_half_life_days, **kwargs)
        self.short_term_half_life = short_term_half_life_days * 24 * 60 * 60 * 1000
        self.long_term_half_life = long_term_half_life_days * 24 * 60 * 60 * 1000
        self.neutral_half_life = self.half_life_ms
    
    def select_half_life(self, query: str) -> float:
        """
        Select appropriate half-life based on query keywords.
        
        Args:
            query: Search query string
        
        Returns:
            Half-life in milliseconds
        """
        query_lower = query.lower()
        
        # Short-term indicators
        short_terms = ['today', 'yesterday', 'recent', 'latest', 'new', 'just', 'recently']
        if any(term in query_lower for term in short_terms):
            return self.short_term_half_life
        
        # Long-term indicators
        long_terms = ['always', 'usually', 'history', 'past', 'old', 'remember', 'when i was']
        if any(term in query_lower for term in long_terms):
            return self.long_term_half_life
        
        return self.neutral_half_life
    
    def rerank_adaptive(
        self,
        candidates: List[Dict[str, Any]],
        query: str,
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank with adaptive half-life based on query.
        
        Args:
            candidates: List of candidates
            query: Search query (used to determine half-life)
            top_k: Number of results to return
        
        Returns:
            Re-ranked candidates
        """
        # Temporarily set half-life based on query
        original_half_life = self.half_life_ms
        self.half_life_ms = self.select_half_life(query)
        
        try:
            return self.rerank(candidates, top_k)
        finally:
            self.half_life_ms = original_half_life


class TimeWindowFilter:
    """
    Filter candidates by time window.
    """
    
    def __init__(
        self,
        window_days: Optional[float] = None,
        timestamp_field: str = 'created_at'
    ):
        self.window_days = window_days
        self.timestamp_field = timestamp_field
    
    def filter(
        self,
        candidates: List[Dict[str, Any]],
        now_ms: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter candidates within time window.
        
        Args:
            candidates: List of candidates
            now_ms: Current time (default: now)
        
        Returns:
            Filtered candidates within time window
        """
        if not self.window_days:
            return candidates
        
        current_time = now_ms if now_ms is not None else _get_current_time_ms()
        cutoff_ms = self.window_days * 24 * 60 * 60 * 1000
        
        return [
            c for c in candidates
            if (current_time - c.get(self.timestamp_field, 0)) <= cutoff_ms
        ]


def normalize_scores(
    candidates: List[Dict[str, Any]],
    score_field: str = 'score'
) -> List[Dict[str, Any]]:
    """
    Normalize scores to 0-1 range.
    
    Args:
        candidates: List of candidates with scores
        score_field: Field name containing score
    
    Returns:
        Candidates with normalized scores
    """
    if not candidates:
        return candidates
    
    max_score = max(c.get(score_field, 0) for c in candidates)
    if max_score == 0:
        return candidates
    
    result = []
    for c in candidates:
        normalized = c.get(score_field, 0) / max_score
        result.append({**c, f'{score_field}_normalized': normalized})
    
    return result
