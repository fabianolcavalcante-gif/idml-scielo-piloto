"""Runs in a non-root application-image client with NO Docker socket or authority files."""

import json
import sys
from pathlib import Path
from uuid import UUID

from idml_foundation.services.package_validation import assess_package
from idml_foundation.services.scoped_validator_transport import ScopedValidatorExecutor


def main():
    scope = json.loads(Path("/qualification/scope.json").read_bytes())
    mode = sys.argv[1]
    if mode == "foreign-resource":
        scope["resource_id"] = str(UUID("11111111-1111-4111-8111-111111111111"))
    if mode == "foreign-tenant":
        scope["organization_id"] = str(UUID("22222222-2222-4222-8222-222222222222"))
    xml = Path("/qualification/candidate.xml").read_bytes()
    if mode == "changed-xml":
        xml += b"\n"
    result = assess_package(
        xml=xml,
        package=Path("/qualification/candidate.zip").read_bytes(),
        registry_path=Path("/qualification/registry.json"),
        executor=ScopedValidatorExecutor(Path("/connection/broker.sock"), scope=scope),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
