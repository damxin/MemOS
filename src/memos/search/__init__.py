"""
Search module for MemOS.

Provides hybrid search combining FTS, vector search, RRF, MMR, and recency decay.
"""

# RRF (Reciprocal Rank Fusion)
from .rrf import (
    rrf_fuse,
    rrf_fuse_with_scores,
    rank_fused_scores,
    RRFFuser,
    RankedItem,
)

# MMR (Maximal Marginal Relevance)
from .mmr import (
    MMRReranker,
    mmr_rerank,
    cosine_similarity,
    euclidean_distance,
    DiversityCalculator,
)

# Recency (Time Decay)
from .recency import (
    apply_recency_decay,
    apply_recency_decay_simple,
    RecencyScorer,
    AdaptiveRecencyScorer,
    TimeWindowFilter,
    normalize_scores,
    calculate_decay,
)

# Hybrid Search Engine
from .hybrid_search import (
    HybridSearchEngine,
    SkillSearchEngine,
    SearchConfig,
    SearchCandidate,
    SearchHit,
    SearchResult,
    SearchSource,
)

# Legacy search service (still supported)
from .search_service import (
    SearchContext,
    build_search_context,
    search_text_memories,
)

__all__ = [
    # RRF
    "rrf_fuse",
    "rrf_fuse_with_scores",
    "rank_fused_scores",
    "RRFFuser",
    "RankedItem",
    # MMR
    "MMRReranker",
    "mmr_rerank",
    "cosine_similarity",
    "euclidean_distance",
    "DiversityCalculator",
    # Recency
    "apply_recency_decay",
    "apply_recency_decay_simple",
    "RecencyScorer",
    "AdaptiveRecencyScorer",
    "TimeWindowFilter",
    "normalize_scores",
    "calculate_decay",
    # Hybrid Search
    "HybridSearchEngine",
    "SkillSearchEngine",
    "SearchConfig",
    "SearchCandidate",
    "SearchHit",
    "SearchResult",
    "SearchSource",
    # Legacy
    "SearchContext",
    "build_search_context",
    "search_text_memories",
]
