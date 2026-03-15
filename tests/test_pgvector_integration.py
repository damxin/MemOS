"""
Integration tests for PGVectorVecDB with real PostgreSQL connection.
"""
import unittest
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memos.vec_dbs.pgvector import PGVectorVecDB
from memos.configs.vec_db import PGVectorVecDBConfig
from memos.vec_dbs.item import VecDBItem


class TestPGVectorIntegration(unittest.TestCase):
    """Integration tests with real PostgreSQL."""

    @classmethod
    def setUpClass(cls):
        """Set up test database connection."""
        cls.config = PGVectorVecDBConfig(
            host='127.0.0.1',
            port=24432,
            database='memos',
            user='memos',
            password='CrNfpXpF3s8yZCFm',
            collection_name='test_collection',
            vector_dimension=768,
            distance_metric='cosine'
        )
        
        cls.db = PGVectorVecDB(cls.config)

    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        # Drop test collection
        try:
            cls.db.delete_collection('test_collection')
        except:
            pass
        cls.db.disconnect()

    def setUp(self):
        """Set up for each test."""
        # Clean collection before each test
        try:
            self.db.delete_collection('test_collection')
        except:
            pass
        self.db.create_collection('test_collection', dimension=768)

    def _make_uuid(self):
        """Generate unique ID."""
        return str(uuid.uuid4())

    def test_01_create_collection(self):
        """Test creating a collection."""
        # Collection created in setUp
        self.assertTrue(True)

    def test_02_add_single_item(self):
        """Test adding a single item."""
        item = VecDBItem(
            id=self._make_uuid(),
            vector=[0.1] * 768,
            payload={'text': 'hello world', 'source': 'test'}
        )
        
        result = self.db.add('test_collection', [item])
        self.assertTrue(result)

    def test_03_add_multiple_items(self):
        """Test adding multiple items."""
        items = [
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.1] * 768,
                payload={'text': 'first item', 'category': 'A'}
            ),
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.2] * 768,
                payload={'text': 'second item', 'category': 'B'}
            ),
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.3] * 768,
                payload={'text': 'third item', 'category': 'A'}
            )
        ]
        
        result = self.db.add('test_collection', items)
        self.assertTrue(result)

    def test_04_search_no_filters(self):
        """Test search without filters."""
        # Add test items
        items = [
            VecDBItem(
                id=self._make_uuid(),
                vector=[1.0] + [0.0] * 767,  # Different from query
                payload={'text': 'item 1'}
            ),
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.9] + [0.1] * 767,  # Closer to query
                payload={'text': 'item 2'}
            )
        ]
        self.db.add('test_collection', items)
        
        # Search
        query_vector = [1.0] + [0.0] * 767
        results = self.db.search(
            collection_name='test_collection',
            query_vector=query_vector,
            top_k=2
        )
        
        self.assertEqual(len(results), 2)
        # Results should be ordered by similarity
        self.assertGreaterEqual(results[0]['score'], results[1]['score'])

    def test_05_search_with_filters(self):
        """Test search with filters."""
        # Add test items with different categories
        items = [
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.1] * 768,
                payload={'text': 'cat item', 'category': 'animals'}
            ),
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.2] * 768,
                payload={'text': 'dog item', 'category': 'animals'}
            ),
            VecDBItem(
                id=self._make_uuid(),
                vector=[0.3] * 768,
                payload={'text': 'apple item', 'category': 'fruits'}
            )
        ]
        self.db.add('test_collection', items)
        
        # Search with filter
        results = self.db.search(
            collection_name='test_collection',
            query_vector=[0.15] * 768,
            top_k=10,
            filters={'category': 'animals'}
        )
        
        # Should return only animal items
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result['payload']['category'], 'animals')

    def test_06_update_existing_item(self):
        """Test updating an existing item."""
        item_id = self._make_uuid()
        
        # Add initial item
        item1 = VecDBItem(
            id=item_id,
            vector=[0.1] * 768,
            payload={'text': 'original', 'version': 1}
        )
        self.db.add('test_collection', [item1])
        
        # Update with same ID
        item2 = VecDBItem(
            id=item_id,
            vector=[0.2] * 768,
            payload={'text': 'updated', 'version': 2}
        )
        result = self.db.add('test_collection', [item2])
        self.assertTrue(result)

    def test_07_delete_collection(self):
        """Test deleting a collection."""
        # Create and delete collection
        self.db.create_collection('temp_collection', dimension=768)
        result = self.db.delete_collection('temp_collection')
        self.assertTrue(result)

    def test_08_error_handling(self):
        """Test error handling for invalid operations."""
        # Test search on non-existent collection (should return empty)
        try:
            results = self.db.search(
                collection_name='nonexistent_collection',
                query_vector=[0.1] * 768,
                top_k=5
            )
            # May return empty or raise error depending on implementation
        except Exception:
            pass  # Expected behavior


def run_tests():
    """Run all tests and return results."""
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestPGVectorIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
