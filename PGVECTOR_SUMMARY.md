# PGVector Implementation Summary

## Overview
PostgreSQL + pgvector vector storage backend implementation for MemOS, following the Qdrant/Milvus pattern.

## Implementation Files

### Core Implementation
- **src/memos/vec_dbs/pgvector.py** (20KB)
  - `PGVectorVecDB` class implementing `BaseVecDB`
  - Full CRUD operations
  - Vector similarity search with pgvector operators
  - HNSW index support
  - Collection management

### Configuration
- **src/memos/configs/vec_db.py**
  - Added `PGVectorVecDBConfig` class
  - Connection parameters (host, port, database, user, password)
  - Collection settings (name, dimension, distance_metric)

### Factory Registration
- **src/memos/vec_dbs/factory.py**
  - Registered `pgvector` backend in `VecDBFactory`
  - Maps `backend_type='pgvector'` to `PGVectorVecDB` class

### Dependencies
- **pyproject.toml**
  - Added `psycopg2-binary` for PostgreSQL connectivity
  - Added `pgvector` for Python bindings

## Key Features

### Vector Operations
- **Distance Metrics**: cosine (`<=>`), euclidean (`<->`), dot product (`<#>`)
- **Vector Type**: `VECTOR(n)` for embedding storage
- **Similarity Scoring**: Normalized similarity scores from distance metrics

### Data Storage
- **Embeddings**: `VECTOR(dimension)` column type
- **Metadata**: `JSONB` payload column for flexible metadata
- **Timestamps**: Automatic `created_at` tracking

### Indexing
- **HNSW Index**: `USING hnsw (embedding vector_cosine_ops)` for fast ANN search
- **GIN Index**: `USING GIN (payload)` for JSONB filtering
- **Payload Indexes**: Automatic indexing of common metadata fields

### Operations
- **Create Collection**: Creates table with VECTOR column, HNSW and GIN indexes
- **Add Items**: INSERT with ON CONFLICT upsert support
- **Search**: Vector similarity search with optional metadata filters
- **Delete Collection**: DROP TABLE cleanup

## SQL Examples

### Create Collection
```sql
CREATE TABLE IF NOT EXISTS vecs_mycollection (
    id TEXT PRIMARY KEY,
    embedding VECTOR(768),
    payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vecs_mycollection_embedding 
ON vecs_mycollection USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_vecs_mycollection_payload 
ON vecs_mycollection USING GIN (payload);
```

### Insert with Upsert
```sql
INSERT INTO vecs_mycollection (id, embedding, payload)
VALUES (%s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    payload = EXCLUDED.payload,
    created_at = CURRENT_TIMESTAMP;
```

### Vector Search
```sql
SELECT id, embedding, payload, 1 - (embedding <=> %s) as score
FROM vecs_mycollection
ORDER BY embedding <=> %s
LIMIT %s;
```

### Search with Filter
```sql
SELECT id, embedding, payload, 1 - (embedding <=> %s) as score
FROM vecs_mycollection
WHERE payload->>'category' = %s
ORDER BY embedding <=> %s
LIMIT %s;
```

## Test Status

### Mock Tests
- ✅ SQL generation tests (6/6 passed)
- ✅ Distance operator tests
- ✅ Index syntax tests

### Integration Tests (requires PostgreSQL)
- ⏳ Connection test
- ⏳ Collection lifecycle test
- ⏳ Add and search test

## Configuration Example

```python
from memos.configs.vec_db import PGVectorVecDBConfig

config = PGVectorVecDBConfig(
    host='127.0.0.1',
    port=24432,
    database='memos',
    user='memos',
    password='CrNfpXpF3s8yZCFm',
    collection_name='my_collection',
    vector_dimension=768,
    distance_metric='cosine'
)
```

## Dependencies

```toml
[project.optional-dependencies]
pgvector = [
    "psycopg2-binary>=2.9.9",
    "pgvector>=0.2.5",
]
```

## Notes

- Requires PostgreSQL 12+ with pgvector extension
- HNSW index requires pgvector 0.5.0+
- GIN index for JSONB requires PostgreSQL 9.4+
- VECTOR type supports up to 16000 dimensions

---

**Implementation Date**: 2026-03-15  
**Status**: ✅ Complete (Mock tests passing)  
**Next Steps**: Integration tests with live PostgreSQL
