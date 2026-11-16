"""Bounded, content-free conversion benchmark; no database, provider or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from idml_foundation.ingest.safe_zip import UnsafeArchiveError
from idml_foundation.pipeline.service import DeterministicPipeline

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from tests.phase3_helpers import synthetic_idml  # noqa: E402 - standalone ops entry point


def percentile(values: list[float], fraction: float = 0.95) -> float:
    if not values or not 0 < fraction <= 1:
        raise ValueError("nonempty samples and percentile in (0,1] required")
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def fixture(paragraphs: int, *, pathological: bool = False) -> bytes:
    if not 1 <= paragraphs <= 512:
        raise ValueError("fixture size outside qualified bounds")
    source = synthetic_idml(include_table=True, include_subsection=True)
    content = b"".join(
        (
            '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/05.0.text">'
            '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/none">'
            f"<Content>Synthetic observation {i} {hashlib.sha256(str(i).encode()).hexdigest()}."
            "</Content></CharacterStyleRange></ParagraphStyleRange>"
        ).encode()
        for i in range(paragraphs)
    )
    output = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(output, "w") as target:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "Stories/Story_u2.xml":
                data = data.replace(b"</Story>", content + b"</Story>")
            target.writestr(entry, data)
        if pathological:
            target.writestr(
                "Stories/oversized.xml", b"x" * (1024 * 1024), compress_type=ZIP_DEFLATED
            )
    return output.getvalue()


def rss_bytes() -> int | None:
    path = Path("/proc/self/status")
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def measure(
    source: bytes, queued: float, *, pipeline=None, logical_name="ESA_2024999_AOP.idml"
) -> dict:
    started = time.perf_counter()
    selected = pipeline or DeterministicPipeline()
    stages = {}
    restorations = []
    for obj, method, label in (
        (selected._parser, "parse", "parse"),
        (selected._mapper, "map", "map"),
        (selected._builder, "build", "build"),
        (selected._validator, "validate", "validate"),
    ):
        original = getattr(obj, method)
        restorations.append((obj, method, method in vars(obj), original))

        def timed(*args, _original=original, _label=label, **kwargs):
            before = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                stages[_label] = round((time.perf_counter() - before) * 1000, 3)

        setattr(obj, method, timed)
    try:
        result = selected.run(source, logical_name=logical_name)
        status = "valid" if result.validation.valid else "invalid"
        digest = hashlib.sha256(result.xml).hexdigest()
        output_bytes = len(result.xml)
    except UnsafeArchiveError as exc:
        status, digest, output_bytes = "rejected:" + exc.code, None, 0
    finally:
        # Do not leave obj -> wrapper -> bound method -> obj cycles behind.
        for obj, method, was_overridden, original in restorations:
            if was_overridden:
                setattr(obj, method, original)
            else:
                delattr(obj, method)
    return {
        "status": status,
        "xml_sha256": digest,
        "source_bytes": len(source),
        "xml_bytes": output_bytes,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "queue_ms": round((started - queued) * 1000, 3),
        "stages_ms": stages,
    }


def benchmark(*, repeats: int, soak_seconds: int) -> dict:
    if not 2 <= repeats <= 10 or not 0 <= soak_seconds <= 600:
        raise ValueError("benchmark exceeds authorized bounds")
    cases = {
        name: fixture(size) for name, size in (("small", 16), ("typical", 128), ("large", 512))
    }
    rows = []
    for concurrency in (1, 2):
        for name, source in cases.items():
            submitted = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(measure, source, submitted) for _ in range(repeats)]
                samples = [future.result() for future in futures]
            rows.append(
                {
                    "case": name,
                    "concurrency": concurrency,
                    "samples": samples,
                    "p95_duration_ms": percentile([s["duration_ms"] for s in samples]),
                    "p95_queue_ms": percentile([s["queue_ms"] for s in samples]),
                    "deterministic": len({s["xml_sha256"] for s in samples}) == 1,
                    "all_valid": all(s["status"] == "valid" for s in samples),
                }
            )
    rejected = measure(fixture(1, pathological=True), time.perf_counter())
    # Warm up before the memory-growth baseline; bounded result accumulation.
    measure(cases["typical"], time.perf_counter())
    initial_rss = rss_bytes()
    beginning = time.perf_counter()
    count = 0
    max_duration = 0.0
    digests = set()
    while time.perf_counter() - beginning < soak_seconds:
        sample = measure(cases["typical"], time.perf_counter())
        if sample["status"] != "valid":
            raise ValueError("soak conversion failed")
        count += 1
        digests.add(sample["xml_sha256"])
        max_duration = max(max_duration, sample["duration_ms"])
        time.sleep(0.2)
    final_rss = rss_bytes()
    growth = None if initial_rss is None or final_rss is None else final_rss - initial_rss
    approved = (
        all(r["all_valid"] and r["deterministic"] for r in rows)
        and rejected["status"].startswith("rejected:")
        and len(digests) <= 1
        and (growth is None or growth <= 32 * 1024 * 1024)
    )
    return {
        "version": "phase7-v12-benchmark-1.0",
        "approved": approved,
        "rows": rows,
        "pathological": rejected,
        "soak": {
            "requested_seconds": soak_seconds,
            "elapsed_seconds": round(time.perf_counter() - beginning, 3),
            "conversions": count,
            "rss_initial_bytes": initial_rss,
            "rss_final_bytes": final_rss,
            "rss_growth_bytes": growth,
            "max_duration_ms": max_duration,
        },
        "queue_scope": "in-process synthetic queue; not production Redis/API throughput",
        "provider_calls": 0,
        "cost_microusd": 0,
        "restricted_content_emitted": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--soak-seconds", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(repeats=args.repeats, soak_seconds=args.soak_seconds)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
