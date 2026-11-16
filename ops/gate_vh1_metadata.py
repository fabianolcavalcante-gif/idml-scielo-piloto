"""Accept only the exact qualified correction and no new native findings; not G-HOMOLOG."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from idml_foundation.release.institution_locations import SOURCES as LOCATION_SOURCES
from ops.gate_vh1_doctype import code_matches
from ops.gate_vh1_editorial import CASES, PACKAGES
from ops.qualify_vh1_metadata import CHANGED, CODE
from ops.vh1_source_evolution import source_matches

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "benchmarks/qualification/reports"
FINAL = {
    "esa-e20240086": (
        "e96ce02848de0c7d5dddd4056a36595db27ca3d66c34bebd5feb3bbf46082eb6",
        "2d4d8f6e1c6d0731a2be0f54fc3b5ab703590e126b1b069f0efd5f987722e33a",
    ),
    "esa-e20240135": (
        "9ff50bc3ae960c16fea624c71482e8aedd7c616f9e36e2fb1a82fdf5f79b0590",
        "793956107ec688fb529fc83340d1dc3b3da5fe517e13558db7aa781b4e03b1a3",
    ),
}
LOCATION_PROOF = {
    "esa-e20240086": (
        "660d3b56cf7fe785585c46eaf056fbb09a3c715bab6dac7c80a68990b3bd380b",
        "fcdd41b732bafd82571fc5d9e7f71ff02c5df66fabd93371fe9ad335a7990a66",
        "45c05b9c4fb900aaf017bdf13774e3eb2d15b7bfa91f5b18d442ff04958444da",
        {
            "tokyo_department": "0316918e0137da0ef9f3fb2155b1ba126c665137159dc8d160dbd9e4bb060754",
            "tokyo_government": "0ee75478c9e37205158768bb36db2f366187d3b9c76589db4e023789dbeabf2b",
        },
    ),
    "esa-e20240135": (
        "2685074388bc75b5f6b73516fa13d42c32618ee261c02cc1d83f7feaadc7d37f",
        "814a7e121339706f3dc4f368c4db8d65526521f92d6ef26273c419a52caa3773",
        "ebbca5ee2213774de3912f164e0019b451c493ac4e585ad78df914dd2106e3f2",
        {
            "cahcet": "f723852057667f8467ac985bece46d913473db7eaec9ef55f53b7b43ba783925",
            "easwari": "328bb585ce497652fb740d4e40865b3d0b435860ce1bdeb83b2542592272cbe5",
            "syed_hameedha": "7b7ba2be9d2c56ba789e259a84b2a18d1073ab543c5599327af304ef2d55eba4",
            "tindivanam": "7c75a435bdb44cfdb938f65293d8f8c2957e801b57d9acbb654f44ae21c6b6a4",
        },
    ),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate(report, before, registry_bytes, reader, previous):
    checks = {}
    try:
        plan = report["qualification"]
        tools = {
            v["name"]: v
            for v in json.loads(registry_bytes)["validators"]
            if v["channel"] == "active"
        }
        checks["not_release"] = all(
            value is False
            for value in (
                report["active_application_changed"],
                report["formal_xml_approved"],
                plan["active_application_changed"],
                plan["formal_xml_approved"],
                plan["gold_read"],
                plan["catalog_values_changed"],
            )
        )
        checks["current_source"] = set(plan["source_sha256"]) == set(CHANGED) and all(
            source_matches(p, h, reader) for p, h in plan["source_sha256"].items()
        )
        checks["current_runner"] = code_matches(plan["code_sha256"], CODE, reader)
        checks["registry"] = plan["registry_sha256"] == sha(registry_bytes)
        checks["cases"] = len(report["cases"]) == 2 and {
            row["case"] for row in report["cases"]
        } == set(plan["cases"]) == set(FINAL)
        for case in report["cases"]:
            name = case["case"]
            metadata = plan["cases"][name]
            original = next(row for row in before["cases"] if row["case"] == name)
            first = name == "esa-e20240086"
            expected_counts = (
                {"critical": 2, "error": 3, "warning": 9}
                if first
                else {"critical": 2, "warning": 5}
            )
            checks[name + "/conversion"] = (
                metadata["offline_valid"] is True
                and metadata["deterministic"] is True
                and metadata["before_xml_sha256"] == CASES[name][0]
                and metadata["before_package_sha256"] == PACKAGES[name]
                and (metadata["xml_sha256"], metadata["package_sha256"]) == FINAL[name]
                and metadata["delta"]
                == {
                    "states_extracted": 2 if first else 0,
                    "credit_roles_normalized": 3 if first else 0,
                    "publication_year_added": 0,
                    **({"funding_structure_deferred": 1} if first else {}),
                    **({"articlemeta_date_fields": 3} if first else {}),
                    **({"verified_author_orcids": 3} if first else {}),
                    "verified_institution_states": 1 if first else 4,
                    **({"verified_funding_pairs": 1} if first else {}),
                }
                and metadata["funding_structure_review_required"] is False
            )
            funding = metadata["verified_funding"]
            checks[name + "/funding_source"] = (
                funding["applied"] is first
                and funding["human_review_required"] is True
                and funding["other_funders_preserved_in_statement"] is first
                and funding["catalog_id"]
                == (
                    "1f07771d45d2e452a07e8a658dcc4367c1020b999b99074166137eaba9d49be4"
                    if first
                    else None
                )
                and (
                    not first
                    or (
                        funding["source"]["sha256"]
                        == metadata["files"]["embrapa-funding.pdf"]
                        == "27beb38146ab3755bca3e02f8afb38abfdd3cf28c156fe7fbf475e3e888617be"
                        and funding["source"]["url"]
                        == (
                            "https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147178/1/"
                            "P-Uso-do-jardim-aquicola-no-tratamento-e-reuso-da-agua-de-piscicultura.pdf"
                        )
                        and metadata["files"]["verified_funding_catalog.json"]
                        == "f97f8dc65e68fda109fb303a50ecae5eb810c43360d66ecb5d31dbf593956843"
                    )
                )
                and (first or funding["source"] is None)
            )
            dates = metadata["articlemeta_dates"]
            snapshot = "2a752569032271a8565e3cb9885f150970e6e73f99b7367768c3a98621c679ed"
            catalog = "f57533610786b92c9df93046c6fec7601b367d5dcf29499db4e42fbe65b2f154"
            checks[name + "/dates"] = (
                dates["applied"] is first
                and dates["human_review_required"] is True
                and dates["catalog_id"] == (catalog if first else None)
                and dates["snapshot_sha256"] == (snapshot if first else None)
                and (
                    not first
                    or (
                        metadata["files"]["articlemeta.json"] == snapshot
                        and metadata["files"]["articlemeta_date_catalog.json"]
                        == "fb1908069a2511eb7ac0b24aff3353de34080e6f4e767bb310812589155e3ee6"
                        and dates["source_idml_sha256"]
                        == "8ce185f5dd03f5403a36ca7b60d9d708b95e2b334e731327dd0b568b0cd44d2c"
                    )
                )
            )
            orcids = metadata["articlemeta_orcids"]
            expected_people = (
                {
                    "0000-0003-1136-7986": (
                        "36109949ff7b73425b30f4bc29600beabaa5ddf1d1f613b97856143bd74fce6c"
                    ),
                    "0000-0002-3963-5973": (
                        "e81c0ed401ba8a09569816458ec3de4ab432893a0effb6483545e121a16a2324"
                    ),
                    "0000-0002-0839-9947": (
                        "8e88176120496aa1a9293abf3cd2940f607e382f5dee6e96113176e637a6f26b"
                    ),
                }
                if first
                else {}
            )
            checks[name + "/orcid_sources"] = (
                orcids["applied"] is first
                and orcids["human_review_required"] is True
                and orcids["authenticated_ownership_claimed"] is False
                and orcids["catalog_id"]
                == (
                    "c3da55a773e7309c6e3331978ec07875be450d1505eb612aa45fb9844d05f8b5"
                    if first
                    else None
                )
                and orcids["evidence_sha256"]
                == (
                    "e8b2f879e9bc0a56dfc70b99b1ac20ed9b2bc4cebd155d398acbfc03e9e4d788"
                    if first
                    else None
                )
                and set(orcids["persons"]) == set(expected_people)
                and all(
                    orcids["persons"][key]["sha256"] == value
                    and orcids["persons"][key]["url"] == f"https://pub.orcid.org/v3.0/{key}/person"
                    and orcids["persons"][key]["status"] == "available"
                    and metadata["files"][f"incoming/{key}.json"] == value
                    for key, value in expected_people.items()
                )
                and (
                    not first
                    or metadata["files"]["articlemeta_orcid_catalog.json"]
                    == "c03ca7db99861d4076872d3a5c1957c9e1ecdbef71e43334fef69624416c117c"
                )
            )
            locations = metadata["institution_locations"]
            location_id, location_file, location_evidence, location_sources = LOCATION_PROOF[name]
            checks[name + "/location_sources"] = (
                locations["applied"] is True
                and locations["human_review_required"] is True
                and locations["catalog_id"] == location_id
                and locations["evidence_sha256"] == location_evidence
                and metadata["files"]["institution_location_catalog.json"] == location_file
                and set(locations["sources"]) == set(location_sources)
                and all(
                    locations["sources"][key]["sha256"] == digest
                    and metadata["files"][key + ".html"] == digest
                    and locations["sources"][key]["url"] == LOCATION_SOURCES[key].url
                    for key, digest in location_sources.items()
                )
            )
            runs = case["validators"]
            checks[name + "/tools"] = len(runs) == 2 and {r["name"] for r in runs} == set(tools)
            for run in runs:
                tool = run["name"]
                prefix = name + "/" + tool
                old = original["validators"][tool]["result"]["findings"]
                prior_case = next(row for row in previous["cases"] if row["case"] == name)
                prior_run = next(row for row in prior_case["validators"] if row["name"] == tool)
                new = run["findings"]
                old_counts = Counter((r["code"], r["response"]) for r in old)
                prior_counts = Counter((r["code"], r["response"]) for r in prior_run["findings"])
                new_counts = Counter((r["code"], r["response"]) for r in new)
                evidence = run["authority_evidence"]
                checks[prefix + "/native"] = (
                    run["image_id"] == tools[tool]["image_id"]
                    and run["candidate_sha256"] == FINAL[name][0 if tool == "packtools" else 1]
                    and run["counts"]
                    == dict(Counter(r["response"] for r in new))
                    == expected_counts
                    and not (new_counts - old_counts)
                    and not (new_counts - prior_counts)
                )
                checks[prefix + "/authority"] = (
                    evidence["version"] == "scoped-authority-evidence-1.0"
                    and evidence["binding"]
                    == {
                        "scope_sha256": metadata["scope_sha256"],
                        "bundle_sha256": metadata["files"]["incoming/manifest.json"],
                        "grant_sha256": metadata["files"]["grant.json"],
                    }
                    and evidence["checks"]
                    == {
                        "doi": [True],
                        "issue": [True],
                        "section": [True],
                        "orcid": [True] * (3 if first else 4),
                        "orcid_reasons": ["public_record_and_name_match"] * 3
                        if first
                        else ["public_registry_and_crossref_author_match"] * 4,
                    }
                )
    except (KeyError, TypeError, ValueError, StopIteration, OSError):
        checks["complete_evidence"] = False
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "formal_xml_approved": False,
        "scope": ("VH-05 source-bound dates, ORCIDs, states and funding; NOT whole XML approval"),
    }


def main():
    result = evaluate(
        json.loads((REPORTS / "vh1-metadata-linux-v7.json").read_bytes()),
        json.loads((REPORTS / "vh1-editorial-linux-v1.json").read_bytes()),
        (ROOT / "config/validator-registry-vh1-scoped.json").read_bytes(),
        lambda path: (ROOT / path).read_bytes(),
        json.loads((REPORTS / "vh1-metadata-linux-v6.json").read_bytes()),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
