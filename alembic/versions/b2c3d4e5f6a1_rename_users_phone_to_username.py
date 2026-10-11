"""rename users.phone to username

Revision ID: a1b2c3d4e5f6
Revises: ecc2d02e6502
Create Date: 2026-10-10
"""

from __future__ import annotations

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "ecc2d02e6502"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 列重命名与 MODIFY 已在前次半执行的升级中生效，这里只补索引名
    op.execute("ALTER TABLE users RENAME INDEX `phone` TO `uk_users_username`")


def downgrade() -> None:
    op.execute("ALTER TABLE users RENAME INDEX `uk_users_username` TO `username`")
    op.execute("ALTER TABLE users MODIFY username VARCHAR(20) NOT NULL")
    op.execute("ALTER TABLE users RENAME COLUMN username TO phone")
