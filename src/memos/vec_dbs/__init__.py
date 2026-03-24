"""
Vector Database module for MemOS.

Provides support for multiple vector database backends including
Milvus, Qdrant, and pgvector.
"""

from memos.vec_dbs.base import BaseVecDB
from memos.vec_dbs.item import VecDBItem
from memos.vec_dbs.factory import VecDBFactory

# Backend implementations
from memos.vec_dbs.milvus import MilvusVecDB
from memos.vec_dbs.pgvector import PGVectorVecDB
from memos.vec_dbs.qdrant import QdrantVecDB

# PGVector adapter for hybrid search
from memos.vec_dbs.pgvector_adapter import (
    PGVectorSearchAdapter,
    IVFFlatIndex,
    VectorCache,
    cosine_similarity_pg,
    batch_search,
)

__all__ = [
    # Base classes
    "BaseVecDB",
    "VecDBItem",
    # Factory
    "VecDBFactory",
    # Backend implementations
    "MilvusVecDB",
    "PGVectorVecDB",
    "QdrantVecDB",
    # Adapters
    "PGVectorSearchAdapter",
    "IVFFlatIndex",
    "VectorCache",
    "cosine_similarity_pg",
    "batch_search",
]
