CREATE TABLE knowledge_documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 300),
    source text NOT NULL CHECK (length(btrim(source)) BETWEEN 1 AND 100),
    source_type text NOT NULL CHECK (source_type IN ('markdown', 'text')),
    original_reference text NOT NULL UNIQUE,
    content_hash char(64) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    embedding_model text NOT NULL,
    indexing_status text NOT NULL DEFAULT 'READY' CHECK (indexing_status IN ('READY', 'FAILED')),
    error_summary text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE knowledge_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL CHECK (length(btrim(content)) > 0),
    embedding vector(1024) NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    embedding_model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX knowledge_chunks_document_idx ON knowledge_chunks(document_id);
CREATE TABLE knowledge_indexing_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    original_reference text NOT NULL,
    content_hash char(64) NOT NULL,
    status text NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    error_type text,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((status='SUCCESS' AND error_type IS NULL) OR (status='FAILED' AND error_type IS NOT NULL))
);
CREATE INDEX knowledge_indexing_attempts_reference_idx ON knowledge_indexing_attempts(original_reference, finished_at DESC);
-- Exact cosine scan is deliberate for the small curated documentation corpus.
