"""Store user-selected region pins.

Revision ID: 0004_region_location
Revises: 0003_notebook_location
"""

from alembic import op

revision = "0004_region_location"
down_revision = "0003_notebook_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE personal_private_region ADD COLUMN visited_on DATE")
    op.execute("ALTER TABLE personal_private_region ADD COLUMN latitude DOUBLE PRECISION")
    op.execute("ALTER TABLE personal_private_region ADD COLUMN longitude DOUBLE PRECISION")
    op.execute(
        "ALTER TABLE personal_private_region ADD CONSTRAINT region_location_pair CHECK ((latitude IS NULL) = (longitude IS NULL))"
    )
    op.execute(
        "ALTER TABLE personal_private_region ADD CONSTRAINT region_latitude_range CHECK (latitude BETWEEN -90 AND 90)"
    )
    op.execute(
        "ALTER TABLE personal_private_region ADD CONSTRAINT region_longitude_range CHECK (longitude BETWEEN -180 AND 180)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE personal_private_region DROP CONSTRAINT region_location_pair, DROP CONSTRAINT region_latitude_range, DROP CONSTRAINT region_longitude_range"
    )
    op.execute(
        "ALTER TABLE personal_private_region DROP COLUMN longitude, DROP COLUMN latitude, DROP COLUMN visited_on"
    )
