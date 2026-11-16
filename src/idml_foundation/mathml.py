from __future__ import annotations

from copy import deepcopy

from lxml import etree

MATHML_NS = "http://www.w3.org/1998/Math/MathML"
MAX_MATHML_BYTES = 32_000
_ALLOWED_ELEMENTS = {
    "math",
    "menclose",
    "merror",
    "mfenced",
    "mfrac",
    "mi",
    "mmultiscripts",
    "mn",
    "mo",
    "mover",
    "mpadded",
    "mphantom",
    "mprescripts",
    "mroot",
    "mrow",
    "ms",
    "mspace",
    "msqrt",
    "mstyle",
    "msub",
    "msubsup",
    "msup",
    "mtable",
    "mtd",
    "mtext",
    "mtr",
    "munder",
    "munderover",
    "none",
    "semantics",
    "annotation",
}
_FORBIDDEN_ATTRIBUTE_NAMES = {"href", "src", "actiontype"}
_FIXED_ELEMENT_ARITY = {
    "mfrac": 2,
    "mroot": 2,
    "msub": 2,
    "msup": 2,
    "munder": 2,
    "mover": 2,
    "msubsup": 3,
    "munderover": 3,
}


def parse_mathml_fragment(value: str, *, display: bool) -> etree._Element:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > MAX_MATHML_BYTES:
        raise ValueError("MathML fragment size is outside the allowed range")
    if b"<!doctype" in encoded.lower():
        raise ValueError("MathML fragment must not contain DTD declarations")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        recover=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    try:
        root = etree.fromstring(encoded, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("MathML fragment is not well-formed") from exc
    if root.tag != f"{{{MATHML_NS}}}math":
        raise ValueError("MathML fragment must have mml:math as its root")
    expected_display = "block" if display else "inline"
    observed_display = root.get("display")
    if observed_display not in {None, expected_display}:
        raise ValueError(f"MathML display must be {expected_display}")
    for element in root.iter():
        if not isinstance(element.tag, str):
            raise ValueError("MathML fragment contains an unsupported node")
        qname = etree.QName(element)
        if qname.namespace != MATHML_NS or qname.localname not in _ALLOWED_ELEMENTS:
            raise ValueError("MathML fragment contains an unsupported element")
        required_arity = _FIXED_ELEMENT_ARITY.get(qname.localname)
        if required_arity is not None and len(element) != required_arity:
            raise ValueError(
                f"MathML {qname.localname} must contain exactly {required_arity} child elements"
            )
        for attribute in element.attrib:
            attribute_name = etree.QName(attribute)
            if attribute_name.localname.casefold() in _FORBIDDEN_ATTRIBUTE_NAMES:
                raise ValueError("MathML fragment contains an unsafe attribute")
            if attribute_name.namespace not in {None, MATHML_NS}:
                raise ValueError("MathML fragment contains an unsupported attribute namespace")
    normalized = deepcopy(root)
    normalized.set("display", expected_display)
    etree.cleanup_namespaces(normalized, top_nsmap={"mml": MATHML_NS})
    normalized.tail = None
    return normalized


def canonical_mathml(value: str, *, display: bool) -> str:
    element = parse_mathml_fragment(value, display=display)
    return etree.tostring(element, encoding="unicode", pretty_print=False)


def _semantic_fingerprint(element: etree._Element) -> tuple[object, ...]:
    qname = etree.QName(element)
    children = tuple(
        fingerprint
        for child in element
        if (fingerprint := _semantic_fingerprint(child))
        if fingerprint[0] != "ignorable-space"
    )
    attributes = tuple(
        sorted(
            (etree.QName(name).localname, value)
            for name, value in element.attrib.items()
            if etree.QName(name).localname not in {"display", "stretchy"}
        )
    )
    text = " ".join((element.text or "").split())
    if qname.localname == "mo" and text == "-":
        text = "\N{MINUS SIGN}"
    if qname.localname == "mo" and text in {".", "\N{MIDDLE DOT}", "\N{DOT OPERATOR}"}:
        text = "."
    if qname.localname == "mtext" and not text:
        return ("ignorable-space", (), "", ())
    if qname.localname == "mi" and not attributes and not children and len(text) > 1:
        return (
            "mrow",
            (),
            "",
            tuple(("mi", (), character, ()) for character in text),
        )
    if qname.localname == "math":
        if len(children) == 1:
            return children[0]
        return ("mrow", (), "", children)
    if qname.localname == "mrow" and not attributes and not text:
        flattened: list[tuple[object, ...]] = []
        for child in children:
            if child[0:3] == ("mrow", (), ""):
                nested = child[3]
                assert isinstance(nested, tuple)
                flattened.extend(nested)
            else:
                flattened.append(child)
        if len(flattened) == 1:
            return flattened[0]
        return ("mrow", (), "", tuple(flattened))
    if qname.localname == "mfenced":
        fenced_children = children
        if len(element) == 1 and etree.QName(element[0]).localname == "mrow":
            fenced_children = tuple(_semantic_fingerprint(child) for child in element[0])
        open_token = ("mo", (), element.get("open", "("), ())
        close_token = ("mo", (), element.get("close", ")"), ())
        return ("mrow", (), "", (open_token, *fenced_children, close_token))
    if qname.localname == "msup" and len(children) == 2 and children[0][0] == "msub":
        subscripted_children = children[0][3]
        assert isinstance(subscripted_children, tuple)
        return (
            "msubsup",
            attributes,
            text,
            (*subscripted_children, children[1]),
        )
    return (qname.localname, attributes, text, children)


def mathml_semantically_equivalent(left: str, right: str, *, display: bool) -> bool:
    """Compare safe Presentation MathML while normalizing redundant sequence wrappers."""
    return _semantic_fingerprint(
        parse_mathml_fragment(left, display=display)
    ) == _semantic_fingerprint(parse_mathml_fragment(right, display=display))
