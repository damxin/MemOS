-- Initialize pgvector extension and create default tables

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create default database (if using different name from POSTGRES_DB)
-- Note: This is handled by environment variables in docker-compose

-- Grant permissions to memos user
GRANT ALL PRIVILEGES ON DATABASE memos TO memos;

-- Note: Tables will be created by the application using SQLAlchemy
