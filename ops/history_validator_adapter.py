"""Lab candidate entrypoint: scoped authorities plus documented history policy."""

import contextlib
import io
import json
from pathlib import Path

import packtools
import scoped_validator_adapter
from history_compat import history_parameters, verify_native_config
from packtools.sps.validation import xml_validations


def main():
    rules = Path(packtools.__file__).parent / "sps/validation_rules/history_dates_rules.json"
    verify_native_config(rules.read_bytes())
    stdout = io.StringIO()
    with history_parameters(xml_validations) as evidence, contextlib.redirect_stdout(stdout):
        scoped_validator_adapter.main()
    if not evidence["invocations"]:
        raise ValueError("history_validation_not_executed")
    result = json.loads(stdout.getvalue())
    evidence["candidate_sha256"] = result["candidate_sha256"]
    result["result"]["history_policy_evidence"] = evidence
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
