"""Add paused_at column to products table.

Revision ID: add_product_paused_at
Revises: 390461e816ea
Create Date: 2026-09-22

The seller's per-product pause switch. Set: the product is hidden from buyers and refused
in create_media_buy while it stays editable in the admin UI. NULL (the default): live.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_product_paused_at"
down_revision: str | Sequence[str] | None = "390461e816ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add paused_at column to products table."""
    op.add_column("products", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove paused_at column from products table."""
    op.drop_column("products", "paused_at")
