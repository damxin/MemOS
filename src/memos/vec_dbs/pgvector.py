"""PostgreSQL + pgvector vector database implementation."""

import json
import re
import uuid
from typing import Any

from memos.configs.vec_db import PGVectorVecDBConfig
from memos.dependency import require_python_package
from memos.log import get_logger
from memos.vec_dbs.base import BaseVecDB
from memos.vec_dbs.item import VecDBItem


logger = get_logger(__name__)


class PGVectorVecDB(BaseVecDB):
    """PostgreSQL + pgvector vector database implementation.

    This class provides a vector database interface using PostgreSQL with the pgvector extension.
    It supports cosine, euclidean, and dot product distance metrics.
    """

    @require_python_package(
        import_name="psycopg2",
        install_command="pip install psycopg2-binary",
        install_link="https://pypi.org/project/psycopg2-binary/",
    )
    @require_python_package(
        import_name="pgvector",
        install_command="pip install pgvector",
        install_link="https://pypi.org/project/pgvector/",
    )
    def __init__(self, config: PGVectorVecDBConfig):
        """Initialize the PostgreSQL + pgvector database.

        Args:
            config: Configuration object containing connection parameters and collection settings.
        """
        import psycopg2
        from pgvector.psycopg2 import register_vector

        self.config = config
        self._default_payload_index_fields = [
            "memory_type",
            "status",
            "vector_sync",
            "user_name",
        ]

        # Build connection parameters
        conn_params = {
            "host": self.config.host,
            "port": self.config.port,
            "database": self.config.database,
            "user": self.config.user,
            "password": self.config.password,
        }

        try:
            # Connect and register pgvector
            self.conn = psycopg2.connect(**conn_params)
            self.conn.autocommit = False
            register_vector(self.conn)

            # Enable pgvector extension
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                self.conn.commit()

            logger.info(
                f"Connected to PostgreSQL: host={self.config.host}, "
                f"port={self.config.port}, database={self.config.database}"
            )

        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

        # Create collection (table) if not exists
        self.create_collection()
        self.ensure_payload_indexes(self._default_payload_index_fields)

        logger.info(
            f"PGVectorVecDB initialized: collection={self.config.collection_name}, "
            f"vector_dimension={self.config.vector_dimension}, "
            f"distance_metric={self.config.distance_metric}"
        )

    def _get_table_name(self) -> str:
        """Get the sanitized table name for the collection.

        Returns:
            Sanitized table name with 'vec_' prefix.
        """
        # Sanitize collection name to be SQL-safe
        table_name = re.sub(r'[^a-zA-Z0-9_]', '_', self.config.collection_name)
        return f"vec_{table_name}"

    def _get_vector_ops(self) -> str:
        """Get the vector operator class for index creation.

        Returns:
            PostgreSQL operator class name for the distance metric.
        """
        ops_map = {
            "cosine": "vector_cosine_ops",
            "euclidean": "vector_l2_ops",
            "dot": "vector_ip_ops",
        }
        return ops_map.get(self.config.distance_metric, "vector_cosine_ops")

    def _get_distance_operator(self) -> str:
        """Get the distance operator for similarity search.

        Returns:
            PostgreSQL distance operator symbol.
        """
        op_map = {
            "cosine": "<=>",  # cosine distance
            "euclidean": "<->",  # L2 distance
            "dot": "<#>",  # negative inner product
        }
        return op_map.get(self.config.distance_metric, "<=>")

    def create_collection(self) -> None:
        """Create a new collection (table) with specified parameters."""
        table_name = self._get_table_name()
        vector_dim = self.config.vector_dimension
        vector_ops = self._get_vector_ops()

        with self.conn.cursor() as cur:
            # Check if table exists
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = %s
                );
                """,
                (table_name,),
            )
            exists = cur.fetchone()[0]

            if exists:
                logger.info(f"Collection '{table_name}' already exists. Skipping creation.")
                return

            # Create table with vector column
            cur.execute(
                f"""
                CREATE TABLE {table_name} (
                    id UUID PRIMARY KEY,
                    vector vector({vector_dim}),
                    payload JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Create HNSW index on vector for similarity search (better performance)
            cur.execute(
                f"""
                CREATE INDEX idx_{table_name}_vector
                ON {table_name}
                USING hnsw (vector {vector_ops});
                """
            )

            # Create GIN index on payload for JSONB queries
            cur.execute(
                f"""
                CREATE INDEX idx_{table_name}_payload
                ON {table_name}
                USING GIN (payload);
                """
            )

            # Create index on created_at for ordering
            cur.execute(
                f"""
                CREATE INDEX idx_{table_name}_created_at
                ON {table_name} (created_at);
                """
            )

            self.conn.commit()
            logger.info(f"Collection '{table_name}' created successfully with HNSW index.")

    def list_collections(self) -> list[str]:
        """List all collections (tables) in the database.

        Returns:
            List of collection names (without 'vec_' prefix).
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public' AND tablename LIKE 'vec_%';
                """
            )
            results = cur.fetchall()
            # Remove 'vec_' prefix to get original collection names
            return [row[0][4:] for row in results]

    def delete_collection(self, name: str) -> None:
        """Delete a collection (table).

        Args:
            name: Name of the collection to delete.
        """
        table_name = f"vec_{re.sub(r'[^a-zA-Z0-9_]', '_', name)}"

        with self.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
            self.conn.commit()
            logger.info(f"Collection '{name}' (table: {table_name}) deleted.")

    def collection_exists(self, name: str) -> bool:
        """Check if a collection (table) exists.

        Args:
            name: Name of the collection to check.

        Returns:
            True if the collection exists, False otherwise.
        """
        table_name = f"vec_{re.sub(r'[^a-zA-Z0-9_]', '_', name)}"

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = %s
                );
                """,
                (table_name,),
            )
            return cur.fetchone()[0]

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        filter: dict[str, Any] | None = None,
    ) -> list[VecDBItem]:
        """Search for similar items in the vector database.

        Args:
            query_vector: Query embedding vector.
            top_k: Number of results to return.
            filter: Optional payload filters.

        Returns:
            List of search results with similarity scores.
        """
        table_name = self._get_table_name()
        distance_op = self._get_distance_operator()

        # Build filter conditions
        where_clauses = []
        filter_params: list[Any] = []

        if filter:
            for key, value in filter.items():
                where_clauses.append(f"payload->>'{key}' = %s")
                filter_params.append(str(value))

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Build query with distance calculation
        # Note: query_vector is used twice (for distance and for order)
        query_sql = f"""
            SELECT id, vector, payload, 
                   vector {distance_op} %s::vector as distance
            FROM {table_name}
            {where_sql}
            ORDER BY vector {distance_op} %s::vector
            LIMIT %s;
        """

        # Parameters order: query_vector (distance), filter_params..., query_vector (order), top_k
        all_params = [query_vector] + filter_params + [query_vector, top_k]

        with self.conn.cursor() as cur:
            cur.execute(query_sql, tuple(all_params))

            results = []
            for row in cur.fetchall():
                distance = row[3]

                # Convert distance to similarity score
                if self.config.distance_metric == "dot":
                    # Negative inner product: more negative = higher similarity
                    score = -distance
                else:
                    # Cosine/Euclidean: convert to similarity (1 / (1 + distance))
                    score = 1.0 / (1.0 + distance) if distance is not None else 0.0

                results.append(VecDBItem(
                    id=str(row[0]),
                    vector=row[1].tolist() if row[1] is not None else None,
                    payload=row[2],
                    score=score,
                ))

            return results

    def get_by_id(self, id: str) -> VecDBItem | None:
        """Get an item from the vector database by ID.

        Args:
            id: Unique identifier of the item.

        Returns:
            VecDBItem if found, None otherwise.
        """
        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, vector, payload
                FROM {table_name}
                WHERE id = %s;
                """,
                (id,),
            )

            row = cur.fetchone()
            if not row:
                return None

            return VecDBItem(
                id=str(row[0]),
                vector=row[1].tolist() if row[1] is not None else None,
                payload=row[2],
            )

    def get_by_ids(self, ids: list[str]) -> list[VecDBItem]:
        """Get multiple items by their IDs.

        Args:
            ids: List of unique identifiers.

        Returns:
            List of VecDBItem objects.
        """
        if not ids:
            return []

        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, vector, payload
                FROM {table_name}
                WHERE id = ANY(%s);
                """,
                (ids,),
            )

            results = []
            for row in cur.fetchall():
                results.append(VecDBItem(
                    id=str(row[0]),
                    vector=row[1].tolist() if row[1] is not None else None,
                    payload=row[2],
                ))
            return results

    def get_by_filter(self, filter: dict[str, Any]) -> list[VecDBItem]:
        """Retrieve all items that match the given filter criteria.

        Args:
            filter: Payload filters to match against stored items.

        Returns:
            List of matching VecDBItem objects.
        """
        table_name = self._get_table_name()

        where_clauses = []
        params = []

        for key, value in filter.items():
            where_clauses.append(f"payload->>'{key}' = %s")
            params.append(str(value))

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, vector, payload
                FROM {table_name}
                {where_sql};
                """,
                tuple(params),
            )

            results = []
            for row in cur.fetchall():
                results.append(VecDBItem(
                    id=str(row[0]),
                    vector=row[1].tolist() if row[1] is not None else None,
                    payload=row[2],
                ))
            return results

    def get_all(self) -> list[VecDBItem]:
        """Retrieve all items in the vector database.

        Returns:
            List of all VecDBItem objects in the collection.
        """
        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, vector, payload
                FROM {table_name};
                """
            )

            results = []
            for row in cur.fetchall():
                results.append(VecDBItem(
                    id=str(row[0]),
                    vector=row[1].tolist() if row[1] is not None else None,
                    payload=row[2],
                ))
            return results

    def count(self, filter: dict[str, Any] | None = None) -> int:
        """Count items in the database, optionally with filter.

        Args:
            filter: Optional payload filters.

        Returns:
            Number of matching items.
        """
        table_name = self._get_table_name()

        where_clauses = []
        params = []

        if filter:
            for key, value in filter.items():
                where_clauses.append(f"payload->>'{key}' = %s")
                params.append(str(value))

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM {table_name} {where_sql};
                """,
                tuple(params),
            )
            return cur.fetchone()[0]

    def add(self, data: list[VecDBItem | dict[str, Any]]) -> None:
        """Add data to the vector database.

        Args:
            data: List of VecDBItem objects or dictionaries containing:
                - 'id': unique identifier
                - 'vector': embedding vector
                - 'payload': additional fields for filtering/retrieval
        """
        if not data:
            return

        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            for item in data:
                if isinstance(item, dict):
                    item_id = item.get("id")
                    vector = item.get("vector")
                    payload = item.get("payload", {})
                else:
                    item_id = item.id
                    vector = item.vector
                    payload = item.payload or {}

                # Validate UUID
                try:
                    uuid.UUID(str(item_id))
                except ValueError:
                    item_id = str(uuid.uuid4())

                # Insert - convert payload dict to JSON string for JSONB
                cur.execute(
                    f"""
                    INSERT INTO {table_name} (id, vector, payload)
                    VALUES (%s, %s, %s::jsonb);
                    """,
                    (item_id, vector, json.dumps(payload)),
                )

            self.conn.commit()
            logger.debug(f"Added {len(data)} items to collection '{table_name}'.")

    def update(self, id: str, data: VecDBItem | dict[str, Any]) -> None:
        """Update an item in the vector database.

        Args:
            id: Unique identifier of the item to update.
            data: Updated data (VecDBItem or dict).
        """
        table_name = self._get_table_name()

        if isinstance(data, dict):
            vector = data.get("vector")
            payload = data.get("payload", {})
        else:
            vector = data.vector
            payload = data.payload or {}

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {table_name}
                SET vector = %s, payload = %s::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (vector, json.dumps(payload), id),
            )
            self.conn.commit()
            logger.debug(f"Updated item '{id}' in collection '{table_name}'.")

    def upsert(self, data: list[VecDBItem | dict[str, Any]]) -> None:
        """Add or update data in the vector database.

        If an item with the same ID exists, it will be updated.
        Otherwise, it will be added as a new item.

        Args:
            data: List of VecDBItem objects or dictionaries.
        """
        if not data:
            return

        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            for item in data:
                if isinstance(item, dict):
                    item_id = item.get("id")
                    vector = item.get("vector")
                    payload = item.get("payload", {})
                else:
                    item_id = item.id
                    vector = item.vector
                    payload = item.payload or {}

                # Validate UUID
                try:
                    uuid.UUID(str(item_id))
                except ValueError:
                    item_id = str(uuid.uuid4())

                # Upsert (INSERT ... ON CONFLICT UPDATE)
                cur.execute(
                    f"""
                    INSERT INTO {table_name} (id, vector, payload)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        vector = EXCLUDED.vector,
                        payload = EXCLUDED.payload,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (item_id, vector, json.dumps(payload)),
                )

            self.conn.commit()
            logger.debug(f"Upserted {len(data)} items to collection '{table_name}'.")

    def delete(self, ids: list[str]) -> None:
        """Delete items from the vector database.

        Args:
            ids: List of unique identifiers to delete.
        """
        if not ids:
            return

        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {table_name}
                WHERE id = ANY(%s);
                """,
                (ids,),
            )
            self.conn.commit()
            logger.debug(f"Deleted {len(ids)} items from collection '{table_name}'.")

    def ensure_payload_indexes(self, fields: list[str]) -> None:
        """Create indexes on payload fields for efficient filtering.

        Args:
            fields: List of field names to index.
        """
        table_name = self._get_table_name()

        with self.conn.cursor() as cur:
            for field in fields:
                # Create GIN index for JSONB key
                index_name = f"idx_{table_name}_payload_{field}"
                try:
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {table_name} ((payload->>'{field}'));
                        """
                    )
                except Exception as e:
                    logger.warning(f"Failed to create index {index_name}: {e}")

            self.conn.commit()
            logger.debug(f"Ensured payload indexes for fields: {fields}")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("PostgreSQL connection closed.")

    def __del__(self):
        """Destructor to ensure connection is closed."""
        try:
            self.close()
        except AttributeError:
            # Connection was never initialized
            pass