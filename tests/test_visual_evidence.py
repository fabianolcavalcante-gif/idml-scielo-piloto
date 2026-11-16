from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any

import pytest

from idml_foundation.ai.evidence import evidence_reference, visual_evidence_bytes
from idml_foundation.ai.outputs import AgentEvidenceReference


def _visual_evidence() -> dict[str, object]:
    data = b"\x89PNG\r\n\x1a\nformula-crop"
    return {
        "evidence_id": "visual-formula-001",
        "source_kind": "pdf",
        "locator": "source.pdf#page=3&bbox=10,20,110,60",
        "media_type": "image/png",
        "image_base64": base64.b64encode(data).decode("ascii"),
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "page_index": 2,
        "bbox": [10.0, 20.0, 110.0, 60.0],
    }


def test_visual_evidence_reference_is_content_free_and_schema_valid() -> None:
    evidence = _visual_evidence()
    assert visual_evidence_bytes(evidence) == b"\x89PNG\r\n\x1a\nformula-crop"
    reference = evidence_reference(evidence)
    assert "image_base64" not in reference
    assert reference["image_sha256"] == evidence["image_sha256"]
    parsed = AgentEvidenceReference.model_validate_json(json.dumps(reference))
    assert parsed.page_index == 2
    assert parsed.bbox == (10.0, 20.0, 110.0, 60.0)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda value: value.update(image_sha256="0" * 64), "hash"),
        (lambda value: value.update(image_base64="not-base64"), "base64"),
        (lambda value: value.update(media_type="image/svg+xml"), "media type"),
        (lambda value: value.update(bbox=[10, 20, 5, 60]), "bounding box"),
        (lambda value: value.update(excerpt="leak"), "cannot mix"),
    ],
)
def test_visual_evidence_rejects_tampering(
    mutation: Callable[[dict[str, Any]], None], message: str
) -> None:
    evidence = _visual_evidence()
    mutation(evidence)
    with pytest.raises(ValueError, match=message):
        visual_evidence_bytes(evidence)
