"""Initial schema with stores, routes, and event_logs tables.

Revision ID: 001
Revises:
Create Date: 2025-01-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # stores table
    op.create_table(
        "stores",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("opening_hours", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{}",
        ),
    )

    # routes table
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "store_id",
            sa.String(50),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_location", sa.String(50), nullable=False, server_default="kiosk"),
    )
    op.create_index("ix_routes_store_id", "routes", ["store_id"])

    # route_steps table
    op.create_table(
        "route_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "route_id",
            sa.Integer(),
            sa.ForeignKey("routes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.String(200), nullable=False),
        sa.Column("landmark", sa.String(100), nullable=True),
        sa.Column("distance_meters", sa.Integer(), nullable=True),
    )
    op.create_index("ix_route_steps_route_id", "route_steps", ["route_id"])

    # event_logs table
    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(50), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("event_logs")
    op.drop_table("route_steps")
    op.drop_table("routes")
    op.drop_table("stores")
