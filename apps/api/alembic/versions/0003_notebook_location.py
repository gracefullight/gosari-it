"""Store user-selected notebook locations.

Revision ID: 0003_notebook_location
Revises: 0002_personal_pg18
"""

from alembic import op

revision = "0003_notebook_location"
down_revision = "0002_personal_pg18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE personal_notebook_entry ADD COLUMN location_address TEXT")
    op.execute("ALTER TABLE personal_notebook_entry ADD COLUMN latitude DOUBLE PRECISION")
    op.execute("ALTER TABLE personal_notebook_entry ADD COLUMN longitude DOUBLE PRECISION")
    op.execute(
        "ALTER TABLE personal_notebook_entry ADD CONSTRAINT notebook_location_pair CHECK ((latitude IS NULL) = (longitude IS NULL))"
    )
    op.execute(
        "ALTER TABLE personal_notebook_entry ADD CONSTRAINT notebook_latitude_range CHECK (latitude BETWEEN -90 AND 90)"
    )
    op.execute(
        "ALTER TABLE personal_notebook_entry ADD CONSTRAINT notebook_longitude_range CHECK (longitude BETWEEN -180 AND 180)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE personal_notebook_entry DROP CONSTRAINT notebook_location_pair, DROP CONSTRAINT notebook_latitude_range, DROP CONSTRAINT notebook_longitude_range"
    )
    op.execute(
        "ALTER TABLE personal_notebook_entry DROP COLUMN longitude, DROP COLUMN latitude, DROP COLUMN location_address"
    )
