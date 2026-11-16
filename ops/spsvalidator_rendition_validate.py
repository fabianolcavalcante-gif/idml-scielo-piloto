"""Qualification-only entry point; retains the pinned adapter output contract."""

import spsvalidator_pinned_adapter as adapter
from sps_rendition_compat import validate_package


def main():
    adapter.validate_sps_zip = validate_package
    return adapter.main()


if __name__ == "__main__":
    raise SystemExit(main())
