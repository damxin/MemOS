#!/usr/bin/env python3
"""Test script for PostgreSQL + pgvector integration."""

import sys
import uuid
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from memos.configs.vec_db import PGVectorVecDBConfig
from memos.vec_dbs.pgvector import PGVectorVecDB
from memos.vec_dbs.item import VecDBItem


def test_pgvector_connection():
    """Test basic PostgreSQL + pgvector connection."""
    print("=" * 60)
    print("Testing PostgreSQL + pgvector Connection")
    print("=" * 60)
    
    # Configuration
    config = PGVectorVecDBConfig(
        host="localhost",  # Docker container running on localhost
        port=5432,
        database="memos",
        user="memos",
        password="2BrnwJTPjtd4iDEQ",
        collection_name="test_collection",
        vector_dimension=128,
        distance_metric="cosine",
    )
    
    print(f"\n✓ Config created:")
    print(f"  - Host: {config.host}")
    print(f"  - Port: {config.port}")
    print(f"  - Database: {config.database}")
    print(f"  - Collection: {config.collection_name}")
    print(f"  - Vector Dimension: {config.vector_dimension}")
    print(f"  - Distance Metric: {config.distance_metric}")
    
    try:
        # Initialize database
        print("\n→ Connecting to PostgreSQL...")
        db = PGVectorVecDB(config)
        print("✓ Connected successfully!")
        
        # Test collection operations
        print("\n→ Testing collection operations...")
        collections = db.list_collections()
        print(f"✓ Collections: {collections}")
        
        exists = db.collection_exists("test_collection")
        print(f"✓ Collection exists: {exists}")
        
        # Test vector operations
        print("\n→ Testing vector operations...")
        
        # Create test data
        test_items = [
            VecDBItem(
                id=str(uuid.uuid4()),
                vector=[0.1] * 128,
                payload={"text": "Hello world", "type": "greeting"}
            ),
            VecDBItem(
                id=str(uuid.uuid4()),
                vector=[0.2] * 128,
                payload={"text": "Good morning", "type": "greeting"}
            ),
            VecDBItem(
                id=str(uuid.uuid4()),
                vector=[0.9] * 128,
                payload={"text": "Technical document", "type": "document"}
            ),
        ]
        
        # Add items
        print(f"→ Adding {len(test_items)} test items...")
        db.add(test_items)
        print("✓ Items added successfully!")
        
        # Count items
        count = db.count()
        print(f"✓ Total items in collection: {count}")
        
        # Search
        print("\n→ Testing similarity search...")
        query_vector = [0.15] * 128
        results = db.search(query_vector, top_k=2)
        print(f"✓ Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. Score: {result.score:.4f}, Payload: {result.payload}")
        
        # Filter search
        print("\n→ Testing filtered search...")
        results = db.search(
            query_vector,
            top_k=5,
            filter={"type": "greeting"}
        )
        print(f"✓ Found {len(results)} greeting results:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. Score: {result.score:.4f}, Text: {result.payload.get('text')}")
        
        # Get by ID
        print("\n→ Testing get by ID...")
        item_id = test_items[0].id
        item = db.get_by_id(item_id)
        if item:
            print(f"✓ Retrieved item: {item.payload}")
        else:
            print("✗ Item not found")
        
        # Update
        print("\n→ Testing update...")
        db.update(item_id, VecDBItem(
            id=item_id,
            vector=[0.11] * 128,
            payload={"text": "Hello world (updated)", "type": "greeting", "updated": True}
        ))
        updated_item = db.get_by_id(item_id)
        print(f"✓ Updated item: {updated_item.payload}")
        
        # Delete
        print("\n→ Testing delete...")
        db.delete([item_id])
        deleted_item = db.get_by_id(item_id)
        print(f"✓ Item deleted: {deleted_item is None}")
        
        # Final count
        final_count = db.count()
        print(f"✓ Final count: {final_count}")
        
        # Cleanup
        print("\n→ Cleaning up test collection...")
        db.delete_collection("test_collection")
        print("✓ Test collection deleted")
        
        # Close connection
        db.close()
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_pgvector_connection()
    sys.exit(0 if success else 1)
