"""Opt-in v1.1 broker. Legacy service remains untouched; one scoped execution at a time."""

import copy
import json

try:
    from ops import validator_broker as legacy
    from ops.scoped_authority_transport import load_selection, mount_selection, stage_selection
except ModuleNotFoundError:
    import validator_broker as legacy
    from scoped_authority_transport import load_selection, mount_selection, stage_selection

try:
    from idml_foundation.services.validation_scope import validate_scope
except ModuleNotFoundError:
    from validation_scope import validate_scope

LEGACY_SELECT = legacy.select_spec
LEGACY_EXECUTE = legacy.execute
LEGACY_ARGUMENTS = legacy.create_arguments


def select_spec(registry, request):
    if request.get("version") != "local-validator-1.1" or "scope" not in request:
        raise ValueError("scoped_request_required")
    scope = validate_scope(request["scope"])
    base = {key: value for key, value in request.items() if key != "scope"}
    base["version"] = "local-validator-1.0"
    spec = copy.deepcopy(LEGACY_SELECT(registry, base))
    root = registry.get("authority_root")
    if not isinstance(root, str) or not root or "doi_authority" in spec:
        raise ValueError("scoped_registry_invalid")
    expected = scope["xml_sha256" if spec["name"] == "packtools" else "package_sha256"]
    if request["candidate_sha256"] != expected:
        raise ValueError("scoped_authority_candidate_mismatch")
    return {
        **spec,
        "_authority_root": root,
        "_scope": scope,
        "_runtime_authorization": registry.get("runtime_article_authorization") is True,
    }


def execute(spec, candidate, work):
    approved = None
    if spec.get("_runtime_authorization"):
        from ops.runtime_source_authority import prepare

        approved = prepare(spec["_authority_root"], spec["_scope"], candidate, spec["name"])
    folder, binding = stage_selection(
        spec["_authority_root"], spec["_scope"], candidate, spec["name"]
    )

    def arguments(selected, target):
        return mount_selection(LEGACY_ARGUMENTS(selected, target), folder)

    previous = legacy.create_arguments
    legacy.create_arguments = arguments
    try:
        output = LEGACY_EXECUTE(spec, candidate, work)
    finally:
        legacy.create_arguments = previous
    # Re-read current grant after native validation: revocation/expiry must suppress
    # publication even if it happened during an expensive validator execution.
    _, current = load_selection(spec["_authority_root"], spec["_scope"])
    if current != binding:
        raise ValueError("scoped_authority_changed_during_execution")
    if approved is not None:
        from ops.runtime_source_authority import decision

        if decision(spec["_scope"]) != approved:
            raise ValueError("article_source_consent_changed_during_execution")
    envelope = json.loads(output)
    if envelope["result"].get("authority_evidence", {}).get("binding") != binding:
        raise ValueError("scoped_authority_response_mismatch")
    return output


def main():
    legacy.select_spec, legacy.execute = select_spec, execute
    legacy.main()


if __name__ == "__main__":
    main()
