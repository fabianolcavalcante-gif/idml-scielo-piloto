from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from enum import StrEnum
from io import BytesIO

from lxml import etree
from pydantic import Field
from pypdf import PdfReader

from idml_foundation.domain.canonical import CanonicalArticle, FigureBlock, Paragraph, TableBlock
from idml_foundation.domain.common import SHA256_PATTERN, StrictModel

_TOKEN = re.compile(r"[\w]+", re.UNICODE)


class FidelityComponent(StrictModel):
    name: str
    source_token_count: int = Field(ge=0)
    pdf_recall: float = Field(ge=0, le=1)
    xml_recall: float = Field(ge=0, le=1)


class PdfTextSource(StrEnum):
    TEXT_LAYER = "text-layer"
    OCR = "ocr"
    UNAVAILABLE = "unavailable"


class FidelityReport(StrictModel):
    report_version: str = "1.0.0"
    pdf_sha256: str = Field(pattern=SHA256_PATTERN)
    xml_sha256: str = Field(pattern=SHA256_PATTERN)
    page_count: int = Field(ge=1)
    text_extraction_available: bool
    pdf_text_source: PdfTextSource
    components: tuple[FidelityComponent, ...]
    minimum_pdf_recall: float = Field(ge=0, le=1)
    minimum_xml_recall: float = Field(ge=0, le=1)
    passed: bool


class FidelityEngine:
    def compare(
        self,
        article: CanonicalArticle,
        xml: bytes,
        pdf: bytes,
        *,
        minimum_pdf_recall: float = 0.80,
        minimum_xml_recall: float = 0.98,
        ocr_text: str | None = None,
    ) -> FidelityReport:
        reader = PdfReader(BytesIO(pdf), strict=True)
        if not reader.pages:
            raise ValueError("PDF must contain at least one page")
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if self._tokens(extracted_text):
            pdf_text = extracted_text
            pdf_text_source = PdfTextSource.TEXT_LAYER
        elif ocr_text and self._tokens(ocr_text):
            pdf_text = ocr_text
            pdf_text_source = PdfTextSource.OCR
        else:
            pdf_text = ""
            pdf_text_source = PdfTextSource.UNAVAILABLE
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        xml_root = etree.fromstring(xml, parser=parser)
        xml_text = " ".join(str(value) for value in xml_root.itertext())
        sources = self._components(article)
        components = tuple(
            FidelityComponent(
                name=name,
                source_token_count=len(self._tokens(value)),
                pdf_recall=self._recall(value, pdf_text),
                xml_recall=self._recall(value, xml_text),
            )
            for name, value in sources
            if self._tokens(value)
        )
        passed = bool(components) and all(
            item.pdf_recall >= minimum_pdf_recall and item.xml_recall >= minimum_xml_recall
            for item in components
        )
        return FidelityReport(
            pdf_sha256=hashlib.sha256(pdf).hexdigest(),
            xml_sha256=hashlib.sha256(xml).hexdigest(),
            page_count=len(reader.pages),
            text_extraction_available=pdf_text_source != PdfTextSource.UNAVAILABLE,
            pdf_text_source=pdf_text_source,
            components=components,
            minimum_pdf_recall=minimum_pdf_recall,
            minimum_xml_recall=minimum_xml_recall,
            passed=passed,
        )

    def _components(self, article: CanonicalArticle) -> tuple[tuple[str, str], ...]:
        titles = " ".join(item.text.value or "" for item in article.front.titles)
        authors = " ".join(
            " ".join(
                value
                for value in (
                    item.name.given_names.value if item.name else None,
                    item.name.surname.value if item.name else None,
                    item.group_name.value if item.group_name else None,
                )
                if value
            )
            for item in article.front.contributors
        )
        body = " ".join(
            " ".join(
                block.content.plain.value or ""
                for block in section.blocks
                if isinstance(block, Paragraph)
            )
            for section in article.body
        )
        references = " ".join(
            item.mixed_citation.plain.value or "" for item in article.back.references
        )
        graphics = " ".join(
            value
            for section in article.body
            for block in section.blocks
            for value in self._graphic_text(block)
        )
        return (
            ("titles", titles),
            ("authors", authors),
            ("body", body),
            ("references", references),
            ("figures-and-tables", graphics),
        )

    def _graphic_text(self, block: object) -> tuple[str, ...]:
        if isinstance(block, FigureBlock):
            return (block.label.value or "", block.caption.plain.value or "")
        if isinstance(block, TableBlock):
            cells = tuple(cell.plain.value or "" for row in block.rows for cell in row)
            return (block.label.value or "", block.caption.plain.value or "", *cells)
        return ()

    def _tokens(self, value: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", value).casefold()
        return _TOKEN.findall("".join(ch for ch in normalized if not unicodedata.combining(ch)))

    def _recall(self, source: str, target: str) -> float:
        expected = Counter(self._tokens(source))
        if not expected:
            return 1.0
        actual = Counter(self._tokens(target))
        matched = sum(min(count, actual[token]) for token, count in expected.items())
        return round(matched / sum(expected.values()), 6)
