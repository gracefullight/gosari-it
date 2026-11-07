"""Store private contacts for sharing history.

Revision ID: 0005_contacts
Revises: 0004_region_location
"""

from alembic import op

revision = "0005_contacts"
down_revision = "0004_region_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE personal_contact (
            contact_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES app_session(session_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX idx_personal_contact_session ON personal_contact (session_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON personal_contact TO gosari_app")


def downgrade() -> None:
    op.execute("DROP TABLE personal_contact")
