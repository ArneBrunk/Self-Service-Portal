ALTER TABLE knowledge_chunk
  ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE INDEX IF NOT EXISTS idx_chunk_embedding ON knowledge_chunk USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- Falls pgvector noch nicht aktiv ist
CREATE EXTENSION IF NOT EXISTS vector;

-- Embedding-Spalte ergänzen
ALTER TABLE knowledge_knowledgegap
ADD COLUMN embedding vector(1536);
