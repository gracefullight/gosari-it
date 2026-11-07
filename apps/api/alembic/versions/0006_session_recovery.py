"""Persist approval receipts and notebook references across process restarts."""

from alembic import op

revision = "0006_session_recovery"
down_revision = "0005_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app_session ADD COLUMN control_state JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE personal_notebook_entry ADD COLUMN private_region_id TEXT")
    op.execute(
        "ALTER TABLE personal_notebook_entry ADD COLUMN public_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE personal_notebook_entry DROP COLUMN public_evidence_ids")
    op.execute("ALTER TABLE personal_notebook_entry DROP COLUMN private_region_id")
    op.execute("ALTER TABLE app_session DROP COLUMN control_state")
