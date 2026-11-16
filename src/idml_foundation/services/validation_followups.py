"""Content-free next actions for trusted, persisted validation summaries.

This projection never accepts warnings, changes a query status or refreshes evidence.
The caller must first check the enclosing package/run bindings.
"""

import re
from typing import Any

from idml_foundation.release.xpm_query_requirements import (
    NATIVE_PROOF_SHA256,
    NORMATIVE_SHA256,
    WaytaServiceObservation,
)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _row(code: str, title: str, detail: str, action: str, **extra: Any) -> dict[str, Any]:
    return dict(
        category="tool",
        code=code,
        status="action-required",
        title=title,
        detail=detail,
        next_action=action,
        **extra,
    )


def warning_followup(
    source: str, count: int, candidate: str, report: str | None = None
) -> dict[str, Any]:
    """Counts cannot identify or approve individual findings."""
    return _row(
        f"{source}-warnings-review",
        f"{source}: tratamento de avisos",
        "Há avisos registrados. Este resumo não contém decisões por ocorrência; "
        "a contagem não informa quais foram corrigidos ou aceitos.",
        "Consultar o relatório desta versão, identificar cada ocorrência e confrontar com "
        "IDML/PDF e fontes autorizadas. Registrar a justificativa e revalidar após correção.",
        counts={"warning": count},
        candidate_sha256=candidate,
        **({"report_sha256": report} if report else {}),
    )


def query_followups(selected: Any) -> list[dict[str, Any]]:
    unavailable = [
        _row(
            "selected-query-evidence-unavailable",
            "Consultas: detalhamento indisponível",
            "Faltam resultados consistentes das consultas selecionadas para esta execução.",
            "Reexecutar a coleta e validação das fontes para este pacote; não usar resposta "
            "de outro artigo ou considerar uma consulta ausente como aprovada.",
        )
        | {"status": "unavailable"}
    ]
    if not isinstance(selected, dict) or (
        selected.get("version") != "xpm-selected-query-assessment-1.0"
        or selected.get("required_queries_complete") is not False
        or selected.get("authenticated_orcid_ownership") is not False
    ):
        return unavailable
    checks = selected.get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 17:
        return unavailable
    seen = set()
    rows = []
    crossref = None
    orcids = set()
    public_diagnostics = {
        "public-name-incomplete": (
            "O registro público não contém nome suficiente para a comparação exata.",
            "Conferir a identificação nas fontes autorizadas; solicitar confirmação editorial "
            "se a informação pública continuar incompleta. Não completar nomes por suposição.",
        ),
        "public-name-not-exact": (
            "O nome público não coincide exatamente com o nome no artigo.",
            "Comparar o autor e o ORCID com as fontes autorizadas. Corrigir somente com "
            "evidência explícita e revalidar; não substituir identificadores por similaridade.",
        ),
        "public-name-unavailable": (
            "O nome público não está disponível para comparação.",
            "Conferir uma fonte autorizada de identificação e registrar a pendência; "
            "ausência de nome público não demonstra que o identificador está incorreto.",
        ),
        "public-record-invalid": (
            "O registro público não pôde ser interpretado com segurança.",
            "Repetir a consulta e verificar o formato da resposta antes de comparar o autor.",
        ),
    }
    for check in checks:
        if not isinstance(check, dict):
            return unavailable
        kind, identity = check.get("kind"), check.get("identifier_sha256")
        state, reason, receipt = (
            check.get("status"),
            check.get("reason"),
            check.get("response_sha256"),
        )
        if kind not in ("crossref", "orcid") or not _sha(identity):
            return unavailable
        key = (kind, identity)
        if key in seen:
            return unavailable
        seen.add(key)
        label = "Crossref" if kind == "crossref" else "ORCID"
        if kind == "crossref":
            if crossref is not None:
                return unavailable
            crossref = check
        else:
            orcids.add(identity)
        status = "action-required"
        if state == "unavailable" and reason == "authority-unavailable" and receipt is None:
            detail = "A fonte externa estava indisponível na execução registrada."
            action = "Repetir a consulta para este pacote. Não alterar o XML por falha de rede."
            status = "unavailable"
        elif state == "matched" and reason == "exact-public-record-match" and _sha(receipt):
            if kind == "orcid" and check.get("public_name_check") != "exact-public-name-match":
                return unavailable
            detail = (
                "Nome público coincidente na consulta registrada; titularidade não autenticada."
                if kind == "orcid"
                else "Metadados coincidentes na consulta registrada."
            )
            action = (
                "Manter a evidência vinculada a esta versão; renovar a consulta na revalidação."
            )
            status = "observed"
        elif (
            state == "conflict" and reason == "authority-response-does-not-match" and _sha(receipt)
        ):
            if kind == "orcid":
                diagnostic = check.get("public_name_check")
                if not isinstance(diagnostic, str) or diagnostic not in public_diagnostics:
                    return unavailable
                detail, action = public_diagnostics[diagnostic]
            else:
                detail = "Os metadados consultados não coincidem com os dados do artigo."
                action = "Conferir DOI, periódico, título e autores nas fontes; corrigir com "
                action += "evidência ou registrar o conflito para revisão e revalidar."
        else:
            return unavailable
        rows.append(
            _row(
                f"query-{kind}-{identity}",
                f"{label}: consulta registrada",
                detail,
                action,
                identifier_sha256=identity,
                source_status=state,
                **({"report_sha256": receipt} if receipt else {}),
            )
            | {"status": status}
        )
    if crossref is None:
        return unavailable

    links = selected.get("crossref_author_links")
    if not isinstance(links, dict) or (
        links.get("version") != "orcid-deposit-diagnostic-1.0"
        or links.get("authenticated_ownership") is not False
    ):
        return unavailable
    if crossref["status"] != "matched":
        if links.get("status") != "unavailable" or links.get("checks") != []:
            return unavailable
        return [
            *rows,
            _row(
                "crossref-links-unavailable",
                "ORCID no Crossref: vínculo não verificado",
                "Verificar o depósito depende primeiro da correspondência dos metadados Crossref.",
                "Resolver a consulta Crossref e repetir a verificação dos vínculos autor/ORCID.",
            )
            | {"status": "unavailable"},
        ]
    link_checks = links.get("checks")
    if (
        links.get("status") != "assessed"
        or links.get("response_sha256") != crossref["response_sha256"]
        or not isinstance(link_checks, list)
        or len(link_checks) != len(orcids)
    ):
        return unavailable
    seen_links = set()
    link_messages = {
        ("matched", "exact-deposited-author-orcid-link"): (
            "O depósito vincula esse ORCID ao autor; isso não autentica sua titularidade.",
            "Preservar o vínculo e conferir separadamente o resultado do registro público ORCID.",
        ),
        ("not-deposited", "author-orcid-not-deposited"): (
            "O depósito Crossref não informa ORCID para o autor; isso não é uma divergência.",
            "Verificar a identificação nas demais fontes autorizadas; não remover o ORCID "
            "do XML apenas por ausência no depósito.",
        ),
        ("conflict", "deposited-author-orcid-mismatch"): (
            "O ORCID depositado difere do identificador do autor no artigo.",
            "Confrontar as fontes e resolver o conflito antes da aprovação; não substituir "
            "automaticamente pelo valor do depósito.",
        ),
        ("conflict", "deposited-author-orcid-invalid"): (
            "O depósito contém um identificador ORCID inválido.",
            "Conferir a fonte do identificador e registrar a inconsistência no depósito.",
        ),
        ("unavailable", "ambiguous-author-name"): (
            "O nome não permite vincular o identificador a um único autor com segurança.",
            "Obter evidência que diferencie os autores antes de vincular o ORCID.",
        ),
    }
    for link in link_checks:
        if not isinstance(link, dict):
            return unavailable
        identity, state, reason = (
            link.get("identifier_sha256"),
            link.get("status"),
            link.get("reason"),
        )
        if not _sha(identity) or identity not in orcids or identity in seen_links:
            return unavailable
        if not isinstance(state, str) or not isinstance(reason, str):
            return unavailable
        message = link_messages.get((state, reason))
        if message is None:
            return unavailable
        seen_links.add(identity)
        rows.append(
            _row(
                f"crossref-orcid-link-{identity}",
                "Crossref: vínculo autor/ORCID",
                *message,
                identifier_sha256=identity,
                source_status=state,
                report_sha256=links["response_sha256"],
            )
            | {
                "status": "observed"
                if state in ("matched", "not-deposited")
                else "unavailable"
                if state == "unavailable"
                else "action-required"
            }
        )
    return rows


def wayta_followup(compatibility: Any) -> dict[str, Any]:
    unavailable = _row(
        "wayta-evidence-unavailable",
        "Wayta: aplicabilidade pendente",
        "Não há diagnóstico consistente da aplicabilidade e disponibilidade do serviço.",
        "Conferir as afiliações nas fontes autorizadas e reexecutar a verificação de "
        "aplicabilidade. A falta de resposta do serviço não valida uma instituição.",
    ) | {"status": "unavailable"}
    if not isinstance(compatibility, dict) or compatibility.get("status") != "assessed":
        return unavailable
    value = compatibility.get("wayta")
    if not isinstance(value, dict) or (
        value.get("policy_version") != "xpm-wayta-requirement-1.0"
        or value.get("requirement") not in ("advisory_for_qualified_profile", "undetermined")
        or value.get("normative_sha256") != NORMATIVE_SHA256
        or value.get("native_proof_sha256") != NATIVE_PROOF_SHA256
        or not _sha(value.get("service_report_sha256"))
        or value.get("mandatory_affiliation_validation_required") is not True
        or any(
            value.get(k) is not False
            for k in (
                "article_query_completed",
                "institution_identity_verified",
                "homologation_ready",
                "release_approved",
            )
        )
    ):
        return unavailable
    try:
        observation = WaytaServiceObservation.model_validate(value.get("service_observation"))
    except ValueError:
        return unavailable
    outcome = {
        "timeout": "Tempo de resposta esgotado",
        "http_response": "Resposta HTTP recebida",
        "blocked_address": "Endereço bloqueado",
        "response_too_large": "Resposta acima do limite",
        "dns_error": "Falha de resolução de endereço",
        "tls_error": "Falha de conexão segura",
        "connection_error": "Falha de conexão",
    }[observation.outcome]
    return _row(
        "wayta-service-observation",
        "Wayta: observação do serviço",
        f"{outcome} na execução registrada. "
        + (
            "Consulta consultiva para o perfil qualificado. "
            if value["requirement"] == "advisory_for_qualified_profile"
            else "Aplicabilidade ainda não determinada. "
        )
        + "A observação não consultou a instituição do artigo nem confirmou sua identidade.",
        "Validar obrigatoriamente as afiliações com as fontes autorizadas. Repetir a observação "
        "do serviço na próxima execução; separar disponibilidade e identidade institucional.",
        report_sha256=value["service_report_sha256"],
    )
