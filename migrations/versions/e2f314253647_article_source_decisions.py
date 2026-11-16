"""Append-only administrative public source decisions; no implicit grants."""

import sqlalchemy as sa
from alembic import op

revision = "e2f314253647"
down_revision = "d1f203142536"
branch_labels = None
depends_on = None


def upgrade():
    name = "article_source_decisions"
    op.create_table(
        name,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "request_id", name="uq_source_decision_request"),
        sa.UniqueConstraint("resource_id", "sequence", name="uq_source_decision_sequence"),
    )
    for column in ("organization_id", "resource_id"):
        op.create_index(f"ix_{name}_{column}", name, [column])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            f"CREATE TRIGGER immutable_{name} BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_autocorrection_history_change()"
        )
    elif op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER immutable_{name}_{action} BEFORE {action} ON {name} "
                "BEGIN SELECT RAISE(ABORT, 'source_decisions_are_append_only'); END"
            )
    else:
        raise RuntimeError("unsupported_source_decision_database")


def downgrade():
    op.drop_table("article_source_decisions")
