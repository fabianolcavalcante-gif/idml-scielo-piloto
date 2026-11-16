"""Freeze the new source; never replace the previous release archive."""

from ops import build_vh09_source

if __name__ == "__main__":
    build_vh09_source.RELEASE = "vh09-heads-20261021-v1"
    build_vh09_source.main()
