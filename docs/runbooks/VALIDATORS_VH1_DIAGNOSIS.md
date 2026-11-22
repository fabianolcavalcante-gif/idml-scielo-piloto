# Validadores formais "indisponíveis" (Packtools / SPSvalidator / XPM) — diagnóstico e correção

## Sintoma
`scielo.package` termina `succeeded`, mas `formal_validation.state = validation-unavailable` e o diagnóstico mostra
"packtools: resultado indisponível", "spsvalidator: resultado indisponível" (e às vezes XPM).

## Como a validação funciona (resumo do código)
- O worker chama os brokers por sockets Unix montados só no worker
  (`IDML_VALIDATOR_SOCKET=/run/idml-modern-vh1/validator.sock`, `IDML_XPM_SOCKET=/run/idml-xpm-vh1/validator.sock`).
- Com `IDML_VALIDATOR_SCOPED_AUTHORITIES=true`, cada execução é **escopada** (empresa, artigo, SHA-256 do IDML, do XML
  e do pacote, perfil). O broker (`ops/scoped_validator_broker.py`) só executa se existir um **bundle de autoridade +
  grant ativo e não vencido** para aquele escopo exato (`ops/scoped_authority_transport.py`).
- Com `runtime_article_authorization: true` no registro do broker, o supervisor (`ops/runtime_source_authority.py`)
  **cria o bundle sozinho**, se: (a) o artigo tem "Fontes públicas" autorizadas e vigentes; (b) o XML tem **exatamente
  um DOI resolvível no Crossref** (`expected.doi == 1`).
- Qualquer exceção vira `unavailable`. **A partir desta versão** o resultado traz `failure_reason` (código fixo, sem
  conteúdo) e o worker registra `validator unavailable` no log.

## O que os testes mostraram (QA externo, 2026-11-18/22)
| Situação | packtools / spsvalidator | XPM |
|---|---|---|
| Artigo sintético, sem DOI real | unavailable | unavailable |
| Reenvio de artigo real | pacote recusado antes (vínculo de equação ausente) | — |
| Sintético com **DOI real** + Fontes públicas autorizadas | **unavailable** | **completed** |

⇒ O transporte escopado e a coleta automática funcionam (XPM concluiu). O defeito está **isolado no broker
"modern"** (packtools/spsvalidator).

## Verificação na VPS (administrador)
```sh
systemctl status idml-validation-modern-vh1.service idml-validation-xpm-vh1.service
journalctl -u idml-validation-modern-vh1.service --since "2026-11-14" | tail -80
ls -la /run/idml-modern-vh1/validator.sock /run/idml-xpm-vh1/validator.sock
python3 -c 'import json;d=json.load(open("/var/lib/idml-validation-vh1/modern.json"));print(d.get("runtime_article_authorization"), d.get("authority_root"))'
docker image ls | grep -Ei "packtools|spsvalidator"
# dentro do worker (sem dados de artigo):
docker exec idml-development-worker-1 idml-admin validators-status
```
Causas prováveis, em ordem: (1) serviço `modern` parado/falhando; (2) `modern.json` sem
`runtime_article_authorization: true` (ex.: reescrito por outro script de implantação); (3) imagem packtools/
spsvalidator com digest diferente de `tool_sha256` do registro (`external evidence mismatch`).

## Correção
1. Restabelecer o serviço `modern` e o flag `runtime_article_authorization: true` em `modern.json`
   (ver `ops/deploy_article_sources.py`, que já faz isso com backup e rollback).
2. Conferir `tool_sha256`/versões do registro do broker × `config/validator-registry-vh1-composed.json` do worker.
3. Incluir `idml-admin validators-status` no comando `status` do SSH, para que a indisponibilidade apareça no
   diagnóstico externo (hoje o `status` só cobre API, banco e Redis).
4. Reenfileirar um pacote de artigo **com DOI real e Fontes públicas autorizadas** e confirmar
   `external_runs[*].status = completed`.

## Limitação de desenho (decisão do proprietário)
Artigos sem DOI registrado no Crossref (manuscritos ainda não publicados) nunca obterão bundle automático. Opções:
(a) modo não escopado para packtools/spsvalidator (o worker já suporta `LocalValidatorExecutor`; o settings exige
modo escopado para XPM); (b) bundle sem DOI para AOP; (c) validação local com packtools ≥ 4.18 como pré-checagem.
