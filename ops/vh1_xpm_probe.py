"""Inspect only the documented public XPM directory; never download or execute installers."""

import argparse
import ftplib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

from lxml import html

DOWNLOAD_PAGE = "https://documentacao.scielo.org/books/scielo-pc-programs/page/download"


def public_download_credentials(data):
    """Read only the published list, including Cloudflare's client-side email encoding."""
    # The official page is UTF-8; lxml's byte-input fallback is Latin-1 without a meta tag.
    # Decode explicitly so NBSP does not become an extra non-whitespace U+00C2 token.
    document = html.fromstring(data.decode("utf-8") if isinstance(data, bytes) else data)
    fields = {}
    for node in document.xpath("//li[not(.//li)]"):
        text = " ".join(node.itertext()).strip()
        if not text.startswith(("user:", "password:")):
            continue
        for encoded in node.xpath(".//*[@data-cfemail]"):
            value = encoded.get("data-cfemail", "")
            if not re.fullmatch(r"[0-9a-fA-F]{4,512}", value) or len(value) % 2:
                raise ValueError("invalid_public_credential_encoding")
            octets = bytes.fromhex(value)
            encoded.text = bytes(byte ^ octets[0] for byte in octets[1:]).decode("ascii")
        text = " ".join(node.itertext()).strip()
        match = re.fullmatch(r"(user|password):\s*([A-Za-z0-9@._+-]{3,128})", text)
        if not match or match[1] in fields:
            raise ValueError("ambiguous_public_access_instructions")
        fields[match[1]] = match[2]
    if fields.keys() != {"user", "password"}:
        raise ValueError("missing_public_access_instructions")
    return fields["user"], fields["password"]


def probe(directory="xpm"):
    if not re.fullmatch(r"xpm(?:/[A-Za-z0-9_-]{1,80}){0,2}", directory):
        raise ValueError("invalid_xpm_directory")
    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "source": DOWNLOAD_PAGE,
        "directory": directory,
        "downloaded": False,
        "executed": False,
        "compatible_distribution_proven": False,
    }
    step = "download_page"
    try:
        with urlopen(DOWNLOAD_PAGE, timeout=20) as response:
            data = response.read(512 * 1024)
        step = "public_access_instructions"
        user, password = public_download_credentials(data)
        step = "ftp_connect"
        with ftplib.FTP("ftp.scielo.br", timeout=20) as ftp:  # noqa: S321 - official public listing
            step = "ftp_login"
            ftp.login(user, password)
            step = "ftp_xpm_listing"
            ftp.cwd(directory)
            names = ftp.nlst()
            if len(names) > 200:
                raise ValueError("listing budget exceeded")
            basenames = [PurePosixPath(name).name for name in names]
            result["entry_count"] = len(names)
            result["entries"] = sorted(
                name for name in basenames if re.fullmatch(r"[A-Za-z0-9_. -]{1,150}", name)
            )
            result["software_files"] = sorted(
                name
                for name in basenames
                if re.fullmatch(r"(?:SciELO|XPM)[A-Za-z0-9_. -]+\.(?:zip|exe|txt)", name, re.I)
            )
            result["archives"] = sorted(
                name for name in basenames if re.fullmatch(r"SciELO_XPM_[A-Za-z0-9_.-]+\.zip", name)
            )
            result["status"] = "listed"
    except (OSError, ValueError, AttributeError, ftplib.Error) as error:
        # No credentials or server traceback in the public diagnostic.
        result["status"] = "source_unavailable_or_changed"
        result["failed_step"] = step
        result["error_type"] = type(error).__name__
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--directory", default="xpm")
    args = parser.parse_args()
    result = probe(args.directory)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
