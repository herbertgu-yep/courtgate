"""booking_items.court_slot_id 可空（取消后置空，唯一约束只约束有效占用）

Revision ID: c3d4e5f6a7b8
Revises: a9b0c1d2e3f4
Create Date: 2026-10-11 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("booking_items", "court_slot_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ix_booking_items_court_slot_id", "booking_items", ["court_slot_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_items_court_slot_id", table_name="booking_items")
    op.execute("UPDATE booking_items SET court_slot_id = id WHERE court_slot_id IS NULL")
    op.alter_column("booking_items", "court_slot_id", existing_type=sa.Integer(), nullable=False)
