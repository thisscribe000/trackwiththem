"""Initial migration: users, tracked_packages, status_history

Revision ID: 0001
Revises:
Create Date: 2026-06-19 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    op.create_table(
        "tracked_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(255), nullable=False),
        sa.Column("carrier_code", sa.String(50), nullable=False),
        sa.Column("carrier_name", sa.String(100), nullable=False),
        sa.Column("nickname", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("last_checkpoint_location", sa.Text(), nullable=True),
        sa.Column("last_checkpoint_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_delivery", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "status_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["tracked_packages.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("status_history")
    op.drop_table("tracked_packages")
    op.drop_table("users")
