"""agent run monetary cost provenance

Revision ID: e6a7b8c9d0e1
Revises: d5f6a7b8c9d0
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6a7b8c9d0e1"
down_revision: str | None = "d5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "cost_source",
            sa.String(20),
            nullable=False,
            server_default="unavailable",
        ),
    )
    op.add_column("agent_runs", sa.Column("pricing_version", sa.String(80)))
    op.add_column("agent_runs", sa.Column("pricing_model_key", sa.String(200)))


def downgrade() -> None:
    op.drop_column("agent_runs", "pricing_model_key")
    op.drop_column("agent_runs", "pricing_version")
    op.drop_column("agent_runs", "cost_source")
