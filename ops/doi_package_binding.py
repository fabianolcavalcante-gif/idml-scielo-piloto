"""Strict single-XML ZIP binding for candidate DOI authority; no disk extraction."""

import hashlib
import io
import stat
import unicodedata
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def bound_package_xml(payload, manifest):
    if not 0 < len(payload) <= 100 * 1024**2:
        raise ValueError("authority_package_budget")
    if hashlib.sha256(payload).hexdigest() != manifest.get("package_sha256"):
        raise ValueError("authority_package_mismatch")
    with ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if not 0 < len(entries) <= 1000:
            raise ValueError("authority_package_entries")
        names, xmls, total = set(), [], 0
        for entry in entries:
            name = entry.filename
            key = unicodedata.normalize("NFKC", name).casefold()
            if (
                not name
                or name in {".", ".."}
                or any(c in name for c in "/\\:")
                or any(unicodedata.category(c).startswith("C") for c in name)
                or key in names
                or entry.is_dir()
            ):
                raise ValueError("authority_package_name")
            names.add(key)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if kind not in {0, stat.S_IFREG} or entry.flag_bits & 1:
                raise ValueError("authority_package_special_entry")
            total += entry.file_size
            if (
                entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                or total > 500 * 1024**2
                or entry.file_size > 100 * 1024**2
                or entry.file_size > max(entry.compress_size, 1) * 100
            ):
                raise ValueError("authority_package_expansion")
            if key.endswith(".xml"):
                xmls.append(entry)
        if len(xmls) != 1:
            raise ValueError("authority_package_ambiguous_xml")
        with archive.open(xmls[0]) as stream:
            xml = stream.read(100 * 1024**2 + 1)
        if len(xml) > 100 * 1024**2 or hashlib.sha256(xml).hexdigest() != manifest.get(
            "candidate_sha256"
        ):
            raise ValueError("authority_candidate_mismatch")
        return xml
