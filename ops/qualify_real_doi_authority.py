"""Local real-candidate native validation. No gold reads or authority upload to VPS."""

import hashlib
import json
import logging
import socket
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from lxml import etree
from packtools.sps.validation import article_doi, utils
from packtools.sps.validation.xml_validator import get_validation_results

from ops.affiliation_compat import install
from ops.doi_authority_runtime import authority_lookup
from ops.doi_model_compat import install as install_doi
from ops.doi_package_binding import bound_package_xml
from ops.doi_validation_evidence import observe_registered_doi, registered_doi_evidence
from ops.sps_rendition_compat import validate_package
from ops.validator_adapter_common import sanitize_validator_result

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "esa-e20240086": "7081d302358f8c022114a0ebf568372af43e115bda38a748cc7c2ebbc1494ad0",
    "esa-e20240135": "1757cdb3a15b7fd44beb009e794ff812995eb59cd6e2c1eee2cabee15f9a9706",
}


@contextmanager
def no_network():
    """Local guard only, not an OS/container sandbox. Unavailable rules must still fail."""
    original = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def denied(*args, **kwargs):
        raise OSError("local qualification network disabled")

    socket.getaddrinfo = socket.socket.connect = socket.socket.connect_ex = denied
    try:
        yield
    finally:
        socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = original


def main():
    logging.disable(logging.CRITICAL)
    install()
    install_doi()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "version": "h1-real-doi-local-1.0",
        "executed_at": datetime.now(UTC).isoformat(),
        "scope": "local native validators with Python network guard; not pinned VPS images",
        "runtime_versions": {name: version(name) for name in ("packtools", "spsvalidator")},
        "gold_read": False,
        "xml_changed": False,
        "vps_upload": False,
        "formal_xml_approved": False,
        "cases": [],
    }
    for case, expected in CASES.items():
        source = ROOT / "benchmarks/private/output/h1-country-codes-v1" / case
        xml, package = (
            (source / "candidate.xml").read_bytes(),
            (source / "candidate.zip").read_bytes(),
        )
        if hashlib.sha256(xml).hexdigest() != expected:
            raise ValueError("fixed_candidate_required")
        tree = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
        doi = tree.xpath("string(front/article-meta/article-id[@pub-id-type='doi'])")
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        with urlopen(url, timeout=30) as response:
            if response.url != url:
                raise ValueError("unexpected_authority_redirect")
            snapshot = response.read(10 * 1024**2 + 1)
        manifest = {
            "candidate_sha256": expected,
            "package_sha256": hashlib.sha256(package).hexdigest(),
            "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "authority": "https://api.crossref.org/works/",
        }
        if bound_package_xml(package, manifest) != xml:
            raise ValueError("package_xml_differs")
        folder = ROOT / "benchmarks/private/output/h1-real-doi-local" / run_id / case
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "crossref.json").write_bytes(snapshot)
        row = {"case": case, **manifest, "validators": {}}
        for name in ("packtools", "spsvalidator"):
            with (
                observe_registered_doi(article_doi) as native_outcomes,
                no_network(),
                authority_lookup(
                    utils, xml, folder, package=package if name == "spsvalidator" else None
                ),
            ):
                raw = (
                    list(get_validation_results(tree, {}))
                    if name == "packtools"
                    else validate_package(str(source / "candidate.zip"))
                )
                clean = sanitize_validator_result(raw)
            row["validators"][name] = {
                **clean,
                "reported_doi_evidence": registered_doi_evidence(raw),
                "native_doi_comparisons": len(native_outcomes),
                "native_doi_passed": bool(native_outcomes) and all(native_outcomes),
            }
            print(
                json.dumps({"case": case, "validator": name, "summary": clean["summary"]}),
                flush=True,
            )
        report["cases"].append(row)
    target = ROOT / "benchmarks/qualification/reports" / f"h1-real-doi-local-{run_id}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": target.name, "formal_xml_approved": False}), flush=True)


if __name__ == "__main__":
    main()
