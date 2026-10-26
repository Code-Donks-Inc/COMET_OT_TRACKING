CREATE TABLE IF NOT EXISTS public.backup_archives (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    archive_filename VARCHAR(255) NOT NULL UNIQUE,

    archive_year INTEGER NOT NULL,
    archive_month INTEGER NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    verified_at TIMESTAMPTZ,

    verification_status VARCHAR(20) NOT NULL DEFAULT 'pending',

    retention_expires_at TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '3 years'),

    file_size_bytes BIGINT,

    CONSTRAINT unique_archive_period
        UNIQUE (archive_year, archive_month),

    CONSTRAINT valid_archive_month
        CHECK (archive_month BETWEEN 1 AND 12),

    CONSTRAINT valid_archive_year
        CHECK (archive_year BETWEEN 2000 AND 9999),

    CONSTRAINT valid_verification_status
        CHECK (
            verification_status IN (
                'pending',
                'verified',
                'failed'
            )
        ),
    CONSTRAINT valid_archive_size
        CHECK (
            file_size_bytes IS NULL
            OR file_size_bytes >= 0
        ) 
);