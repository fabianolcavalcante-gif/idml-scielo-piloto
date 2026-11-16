"""Export deterministic JSON Schemas for external contracts."""

import json
import os
import tempfile
from pathlib import Path

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.domain.corpus import CorpusManifest
from idml_foundation.domain.raw import RawArticle

OUTPUTS = {
    "canonical-article-1.6.0.schema.json": CanonicalArticle.model_json_schema(),
    "corpus-manifest-1.0.0.schema.json": CorpusManifest.model_json_schema(),
    "raw-article-1.3.0.schema.json": RawArticle.model_json_schema(),
}


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".schema-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "schemas"
    for name, schema in OUTPUTS.items():
        content = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        write_atomic(root / name, content)
    print(f"exported {len(OUTPUTS)} schemas")


if __name__ == "__main__":
    main()
