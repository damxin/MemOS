"""
Core integration tests for PGVectorVecDB with real PostgreSQL.
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memos.vec_dbs.pgvector import PGVectorVecDB
from memos.configs.vec_db import PGVectorVecDBConfig
from memos.vec_dbs.item import VecDBItem


def make_uuid():
    """Generate unique ID."""
    return str(uuid.uuid4())


def test_connection():
    """Test basic connection."""
    print("\n=== Test 1: Connection ===")
    config = PGVectorVecDBConfig(
        host='127.0.0.1',
        port=24432,
        database='memos',
        user='memos',
        password='CrNfpXpF3s8yZCFm',
        collection_name='test',
        vector_dimension=768,
        distance_metric='cosine'
    )
    
    db = PGVectorVecDB(config)
    print(f"✅ Connected: {db.is_connected}")
    db.disconnect()
    print("✅ Disconnected successfully")
    return True


def test_collection_lifecycle():
    """Test collection create and delete."""
    print("\n=== Test 2: Collection Lifecycle ===")
    config = PGVectorVecDBConfig(
        host='127.0.0.1',
        port=24432,
        database='memos',
        user='memos',
        password='CrNfpXpF3s8yZCFm',
        collection_name='lifecycle_test',
        vector_dimension=768,
        distance_metric='cosine'
    )
    
    db = PGVectorVecDB(config)
    
    # Create collection
    db.create_collection('lifecycle_test', dimension=768)
    print("✅ Collection created")
    
    # Delete collection
    db.delete_collection('lifecycle_test')
    print("✅ Collection deleted")
    
    db.disconnect()
    return True


def test_add_and_search():
    """Test adding items and searching."""
    print("\n=== Test 3: Add and Search ===")
    config = PGVectorVecDBConfig(
        host='127.0.0.1',
        port=24432,
        database='memos',
        user='memos',
        password='CrNfpXpF3s8yZCFm',
        collection_name='search_test',
        vector_dimension=768,
        distance_metric='cosine'
    )
    
    db = PGVectorVecDB(config)
    
    # Create collection
    db.create_collection('search_test', dimension=768)
    
    # Add items
    items = [
        VecDBItem(
            id=make_uuid(),
            vector=[0.1] * 768,
            payload={'text': 'hello world', 'source': 'test'}
        ),
        VecDBItem(
            id=make_uuid(),
            vector=[0.2] * 768,
            payload={'text': 'second item', 'source': 'test'}
        )
    ]
    
    db.add('search_test', items)
    print(f"✅ Added {len(items)} items")
    
    # Search
    results = db.search(
        collection_name='search_test',
        query_vector=[0.1] * 768,
        top_k=2
    )
    
    print(f"✅ Found {len(results)} results")
    for i, r in enumerate(results[:2]):
        print(f"  {i+1}. score={r['score']:.4f}, text={r['payload'].get('text', 'N/A')}")
    
    # Cleanup
    db.delete_collection('search_test')
    db.disconnect()
    
    return True


def run_all_tests():
    """Run all tests."""
    tests = [
        test_connection,
        test_collection_lifecycle,
        test_add_and_search,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
