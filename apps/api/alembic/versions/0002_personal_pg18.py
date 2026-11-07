"""PostgreSQL 18 session and personal records schema (3NF with CASCADE)

Revision ID: 0002_personal_pg18
Revises: 0001_public
"""

from alembic import op

revision = "0002_personal_pg18"
down_revision = "0001_public"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_session (
            session_id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            lifecycle TEXT NOT NULL DEFAULT 'active'
                CHECK (lifecycle IN ('active', 'expired', 'closed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_notebook_entry (
            record_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES app_session(session_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
            experience_date DATE NOT NULL,
            companion_aliases JSONB NOT NULL DEFAULT '[]',
            activity_text TEXT NOT NULL,
            amount_value TEXT,
            amount_unit TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_notebook_session_date
        ON personal_notebook_entry (session_id, experience_date)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_private_region (
            region_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES app_session(session_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
            kind TEXT NOT NULL CHECK (kind IN ('existing', 'interest')),
            public_area_code TEXT,
            coarse_grid TEXT,
            local_alias TEXT NOT NULL,
            selected_station_mapping_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_region_session
        ON personal_private_region (session_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_share_draft (
            share_draft_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES app_session(session_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
            items JSONB NOT NULL DEFAULT '[]',
            message_enabled BOOLEAN NOT NULL DEFAULT true,
            editable_message TEXT,
            source_record_ids JSONB NOT NULL DEFAULT '[]',
            public_evidence_ids JSONB NOT NULL DEFAULT '[]',
            prepared_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_personal_share_session
        ON personal_share_draft (session_id)
        """
    )


def downgrade() -> None:
    for table in (
        "personal_share_draft",
        "personal_private_region",
        "personal_notebook_entry",
        "app_session",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
