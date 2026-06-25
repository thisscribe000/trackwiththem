"""Add Shipment + ShipmentStatusHistory tables for P2P sending

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("share_code", sa.String(6), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("receiver_phone", sa.String(20), nullable=False),
        sa.Column("receiver_user_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("origin", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("bus_company", sa.String(100), nullable=True),
        sa.Column("bus_flight_number", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PREPARING"),
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
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["receiver_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipments_share_code", "shipments", ["share_code"], unique=True)

    op.create_table(
        "shipment_status_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(10), nullable=False, server_default="sender"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shipment_status_history")
    op.drop_table("shipments")
