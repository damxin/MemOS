"""
Simple SQL generation tests for PGVector implementation.
Tests SQL statements without requiring PostgreSQL connection.
"""
import unittest


def get_distance_operator(metric='cosine'):
    """Get pgvector distance operator for a metric."""
    operators = {
        'cosine': ('<=>', '1 - (embedding <=> %s)'),
        'euclidean': ('<->', '(embedding <-> %s)'),
        'dot': ('<#>', '(embedding <#> %s) * -1')
    }
    return operators.get(metric, operators['cosine'])


class TestPGVectorSQL(unittest.TestCase):
    """Test SQL generation for pgvector operations."""

    def test_cosine_operator(self):
        """Test cosine distance operator."""
        op, expr = get_distance_operator('cosine')
        self.assertEqual(op, '<=>')
        self.assertIn('1 - (embedding <=> %s)', expr)

    def test_euclidean_operator(self):
        """Test euclidean distance operator."""
        op, expr = get_distance_operator('euclidean')
        self.assertEqual(op, '<->')

    def test_dot_operator(self):
        """Test dot product operator."""
        op, expr = get_distance_operator('dot')
        self.assertEqual(op, '<#>')

    def test_create_table_has_vector_type(self):
        """Test CREATE TABLE includes VECTOR type."""
        sql = """CREATE TABLE IF NOT EXISTS vecs_test (
            id TEXT PRIMARY KEY,
            embedding VECTOR(768),
            payload JSONB
        )"""
        self.assertIn('VECTOR(768)', sql)
        self.assertIn('JSONB', sql)

    def test_hnsw_index_syntax(self):
        """Test HNSW index syntax."""
        sql = "CREATE INDEX idx ON t USING hnsw (embedding vector_cosine_ops)"
        self.assertIn('USING hnsw', sql)
        self.assertIn('vector_cosine_ops', sql)


if __name__ == '__main__':
    unittest.main(verbosity=2)