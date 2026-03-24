"""
PGVector Adapter for HybridSearchEngine

Provides integration between PGVectorVecDB and the hybrid search module.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
import math

from .base import BaseVecDB
from .pgvector import PGVectorVecDB
from .item import VecDBItem


class PGVectorSearchAdapter:
    """
    Adapter to integrate PGVectorVecDB with HybridSearchEngine.
    
    Wraps PGVector's vector search and provides callbacks for
    the hybrid search pipeline.
    """
    
    def __init__(
        self,
        pgvector_db: PGVectorVecDB,
        embedding_field: str = "embedding",
        timestamp_field: str = "created_at"
    ):
        """
        Args:
            pgvector_db: PGVectorVecDB instance
            embedding_field: Field name in payload containing embedding
            timestamp_field: Field name in payload containing timestamp
        """
        self.db = pgvector_db
        self.embedding_field = embedding_field
        self.timestamp_field = timestamp_field
    
    def vector_search(
        self,
        query_embedding: List[float],
        top_k: int,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float]]:
        """
        Execute vector search and return results.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results
            filter_dict: Optional filter criteria
        
        Returns:
            List of (id, score) tuples
        """
        results = self.db.search(query_embedding, top_k, filter_dict)
        return [(r.id, r.score) for r in results]
    
    def get_embedding(self, item_id: str) -> Optional[List[float]]:
        """
        Get embedding for an item.
        
        Args:
            item_id: Item ID
        
        Returns:
            Embedding vector or None
        """
        item = self.db.get_by_id(item_id)
        if not item or not item.payload:
            return None
        
        embedding_data = item.payload.get(self.embedding_field)
        if isinstance(embedding_data, list):
            return embedding_data
        return None
    
    def get_timestamp(self, item_id: str) -> float:
        """
        Get timestamp for an item.
        
        Args:
            item_id: Item ID
        
        Returns:
            Timestamp in milliseconds
        """
        item = self.db.get_by_id(item_id)
        if not item:
            return 0
        
        # Check payload first
        if item.payload:
            ts = item.payload.get(self.timestamp_field)
            if ts:
                # Assume epoch seconds if larger than year 3000 in ms
                if isinstance(ts, (int, float)):
                    if ts > 32503680000000:  # year 3000 in ms
                        return ts / 1000  # convert to ms
                    return ts * 1000  # assume epoch seconds
                return 0
        
        # Fall back to updated_at
        if hasattr(item, 'updated_at') and item.updated_at:
            return item.updated_at.timestamp() * 1000
        
        return 0
    
    def get_chunk(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full chunk data for an item.
        
        Args:
            item_id: Item ID
        
        Returns:
            Dict with id, content, summary, role, etc.
        """
        item = self.db.get_by_id(item_id)
        if not item:
            return None
        
        # Extract common fields from payload
        payload = item.payload or {}
        
        return {
            'id': item.id,
            'content': payload.get('content', ''),
            'summary': payload.get('summary'),
            'role': payload.get('role'),
            'session_key': payload.get('session_key'),
            'turn_id': payload.get('turn_id'),
            'seq': payload.get('seq', 0),
            'task_id': payload.get('task_id'),
            'skill_id': payload.get('skill_id'),
            'owner': payload.get('owner'),
            'embedding': payload.get(self.embedding_field),
            'created_at': self.get_timestamp(item_id)
        }


class IVFFlatIndex:
    """
    IVFFlat (Inverted File Index) index for pgvector.
    
    Alternative to HNSW for large datasets with faster build times.
    Note: PGVectorVecDB uses HNSW by default, but this can be used
    for custom table creation with IVFFlat.
    """
    
    def __init__(
        self,
        conn,
        table_name: str,
        vector_dimension: int,
        distance_metric: str = "cosine",
        lists: int = 100
    ):
        """
        Args:
            conn: PostgreSQL connection
            table_name: Table name
            vector_dimension: Dimension of vectors
            distance_metric: 'cosine', 'euclidean', or 'dot'
            lists: Number of lists for IVFFlat (higher = more accurate but slower)
        """
        self.conn = conn
        self.table_name = table_name
        self.vector_dimension = vector_dimension
        self.distance_metric = distance_metric
        self.lists = lists
    
    def _get_ops(self) -> str:
        """Get operator class for distance metric"""
        ops_map = {
            "cosine": "vector_cosine_ops",
            "euclidean": "vector_l2_ops",
            "dot": "vector_ip_ops",
        }
        return ops_map.get(self.distance_metric, "vector_cosine_ops")
    
    def _get_distance_op(self) -> str:
        """Get distance operator"""
        op_map = {
            "cosine": "<=>",
            "euclidean": "<->",
            "dot": "<#>",
        }
        return op_map.get(self.distance_metric, "<=>")
    
    def create_ivfflat_index(self) -> None:
        """Create IVFFlat index on the vector column."""
        ops = self._get_ops()
        
        with self.conn.cursor() as cur:
            # First create the index with lists parameter
            cur.execute(f"""
                CREATE INDEX idx_{self.table_name}_ivfflat
                ON {self.table_name}
                USING ivfflat (vector {ops})
                WITH (lists = {self.lists});
            """)
            self.conn.commit()
    
    def rebuild_with_probes(self, probes: int = 1) -> None:
        """
        Set probe count for query planning.
        
        Args:
            probes: Number of lists to probe (higher = more accurate but slower)
        """
        with self.conn.cursor() as cur:
            cur.execute(f"SET ivfflat.probes = {probes};")
            self.conn.commit()


def cosine_similarity_pg(a: List[float], b: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
    
    Returns:
        Cosine similarity score (-1 to 1)
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimensions must match: {len(a)} vs {len(b)}")
    
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def batch_search(
    db: PGVectorVecDB,
    query_embeddings: List[List[float]],
    top_k: int,
    filter_dict: Optional[Dict[str, Any]] = None
) -> List[List[VecDBItem]]:
    """
    Execute batch vector search.
    
    Args:
        db: PGVectorVecDB instance
        query_embeddings: List of query vectors
        top_k: Results per query
        filter_dict: Optional filter
    
    Returns:
        List of result lists, one per query
    """
    results = []
    for embedding in query_embeddings:
        search_results = db.search(embedding, top_k, filter_dict)
        results.append(search_results)
    return results


class VectorCache:
    """
    Simple LRU cache for vector embeddings.
    
    Reduces repeated database lookups for embeddings.
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: Dict[str, Tuple[List[float], int]] = {}
        self._access_order: List[str] = []
    
    def get(self, key: str) -> Optional[List[float]]:
        """Get embedding from cache"""
        if key in self._cache:
            # Update access order
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key][0]
        return None
    
    def set(self, key: str, embedding: List[float]) -> None:
        """Add embedding to cache"""
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self.max_size:
            # Evict least recently used
            lru_key = self._access_order.pop(0)
            del self._cache[lru_key]
        
        self._cache[key] = (embedding, len(self._access_order))
        self._access_order.append(key)
    
    def clear(self) -> None:
        """Clear the cache"""
        self._cache.clear()
        self._access_order.clear()
    
    def size(self) -> int:
        """Get current cache size"""
        return len(self._cache)
