"""Add Computer audit and immutable confirmation records."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "computer_confirmations" not in tables:
        op.create_table(
            "computer_confirmations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tool_name", sa.String(length=100), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("arguments", sa.JSON(), nullable=False),
            sa.Column("arguments_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_computer_confirmations_status",
            "computer_confirmations",
            ["status"],
        )
        op.create_index(
            "ix_computer_confirmations_expires_at",
            "computer_confirmations",
            ["expires_at"],
        )
    if "computer_invocations" not in tables:
        op.create_table(
            "computer_invocations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tool_name", sa.String(length=100), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("arguments", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "confirmation_id",
                sa.String(length=36),
                sa.ForeignKey("computer_confirmations.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_computer_invocations_tool_name",
            "computer_invocations",
            ["tool_name"],
        )
        op.create_index(
            "ix_computer_invocations_status",
            "computer_invocations",
            ["status"],
        )
        op.create_index(
            "ix_computer_invocations_created_at",
            "computer_invocations",
            ["created_at"],
        )


def downgrade() -> None:
    op.drop_table("computer_invocations")
    op.drop_table("computer_confirmations")
