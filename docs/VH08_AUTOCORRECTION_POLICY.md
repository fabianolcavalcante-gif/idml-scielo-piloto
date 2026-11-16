# VH-08 — Política fechada de correções automáticas

Checkpoint inicial de 2026-10-19; requalificação em 2026-10-21, conferida em 22/10.
**Contrato/política concluídos; aplicação automática ainda não ativa.**
Este documento detalha VH-08, não cria nova fila. VH-09 segue parcial no plano único.
As descrições da entrega inicial abaixo são históricas; a persistência, os locks
humanos e a linhagem posteriores estão em `VH09_CANONICAL_HEAD_AND_RESTORE.md`.

## Lista inicial, três operações

| Operação | Único destino permitido | Condições adicionais |
|---|---|---|
| `country-code-exact` | `/front/affiliations/{i}/country_code` | Campo ausente; país literal presente e comprovado; mapa ESA 1.1 exato: Brazil/Brasil→BR, India→IN, Japan→JP |
| `figure-asset-exact` | `asset_id` de FigureBlock em `/body/{i}/…/blocks/{j}` | Vínculo ausente; IDML comprova nome lógico simples; exatamente um asset com esse nome, presente, imagem e com hash verificado; IDs já existentes |
| `affiliation-original-literal` | `/front/affiliations/{i}/original_text` | Campo ausente; extrato literal autorizado para a mesma afiliação; instituição principal não ambígua; sem reescrever nome institucional |

Índices/caminhos/valores são resolvidos pelo servidor. O agente envia apenas tipo
da operação, ID do objeto/achado/evidência, escopo e hash esperado do valor atual.
Não envia JSON Patch, texto substituto, caminho de arquivo, URL, comando ou confiança
para obter autoridade. Não há add/remove genérico, aproximação de nome ou inferência
por ordem. Não substituir valor existente, mesmo que pareça incorreto: exige outro
tratamento explícito, não ampliação silenciosa desta lista.

Fórmulas, texto científico, números/unidades, nomes/autoria, ORCID, datas, CRediT,
financiamento, licença, referências/citações e outros vínculos ficam fora. As três
famílias previstas na VH1 são representadas por esses três caminhos; não significa
que todas as correções possíveis da família estejam habilitadas.

## Contratos e fronteira de confiança

Arquivos: `ai/autocorrection_contracts.py` e `ai/autocorrection_policy.py`.
Versões intent/decision/event 1.0, política `vh1-autocorrection-1.0`.
Schemas exportados em `schemas/autocorrection-*-1.0.schema.json`; manifesto em
`config/autocorrection-policy-vh1-1.0.json`. Não são uma flag de ativação da aplicação.

`AutomationIntent` é o único contrato destinado à saída do modelo. Contexto,
achados, evidências e grants são dados internos do servidor. **Não criar endpoint
que aceite essas provas como autoridade do usuário ou do agente.** Hash não é
assinatura nem consentimento. A implementação futura deve resolver o grant ativo,
extrair o trecho exato no campo/objeto do IDML autorizado e verificar bytes do asset
antes de construir `AutomationEvidence`. Nesta etapa esses produtores são fixtures
sintéticas de teste; não se declara que o extrator/serviço já esteja integrado.

Política confere empresa/artigo/snapshot/revisão, hash do modelo canônico e perfil,
achado-alvo elegível, hash de campo anterior, existência da evidência no snapshot,
tipo IDML, arquivo/extrato e vínculo ao objeto/campo. Evidência sem hash de conteúdo,
vencida, revogada, futura, de outra empresa ou ambígua é recusada. Grants têm no
máximo 30 dias e devem ser reconsultados no instante da aplicação.

Propostas com `needs_human`, achados históricos assistivos, decisões humanas e
caminhos humanos protegidos permanecem em abstenção/proteção. Inclui pais e filhos
do caminho; caminhos não canônicos são rejeitados. `ai/policy.py`, `ai/outputs.py`
e proteções genéricas de `services/reviews.py` não foram alterados. Nenhuma decisão
anterior foi migrada, removida ou reinterpretada.

Cada lote é indivisível para elegibilidade: uma recusa elimina todas as operações
preparadas. Resultado `eligible_for_candidate` contém material **privado** para o
executor e não significa aplicado. `applied=false`, revalidação obrigatória e
`release_approved=false`. Evento de serviço guarda escopo/hashes, sem texto privado;
persistência append-only será feita em VH-09. Não houve migração de banco aqui.

## Limites e controles

Contrato padrão: dois ciclos por artigo, até cinco operações por lote, 300 s,
50.000 tokens e US$ 5 por artigo; uma execução concorrente na VPS. Configuração
administrativa pode reduzir ou ajustar até os tetos de 900 s/200.000 tokens/US$ 100,
sem ultrapassar dois ciclos/cinco operações. Esses valores são limites operacionais,
não estimativas de preço/modelo. Nenhuma chamada paga foi feita nesta etapa.

O avaliador rejeita contador esgotado, relógio futuro, execução concorrente,
automação desativada e intenção repetida. Trocar ID de proposta ou ordem das
operações não evita deduplicação. O executor/orquestrador deve implementar locks,
reservas de custo/tokens e deadline real; passar números a este contrato **não**
equivale a já ter esse controle distribuído implantado.

Detecção conservadora de instruções no extrato recusa a operação. Não depende só
desse filtro: o modelo nunca tem valores/paths/comandos livres, poder de executar
ou de aprovar release. A etapa não usa rede, filesystem ou banco para aplicar XML.

## Evidências e testes

102 testes de política aprovados, com 100% de linhas e ramificações dos **dois
módulos novos**; não é cobertura global nem garantia de ausência de defeitos.
JUnit `tmp/vh08-policy-tests.xml`; cobertura `tmp/vh08-policy-coverage.json`.
Regressão direcionada: **223 aprovados, zero falhas/erros/skip**, incluindo 113
novos, contratos assistivos, revisão/UI, modelo canônico e cadeia Wayta anterior.
JUnit `tmp/vh08-focused-regression.xml`. Ruff global, mypy de 118 módulos e
formatação dos arquivos novos aprovados. Sem nova suíte integral/cobertura global.
Gates V10/V11 e a cadeia Wayta/DOI/SPS também passaram sem reescrever suas provas.

Prova `benchmarks/qualification/reports/vh08-autocorrection-policy-v1.json`, SHA-256
`cc7374ae21886380e9c15b2bc3e5331e6956a0187dee072770740035adbdb89c`.
Registra fontes e schemas por hash, testes sintéticos e ausência de aplicação/IA
real. Não é corpus independente, benchmark de modelo ou validação de XML de artigo.
Verificação incorporada ao CI; não declara CI global aprovado.

Prova vigente: `benchmarks/qualification/reports/vh08-autocorrection-policy-v2.json`.
A mudança transacional de `reviews.py` na VH-09 invalidou a vinculação da v1 à
fonte atual. Os 102 testes da política foram reexecutados com 100% de linhas e
ramificações dos mesmos dois módulos; os 11 testes de contrato passaram novamente.
Allowlist e critérios de recusa não mudaram. V1 permanece como evidência histórica,
não deve ser usada para atestar a árvore atual. A v2 é a prova verificada pelo CI.

```powershell
.venv/Scripts/python -m pytest tests/test_autocorrection_policy.py tests/test_autocorrection_contract_exports.py --no-cov
.venv/Scripts/python -m ops.qualify_vh08_autocorrection --check benchmarks/qualification/reports/vh08-autocorrection-policy-v2.json
```

## Handoff para VH-09

1. Resolver fontes/grants/extratos e assets no servidor, sem aceitar prova do agente;
   ausência de extrato qualificado deve recusar, não gerar catálogo por consenso.
2. Implementar transação, trava otimista/isolamento multiempresa e idempotência.
   Reavaliar política, grant, snapshot e decisão humana dentro da operação.
3. Gerar cópia candidata, preservando origem, evidências e histórico append-only.
   Aplicar só as operações dedicadas; não relaxar o editor genérico para viabilizar.
4. Reconstruir XML/pacote, conferir invariantes e revalidar novos hashes. Validador
   falho/indisponível ou conteúdo perdido impede promoção; contagem menor não basta.
5. Testar queda, repetição, concorrência, revogação, nova decisão humana e rollback.
   Depois VH-10 conecta OpenClaw e testa chamadas reais com/sem IA.

Nenhuma nova instalação/deploy foi necessária para a política pura. XMLs, VPS ativa
e flags IA não foram alterados. Pendências XPM em VH-02/07 continuam explícitas;
não se reutiliza a aprovação de uma entrada anterior para promover outra.
