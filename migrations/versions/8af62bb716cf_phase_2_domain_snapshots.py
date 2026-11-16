"""phase 2 domain snapshots

Revision ID: 8af62bb716cf
Revises: 055fc21c9963
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8af62bb716cf"
down_revision: str | Sequence[str] | None = "055fc21c9963"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "domain_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("source_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("parent_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("model_kind", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["parent_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_id",
            "model_kind",
            "revision",
            name="uq_snapshot_resource_kind_revision",
        ),
        sa.UniqueConstraint(
            "resource_id",
            "model_kind",
            "content_sha256",
            name="uq_snapshot_resource_kind_content",
        ),
    )
    op.create_index(
        "ix_snapshot_org_kind_created",
        "domain_snapshots",
        ["organization_id", "model_kind", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_org_kind_created", table_name="domain_snapshots")
    op.drop_table("domain_snapshots")
