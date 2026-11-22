"""Convert a private corpus with the deterministic pipeline and score it against published XML.

Cases file (JSON list, kept outside Git because it points to private material):
    [{"case": "rbepid-2024375", "idml": "/private/RBEPID_2024375_IN_AOP.idml",
      "published": "/private/2024375.xml", "profile": "profiles/rbepid-aop-1.0.json"}]

The published XML is read only by the scorer, after conversion; it is never given to the
pipeline. Generated XML and a JSON report are written to --out.

Usage: python -m ops.benchmark_corpus --cases cases.json --out DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from idml_foundation.pipeline.bilingual import compose_bilingual, translation_profile
from idml_foundation.pipeline.profile import load_profile
from idml_foundation.pipeline.service import DeterministicPipeline
from ops.benchmark_published_xml import score, summarize


def run_case(case: dict[str, str], out: Path) -> dict[str, object]:
    idml = Path(case["idml"])
    profile = load_profile(Path(case["profile"])) if case.get("profile") else None
    try:
        result = DeterministicPipeline(profile=profile).run(
            idml.read_bytes(), logical_name=idml.name
        )
    except Exception as exc:  # report and continue with the remaining cases
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    xml = result.xml
    if case.get("translation_idml"):
        translation = Path(case["translation_idml"])
        translated_profile = translation_profile(profile or load_profile())
        try:
            translated = DeterministicPipeline(profile=translated_profile).run(
                translation.read_bytes(), logical_name=translation.name
            )
            xml = compose_bilingual(result.xml, translated.xml)
        except Exception as exc:
            return {"error": f"translation {type(exc).__name__}: {exc}"[:300]}
    (out / f"{case['case']}.xml").write_bytes(xml)
    published = Path(case["published"]).read_bytes()
    scores = score(xml, published)
    return {
        "overall": round(summarize(scores), 4),
        "valid": result.validation.valid,
        "issues": len(result.validation.issues),
        "review_reasons": len(result.canonical.review_reasons)
        if hasattr(result.canonical, "review_reasons")
        else None,
        "fields": scores,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = {case["case"]: run_case(case, args.out) for case in cases}
    (args.out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    width = max(len(c) for c in report) + 2
    fields = sorted({f for r in report.values() for f in r.get("fields", {})})
    print("campo".ljust(16) + "".join(c[-width + 1 :].rjust(width) for c in report))
    for name in ["overall", "valid", *fields]:
        cells = []
        for result in report.values():
            if "error" in result:
                cells.append("ERRO".rjust(width))
                continue
            value = result.get(name) if name in ("overall", "valid") else result["fields"][name]
            text = (
                "-"
                if value is None
                else (str(value) if isinstance(value, bool) else f"{value:.2f}")
            )
            cells.append(text.rjust(width))
        print(name.ljust(16) + "".join(cells))
    for case, result in report.items():
        if "error" in result:
            print(f"{case}: {result['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
