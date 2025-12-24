"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-06-02
"""

from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("token", sa.String(length=64), unique=True, nullable=True),
        sa.Column("status", sa.Enum("draft", "open", "paid", name="receiptstatus"), nullable=False, server_default="draft"),
        sa.Column("image_path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("receipt_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("receipts.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("qty_total", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint("ck_items_qty_positive", "items", "qty_total > 0")

    op.create_table(
        "item_units",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("unit_index", sa.Integer(), nullable=False),
        sa.Column("amount_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.Enum("unpaid", "partial", "paid", name="unitstatus"), nullable=False, server_default="unpaid"),
        sa.UniqueConstraint("item_id", "unit_index", name="uq_item_unit_index"),
    )
    op.create_check_constraint("ck_unit_amount_paid_non_negative", "item_units", "amount_paid >= 0")

    op.create_table(
        "payments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("receipt_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("receipts.id", ondelete="CASCADE")),
        sa.Column("item_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("unit_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("item_units.id", ondelete="CASCADE")),
        sa.Column("payer_name", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("item_units")
    op.drop_table("items")
    op.drop_table("receipts")
    op.execute("DROP TYPE IF EXISTS receiptstatus")
    op.execute("DROP TYPE IF EXISTS unitstatus")

