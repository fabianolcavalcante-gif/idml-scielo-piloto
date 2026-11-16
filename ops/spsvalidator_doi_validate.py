"""Candidate SPS wrapper: package and XML authority binding before native validation."""

import sys
from pathlib import Path

import spsvalidator_pinned_adapter as adapter
from affiliation_compat import install
from doi_authority_runtime import authority_lookup
from doi_model_compat import install as install_doi_model
from packtools.sps.validation import utils
from sps_rendition_compat import validate_package

if __name__ == "__main__":
    install()
    install_doi_model()
    if len(sys.argv) != 2 or Path(sys.argv[1]).stat().st_size > 100 * 1024**2:
        raise ValueError("invalid_candidate")
    adapter.validate_sps_zip = validate_package
    with authority_lookup(utils, b"", Path("/authority"), package=Path(sys.argv[1]).read_bytes()):
        raise SystemExit(adapter.main())
