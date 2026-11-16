import hashlib
from datetime import timedelta
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from idml_foundation.domain.canonical import CanonicalArticle
from idml_foundation.services.autocorrection_sources import (
    ExtractionGrant,
    SourceResolutionError,
    resolve_idml_evidence,
)
from tests.autocorrection_helpers import source_data


def request(data, settings, index=0):
    return dict(
        article=data["article"],
        operation=data["intent"].operations[index],
        scope=data["context"].scope,
        grant=data["grants"][index],
        idml=data["idml"],
        assets={"asset-1": data["asset"]},
        settings=settings,
        now=data["now"],
    )


def rewrite_source(args, *, member=None, locator=None, text=None):
    if member is not None:
        output = BytesIO()
        with ZipFile(BytesIO(args["idml"])) as source, ZipFile(output, "w") as target:
            for name in source.namelist():
                target.writestr(
                    name, member if name == "Stories/Story_u1.xml" else source.read(name)
                )
        args["idml"] = output.getvalue()
    digest = hashlib.sha256(args["idml"]).hexdigest()
    args["scope"] = args["scope"].model_copy(update={"source_idml_sha256": digest})
    raw = args["article"].model_dump(mode="json")
    selected = next(e for e in raw["evidence"] if e["id"] == args["operation"].evidence_id)
    selected["locator"].update(artifact_sha256=digest, **(locator or {}))
    if text is not None:
        selected["content_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    args["article"] = CanonicalArticle.model_validate(raw)
    selected_model = next(
        e for e in args["article"].evidence if e.id == args["operation"].evidence_id
    )
    args["grant"] = args["grant"].model_copy(
        update={
            "scope": args["scope"],
            "locator": selected_model.locator,
            "source_text_sha256": selected_model.content_sha256,
        }
    )


@pytest.mark.parametrize(
    "index,text", [(0, "Brazil"), (1, "article-gf01.jpg"), (2, "Example University, City, Brazil")]
)
def test_exact_bytes_produce_field_bound_evidence(settings, index, text):
    args = request(source_data(), settings, index)
    evidence = resolve_idml_evidence(**args)
    assert evidence.source_text == text
    assert evidence.source_text_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert evidence.scope == args["scope"]
    assert evidence.authorization_id == args["grant"].authorization_id
    assert evidence.extraction_sha256 != evidence.source_text_sha256


@pytest.mark.parametrize(
    "change,code",
    [
        ("idml", "idml_hash_mismatch"),
        ("scope", "extraction_scope_mismatch"),
        ("operation", "extraction_operation_mismatch"),
        ("expired", "extraction_grant_expired"),
        ("naive", "clock_timezone_required"),
        ("binding", "extraction_binding_mismatch"),
        ("asset", "asset_bytes_mismatch"),
        ("missing_asset", "asset_bytes_missing"),
    ],
)
def test_untrusted_or_stale_inputs_refused(settings, change, code):
    args = request(source_data(), settings, 1 if "asset" in change else 0)
    if change == "idml":
        args["idml"] += b"corruption"
    elif change == "scope":
        args["scope"] = args["scope"].model_copy(update={"organization_id": uuid4()})
    elif change == "operation":
        args["operation"] = args["operation"].model_copy(update={"subject_id": "different"})
    elif change == "expired":
        args["now"] = args["grant"].expires_at
    elif change == "naive":
        args["now"] = args["now"].replace(tzinfo=None)
    elif change == "binding":
        args["grant"] = args["grant"].model_copy(update={"source_text_sha256": "f" * 64})
    else:
        args["assets"] = {} if change == "missing_asset" else {"asset-1": b"bad"}
    with pytest.raises(SourceResolutionError, match=f"^{code}$"):
        resolve_idml_evidence(**args)


@pytest.mark.parametrize(
    "member,code",
    [
        (
            b'<Story><Content Self="country">Brazil</Content>'
            b'<Content Self="country">Brazil</Content></Story>',
            "extraction_element_not_unique",
        ),
        (b'<Story><Content Self="other">Brazil</Content></Story>', "extraction_element_not_unique"),
        (
            b'<Story Self="country"><Table><Content>Brazil</Content></Table></Story>',
            "unsupported_idml_text",
        ),
        (
            b'<Story Self="country"><Content>Brazil<Unknown/></Content></Story>',
            "unsupported_idml_text",
        ),
        (b'<Story Self="country"><Content>Brazil</Content>lost</Story>', "unsupported_idml_text"),
        (b'<Story Self="country"><Content>India</Content></Story>', "extraction_text_mismatch"),
        (
            b'<!DOCTYPE Story [<!ENTITY x SYSTEM "file:///private">]>'
            b'<Story Self="country"><Content>&x;</Content></Story>',
            "idml_extraction_unavailable",
        ),
        (b"<Story", "idml_extraction_unavailable"),
    ],
)
def test_no_guessing_no_silent_omissions_or_xml_entities(settings, member, code):
    args = request(source_data(), settings)
    rewrite_source(args, member=member)
    with pytest.raises(SourceResolutionError, match=f"^{code}$"):
        resolve_idml_evidence(**args)


def test_offsets_are_exact_unicode_character_offsets(settings):
    args = request(source_data(), settings)
    rewrite_source(
        args,
        member='<Story Self="country"><Content>á Brazil</Content><Br/></Story>'.encode(),
        locator={"start_offset": 2, "end_offset": 8},
    )
    assert resolve_idml_evidence(**args).source_text == "Brazil"


@pytest.mark.parametrize("start,end", [(0, None), (0, 0), (0, 7), (7, 8)])
def test_invalid_offsets_refused(settings, start, end):
    args = request(source_data(), settings)
    rewrite_source(args, locator={"start_offset": start, "end_offset": end})
    with pytest.raises(SourceResolutionError, match="extraction_offsets_invalid"):
        resolve_idml_evidence(**args)


@pytest.mark.parametrize(
    "name", ["file:/article-gf01.jpg", "../article-gf01.jpg", "https://example.test/x", ".", ""]
)
def test_link_is_not_a_path_or_network_request(settings, name):
    args = request(source_data(), settings, 1)
    rewrite_source(args, member=f'<Link Self="link" LinkResourceURI="{name}"/>'.encode())
    with pytest.raises(SourceResolutionError, match="unsupported_idml_link"):
        resolve_idml_evidence(**args)


@pytest.mark.parametrize("change", ["long", "reversed", "wrong_source"])
def test_grant_has_bounded_dates_and_source(change):
    grant = source_data()["grants"][0].model_dump(mode="python")
    if change == "long":
        grant["expires_at"] += timedelta(days=31)
    elif change == "reversed":
        grant["issued_at"] = grant["expires_at"]
    else:
        grant["locator"] = grant["locator"] | {"artifact_sha256": "f" * 64}
    with pytest.raises(ValidationError):
        ExtractionGrant.model_validate(grant)
