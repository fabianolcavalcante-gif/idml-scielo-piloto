"""Candidate Packtools wrapper, authority files mounted by the trusted broker only."""

import sys
from pathlib import Path

import packtools_pinned_adapter as adapter
from affiliation_compat import install
from doi_authority_runtime import authority_lookup
from doi_model_compat import install as install_doi_model
from packtools.sps.validation import utils

if __name__ == "__main__":
    install()
    install_doi_model()
    if len(sys.argv) != 2 or Path(sys.argv[1]).stat().st_size > 100 * 1024**2:
        raise ValueError("invalid_candidate")
    with authority_lookup(utils, Path(sys.argv[1]).read_bytes(), Path("/authority")):
        raise SystemExit(adapter.main())
