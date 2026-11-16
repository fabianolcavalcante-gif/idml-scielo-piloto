# Revisão do Gate G3 — Pipeline determinístico mínimo

- Data: 2026-08-24
- Ambiente: desenvolvimento local + stack isolada na VPS
- Decisão: `APPROVED`
- Próxima fase: não autorizada
- Produção: não autorizada

## Evidências locais

- corpus real ESA conferido por SHA-256 antes da avaliação;
- 46 Stories, 55 TextFrames, 6 Spreads, 4 tabelas e 20 links de assets extraídos;
- integridade das cadeias de frames: 100%, sem ciclo, gap ou link não recíproco;
- 12 Stories sem frame classificadas e preservadas via fallback auditável;
- 3 autores, 3 afiliações e 52 referências reconstruídos, iguais às contagens
  aprovadas do corpus;
- JATS Publishing 1.3 MathML3 válido pela DTD oficial local;
- regras SPS baseline: zero errors/warnings no XML produzido;
- duas execuções produziram Raw, Canonical, XML e relatório idênticos;
- SHA-256 do XML do Gate:
  `7d31dae2b97541b22648bd7683535aa0f2ee5c177073f9b665e7ef02aa74ded3`;
- 45 testes aprovados; cobertura total 84,53%; Ruff e mypy strict aprovados.

O comando de evidência é:

```text
python ops/gate_g3.py --idml <ESA_IDML_RESTRITO> --gold-xml <ESA_XML_GOLD_RESTRITO>
```

O gold é lido somente pelo gate para hashes e contagens. Não entra no pipeline.
Nenhum conteúdo ou binário restrito foi copiado para Git, imagem ou VPS.

## Evidência posterior — citações bibliográficas

Em 2026-08-26, o Gate G3 passou a medir também os alvos bibliográficos. O resolvedor offline gerou
81 `xref` para os 52 alvos, com XML válido e zero issue local. Contra os 78 vínculos aprovados, a
comparação bruta obteve precisão 0,925926, recall 0,961538 e F1 0,943396, mantendo a submétrica em
`needs_review`. As seis divergências foram registradas sem conteúdo restrito em
`benchmarks/agents/reports/esa-crossrefs-v1-report.json`; o XML aprovado permanece exclusivamente
oráculo do gate e não é consultado em runtime.

## Checklist G3

| Critério | Evidência | Resultado |
|---|---|---|
| Artigo real gera XML sem IA | ESA e20240086, DTD/SPS baseline válidos | Aprovado |
| Idempotência | duas execuções com modelos e bytes idênticos | Aprovado |
| Reprodutibilidade | versões de profile, schema, builder e DTD fixadas | Aprovado |
| Reading order | 55/55 frames, integridade de thread 100% | Aprovado |
| Sem correção silenciosa | 19 motivos de revisão + Raw integral | Aprovado |
| Falhas auditáveis | ReadingOrderIssue e ValidationReport normalizados | Aprovado |

## Evidências na VPS

A imagem `idml-foundation:phase3`, ID
`sha256:abcb5d16f7bfa7c607ce48439c2e2357d6c29bd25a1430c4dd57d9056eb17a76`,
contém código, profile ESA e DTD vendorizada. O smoke test offline executou a
conversão sintética em container sem rede e read-only, com zero issues, e
conferiu os 64 hashes da distribuição JATS.

API e worker estão healthy. PostgreSQL/Redis não foram recriados e a migration
permanece no head `8af62bb716cf`. O Compose `idml-development` mantém a API
somente em `127.0.0.1:18080`; banco e Redis não publicam portas no host.
Consumo após o deploy: API 67,11 MiB/256 MiB; worker 51,07 MiB/256 MiB;
PostgreSQL 13,85 MiB/384 MiB; Redis 2,51 MiB/96 MiB.

OpenClaw permaneceu `2026.6.11`, healthy e vinculado a `127.0.0.1:47716`.
Mapalead permaneceu ativo; nenhum serviço desses projetos foi recriado ou
alterado. O timer de backup do IDML continua ativo.

## Restrições transportadas

- o XML é formalmente válido, mas permanece `NEEDS_REVIEW`;
- fidelidade integral contra PDF/XML, equações, notas, captions/assets e a
  divergência 4 IDML versus 3 tabelas são trabalho da Fase 4;
- Packtools, XPM, Package Builder e Release Policy ainda não foram integrados;
- o artigo real restrito não foi enviado à VPS;
- produção continua fora de escopo.

O Gate G3 está aprovado. A Fase 4 aguarda autorização explícita.
