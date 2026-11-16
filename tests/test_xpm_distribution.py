from io import BytesIO
from zipfile import ZipFile, ZipInfo

import pytest

from ops.download_xpm_official import verify_archive
from ops.vh1_xpm_probe import public_download_credentials


def test_public_password_obfuscation_is_decoded_not_placeholder():
    key = 37
    value = bytes([key, *(ord(c) ^ key for c in "example@scielo")]).hex()
    page = (
        '<ul><li>user: public-example</li><li>password: <a data-cfemail="'
        + value
        + '">[email\u00a0protected]</a></li></ul>'
    )
    assert public_download_credentials(page) == ("public-example", "example@scielo")


def test_plain_access_instructions_are_supported():
    assert public_download_credentials(
        "<ul><li>user: public-example</li><li>password: example@scielo</li></ul>"
    ) == ("public-example", "example@scielo")


def test_utf8_nonbreaking_separator_is_not_used_as_password():
    assert public_download_credentials(
        (
            "<ul><li>user: public-example</li><li>password:\u00a0"
            '<a href="mailto:example@scielo">example@scielo</a></li></ul>'
        ).encode("utf-8")
    ) == ("public-example", "example@scielo")


@pytest.mark.parametrize(
    "page",
    [
        "<li>password: [email protected]</li><li>user: public-example</li>",
        "<li>user: public-example</li>",
        "<li>user: public-example</li><li>user: duplicate</li><li>password: example</li>",
        '<li>user: public-example</li><li>password: <a data-cfemail="xyz">hidden</a></li>',
        '<li>user: public-example</li><li>password: <a data-cfemail="12345">hidden</a></li>',
        "<li>user: public-example</li><li>password: example\ufffd@scielo</li>",
    ],
)
def test_ambiguous_or_changed_instructions_fail_without_credentials(page):
    with pytest.raises(ValueError):
        public_download_credentials(page)


def archive_bytes(entries):
    target = BytesIO()
    with ZipFile(target, "w") as output:
        for name, content in entries:
            output.writestr(name, content)
    return target


def test_archive_inspection_does_not_execute_code():
    result = verify_archive(
        archive_bytes(
            [
                ("SciELO_XPM/xml/requirements.txt", "packtools==2.4.2\npillow==6.2.2"),
                ("SciELO_XPM/program.py", "raise RuntimeError('never execute')"),
            ]
        )
    )
    assert result["zip_safety_verified"]
    assert result["declared_dependencies"] == ["packtools==2.4.2", "pillow==6.2.2"]


@pytest.mark.parametrize("name", ["../escape.py", "/absolute.py", "C:/absolute.py", "dir\\file"])
def test_archive_rejects_unsafe_paths(name):
    source = archive_bytes([(name.replace("\\", "/"), "data")])
    if "\\" in name:
        # ZipInfo on Windows normalizes slashes on write; simulate raw hostile ZIP bytes.
        source = BytesIO(source.getvalue().replace(name.replace("\\", "/").encode(), name.encode()))
    with pytest.raises(ValueError, match="unsafe_xpm_archive"):
        verify_archive(source)


def test_archive_rejects_case_collision():
    with pytest.raises(ValueError, match="unsafe_xpm_archive"):
        verify_archive(archive_bytes([("file.py", "x"), ("FILE.py", "x")]))


def test_archive_rejects_symlink():
    link = ZipInfo("link")
    link.external_attr = 0o120777 << 16
    with pytest.raises(ValueError, match="unsafe_xpm_archive"):
        verify_archive(archive_bytes([(link, "target")]))
