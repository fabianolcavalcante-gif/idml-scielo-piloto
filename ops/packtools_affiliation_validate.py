"""Pinned qualification wrapper, not the active Packtools adapter."""

import packtools_pinned_adapter as adapter
from affiliation_compat import install

if __name__ == "__main__":
    install()
    raise SystemExit(adapter.main())
