CREATE TABLE generation_jobs (
    job_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision >= 0),
    status TEXT NOT NULL CHECK (status IN ('submitting','submitted','in_progress','succeeded','failed')),
    prompt TEXT NOT NULL CHECK (length(prompt) > 0),
    model TEXT NOT NULL CHECK (length(model) > 0),
    size_width INTEGER NOT NULL CHECK (size_width > 0),
    size_height INTEGER NOT NULL CHECK (size_height > 0),
    negative_prompt TEXT,
    seed INTEGER,
    provider TEXT,
    provider_task_id TEXT,
    provider_request_id TEXT,
    last_provider_status TEXT,
    error_code TEXT,
    error_stage TEXT,
    error_category TEXT,
    error_retryable INTEGER,
    error_retry_after_seconds INTEGER,
    error_safe_message TEXT,
    error_provider_request_id TEXT,
    error_possibly_submitted INTEGER,
    error_occurred_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    completed_at TEXT,
    CHECK (provider_task_id IS NULL OR length(provider_task_id) > 0),
    CHECK (
        (status = 'submitting' AND provider_task_id IS NULL AND submitted_at IS NULL AND completed_at IS NULL)
        OR (status IN ('submitted','in_progress') AND provider_task_id IS NOT NULL AND submitted_at IS NOT NULL AND completed_at IS NULL)
        OR (status = 'succeeded' AND provider_task_id IS NOT NULL AND submitted_at IS NOT NULL AND completed_at IS NOT NULL)
        OR (status = 'failed' AND completed_at IS NOT NULL)
    ),
    CHECK (
        error_code IS NULL
        OR (error_stage IS NOT NULL AND error_category IS NOT NULL AND error_retryable IS NOT NULL AND error_safe_message IS NOT NULL AND error_occurred_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uq_generation_jobs_provider_task_id ON generation_jobs(provider_task_id) WHERE provider_task_id IS NOT NULL;
CREATE INDEX ix_generation_jobs_status_updated ON generation_jobs(status, updated_at DESC);
CREATE INDEX ix_generation_jobs_updated ON generation_jobs(updated_at DESC);

CREATE TABLE generated_images (
    image_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES generation_jobs(job_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    provider_locator TEXT NOT NULL,
    provider_metadata_json TEXT,
    artifact_status TEXT NOT NULL CHECK (artifact_status IN ('pending','available','failed')),
    artifact_key TEXT,
    relative_path TEXT,
    sha256 TEXT,
    byte_size INTEGER,
    media_type TEXT,
    image_format TEXT,
    width INTEGER,
    height INTEGER,
    saved_at TEXT,
    error_code TEXT,
    error_stage TEXT,
    error_category TEXT,
    error_retryable INTEGER,
    error_retry_after_seconds INTEGER,
    error_safe_message TEXT,
    error_provider_request_id TEXT,
    error_occurred_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (artifact_status = 'available' AND artifact_key IS NOT NULL AND relative_path IS NOT NULL AND sha256 IS NOT NULL AND byte_size > 0 AND media_type IS NOT NULL AND image_format IS NOT NULL AND width > 0 AND height > 0 AND saved_at IS NOT NULL AND error_code IS NULL)
        OR (artifact_status = 'pending' AND artifact_key IS NULL AND relative_path IS NULL AND sha256 IS NULL AND byte_size IS NULL AND media_type IS NULL AND image_format IS NULL AND width IS NULL AND height IS NULL AND saved_at IS NULL AND error_code IS NULL)
        OR (artifact_status = 'failed' AND artifact_key IS NULL AND relative_path IS NULL AND sha256 IS NULL AND byte_size IS NULL AND media_type IS NULL AND image_format IS NULL AND width IS NULL AND height IS NULL AND saved_at IS NULL AND error_code IS NOT NULL)
    ),
    CHECK (sha256 IS NULL OR (length(sha256) = 64 AND sha256 = lower(sha256))),
    UNIQUE(job_id, position),
    UNIQUE(artifact_key),
    UNIQUE(relative_path)
);
CREATE INDEX ix_generated_images_job_position ON generated_images(job_id, position);

CREATE TABLE artifact_cleanup_queue (
    cleanup_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    relative_job_dir TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
PRAGMA user_version = 1;
