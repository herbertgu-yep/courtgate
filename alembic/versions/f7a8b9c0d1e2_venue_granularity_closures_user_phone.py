"""场馆粒度配置 + 闭馆表 + 用户联系手机号 + 批次级时段切片

Revision ID: f7a8b9c0d1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-11 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "phone_number" not in _cols("users"):
        op.add_column("users", sa.Column("phone_number", sa.String(length=20), nullable=True))
    if "slot_minutes" not in _cols("venues"):
        op.add_column("venues", sa.Column("slot_minutes", sa.Integer(), nullable=False, server_default="60"))
    if "breaks_json" not in _cols("venues"):
        # MySQL 的 TEXT 列不接受字面默认值：先可空建列，回填后再置 NOT NULL
        op.add_column("venues", sa.Column("breaks_json", sa.Text(), nullable=True))
        op.execute("UPDATE venues SET breaks_json = '[]' WHERE breaks_json IS NULL")
        op.execute("ALTER TABLE venues MODIFY breaks_json TEXT NOT NULL")
    if "release_id" not in _cols("time_slots"):
        op.add_column("time_slots", sa.Column("release_id", sa.Integer(), nullable=True))
        op.create_index("ix_time_slots_release_id", "time_slots", ["release_id"])
    # start_time 原为全局唯一（时段模板表）；批次级切片后改为 (release_id, start_time) 唯一
    old_idx = bind.execute(
        sa.text(
            "SELECT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'time_slots' "
            "AND COLUMN_NAME = 'start_time' AND NON_UNIQUE = 0 LIMIT 1"
        )
    ).scalar()
    if old_idx:
        op.execute(f"ALTER TABLE time_slots DROP INDEX `{old_idx}`")
    existing_uk = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'time_slots' "
            "AND CONSTRAINT_NAME = 'uk_time_slots_release_start'"
        )
    ).scalar()
    if not existing_uk:
        op.create_unique_constraint("uk_time_slots_release_start", "time_slots", ["release_id", "start_time"])
    if not sa.inspect(bind).has_table("venue_closures"):
        op.create_table(
            "venue_closures",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("venue_id", sa.BigInteger(), nullable=False),
            sa.Column("closure_date", sa.Date(), nullable=False),
            sa.Column("notify_content", sa.Text(), nullable=True),
            sa.Column("affected_bookings", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.BigInteger(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
            sa.UniqueConstraint("venue_id", "closure_date", name="uk_closures_venue_date"),
        )
        op.create_index("ix_venue_closures_venue_id", "venue_closures", ["venue_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("venue_closures"):
        op.drop_index("ix_venue_closures_venue_id", table_name="venue_closures")
        op.drop_table("venue_closures")
    if "uk_time_slots_release_start" in {
        r[0]
        for r in bind.execute(
            sa.text(
                "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'time_slots'"
            )
        ).all()
    }:
        op.drop_constraint("uk_time_slots_release_start", "time_slots", type_="unique")
    op.create_unique_constraint("uk_time_slots_start_time", "time_slots", ["start_time"])
    if "release_id" in _cols("time_slots"):
        op.drop_index("ix_time_slots_release_id", table_name="time_slots")
        op.drop_column("time_slots", "release_id")
    if "breaks_json" in _cols("venues"):
        op.drop_column("venues", "breaks_json")
    if "slot_minutes" in _cols("venues"):
        op.drop_column("venues", "slot_minutes")
    if "phone_number" in _cols("users"):
        op.drop_column("users", "phone_number")
