"""Append-only restored package validation; no head changes or backfill."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1f203142536"
down_revision: str | None = "c0e1f2031425"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "restored_package_validations"
    op.create_table(
        table,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column(
            "restore_event_id",
            sa.String(36),
            sa.ForeignKey("canonical_head_events.id"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id", sa.String(36), sa.ForeignKey("domain_snapshots.id"), nullable=False
        ),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("xml_artifact_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False),
        sa.Column(
            "package_artifact_id", sa.String(36), sa.ForeignKey("artifacts.id"), nullable=False
        ),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("reports", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "request_id", name="uq_restored_validation_request"),
    )
    for column in ("organization_id", "resource_id"):
        op.create_index(f"ix_{table}_{column}", table, [column])
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_autocorrection_history_change()"
        )
    elif dialect == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'restored_validation_history_is_append_only'); END"
            )
    else:
        raise RuntimeError("unsupported_restored_validation_database")


def downgrade() -> None:
    op.drop_table("restored_package_validations")
