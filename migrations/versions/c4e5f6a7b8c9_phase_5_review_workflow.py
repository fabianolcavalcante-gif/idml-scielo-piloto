"""phase 5 review workflow, MFA and editorial approvals

Revision ID: c4e5f6a7b8c9
Revises: 8af62bb716cf
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e5f6a7b8c9"
down_revision: str | None = "8af62bb716cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_secret_ciphertext", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("mfa_last_counter", sa.BigInteger()))
    op.add_column(
        "users",
        sa.Column("mfa_recovery_codes", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )
    op.add_column(
        "session_tokens",
        sa.Column(
            "authenticated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "session_tokens", sa.Column("mfa_verified_at", sa.DateTime(timezone=True))
    )

    op.create_table(
        "review_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("base_snapshot_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("rule_code", sa.String(200), nullable=False),
        sa.Column("field_path", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("assigned_user_id", sa.String(36)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["base_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_review_org_state_created", "review_items", ["organization_id", "state", "created_at"])
    op.create_index("ix_review_resource_state", "review_items", ["resource_id", "state"])

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("review_item_id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("base_snapshot_id", sa.String(36), nullable=False),
        sa.Column("result_snapshot_id", sa.String(36)),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("patch", sa.JSON(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("patch_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["result_snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_review_decision_item_created", "review_decisions", ["review_item_id", "created_at"])

    op.create_table(
        "review_builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("review_decision_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("xml_sha256", sa.String(64), nullable=False),
        sa.Column("xml_content", sa.Text(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("validation_valid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["review_decision_id"], ["review_decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("review_decision_id", name="uq_review_build_decision"),
    )
    op.create_index("ix_review_build_org_created", "review_builds", ["organization_id", "created_at"])

    op.create_table(
        "release_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["domain_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "package_sha256", name="uq_release_org_package"),
    )
    op.create_index("ix_release_org_state_created", "release_requests", ["organization_id", "state", "created_at"])

    op.create_table(
        "release_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("release_request_id", sa.String(36), nullable=False),
        sa.Column("approver_user_id", sa.String(36), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["release_request_id"], ["release_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("release_request_id", "approver_user_id", name="uq_release_approval_user"),
    )


def downgrade() -> None:
    op.drop_table("release_approvals")
    op.drop_index("ix_release_org_state_created", table_name="release_requests")
    op.drop_table("release_requests")
    op.drop_index("ix_review_build_org_created", table_name="review_builds")
    op.drop_table("review_builds")
    op.drop_index("ix_review_decision_item_created", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_review_resource_state", table_name="review_items")
    op.drop_index("ix_review_org_state_created", table_name="review_items")
    op.drop_table("review_items")
    op.drop_column("session_tokens", "mfa_verified_at")
    op.drop_column("session_tokens", "authenticated_at")
    op.drop_column("users", "mfa_recovery_codes")
    op.drop_column("users", "mfa_last_counter")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_secret_ciphertext")
