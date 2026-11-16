"""Scoped second VH-09 deployment; no active restoration endpoint or AI cycle."""

from ops import deploy_vh09

if __name__ == "__main__":
    deploy_vh09.NAME = "vh09-heads-20261021-v1"
    deploy_vh09.STAGE = deploy_vh09.ROOT / "releases" / deploy_vh09.NAME
    deploy_vh09.IMAGE = f"idml-foundation:{deploy_vh09.NAME}"
    deploy_vh09.TEST_IMAGE = f"{deploy_vh09.IMAGE}-qualification"
    deploy_vh09.POSTGRES_QUALIFIER = "ops.qualify_vh09_heads_postgres"
    deploy_vh09.EXPECTED_MIGRATION = "c0e1f2031425"
    deploy_vh09.EXTRA_TESTS = ("tests/test_canonical_heads.py", "tests/test_snapshots.py")
    deploy_vh09.main()
