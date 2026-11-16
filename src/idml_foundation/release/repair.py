from __future__ import annotations

import hashlib
from enum import StrEnum

from lxml import etree
from pydantic import Field

from idml_foundation.domain.common import SHA256_PATTERN, StrictModel
from idml_foundation.pipeline.validation import OfflineJatsValidator, ValidationReport


class RepairKind(StrEnum):
    TRIM_ID = "trim-id"
    NORMALIZE_RID_WHITESPACE = "normalize-rid-whitespace"


class RepairOperation(StrictModel):
    kind: RepairKind
    element: str
    attribute: str
    before_sha256: str = Field(pattern=SHA256_PATTERN)
    after_sha256: str = Field(pattern=SHA256_PATTERN)


class RepairReport(StrictModel):
    report_version: str = "1.0.0"
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    passes: int = Field(ge=0, le=2)
    operations: tuple[RepairOperation, ...]


class SafeRepairEngine:
    """Apply only atomic identifier whitespace repairs with resolved references."""

    def repair(self, xml: bytes, *, max_passes: int = 2) -> tuple[bytes, RepairReport]:
        if max_passes not in (1, 2):
            raise ValueError("max_passes must be 1 or 2")
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_blank_text=False,
        )
        root = etree.fromstring(xml, parser=parser)
        operations: list[RepairOperation] = []
        passes = 0
        for pass_number in range(1, max_passes + 1):
            changed = False
            ids = {value for element in root.iter() if (value := element.get("id"))}
            for element in root.iter():
                identifier = element.get("id")
                if identifier and identifier != identifier.strip():
                    clean = identifier.strip()
                    if clean and clean not in ids:
                        for referenced in root.iter():
                            rid = referenced.get("rid")
                            if rid:
                                tokens = rid.split()
                                if identifier in tokens:
                                    referenced.set(
                                        "rid",
                                        " ".join(
                                            clean if token == identifier else token
                                            for token in tokens
                                        ),
                                    )
                        element.set("id", clean)
                        ids.remove(identifier)
                        ids.add(clean)
                        operations.append(
                            self._operation(RepairKind.TRIM_ID, element, "id", identifier, clean)
                        )
                        changed = True
                rid = element.get("rid")
                if rid:
                    clean_rid = " ".join(rid.split())
                    if clean_rid != rid and set(clean_rid.split()) <= ids:
                        element.set("rid", clean_rid)
                        operations.append(
                            self._operation(
                                RepairKind.NORMALIZE_RID_WHITESPACE,
                                element,
                                "rid",
                                rid,
                                clean_rid,
                            )
                        )
                        changed = True
            if not changed:
                break
            passes = pass_number
        if not operations:
            repaired = xml
        else:
            docinfo = root.getroottree().docinfo
            doctype = str(getattr(docinfo, "doctype", ""))
            repaired = etree.tostring(
                root,
                encoding="UTF-8",
                xml_declaration=True,
                doctype=doctype,
                pretty_print=False,
            )
        return repaired, RepairReport(
            source_sha256=hashlib.sha256(xml).hexdigest(),
            result_sha256=hashlib.sha256(repaired).hexdigest(),
            passes=passes,
            operations=tuple(operations),
        )

    def repair_and_revalidate(
        self,
        xml: bytes,
        validator: OfflineJatsValidator,
        *,
        asset_names: set[str] | None = None,
    ) -> tuple[bytes, RepairReport, tuple[ValidationReport, ...]]:
        reports = [validator.validate(xml, asset_names=asset_names)]
        repaired, repair_report = self.repair(xml, max_passes=2)
        if repair_report.operations:
            reports.append(validator.validate(repaired, asset_names=asset_names))
        return repaired, repair_report, tuple(reports)

    def _operation(
        self,
        kind: RepairKind,
        element: etree._Element,
        attribute: str,
        before: str,
        after: str,
    ) -> RepairOperation:
        return RepairOperation(
            kind=kind,
            element=etree.QName(element).localname,
            attribute=attribute,
            before_sha256=hashlib.sha256(before.encode()).hexdigest(),
            after_sha256=hashlib.sha256(after.encode()).hexdigest(),
        )
