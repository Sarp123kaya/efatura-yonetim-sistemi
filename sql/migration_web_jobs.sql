-- Web panel background job queue.

CREATE TABLE IF NOT EXISTS web_jobs (
    id UUID PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success', 'failed', 'cancelled')),
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_by TEXT,
    locked_at TIMESTAMPTZ,
    log_text TEXT NOT NULL DEFAULT '',
    log_path TEXT,
    created_files JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_web_jobs_status_created
    ON web_jobs(status, created_at);

CREATE INDEX IF NOT EXISTS idx_web_jobs_type_created
    ON web_jobs(type, created_at DESC);
