
BEGIN;

CREATE TABLE public.backup_jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,

    trigger_type varchar(20) NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'pending',

    filename varchar(255),
    file_size_bytes bigint,
    error_message text,

    CONSTRAINT backup_jobs_trigger_check
        CHECK (trigger_type IN ('manual', 'scheduled')),

    CONSTRAINT backup_jobs_status_check
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),

    CONSTRAINT backup_jobs_file_size_check
        CHECK (file_size_bytes IS NULL OR file_size_bytes >= 0)
);

CREATE INDEX backup_jobs_status_requested_idx
    ON public.backup_jobs (status, requested_at);

COMMIT;
