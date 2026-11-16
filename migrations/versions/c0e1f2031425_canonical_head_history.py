"""Explicit working-head lineage. Existing snapshots remain untouched."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0e1f2031425"
down_revision: str | None = "b9d0e1f20314"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table = "canonical_head_events"
    op.create_table(
        table,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("domain_snapshots.id"), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(36), sa.ForeignKey("domain_snapshots.id")),
        sa.Column("previous_event_id", sa.String(36), sa.ForeignKey("canonical_head_events.id")),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resource_id", "sequence", name="uq_canonical_head_sequence"),
        sa.UniqueConstraint("organization_id", "request_id", name="uq_canonical_head_request"),
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
                "BEGIN SELECT RAISE(ABORT, 'canonical_head_history_is_append_only'); END"
            )
    else:
        raise RuntimeError("unsupported_canonical_head_database")


def downgrade() -> None:
    op.drop_table("canonical_head_events")
