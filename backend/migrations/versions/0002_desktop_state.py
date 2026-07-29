"""Add persisted active desktop operation."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "active_operations" in inspector.get_table_names():
        return
    op.create_table(
        "active_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation_type", sa.String(length=60), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("route_payload", sa.JSON(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manual_progress", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("active_operations")
