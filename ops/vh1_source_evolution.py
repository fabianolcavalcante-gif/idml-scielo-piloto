"""Accept a superseded source only through an independently pinned successor proof."""

import hashlib
import json


def source_matches(path, expected, reader):
    current = hashlib.sha256(reader(path)).hexdigest()
    if current == expected:
        return True
    from ops.gate_vh1_journal_metadata import source_matches as journal_source_matches

    if journal_source_matches(path, expected, reader):
        return True
    # The newest gate checks current bytes directly (never through this helper),
    # so traversing the historical chain cannot recursively qualify itself.
    from ops.gate_vh1_final_validation import PREVIOUS as final_previous
    from ops.gate_vh1_final_validation import REPORT as final_report
    from ops.gate_vh1_final_validation import ROOT as final_root
    from ops.gate_vh1_final_validation import evaluate as final_evaluate

    try:
        report = json.loads(reader(final_report.relative_to(final_root).as_posix()))
        previous = json.loads(reader(final_previous.relative_to(final_root).as_posix()))
        plan = report["qualification"]
        if (
            plan["before_source_sha256"].get(path) == expected
            and plan["source_sha256"].get(path) == current
            and final_evaluate(report, previous, reader)["passed"]
        ):
            return True
    except (KeyError, ValueError, TypeError, OSError):
        pass
    from ops.gate_vh1_reference_types import PREVIOUS as types_previous
    from ops.gate_vh1_reference_types import REPORT as types_report
    from ops.gate_vh1_reference_types import ROOT as types_root
    from ops.gate_vh1_reference_types import evaluate as types_evaluate

    try:
        report = json.loads(reader(types_report.relative_to(types_root).as_posix()))
        previous = json.loads(reader(types_previous.relative_to(types_root).as_posix()))
        plan = report["qualification"]
        if (
            plan["before_source_sha256"].get(path) == expected
            and plan["source_sha256"].get(path) not in (None, expected)
            and source_matches(path, plan["source_sha256"][path], reader)
            and types_evaluate(report, previous, reader)["passed"]
        ):
            return True
    except (KeyError, ValueError, TypeError, OSError):
        pass
    from ops.gate_vh1_reference_metadata import (
        PREVIOUS as metadata_previous,
    )
    from ops.gate_vh1_reference_metadata import (
        REPORT as metadata_report,
    )
    from ops.gate_vh1_reference_metadata import (
        ROOT as metadata_root,
    )
    from ops.gate_vh1_reference_metadata import (
        evaluate as metadata_evaluate,
    )

    try:
        report = json.loads(reader(metadata_report.relative_to(metadata_root).as_posix()))
        previous = json.loads(reader(metadata_previous.relative_to(metadata_root).as_posix()))
        plan = report["qualification"]
        if (
            plan["before_source_sha256"].get(path) == expected
            and plan["source_sha256"].get(path) not in (None, expected)
            and source_matches(path, plan["source_sha256"][path], reader)
            and metadata_evaluate(report, previous, reader)["passed"]
        ):
            return True
    except (KeyError, ValueError, TypeError, OSError):
        pass
    if path != "src/idml_foundation/pipeline/canonical_mapper.py":
        return False
    # The original native report remains immutable. A newer native run plus an
    # exact whole-XML delta, not a hash allowlist alone, qualifies this transition.
    from ops.gate_vh1_references import PREVIOUS, REPORT, ROOT, evaluate

    try:
        report = json.loads(reader(REPORT.relative_to(ROOT).as_posix()))
        previous = json.loads(reader(PREVIOUS.relative_to(ROOT).as_posix()))
        plan = report["qualification"]
        return (
            plan["before_source_sha256"][path] == expected
            and source_matches(path, plan["source_sha256"][path], reader)
            and evaluate(report, previous, reader)["passed"]
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False
