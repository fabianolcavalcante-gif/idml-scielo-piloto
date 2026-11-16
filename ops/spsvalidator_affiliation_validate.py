"""Pinned qualification wrapper retaining the PDF compatibility view."""

import spsvalidator_pinned_adapter as adapter
from affiliation_compat import install
from sps_rendition_compat import validate_package

if __name__ == "__main__":
    install()
    adapter.validate_sps_zip = validate_package
    raise SystemExit(adapter.main())
