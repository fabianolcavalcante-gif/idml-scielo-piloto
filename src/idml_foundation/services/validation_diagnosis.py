"""Read-only explanation of persisted validation results, never a release decision.

Only server-stored job results belong here. This projection does not execute tools,
refresh receipts, infer causes from article text, or accept compatibility exceptions.
"""

import re
from typing import Any

from idml_foundation.release.xpm_compatibility import TOOL_SHA256
from idml_foundation.services.validation_followups import (
    query_followups,
    warning_followup,
    wayta_followup,
)

_MODERN_COUNTS = ("blocking", "critical", "error", "warning")
_XPM_COUNTS = ("blocking_errors", "fatal_errors", "errors", "warnings")
_JATS13_PROFILES = (
    "jats-1.3+sps-baseline-1.2.0",
    "jats-1.3-mathml3+sps-baseline-1.2.0",
)


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _digest(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _counts(value: Any, keys: tuple[str, ...]) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != set(keys):
        return None
    if any(type(value[key]) is not int or value[key] < 0 for key in keys):
        return None
    return {key: value[key] for key in keys}


def describe_validation(result: Any) -> dict[str, Any]:
    """Return fixed, content-free labels with hashes and original aggregate counts."""
    result = _object(result)
    rows: list[dict[str, Any]] = []

    def add(category: str, code: str, status: str, title: str, detail: str, **data: Any) -> None:
        rows.append(
            dict(category=category, code=code, status=status, title=title, detail=detail, **data)
        )

    if result.get("version") == "edit-preflight-1.0":
        state = result.get("state")
        if state == "staged" and result.get("offline_valid") is True:
            status, detail = (
                "observed",
                "Candidato separado validado localmente. O rascunho ativo foi preservado.",
            )
        elif state == "abstained" and result.get("reason") == "no_eligible_field":
            status, detail = "observed", "Nenhum campo tinha evidência suficiente para correção."
        else:
            status, detail = (
                "action-required",
                "A edição requer autorização, evidência e validação para esta revisão.",
            )
        add(
            "xml",
            "edit-preflight",
            status,
            "Verificação prévia da edição",
            detail + " Nenhum agente foi chamado.",
        )

    rejected = _object(result.get("error_detail"))
    if isinstance(rejected.get("reason"), str):
        subject = rejected.get("subject")
        add(
            "input",
            "job-input-rejected",
            "action-required",
            "Entrada recusada antes da validação",
            "O job parou antes de gerar o pacote; nenhuma validação foi executada. "
            + (f"Arquivo ou campo indicado: {subject}. " if isinstance(subject, str) else "")
            + "Corrija a entrada e enfileire novamente.",
            reason=rejected["reason"],
        )
        return dict(
            version="validation-diagnosis-1.0",
            basis="stored-job-result",
            notice="Resultado salvo deste job. Não executa nem renova validações ou consultas.",
            package_sha256=None,
            xml_sha256=None,
            items=rows,
            approval_granted=False,
            modifies_validation=False,
        )

    package_sha = _digest(result.get("package_sha256"))
    bindings = _object(result.get("figure_bindings"))
    if package_sha and bindings.get("version") == "package-figure-bindings-1.0":
        figures = bindings.get("figures")
        listed = _object(result.get("manifest")).get("files")
        if isinstance(listed, list) and isinstance(figures, list):
            assets = {
                r["name"]: r.get("sha256")
                for r in listed
                if isinstance(r, dict)
                and r.get("role") == "asset"
                and isinstance(r.get("name"), str)
            }
            if (
                bindings.get("package_sha256") == package_sha
                and len(figures) == len(assets)
                and all(
                    isinstance(f, dict)
                    and isinstance(f.get("package_name"), str)
                    and _digest(f.get("sha256"))
                    and assets.get(f["package_name"]) == f["sha256"]
                    and type(f.get("canonical_origin_verified")) is bool
                    for f in figures
                )
                and len({f["package_name"] for f in figures}) == len(assets)
            ):
                unresolved = sum(not f["canonical_origin_verified"] for f in figures)
                add(
                    "xml",
                    "figure-origin-bindings",
                    "action-required" if unresolved else "observed",
                    "Figuras do pacote",
                    f"{len(figures)} arquivo(s) vinculado(s) ao XML por hash. "
                    f"Origem no documento canônico a confirmar: {unresolved}.",
                )
    formal = _object(result.get("formal_validation"))
    formal_bound = bool(
        package_sha
        and formal.get("version") == "package-formal-assessment-1.0"
        and formal.get("package_sha256") == package_sha
        and _digest(formal.get("xml_sha256"))
    )
    xml_sha = (
        _digest(formal.get("xml_sha256")) if formal_bound else _digest(result.get("xml_sha256"))
    )
    enrichment = _object(result.get("enrichment"))
    catalogs = _object(enrichment.get("catalog_sha256"))
    if enrichment.get("status") == "selected" and catalogs:
        add(
            "xml",
            "conversion-catalogs-selected",
            "observed",
            "Catálogos aplicados na conversão",
            f"O worker aplicou {len(catalogs)} catálogos autorizados para este artigo. "
            "Os hashes das fontes e a validade da autorização estão no resultado técnico do job.",
        )
    elif enrichment.get("status") == "no_matching_bundle":
        add(
            "xml",
            "conversion-catalogs-unmatched",
            "observed",
            "Conversão a partir do IDML",
            "Este artigo foi convertido apenas com os dados do IDML e do perfil do periódico.",
        )
    fields = _object(result.get("field_evidence"))
    if fields:
        title = "Evidências do IDML para correção automática"
        if fields.get("status") == "historical_snapshot_unprepared":
            add(
                "xml",
                "field-evidence-historical",
                "unavailable",
                title,
                "Esta conversão preservou uma versão anterior à preparação de evidências.",
            )
        elif fields.get("status") == "profile_not_qualified":
            add(
                "xml",
                "field-evidence-profile",
                "unavailable",
                title,
                "O perfil desta conversão não dispõe de regras qualificadas para correção.",
            )
        elif (
            fields.get("status") == "prepared"
            and xml_sha
            and fields.get("xml_sha256") == xml_sha
            and all(
                _digest(fields.get(k))
                for k in ("catalog_sha256", "source_sha256", "snapshot_sha256")
            )
            and all(type(fields.get(k)) is int and fields[k] >= 0 for k in ("bindings", "refused"))
            and type(fields.get("source_scanned")) is bool
        ):
            detail = (
                f"Vínculos exatos encontrados pelas três regras do perfil: {fields['bindings']}. "
                f"Verificações recusadas: {fields['refused']}."
            )
            if fields["bindings"] and not fields["source_scanned"]:
                detail += " A correção depende também da verificação antivírus do arquivo."
            add(
                "xml",
                "field-evidence-prepared",
                "observed",
                title,
                detail,
                report_sha256=fields["catalog_sha256"],
            )
        else:
            add(
                "xml",
                "field-evidence-unavailable",
                "unavailable",
                title,
                "O registro das evidências não pôde ser confirmado para este XML.",
            )
    offline = _object(result.get("validation"))
    offline_bound = bool(xml_sha and offline.get("xml_sha256") == xml_sha)
    jats13 = offline_bound and offline.get("validator_profile") in _JATS13_PROFILES
    raw_issues = offline.get("issues")
    issues = raw_issues if isinstance(raw_issues, list) else []
    offline_known = (
        offline_bound
        and isinstance(raw_issues, list)
        and all(isinstance(i, dict) and i.get("severity") in ("error", "warning") for i in issues)
        and type(offline.get("valid")) is bool
    )
    if offline_known:
        errors = sum(i["severity"] == "error" for i in issues)
        warnings = sum(i["severity"] == "warning" for i in issues)
        # An internally inconsistent stored report cannot be presented as a clean result.
        offline_known = offline["valid"] == (errors == 0)
    if offline_known:
        add(
            "xml",
            "offline-findings" if errors else "offline-no-errors",
            "action-required" if errors else "observed",
            "Validação local do XML",
            "Corrigir os achados locais e gerar uma nova versão para revalidação."
            if errors
            else "Sem erros locais registrados. Os demais validadores continuam necessários.",
            counts={"error": errors, "warning": warnings},
            candidate_sha256=xml_sha,
        )
        if any(i.get("code") == "unexpected-doctype" and i["severity"] == "error" for i in issues):
            add(
                "xml",
                "doctype-pair-mismatch",
                "action-required",
                "Cabeçalho XML incompatível",
                "O validador local recusou o par PUBLIC/SYSTEM. Regenerar o XML com o cabeçalho "
                "correto e revalidar; a limitação do XPM não dispensa essa correção.",
            )
        if warnings:
            rows.append(warning_followup("local", warnings, xml_sha or ""))
    else:
        add(
            "xml",
            "offline-evidence-unavailable",
            "unavailable",
            "Validação local indisponível",
            "Não há relatório local consistente vinculado ao XML deste resultado.",
        )

    if not formal_bound:
        add(
            "tool",
            "formal-evidence-unavailable",
            "unavailable",
            "Validação formal pendente",
            "Gerar e validar o pacote para obter resultados vinculados à mesma versão.",
        )
    else:
        runs = formal.get("external_runs")
        runs = runs if isinstance(runs, list) else []
        for name, kind, candidate in (
            ("packtools", ".xml", xml_sha),
            ("spsvalidator", ".zip", package_sha),
        ):
            matches = [r for r in runs if isinstance(r, dict) and r.get("name") == name]
            run = matches[0] if len(matches) == 1 else {}
            counts = _counts(run.get("counts"), _MODERN_COUNTS)
            if not (
                run.get("status") == "completed"
                and run.get("input_kind") == kind
                and run.get("candidate_sha256") == candidate
                and counts is not None
                and _digest(run.get("report_sha256"))
                and _digest(run.get("tool_sha256"))
            ):
                add(
                    "tool",
                    f"{name}-unavailable",
                    "unavailable",
                    f"{name}: resultado indisponível",
                    "Reexecutar o validador e conferir o vínculo com este pacote. "
                    "Falha de execução não demonstra que o XML está correto ou incorreto."
                    + (
                        f" Motivo técnico: {run['failure_reason']}."
                        if isinstance(run.get("failure_reason"), str)
                        else ""
                    ),
                )
                continue
            errors = sum(counts[key] for key in _MODERN_COUNTS[:-1])
            add(
                "xml",
                f"{name}-findings",
                "action-required" if errors else "observed",
                f"{name}: achados registrados",
                "Há achados que precisam de correção ou análise das evidências."
                if errors
                else "Sem erros registrados. Os avisos precisam de tratamento explícito.",
                counts=counts,
                report_sha256=run["report_sha256"],
                candidate_sha256=candidate,
            )
            if counts["warning"]:
                rows.append(
                    warning_followup(name, counts["warning"], candidate or "", run["report_sha256"])
                )

        xpm = _object(formal.get("xpm"))
        counts = _counts(xpm.get("counts"), _XPM_COUNTS)
        xpm_bound = (
            xpm.get("status") == "completed"
            and xpm.get("attested") is True
            and xpm.get("candidate_package_sha256") == package_sha
            and _digest(xpm.get("report_sha256"))
            and _digest(xpm.get("tool_sha256"))
            and counts is not None
        )
        if xpm_bound:
            add(
                "tool",
                "xpm-raw-findings",
                "observed",
                "XPM: resultado original",
                "Contagens originais preservadas. A causa de cada ocorrência não é determinada "
                "somente por esses totais.",
                counts=counts,
                report_sha256=xpm["report_sha256"],
                candidate_sha256=package_sha,
            )
            if counts and counts["warnings"]:
                rows.append(
                    warning_followup(
                        "xpm", counts["warnings"], package_sha or "", xpm["report_sha256"]
                    )
                )
            rows.extend(query_followups(xpm.get("selected_queries")))
            rows.append(wayta_followup(xpm.get("compatibility")))
            if (
                jats13
                and xpm.get("xpm_version") == "4.0.096"
                and xpm.get("tool_sha256") == TOOL_SHA256
            ):
                add(
                    "tool",
                    "xpm-legacy-capability",
                    "known-limitation",
                    "Limitação conhecida do XPM 4.0.096",
                    "A qualificação desta versão demonstrou que o seletor DTD não reconhece "
                    "JATS 1.3 e que o Style Checker incorporado não suporta SPS 1.10. É contexto "
                    "sobre a ferramenta, não atribuição de causa aos erros deste artigo "
                    "nem dispensa deles.",
                )
            if xpm.get("required_queries_complete") is not True:
                add(
                    "tool",
                    "xpm-queries-pending",
                    "action-required",
                    "Consultas externas pendentes",
                    "Concluir as verificações de fontes externas e identidades. Resposta de rede "
                    "ou coincidência parcial de nomes não comprova identidade.",
                )
        else:
            add(
                "tool",
                "xpm-unavailable",
                "unavailable",
                "XPM: execução indisponível",
                "Não há resultado atestado consistente para este pacote. Reexecutar a validação.",
            )

    if jats13:
        add(
            "editorial",
            "doctype-delivery-pending",
            "action-required",
            "Entrega com JATS 1.3",
            "A decisão documentada de compatibilidade mantém pendente a aceitação do novo DOCTYPE "
            "para entrega SciELO. Validade técnica não confirma aceitação editorial. Não alterar "
            "a versão do XML apenas para silenciar o XPM.",
        )
    add(
        "editorial",
        "editorial-separate",
        "separate-workflow",
        "Homologação e publicação",
        "A liberação para o especialista depende do fechamento de G-HOMOLOG. A aprovação editorial "
        "e a autorização de publicação são decisões separadas deste diagnóstico.",
    )
    return dict(
        version="validation-diagnosis-1.0",
        basis="stored-job-result",
        notice="Resultado salvo deste job. Não executa nem renova validações ou consultas.",
        package_sha256=package_sha,
        xml_sha256=xml_sha,
        items=rows,
        approval_granted=False,
        modifies_validation=False,
    )
