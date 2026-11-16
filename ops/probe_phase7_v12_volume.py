"""Bounded synthetic persistence/conversion probes; no private corpus or provider."""

import argparse
import hashlib
import json
import random
import time
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from idml_foundation.database import Base
from idml_foundation.ingest.scanner import PolicyOnlyScanner
from idml_foundation.models import Organization
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.services.artifacts import (
    read_artifact_bytes,
    store_generated_artifact,
    store_idml_artifact,
)
from idml_foundation.services.storage_budget import ArtifactStorageError, tenant_usage
from idml_foundation.settings import Settings
from tests.phase3_helpers import synthetic_idml

MIB = 1024**2
CASES = ("stored_16m", "stored_100m", "expanded_500m", "text_14m", "files_10000", "disk_reserve")


def make_text_package(path, text_bytes=7 * MIB):
    with ZipFile(BytesIO(synthetic_idml())) as source, ZipFile(path, "w") as output:
        for info in source.infolist():
            value = source.read(info.filename)
            if info.filename == "Stories/Story_u2.xml":
                value = value.replace(
                    b"<Content>Plain </Content>", b"<Content>" + b"a" * text_bytes + b"</Content>"
                )
                value = value.replace(
                    b"<Content>emphasis</Content>", b"<Content>" + b"b" * text_bytes + b"</Content>"
                )
            output.writestr(info.filename, value, compress_type=ZIP_STORED)


def make_package(path, *, stored_bytes=None, expanded_bytes=None):
    """Write incrementally on disk so fixture generation does not fake pipeline RSS."""
    if (stored_bytes is None) == (expanded_bytes is None):
        raise ValueError("choose one size")
    with ZipFile(BytesIO(synthetic_idml())) as source, ZipFile(path, "w") as output:
        original_total = 0
        for info in source.infolist():
            value = source.read(info.filename)
            original_total += len(value)
            output.writestr(info.filename, value, compress_type=ZIP_STORED)
        name = "Resources/SyntheticPayload.bin"
        if stored_bytes is not None:
            # ZIP local header + central directory + EOCD; ASCII paths, no extras.
            overhead = sum(
                76 + 2 * len(i.filename.encode()) + i.file_size for i in output.infolist()
            )
            remaining = stored_bytes - overhead - (76 + 2 * len(name)) - 22
            output.compression = ZIP_STORED
            block = b"x" * 65536
        else:
            remaining = expanded_bytes - original_total
            output.compression = ZIP_DEFLATED
            # Bounded ratio (~45), unlike a zero-only decompression bomb.
            block = random.Random(42).randbytes(4096) + b"x" * (196608 - 4096)  # noqa: S311 -- synthetic fixture
        if remaining < 1:
            raise ValueError("fixture too small")
        with output.open(name, "w") as target:
            while remaining:
                count = min(remaining, len(block))
                target.write(block[:count])
                remaining -= count
    if stored_bytes is not None and path.stat().st_size != stored_bytes:
        raise AssertionError("stored size is not exact")


def run(case, work):
    import resource

    settings = Settings(environment="test", artifact_root=work / "artifacts")
    engine = create_engine(f"sqlite+pysqlite:///{work / 'lab.db'}")
    Base.metadata.create_all(engine)
    started = time.perf_counter()
    with Session(engine, expire_on_commit=False) as db:
        org = Organization(slug="volume-lab", name="Synthetic volume")
        db.add(org)
        db.commit()
        if case in {"files_10000", "disk_reserve"}:
            if case == "files_10000":
                tenant = settings.artifact_root / org.id
                for index in range(settings.artifact_tenant_max_files):
                    value = f"synthetic-{index}".encode()
                    digest = hashlib.sha256(value).hexdigest()
                    path = tenant / digest[:2] / digest
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(value)
                usage = tenant_usage(tenant, settings)
                expected = "artifact_quota_exceeded"
            else:
                settings.artifact_root = Path("/tmp/pressure-artifacts")  # noqa: S108
                settings.artifact_disk_reserve_bytes = 16 * MIB
                with Path("/tmp/synthetic-pressure.bin").open("wb") as pressure:  # noqa: S108
                    for _ in range(52):
                        pressure.write(b"x" * MIB)
                usage = (0, 0)
                expected = "artifact_disk_reserve"
            status = "unexpected_accept"
            try:
                store_generated_artifact(
                    db,
                    organization_id=org.id,
                    original_name="synthetic.xml",
                    data=b"<x/>",
                    media_type="application/xml",
                    settings=settings,
                )
            except ArtifactStorageError as exc:
                status = exc.code
            finally:
                db.rollback()
            result = {"approved": status == expected, "status": status, "usage": usage}
        else:
            package = work / "synthetic.idml"
            if case == "text_14m":
                make_text_package(package)
            else:
                make_package(
                    package,
                    stored_bytes={"stored_16m": 16 * MIB, "stored_100m": 100 * MIB}.get(case),
                    expanded_bytes=500 * MIB if case == "expanded_500m" else None,
                )
            data = package.read_bytes()
            artifact, inspection = store_idml_artifact(
                db,
                organization_id=org.id,
                original_name="ESA_2024001_AOP.idml",
                data=data,
                settings=settings,
                scanner=PolicyOnlyScanner(),
            )
            db.commit()
            del data
            content = read_artifact_bytes(artifact, settings)
            converted = DeterministicPipeline(settings=settings).run(
                content, logical_name="ESA_2024001_AOP.idml"
            )
            del content
            xml = store_generated_artifact(
                db,
                organization_id=org.id,
                original_name="synthetic.xml",
                data=converted.xml,
                media_type="application/xml",
                settings=settings,
            )
            db.commit()
            result = {
                "approved": converted.validation.valid
                and read_artifact_bytes(xml, settings) == converted.xml,
                "status": "converted",
                "input_bytes": artifact.size_bytes,
                "expanded_bytes": inspection.total_uncompressed_bytes,
                "max_compression_ratio": inspection.max_compression_ratio,
                "xml_sha256": xml.sha256,
                "xml_bytes": xml.size_bytes,
                "offline_valid": converted.validation.valid,
            }
    engine.dispose()
    return {
        **result,
        "case": case,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "provider_calls": 0,
        "restricted_content_emitted": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    result = run(args.case, Path("/work"))
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result["approved"] else 2)
