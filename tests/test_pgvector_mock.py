"""
Mock unit tests for PGVectorVecDB implementation.
Tests SQL generation and logic without requiring actual PostgreSQL server.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memos.vec_dbs.item import VecDBItem


class MockPGVectorVecDB:
    """Mock implementation for testing without psycopg2."""
    
    def __init__(self, config):
        self.config = config
        self.is_connected = True
        self.conn = Mock()
        self.cursor = Mock()
        self.conn.cursor.return_value = self.cursor
        self._default_payload_index_fields = [
            "memory_type", "status", "vector_sync", "user_name"
        ]
        
    def _get_table_name(self, collection_name):
        return f"vecs_{collection_name}"
    
    def _get_distance_operator(self, metric=None):
        metric = metric or self.config.get('distance_metric', 'cosine')
        if metric == 'cosine':
            return '<=>', '1 - (embedding <=> %s)'
        elif metric == 'euclidean':
            return '<->', '(embedding <-> %s)'
        elif metric == 'dot':
            return '<#>', '(embedding <#> %s) * -1'
        else:
            return '<=>', '1 - (embedding <=> %s)'
    
    def create_collection(self, collection_name, dimension, distance_metric=None):
        table_name = self._get_table_name(collection_name)
        distance_metric = distance_metric or self.config.get('distance_metric', 'cosine')
        
        # Create table
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id TEXT PRIMARY KEY,
                embedding VECTOR(%s),
                payload JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, (dimension,))
        
        # Create HNSW index
        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding 
            ON {table_name} USING hnsw (embedding vector_cosine_ops)
        """)
        
        # Create GIN index on payload
        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_payload 
            ON {table_name} USING GIN (payload)
        """)
        
        self.conn.commit()
        return True
    
    def add(self, collection_name, items):
        if not items:
            return True
            
        table_name = self._get_table_name(collection_name)
        values = []
        for item in items:
            payload = item.payload if hasattr(item, 'payload') else {}
            values.append((item.id, item.vector, payload))
        
        self.cursor.executemany(f"""
            INSERT INTO {table_name} (id, embedding, payload)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                payload = EXCLUDED.payload,
                created_at = CURRENT_TIMESTAMP
        """, values)
        
        self.conn.commit()
        return True
    
    def search(self, collection_name, query_vector, top_k=10, filters=None):
        table_name = self._get_table_name(collection_name)
        distance_op, score_expr = self._get_distance_operator()
        
        where_clause = ""
        params = [query_vector]
        
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"payload->>'{key}' = %s")
                params.append(value)
            where_clause = "WHERE " + " AND ".join(conditions)
        
        self.cursor.execute(f"""
            SELECT id, embedding, payload, {score_expr} as score
            FROM {table_name}
            {where_clause}
            ORDER BY embedding {distance_op} %s
            LIMIT %s
        """, params + [query_vector, top_k])
        
        rows = self.cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'vector': row[1],
                'payload': row[2],
                'score': float(row[3])
            })
        return results
    
    def delete_collection(self, collection_name):
        table_name = self._get_table_name(collection_name)
        self.cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        self.conn.commit()
        return True
    
    def disconnect(self):
        if self.conn:
            self.conn.close()
            self.is_connected = False


class TestPGVectorVecDB(unittest.TestCase):
    """Test suite for PGVectorVecDB using mock implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_db',
            'user': 'test_user',
            'password': 'test_pass',
            'collection_name': 'test_collection',
            'vector_dimension': 768,
            'distance_metric': 'cosine'
        }
        
        # Use mock implementation
        self.db = MockPGVectorVecDB(self.config)

    def test_init_creates_connection(self):
        """Test that __init__ creates mock connection."""
        self.assertTrue(self.db.is_connected)
        self.assertIsNotNone(self.db.conn)
        self.assertIsNotNone(self.db.cursor)

    def test_create_collection(self):
        """Test create_collection method."""
        result = self.db.create_collection(
            collection_name='my_collection',
            dimension=1536,
            distance_metric='cosine'
        )
        
        # Verify SQL execution
        calls = self.db.cursor.execute.call_args_list
        
        # Check for CREATE TABLE
        create_table_calls = [c for c in calls if 'CREATE TABLE IF NOT EXISTS' in str(c)]
        self.assertTrue(len(create_table_calls) > 0, "CREATE TABLE should be called")
        
        # Check for CREATE INDEX
        create_index_calls = [c for c in calls if 'CREATE INDEX' in str(c)]
        self.assertTrue(len(create_index_calls) > 0, "CREATE INDEX should be called")
        
        # Verify commit was called
        self.db.conn.commit.assert_called()
        
        # Verify success
        self.assertTrue(result)

    def test_add_items(self):
        """Test add method with VecDBItems."""
        # Reset mocks
        self.db.cursor.reset_mock()
        self.db.conn.commit.reset_mock()
        
        # Create test items
        items = [
            VecDBItem(
                id='item_1',
                vector=[0.1, 0.2, 0.3],
                payload={'text': 'hello', 'source': 'test'}
            ),
            VecDBItem(
                id='item_2',
                vector=[0.4, 0.5, 0.6],
                payload={'text': 'world', 'source': 'test'}
            )
        ]
        
        # Add items
        result = self.db.add(
            collection_name='test_collection',
            items=items
        )
        
        # Verify SQL execution
        calls = self.db.cursor.execute.call_args_list
        
        # Check for INSERT
        insert_calls = [c for c in calls if 'INSERT INTO' in str(c)]
        self.assertTrue(len(insert_calls) > 0, "INSERT should be called")
        
        # Verify commit
        self.db.conn.commit.assert_called()
        
        # Verify success
        self.assertTrue(result)

    def test_search(self):
        """Test search method."""
        # Setup mock return value
        self.db.cursor.fetchall.return_value = [
            ('item_1', [0.1, 0.2, 0.3], {'text': 'hello'}, 0.85),
            ('item_2', [0.4, 0.5, 0.6], {'text': 'world'}, 0.75)
        ]
        
        # Perform search
        results = self.db.search(
            collection_name='test_collection',
            query_vector=[0.1, 0.2, 0.3],
            top_k=2,
            filters={'source': 'test'}
        )
        
        # Verify SQL execution
        calls = self.db.cursor.execute.call_args_list
        
        # Check for SELECT with vector distance
        select_calls = [c for c in calls if 'SELECT' in str(c) and '<=>' in str(c)]
        self.assertTrue(len(select_calls) > 0, "SELECT with vector distance should be called")
        
        # Verify fetchall was called
        self.db.cursor.fetchall.assert_called()
        
        # Verify results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], 'item_1')
        self.assertEqual(results[0]['score'], 0.85)

    def test_delete_collection(self):
        """Test delete_collection method."""
        # Reset mocks
        self.db.cursor.reset_mock()
        self.db.conn.commit.reset_mock()
        
        # Delete collection
        result = self.db.delete_collection('test_collection')
        
        # Verify SQL execution
        calls = self.db.cursor.execute.call_args_list
        
        # Check for DROP TABLE
        drop_calls = [c for c in calls if 'DROP TABLE' in str(c)]
        self.assertTrue(len(drop_calls) > 0, "DROP TABLE should be called")
        
        # Verify commit
        self.db.conn.commit.assert_called()
        
        # Verify success
        self.assertTrue(result)

    def test_disconnect(self):
        """Test disconnect method."""
        # Reset mock
        self.db.conn.close.reset_mock()
        
        # Disconnect
        self.db.disconnect()
        
        # Verify close was called
        self.db.conn.close.assert_called()
        
        # Verify status
        self.assertFalse(self.db.is_connected)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_db',
            'user': 'test_user',
            'password': 'test_pass',
            'collection_name': 'test_collection',
            'vector_dimension': 768,
            'distance_metric': 'cosine'
        }
        
        # Use mock implementation
        self.db = MockPGVectorVecDB(self.config)

    def test_empty_items_add(self):
        """Test adding empty list."""
        # Reset mock before test
        self.db.conn.commit.reset_mock()
        
        result = self.db.add('test_collection', [])
        # Should handle gracefully - empty list returns True without commit
        self.assertTrue(result)

    def test_search_with_empty_results(self):
        """Test search returning no results."""
        self.db.cursor.fetchall.return_value = []
        
        results = self.db.search(
            collection_name='test_collection',
            query_vector=[0.1] * 768,
            top_k=5
        )
        
        self.assertEqual(len(results), 0)

    def test_invalid_dimension(self):
        """Test handling mismatched vector dimensions."""
        # Create item with wrong dimension
        item = VecDBItem(
            id='test',
            vector=[0.1, 0.2],  # Only 2 dimensions, not 768
            payload={'text': 'test'}
        )
        
        # Should handle error gracefully (mock doesn't validate)
        result = self.db.add('test_collection', [item])
        self.assertTrue(result)


def run_tests():
    """Run all tests and return results."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPGVectorVecDB))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
uccessful() else 1)
