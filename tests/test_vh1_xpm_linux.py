from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from idml_foundation.release.xpm import XpmReportParser
from ops.qualify_vh1_xpm_linux import checked_members, docker_arguments, mutate
from ops.run_xpm_qualification import inspect_report
from ops.summarize_vh1_xpm_linux import negative_detected, visible_text

REPORT = b"""<html><body><!-- 4.0.096 22/04/2019 -->
<span>Total of blocking errors</span>: 4 <span>Total of fatal errors</span>: 3
<span>Total of errors</span>: 1 <span>Total of warnings</span>: 0
<p>invalid XML files.</p></body></html>"""


def members():
    return {
        "article.xml": b"<article><journal-title>Test</journal-title></article>",
        "article-gf01.jpg": b"test-asset",
    }


@pytest.mark.parametrize(
    "kind", ["baseline", "missing_journal_title", "missing_graphic", "malformed_xml"]
)
def test_mutations_preserve_original(kind):
    original = members()
    expected = dict(original)
    result = mutate(original, kind)
    assert original == expected and result is not original
    if kind == "missing_graphic":
        assert list(result) == ["article.xml"]
    elif kind == "missing_journal_title":
        assert result["article.xml"] == b"<article></article>"


@pytest.mark.parametrize(
    "xml", [b"<article/>", b"<journal-title>A</journal-title><journal-title>B</journal-title>"]
)
def test_missing_or_ambiguous_mutation_rejected(xml):
    with pytest.raises(ValueError, match="not_unique"):
        mutate({"article.xml": xml}, "missing_journal_title")


def test_unknown_mutation_rejected():
    with pytest.raises(ValueError, match="unknown_mutation"):
        mutate(members(), "arbitrary")


def zipped(entries):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    output.seek(0)
    return ZipFile(output)


@pytest.mark.parametrize(
    "name", ["../escape.xml", "/escape.xml", "a/b.xml", "C:escape.xml", "..", "dir/"]
)
def test_unsafe_package_member_rejected(name):
    with zipped([(name, "x")]) as archive, pytest.raises(ValueError):
        checked_members(archive)


def test_flat_package_is_exact():
    with zipped(list(members().items())) as archive:
        assert checked_members(archive) == members()


def test_symlink_rejected():
    entry = ZipInfo("article.xml")
    entry.external_attr = 0o120777 << 16
    with zipped([(entry, "target")]) as archive, pytest.raises(ValueError):
        checked_members(archive)


def test_collision_rejected():
    with zipped([("article.xml", "a"), ("ARTICLE.XML", "b")]) as archive, pytest.raises(ValueError):
        checked_members(archive)


@pytest.mark.parametrize("entries", [[], [("a.jpg", "a")], [("a.xml", "a"), ("b.xml", "b")]])
def test_exactly_one_xml_required(entries):
    with zipped(entries) as archive, pytest.raises(ValueError, match="expected_one_xml"):
        checked_members(archive)


def test_isolation_is_explicit():
    args = docker_arguments("sha256:" + "a" * 64, "idml-xpm-test", Path("/input"), Path("/work"))
    for value in (
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--memory=384m",
        "--memory-swap=384m",
        "--pids-limit=64",
    ):
        assert value in args
    assert not any("docker.sock" in value or "privileged" in value for value in args)


@pytest.mark.parametrize(
    "image,name", [("latest", "idml-xpm-test"), ("sha256:" + "a" * 64, "unrelated")]
)
def test_mutable_image_or_broad_name_rejected(image, name):
    with pytest.raises(ValueError):
        docker_arguments(image, name, Path("/input"), Path("/work"))


def test_native_counts_not_process_exit_code_decide_failure(tmp_path):
    path = tmp_path / "xpm.html"
    path.write_bytes(REPORT)
    assert inspect_report(path)["totals"]["blocking_errors"] == [4]
    result = XpmReportParser().parse(
        REPORT, candidate_package_sha256="a" * 64, tool_sha256="b" * 64
    )
    assert not result.passed
    assert negative_detected("malformed_xml", visible_text(REPORT), "baseline", result)


def test_script_text_cannot_satisfy_negative_control():
    doc = b"<html><body><script>invalid XML files.</script><p>normal</p></body></html>"
    assert visible_text(doc) == "normal"


@pytest.mark.parametrize(
    "text,baseline", [("nothing", "baseline"), ("invalid XML files.", "invalid XML files.")]
)
def test_control_must_be_new_and_specific(text, baseline):
    result = XpmReportParser().parse(
        REPORT, candidate_package_sha256="a" * 64, tool_sha256="b" * 64
    )
    assert not negative_detected("malformed_xml", text, baseline, result)
