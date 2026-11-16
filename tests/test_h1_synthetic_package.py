import io
from zipfile import ZipFile

from lxml import etree
from pypdf import PdfReader

from ops.build_h1_synthetic_package import candidates


def test_synthetic_package_complete_and_deterministic():
    xml, package = candidates()
    assert candidates() == (xml, package)
    with ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        assert len(names) == 4
        assert archive.read(next(n for n in names if n.endswith(".xml"))) == xml
        assert (
            len(
                PdfReader(
                    io.BytesIO(archive.read(next(n for n in names if n.endswith(".pdf"))))
                ).pages
            )
            == 1
        )
        root = etree.fromstring(
            xml, parser=etree.XMLParser(resolve_entities=False, no_network=True)
        )
        links = root.xpath("//@xlink:href", namespaces={"xlink": "http://www.w3.org/1999/xlink"})
        assert all(link in names for link in links if not link.startswith("http"))
