"""phase 6 assistive agent runs and proposals

Revision ID: d5f6a7b8c9d0
Revises: c4e5f6a7b8c9
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f6a7b8c9d0"
down_revision: str | None = "c4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("review_item_id", sa.String(36), nullable=False),
        sa.Column("base_snapshot_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("orchestrator", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("output_schema_version", sa.String(80), nullable=False),
        sa.Column("config_version", sa.String(80), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("output_sha256", sa.String(64)),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_agent_run_org_idempotency"
        ),
    )
    op.create_index("ix_agent_run_org_created", "agent_runs", ["organization_id", "created_at"])
    op.create_index("ix_agent_run_review_created", "agent_runs", ["review_item_id", "created_at"])

    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("agent_run_id", sa.String(36), nullable=False),
        sa.Column("review_item_id", sa.String(36), nullable=False),
        sa.Column("base_snapshot_id", sa.String(36), nullable=False),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("patch", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("needs_human", sa.Boolean(), nullable=False),
        sa.Column("proposal_sha256", sa.String(64), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("agent_run_id", name="uq_agent_proposal_run"),
    )
    op.create_index(
        "ix_agent_proposal_org_created", "agent_proposals", ["organization_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_proposal_org_created", table_name="agent_proposals")
    op.drop_table("agent_proposals")
    op.drop_index("ix_agent_run_review_created", table_name="agent_runs")
    op.drop_index("ix_agent_run_org_created", table_name="agent_runs")
    op.drop_table("agent_runs")
