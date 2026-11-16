"""Audit private XPM online evidence without granting XML approval or hiding findings."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from idml_foundation.release.xpm import XpmReportParser
from ops.qualify_vh1_xpm_linux import PACKAGES, checked_members, digest, mutate
from ops.run_xpm_qualification import ARCHIVE_SHA256
from ops.summarize_vh1_xpm_linux import BASELINE, REPO, negative_detected, visible_text

MATRIX = {
    ("esa-e20240086", "baseline"),
    ("esa-e20240135", "baseline"),
    ("esa-e20240086", "missing_graphic"),
}
SOURCES = (
    "deploy/Dockerfile.xpm-online-qualification",
    "ops/xpm_egress_proxy.py",
    "ops/run_xpm_online_qualification.py",
    "ops/qualify_vh1_xpm_online.py",
    "ops/qualify_vh1_xpm_linux.py",
    "ops/run_xpm_qualification.py",
    "ops/summarize_vh1_xpm_linux.py",
    "ops/audit_vh1_xpm_online.py",
    "tests/test_xpm_egress_proxy.py",
    "tests/test_vh1_xpm_online.py",
    "src/idml_foundation/release/xpm.py",
)


def sealed(path, expected):
    if path.is_symlink() or digest(path) != expected:
        raise ValueError("evidence_hash_mismatch")
    return path.read_bytes()


def xml_root(data):
    # The known candidate contains a public DOCTYPE, but it must never be fetched.
    if len(data) > 8 * 1024**2 or b"<!ENTITY" in data.upper():
        raise ValueError("unsafe_xml")
    root = etree.fromstring(
        data,
        parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
    )
    if root.tag != "article" or any(isinstance(n, etree._Entity) for n in root.iter()):
        raise ValueError("unsafe_xml")
    return root


def catalogue_comparison(xml, catalogue):
    """Exact authoritative comparison, not an accent-folding heuristic or automatic patch."""
    root = xml_root(xml)
    journal = root.findall("front/journal-meta")
    if len(journal) != 1:
        raise ValueError("journal_not_unique")
    journal = journal[0]

    def one(path):
        nodes = journal.findall(path)
        if len(nodes) != 1 or not (nodes[0].text or "").strip():
            raise ValueError("journal_field_not_unique")
        return nodes[0].text.strip()

    print_issn = one("issn[@pub-type='ppub']")
    online_issn = one("issn[@pub-type='epub']")
    acronym = one("journal-id[@journal-id-type='publisher-id']")
    rows = list(csv.reader(io.StringIO(catalogue.decode("utf-8-sig")), delimiter="\t"))
    matches = [
        row
        for row in rows
        if len(row) >= 12
        and row[0] == "scl"
        and row[2:4] == [print_issn, online_issn]
        and row[5] == acronym
    ]
    if len(matches) != 1:
        raise ValueError("catalogue_match_not_unique")
    row = matches[0]
    paths = {
        "journal_title": ("journal-title-group/journal-title", 7),
        "publisher_name": ("publisher/publisher-name", 9),
    }
    findings = {}
    for field, (path, index) in paths.items():
        candidate, expected = one(path), row[index].strip()
        if not expected:
            raise ValueError("catalogue_field_empty")
        findings[field] = {
            "matches": candidate == expected,
            "candidate_value_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
            "catalogue_value_sha256": hashlib.sha256(expected.encode()).hexdigest(),
        }
    return findings


def transport_evidence(events, catalogue_sha256):
    catalogues = [e for e in events if e["event"] == "catalogue_https_response"]
    if len(catalogues) != 3 or any(
        e["status"] != 200 or e["sha256"] != catalogue_sha256 or e["bytes"] <= 0 for e in catalogues
    ):
        raise ValueError("catalogue_transport_unproven")
    tunnels = [e for e in events if e["event"] == "tls_tunnel"]
    hosts = {e["host"] for e in tunnels}
    if hosts != {"api.crossref.org", "orcid.org"}:
        raise ValueError("tls_authorities_unproven")
    return {
        "catalogue_https_responses": len(catalogues),
        "tls_tunnels_by_authority": dict(Counter(e["host"] for e in tunnels)),
        "tls_outcomes": dict(Counter(e["result"] for e in tunnels)),
        "denied_http_authorities": dict(
            Counter(
                e.get("authority", "unclassified")
                for e in events
                if e["event"] == "denied" and e["reason"] == "catalogue_url_denied"
            )
        ),
        "catalogue_last_modified": sorted({e["last_modified"] for e in catalogues}),
        # CONNECT does not reveal HTTP status or prove DOI/ORCID semantics.
        "all_external_queries_completed": False,
        "authenticated_orcid_ownership_proven": False,
    }


def audit(directory):
    raw = json.loads((directory / "report.json").read_bytes())
    if len(raw["cases"]) != 3 or {(c["article"], c["mutation"]) for c in raw["cases"]} != MATRIX:
        raise ValueError("case_matrix_mismatch")
    if (
        not raw["services_unchanged"]
        or raw["before"] != raw["after"]
        or raw["after"]["readiness"]["status"] != "ok"
        or raw["boundary_denials"] != [True, True, True]
        or raw["release_approved"]
        or raw["production_deployed"]
        or raw["sps_1_10_compatibility_proven"]
    ):
        raise ValueError("unsafe_or_approving_run")
    expected_host_sources = {
        name: digest(REPO / "ops" / name)
        for name in ("qualify_vh1_xpm_online.py", "qualify_vh1_xpm_linux.py")
    }
    if raw["host_sources_sha256"] != expected_host_sources:
        raise ValueError("host_source_mismatch")
    events = [
        json.loads(line)
        for line in sealed(
            directory / "proxy/events.jsonl", raw["proxy_events_sha256"]
        ).splitlines()
    ]
    catalogue = (directory / "proxy/catalogue.csv").read_bytes()
    catalogue_sha256 = hashlib.sha256(catalogue).hexdigest()
    transport = transport_evidence(events, catalogue_sha256)
    cases, texts, results = [], {}, {}
    for case in raw["cases"]:
        article, mutation = case["article"], case["mutation"]
        folder = directory / (article + "-" + mutation)
        work = folder / "work"
        execution = json.loads(sealed(work / "execution.json", case["execution_sha256"]))
        if execution != case["execution"]:
            raise ValueError("execution_evidence_mismatch")
        if (
            case["actual_image"] != raw["image"]
            or case["actual_network"] != "idml-xpm-net-" + raw["run_id"].lower()
            or case["docker_exit_code"] != 0
            or case["oom_killed"]
            or execution["returncode"] != 0
            or execution["timed_out"]
            or execution["network"] != "internal_bridge_via_allowlisted_proxy"
            or not execution["input_unchanged"]
            or not execution["vendor_files_unchanged"]
            or execution["archive_sha256"] != ARCHIVE_SHA256
            or execution["runner_sha256"] != digest(REPO / "ops/run_xpm_online_qualification.py")
            or execution["proxy_source_sha256"] != digest(REPO / "ops/xpm_egress_proxy.py")
            or execution["catalogue_sha256"] != catalogue_sha256
            or execution["catalogue_bytes"] != len(catalogue)
            or any(
                execution[key]
                for key in (
                    "release_approved",
                    "sps_1_10_compatibility_proven",
                    "authenticated_orcid_ownership_proven",
                )
            )
        ):
            raise ValueError("unqualified_execution")
        candidate = BASELINE / article / "candidate.zip"
        if (
            digest(candidate) != PACKAGES[article]
            or case["original_package_sha256"] != PACKAGES[article]
        ):
            raise ValueError("baseline_binding_mismatch")
        with ZipFile(candidate) as archive:
            members = mutate(checked_members(archive), mutation)
        expected = {n: hashlib.sha256(data).hexdigest() for n, data in members.items()}
        if execution["input_manifest"] != expected:
            raise ValueError("input_manifest_mismatch")
        identity = (
            PACKAGES[article]
            if mutation == "baseline"
            else hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()
        )
        if list(execution["reports"]) != ["input_xpm/errors/xpm.html"]:
            raise ValueError("unexpected_reports")
        native = execution["reports"]["input_xpm/errors/xpm.html"]
        report = sealed(work / "input_xpm/errors/xpm.html", native["sha256"])
        result = XpmReportParser().parse(
            report, candidate_package_sha256=identity, tool_sha256=ARCHIVE_SHA256
        )
        totals = {
            k: getattr(result, k) for k in ("blocking_errors", "fatal_errors", "errors", "warnings")
        }
        if (
            native["totals"] != {k: [v] for k, v in totals.items()}
            or len(report) != native["bytes"]
        ):
            raise ValueError("totals_mismatch")
        for stream in ("stdout", "stderr"):
            sealed(work / (stream + ".log"), execution[stream + "_sha256"])
        xml_name = next(n for n in members if n.endswith(".xml"))
        original = sealed(folder / "input" / xml_name, expected[xml_name])
        generated = sealed(
            work / "input_xpm/scielo_package" / xml_name,
            execution["generated_package_manifest"][xml_name],
        )
        texts[(article, mutation)], results[(article, mutation)] = visible_text(report), result
        cases.append(
            {
                "article": article,
                "mutation": mutation,
                "input_identity_sha256": identity,
                "report_sha256": result.report_sha256,
                "counts": totals,
                "parser_errors": result.parser_errors,
                "elapsed_seconds": execution["elapsed_seconds"],
                "child_max_rss_kib": execution["child_max_rss_kib"],
                "catalogue_comparison": catalogue_comparison(original, catalogue),
                "generated_xml_differs": original != generated,
                "generated_doctype_unchanged": (
                    xml_root(original).getroottree().docinfo.doctype
                    == xml_root(generated).getroottree().docinfo.doctype
                ),
                "input_and_vendor_unchanged": True,
                "execution_completed": True,
                "validation_approved": False,
            }
        )
    key = ("esa-e20240086", "missing_graphic")
    if not negative_detected(key[1], texts[key], texts[(key[0], "baseline")], results[key]):
        raise ValueError("negative_control_not_detected")
    return {
        "version": "vh1-xpm-online-public-1.0",
        "run_id": raw["run_id"],
        "private_report_sha256": digest(directory / "report.json"),
        "proxy_events_sha256": raw["proxy_events_sha256"],
        "image": raw["image"],
        "archive_sha256": ARCHIVE_SHA256,
        "source_sha256": {name: digest(REPO / name) for name in SOURCES},
        "catalogue_sha256": catalogue_sha256,
        "catalogue_bytes": len(catalogue),
        "transport": transport,
        "cases": cases,
        "negative_control_detected": True,
        "boundary_denials": 3,
        "services_unchanged": True,
        "observed_service_count": len(raw["before"]["services"]),
        "sps_1_10_compatibility_proven": False,
        "release_approved": False,
        "production_deployed": False,
        "outstanding": [
            "JOURNAL_CATALOGUE_METADATA_CORRECTIONS",
            "SPS_1_10_JATS_1_3_DELIVERY_POLICY",
            "LEGACY_DOI_FALSE_POSITIVES",
            "WAYTA_QUERY_DENIED",
            "SUPERVISED_WEB_INTEGRATION_AND_HARDENING",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"evidence_verified": True, "release_approved": False}))
