# Revisão do Gate G5 — Revisão humana e interface mínima

- Data: 2026-08-26
- Ambiente: desenvolvimento local e runtime de desenvolvimento na VPS
- Decisão local: `APPROVED`
- Gate G4: permanece `BLOCKED`
- Produção: não autorizada

## Checklist G5

| Critério | Evidência | Estado |
|---|---|---|
| Corrigir sem editar XML | API aplica patch no modelo e reconstrói JATS | Aprovado |
| Bloquear usuário sem permissão | release manager recebe 403 em decisão de revisão | Aprovado |
| Isolamento entre empresas | identificador de outro tenant retorna 404 | Aprovado |
| Controle de concorrência | versão obsoleta retorna 409 | Aprovado |
| Nova versão e revalidação | snapshot filho + ReviewBuild/validação | Aprovado |
| Histórico íntegro | snapshots, decisões e builds append-only | Aprovado |
| Reconstrução pelo auditor | ator, empresa, patch/hash, diff, XML e auditoria | Aprovado |
| MFA em ações sensíveis | TOTP/recovery/replay e sessão MFA testados | Aprovado |
| Dupla aprovação | solicitante bloqueado e dois aprovadores distintos | Aprovado |
| Separação do gate técnico | estado `editorially_approved`, nunca READY | Aprovado |

## Verificações locais

- `ruff check .`: aprovado;
- `mypy src`: aprovado;
- `pytest`: 57 testes aprovados;
- cobertura: 85,26%, acima do mínimo de 80%;
- Alembic: upgrade até `c4e5f6a7b8c9`, downgrade para `8af62bb716cf` e novo
  upgrade aprovados em banco efêmero.

## Riscos residuais

- TOTP é o único segundo fator nesta fase; WebAuthn pode ser acrescentado;
- rate limiting distribuído deve preceder exposição pública da interface;
- a UI é deliberadamente mínima e não substitui testes de acessibilidade/UX;
- a aprovação editorial não resolve os erros SPS nem a ausência do XPM que
  mantêm o Gate G4 bloqueado.

## Evidências na VPS

A imagem `idml-foundation:phase5`, ID
`sha256:9ce77ba57e8270917f20e4691d02cac723b857af15c335f2e204ac672f1374b3`,
foi construída com locks e hashes. API e worker ficaram healthy; a API respondeu
database/Redis `ok`, serviu `/app` com CSP e expôs as rotas de MFA, revisão,
aprovação e auditoria. A migration PostgreSQL ficou em `c4e5f6a7b8c9`.

PostgreSQL e Redis não foram recriados. O consumo observado foi: API 75,32 MiB,
worker 51,05 MiB, PostgreSQL 17,91 MiB e Redis 1,805 MiB. A imagem `phase4`
`sha256:f2a5fba2e25278d2efdc97f1ddfcf2618d1b34947c60c19070b8ffc99da4a8ca`
permanece disponível para rollback.

Foi gerado backup modo 600 em `backups/20260826T145036Z`; hashes foram
verificados e o restore isolado passou com 19 tabelas públicas e um artefato
sintético. O timer diário permanece ativo. OpenClaw 2026.6.11 e Mapalead
permaneceram healthy. Nenhum artefato do corpus restrito foi enviado à VPS.

## Condição da próxima fase

O Gate G5 autoriza iniciar a Fase 6 de IA assistiva. Isso não autoriza produção,
nem habilita OpenClaw, nem amplia a autoridade de IA sobre release.
