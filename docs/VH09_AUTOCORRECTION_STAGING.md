# VH-09 — Executor: staging privado e fontes exatas

Checkpoint inicial 2026-10-19, atualizado em 2026-10-20.
**VH-09 em andamento**, dentro da entrega 2 da VH1.
Este documento descreve os checkpoints iniciais, sem implantação naquela etapa.
Persistência, PostgreSQL nativo e implantação posteriores estão registrados em
`VH09_REVALIDATION_HISTORY_AND_DEPLOY.md`. A linhagem e a restauração de rascunhos
posteriores estão em `VH09_CANONICAL_HEAD_AND_RESTORE.md`. Não é conclusão da
VH-09 ou aprovação SciELO.

## Entregue neste incremento

- `services/autocorrection_sources.py`: extrator fechado, sem XPath livre, rede
  ou extração ZIP para disco. Confere IDML seguro, membro/elemento único, hash do
  trecho e correspondência exata com a evidência canônica. Suporta texto literal
  `Story/ParagraphStyleRange/CharacterStyleRange/Content/Br`, offsets de caracteres
  Unicode completos ou `Link@LinkResourceURI` com nome lógico simples. Recusa
  omissão silenciosa de tabelas/notas/objetos, URI/path, ambiguidade e hash ausente.
- `services/autocorrection_executor.py`: carrega snapshot/fonte pela empresa,
  verifica armazenamento endereçado por conteúdo, bytes e `clamav_clean`, resolve
  grants/revogações no banco e reavalia a política VH-08. A IA não fornece os valores
  finais, paths, contexto de autoridade ou evidências confiáveis.
- Cópia candidata com substituições fechadas, before/after hashes, verificação
  de que a normalização canônica não acrescentou mudanças e reconstrução de XML.
  Validador offline recebe exatamente o XML novo; relatório de outro hash ou
  exceção resulta em indisponibilidade, nunca em aprovação herdada.
- Recusa/abstenção persistida sem operações parciais. Tentativa com candidata
  continua `requires_revalidation=true`, `active_snapshot_changed=false`,
  `release_approved=false`, inclusive se a validação offline passar.
- Recibos sem valores/texto privado; candidata, XML e relatório são dados privados
  da empresa. Descarte adiciona recibo ligado ao hash anterior e preserva a tentativa.

## Transação e histórico

O chamador é dono de commit/rollback. Savepoint protege a tentativa; falha na
construção não deixa candidata parcial. SQLite inicia transação real antes do
savepoint, inclusive quando não houve DML anterior, para não confirmar mudanças
indevidamente ao liberar o savepoint. Duas sessões reais foram exercitadas em
SQLite de arquivo; uma só tentativa é confirmada para a mesma intenção.

Locks de recurso/itens/grants em PostgreSQL foram qualificados posteriormente no
ensaio isolado de staging/histórico com duas sessões; isso não qualifica a promoção
ainda não implementada. SQLite usa transação de escrita serializada.
Índice único por empresa/recurso/intenção é a última barreira à duplicação.
Trocar ID da proposta ou ordem das operações não cria outra tentativa.

`scope.review_version` é comparado à versão do recurso nesta camada. Além disso,
snapshot de trabalho atual, versões/estados dos itens e decisões humanas são lidos no
banco. Caminhos atuais e históricos são protegidos conservadoramente. Há nova
checagem após a construção; mudança concorrente detectada aborta o staging.
Isso não substitui a futura barreira atômica de promoção: snapshot, estado humano,
autorização e validade terão que ser conferidos novamente nesse instante.

Repetição retorna **a tentativa histórica**, não nova autorização para usar a
candidata: pode existir revogação/descarte posterior. Nenhum consumidor deve tratar
`state=staged` como candidata aprovada. A futura promoção deve consultar descarte,
grants e estados atuais; não basta ler o recibo antigo.

`autocorrection_models.py` contém quatro tabelas: `automation_grants`,
`automation_grant_revocations`, `automation_attempts`, `automation_discards`.
Migração `a8c9d0e1f203` após `f7b8c9d0e1f2`; registrada em `migrations/env.py`.
Proteções ORM e triggers de UPDATE/DELETE no SQLite/PostgreSQL. Migration testada
no SQLite, SQL PostgreSQL compilada. `Base.metadata.create_all` sozinho não instala
triggers; ambientes implantados precisam da migração. Downgrade remove as quatro
tabelas e seus dados: somente testado em banco descartável, não executar na VPS
como rotina de rollback de artigo. Não protege contra administrador do banco capaz
de remover triggers; controles operacionais/RBAC permanecem necessários.

Nenhuma tentativa é inserida em `DomainSnapshot`, cuja maior revisão era consumida
pela revisão humana naquele checkpoint. Desde o incremento de 21/10, os consumidores
de trabalho usam a linhagem explícita; candidatas continuam privadas até promoção
formal. Nenhuma decisão histórica ou contrato assistivo foi reinterpretado.

## Fronteiras ainda não integradas

O serviço é interno, sem rota HTTP, worker ou flag ativa. Contexto de runtime,
achados, perfil e validador são dependências confiáveis do servidor; não expor uma
rota que aceite esses dados como autoridade de agente/cliente. Contadores fornecidos
ao contexto ainda não são reserva distribuída de custo/concorrência: VH-10 integra.

`register_extraction_grant` é provisão interna sob autorização da fonte, não
consentimento autenticado por um hash. Nesta qualificação as autorizações são
fixtures sintéticas. O produtor administrativo deve vinculá-las às decisões reais
já registradas, sem pedir aceite humano a cada correção. Nenhuma autorização de
artigo real foi inventada ou criada automaticamente a partir do texto da IA.

O parser legado não garante hash de trecho/locator fino em todas as evidências.
O produtor opt-in descrito abaixo agora prepara seletores verificáveis, sem alterar
snapshots históricos nem reduzir as exigências VH-08. Links URI complexos e
estruturas fora da gramática fechada continuam recusados.

## Verificação do checkpoint inicial — 2026-10-19

85 testes novos aprovados e 312 na regressão direcionada, zero falhas/erros/skip.
Cobertura dos **três módulos novos**, não do sistema: 334/351 linhas (**95,16%**),
85/102 ramificações (**83,33%**), combinada **92,49%**. Inclui operação individual
e lote, bytes adulterados/ausentes, empresa errada, grant vencido/revogado/ambíguo,
instruções XML perigosas, proteção de paths ancestrais/descendentes, histórico
humano, revisão concorrente, erro de validador, interrupção, rollback externo,
idempotência, duas sessões, descarte e triggers de histórico no banco migrado.

Ruff global, mypy 121 módulos, formatação do incremento e verificação da prova
VH-08 aprovados. Sem nova suíte integral, novo benchmark de artigo real ou CI
global aprovado. Registro de execução local por hashes:
`benchmarks/qualification/reports/vh09-staging-local-v1.json` (registro histórico,
não gate de aprovação do XML). Evidências temporárias locais:
`tmp/vh09-staging-tests.xml`, `tmp/vh09-staging-coverage.json`,
`tmp/vh09-focused-regression.xml`.

```powershell
.venv/Scripts/python -m pytest tests/test_autocorrection_sources.py tests/test_autocorrection_executor.py tests/test_autocorrection_transactions.py --no-cov
.venv/Scripts/python -m ops.qualify_vh08_autocorrection --check benchmarks/qualification/reports/vh08-autocorrection-policy-v2.json
```

## Próximo passo delimitado — concluir VH-09

1. Persistência concluída pelo wrapper `autocorrection_history.py`, com
   idempotência e histórico. O construtor de pacote abaixo continua sem gravar.
2. Concluir promoção/restauração de pacote sem apagar histórico, com rechecagem
   atômica de fonte/decisões/descarte/validações. A linhagem explícita e a restauração
   conservadora de rascunhos já foram qualificadas em 21/10; não inserir candidata
   não validada nesse fluxo. Ainda falta reconstruir/revalidar o pacote restaurado
   e implementar a promoção formal. Não duplicar snapshots nem apagar tentativas.
3. Migração e concorrência de staging/histórico qualificadas em PostgreSQL isolado;
   repetir para a futura promoção. Descarte de uma cópia nunca promovida não
   comprova restauração. Integrar execução real dos
   validadores aplicáveis; XPM ainda exige a conexão prevista em VH-02/07.

Depois VH-10 conecta agentes/ciclos reais. Nos checkpoints iniciais deste documento
não houve deploy, mudança de flags/banco ativo, XML real ou chamada paga.
O deploy posterior, com migrações e flags desligadas, está documentado em
`VH09_REVALIDATION_HISTORY_AND_DEPLOY.md`.
DOCTYPE/JATS, erro residual e consultas XPM em VH-02/07 continuam pendentes;
não há aprovação formal do XML nem G-HOMOLOG.

## Incremento de integração — 2026-10-20

### Evidências e autorização por lote

`pipeline/autocorrection_evidence.py` fornece `run_evidence_ready_pipeline`:
executa o pipeline existente e acrescenta evidência exata apenas a campos já
vinculados à fonte. Confere que o XML permanece byte a byte igual. Não preenche
valores nessa etapa. O catálogo vincula IDML, canônico, perfil e as três operações
VH-08; evidências anteriores são preservadas. Seletores virtuais reais do parser
`Story:paragraph:N` são resolvidos deterministicamente; colisões com `Self`, fontes
humanas, correspondências parciais de instituição e fontes ambíguas são recusadas.

`services/autocorrection_authorization.py` recalcula o catálogo a partir dos bytes
armazenados e deriva grants por campo somente de uma autorização administrativa
explícita de lote. Contrato `autocorrection-batch-authorization-1.0`, caminho fixo
`enrichment_root/autocorrection-authorizations/{authorization_id}.json`, limite
16 KiB, sem caminhos de cliente e sem symlink/junction. Confere empresa, recurso,
fonte, canônico, catálogo, perfil, destino local/VPS e validade máxima de 30 dias.
O hash da decisão é rastreabilidade, **não é autenticação/consentimento**.

Não reinterpreta as autorizações antigas de catálogos como permissão irrestrita.
Grants individuais históricos continuam compatíveis. Novos grants por lote levam
ID/hash da autorização-mãe; o executor a relê antes e depois da construção.
Revogar, remover ou modificar a autorização-mãe invalida seus filhos. Provisão
repetida é idempotente e não ressuscita grant revogado.

Não exige especialista aprovando cada correção. A administração deve provisionar
o lote sob a autorização de fonte já concedida. Nesta execução foram usadas
autorizações sintéticas em diretórios temporários, não permissões reais inventadas.
O entrypoint é interno/opt-in: o worker e os snapshots antigos não foram alterados.

### Pacote completo e nova revalidação

`services/autocorrection_package.py`, entrada `revalidate_candidate_package`:

- Recarrega tentativa, cabeça canônica, versão do recurso, estado humano, grants,
  autorização-mãe e fontes da empresa; rejeita descarte/revogação. Reavalia VH-08
  e reconstrói os valores a partir da fonte, inclusive quando os hashes de uma
  candidata adulterada tenham sido recalculados.
- Lê PDF explicitamente selecionado pelo servidor e imagens presentes no canônico
  via armazenamento por hash, `clamav_clean`, tamanho e bytes conferidos. A seleção
  do PDF ainda é responsabilidade do fluxo confiável; conferir seus bytes **não
  comprova correspondência científica/visual** com o artigo.
- Exige vínculo exato e único entre `graphic`/`inline-graphic` e imagens. Não usa
  a heurística de número de figura disponível no empacotador genérico. Ativos
  extras, faltantes ou reutilizados ambiguamente bloqueiam a execução automática.
  Este caminho qualifica JPEG/PNG/TIFF com nomes simples; não amplia a allowlist.
- Reconstrói ZIP/manifesto determinísticos, com limite conservador de bytes. Só
  permite renomear os hrefs para o padrão do pacote. Compara a árvore XML completa
  em C14N e DOCTYPE; texto, tabelas, fórmulas, referências, xrefs, PDF e imagens
  não podem mudar silenciosamente durante o empacotamento.
- Executa novamente o validador offline sobre o XML empacotado. Erro, hash errado
  ou relatório inconsistente não autoriza chamada externa. Quando offline passa,
  `assess_package` recebe exatamente o XML novo para Packtools e ZIP novo para
  SPSValidator, pelas dependências confiáveis já existentes.
- Reconfere estado, fontes, autorizações e relógio após a execução. Mudança/expiração
  invalida o resultado. Devolve pacote e relatórios privados e recibo redigido
  vinculado aos novos hashes; **não grava artefato, não muda cabeça nem promove**.

`assess_package` ainda declara XPM indisponível neste caminho. Mesmo duas respostas
externas positivas mantêm `complete=false`, `promotion_authorized=false` e
`release_approved=false`. Não há aprovação herdada de um XML/pacote anterior.

Os testes externos desta integração usam executores sintéticos; o validador
offline/JATS é também executado de verdade sobre a fixture mínima e registra seus
erros, sem escondê-los. Não é benchmark de artigo real, inspeção visual de mídia ou
nova execução Packtools/SPSValidator/XPM na VPS.

### Verificação deste incremento

**82 testes adicionados**, 167 testes VH-09 e **421 na regressão direcionada
aprovados**, zero falhas/erros/skip. Os conjuntos se sobrepõem, não somam 588.
Cobertura dos seis módulos VH-09, não do sistema: 761/807 linhas (**94,30%**),
229/274 ramificações (**83,58%**), combinada **91,58%**. O escopo cresceu em
relação aos três módulos do checkpoint anterior; não comparar os percentuais
como se representassem exatamente o mesmo código. A execução de cobertura
registrou um warning.

Ruff global, mypy de 124 módulos, formatação dos 11 arquivos do incremento e
prova VH-08 aprovados. Registro local por hashes:
`benchmarks/qualification/reports/vh09-integration-local-v1.json`. Preservado
`vh09-staging-local-v1.json` como checkpoint histórico, não prova da fonte atual.
Evidências: `tmp/vh09-integration-tests.xml`, `tmp/vh09-integration-focused.xml`
e `tmp/vh09-integration-coverage.json`. Sem nova suíte integral ou aprovação CI.
