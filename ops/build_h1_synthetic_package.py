"""Build a content-free integration fixture, not an editorially valid article."""

import hashlib
import io
import json
from pathlib import Path

from pypdf import PdfWriter

from idml_foundation.pipeline.jats_builder import JatsBuilder
from idml_foundation.release.package_builder import AssetPayload, PackageBuilder
from ops.v05_fixture import complete_article


def candidates():
    article = complete_article()
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        b'<rect width="100" height="100" fill="gray"/></svg>'
    )
    article = article.model_copy(
        update={
            "assets": (
                article.assets[0].model_copy(
                    update={
                        "logical_name": "synthetic.svg",
                        "media_type": "image/svg+xml",
                        "sha256": hashlib.sha256(svg).hexdigest(),
                    }
                ),
            )
        }
    )
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    builder = PackageBuilder()
    files = builder.scielo_files(
        package_stem="1234-5678-example-31-01-e20260001",
        xml=JatsBuilder().build(article),
        pdf=pdf.getvalue(),
        assets=(AssetPayload(source_name="synthetic.svg", data=svg),),
    )
    package = builder.build(
        article_id=article.article_id,
        profile_id="sps-1.10/jats-1.3",
        source_idml_sha256="a" * 64,
        files=files,
        validator_versions={},
    )
    return files[0].data, package.archive


def main():
    output = Path("tmp/h1-synthetic-complete-v1")
    output.mkdir(exist_ok=True)
    xml, package = candidates()
    for name, data in (("candidate.xml", xml), ("candidate.zip", package)):
        (output / name).write_bytes(data)
    print(
        json.dumps(
            {
                "xml_sha256": hashlib.sha256(xml).hexdigest(),
                "package_sha256": hashlib.sha256(package).hexdigest(),
                "private_corpus_used": False,
            }
        )
    )


if __name__ == "__main__":
    main()
