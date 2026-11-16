# Plano de Desenvolvimento por Fases — Plataforma IDML → XML SciELO

## 1. Finalidade deste documento

Este arquivo controla o planejamento e a execução futura do desenvolvimento da plataforma de conversão IDML para XML SciELO SPS/JATS.

Este documento controla a autorização por fase. Cada fase somente poderá começar após autorização explícita e deverá terminar com evidências verificáveis.

Documento arquitetural de referência:

```text
PLANO_ANALISE_CODEX_SCIELO_IDML_OPENCLAW_SWARM.md
```

Plano obrigatório de testes e homologação:

```text
docs/XML_VALIDATION_MASTER_PLAN.md
```

## 2. Estado geral

```text
PROJECT_STATUS: EXPERT_HOMOLOGATION_PREPARATION
CURRENT_PHASE: VH1 — Correção por IA autorizada pelo portal na VPS em vh19-web-provider-20261114-v1. Próximo aceite: congelar a versão do piloto, conferir o roteiro final e registrar a decisão G-HOMOLOG. Ver seção 65 de docs/HOMOLOGATION_VH1_DELIVERY.md.
CURRENT_IMPLEMENTATION_AUTHORIZED: PHASE_7
DEVELOPMENT_ROADMAP_AUTHORIZED: THROUGH_PHASE_8_PRODUCTION_READINESS
PRODUCTION_ACTIVATION_AUTHORIZED: NO — REQUIRES XML_EXPERT_FINAL_ACCEPTANCE
EXPERT_TEST_ACCESS_READY: NO — REQUIRES G-HOMOLOG
CURRENT_INCREMENT: 2026-11-09 — 3.244 testes por plataforma. Cobertura de 90,16% no Windows e 90,15% no Linux. 42 verificações do workflow aprovadas. Revisor recuperou os dois ZIPs de avaliação após a implantação.
HOMOLOGATION_AI_AUTOCORRECTION: NAMED OPERATOR AND REVIEWER PATH AND VH-17 REGRESSION QUALIFIED. FINAL EDIT, RESTORE AND REVALIDATION ACCEPTANCE, PILOT SOURCE GOVERNANCE AND INDIVIDUAL SPECIALIST HANDOFF PENDING. See docs/HOMOLOGATION_VH1_DELIVERY.md section 63.
ARCHITECTURE_STATUS: APPROVED_WITH_CHANGES
INFRASTRUCTURE_STATUS: IN_USE_WITH_CONSTRAINTS
```

Registro histórico da candidata `vh1-doctype-20261027-v1`: 2.906 testes locais e 966 Linux
aprovados, conjuntos sobrepostos, 41 novos; zero falhas/erros/skip finais. Auditoria
nativa reproduzida, 1.176 arquivos conferidos, 25 serviços preservados e ready/app
HTTP 200. Documentação/prova na seção 44 da VH1. Naquele fechamento, a candidata
estava armazenada, sem ativação. Estado ativo atual na seção 52; aprovação SciELO
e G-HOMOLOG não concedidos.

Fechamento da release implantada vh09-heads-20261021-v1 em 22/10: 2.654 testes locais aprovados, zero falhas/erros/skip,
90,04% de cobertura de linhas; 223 testes Linux e concorrência PostgreSQL aprovados
(conjuntos sobrepostos). VPS atualizada e documentação de fechamento sincronizada.
Evidência: `benchmarks/qualification/reports/vh09-head-vps-v1.json` e seção 37 do
plano VH1. Isso não encerra VH-09, não declara CI global aprovado e não aprova XML.

### Legenda de status

- `[ ]` Não iniciado
- `[~]` Em andamento
- `[x]` Concluído e verificado
- `[!]` Bloqueado
- `[-]` Removido do escopo

### Regras de atualização

Ao concluir um item:

1. marcar o checklist;
2. registrar a evidência ou artefato produzido;
3. registrar decisões relevantes em ADR;
4. atualizar riscos e dependências;
5. não aprovar o próprio gate sem validação definida para a fase.

## 3. Princípios obrigatórios

Para concluir a primeira homologação, seguir exclusivamente a fila VH-01–20 em
`docs/HOMOLOGATION_VH1_DELIVERY.md` (ADR-017). Fases históricas abaixo preservam
contexto e escopo de produção, mas não adicionam pré-requisitos automaticamente.
H1-A permanece obrigatório dentro dos itens mapeados; não ativar automação sem provas.

- Parser, aplicação de patches, builder XML, validações formais e empacotamento devem ser determinísticos.
- IA não gera nem edita diretamente o XML final.
- O Canonical Article Model é a fonte estrutural interna.
- Agentes somente propõem operações tipadas e validadas.
- Validadores oficiais e políticas determinísticas controlam o release.
- Swarm deve ser substituível e ativado por feature flag.
- Todo dado relevante deve possuir versão, proveniência e auditoria.
- Nenhum dado ausente pode ser inventado.
- Segurança, testes, persistência e observabilidade são transversais.
- O desenvolvimento não deve ocorrer diretamente no ambiente de produção existente.
- A primeira versão atende um periódico e um template IDML conhecidos.

## 4. Restrições atuais de infraestrutura

Baseline preliminar da VPS HostGator:

```text
SO: Ubuntu 22.04.5 LTS
CPU: 2 vCPUs
RAM: 3,8 GB
Swap em uso na inspeção: 1,3 GB
Disco: 98 GB, 78% utilizado, aproximadamente 21 GB livres
Docker: disponível
Docker Compose: disponível
OpenClaw: 2026.6.11, ativo em container
Reverse proxy: Nginx ativo
Outros serviços: sistema Mapalead, PostgreSQL, Redis e múltiplos workers
```

Decisão:

```text
VPS_USAGE: INITIAL_DEVELOPMENT_AND_PILOT
HARDWARE_UPGRADE: ON_DEMAND
```

A VPS atual será utilizada para iniciar o desenvolvimento, executar os spikes, hospedar o ambiente inicial e realizar o piloto. Os serviços novos devem ser isolados do sistema existente e receber limites de recursos compatíveis com a capacidade disponível.

Não é necessário realizar upgrade preventivo. A necessidade de upgrade será avaliada com base em medições durante o desenvolvimento e o piloto, sem comprometer a disponibilidade do sistema e do OpenClaw já existentes.

Indicadores para avaliar upgrade:

- pressão recorrente de memória ou aumento contínuo de swap;
- CPU sustentada em nível que prejudique os serviços existentes;
- espaço livre em disco insuficiente para artefatos, imagens, volumes e backups;
- aumento relevante da latência ou reinícios por falta de recursos;
- impossibilidade de manter banco, filas e workers isolados;
- crescimento da concorrência ou do volume de artigos;
- necessidade de processamento paralelo de PDF, IDML, validações ou agentes.

Antes de qualquer implantação futura na VPS:

- [x] Criar baseline técnico completo.
- [x] Confirmar backup e testar restauração do ambiente atual.
- [x] Investigar ocupação de disco.
- [x] Criar usuário administrativo não-root.
- [x] Definir diretório e Docker Compose project exclusivos.
- [x] Definir networks, volumes, banco e Redis exclusivos.
- [x] Definir limites de CPU, RAM, disco e concorrência.
- [x] Garantir que nenhum serviço novo seja exposto diretamente à internet.

## 5. Visão das macrofases

| Fase | Nome | Resultado principal | Estado |
|---|---|---|---|
| 0 | Descoberta e viabilidade | Decisão formal GO/NO-GO | Concluída — `GO_WITH_CONSTRAINTS` |
| 1 | Fundação técnica e segurança | Base isolada, persistente e auditável | Concluída — Gate G1 aprovado |
| 2 | Corpus e modelo de domínio | Corpus piloto e modelo canônico estável | Concluída — Gate G2 aprovado |
| 3 | Pipeline determinístico mínimo | IDML → modelo → XML válido sem IA | Concluída — Gate G3 aprovado |
| 4 | Validação, fidelidade e pacote | Pacote validado e política de release | Implementada — Gate G4 bloqueado por validadores externos/crossrefs |
| 5 | Revisão humana e interface mínima | Correção humana auditável | Concluída — Gate G5 aprovado |
| 6 | IA assistiva e OpenClaw | Assistência semântica controlada | Concluída — Gate G6-T aprovado; produção não autorizada |
| 7 | Homologação automatizada e piloto simulado | Validação técnica e versão funcional para avaliação | Em andamento — prioridade H0–H4/G-HOMOLOG; V-12 incompleta |
| 8 | Prontidão, homologação humana e produção | RC operacional, aceite final e rollout | Avaliação inicial antecipada via G-HOMOLOG; prontidão completa pendente |
| 9 | Expansão controlada | Novos periódicos e casos complexos | Não iniciada |

---

## 5.1 Estratégia revisada de homologação

Revisão autorizada em 2026-09-25 (ADR-015): priorizar uma versão funcional de homologação (VH)
para avaliação editorial e de usabilidade antes da prontidão operacional completa. O plano
executável é `docs/EXPERT_TEST_READINESS_PLAN.md`. G-HOMOLOG libera somente testes restritos;
G7-T/G8-RC e todos os requisitos de produção continuam pendentes quando não comprovados.

Fluxo obrigatório:

1. Codex e agentes OpenClaw executam testes técnicos, semânticos, adversariais e comparativos;
2. validadores determinísticos têm precedência sobre qualquer conclusão de IA;
3. H0–H4 fecham escopo, validação formal (incluindo XPM), implantação segura mínima, fluxo e acessos;
4. a VH é congelada e G-HOMOLOG autoriza testes restritos, sem publicação/tráfego editorial real;
5. o especialista avalia XML e usabilidade; cada defeito confirmado gera correção e regressão;
6. V-12 a V-15 e prontidão G7-T/G8-RC são concluídos depois ou em paralelo, sem perder pendências;
7. o especialista revalida a RC final; G8-H e critérios operacionais autorizam ou rejeitam produção;
8. a ativação permanece acompanhada e com revisão humana por artigo.

O catálogo, os critérios e as evidências estão definidos em
`docs/XML_VALIDATION_MASTER_PLAN.md`. Nenhuma métrica ou consenso de agentes substitui o G8-H.

---

# FASE 0 — Descoberta e viabilidade

## Objetivo

Eliminar as principais incertezas antes de escrever código de produção.

## Dependências

- Acesso somente leitura à VPS.
- Documentação oficial SciELO vigente.
- Amostras reais do periódico piloto.
- Acesso autorizado às configurações do OpenClaw.

## Pacote 0.1 — Baseline da infraestrutura

- [x] Inventariar SO, CPU, memória, swap, disco e filesystem.
- [x] Inventariar Docker, Compose, networks, volumes e containers.
- [x] Mapear Nginx, domínios, SSL, firewall e portas.
- [x] Mapear persistência, backups, deploy e recuperação atuais.
- [x] Inventariar PostgreSQL, Redis e processos persistentes.
- [x] Inventariar instalação, versão e operação do OpenClaw.
- [x] Identificar consumo de recursos e riscos de coexistência.
- [x] Produzir `docs/ENVIRONMENT_BASELINE.md`.

## Pacote 0.2 — Requisitos oficiais SciELO

- [x] Identificar a versão SPS inicialmente suportada.
- [x] Confirmar JATS/DTD correspondente.
- [x] Confirmar regras de front, body, back e referências.
- [x] Confirmar requisitos de assets e nomes de arquivos.
- [x] Confirmar Packtools, XPM e demais validadores aplicáveis.
- [x] Registrar fontes, versões e data da consulta.
- [x] Produzir `docs/SCIELO_REQUIREMENTS.md`.

## Pacote 0.3 — Spike Packtools

- [x] Selecionar XML oficial ou previamente aprovado.
- [x] Provar execução isolada em Linux.
- [x] Capturar errors e warnings em formato processável.
- [x] Registrar versão, dependências e limitações.
- [x] Não instalar no host sem isolamento aprovado.
- [x] Produzir relatório do spike em `docs/PACKTOOLS_SPIKE.md`.

## Pacote 0.4 — Spike XPM

- [x] Confirmar exigência e função atual do XPM.
- [x] Avaliar execução em Linux/container.
- [x] Avaliar execução headless e formato de resultados.
- [x] Avaliar alternativa com worker Windows dedicado.
- [x] Avaliar licenciamento e automação permitida.
- [x] Produzir `docs/XPM_FEASIBILITY.md`.
- [x] Classificar como `GO_WITH_CONSTRAINTS`.

## Pacote 0.5 — OpenClaw e Swarm

- [x] Registrar versão e método de instalação.
- [x] Confirmar APIs reais de ferramentas e structured output.
- [x] Confirmar suporte real a Swarm, subagents, hooks e schemas.
- [x] Mapear persistência, sessões, retries, timeouts e concorrência.
- [x] Identificar APIs experimentais.
- [x] Definir interface abstrata de orquestração.
- [x] Produzir `docs/OPENCLAW_SWARM_DESIGN.md`.

## Pacote 0.6 — Amostras e IDML

- [x] Selecionar periódico e template piloto.
- [x] Obter IDML, PDF, assets e XML aprovado dos mesmos artigos.
- [x] Inspecionar ZIP, Stories, Spreads, frames, threads e estilos.
- [x] Investigar regras reais de reading order.
- [x] Identificar tabelas, equações, notas, links e objetos ancorados.
- [x] Produzir `docs/IDML_MODEL_ANALYSIS.md`.

## Entregáveis

- `ENVIRONMENT_BASELINE.md`
- `SCIELO_REQUIREMENTS.md`
- `XPM_FEASIBILITY.md`
- `IDML_MODEL_ANALYSIS.md`
- `OPENCLAW_SWARM_DESIGN.md`
- `ARCHITECTURE_REVIEW.md`
- matriz inicial de riscos;
- decisão de infraestrutura.

## Gate de saída G0

- [x] Reading order possui estratégia tecnicamente plausível.
- [x] Versão SPS/JATS inicial foi definida.
- [x] Packtools foi provado ou possui alternativa documentada.
- [x] XPM possui caminho de integração decidido.
- [x] OpenClaw foi auditado sem alteração.
- [x] Corpus piloto foi selecionado.
- [x] Infraestrutura para desenvolvimento foi aprovada.
- [x] Decisão registrada: `GO_WITH_CONSTRAINTS`.

---

# FASE 1 — Fundação técnica e segurança

## Objetivo

Criar a base de desenvolvimento isolada, persistente, segura, observável e testável.

## Dependências

- Gate G0 aprovado.
- Ambiente de desenvolvimento definido na VPS atual, com isolamento e limites de recursos.
- Estratégia de armazenamento aprovada.

## Pacote 1.1 — Repositório e qualidade

- [x] Criar monorepo e convenções de diretórios.
- [x] Definir branching, revisão e proteção de branch.
- [x] Configurar lockfiles e versões de runtime.
- [x] Configurar lint, format, type checking e testes.
- [x] Configurar CI sem acesso a dados de produção.
- [x] Criar templates de issue, ADR e pull request.

## Pacote 1.2 — Ambientes

- [x] Definir development, test, staging e production.
- [x] Criar Compose isolado para desenvolvimento.
- [x] Criar health checks.
- [x] Definir configuração por ambiente.
- [x] Definir feature flags.
- [x] Proibir uso de secrets reais em desenvolvimento.

## Pacote 1.3 — Persistência e artefatos

- [x] Definir PostgreSQL e migrations.
- [x] Definir object/file storage.
- [x] Definir hashes, imutabilidade e retenção de artefatos.
- [x] Definir transações e controle de concorrência.
- [x] Definir backup e restore.
- [x] Definir separação entre versão semântica, execução e tentativa.

## Pacote 1.4 — Identidade e acesso

- [x] Definir Organization, User, Membership, Role e Permission.
- [x] Definir matriz RBAC com negação por padrão.
- [x] Definir autenticação local ou OIDC.
- [x] Definir login, logout, convite e recuperação.
- [x] Definir MFA e reautenticação sensível.
- [x] Definir sessões, expiração, rotação e revogação.
- [x] Definir service accounts.
- [x] Definir isolamento multiempresa no banco, cache, filas e storage.
- [x] Produzir `docs/IDENTITY_AND_ACCESS_MODEL.md`.

## Pacote 1.5 — Estado, jobs e idempotência

- [x] Definir máquina de estados do artigo/job.
- [x] Definir estados retryable, permanent failure e quarantined.
- [x] Definir comandos, eventos e pré-condições de transição.
- [x] Definir idempotency keys.
- [x] Definir retry, backoff, timeout, cancellation e replay.
- [x] Definir retomada após restart.

## Pacote 1.6 — Segurança de ingestão

- [x] Definir limites de upload.
- [x] Proteger contra ZIP bomb e path traversal.
- [x] Impedir symlinks, hardlinks e nested archives não autorizados.
- [x] Configurar XML parser sem XXE e sem rede.
- [x] Validar MIME e conteúdo de assets.
- [x] Isolar parsing por job.
- [x] Definir antivírus/content scanning.
- [x] Definir quarentena.

## Pacote 1.7 — Observabilidade e auditoria

- [x] Definir logs estruturados e correlation IDs.
- [x] Definir métricas de CPU, RAM, disco, fila, latência e custo.
- [x] Definir timeline de jobs.
- [x] Definir security events.
- [x] Impedir secrets e dados desnecessários em logs.
- [x] Definir alertas mínimos.

## Gate de saída G1

- [x] Stack mínimo sobe com health checks.
- [x] Migrations são reproduzíveis.
- [x] Backup e restore foram testados.
- [x] Upload malicioso conhecido é bloqueado.
- [x] Retry não duplica efeitos.
- [x] Usuário não acessa recurso de outra empresa.
- [x] Nenhum serviço interno está exposto publicamente.
- [x] Logs e auditoria permitem reconstruir uma execução.

---

# FASE 2 — Corpus e modelo de domínio

## Objetivo

Construir o corpus de referência e definir modelos independentes de IDML, IA e XML.

## Pacote 2.1 — Corpus gold standard

- [x] Definir licença, confidencialidade e retenção do corpus.
- [x] Anonimizar amostras quando necessário.
- [x] Versionar IDML, PDF, XML e assets.
- [x] Criar ficha de expectativas por artigo.
- [x] Incluir casos simples, limites e documentos problemáticos.
- [x] Definir conjunto de treino interno e conjunto de homologação separado.

## Pacote 2.2 — Raw Article Model

- [x] Representar Stories, frames, threads e coordenadas.
- [x] Representar texto, whitespace, estilos e conteúdo inline.
- [x] Representar links, objetos ancorados, tabelas, notas e assets.
- [x] Preservar referências aos XMLs internos do IDML.
- [x] Definir serialização e compatibilidade de versões.

## Pacote 2.3 — Canonical Article Model

- [x] Modelar front, body e back.
- [x] Modelar contributors, affiliations e correspondência.
- [x] Modelar seções e conteúdo inline sem perda.
- [x] Modelar figuras, tabelas, equações, notas e referências.
- [x] Modelar cross-references e IDs estáveis.
- [x] Separar conteúdo, evidência, decisões e patches.
- [x] Definir estados missing, ambiguous e needs_review.
- [x] Definir migrations de schema.
- [x] Produzir `docs/CANONICAL_ARTICLE_MODEL.md`.

## Pacote 2.4 — Métricas e critérios

- [x] Definir Text Fidelity.
- [x] Definir Metadata, Author e Affiliation Accuracy.
- [x] Definir Reference, Figure e Table Accuracy.
- [x] Definir CrossRef Accuracy.
- [x] Definir tolerâncias de Unicode, espaços e hifenização.
- [x] Definir warnings bloqueadores.
- [x] Definir `NEEDS_REVIEW` versus `FAILED`.
- [x] Definir metas do piloto e STP.

## Gate de saída G2

- [x] Corpus mínimo representa o periódico piloto.
- [x] Modelos serializam e desserializam sem perda.
- [x] IDs permanecem estáveis entre versões.
- [x] Evidências podem ser rastreadas até a fonte.
- [x] Casos não representáveis estão documentados.
- [x] Métricas e limiares foram aprovados antes do parser final.

---

# FASE 3 — Pipeline determinístico mínimo

## Objetivo

Produzir o primeiro XML válido sem IA e sem depender do Swarm.

## Pacote 3.1 — Parser IDML seguro

- [x] Abrir e validar IDML como ZIP não confiável.
- [x] Extrair DesignMap, Stories, Spreads, Styles e Resources.
- [x] Reconstruir threads e relações de frames.
- [x] Implementar estratégia de reading order.
- [x] Extrair texto e estrutura sem IA.
- [x] Extrair assets e registrar proveniência.
- [x] Produzir Raw Article Model.
- [x] Medir cobertura no corpus.

## Pacote 3.2 — Mapeamento canônico

- [x] Criar mapeamento Raw → Canonical.
- [x] Criar Journal Profile piloto.
- [x] Criar style mappings versionados.
- [x] Registrar ambiguidades sem inventar conteúdo.
- [x] Preservar elementos não reconhecidos para auditoria.

## Pacote 3.3 — Builder SPS/JATS

- [x] Implementar builder com árvore XML.
- [x] Implementar front, body e back por componentes.
- [x] Implementar IdRegistry.
- [x] Impedir IDs duplicados e RIDs órfãos.
- [x] Aplicar SpsProfile versionado.
- [x] Gerar XML reprodutível.

## Pacote 3.4 — Validação básica

- [x] Validar well-formed XML.
- [x] Validar DTD/JATS offline e allowlisted.
- [x] Executar regras SPS disponíveis.
- [x] Normalizar resultados dos validadores.
- [x] Produzir relatório processável.

## Gate de saída G3

- [x] Ao menos um artigo real gera XML válido sem IA.
- [x] Pipeline é idempotente.
- [x] Mesmo input e mesmas versões geram resultado equivalente.
- [x] Reading order atinge o limiar definido.
- [x] Nenhum erro é corrigido silenciosamente.
- [x] Falhas são classificadas e auditáveis.

---

# FASE 4 — Validação, fidelidade e pacote

## Objetivo

Comprovar conformidade, fidelidade e integridade do pacote antes de adicionar IA.

## Pacote 4.1 — Validation Engine

- [x] Integrar well-formed, DTD, SPS/Schematron e Packtools/SPSValidator.
- [x] Criar formato único para errors e warnings.
- [x] Implementar regras internas e cross-reference validator.
- [x] Implementar asset validator.
- [x] Registrar versões dos validadores.

## Pacote 4.2 — PDF Fidelity Engine

- [x] Extrair camada textual do PDF quando disponível.
- [x] Usar OCR apenas quando necessário.
- [x] Comparar PDF, modelo canônico e XML.
- [x] Medir título, autores, texto, figuras, tabelas e referências.
- [x] Classificar divergências legítimas e bloqueadoras.

## Pacote 4.3 — Error Classifier e reparos determinísticos

- [x] Classificar deterministic, semantic, missing data, source conflict e system.
- [x] Implementar apenas reparos formalmente seguros.
- [x] Definir limite de ciclos.
- [x] Rebuild e revalidation após cada patch.
- [x] Encaminhar ambiguidades para revisão humana.

## Pacote 4.4 — Package Builder

- [x] Definir layout final do pacote.
- [x] Aplicar regras de nomes de arquivos.
- [x] Verificar presença e hash dos assets.
- [x] Gerar ConversionManifest.
- [x] Tornar releases imutáveis.

## Pacote 4.5 — XPM e Release Policy

- [x] Integrar contrato/parser XPM; executor Linux qualificado em laboratório em 2026-10-15, integração supervisionada e compatibilidade ainda pendentes (ADR-002 revisada).
- [x] Criar política determinística de release.
- [x] Definir gates obrigatórios por SpsProfile.
- [x] Impedir que IA conceda `READY_FOR_SCIELO`.
- [x] Registrar override humano permitido e sua justificativa.

## Gate de saída G4

- [x] Pacote é construído antes do gate XPM.
- [ ] Todos os validadores obrigatórios são executados (XPM do candidato pendente).
- [x] Release Policy é versionada e testada.
- [x] ConversionManifest permite auditar a conversão.
- [ ] Corpus determinístico alcança todos os targets e fica sem erros SPS.

---

# FASE 5 — Revisão humana e interface mínima

## Objetivo

Permitir que pessoas autorizadas resolvam ambiguidades no modelo canônico com evidência e auditoria.

## Pacote 5.1 — Fluxo de revisão

- [x] Criar ReviewItem e estados.
- [x] Mostrar evidências de IDML e PDF.
- [x] Mostrar regra, validação e alternativas.
- [x] Aplicar decisão humana como patch.
- [x] Implementar controle de concorrência.
- [x] Reconstruir e revalidar automaticamente.

## Pacote 5.2 — Interface mínima

- [x] Login, logout, recuperação e MFA.
- [x] Seleção e administração de empresa.
- [x] Usuários, convites, papéis e sessões.
- [x] Dashboard de jobs.
- [x] Upload seguro de artigo e assets.
- [x] Timeline de processamento.
- [x] Review Queue.
- [x] Visualização de modelo, XML e validações.
- [x] Diff entre versões.
- [x] Auditoria e download controlado.

## Pacote 5.3 — Aprovação editorial

- [x] Separar permissão de revisão e release.
- [x] Definir ações que exigem MFA/reautenticação.
- [x] Avaliar dupla aprovação.
- [x] Registrar identidade e empresa em todas as decisões.

## Gate de saída G5

- [x] Usuário autorizado corrige uma pendência sem editar XML.
- [x] Usuário não autorizado é bloqueado no backend.
- [x] Patch humano gera nova versão e revalidação.
- [x] Histórico anterior permanece íntegro.
- [x] Auditor consegue reconstruir quem alterou o quê.

---

# FASE 6 — IA assistiva e OpenClaw

## Objetivo

Adicionar IA somente onde houver ganho técnico mensurável, evidência válida e abstenção segura,
preparando a comparação editorial humana para a RC final.

## Pacote 6.1 — Contratos de ferramentas

- [x] Definir ferramentas de leitura com menor privilégio.
- [x] Definir `propose_patch` e `validate_patch`.
- [x] Proibir shell, filesystem global e SQL livre.
- [x] Aplicar escopo de job e empresa em todas as ferramentas.
- [x] Produzir `docs/OPENCLAW_TOOL_CONTRACTS.md`.

## Pacote 6.2 — Schemas de saída

- [x] Criar JSON Schemas por domínio.
- [x] Validar saídas antes de qualquer aplicação.
- [x] Definir confidence, evidence, alternatives e reason.
- [x] Rejeitar saída inválida ou sem evidência.
- [x] Exigir patch atômico de `RichText` para `plain.value` e `inlines`.
- [x] Exigir patch atômico de fórmula para `source.value` e `representation=mathml`.
- [x] Vincular cada operação às evidências exatas e rejeitar evidência declarada sem uso.
- [x] Produzir `docs/AGENT_OUTPUT_SCHEMAS.md`.

## Pacote 6.3 — Orquestração substituível

- [x] Implementar contrato `Orchestrator`.
- [x] Implementar SequentialOrchestrator.
- [x] Implementar TestOrchestrator.
- [x] Implementar SwarmOrchestrator atrás de feature flag.
- [x] Implementar cliente OpenResponses restrito com modelo e agente fixados.
- [x] Definir timeout, retry, custo, cancelamento e concorrência.
- [x] Impedir workers de criar novos Swarms.

## Pacote 6.4 — Domínios assistidos incrementalmente

- [x] Metadata.
- [x] Contributors e affiliations.
- [x] Structure.
- [x] References.
- [x] Figures e tables.
- [x] Math e notes, com MathML seguro, aplicação atômica e recurso inativo.
- [x] Medir cada domínio contra corpus automático congelado, regras determinísticas e consenso crítico.
- [x] Executar proxy técnico provisório no corpus autorizado sem substituir baseline humano.

## Pacote 6.5 — Segurança e avaliação de agentes

- [x] Testar prompt injection proveniente de IDML/PDF.
- [x] Testar saída inválida, timeout e worker crash.
- [x] Testar indisponibilidade OpenAI/OpenClaw.
- [x] Testar patches conflitantes ou atrasados.
- [x] Versionar prompts, Skills, modelos e configurações.
- [x] Deduplicar e limitar o envelope assistivo, registrando seu tamanho canônico.
- [x] Registrar tokens, latência, custo, fonte monetária e versão tarifária sem raciocínio privado.
- [x] Rejeitar a proposta com `COST_UNAVAILABLE` quando provider e catálogo exato não informam custo.
- [x] Fixar tarifa oficial exata para `openai/gpt-5.4-mini`, incluindo entrada em cache.
- [x] Aplicar preflight conservador e orçamento monetário agregado por artigo.
- [x] Isolar o endpoint OpenResponses em gateway dedicado/restrito antes da ativação.
- [x] Fixar imagem por digest, estado/workspace próprios e token de gateway independente.
- [x] Manter o gateway base sem porta publicada, egress, provider key, tools, Skills, plugins ou canais.
- [x] Desabilitar heartbeat recorrente no default e no agente dedicado.
- [x] Incluir o estado OpenClaw no backup consistente e no restore test.
- [x] Preparar credencial de provider e egress sob ativação explícita, sem executar agentes.
- [x] Restringir o egress do provider ao proxy allowlist para `api.openai.com:443`.
- [x] Testar o fail-closed: domínio não autorizado negado e saída direta do gateway bloqueada.
- [x] Implementar e testar kill switch que remove credencial, proxy e redes de provider.
- [x] Confirmar flags falsas e zero sessões, runs e propostas antes e depois do staging.
- [x] Reconstruir o dataset privado v1.3 e congelar hashes sem versionar conteúdo restrito.
- [x] Preparar primeira janela com dois casos, concorrência 1, tentativa única e preflight agregado.
- [x] Implementar runner com confirmação explícita, output privado e interrupção no primeiro erro.
- [x] Implementar limpeza final com kill switch e reset validado do estado OpenClaw dedicado.
- [x] Reproduzir o manifesto em dry-run local e na VPS sem executar agentes.
- [x] Executar a primeira janela controlada após autorização explícita, com custo e cleanup verificados.
- [x] Comparar as propostas com os alvos automáticos sem promover esses alvos a baseline humano.
- [-] Adjudicar o caso de referências por humano nesta fase — transferido para o Gate G8-H.

## Pacote 6.6 — QA e repair assistidos

- [x] Adicionar auditoria assistida após baseline automático multiagente congelado.
- [x] Adicionar repair semântico com limite de ciclos.
- [x] Manter Release Judge apenas consultivo.
- [x] Encaminhar baixa confiança para humano.

## Pacote 6.7 — Laboratório multiagente de qualidade XML

- [x] Implementar papéis separados de proponente, crítico XML, crítico editorial e adjudicador.
- [x] Impedir compartilhamento de raciocínio privado entre sessões e registrar somente saídas estruturadas.
- [x] Executar os dez casos reais disponíveis do corpus ESA, em quatro domínios, com custo, tokens e latência contabilizados.
- [x] Obter e qualificar casos autorizados derivados do artigo real para estrutura e matemática; a estrutura usa omissão controlada e o caso matemático aplica a transição atômica para MathML.
- [x] Criar matriz sintética com casos positivos, negativos, ambíguos, de abstenção e de prompt injection nos seis domínios.
- [x] Comparar propostas da primeira janela com fonte, regras determinísticas e alvos automáticos ocultos dos agentes.
- [x] Medir falso consenso na primeira janela e impedir que concordância substitua evidência.
- [x] Transformar os defeitos confirmados até esta janela em fixtures de regressão.
- [x] Produzir relatório sanitizado para os quatro domínios reais disponíveis, sem promover o resultado a baseline humano.
- [x] Substituir evidência truncada por transporte segmentado, completo, limitado e autenticado por hash individual e agregado.
- [x] Tornar a saída estruturada real confiável nos quatro papéis com function call terminal, schema revalidado e zero ferramenta executável.
- [x] Materializar referências longas multissegmento por intent autenticado e validar fidelidade exata nos quatro papéis.
- [x] Alinhar críticos ao contrato atômico sem reduzir a precedência das oito verificações determinísticas.
- [x] Ampliar o relatório sanitizado com estrutura e matemática reais, sem texto do artigo e sem promover o caso matemático a aplicação.
- [x] Validar a transição atômica imagem→MathML em memória, no JATS e nos quatro papéis OpenClaw.
- [x] Preservar a ordem e os rótulos das 15 fórmulas display e detectar as duas lacunas inline do artigo real.
- [x] Transcrever a fonte visual sem depender do XML aprovado e preencher as fórmulas inline ausentes no IDML.
- [x] Mitigar o risco de consenso correlacionado: registrar modelo compartilhado, manter aceite apenas para revisão humana e impedir que o consenso autorize release.

## Gate técnico de saída G6-T

- [x] Desativar Swarm não interrompe o pipeline principal.
- [x] Os seis domínios têm casos executados; os três casos visuais de matemática passam nos checks, críticos e equivalência semântica contra gold oculto.
- [x] Nenhuma proposta sem evidência, com invenção lexical ou falso consenso crítico é aceita pelo juiz determinístico.
- [x] Nenhum patch é aplicado sem schema, evidência e validação.
- [x] Prompt injection não altera ferramentas ou políticas.
- [x] Orçamento de tokens e custo monetário agregado por artigo é respeitado.
- [x] Release continua sendo determinístico.
- [x] Relatório técnico permite iniciar a Fase 7 sem autorizar produção.

---

# FASE 7 — Homologação automatizada e piloto simulado

## Objetivo

Validar o sistema completo em corpus separado e operação editorial simulada, preparando uma RC para
o especialista sem depender de revisão humana intermediária.

## Pacote 7.1 — Testes completos

- [x] V-01 a V-11 reexecutadas; V-07 passou no corpus atual após encerramento da trilha 7C.
- [x] V-01 — proveniência, integridade, segregação e reprodução do catálogo do corpus.
- [x] V-02 — segurança da ingestão IDML.
- [x] V-03 — leitura e fidelidade do IDML.
- [x] V-04 — invariantes do Canonical Article Model.
- [x] V-05 — construção XML JATS/SPS.
- [x] V-06 — validadores formais e regras editoriais, com restrições documentadas.
- [x] V-07 — mecanismo e corpus atual requalificados; zero bloqueio semântico nos dois artigos.
- [x] V-08 — validação assistiva OpenClaw.
- [x] V-09 — segurança, identidade e multiempresa.
- [x] V-10 — fluxo ponta a ponta e experiência operacional.
- [x] V-11 — robustez, propriedades e mutações.
- [x] Unit tests e metas específicas para módulos críticos.
- [x] Golden tests sem exigir igualdade byte a byte quando inadequada.
- [x] Property, metamorphic, fuzz e mutation tests.
- [x] Integration e end-to-end tests.
- [x] Contract tests de validadores e OpenClaw.
- [x] Testes de segurança, autorização e isolamento multiempresa.
- [ ] Fault injection, restore e disaster recovery.

## Pacote 7.2 — Homologação do corpus

- [x] Executar primeiro artigo não usado no desenvolvimento; o caso e20240135 bloqueou o candidato e abriu a trilha 7C.
- [ ] Congelar `regression`, `adversarial`, `holdout-ai` e reservar `holdout-human`.
- [ ] Medir qualidade por tipo de artigo.
- [ ] Comparar resultados com XML aprovado.
- [ ] Classificar falsos positivos e falsos negativos.
- [ ] Medir concordância, falso consenso, abstenção e ciclos de reparo dos agentes.
- [ ] Impedir acesso dos agentes proponentes aos alvos do holdout.

### Trilha corretiva 7C — Generalização do artigo e20240135

Plano detalhado: `docs/PHASE_7_CORRECTIVE_E20240135.md`.

- [x] 7C-00 — congelar baseline, hashes, métricas e famílias de defeito.
- [x] 7C-01 — gate de regressão e inventário content-addressed da origem aprovados.
- [x] 7C-02 — figuras, ativos, ordem global e resolução de nomes finais aprovados.
- [x] 7C-03 — detecção inline/display e 43 fórmulas MathML aprovadas pelo gate corretivo.
- [x] 7C-04 — hierarquia de 26 seções, fluxo do corpo e notas editoriais aprovados.
- [x] 7C-05 — autores compostos, metadados e 39 cross-references aprovados.
- [x] 7C-06 — zerar erros reais SPS e construir pacote reproduzível.
- [x] 7C-07 — reavaliar domínios alterados com OpenClaw em modo assistivo.
- [x] 7C-08 — requalificação integral, implantação, backup/restore e rollback aprovados.

G7C-08 foi aprovado em 2026-09-21. Próxima ação: V-12 na VPS atual, com carga controlada,
limites de interrupção e medição de CPU/RAM/swap/disco/latência/custo, sem upgrade antecipado.

### Execução incremental V-12 — Desempenho, capacidade e custo

Prioridade revisada em 2026-09-25: registros abaixo preservam o histórico. Suas indicações de
"próximo" não sobrepõem H0–H4 em `docs/EXPERT_TEST_READINESS_PLAN.md`. Executar agora apenas
os controles V-12 necessários à segurança da VH; os restantes não foram cancelados/aprovados.

- [x] V-12.1 — baseline, instrumentação, matriz sintética 1/2 concorrentes, janela limitada de
  cinco minutos e medição local dos dois artigos; gate aprovado em 2026-09-22 (728 conversões,
  25 containers preservados, sem crescimento de RSS na janela, zero novas inferências).
- [~] V-12.2 — fila durável API/Redis/worker em ambiente isolado; espera, recuperação sob carga,
  upload/descompactação, quotas de artefatos e política de logs/backups.
  Laboratório real da fila aprovado em 2026-09-22: 24 conversões na execução reforçada,
  quatro cenários (normal, duplicados, avisos perdidos e Redis desligado), sem antecipação ou
  efeitos duplicados; 25 serviços preservados. Limites de ingestão/armazenamento ainda pendentes.
  Ingestão XML limitada: OOM sintético reproduzido/corrigido; oito casos VPS aprovados,
  453 testes/87,57%; 16 MiB de XML agregado e 200 mil unidades de complexidade na candidata.
  Restam corpo HTTP/multipart, pipeline completo próximo aos limites e quotas/logs/backups.
  Ver `docs/PHASE_7_V12_INGESTION.md`; alterações ainda não implantadas nos serviços existentes.
  Recepção HTTP/multipart concluída na candidata em 2026-09-24: 100 MiB com/sem Content-Length
  testados em laboratório, limpeza de temporários e recusa antecipada comprovadas;
  489 testes/87,65%. Restam quotas/admissão concorrente, pipeline completo, logs/backups e
  implantação com backup/restore e rollback. Ver `docs/PHASE_7_V12_HTTP_UPLOAD.md`.
  Admissão de uploads concluída na candidata: trava entre processos, verificação de espaço
  temporário, timeout ocioso/total e liberação após falhas. Ensaio HTTP VPS confirmou 503 por
  ocupação, 408 por inatividade e recuperação 200; serviços existentes preservados.
  Regressão local: 502 testes aprovados, cobertura 87,68%.
  Próximo bloco: quotas por empresa e reserva concorrente do armazenamento definitivo,
  incluindo uploads e artefatos gerados. Ver `docs/PHASE_7_V12_UPLOAD_ADMISSION.md`.
  Quotas/armazenamento concluídos na candidata em 2026-09-24: limite de bytes/arquivos por
  empresa, margem livre no disco, trava até commit/rollback e deduplicação verificada.
  530 testes/87,72%, 18 gates, HTTP/ingestão repetidos e fila PostgreSQL aprovada com 24
  conversões e cinco controles de concorrência/órfãos. Tentativas bloqueadas/OOM do laboratório
  preservadas; rodada final sem OOM e 25 serviços intactos. Ainda não implantado.
  Próximo: armazenamento/pipeline perto dos limites, alertas/logs/backups e implantação controlada.
  Ver `docs/PHASE_7_V12_STORAGE_BUDGET.md`.
  Ensaios volumétricos aprovados em 2026-09-24: seis perfis isolados, incluindo IDML de
  100 MiB, ZIP de 500 MiB expandidos com payload binário, texto XML de 14 MiB, 10 mil
  arquivos e recusa por margem de disco. Sem OOM, 25 serviços preservados, sem implantação.
  Regressão local: 546 testes aprovados, cobertura 87,72%.
  Não qualifica qualquer combinação editorial desses tamanhos. Próximo: alertas/reconciliação,
  logs/backups e implantação controlada; diversidade/saturação prolongada em V-12.3.
  Ver `docs/PHASE_7_V12_VOLUME_PROFILES.md`.
- [ ] V-12.3 — janela prolongada, orçamento integrado de IA, critérios de saturação e fechamento
  da capacidade por perfil de artigo, com pausas automáticas para proteger os demais serviços.

A aprovação de V-12.1 não libera V-13 nem declara capacidade de produção. Não extrapolar tempo de
fila em threads do benchmark para a fila Redis. O inventário identificou 100 MiB de upload e
500 MiB descompactados frente a 256 MiB do worker; são limites ainda não qualificados sob carga.
O OpenClaw dedicado precisa de rotação explícita de logs. Não remover backups nem alterar os
serviços compartilhados para ganhar espaço. Detalhes em `docs/PHASE_7_V12_CAPACITY.md`.

## Pacote 7.3 — Piloto editorial simulado

- [ ] Simular usuários, empresas, responsabilidades e segregação de funções.
- [ ] Executar upload, conversão, revisão, aprovação e pacote ponta a ponta.
- [ ] Executar artigos autorizados sem release automático.
- [ ] Testar operação degradada sem IA e recuperação de incidentes.
- [ ] Validar interface, mensagens, auditoria e downloads controlados.

## Pacote 7.4 — Release Candidate técnica

Este pacote continua obrigatório para a RC de produção, mas não é pré-requisito integral
para a primeira avaliação humana: a VH usa H0–H4/G-HOMOLOG (ADR-015).

- [ ] Corrigir todos os defeitos blocker, critical e major encontrados automaticamente.
- [ ] Executar integralmente V-12 a V-14 do plano mestre.
- [ ] Produzir matriz de cobertura e rastreabilidade requisito → teste → evidência.
- [ ] Congelar código, corpus, prompts, modelos, schemas, profiles e validadores.
- [ ] Produzir relatório de riscos residuais e pacote de homologação humana.

## Métricas mínimas a reportar

- Text Fidelity.
- Metadata, Author e Affiliation Accuracy.
- Reference, Figure, Table e CrossRef Accuracy.
- Validation Pass Rate.
- Straight Through Processing Rate.
- Projected Human Review Rate, estimada pelas abstenções e discordâncias dos agentes.
- Agent Agreement, False Consensus e Abstention Rate.
- Failure Rate.
- Average Repair Passes.
- Average Cost per Article.
- Processing Time.

## Gate técnico de saída G7-T

- [ ] Métricas mínimas foram atingidas.
- [ ] Todos os testes bloqueadores e críticos do plano mestre passaram.
- [ ] XMLs do corpus estão well-formed e sem erro crítico nos validadores aplicáveis.
- [ ] Não existe perda, duplicação ou invenção conhecida de conteúdo.
- [ ] Não existem bloqueadores de segurança.
- [ ] Restore foi testado.
- [ ] Operação degradada sem IA foi comprovada.
- [ ] Capacidade da infraestrutura de produção foi dimensionada.
- [ ] Plano de rollback foi aprovado.
- [ ] RC técnica está pronta para o desenvolvimento de prontidão G8-RC, sem ativação real.

---

# FASE 8 — Prontidão, homologação humana e produção

## Objetivo

Antecipar a avaliação da VH via G-HOMOLOG, corrigir seus apontamentos, concluir a prontidão
operacional e obter revalidação da RC final antes do rollout gradual de produção.

## Pacote 8.1 — Infraestrutura de produção

- [ ] Reavaliar a capacidade da VPS atual com métricas coletadas no piloto.
- [ ] Manter a VPS atual se os critérios operacionais forem atendidos.
- [ ] Realizar upgrade de hardware somente se as medições demonstrarem necessidade.
- [ ] Definir limites e autoscaling possível.
- [ ] Configurar TLS, firewall e redes privadas.
- [ ] Configurar secret management.
- [ ] Configurar storage e backups.
- [ ] Testar restore no ambiente alvo.
- [ ] Executar V-12 a V-15 do plano mestre na configuração candidata.

## Pacote 8.2 — Deploy

- [ ] Definir pipeline de deploy.
- [ ] Definir migrations compatíveis e rollback.
- [ ] Definir smoke tests.
- [ ] Definir rollout gradual.
- [ ] Manter OpenClaw existente sem atualização não auditada.

## Pacote 8.3 — Operação

- [ ] Criar runbooks.
- [ ] Definir monitoramento e alertas.
- [ ] Definir resposta a incidentes.
- [ ] Definir SLO/SLA operacional.
- [ ] Definir retenção e exclusão LGPD.
- [ ] Definir revisão periódica de acessos.
- [ ] Definir atualização controlada de SPS, dependências e modelos.

## Gate de prontidão G8-RC

- [ ] Sistema funcional e operacionalmente completo em ambiente controlado.
- [ ] Zero blocker, critical ou major conhecido.
- [ ] Rollback, restore, alertas, runbooks e modo degradado comprovados.
- [ ] Segurança, acessos, capacidade, custo e observabilidade aprovados tecnicamente.
- [ ] RC congelada e reproduzível com pacote completo de evidências.
- [ ] Nenhum tráfego editorial real ou release automático foi habilitado.

## Pacote 8.4 — Homologação do especialista em XML

A avaliação inicial pode começar após G-HOMOLOG, sem aguardar G8-RC. A avaliação final e
G8-H permanecem posteriores à prontidão completa; usar H4/H5 para acesso, roteiro e feedback.

- [ ] Disponibilizar ambiente isolado e corpus `holdout-human` nunca usado no desenvolvimento.
- [ ] Entregar fontes, XMLs, diffs semânticos, relatórios e matriz de rastreabilidade.
- [ ] Permitir testes livres e roteiros de casos críticos pelo especialista.
- [ ] Classificar apontamentos como blocker, critical, major, minor ou melhoria.
- [ ] Registrar evidência e reprodução de cada apontamento.
- [ ] Converter todo defeito confirmado em teste automático de regressão.

## Pacote 8.5 — Correções e requalificação da RC

- [ ] Corrigir todos os blockers, criticals e majors apontados.
- [ ] Reexecutar integralmente a suíte e os validadores após cada ciclo relevante.
- [ ] Gerar nova RC sem alterar silenciosamente corpus, prompt, modelo ou profile.
- [ ] Reapresentar ao especialista os casos corrigidos e as evidências de regressão.

## Gate Humano Final G8-H

- [ ] Especialista em XML homologou a RC final.
- [ ] Produção aprovada pelos responsáveis técnico e editorial.
- [ ] Zero blocker/critical e todos os major corrigidos.
- [ ] Riscos minor/residuais foram aceitos explicitamente.
- [ ] Rollback, restore, alertas e runbooks foram comprovados.
- [ ] Acessos foram revisados.

Somente a aprovação deste gate autoriza o início do rollout de produção.

## Pacote 8.6 — Ativação acompanhada

- [ ] Executar rollout gradual acompanhado, inicialmente com revisão humana por artigo.
- [ ] Manter kill switch, rollback e modo determinístico disponíveis.
- [ ] Produzir o primeiro pacote com acompanhamento humano.
- [ ] Monitorar o período inicial e interromper/reverter diante de violação dos limites.

## Gate operacional G8-O

- [ ] Primeiro pacote produzido com acompanhamento humano.
- [ ] Período inicial de operação estabilizado.
- [ ] Nenhum incidente crítico ou regressão editorial ficou aberto.
- [ ] Métricas operacionais permaneceram dentro dos SLOs aprovados.
- [ ] Evidências finais de produção foram arquivadas.

---

# FASE 9 — Expansão controlada

## Objetivo

Expandir somente após estabilidade do piloto.

- [ ] Adicionar segundo periódico e novo Journal Profile.
- [ ] Medir regressões no periódico piloto.
- [ ] Adicionar terceiro template.
- [ ] Expandir tabelas complexas e matemática.
- [ ] Expandir suplementos e multimídia.
- [ ] Promover correções recorrentes a regras determinísticas.
- [ ] Validar cada regra candidata antes da promoção.
- [ ] Avaliar generalização para IDML não conhecido.

## Gate de expansão

Cada novo periódico deve possuir corpus, profile, style mapping, métricas, homologação e rollback próprios.

---

# 6. Dependências críticas

| Dependência | Fases afetadas | Plano de contingência |
|---|---|---|
| Documentação SPS vigente | 0–9 | Versionar perfil e bloquear release sem regra confirmada |
| Packtools | 0, 3, 4, 7 | Isolar versão e registrar incompatibilidades |
| XPM | 0, 4, 7, 8 | Worker Linux isolado na mesma VPS; qualificação em VH-02 e serviço em VH-14/16 |
| Amostras reais | 0–3, 7 | Não congelar modelo/parser sem corpus |
| OpenClaw/Swarm | 0, 6–9 | SequentialOrchestrator e revisão humana |
| OpenAI | 6–9 | Pipeline determinístico e modo degradado |
| Capacidade da VPS | 0–9 | Monitorar, limitar recursos e realizar upgrade quando as métricas demonstrarem necessidade |

# 7. Registro de riscos

| ID | Risco | Impacto | Mitigação | Estado |
|---|---|---|---|---|
| R-01 | Reading order incorreto no IDML | Crítico | Corpus real, frames/threads/coordenadas e revisão visual | Mitigação definida |
| R-02 | XPM legado incompatível com SPS 1.10/JATS 1.3 | Crítico | Executor Linux já demonstrado; qualificar regras/consultas sem rebaixar XML, manter adapter desacoplado | Execução resolvida em 2026-10-15; compatibilidade pendente |
| R-03 | Regras SPS mudarem | Alto | SpsProfile versionado e testes de regressão | Aberto |
| R-04 | Capacidade da VPS tornar-se insuficiente | Alto | Monitoramento, limites por serviço e upgrade de hardware sob demanda | Monitorado |
| R-05 | Impacto no sistema atual | Crítico | Compose/network/volumes exclusivos e limites | Mitigado e monitorado |
| R-06 | Prompt injection por artigo | Alto | Ferramentas tipadas, conteúdo não confiável e testes | Aberto |
| R-07 | Vazamento entre empresas | Crítico | Escopo no backend, storage isolado e testes negativos | Mitigado na fundação; monitorado |
| R-08 | Modelo canônico insuficiente | Alto | Corpus antes do congelamento e migrations | Mitigado no contrato; validar no parser |
| R-09 | Confiança de IA mal calibrada | Alto | Evidência, agreement, métricas e revisão humana | Aberto |
| R-10 | Custo ou latência excessivos | Médio/Alto | Envelope compacto, tarifa oficial, cache auditado, preflight e teto agregado | Mitigado tecnicamente; monitorar em piloto |
| R-11 | Falha sem retomada idempotente | Alto | Máquina de estados, idempotency keys e recuperação pelo PostgreSQL | Mitigado na fundação; monitorado |
| R-12 | Perda de dados ou histórico | Crítico | Imutabilidade, backups e restore testado | Mitigado na fundação; monitorado |
| R-13 | Vazamento ou contaminação do corpus | Alto | Manifestos sem conteúdo, acesso restrito e holdout separado | Mitigado; monitorado |
| R-14 | Referências sem `xref` bibliográfico | Alto | Detecção offline, CrossRef Accuracy e resolver determinístico de citações | Mitigado tecnicamente — 81 vínculos/52 alvos; seis divergências qualificadas por fonte e pendentes apenas do Gate Humano Final |
| R-15 | Patch escalar quebrar invariantes de `RichText` | Alto | Patch atômico de `plain` + `inlines` e validação prévia | Mitigado; benchmark v1.3 preparado sem execução de agentes |
| R-16 | Segredo do OpenClaw compartilhado exposto em comando de inicialização | Alto | Não reutilizar no IDML; rotacionar separadamente em janela do sistema existente | Aberto no sistema legado; isolado do IDML |
| R-17 | Credencial OpenAI reutilizada entre o OpenClaw existente e o staging IDML | Médio/Alto | Injetar apenas no overlay opt-in, nunca em API/worker; manter kill switch; coordenar rotação e separar a chave se o acoplamento se tornar operacionalmente inadequado | Aceito pelo usuário; mitigado tecnicamente e monitorado |
| R-18 | Harness de benchmark contorna intencionalmente o fluxo persistido da aplicação | Alto | Dois casos minimizados, dupla confirmação, flags falsas, nenhuma aplicação de patch, output privado, orçamento agregado, tentativa única e reset final do gateway | Mitigado para avaliação; proibido como caminho de produção |
| R-19 | Agentes correlacionados produzirem falso consenso | Crítico | Sessões/prompts separados, alvos ocultos, críticos independentes e juiz determinístico com abstenção | Aberto; medir no laboratório multiagente |
| R-20 | Homologação humana tardia encontrar erro arquitetural caro | Alto | Corpus holdout, testes V-01 a V-15, RC reproduzível e correções com regressão antes do go-live | Aceito pelo usuário; mitigação planejada |
| R-21 | Overfitting ao único artigo/template ESA | Crítico | Trilha 7C, regressões gerais, múltiplos artigos e reserva de `holdout-human` | Materializado pelo e20240135; correção em andamento |
| R-22 | Atualização de SPS/JATS/validadores invalidar evidências | Alto | Fixar versões, monitorar mudanças, executar regressão e manter rollback de profile | Aberto; controle planejado |

# 8. Definition of Done global

Um item somente é considerado concluído quando:

- [ ] implementação e documentação correspondem;
- [ ] critérios de aceite foram testados;
- [ ] testes automatizados relevantes passam;
- [ ] segurança e isolamento foram avaliados;
- [ ] observabilidade foi incluída;
- [ ] versões e dependências foram registradas;
- [ ] não existem secrets em código ou logs;
- [ ] evidências estão vinculadas ao item;
- [ ] riscos residuais estão documentados;
- [ ] revisão técnica automatizada/multiagente necessária foi realizada.
- [ ] para RC final, homologação do especialista em XML foi realizada e seus defeitos foram regredidos.

# 9. Critério final de READY_FOR_SCIELO

`READY_FOR_SCIELO` deve ser resultado de política determinística versionada, nunca apenas decisão de um agente.

Condições conceituais:

- [ ] Ingestão segura aprovada.
- [ ] Canonical Article Model válido.
- [ ] Metadados obrigatórios satisfeitos.
- [ ] Fidelidade acima dos limiares.
- [ ] Autores, afiliações e referências resolvidos.
- [ ] Figuras, tabelas, equações e cross-references resolvidos.
- [ ] Assets presentes e íntegros.
- [ ] XML well-formed, JATS/DTD e SPS válidos.
- [ ] Packtools aprovado.
- [ ] XPM aprovado, quando aplicável.
- [ ] Sem ReviewItem bloqueador.
- [ ] Package Builder e ConversionManifest aprovados.
- [ ] Usuário ou processo de release possui autorização válida.
- [ ] Auditoria completa disponível.
- [ ] Gate Humano Final G8-H aprovado pelo especialista em XML e responsáveis.

# 10. Registro de decisões

Decisões arquiteturais devem ser registradas em:

```text
docs/adr/ADR-NNN-titulo.md
```

ADRs iniciais esperados:

- [x] ADR-001 — versão inicial SPS/JATS.
- [x] ADR-002 — estratégia XPM.
- [x] ADR-003 — ambiente de desenvolvimento e produção.
- [x] ADR-006 — storage de artefatos.
- [x] ADR-007 — fila e execução de jobs.
- [x] ADR-008 — autenticação local ou OIDC.
- [x] ADR-009 — RBAC e isolamento multiempresa.
- [x] ADR-010 — modelos de domínio versionados.
- [x] ADR-011 — governança do corpus e holdout.
- [ ] ADR — estrutura do Canonical Article Model.
- [x] ADR-004 — estratégia de reading order.
- [x] ADR-005 — abstração de orquestração e fallback.
- [x] ADR-012 — política determinística de release.
- [x] ADR-013 — egress controlado do provider OpenClaw.
- [x] ADR-014 — gates técnicos, RC e homologação humana final.

# 11. Histórico deste plano

| Data | Alteração | Responsável |
|---|---|---|
| 2026-08-24 | Criação do planejamento por fases; nenhuma implementação iniciada | Codex |
| 2026-08-24 | Fase 0 concluída; Gate G0 aprovado como `GO_WITH_CONSTRAINTS`; nenhuma funcionalidade desenvolvida | Codex |
| 2026-08-24 | Fase 1 concluída; Gate G1 aprovado com testes locais e validação ao vivo na VPS; Fase 2 não autorizada | Codex |
| 2026-08-24 | Fase 2 autorizada; corpus, modelos e métricas implementados; Gate G2 em validação | Codex |
| 2026-08-24 | Fase 2 concluída; Gate G2 aprovado localmente e na VPS; Fase 3 não autorizada | Codex |
| 2026-08-24 | Fase 3 autorizada e concluída; parser, profile ESA, builder JATS 1.3 e validação offline implementados; Gate G3 aprovado; Fase 4 não autorizada | Codex |
| 2026-08-24 | Fase 4 implementada; validação/fidelidade/pacote/policy concluídos; Gate G4 bloqueado por erros SPS/editoriais e ausência do XPM do candidato; Fase 5 não autorizada | Codex |
| 2026-08-26 | Fase 5 concluída; revisão humana, interface, identidade/MFA, RBAC e dupla aprovação editorial implementados; Gate G5 aprovado; Gate G4 continua bloqueando release | Codex |
| 2026-08-26 | Fundação da Fase 6 implantada com flags desligadas; agente OpenClaw isolado e benchmark real v1.1 executado; G6 permanece bloqueado por baixa qualidade, custo não observável e ausência de baseline humano | Codex |
| 2026-08-26 | Resolvedor determinístico ESA concluído; 81 vínculos bibliográficos gerados, parser de células corrigido e CrossRef Accuracy incorporada ao G3; seis divergências com o XML aprovado aguardam adjudicação humana | Codex |
| 2026-08-27 | Resolvedor bibliográfico implantado na VPS com backup/restore e rollback; serviços saudáveis e flags de IA mantidas desligadas | Codex |
| 2026-08-27 | Patch atômico de RichText implantado com backup/restore e rollback; prompts 1.1 e benchmark v1.2 preparados; nenhum agente executado e flags mantidas desligadas | Codex |
| 2026-08-27 | Vínculo operação-evidência e envelope compacto implantados; schema 1.1, prompts 1.2 e benchmark v1.3 preparados; nenhum agente executado e flags mantidas desligadas | Codex |
| 2026-08-27 | Política monetária fail-closed implementada e implantada: custo do provider ou tarifa exata versionada, auditoria de proveniência e bloqueio `COST_UNAVAILABLE`; alias real permanece sem preço oficial verificado e flags desligadas | Codex |
| 2026-08-27 | Tarifa oficial do `gpt-5.4-mini` fixada; cache, preflight, teto agregado por artigo e cliente OpenResponses restrito implementados e implantados; integração continua desligada até existir gateway dedicado ao IDML | Codex |
| 2026-08-27 | Gateway OpenClaw dedicado implantado com digest fixo, token próprio, rede interna sem egress, endpoint mínimo, estado/backup próprios e zero sessões; flags de IA permanecem desligadas | Codex |
| 2026-08-28 | Staging controlado do provider preparado com chave reutilizada por autorização explícita, proxy allowlist, saída direta bloqueada e kill switch testado; nenhum agente ou chamada autenticada foi executado e o estado final voltou a ficar desligado | Codex |
| 2026-08-31 | Harness do benchmark real v1.3 preparado com dois casos, teto agregado, confirmação explícita, runner isolado e reset final; dry-run reproduzido localmente/VPS, execução sem confirmação bloqueada e nenhum agente chamado | Codex |
| 2026-09-01 | Primeira janela OpenClaw concluída em dois casos reais minimizados; custo de 13.024 micro-USD, contratos e cleanup aprovados; metadado exato e referência inconclusiva sem baseline humano; G6 permanece bloqueado | Codex |
| 2026-09-01 | Governança revisada: desenvolvimento planejado até a prontidão de produção; quinze famílias de testes e validação multiagente precedem a RC; homologação do especialista em XML transferida para o Gate Humano Final G8-H antes do go-live | Codex |
| 2026-09-01 | Laboratório multiagente v1 implementado e executado em metadados/referências por 32.824 micro-USD; metadados exato, referência atômica rejeitada antes dos críticos e convertida em regressão; cleanup integral aprovado e G6-T ainda pendente | Codex |
| 2026-09-01 | Laboratório multiagente v2 executado nos dez casos ESA disponíveis por 218.200 micro-USD; contrato atômico e contabilização fail-closed reforçados; nove saídas não JSON rejeitadas; cleanup, rotação do token e relatório sanitizado concluídos; G6-T permanece pendente | Codex |
| 2026-09-01 | Matriz adversarial v1 concluída localmente e reproduzida na VPS com `--network none`: 30 casos em seis domínios, 84 papéis simulados, 100% dos oráculos e zero provider/custo; paths passaram a ser domain-bound; G6-T ainda requer evidência real e JSON confiável | Codex |
| 2026-09-01 | Grounding `normalized_exact` adicionado ao juiz: invenção é rejeitada mesmo com ID/locator/hash válidos; oito de dez alvos ESA têm suporte integral e duas referências ficam fail-closed até ampliação da evidência; G6-T segue pendente por JSON real e cobertura real | Codex |
| 2026-09-02 | Evidência segmentada v1.4 implementada e implantada sem truncamento: 10/10 alvos ESA sustentados, 12 segmentos autenticados, duas referências longas remontadas integralmente; formato legado preservado, janela OpenClaw v3 preparada localmente/VPS sem provider; G6-T segue pendente por JSON real e corpus real de estrutura/matemática | Codex |
| 2026-09-02 | Saída estruturada OpenClaw validada por function call terminal: quatro papéis reais concluídos no caso de metadados, referência de 734 caracteres rejeitada fail-closed por prefixo incompleto, contexto dedicado ampliado para 32 mil, custo acumulado conservador de 627.552 micro-USD e cleanup integral; G6-T segue pendente por fidelidade longa e corpus real de estrutura/matemática | Codex |
| 2026-09-02 | Referência real de 734 caracteres validada por intent autenticado e materialização atômica: fidelidade/Jaccard 1,0, oito checks, dois críticos e adjudicador aprovados; 148 testes com cobertura 84,86%, custo acumulado 685.949 micro-USD e cleanup integral; G6-T segue pendente apenas pelo corpus real autorizado de estrutura/matemática | Codex |
| 2026-09-02 | Estrutura hierárquica e 15 fórmulas PDF do artigo autorizado preservadas deterministicamente; V9 validou casos reais derivados de estrutura/matemática nos quatro papéis por 44.523 micro-USD, 153 testes atingiram 85,02% e o cleanup integral passou; G6-T segue pendente pela transição atômica para MathML e pelo mapeamento inline | Codex |
| 2026-09-03 | Transição imagem→MathML atômica e segura implantada; 15 fórmulas display preservam ordem/rótulo, 2/2 lacunas inline são detectadas, candidato MathML passa JATS e V10 conclui quatro papéis por 31.747 micro-USD; proposta e críticos passam, adjudicador se abstém por consenso correlacionado; 164 testes e 85,04% de cobertura; G6-T segue pendente por transcrição visual/inline independente | Codex |
| 2026-09-04 | Transporte visual autenticado e recortes PDF a 300 DPI concluídos; OpenClaw declarou `gpt-5.4-mini` como `text+image`; fórmula display e duas inline foram transcritas sem expor o gold, passaram 24 checks, seis críticas, três adjudicações e equivalência MathML semântica; custo acumulado 935.233 micro-USD, 181 testes/84,76%; imagem `phase6-visual-formula-v4` saudável, flags/provider desligados; G6-T segue para QA/repair limitado | Codex |
| 2026-09-04 | Auditoria assistida e reparo semântico limitado concluídos; janela final V14 completou três casos por 85.654 micro-USD, com 24 checks, equivalência semântica 3/3, seis críticas, dois aceites e uma abstenção segura; 192 testes/84,86%, cleanup e deploy `phase6-qa-repair-v1` aprovados; Gate G6-T aprovado apenas para iniciar a Fase 7 | Codex |
| 2026-09-04 | Fase 7 iniciada; V-01 verificou 6 manifestos e 21/21 artefatos privados, bloqueia duplicação/contaminação/exposição do holdout e reproduziu o fingerprint local/VPS sem rede; gate incluído na CI, 199 testes/84,89%, backup/restore e imagem `phase7-v01-corpus-integrity-v1` saudáveis; Pacote 7.1 segue em V-02 | Codex |
| 2026-09-08 | V-02 concluído: ingestão ZIP/XML endurecida, referências IDML incompletas classificadas, scanner fail-closed e limpeza/cancelamento testados; 26/26 casos sintéticos, 6/6 IDML reais, 226 testes/85,29%, gate local/CI/VPS sem rede, backup/restore e imagem `phase7-v02-ingest-security-v1` saudáveis; Pacote 7.1 segue em V-03 | Codex |
| 2026-09-08 | V-03 a V-05 concluídos: leitura/fidelidade IDML, invariantes do modelo canônico e construção JATS/SPS determinística foram validadas localmente, no corpus autorizado e na VPS; imagem `phase7-v05-jats-construction-v1` saudável | Codex |
| 2026-09-09 | V-06 qualificado e implantado com restrição: Packtools/SPSValidator ativo e rollback fixados em quatro imagens e executados isoladamente sem exceções; Canonical Article 1.4.0 incorporou metadados formais; 257 testes/86,44%; backup/restore, gate VPS sem rede e imagem `phase7-v06-formal-validators-v1` saudáveis; falso positivo externo de afiliação e worker XPM Windows permanecem explícitos e sem waiver de release; próxima família V-07 | Codex |
| 2026-09-09 | V-07 instrumentado: comparador semântico content-safe e gate de mutações detectam omissão, invenção, alteração, duplicação e deslocamento; inspeção visual aprovou 10/10 páginas do PDF ESA; baseline real atingiu recall textual 0,999269 e revelou bloqueios rastreáveis em metadados, estrutura, figuras, tabelas, fórmulas, notas e cross-references; 272 testes/86,40%, backup/restore e deploy `phase7-v07-semantic-fidelity-v1` saudáveis, com gate VPS sem rede e sem corpus privado; candidato permanece corretamente reprovado e segue para correção por domínio | Codex |
| 2026-09-09 | Primeiro lote corretivo V-07 concluído localmente: DOI extraído do estilo `0.1.doi`, captions separadas de seus labels e figuras ordenadas por número preservando a intercalação; figuras atingiram precisão/recall 1,0 e os bloqueadores caíram de 39 para 37; 272 testes/86,37%; notas, estrutura, tabelas, fórmulas, corpo e cross-references seguem para os próximos lotes | Codex |
| 2026-09-09 | Segundo lote corretivo V-07 concluído e implantado: o bloco `03.5` passou a gerar correspondência, datas editoriais, financiamento, conflito e notas de editores; o comparador unificou marcações JATS semanticamente equivalentes; notas passaram de 4 omissões para 2 exatas e 2 alterações rastreadas por ORCID ausente na fonte; bloqueadores caíram de 37 para 35; 274 testes/86,32%; backup/restore e deploy `phase7-v07-correspondence-v1` saudáveis, agentes desativados e corpus restrito somente local | Codex |
| 2026-09-10 | Terceiro lote corretivo V-07 concluído e implantado: estilos inline das tabelas preservados, figuras/tabelas posicionadas pela primeira menção, contribuições e disponibilidade movidas ao `back`, e conteúdo de fórmulas separado do corpo no comparador; estrutura, corpo e tabelas atingiram precisão/recall/F1 1,0; bloqueadores caíram de 35 para 25; 278 testes/86,61%; backup/restore, gate sem rede e deploy `phase7-v07-structure-tables-v1` saudáveis, com agentes desativados e corpus restrito local | Codex |
| 2026-09-10 | V-07 concluída e implantada: 17 fórmulas qualificadas visualmente, identificador editorial e dois ORCIDs enriquecidos por catálogo, diferenças de metadados/cross-references ligadas a autoridades exatas e gate real aprovado com zero bloqueios; 287 testes/86,68%, Ruff/mypy, backup/restore e imagem `phase7-v07-qualified-v1` saudáveis; flags/provider desligados e corpus/catálogos privados somente locais; próxima família V-08 | Codex |
| 2026-09-11 | V-08 concluída e implantada: materialização confiável por evidence intent eliminou cópia incompleta e preservou RichText; janela real final teve 10/10 propostas exatas, nove aceites efetivos e uma rejeição semântica segura; regressão do adjudicador passou; matriz 30/30, 84 papéis e sete mutações de contrato passaram; custo novo 297.872 micro-USD; backup/restore e gate sem rede passaram; imagem `phase7-v08-assistive-v1` saudável, flags/provider desligados e zero persistência; próxima família V-09 | Codex |
| 2026-09-11 | V-09 concluída e implantada: 35 testes dedicados, 305 testes completos/87,02%, 40 operações autenticadas e 30 multiempresa inventariadas; zero achado crítico/alto aberto e zero vazamento conhecido; limitação Redis, equalização de login, auditoria de falhas, redaction de logs, contratos anti-mass-assignment e cabeçalhos defensivos implementados; backup/restore e gate sem rede passaram; imagem `phase7-v09-security-v1` saudável; próxima família V-10 | Codex |
| 2026-09-11 | V-10 concluída e implantada: jobs reais de conversão IDML e pacote SciELO, snapshots/artefatos atômicos, idempotência estrita, cancelamento/retry/retomada, revisão, manifesto, hashes, dupla aprovação e UI operacional passaram de ponta a ponta; 308 testes/87,44%, gate local/VPS sem rede, backup/restore e imagem `phase7-v10-operational-v1` saudáveis; OpenClaw desligado e banco de agentes em zero; próxima família V-11 | Codex |
| 2026-09-11 | V-11 concluída e implantada: 121 entradas binárias arbitrárias, 128 mutações de ZIP, cinco XMLs hostis e propriedades de Unicode, conteúdo misto, ordem e empacotamento passaram; 13/13 mutações comportamentais foram detectadas; uma propagação de `zlib.error` foi encontrada, corrigida e coberta por regressão; 317 testes/87,50%, Ruff/mypy, gate local/VPS read-only sem rede, backup/restore e imagem `phase7-v11-robustness-v1` saudáveis; próxima família V-12 | Codex |
| 2026-09-11 | Novo artigo e20240135 testado como caso não usado anteriormente: comparador bloqueou 108 divergências, Packtools registrou 108 críticos/79 erros e o pacote recusou ativos ausentes; risco R-21 materializado; aberta a trilha corretiva 7C, baseline 7C-00 concluído e V-12 adiada até G7C-08 | Codex |
| 2026-09-14 | 7C-01 concluída: manifesto verificou 12/12 artefatos privados; inventário content-safe mapeou 60 Stories, 68 frames, 54 objetos/ativos, 89 links, 292 estilos e 697 evidências; gate reproduziu deterministicamente os 108 bloqueios sem mismatch; regressões anti-vazamento e anti-special-case adicionadas; 321 testes/87,58%, Ruff e mypy aprovados; próxima etapa 7C-02 | Codex |
| 2026-09-14 | 7C-02 concluída: PDFs `FigNN` deixaram de ser classificados como fórmulas, sete captions foram ligadas um-a-um a sete `graphic`, ordem global 1–7 restaurada e seção artificial removida; figuras e mídia atingiram precisão/recall/F1/fidelidade 1,0, bloqueios caíram de 108 para 94 e os sete JPGs finais passaram no pré-empacotamento por ordinal; gate real determinístico sem mismatch, 325 testes/87,50%, Ruff e mypy aprovados; próxima etapa 7C-03 | Codex |
| 2026-09-15 | 7C-03 concluída: parser e mapper passaram a detectar 43 fórmulas na ordem correta (32 inline/11 display); 43 recortes PDF autenticados foram avaliados com gold oculto por proponente, dois críticos e adjudicador; catálogo registrou 43 aceites, 86 passes de críticos, zero abstensão incorporada e custo de 1.793.642 micro-USD; XML determinístico/válido com zero fórmula gráfica, domínios `formulas` e `formula_content` aprovados e bloqueios gerais reduzidos de 94 para 33; 335 testes/87,59%, Ruff, formatação e mypy aprovados; próxima etapa 7C-04 | Codex |
| 2026-09-16 | 7C-04 concluída: hierarquia reproduziu 26 seções nos níveis 6/11/9; sete notas estruturais e dez unidades semânticas foram aprovadas; corpo sem omissão, invenção, alteração, deslocamento ou token não autenticado, com precisão 0,998969 e recall 1,0; tabelas, referências e 43 fórmulas permaneceram aprovadas; bloqueios gerais reduzidos de 30 para 6; gate determinístico sem mismatch, 343 testes/87,72%, Ruff, formatação e mypy aprovados; próxima etapa 7C-05 | Codex |
| 2026-09-16 | 7C-05 concluída: quatro autores e ORCIDs preservados da fonte e componentes confirmados por autoridade Crossref independente; título do periódico e `other=00224` emitidos com proveniência; chamada da referência ordinal 18 resolvida, atingindo 39/39 cross-references e 35 destinos; corpo exato 5.814/5.814 sem duplicação; comparador com zero bloqueio nos 12 domínios após 24 fórmulas qualificadas; XML determinístico e válido sem issues, gate sem mismatch, 350 testes/87,70%, Ruff, formatação, mypy e diff check aprovados; próxima etapa 7C-06 | Codex |
| 2026-09-17 | 7C-06 concluída: metadados formais content-addressed, idiomas, afiliações, 14 papéis CRediT, IDs, acessibilidade e 35 referências estruturadas implementados; oito erros reais de paginação e nove divergências de citação eliminados; pacote byte a byte reproduzível com XML, PDF e sete JPEGs, vínculos completos e zero issue offline; gate externo aceita somente códigos/quantidades comprovados e registra zero erro real, mantendo `release_ready=false` pelo XPM SPS 1.10 pendente; 360 testes/87,33%, Ruff, formatação e mypy aprovados; próxima etapa 7C-07 | Codex |
| 2026-09-17 | 7C-07 concluída: seis domínios reavaliados por proponente, dois críticos e adjudicador em 24 chamadas, com seis propostas somente para revisão humana, cinco exatas e uma fórmula semanticamente equivalente; precisão/recall controlados 1,0, zero reparo/falso consenso/tool/Skill e custo de 140.447 micro-USD; cinco controles negativos falharam fechado e matriz adversarial passou 30/30; cleanup da VPS confirmou serviços saudáveis, flags falsas e zero credencial, rede, sessão ou persistência; gate content-safe/CI, 367 testes/87,29%, Ruff, formatação e mypy aprovados; próxima etapa 7C-08 | Codex |
| 2026-09-21 | 7C-08 concluída: dois artigos requalificados com zero bloqueio semântico; 106/106 stories preservadas; regressão de ORCID editorial ambíguo e compatibilidade de catálogo corrigidas; 380 testes/87,31%, Ruff/mypy e 18 gates locais/VPS read-only sem rede aprovados; imagem `phase7-7c08-v1` implantada com backup/restore e rollback real comprovados; 23 serviços preservados, flags falsas e corpus privado somente local; V-07 PASSOU NO CORPUS ATUAL; próxima V-12, mantendo XPM e Gate Humano Final como bloqueios de release | Codex |
