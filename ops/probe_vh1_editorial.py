"""Runs INSIDE pinned Linux validators; emits counts/codes, never source content."""

import copy
import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from affiliation_compat import install
from doi_authority_runtime import authority_lookup
from doi_model_compat import install as install_doi
from doi_package_binding import bound_package_xml
from doi_snapshot import bind_doi_snapshot
from doi_validation_evidence import observe_registered_doi
from editorial_authority import BoundEditorialAuthority, digest, parse_candidate
from editorial_authority_runtime import editorial_parameters
from lxml import etree
from packtools.sps.validation import article_doi, utils, xml_validations
from packtools.sps.validation.xml_validator import get_validation_results
from packtools.sps.validation.xml_validator_rules import get_default_rules
from validator_adapter_common import sanitize_validator_result


def main():
    logging.disable(logging.CRITICAL)
    install()
    install_doi()
    candidate = Path(sys.argv[1])
    package = candidate.read_bytes() if candidate.suffix == ".zip" else None
    if package:
        from sps_rendition_compat import validate_package
    doi_manifest = json.loads(Path("/authority/manifest.json").read_bytes())
    xml = bound_package_xml(package, doi_manifest) if package else candidate.read_bytes()
    folder = Path("/editorial")
    manifest = json.loads((folder / "manifest.json").read_bytes())

    def reader(name):
        path = folder / name
        if path.is_symlink() or not 0 < path.stat().st_size <= 1024**2:
            raise ValueError("editorial_snapshot_budget")
        return path.read_bytes()

    def bind(payload, context):
        # Original candidate/package binding was checked before this point. For
        # negative controls only, rebind the SAME authority to an in-memory mutation.
        crossref = bind_doi_snapshot(
            candidate=payload,
            snapshot=Path("/authority/crossref.json").read_bytes(),
            expected_candidate_sha256=digest(payload),
            expected_snapshot_sha256=doi_manifest["snapshot_sha256"],
            retrieved_at=datetime.fromisoformat(doi_manifest["retrieved_at"]),
            now=datetime.now(UTC),
        )
        return BoundEditorialAuthority(
            payload, context, reader, now=datetime.now(UTC), crossref=crossref
        )

    bound = bind(xml, manifest)
    tree = parse_candidate(xml)
    doi_context = (
        authority_lookup(utils, xml, Path("/authority"), package=package)
        if package
        else authority_lookup(utils, xml, Path("/authority"))
    )
    with (
        observe_registered_doi(article_doi) as doi_evidence,
        doi_context,
        editorial_parameters(xml_validations, bound) as evidence,
    ):
        raw = (
            validate_package(str(candidate)) if package else list(get_validation_results(tree, {}))
        )
        clean = sanitize_validator_result(raw)
    negative = {}
    # Candidate mutations are in memory ONLY and never become a released artifact.
    for kind, xpath in (
        ("issue", "./front/article-meta/volume"),
        ("section", './/article-categories/subj-group[@subj-group-type="heading"]/subject'),
        ("orcid", './/contrib[contrib-id[@contrib-id-type="orcid"]]/name/surname'),
    ):
        mutated = copy.deepcopy(tree)
        nodes = mutated.xpath(xpath)
        if not nodes:
            negative[kind] = {"applicable": False}
            continue
        nodes[0].text = "999" if kind == "issue" else "VH1 negative control"
        payload = etree.tostring(mutated)
        context = copy.deepcopy(manifest)
        context["candidate_sha256"] = digest(payload)
        group = {
            "issue": "validate_bibliographic_strip",
            "section": "validate_article_toc_sections",
            "orcid": "validate_article_contribs",
        }[kind]
        with editorial_parameters(xml_validations, bind(payload, context)) as observed:
            list(getattr(xml_validations, group)(mutated, get_default_rules()))
        negative[kind] = {
            "applicable": True,
            "native_rejected": False in observed[kind],
            "comparisons": len(observed[kind]),
        }
    missing = copy.deepcopy(manifest)
    for source in missing["sources"].values():
        source.update(status="unavailable", sha256=None)
    with editorial_parameters(xml_validations, bind(xml, missing)) as missing_evidence:
        rows = []
        for group in (
            "validate_bibliographic_strip",
            "validate_article_toc_sections",
            "validate_article_contribs",
        ):
            rows.extend(getattr(xml_validations, group)(tree, get_default_rules()))
        unavailable = sanitize_validator_result(rows)
    output = {
        "candidate_sha256": digest(xml),
        "package_sha256": digest(package) if package else None,
        "manifest_sha256": digest((folder / "manifest.json").read_bytes()),
        "runtime_versions": {"packtools": version("packtools")},
        "native_context_evidence": evidence,
        "native_doi_comparisons": len(doi_evidence),
        "native_doi_passed": bool(doi_evidence) and all(doi_evidence),
        "result": clean,
        "negative_controls": negative,
        "unavailable_control": {"native_evidence": missing_evidence, "result": unavailable},
        "xml_unchanged": digest(etree.tostring(tree, method="c14n"))
        == digest(etree.tostring(parse_candidate(xml), method="c14n")),
        "formal_xml_approved": False,
    }
    if package:
        output["runtime_versions"]["spsvalidator"] = version("spsvalidator")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No traceback/raw native advice: may contain article text or public personal data.
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print(
            json.dumps(
                {
                    "probe_error_type": type(error).__name__,
                    "file": Path(frame.filename).name,
                    "line": frame.lineno,
                    "code": str(error)
                    if str(error).startswith("editorial_") and str(error).replace("_", "").isalnum()
                    else "native_probe_failed",
                }
            )
        )
