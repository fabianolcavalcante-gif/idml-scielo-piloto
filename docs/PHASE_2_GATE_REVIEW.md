# Revisão do Gate G2 — Corpus e modelo de domínio

- Data: 2026-08-24
- Ambiente: desenvolvimento local + stack isolada na VPS
- Decisão: `APPROVED`
- Próxima fase: não autorizada
- Produção: não autorizada

## Evidências locais

- seis manifestos e 21 arquivos reais conferidos por tamanho e SHA-256;
- nenhum binário/texto do corpus copiado para Git, CI, imagem ou VPS;
- 39 testes aprovados e cobertura de 87,65%;
- Ruff, formatação e mypy strict aprovados;
- schemas Raw, Canonical e Corpus exportados e comparados ao contrato runtime;
- migration reproduzida em upgrade/downgrade/upgrade, head `8af62bb716cf`;
- round-trip JSON sem perda, hash determinístico e IDs UUIDv5 estáveis;
- testes negativos para referências órfãs, conteúdo inline divergente, path de
  corpus inseguro e snapshot cross-tenant.

## Checklist G2

| Critério | Evidência | Resultado |
|---|---|---|
| Corpus representa o piloto | ESA gold com 11 artefatos e ficha estrutural | Aprovado |
| Serialização sem perda | Raw/Canonical round-trip + JSON Schema | Aprovado |
| IDs estáveis | UUIDv5 por artigo/tipo/localizador | Aprovado |
| Proveniência | Evidence aponta SHA-256 + locator da fonte | Aprovado |
| Casos não representáveis | registrados em `CORPUS_POLICY.md` | Aprovado |
| Métricas antes do parser | targets, hard floor e decisões congelados | Aprovado |

## Evidências na VPS

- imagem `idml-foundation:phase2` saudável, ID
  `sha256:4224ef8e6d040d78563ae9509a12565ae43313b0547795e0c445901477173468`;
- migration PostgreSQL aplicada no head `8af62bb716cf`;
- Raw e Canonical persistidos/restaurados como snapshots imutáveis;
- repetição do mesmo conteúdo retornou o mesmo snapshot;
- gravação cross-tenant foi bloqueada;
- backup `/opt/idml-platform/backups/20260824T181444Z` validado;
- restore recriou 14 tabelas e 1 artefato em destinos temporários;
- API somente em `127.0.0.1:18080`; PostgreSQL/Redis sem porta publicada;
- timer de backup ativo.

Snapshot operacional após o gate:

- API: 68,84 MiB / 256 MiB;
- worker: 50,99 MiB / 256 MiB;
- PostgreSQL: 52,02 MiB / 384 MiB;
- Redis: 7,69 MiB / 96 MiB;
- disco: 21 GB livres;
- memória disponível: aproximadamente 795 MiB no instante da medição.

Durante o deploy, a recriação do Redis revelou que seu entrypoint precisa de
`DAC_READ_SEARCH` para inspecionar o diretório AOF persistente com permissões 700.
A capability mínima foi adicionada; o volume permaneceu íntegro e o serviço
voltou healthy. Deploys rotineiros não devem forçar recriação do PostgreSQL/Redis.

## Restrições transportadas

- a Fase 2 não implementa parser IDML, mapping nem XML builder;
- nenhum artigo real foi convertido para Raw/Canonical; isso é Gate G3;
- o holdout RBEdu não substitui um conjunto futuro de homologação ESA;
- snapshots ainda são serviço interno, sem endpoints/telas;
- métricas de STP, custo e tempo só serão medidas com pipeline real;
- ClamAV, OpenClaw e produção continuam fora deste escopo.

O Gate G2 está aprovado. A Fase 3 aguarda autorização explícita.
