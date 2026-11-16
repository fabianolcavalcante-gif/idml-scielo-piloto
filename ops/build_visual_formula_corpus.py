from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from idml_foundation.ai.visual_formula_corpus import (
    PdfFormulaCrop,
    attach_visual_formula_evidence,
    render_formula_crop,
)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build(
    *,
    dataset_path: Path,
    pdf_path: Path,
    crop_config_path: Path,
    output_path: Path,
    pdftoppm: str,
) -> dict[str, Any]:
    dataset = _json_object(dataset_path)
    config = _json_object(crop_config_path)
    if config.get("version") != "visual-formula-crops-1.0":
        raise ValueError("unsupported visual formula crop configuration")
    if _sha256(pdf_path) != config.get("source_pdf_sha256"):
        raise ValueError("visual formula source PDF hash mismatch")
    crops = config.get("crops")
    if not isinstance(crops, list) or not crops:
        raise ValueError("visual formula crop configuration has no cases")
    result = dataset
    for raw_crop in crops:
        if not isinstance(raw_crop, dict):
            raise ValueError("visual formula crop entry must be an object")
        case_id = raw_crop.get("case_id")
        bbox = raw_crop.get("bbox")
        page_index = raw_crop.get("page_index")
        if (
            not isinstance(case_id, str)
            or not isinstance(page_index, int)
            or isinstance(page_index, bool)
            or not isinstance(bbox, list)
            or len(bbox) != 4
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox)
        ):
            raise ValueError("visual formula crop entry is invalid")
        crop = PdfFormulaCrop(
            page_index=page_index,
            bbox=tuple(float(value) for value in bbox),
        )
        image = render_formula_crop(pdf_path, crop, pdftoppm=pdftoppm)
        result = attach_visual_formula_evidence(
            result,
            case_id=case_id,
            image_data=image,
            source_pdf_name=pdf_path.name,
            crop=crop,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "case_count": len(crops),
        "output_sha256": _sha256(output_path),
        "source_pdf_sha256": config["source_pdf_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build authenticated visual formula evidence")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--crops", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pdftoppm", default="pdftoppm")
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                dataset_path=args.dataset,
                pdf_path=args.pdf,
                crop_config_path=args.crops,
                output_path=args.output,
                pdftoppm=args.pdftoppm,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
