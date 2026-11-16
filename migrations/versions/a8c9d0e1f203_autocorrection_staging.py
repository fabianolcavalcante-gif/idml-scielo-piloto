"""Private autocorrection staging; no active snapshot migration.

Revision ID: a8c9d0e1f203
Revises: f7b8c9d0e1f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c9d0e1f203"
down_revision: str | None = "f7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "automation_grants",
    "automation_grant_revocations",
    "automation_attempts",
    "automation_discards",
)


def upgrade() -> None:
    op.create_table(
        "automation_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column(
            "base_snapshot_id", sa.String(36), sa.ForeignKey("domain_snapshots.id"), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "automation_grant_revocations",
        sa.Column(
            "grant_id", sa.String(36), sa.ForeignKey("automation_grants.id"), primary_key=True
        ),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("decision_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "automation_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column(
            "base_snapshot_id", sa.String(36), sa.ForeignKey("domain_snapshots.id"), nullable=False
        ),
        sa.Column("intent_sha256", sa.String(64), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("candidate", sa.JSON(none_as_null=True)),
        sa.Column("xml_content", sa.Text()),
        sa.Column("validation", sa.JSON(none_as_null=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "resource_id", "intent_sha256", name="uq_auto_intent"
        ),
    )
    op.create_table(
        "automation_discards",
        sa.Column(
            "attempt_id", sa.String(36), sa.ForeignKey("automation_attempts.id"), primary_key=True
        ),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in TABLES:
        columns = ["organization_id"]
        if table in {"automation_grants", "automation_attempts"}:
            columns.append("resource_id")
        if table == "automation_grants":
            columns.append("base_snapshot_id")
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    # ORM guards are not sufficient: bulk SQL must not silently rewrite history.
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("""CREATE FUNCTION prevent_autocorrection_history_change() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'autocorrection_history_is_append_only'; END; $$""")
        for table in TABLES:
            op.execute(
                f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION prevent_autocorrection_history_change()"
            )
    elif dialect == "sqlite":
        for table in TABLES:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'autocorrection_history_is_append_only'); END"
                )
    else:
        raise RuntimeError("unsupported_autocorrection_database")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION prevent_autocorrection_history_change()")
