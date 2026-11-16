# Revisão do Gate G4 — Validação, fidelidade e pacote

- Data: 2026-08-24
- Ambiente: desenvolvimento local; runtime da API também validado na VPS
- Decisão: `BLOCKED`
- Motivo primário: XPM não executado para o candidato e erros SPS/editoriais
- Fase 5: não autorizada
- Produção: não autorizada

## Evidências do candidato real

| Evidência | Resultado |
|---|---:|
| IDML conferido | SHA-256 `8ce185f5...44d2c` |
| XML resolvido | SHA-256 `81c2bba2...4d812` |
| ZIP determinístico | SHA-256 `de4efc6c...a080a` |
| Tamanho do ZIP | 1.084.422 bytes |
| Páginas PDF | 10 |
| Figuras / tabelas / referências | 5 / 3 / 52 |
| Offline JATS/SPS baseline | válido, zero issues |
| SPSValidator obrigatório | executado, resultado inválido |
| Packtools StyleChecker clássico | incompatível com SPS 1.10/JATS 1.3 |
| XPM do mesmo SHA | indisponível |

O Package Builder gerou bytes idênticos em duas execuções. Os cinco assets
foram conferidos pelo manifesto e entregues como `...-gf01.jpg` a
`...-gf05.jpg`; os hrefs do XML apontam para esses mesmos basenames.

## Fidelidade

| Componente | Recall no PDF | Recall no XML |
|---|---:|---:|
| Títulos | 100% | 100% |
| Autores | 100% | 100% |
| Corpo | 98,9725% | 99,6881% |
| Referências | 99,9454% | 100% |
| Figuras e tabelas | 100% | 100% |

O PDF tem camada textual; OCR não foi acionado. O hard floor de fidelidade foi
superado, mas o corpo permanece abaixo do target de 99,5%, portanto exige
revisão e não é STP.

## Pendências normalizadas

O SPSValidator retornou 130 itens: 68 `ERROR`, 41 `CRITICAL`, 21 `WARNING`, além
de 3 exceções registradas pelo executor. Os grupos incluem datas editoriais,
metadados SPS, estrutura de contribuições, `element-citation`, IDs de gráficos,
citações bibliográficas e xrefs de figuras/tabelas. Corrigir isso requer ampliar
o modelo/mapeamento ou decisão humana; o reparador formal não inventa dados.

O relatório XPM histórico do corpus foi parseado (XPM `4.0.096`, 0 blocking,
0 fatal, 1 error e 119 warnings), mas ele pertence ao pacote aprovado histórico.
Por não ter o SHA do candidato atual, não foi aceito pela Release Policy.

## Checklist G4

| Critério | Estado |
|---|---|
| Pacote construído antes do XPM | Aprovado |
| Validadores SPS 1.10 obrigatórios executados | Aprovado |
| Release Policy versionada e testada | Aprovado |
| ConversionManifest auditável | Aprovado |
| Fidelidade acima do hard floor | Aprovado, requer revisão abaixo do target |
| SPSValidator sem erros | Bloqueado |
| XPM executado para o mesmo SHA-256 | Bloqueado |
| `READY_FOR_SCIELO` | Negado corretamente |

## Condições para reabrir G4

1. resolver os erros SPS sem copiar conteúdo do XML gold;
2. tratar as pendências editoriais via fonte ou revisão humana;
3. reconstruir o ZIP e repetir fidelidade/SPSValidator;
4. executar XPM no Windows Worker sobre esse ZIP exato;
5. anexar resultado autenticado com versão, tool hash, report hash e package hash.

## Evidências na VPS

A imagem `idml-foundation:phase4`, ID
`sha256:f2a5fba2e25278d2efdc97f1ddfcf2618d1b34947c60c19070b8ffc99da4a8ca`,
foi construída com locks hash-pinned. API e worker ficaram healthy; o smoke test
sem rede/read-only converteu o IDML sintético, declarou `sps-1.10` e validou a
DTD sem issues. A migration permaneceu em `8af62bb716cf`.

PostgreSQL e Redis não foram recriados. O consumo observado foi: API 66,83 MiB,
worker 50,83 MiB, PostgreSQL 12,21 MiB e Redis 1,30 MiB. A imagem `phase3`
permanece disponível para rollback.

OpenClaw permaneceu na imagem `2026.6.11`, healthy em
`127.0.0.1:47716`; Mapalead permaneceu healthy. O timer de backup segue ativo.
Nenhum artefato do corpus real foi enviado à VPS.
