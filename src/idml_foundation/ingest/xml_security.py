from dataclasses import dataclass

from lxml import etree

MAX_UNTRUSTED_XML_BYTES = 32 * 1024 * 1024
MAX_IDML_XML_BYTES = 16 * 1024 * 1024
MAX_IDML_XML_COMPLEXITY = 200_000


class UnsafeXmlError(ValueError):
    pass


@dataclass
class XmlComplexityBudget:
    limit: int = MAX_IDML_XML_COMPLEXITY
    used: int = 0

    def consume(self, amount: int) -> None:
        self.used += amount
        if self.used > self.limit:
            raise UnsafeXmlError("XML exceeds the ingestion complexity limit")


class _CountingTarget:
    """Count without building a tree; account across every XML in an IDML."""

    def __init__(self, budget: XmlComplexityBudget) -> None:
        self.budget = budget

    def start(self, tag: str | bytes, attributes: dict[str | bytes, str | bytes]) -> None:
        self.budget.consume(1 + len(attributes))

    def end(self, tag: str | bytes) -> None:
        pass

    def data(self, value: str | bytes) -> None:
        pass

    def comment(self, value: str | bytes) -> None:
        self.budget.consume(1)

    def pi(self, target: str, value: str) -> None:
        self.budget.consume(1)

    def doctype(self, name: str, public_id: str | None, system_id: str | None) -> None:
        raise UnsafeXmlError("DOCTYPE and entity declarations are forbidden at ingestion")

    def close(self) -> None:
        pass


def parse_untrusted_xml(
    data: bytes, *, budget: XmlComplexityBudget | None = None
) -> etree._Element:
    if len(data) > MAX_UNTRUSTED_XML_BYTES:
        raise UnsafeXmlError("XML exceeds the ingestion size limit")
    if b"<!ENTITY" in data.upper() or b"<!DOCTYPE" in data.upper():
        raise UnsafeXmlError("DOCTYPE and entity declarations are forbidden at ingestion")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
        remove_comments=False,
    )
    try:
        counter = etree.XMLParser(
            target=_CountingTarget(budget if budget is not None else XmlComplexityBudget()),
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
            remove_comments=False,
        )
        for offset in range(0, len(data), 64 * 1024):
            counter.feed(data[offset : offset + 64 * 1024])
        counter.close()
        root = etree.fromstring(data, parser=parser)
    except UnsafeXmlError:
        raise
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise UnsafeXmlError("XML is malformed or uses a forbidden construct") from exc
    document = root.getroottree().docinfo
    if (
        bool(getattr(document, "doctype", ""))
        or getattr(document, "internalDTD", None) is not None
        or getattr(document, "externalDTD", None) is not None
    ):
        raise UnsafeXmlError("DOCTYPE and entity declarations are forbidden at ingestion")
    if any(isinstance(element, etree._Entity) for element in root.iter()):
        raise UnsafeXmlError("unresolved entities are forbidden at ingestion")
    return root
