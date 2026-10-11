"""高峰时段窗口 + 编辑场地价格（只影响之后放场的批次）

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-10-11 16:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "peak_start_time" not in _cols("venues"):
        op.add_column("venues", sa.Column("peak_start_time", sa.Time(), nullable=True))
        op.add_column("venues", sa.Column("peak_end_time", sa.Time(), nullable=True))
        op.add_column("venues", sa.Column("peak_ratio_bp", sa.Integer(), nullable=False, server_default="15000"))


def downgrade() -> None:
    if "peak_start_time" in _cols("venues"):
        op.drop_column("venues", "peak_ratio_bp")
        op.drop_column("venues", "peak_end_time")
        op.drop_column("venues", "peak_start_time")
