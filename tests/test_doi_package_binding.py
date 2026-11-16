import hashlib
import io
import stat
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from ops.doi_authority_runtime import authority_lookup
from ops.doi_package_binding import bound_package_xml
from tests.test_doi_authority_transport import setup_case, stage


def package(entries):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


def manifest(payload, xml=b"<article/>"):
    return {
        "package_sha256": hashlib.sha256(payload).hexdigest(),
        "candidate_sha256": hashlib.sha256(xml).hexdigest(),
    }


def test_binds_zip_and_xml_separately():
    payload = package([("article.xml", b"<article/>"), ("figure.svg", b"synthetic")])
    authority = manifest(payload)
    assert bound_package_xml(payload, authority) == b"<article/>"
    with pytest.raises(ValueError, match="package_mismatch"):
        bound_package_xml(payload + b" ", authority)
    with pytest.raises(ValueError, match="candidate_mismatch"):
        bound_package_xml(payload, {**authority, "candidate_sha256": "a" * 64})


@pytest.mark.parametrize(
    "names",
    [
        [],
        ["a.xml", "b.xml"],
        ["A.xml", "a.xml"],
        ["../a.xml"],
        ["dir/a.xml"],
        ["C:a.xml"],
        ["a\\b.xml"],
        ["file.txt"],
    ],
)
def test_rejects_ambiguous_or_unsafe_package(names):
    payload = package([(name, b"<article/>") for name in names])
    with pytest.raises(ValueError):
        bound_package_xml(payload, manifest(payload))


def test_rejects_symlink_and_high_expansion():
    link = ZipInfo("article.xml")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    payload = package([(link, b"<article/>")])
    with pytest.raises(ValueError, match="special_entry"):
        bound_package_xml(payload, manifest(payload))
    compressed = ZipInfo("article.xml")
    compressed.compress_type = ZIP_DEFLATED
    payload = package([(compressed, b"a" * 100000)])
    with pytest.raises(ValueError, match="expansion"):
        bound_package_xml(payload, manifest(payload))


def test_broker_stages_package_bound_authority(tmp_path):
    candidate, snapshot, authority, spec = setup_case(tmp_path)
    xml = candidate.read_bytes()
    payload = package([("article.xml", xml)])
    candidate.write_bytes(payload)
    authority["package_sha256"] = hashlib.sha256(payload).hexdigest()
    spec["name"] = "spsvalidator"
    folder = stage((candidate, snapshot, authority, spec))
    assert (folder / "manifest.json").is_file()
    original = lambda _: None  # noqa: E731
    utils = SimpleNamespace(get_doi_information=original)
    with authority_lookup(utils, b"", folder, package=payload):
        assert utils.get_doi_information("10.1234/test")["message"]["DOI"] == "10.1234/test"
    assert utils.get_doi_information is original
    with pytest.raises(ValueError, match="package_mismatch"):
        with authority_lookup(utils, b"", folder, package=payload + b" "):
            pytest.fail("must reject modified ZIP")
