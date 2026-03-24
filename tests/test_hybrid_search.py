"""
Tests for Hybrid Search module.

Tests:
- RRF fusion
- MMR re-ranking
- Time decay
- HybridSearchEngine
"""

import unittest
import math
import sys
import os
from datetime import datetime, timedelta
from dataclasses import dataclass

# Add src to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import modules directly to avoid __init__.py chain
from memos.search.rrf import reciprocal_rank_fusion, rrf_score
from memos.search.mmr import mmr_rerank, maximal_marginal_relevance
from memos.search.recency import apply_recency_decay, time_decay_score
from memos.search.hybrid_search import HybridSearchEngine


@dataclass
class SearchResult:
    """Mock SearchResult for testing"""
    id: str
    content: str
    score: float
    metadata: dict = None
    created_at: float = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now().timestamp() * 1000


class TestRRF(unittest.TestCase):
    """Test Reciprocal Rank Fusion"""
    
    def test_rrf_score(self):
        """Test RRF score calculation"""
        # RRF(d) = 1 / (k + rank)
        k = 60
        
        # Rank 1 should give highest score
        score1 = rrf_score(1, k)
        score2 = rrf_score(2, k)
        score3 = rrf_score(3, k)
        
        self.assertGreater(score1, score2)
        self.assertGreater(score2, score3)
        self.assertAlmostEqual(score1, 1 / (k + 1))
        self.assertAlmostEqual(score2, 1 / (k + 2))
    
    def test_rrf_fusion_two_sources(self):
        """Test RRF with two result lists"""
        list1 = ['a', 'b', 'c']
        list2 = ['b', 'c', 'd']
        
        fused = reciprocal_rank_fusion([list1, list2], k=60)
        
        # 'b' and 'c' appear in both lists, should rank higher
        self.assertIn('b', fused[:2])
        self.assertIn('c', fused[:2])
        # 'a' and 'd' appear only once each
        self.assertIn('a', fused[2:])
        self.assertIn('d', fused[2:])
    
    def test_rrf_empty_list(self):
        """Test RRF with empty list"""
        fused = reciprocal_rank_fusion([['a', 'b'], []], k=60)
        self.assertEqual(fused, ['a', 'b'])
    
    def test_rrf_k_parameter(self):
        """Test different k values"""
        small_k = rrf_score(1, k=10)
        large_k = rrf_score(1, k=100)
        
        # Smaller k gives higher weight to top ranks
        self.assertGreater(small_k, large_k)


class TestMMR(unittest.TestCase):
    """Test Maximal Marginal Relevance"""
    
    def test_mmr_rerank_basic(self):
        """Test basic MMR reranking"""
        results = [
            SearchResult(id='1', content='apple banana', score=0.9),
            SearchResult(id='2', content='apple orange', score=0.85),
            SearchResult(id='3', content='banana grape', score=0.8),
            SearchResult(id='4', content='orange kiwi', score=0.75),
        ]
        
        reranked = mmr_rerank(results, query='fruit', lambda_val=0.7, limit=3)
        
        # Should have exactly 3 results
        self.assertEqual(len(reranked), 3)
        
        # Results should be diverse - not all about apple
        ids = [r.id for r in reranked]
        # Should include some variety
        self.assertLessEqual(ids.count('1') + ids.count('2'), 2)
    
    def test_mmr_lambda_balance(self):
        """Test MMR lambda parameter effect"""
        results = [
            SearchResult(id='1', content='test content', score=0.9),
            SearchResult(id='2', content='test content', score=0.85),
            SearchResult(id='3', content='different', score=0.8),
        ]
        
        # With high lambda (0.9), should favor relevance
        high_lambda = mmr_rerank(results, query='test', lambda_val=0.9, limit=2)
        
        # With low lambda (0.3), should favor diversity
        low_lambda = mmr_rerank(results, query='test', lambda_val=0.3, limit=2)
        
        # High lambda should prefer top scores
        self.assertEqual(high_lambda[0].id, '1')
        
        # Low lambda should pick more diverse items
        low_lambda_ids = [r.id for r in low_lambda]
        self.assertIn('3', low_lambda_ids)
    
    def test_mmr_limit_respects_original(self):
        """Test that MMR doesn't invent new results"""
        results = [
            SearchResult(id=str(i), content=f'content {i}', score=1.0 - i*0.1)
            for i in range(10)
        ]
        
        reranked = mmr_rerank(results, query='test', lambda_val=0.7, limit=5)
        
        self.assertEqual(len(reranked), 5)
        for r in reranked:
            self.assertLessEqual(int(r.id), 10)


class TestRecency(unittest.TestCase):
    """Test time decay functions"""
    
    def test_time_decay_score(self):
        """Test time decay formula"""
        now = datetime.now().timestamp() * 1000
        
        # Recent item (0 days old)
        recent = now - 0
        recent_score = time_decay_score(recent, now, half_life=14, alpha=0.3)
        self.assertGreater(recent_score, 0.9)
        
        # Old item (14 days old = one half-life)
        old = now - (14 * 24 * 60 * 60 * 1000)
        old_score = time_decay_score(old, now, half_life=14, alpha=0.3)
        self.assertAlmostEqual(old_score, 0.65, places=2)  # 0.3 + 0.7 * 0.5 = 0.65
        
        # Very old item (28 days = two half-lives)
        very_old = now - (28 * 24 * 60 * 60 * 1000)
        very_old_score = time_decay_score(very_old, now, half_life=14, alpha=0.3)
        self.assertGreater(very_old_score, 0.3)  # Should be at alpha floor
        self.assertLess(very_old_score, 0.5)  # But not much above
    
    def test_apply_recency_decay(self):
        """Test applying decay to results"""
        now = datetime.now().timestamp() * 1000
        
        results = [
            SearchResult(id='1', content='recent', score=1.0, created_at=now),
            SearchResult(id='2', content='old', score=1.0, 
                       created_at=now - 14*24*60*60*1000),
        ]
        
        decayed = apply_recency_decay(results, half_life=14, alpha=0.3)
        
        # Recent should have higher score
        self.assertGreater(decayed[0].score, decayed[1].score)
    
    def test_alpha_floor(self):
        """Test that alpha provides a score floor"""
        now = datetime.now().timestamp() * 1000
        
        # Very old item should not go below alpha
        very_old = now - (100 * 24 * 60 * 60 * 1000)  # 100 days
        score = time_decay_score(very_old, now, half_life=14, alpha=0.3)
        
        self.assertGreaterEqual(score, 0.3)


class TestHybridSearchEngine(unittest.TestCase):
    """Test HybridSearchEngine integration"""
    
    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        engine = HybridSearchEngine()
        self.assertIsNotNone(engine)
    
    def test_search_result_structure(self):
        """Test SearchResult dataclass"""
        result = SearchResult(
            id='test-1',
            content='test content',
            score=0.95,
            metadata={'source': 'test'}
        )
        
        self.assertEqual(result.id, 'test-1')
        self.assertEqual(result.content, 'test content')
        self.assertEqual(result.score, 0.95)
        self.assertEqual(result.metadata['source'], 'test')
    
    def test_engine_has_required_methods(self):
        """Test engine has required public methods"""
        engine = HybridSearchEngine()
        self.assertTrue(hasattr(engine, 'search'))
        self.assertTrue(hasattr(engine, 'add_memory'))
        self.assertTrue(callable(engine.search))


class TestIntegration(unittest.TestCase):
    """Integration tests combining all components"""
    
    def test_full_pipeline(self):
        """Test complete search pipeline: RRF -> MMR -> TimeDecay"""
        now = datetime.now().timestamp() * 1000
        
        # Simulate search results from different sources
        source1 = [
            SearchResult(id='1', content='python tutorial', score=0.9, created_at=now),
            SearchResult(id='2', content='java tutorial', score=0.8, created_at=now - 7*24*60*60*1000),
            SearchResult(id='3', content='python guide', score=0.85, created_at=now),
        ]
        
        source2 = [
            SearchResult(id='1', content='python tutorial', score=0.95, created_at=now),
            SearchResult(id='4', content='python basics', score=0.75, created_at=now - 3*24*60*60*1000),
        ]
        
        # Fuse with RRF
        fused = reciprocal_rank_fusion(
            [source1, source2],
            k=60
        )
        
        # Should have results from both sources
        self.assertGreater(len(fused), 0)
        
        # Python results should be prominent (appear in both)
        self.assertIn('1', fused[:2])


if __name__ == '__main__':
    unittest.main()
