"""Add customs_warning_sent column to tracked_packages

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-24 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tracked_packages",
        sa.Column(
            "customs_warning_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tracked_packages", "customs_warning_sent")
