"""Shared normalized public tool cache and response integrity digests."""

from alembic import op

revision = "0007_public_shared_cache"
down_revision = "0006_session_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public_response_cache ADD COLUMN answer_hash TEXT")
    op.execute("""
        CREATE TABLE public_source_cache (
            cache_key TEXT PRIMARY KEY,
            public_query_spec JSONB NOT NULL,
            normalized_result JSONB NOT NULL,
            source_manifests JSONB NOT NULL,
            observed_period JSONB NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
            parser_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            source_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            valid_until TIMESTAMPTZ NOT NULL,
            invalidated_at TIMESTAMPTZ,
            quality_passed BOOLEAN NOT NULL DEFAULT false,
            hit_count BIGINT NOT NULL DEFAULT 0,
            last_used_at TIMESTAMPTZ,
            CHECK (valid_until > created_at)
        )
    """)
    op.execute(
        "CREATE INDEX idx_public_source_cache_expiry ON public_source_cache (valid_until) WHERE invalidated_at IS NULL AND quality_passed = true"
    )


def downgrade() -> None:
    op.execute("DROP TABLE public_source_cache")
    op.execute("ALTER TABLE public_response_cache DROP COLUMN answer_hash")
