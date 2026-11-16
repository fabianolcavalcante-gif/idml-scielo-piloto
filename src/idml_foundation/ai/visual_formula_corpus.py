from __future__ import annotations

import base64
import copy
import hashlib
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from idml_foundation.ai.evidence import visual_evidence_bytes

PDF_RENDER_DPI = 300
PDF_POINTS_PER_INCH = 72
MAX_PDF_PAGES = 500
MAX_CROP_AREA_POINTS = 250_000


@dataclass(frozen=True)
class PdfFormulaCrop:
    page_index: int
    bbox: tuple[float, float, float, float]


def _validated_crop(pdf_path: Path, crop: PdfFormulaCrop) -> None:
    if not pdf_path.is_file() or pdf_path.suffix.casefold() != ".pdf":
        raise ValueError("visual formula source must be an existing PDF")
    reader = PdfReader(pdf_path, strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted visual formula PDFs are not supported")
    if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        raise ValueError("visual formula PDF page count is outside the allowed bound")
    if isinstance(crop.page_index, bool) or not 0 <= crop.page_index < len(reader.pages):
        raise ValueError("visual formula page index is invalid")
    page = reader.pages[crop.page_index]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    x0, y0, x1, y1 = crop.bbox
    if (
        not all(math.isfinite(value) for value in crop.bbox)
        or min(crop.bbox) < 0
        or x1 <= x0
        or y1 <= y0
        or x1 > width
        or y1 > height
        or (x1 - x0) * (y1 - y0) > MAX_CROP_AREA_POINTS
    ):
        raise ValueError("visual formula crop is outside the PDF page")


def render_formula_crop(
    pdf_path: Path,
    crop: PdfFormulaCrop,
    *,
    pdftoppm: str | Path = "pdftoppm",
) -> bytes:
    """Render a bounded PDF region to PNG with no shell and no network access."""
    _validated_crop(pdf_path, crop)
    executable = shutil.which(str(pdftoppm))
    if executable is None:
        candidate = Path(pdftoppm).resolve()
        if not candidate.is_file() or candidate.name.casefold() not in {
            "pdftoppm",
            "pdftoppm.exe",
        }:
            raise RuntimeError("pdftoppm is unavailable")
        executable = str(candidate)
    scale = PDF_RENDER_DPI / PDF_POINTS_PER_INCH
    x0, y0, x1, y1 = crop.bbox
    with tempfile.TemporaryDirectory(prefix="idml-formula-crop-") as temp_name:
        output_prefix = Path(temp_name) / "crop"
        command = [
            executable,
            "-f",
            str(crop.page_index + 1),
            "-l",
            str(crop.page_index + 1),
            "-singlefile",
            "-png",
            "-r",
            str(PDF_RENDER_DPI),
            "-x",
            str(math.floor(x0 * scale)),
            "-y",
            str(math.floor(y0 * scale)),
            "-W",
            str(math.ceil((x1 - x0) * scale)),
            "-H",
            str(math.ceil((y1 - y0) * scale)),
            str(pdf_path.resolve()),
            str(output_prefix),
        ]
        try:
            subprocess.run(  # noqa: S603 - fixed executable name/path and argument vector
                command,
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("visual formula crop rendering failed") from exc
        output = output_prefix.with_suffix(".png")
        if not output.is_file():
            raise RuntimeError("visual formula crop renderer produced no PNG")
        data = output.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("visual formula crop renderer produced invalid PNG")
    return data


def attach_visual_formula_evidence(
    dataset: dict[str, Any],
    *,
    case_id: str,
    image_data: bytes,
    source_pdf_name: str,
    crop: PdfFormulaCrop,
) -> dict[str, Any]:
    """Replace gold-as-input with authenticated visual input while retaining hidden evaluation."""
    copied = copy.deepcopy(dataset)
    cases = copied.get("cases")
    if not isinstance(cases, list):
        raise ValueError("visual formula dataset has no cases")
    matches = [case for case in cases if isinstance(case, dict) and case.get("case_id") == case_id]
    if len(matches) != 1:
        raise ValueError("visual formula case must exist exactly once")
    case = matches[0]
    atomic = case.get("atomic_formula")
    if not isinstance(atomic, dict):
        raise ValueError("visual formula case requires an atomic formula contract")
    x0, y0, x1, y1 = crop.bbox
    image_sha256 = hashlib.sha256(image_data).hexdigest()
    evidence = {
        "evidence_id": f"visual-{case_id}",
        "source_kind": "pdf",
        "locator": (
            f"{Path(source_pdf_name).name}#page={crop.page_index + 1}"
            f"&bbox={x0:g},{y0:g},{x1:g},{y1:g}"
        ),
        "media_type": "image/png",
        "image_base64": base64.b64encode(image_data).decode("ascii"),
        "image_sha256": image_sha256,
        "page_index": crop.page_index,
        "bbox": [x0, y0, x1, y1],
    }
    visual_evidence_bytes(evidence)
    case["evidence"] = evidence
    case["grounding_policy"] = "visual_formula"
    case["alternatives"] = ["Retain the current representation pending human review"]
    provenance = case.get("fixture_provenance")
    if isinstance(provenance, dict):
        provenance["kind"] = "source_pdf_visual_formula_transcription"
        provenance["gold_exposed_to_agent"] = False
    return copied
