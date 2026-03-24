"""
Maximal Marginal Relevance (MMR) Re-ranking Implementation

Re-ranks candidates to balance relevance with diversity,
preventing top-K results from being too similar.

MMR = λ · sim(q, d) - (1-λ) · max(sim(d, d_selected))

Reference: Local Plugin src/recall/mmr.ts
"""

from typing import List, Dict, Any, Callable, Optional, Tuple
import math


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        vec_a: First vector
        vec_b: Second vector
    
    Returns:
        Cosine similarity score (0-1)
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimensions mismatch: {len(vec_a)} vs {len(vec_b)}")
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def euclidean_distance(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute Euclidean distance between two vectors"""
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimensions mismatch")
    
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


class MMRReranker:
    """
    Maximal Marginal Relevance re-ranker.
    
    Balances relevance (similarity to query) with diversity 
    (dissimilarity to selected items).
    """
    
    def __init__(
        self,
        lambda_param: float = 0.7,
        similarity_fn: Callable[[List[float], List[float]], float] = None
    ):
        """
        Args:
            lambda_param: Weight for relevance vs diversity (0-1)
                         Higher = more relevance, Lower = more diversity
            similarity_fn: Custom similarity function (default: cosine)
        """
        self.lambda_param = lambda_param
        self.similarity_fn = similarity_fn or cosine_similarity
    
    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        get_embedding: Callable[[str], Optional[List[float]]],
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Re-rank candidates using MMR algorithm.
        
        Args:
            candidates: List of dicts with 'id' and 'score' keys
            get_embedding: Function to get embedding for an item id
            top_k: Number of results to return
        
        Returns:
            Re-ranked list of candidates
        """
        if len(candidates) <= 1:
            return candidates
        
        # Pre-fetch all embeddings
        embeddings: Dict[str, List[float]] = {}
        for c in candidates:
            emb = get_embedding(c['id'])
            if emb is not None:
                embeddings[c['id']] = emb
        
        selected: List[Dict[str, Any]] = []
        remaining = list(candidates)
        
        while len(selected) < top_k and remaining:
            best_idx = 0
            best_mmr = float('-inf')
            
            for i, cand in enumerate(remaining):
                cand_id = cand['id']
                cand_score = cand.get('score', 0.0)
                cand_emb = embeddings.get(cand_id)
                
                # Calculate max similarity to selected items
                max_sim_to_selected = 0.0
                if cand_emb and selected:
                    for sel in selected:
                        sel_emb = embeddings.get(sel['id'])
                        if sel_emb:
                            sim = self.similarity_fn(cand_emb, sel_emb)
                            max_sim_to_selected = max(max_sim_to_selected, sim)
                
                # MMR formula: λ * relevance - (1 - λ) * max_diversity
                mmr_score = (
                    self.lambda_param * cand_score -
                    (1 - self.lambda_param) * max_sim_to_selected
                )
                
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = i
            
            # Move best candidate from remaining to selected
            chosen = remaining.pop(best_idx)
            # Preserve original relevance score, not MMR score
            selected.append({
                'id': chosen['id'],
                'score': chosen.get('score', 0.0),
                'mmr_score': best_mmr
            })
        
        return selected


def mmr_rerank(
    candidates: List[Dict[str, Any]],
    get_embedding: Callable[[str], Optional[List[float]]],
    lambda_param: float = 0.7,
    top_k: int = 20
) -> List[Dict[str, Any]]:
    """
    Convenience function for MMR re-ranking.
    
    Args:
        candidates: List of candidates with 'id' and 'score'
        get_embedding: Function(item_id) -> embedding or None
        lambda_param: Relevance vs diversity weight
        top_k: Number of results
    
    Returns:
        Re-ranked candidates
    """
    reranker = MMRReranker(lambda_param=lambda_param)
    return reranker.rerank(candidates, get_embedding, top_k)


class DiversityCalculator:
    """
    Calculate diversity metrics for a set of selected items.
    """
    
    def __init__(
        self,
        similarity_fn: Callable[[List[float], List[float]], float] = None
    ):
        self.similarity_fn = similarity_fn or cosine_similarity
    
    def avg_pairwise_similarity(
        self,
        embeddings: Dict[str, List[float]]
    ) -> float:
        """
        Calculate average pairwise similarity among embeddings.
        
        Returns:
            Average cosine similarity (0-1, higher = less diverse)
        """
        items = list(embeddings.items())
        if len(items) <= 1:
            return 0.0
        
        total_sim = 0.0
        count = 0
        
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                sim = self.similarity_fn(items[i][1], items[j][1])
                total_sim += sim
                count += 1
        
        return total_sim / count if count > 0 else 0.0
    
    def min_distance_to_set(
        self,
        target_emb: List[float],
        selected_embs: List[List[float]]
    ) -> float:
        """
        Calculate minimum distance from target to any item in selected set.
        
        Returns:
            Minimum Euclidean distance (lower = closer)
        """
        if not selected_embs:
            return float('inf')
        
        min_dist = float('inf')
        for sel_emb in selected_embs:
            dist = euclidean_distance(target_emb, sel_emb)
            min_dist = min(min_dist, dist)
        
        return min_dist
    
    def max_similarity_to_set(
        self,
        target_emb: List[float],
        selected_embs: List[List[float]]
    ) -> float:
        """
        Calculate maximum similarity from target to any item in selected set.
        
        Returns:
            Maximum cosine similarity (higher = more similar)
        """
        if not selected_embs:
            return 0.0
        
        max_sim = 0.0
        for sel_emb in selected_embs:
            sim = self.similarity_fn(target_emb, sel_emb)
            max_sim = max(max_sim, sim)
        
        return max_sim


class MMRScorer:
    """
    Flexible MMR scoring with configurable parameters.
    """
    
    def __init__(
        self,
        lambda_param: float = 0.7,
        similarity_fn: Callable[[List[float], List[float]], float] = None,
        distance_fn: Callable[[List[float], List[float]], float] = None,
        use_cosine: bool = True
    ):
        self.lambda_param = lambda_param
        self.similarity_fn = similarity_fn or cosine_similarity
        self.distance_fn = distance_fn or euclidean_distance
        self.use_cosine = use_cosine
    
    def calculate_mmr(
        self,
        relevance_score: float,
        max_similarity_to_selected: float
    ) -> float:
        """Calculate MMR score given relevance and diversity components"""
        if self.use_cosine:
            # For cosine similarity (higher = more similar)
            diversity_score = max_similarity_to_selected
        else:
            # For distance metrics (lower = more similar)
            diversity_score = max_similarity_to_selected
        
        return (
            self.lambda_param * relevance_score -
            (1 - self.lambda_param) * diversity_score
        )
    
    def rerank_with_scores(
        self,
        candidates: List[Dict[str, Any]],
        embeddings: Dict[str, List[float]],
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """Re-rank with detailed MMR score breakdown"""
        selected = []
        remaining = list(candidates)
        
        while len(selected) < top_k and remaining:
            best_idx = 0
            best_mmr = float('-inf')
            
            for i, cand in enumerate(remaining):
                cand_id = cand['id']
                relevance = cand.get('score', 0.0)
                cand_emb = embeddings.get(cand_id)
                
                if cand_emb and selected:
                    # Get all selected embeddings
                    selected_embs = [
                        embeddings[s['id']]
                        for s in selected
                        if s['id'] in embeddings
                    ]
                    
                    if self.use_cosine:
                        max_sim = self.similarity_fn(cand_emb, selected_embs[0])
                        for sel_emb in selected_embs[1:]:
                            max_sim = max(max_sim, self.similarity_fn(cand_emb, sel_emb))
                    else:
                        max_sim = min(
                            self.distance_fn(cand_emb, sel_emb)
                            for sel_emb in selected_embs
                        )
                else:
                    max_sim = 0.0
                
                mmr = self.calculate_mmr(relevance, max_sim)
                
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i
            
            chosen = remaining.pop(best_idx)
            selected.append({
                'id': chosen['id'],
                'score': chosen.get('score', 0.0),
                'mmr_score': best_mmr
            })
        
        return selected
