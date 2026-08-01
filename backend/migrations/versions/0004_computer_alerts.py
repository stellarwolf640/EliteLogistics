"""Add deterministic Computer alert and snooze records."""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "computer_alerts" not in tables:
        op.create_table(
            "computer_alerts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("fingerprint", sa.String(length=64), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("facts", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("interrupt_allowed", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        )
        for column in ("fingerprint", "category", "severity", "status", "created_at"):
            op.create_index(f"ix_computer_alerts_{column}", "computer_alerts", [column])
    if "computer_alert_snoozes" not in tables:
        op.create_table(
            "computer_alert_snoozes",
            sa.Column("category", sa.String(length=80), primary_key=True),
            sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_computer_alert_snoozes_snoozed_until",
            "computer_alert_snoozes",
            ["snoozed_until"],
        )


def downgrade() -> None:
    op.drop_table("computer_alert_snoozes")
    op.drop_table("computer_alerts")
