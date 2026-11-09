"""Member accounts that own a home session for anonymous-history merge.

Revision ID: 0008_members
Revises: 0007_public_shared_cache
"""

from alembic import op

revision = "0008_members"
down_revision = "0007_public_shared_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE app_member (
            member_id TEXT PRIMARY KEY,
            login_id TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )"""
    )
    op.execute(
        """ALTER TABLE app_session
        ADD COLUMN member_id TEXT REFERENCES app_member(member_id) ON DELETE SET NULL"""
    )
    op.execute("CREATE INDEX idx_app_session_member ON app_session (member_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON app_member TO gosari_app")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_app_session_member")
    op.execute("ALTER TABLE app_session DROP COLUMN member_id")
    op.execute("DROP TABLE app_member")
