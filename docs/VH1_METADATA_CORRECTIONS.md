# VH-05 — correções de metadados e precisão das fontes

Checkpoint: 2026-10-07. **VH-05 concluída no desenvolvimento candidato; sem implantação, aprovação integral do
XML ou liberação G-HOMOLOG.** Continuação do lote 2 da lista única, sem nova fase.

Continuidade posterior: os vínculos de fórmulas foram corrigidos e revalidados
na VH-06; os dois artigos estão sem críticos/erros nas duas ferramentas fixadas,
mas há pendência de fidelidade científica. Estado vigente e próximo passo em
`VH1_FORMULA_LINKS_AND_FIDELITY.md`; contagens abaixo são históricas da VH-05.

## Checkpoint atual — presença de revisões conforme SPS 1.10

Evidências: `vh1-history-images-v1.json` e `vh1-history-linux-v1.json`, em
`benchmarks/qualification/reports/`. A correção tem fundamento normativo específico,
registrado na [ADR-018](adr/ADR-018-historico-sps-110.md); não é redução genérica de
severidade nem declaração editorial de que os artigos não passaram por revisão.

### Causa e correção

Foi obtida a [especificação 1.10 referenciada no módulo nativo](https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit#heading=h.history),
cuja seção de histórico distingue datas obrigatórias de eventos possíveis.
As exigências universais de `rev-request`/`rev-recd` na configuração fixada divergem
dessa distinção. As fontes dos artigos não oferecem essas datas; elas não foram
inventadas nem copiadas do aceite. Ausência de informação não comprova ausência de revisão.

Novo `history_compat.py` ajusta somente os dois flags de presença, no processo
isolado da validação. Não altera a biblioteca instalada nem o XML. Exige perfil
exato e hash/configuração nativa conhecidos; recusa parâmetros novos, severidades
alteradas e instalação duplicada. Executa os checks nativos originais e efetivos;
qualquer diferença fora das duas regras específicas interrompe a execução.
Resultados originais são auditáveis, sem serem confundidos com o resultado efetivo.
Continua verificando datas de revisão informadas, recebimento/aceite, publicação,
tipos de data, histórico duplicado e contexto de tradução.

### Resultado nativo, por ferramenta

| Artigo | Antes, v7 padrão | Agora, parâmetros qualificados |
|---|---|---|
| e20240086 | 2 críticos / 3 erros / 9 avisos | **0 críticos / 3 erros / 9 avisos** |
| e20240135 | 2 críticos / 0 erros / 5 avisos | **0 críticos / 0 erros / 5 avisos** |

Quatro execuções completas na VPS, Packtools e SPSValidator, com as mesmas fontes,
grants válidos e arquivos do v7. Nenhum outro achado mudou, incluindo mensagens e
localizadores; DOI, fascículo, seção e sete ORCIDs continuam confirmados. Não houve
reconversão nesta entrega: XML/ZIP idênticos aos hashes documentados no v7.

- Política `sps-1.10-history-presence-1.0`; fonte/trecho preservados em
  `vh1-history-spec-20261007T114702Z`, na área privada.
- Registro candidato: `config/validator-registry-vh1-history.json`; registro scoped
  e provas v7 anteriores mantidos, sem reescrita. Não é o registro da aplicação ativa.
- Imagem Packtools: `sha256:4d5aadab7d75822c778890e1704e0533d9fc0578aed87034b128f20ec6da2eca`.
- Imagem SPSValidator: `sha256:61b90cc8ecca8de508c6cd19701551860de32f053a4899fd056835c8f05ab048`.
- Plano `vh1-history-20261007T115427Z`, SHA-256
  `0d094d45486eeba66387a0ad2120f17ea339eacfb8459b42df620d269deba1fa`.
  Mesmo nome na área privada de qualificação da VPS; executor do broker, não E2E/socket.
- Treze cenários sintéticos nativos em cada imagem: ausência/presença de revisão,
  precisão de ano, datas obrigatórias ausentes, revisão sem ano, recebimento incompleto,
  tipos inválidos/ausentes, duplicação de histórico e recebimento ausente na tradução.
- 62 testes locais novos: 21 da camada e 41 do gate, incluindo adulteração de
  relatórios, fonte, pacote, imagem, regras e retirada indevida de erros/avisos.
  Formatação do incremento, Ruff global, mypy (108 arquivos) e gates
  histórico/metadados/editorial/scoped/V10/V11 passam. V09 e formatação históricos
  seguem em VH-17; nenhuma alegação de CI global verde.

Regressão final: **1.297 testes aprovados**, zero falhas/erros/skip, cobertura de
linhas **88,69%**, sem mudança de código em `src`. Evidências:
`tmp/vh1-history-final-tests.xml` e `tmp/vh1-history-final-coverage.json`.
Os 62 testes novos estão incluídos no total; as 26 contraprovas Linux são ensaios
adicionais dos validadores. A cobertura não inclui os scripts `ops` e não mede
conformidade SciELO. Nenhuma chamada IA foi necessária neste incremento.

**Próximo passo: VH-06, corrigir os três vínculos de fórmulas do e20240086 com destino
comprovado e sem alterar conteúdo científico.** Depois VH-07 para pacote inteiro e
classificação dos avisos. XPM e IA/UI/operação/E2E permanecem nos IDs existentes.
Revisão humana futura dos enriquecimentos continua requerida. Sem implantação,
ativação IA, aprovação integral dos XMLs ou G-HOMOLOG.

## Checkpoint histórico — vínculo de financiamento comprovado (v7)

Evidência atual: `benchmarks/qualification/reports/vh1-metadata-linux-v7.json`.
Revalidação posterior com política de histórico qualificada está no checkpoint acima;
status e próximos passos desta seção referem-se à data histórica.
Continuação da VH-05; sem nova fase, implantação ou flexibilização dos validadores.

### Correção e fonte

Implementado `verified-funding-catalog-1.0`, integrado ao conversor e worker candidato.
O artigo e20240086 já declara um número de auxílio e vários apoiadores, mas a
proximidade textual não identificava com segurança a agência responsável pelo número.
ArticleMeta divide o nome do ministério em dois registros; essa segmentação não
foi importada. Não foram copiados contratos de outros artigos nem criado um grupo
com todas as agências artificialmente associadas ao mesmo auxílio.

A publicação institucional da [Embrapa, página impressa 75](https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1147178/1/P-Uso-do-jardim-aquicola-no-tratamento-e-reuso-da-agua-de-piscicultura.pdf)
associa explicitamente **Embrapa SEG 21.17.02.001.05.00**. A página única foi
extraída e conferida visualmente com Poppler. O número coincide exatamente com o
já declarado no IDML; somente esse vínculo desambiguado foi estruturado:

- `funding-source`: Brazilian Agricultural Research Corporation, literal do artigo;
- `award-id`: 21.17.02.001.05.00, já presente no artigo;
- declaração integral e nota de divulgação financeira preservadas, incluindo
  banco/ministério e projeto. Sem novos contratos para os demais apoiadores.

A [documentação pública de funding-group](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-funding-group.html)
orienta sua utilização para número de contrato declarado no artigo. A página
consultada se identifica como SPS 1.7; não foi usada para dispensar requisitos da
versão 1.10. A aceitação técnica foi verificada nas imagens 1.10 já fixadas.

### Proteções implementadas

- Regra administrativa qualificada para o par e a declaração exata, não inferência
  genérica de financiamento. Novos pares/textos requerem evidência e curadoria.
- Hash do PDF institucional revisado, URL fixa sem redirects, coleta com orçamento
  de tamanho; catálogo vinculado ao IDML, DOI, perfil e registro de financiamento.
  Nenhum parser de PDF nem requisição de rede executa dentro de `apply`.
- Preenche agência/auxílio somente no estado original `unresolved-funding-structure`.
  Agência/auxílio já decididos, declaração ou proveniência alterada, fonte incorreta,
  outro artigo/perfil e aplicação parcial são recusados. Repetição é idempotente.
- Cada valor combina evidência original do artigo e a evidência institucional.
  Declaração, demais metadados e conteúdo científico não mudam. Outros registros
  de financiamento pendentes, se existentes, conservam sua razão de revisão.
- Autorização por empresa/artigo/destino, hash da fonte/catálogo, validade de sete
  dias e revogação. A origem nova não aceita grant de artigo genérico. Mantém
  `verified_funding_pending_human`; revisão futura do especialista não foi dispensada.
- Não concede alteração autônoma de financiamento à IA/OpenClaw.

### Ensaios e artefatos

| Caso | v6, por ferramenta | v7, por ferramenta |
|---|---|---|
| e20240086 | 4 críticos / 3 erros / 9 avisos | **2 críticos / 3 erros / 9 avisos** |
| e20240135 | 2 críticos / 0 erros / 5 avisos | **Inalterado**, inclusive XML/ZIP |

Quatro execuções nativas pelo executor do broker nas mesmas imagens fixadas.
Eliminadas as duas ocorrências críticas de auxílio não estruturado no primeiro
artigo, sem nenhum achado novo. São duas ocorrências da mesma pendência, não dois
auxílios diferentes; tampouco somar a duplicação entre ferramentas. Autoridades
DOI/ORCID/fascículo/seção continuam positivas. XML inteiro comparado com lista
independente de alterações; conversão/ZIP repetidos, DTD offline válida, sem gold.

- XML e20240086: `e96ce02848de0c7d5dddd4056a36595db27ca3d66c34bebd5feb3bbf46082eb6`;
  ZIP: `2d4d8f6e1c6d0731a2be0f54fc3b5ab703590e126b1b069f0efd5f987722e33a`.
- Catálogo: `1f07771d45d2e452a07e8a658dcc4367c1020b999b99074166137eaba9d49be4`;
  arquivo: `f97f8dc65e68fda109fb303a50ecae5eb810c43360d66ecb5d31dbf593956843`.
- Fonte privada: `vh1-funding-20261006T174304Z/embrapa.pdf`, SHA-256
  `27beb38146ab3755bca3e02f8afb38abfdd3cf28c156fe7fbf475e3e888617be`.
- Plano: `vh1-metadata-20261006T223858Z`, SHA-256
  `58f472b57cd5ba63314fa233912aa3d24190b62e360ba78b0d02e95adc68e174`.
  VPS: `/opt/idml-platform/private/qualification/vh1-metadata-20261006T223858Z`.
- API/worker seguem na imagem `4fcf4766…`, readiness/banco/Redis `ok`; 990 MiB
  disponíveis e 15 GiB em disco após ensaio. Sem bundles na empresa piloto ou
  alterações da aplicação ativa. Temporários de execução removidos automaticamente.

33 testes novos de catálogo/worker e 12 contraprovas adicionais de comparação/gate.
198 testes focados e 62 do gate aprovados; gates metadados/editorial/scoped e
V10/V11 passam, com novas provas imutáveis `v10-operational-workflow-vh1-articlemeta-v4.json`
e `v11-robustness-mutation-vh1-articlemeta-v4.json`. Ruff global, formatação dos
12 arquivos envolvidos e mypy nos 108 arquivos de aplicação aprovados.
**1.235 testes aprovados**, sem falhas/erros/skip; cobertura de linhas **88,69%**.
Evidências: `tmp/vh1-funding-all-tests.xml`, `tmp/vh1-funding-coverage.json` e
`tmp/vh1-funding-focused.xml`. Focados/gate estão incluídos no total, não somados.
Cobertura de código não mede conformidade SciELO e não inclui os scripts `ops`.
V09/formatação históricos permanecem em VH-17; não há alegação de CI global verde.

### Próximo passo finito — histórico/revisões

As duas críticas restantes em **cada artigo** são `rev-request` e `rev-recd`.
Inspeção read-only na imagem Packtools fixada confirmou ambos como `required: true`
em `packtools/sps/validation_rules/history_dates_rules.json`, SHA-256
`a6a62e10d817310f922d8acbe0a99bdabdd8354f6f98e5c306ffa7593a7c4f5d`.
Isso explica a origem do bloqueio, mas não prova a ocorrência dos eventos nem
autoriza rebaixar severidade. Não se alterou configuração, imagem ou histórico.

Próxima entrega VH-05: confrontar exigência configurada com a especificação 1.10
e com evidência editorial aplicável; implementar tratamento rastreável e contraprovas
para informação existente, ausente, conflitante e comprovadamente não aplicável.
Ausência no IDML/PDF/registro não é prova de não aplicabilidade. Não inventar datas
ou usar a data de aceite para preencher revisão. Fechar somente com fonte/regra
comprovadas, preservando erros reais obrigatórios. Depois VH-06 (três vínculos de
fórmulas) e VH-07. XPM, IA/UI/operação/E2E continuam nos IDs existentes.
**VH-05 permanece parcial; XML integral e G-HOMOLOG não aprovados.**

## Checkpoint histórico — estados/províncias com fontes oficiais (v6)

Evidência histórica: `benchmarks/qualification/reports/vh1-metadata-linux-v6.json`.
Sucedida pelo checkpoint v7 acima; os próximos passos desta seção são históricos.

### Implementação e limites

Novo `institution-location-catalog-1.0` integrado ao conversor e worker candidato.
Preenche somente estados ausentes, por atribuição administrativa explícita à
afiliação exata. Exige instituição, departamento, cidade, país/código, DOI,
perfil e hash do IDML; não faz geocodificação, aproximação de nomes ou busca IA.

- Seis páginas oficiais coletadas em 2026-10-06, com URLs fixas, HTTPS sem redirects,
  limite de tamanho e sem execução de scripts. HTML tratado como dado inerte.
- Cada regra fixa o fragmento de endereço por XPath, quantidade de nós e hash do
  texto normalizado. Mudança/ambiguidade exige nova curadoria, não fallback silencioso.
  O catálogo preserva hash da página, fragmento, data de coleta e evidência por campo.
- Campo já preenchido ou explicitamente decidido como ausente não é sobrescrito.
  Instituição, departamento, cidade, país, endereço original e texto científico
  permanecem iguais. Repetição idempotente; aplicação parcial recusada.
- Bundle exige autorização por empresa/artigo/destino, hash do catálogo e conjunto
  de fontes. Todas as fontes devem anteceder a autorização; a mais antiga governa
  o prazo de sete dias. Revogação, fonte errada, fonte futura e vencimento bloqueiam.
- Não é solução universal para instituições: somente cinco regras qualificadas.
  Novas instituições/campi precisam de fonte e regra revisada, não são preenchidos
  automaticamente pela semelhança da cidade. Revisão humana continua requerida.
  Não há nova permissão de edição autônoma para OpenClaw.

### Correspondências e fontes

| Afiliação do artigo | Estado/província | Evidência oficial |
|---|---|---|
| University of Tokyo / General Systems Studies, Tokyo | Tokyo | [Contato do departamento](https://ml.c.u-tokyo.ac.jp/en/contact/) e [governo metropolitano](https://www.english.metro.tokyo.lg.jp/w/000-101-007591) |
| C. Abdul Hakeem College of Engineering & Technology, Melvisharam | Tamil Nadu | [Contato institucional](https://cahcet.in/?page_id=659) |
| Easwari Engineering College, Chennai | Tamil Nadu | [Registro governamental NIRF 2024](https://www.nirfindia.org/Rankings/2024/EngineeringRanking200.html) |
| University College of Engineering Tindivanam, Tindivanam | Tamil Nadu | [Governo distrital](https://viluppuram.nic.in/public-utility/university-college-of-engineering-tindivanam/) |
| Syed Hameedha Arts and Science College, Kilakarai | Tamil Nadu | [Contato institucional](https://www.shartsandscience-edu.in/contact.php) |

No caso japonês, o endereço do departamento está em Komaba/Meguro-ku, Tokyo; o
governo confirma Tokyo como prefeitura metropolitana. **Kanto é região, não a
prefeitura**, e não foi copiada do campo normalizado do ArticleMeta. Nos registros
indianos, divergências históricas de distrito/CEP não autorizam mudar esses campos:
somente Tamil Nadu, concordante com as fontes vinculadas, foi acrescentado.

### Qualificação na VPS

| Caso | v5, por ferramenta | v6, por ferramenta |
|---|---|---|
| e20240086 | 5 críticos / 3 erros / 9 avisos | **4 críticos / 3 erros / 9 avisos** |
| e20240135 | 6 críticos / 0 erros / 5 avisos | **2 críticos / 0 erros / 5 avisos** |

Quatro execuções nativas nas mesmas imagens fixadas Packtools/SPS. Eliminadas
cinco ocorrências de estado ausente por ferramenta, sem nenhum achado novo.
Não somar resultados duplicados entre os validadores. DOI, fascículo, seção e
os sete ORCIDs dos dois artigos mantêm suas verificações positivas.

Conversão/ZIP repetidos e idênticos, DTD offline válida e guarda independente do
XML inteiro: apenas uma inclusão de estado no e20240086 e quatro no e20240135
em relação ao v5. Gold/holdout não foram usados como entrada.

- XML e20240086: `1ece49f296083a67285d0b62cfe23941630a14e4a24c4a1219729e692d93cffd`;
  ZIP: `0f4707385d3f78695ce752af224842173aa46cb553952fea5f717b73b0b03350`.
- XML e20240135: `9ff50bc3ae960c16fea624c71482e8aedd7c616f9e36e2fb1a82fdf5f79b0590`;
  ZIP: `793956107ec688fb529fc83340d1dc3b3da5fe517e13558db7aa781b4e03b1a3`.
- Catálogos: e86 `660d3b56cf7fe785585c46eaf056fbb09a3c715bab6dac7c80a68990b3bd380b`;
  e135 `2685074388bc75b5f6b73516fa13d42c32618ee261c02cc1d83f7feaadc7d37f`.
- Fontes privadas: `vh1-affiliations-20261006T165008Z`; manifesto
  `05cd792703f1f88f071f9052d7196636d66c75e104dd5d8d89f0da75ef6f4574`.
- Plano privado: `vh1-metadata-20261006T170327Z`; SHA-256
  `f47a17f350aecba3793dc0c3afb4b68b0234479c53e9a7e47578f3394cc20376`.
  VPS: `/opt/idml-platform/private/qualification/vh1-metadata-20261006T170327Z`.
- Primeiro disparo bloqueado por permissões de diretório recebidas pelo SCP;
  permissões da pasta específica corrigidas para acesso exclusivo de root e
  ensaio repetido integralmente. Nenhuma verificação de segurança foi desativada.
  Temporários de validação removidos automaticamente; fontes privadas preservadas.
- API/worker continuam na imagem `4fcf4766…`; readiness/banco/Redis `ok` antes/depois.
  Após ensaio: 870 MiB disponíveis e 15 GiB em disco. Sem mudança da aplicação ativa,
  bundles da empresa piloto ou flags IA. Executor do broker em laboratório, não E2E
  implantado nem declaração de aprovação integral.

### Testes e continuação

40 testes novos do catálogo/worker e 11 contraprovas adicionais do gate. Suíte focada
com 165 testes e gate com 50 testes aprovados. V10/V11 reexecutados e vinculados a
`v10-operational-workflow-vh1-articlemeta-v3.json` e
`v11-robustness-mutation-vh1-articlemeta-v3.json`. Gates editorial/scoped/metadados,
Ruff global, formatação dos 12 arquivos envolvidos e mypy nos 107 arquivos passam.
**1.190 testes aprovados**, sem falhas/erros/skip, cobertura de linhas **88,62%**.
Evidências: `tmp/vh1-affiliations-all-tests.xml`,
`tmp/vh1-affiliations-coverage.json` e `tmp/vh1-affiliations-focused.xml`.
Os testes focados/gate estão incluídos no total, não são adicionais. Cobertura de
código não é percentual de conformidade SciELO; scripts `ops` não entram nessa métrica.
Pendências históricas V09/formatação permanecem em VH-17, sem alegar CI global verde.

**Próximo: financiamento e revisões/aplicabilidade, ainda em VH-05.** No e20240086
restam duas ocorrências críticas de agência/auxílio e duas de datas de revisão;
no e20240135, as duas datas de revisão. Essas contagens não representam
necessariamente defeitos únicos. Ausência na fonte não comprova não aplicabilidade:
não inventar datas nem atribuir auxílio por proximidade textual. Depois, fechar os
três vínculos de fórmulas em VH-06 e a revalidação integral em VH-07. XPM/VH-02,
IA/UI/operação/E2E seguem na lista única. G-HOMOLOG permanece não liberado.

## Checkpoint histórico — ORCIDs dos autores confirmados (v5)

Evidência histórica: `benchmarks/qualification/reports/vh1-metadata-linux-v5.json`.
Sucedida pelo checkpoint v6 acima; os próximos passos desta seção são históricos.

### Desenvolvimento e segurança da associação

Implementado `articlemeta-orcid-catalog-1.0` e integrado ao conversor/worker candidato.
O registro oficial ArticleMeta do DOI/PID fornece três associações autor/ORCID em
`article/v10` (`n`, `s`, `k`). Cada uma foi conferida no registro público ORCID.
O nome completo coincide, mesmo quando as duas fontes dividem os sobrenomes
compostos em campos diferentes. Não se alteraram os nomes no XML.

- Exige correspondência exata da lista de autores, IDML, perfil e DOI. Não faz
  pesquisa aproximada, expansão de iniciais, remoção de acentos ou troca de autor.
  Identificadores com checksum inválido, nomes duplicados/ambíguos, fontes trocadas,
  registros privados/incompletos e qualquer ORCID já decidido são recusados.
- Acrescenta somente identificadores ausentes, cada um com duas evidências e hashes
  das fontes. Repetição é idempotente; aplicação parcial ou alvo alterado é recusado.
  Texto científico, datas, nomes, afiliações, CRediT, financiamento e demais elementos
  permanecem iguais ao v4. Uma guarda independente compara o XML inteiro.
- Bundle exige autorização por empresa/artigo/destino e vincula o conjunto das duas
  fontes por hash. A fonte mais antiga governa o prazo de sete dias; fonte futura,
  vencida ou revogada não é aceita. As datas originais de coleta são preservadas.
- XML mantém **`authenticated="false"`**: o registro público confirma consistência
  de nome/identificador, não autenticação OAuth ou controle do identificador pelo
  autor. Revisão humana permanece requerida. Não foi ativada autocorreção IA.

Fontes: [registro editorial ArticleMeta](https://articlemeta.scielo.org/api/v1/article/?collection=scl&code=S1413-41522025000100212),
[mapeamento oficial SciELO/xylose](https://github.com/scieloorg/xylose/blob/master/xylose/scielodocument.py),
[API pública ORCID](https://info.orcid.org/documentation/api-tutorials/api-tutorial-read-data-on-a-record/).
Registros consultados: [0000-0003-1136-7986](https://orcid.org/0000-0003-1136-7986),
[0000-0002-3963-5973](https://orcid.org/0000-0002-3963-5973) e
[0000-0002-0839-9947](https://orcid.org/0000-0002-0839-9947).
Respostas completas ficaram na área privada, não nos relatórios públicos.

### Resultado dos ensaios na VPS

| Caso | v4, por ferramenta | v5, por ferramenta |
|---|---|---|
| e20240086 | 8 críticos / 3 erros / 9 avisos | **5 críticos / 3 erros / 9 avisos** |
| e20240135 | 6 críticos / 0 erros / 5 avisos | **Inalterado**, inclusive XML e ZIP |

Quatro execuções nativas nas mesmas imagens fixadas da VH-04, sem reconstrução
ou mudança de regras: os três ORCIDs novos foram explicitamente aprovados por
cada ferramenta com `public_record_and_name_match`. Os quatro do segundo artigo
mantêm sua confirmação anterior. DOI/fascículo/seção continuam positivos.
Nenhum achado novo comparado ao v4 ou à base original; eliminados três críticos
de ORCID. Não somar resultados duplicados entre os dois validadores.

- Conversão/ZIP repetidos e idênticos; DTD offline válida; gold/holdout não lidos.
  Guarda rejeita identificadores trocados, autenticação falsa, mudança de nome,
  alteração científica e correção parcial.
- XML e20240086: `fac9f6018483f5207b41d8c98d5bcb71e2e391bd6389fc976c4d6f33515ede26`;
  ZIP: `97eef1ab0e66b2b54ecd6ee80d2343838ff84e2cc7549745f774859b0fec6853`.
- Catálogo: `c3da55a773e7309c6e3331978ec07875be450d1505eb612aa45fb9844d05f8b5`;
  conjunto de evidências: `e8b2f879e9bc0a56dfc70b99b1ac20ed9b2bc4cebd155d398acbfc03e9e4d788`.
  ORCID coletado em 2026-10-06; ArticleMeta original de 2026-10-05 preservado.
- Plano privado: `vh1-metadata-20261006T121652Z`, SHA-256
  `50b8dda4ec2cc9e37f29b2df499168887240dad57e3b65019e34acc59024dcf6`.
  VPS: `/opt/idml-platform/private/qualification/vh1-metadata-20261006T121652Z`.
- API/worker na imagem `4fcf4766…`, readiness/banco/Redis `ok` antes e depois;
  845 MiB de memória disponível e 15 GiB em disco após ensaio. Aplicação ativa
  preservada. Ensaios pelo executor do broker com IDs sintéticos de laboratório,
  não pelo fluxo E2E implantado. Nenhum bundle instalado na empresa piloto.

### Verificação e próximo item

**1.139 testes aprovados**, sem falhas/erros/skip; cobertura **88,52%** das linhas
de aplicação, não da conformidade SciELO nem dos scripts `ops`. Artefatos:
`tmp/vh1-orcids-all-tests.xml`, `tmp/vh1-orcids-coverage.json` e
`tmp/vh1-orcids-focused.xml`. Os focados e testes do gate abaixo estão incluídos
no total, não são adicionais.

250 testes focados e 39 testes do gate aprovados, com 41 testes novos do catálogo
e contraprovas da comparação independente. Gates editorial/scoped/metadados,
V10 e V11 passam; estes dois reexecutados e vinculados a provas imutáveis
`v10-operational-workflow-vh1-articlemeta-v2.json` e
`v11-robustness-mutation-vh1-articlemeta-v2.json`. Ruff global, formatação dos
12 arquivos envolvidos e mypy nos 106 arquivos de aplicação aprovados.
As pendências históricas V09/formatação continuam registradas em VH-17.

**Próximo trabalho: estados/províncias das afiliações, ainda em VH-05**, com fonte
autoritativa e correspondência à instituição/endereço do artigo. Não usar região
geográfica como província por conveniência. Restam cinco críticos no e20240086:
um estado, dois de financiamento e dois de revisão; no e20240135, quatro estados
e duas revisões. Financiamento precisa de vínculo agência/auxílio; ausência de
datas de revisão não equivale a evento não aplicável. Depois VH-06 (três vínculos
de fórmulas) e VH-07. XPM/IA/UI/operação/E2E continuam nos IDs existentes.
**VH-05 parcial; XML integral e G-HOMOLOG ainda não aprovados.**

## Histórico — datas confirmadas no ArticleMeta (v4)

Evidência deste checkpoint: `benchmarks/qualification/reports/vh1-metadata-linux-v4.json`.
Os checkpoints v3/v2 abaixo são históricos, inclusive seus próximos passos.

### Fonte e correção entregues

O registro oficial do SciELO ArticleMeta foi obtido e preservado em área privada.
O PID `S1413-41522025000100212`, DOI e coleção foram conferidos no envelope e
nos campos internos do registro. A data do artigo é `v223`, não o ano do fascículo
em `v65` nem a data de processamento. Recebimento/aceite são `v112`/`v114`.

| Campo do e20240086 | Antes | Fonte oficial e candidata atual |
|---|---|---|
| Publicação online | Somente 2025 | 2025-07-07 |
| Recebimento | 2024-06-09 | 2024-09-06 |
| Aceite | 2025-09-03 | 2025-03-09 |

As duas datas impressas no IDML eram ambíguas. **A inversão dia/mês foi confirmada
pela fonte para este artigo**, não inferida para silenciar o validador. A regra
genérica de interpretação dos outros IDMLs não foi invertida. O catálogo permite
somente confirmação ou desambiguação literal dia/mês do mesmo ano, recusa mudanças
arbitrárias e não substitui uma decisão humana por essa interpretação.

Implementado `articlemeta-date-catalog-1.0`: vínculo a IDML/perfil/DOI, snapshot
com hash e coleta original, cronologia coerente, aplicação idempotente e revisão
humana ainda requerida. O worker candidato aceita o catálogo por bundle autorizado
para empresa/artigo/destino; fontes expiradas, revogadas ou com hash/data de coleta
divergente são recusadas. Validade máxima da fonte mutável: sete dias, sem renovação
artificial ao copiar. Nenhuma consulta de rede ocorre dentro do conversor.

A origem das evidências anteriores é preservada; novas evidências identificam os
campos ArticleMeta. A guarda de comparação do XML completo permite somente estas
datas além das correções já qualificadas em v3. Corpo científico, autores, fórmulas,
referências e financiamento não foram reescritos. Não se leu gold/holdout como
entrada. Esse é enriquecimento administrativo verificável, não autocorreção IA.

Fontes primárias: [registro ArticleMeta do artigo](https://articlemeta.scielo.org/api/v1/article/?collection=scl&code=S1413-41522025000100212)
e [mapeamento SciELO/xylose](https://github.com/scieloorg/xylose/blob/master/xylose/scielodocument.py).
O mapeamento explica os campos, não é uma dispensa normativa de regras SPS.

### Resultado nativo e limites

Conversão/pacote repetidos com resultado idêntico, DTD offline válida. Quatro
execuções nativas na VPS, em 2026-10-06, nas duas imagens fixadas da VH-04:

| Caso | v3, por ferramenta | v4, por ferramenta |
|---|---|---|
| e20240086 | 13 críticos / 3 erros / 9 avisos | **8 críticos / 3 erros / 9 avisos** |
| e20240135 | 6 críticos / 0 erros / 5 avisos | **Inalterado**, inclusive hashes de XML/ZIP |

Eliminados cinco críticos: formato/dia/mês da publicação, valor de aceite e
publicação ausente no histórico. Nenhum achado novo frente a v3 ou à base original;
nenhuma regra rebaixada/dispensada. DOI/fascículo/seção positivos nos quatro ensaios,
e os quatro ORCIDs já existentes do e20240135 continuam positivos por ferramenta.
As execuções usam o executor do broker, não o fluxo E2E da aplicação ativa.

- e20240086 XML: `ff86dc3d503839ecad91a0005cdca0879ee6fae23e83591622ef2e621ed512c7`;
  ZIP: `4c5c4fa9bcededcbce5e064d8164efd3f6f583aea7a38ed66d2853c134d328fc`.
- Snapshot coletado em 2026-10-05, SHA-256
  `2a752569032271a8565e3cb9885f150970e6e73f99b7367768c3a98621c679ed`.
  Catálogo: `f57533610786b92c9df93046c6fec7601b367d5dcf29499db4e42fbe65b2f154`.
- Plano privado `vh1-metadata-20261005T182024Z`, SHA-256
  `253c02b4427df9f6bd641bfa3f696d1ff6be3473ed5bd425d0986253d6ea3562`;
  VPS `/opt/idml-platform/private/qualification/vh1-metadata-20261005T182024Z`.
  Relatórios anteriores preservados; catálogo privado novo, sem alterar os históricos.
- API/worker mantidos na imagem `4fcf4766…`; pós-teste banco/Redis/readiness `ok`,
  835 MiB de memória disponível e 15 GiB livres em disco. Sem reinício, implantação,
  mudanças de flags IA ou instalação de bundle na empresa piloto.

### Verificações e fila restante

- **1.088 testes aprovados**, sem falhas/erros/skip; cobertura **88,41%** das linhas
  de aplicação, não da conformidade SciELO ou dos scripts `ops`. Os focados e os
  testes do gate abaixo estão incluídos nesse total. Artefatos locais:
  `tmp/vh1-articlemeta-all-tests.xml`, `tmp/vh1-articlemeta-coverage.json` e
  `tmp/vh1-articlemeta-focused.xml`.
- 169 testes focados e 29 testes do gate aprovados, incluindo 36 de ArticleMeta e
  contraprovas de datas, fonte, escopo, expiração/revogação e alterações fora da lista.
  Os testes do gate comparam datas esperadas independentemente do catálogo e
  recusam revisão inventada, mudança científica/autoral e evidência adulterada.
- Gate de metadados, gates editoriais/scoped e V10/V11 aprovados. V10/V11 foram
  reexecutados com nova prova imutável `v10-operational-workflow-vh1-articlemeta-v1.json`
  e `v11-robustness-mutation-vh1-articlemeta-v1.json`, não só troca de hashes.
- Ruff global e mypy nos 105 arquivos de aplicação passam. A formatação do
  incremento passa. V09 ainda recusa o relatório histórico por `settings.py`
  desatualizado; seus cinco checks dinâmicos passam. Dois scripts históricos ainda
  precisam de formatação/requalificação. Ambos permanecem em VH-17; CI global
  não está integralmente aprovado.

**Próxima implementação: continuar VH-05 com os ORCIDs ausentes do e20240086.**
O ArticleMeta fornece identificadores associados aos autores; falta qualificar
essa associação e os registros públicos ORCID no catálogo e nos validadores.
Não basta encontrar um nome semelhante ou inserir o identificador no XML.

Restam no primeiro artigo: um crítico de estado de afiliação, três de ORCID,
dois de financiamento e dois de datas de revisão; os três erros são vínculos de
fórmulas (VH-06). No segundo: quatro estados e duas datas de revisão. A região
`Kanto` no registro normalizado não comprova por si só a província da afiliação;
não foi copiada. A ausência de `v116` não prova que não houve revisão. O número
de financiamento disponível não pode ser atribuído a várias agências por suposição.

Fechar fontes/aplicabilidade dos metadados em VH-05, vínculos em VH-06 e revalidação
integral em VH-07. XPM, IA, UI, implantação e E2E permanecem nos IDs existentes.
**Este incremento não encerra VH-05, não aprova o XML integral e não libera testes
de homologação.**

## Histórico — datas e financiamento (v3)

Substitui o status v2 abaixo, mantido como histórico. Evidência atual:
`benchmarks/qualification/reports/vh1-metadata-linux-v3.json`.

### Desenvolvimento entregue

- O importador Crossref deixava apenas o ano mesmo quando o registro continha
  mês/dia. Agora conserva `AAAA`, `AAAA-MM` ou `AAAA-MM-DD`, valida o calendário
  e exige compatibilidade entre `published`, `published-online` e `issued`.
  Datas distintas não são resolvidas por preferência silenciosa. Datas de
  criação/depósito não substituem publicação; nenhuma parte faltante é inventada.
- O builder emite mês/ano conhecidos sem fabricar dia. Catálogo pode refinar uma
  data compatível, mas não reduzir sua precisão nem sobrescrever conflito.
  A data fornecida por referência formal aponta para o hash dessa referência;
  volume/licença continuam apontando para Crossref. Não atribuir ao Crossref
  precisão que veio de outra fonte. Catálogos privados históricos não foram editados.
- Removida a regra que tomava tudo antes da primeira vírgula como agência.
  O parser suporta pares explícitos como `Foundation Alpha, grant 123.` e
  `Funder: Ministry of Science, Technology and Research; Award: AB-123`.
  O nome completo e o auxílio ficam ligados à mesma evidência. Essa gramática é
  intencionalmente limitada: múltiplos financiadores/auxílios em prosa livre
  precisam de fonte estruturada verificável, não segmentação por vírgulas.
- Declaração ambígua conserva seu texto integral, evidência e nota de divulgação;
  o campo agência fica `needs_review` e a razão
  `funding_structure_requires_authority` acompanha o canônico. Não equivale a
  declaração de ausência de financiamento. `Funding: None.` continua distinto.

Código: `publication_dates.py`, `release/formal_metadata.py`,
`pipeline/funding_parser.py`, mapper e builder. Sem mudança no esquema canônico
1.4.0; o catálogo 1.0 aceita adicionalmente mês/ano, preservando catálogos válidos
anteriores. Não é automação IA de dados sensíveis.

### Resultado real e limite do avanço

Os dois IDMLs foram convertidos duas vezes, com pacotes idênticos entre repetições,
DTD offline válida e comparação integral contra a base. Sem gold/holdout como
entrada. A única mudança adicional no XML do e20240086 é a retirada do
`award-group` incompleto criado pela antiga regra de primeira vírgula. Declaração,
datas, corpo, autores, figuras, fórmulas e referências ficam intactos. O segundo
artigo mantém exatamente XML e ZIP anteriores. A comparação rejeita alterações
no texto de financiamento, corpo ou inserção de auxílio não comprovado.

| Caso | v2, por ferramenta | v3, por ferramenta |
|---|---|---|
| e20240086 | 14 críticos / 3 erros / 9 avisos | 13 críticos / 3 erros / 9 avisos |
| e20240135 | 6 críticos / 0 erros / 5 avisos | Inalterado |

**A redução de um crítico NÃO significa financiamento corrigido ou aprovado.**
Saiu um grupo incompleto; os dois achados de auxílio ainda não estruturado e a
pendência explícita de revisão continuam. Os números não podem ser usados como
único critério de qualidade. Não houve rebaixamento de regra ou waiver.

Quatro execuções nativas nas imagens fixadas da VH-04, pelo executor do broker,
não pelo socket/aplicação ativa. Nenhum achado novo em relação a v2 nem à base
original; o gate verifica ambos, além de exigir a pendência de financiamento.
DOI/fascículo/seção continuam positivos nos quatro ensaios; quatro ORCIDs presentes
do e20240135 positivos por ferramenta. Ausência de ORCID no outro caso não é aprovação.

- e20240086 XML: `d4b9e2e78342e11475acde63a5268c490209dc95288ff2e9fd0f19c6f4e53980`;
  ZIP: `b675b1123e9ea9e130b1269ed2f681ae7bf780c2a96bacbe43abdf5886461b26`.
- Plano privado: `vh1-metadata-20261005T175855Z`, SHA-256
  `23ac3a353edfbcd5b4a11fda2632db197eb586b4cec0b3160b698a23dbba7679`.
  VPS: `/opt/idml-platform/private/qualification/vh1-metadata-20261005T175855Z`.
- Fontes continuam com as datas de coleta originais, sem renovação artificial.
  API/worker continuam na imagem `4fcf4766…`; banco/Redis/readiness `ok` após ensaio.
  Nenhum reinício da aplicação, mudança de flags IA ou implantação.

### Triagem das fontes — não copiar inconsistências

O snapshot Crossref autorizado do e20240086 contém somente ano em todas as datas
de publicação. Portanto a correção de precisão não cria dia/mês para esse artigo.
O mesmo registro separa em dois financiadores as partes do nome de um ministério;
a declaração literal preservada no IDML/PDF não justifica essa segmentação. Não
copiar essa lista automaticamente nem distribuir um único identificador entre
todos os financiadores. Publicações institucionais de outros trabalhos citam o
mesmo projeto/auxílio, mas não são confirmação suficiente de cada vínculo deste
artigo. A consulta do portal SciELO foi intermitente e não produziu snapshot
de data de publicação apto a entrar no catálogo nesta execução.

Fontes consultadas: [artigo no SciELO](https://doi.org/10.1590/S1413-415220240086),
[Crossref do DOI](https://api.crossref.org/works/10.1590/S1413-415220240086),
[JATS4R — financiamento](https://jats4r.niso.org/funding/) e
[SciELO — award-group](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-award-group.html).
Esta última página se identifica como SPS 1.7; não fundamenta dispensa SPS 1.10.

### Verificação e sequência restante

- **1.042 testes aprovados**, sem falhas/erros/skip; cobertura **88,32%** das linhas
  de aplicação, não de `ops` nem de conformidade SciELO. 111 testes focados
  incluídos no total; 54 novos testes de datas/financiamento e 19 testes do gate.
  Artefatos: `tmp/vh1-dates-funding-all-tests.xml`,
  `tmp/vh1-dates-funding-coverage.json`, `tmp/vh1-dates-funding-focused.xml`.
  Gate de metadados repetido após reforçar a comparação com a versão imediatamente anterior.
- Ruff global e mypy nos 104 arquivos de aplicação aprovados. Formatação dos
  arquivos deste incremento aprovada; permanecem os dois scripts históricos já
  registrados em VH-17. V10 e V11 passam, este com evidência nova imutável
  `v11-robustness-mutation-vh1-metadata-v3.json` e reexecução de fuzz/propriedades.
- Checagem ampliada 7C-08: 17 de 18 gates sintéticos passaram. **V09 recusou o
  relatório antigo por hash desatualizado de `settings.py`**, não alterado neste
  incremento. Os cinco checks dinâmicos de V09 passaram. Não renovar o hash sem
  requalificação; pendência de evidência registrada em VH-17. CI global ainda não
  deve ser anunciado como totalmente aprovado.

Próximo trabalho permanece **VH-05**: obter/provisionar evidência editorial
consistente para publicação completa, convenção do histórico, revisões e vínculos
de financiamento; resolver estados/ORCID ausentes por fontes vinculadas. Preservar
as pendências de dados quando a fonte não as resolver. Depois VH-06 (três vínculos
de fórmulas) e VH-07. VH-02/XPM, IA, UI, implantação e E2E permanecem nos IDs
existentes; esta entrega não encerra VH-05 nem libera G-HOMOLOG.

## Histórico — checkpoint v2

## Correções implementadas e mantidas

1. Duas afiliações do e20240086 trazem literalmente `São Carlos (SP), Brazil`.
   O mapper deixava a UF dentro do campo cidade e não preenchia estado. Agora
   separa cidade/UF apenas na notação explícita `Cidade (UF), Brazil/Brasil`, com
   UF válida. Mantém texto original e os mesmos IDs de evidência. Não consulta
   geolocalização, não infere estado pela instituição/cidade e não trata uma sigla
   ambígua como confirmação. Demais afiliações permanecem intactas.
2. Três papéis já atribuídos na fonte não recebiam URI CRediT por variantes de
   travessão/espaçamento e `and` versus `&`. O builder reconhece somente as
   variantes enumeradas de `Writing – original draft` e `Writing – review & editing`.
   Emite rótulo/URI canônicos; conserva o papel literal no modelo e a declaração
   original. Não muda autor, não acrescenta papel e não classifica termos desconhecidos,
   combinações ou qualificadores como se fossem equivalentes.

Código: `pipeline/metadata_normalization.py`, `canonical_mapper.py`, `jats_builder.py`.
É correção determinística de representação, não implantação do ciclo IA VH-08–10.

## Comparativo independente e execução real

`ops/qualify_vh1_metadata.py` reprocessou os dois IDMLs, usando os mesmos catálogos,
PDF/imagens autorizados e perfil 1.1. Não leu gold XML nem holdout. Catálogos
históricos conservam a proveniência e limitações anteriores; não foram declarados
novas fontes independentes. Conversão/pacote repetidos e idênticos, validação
offline aprovada. Guarda compara o XML inteiro contra a base e permite **somente**
duas separações cidade/estado e três normalizações de papel no primeiro artigo.
No segundo, XML e ZIP permanecem idênticos. Ciência, fórmulas, autores, datas,
financiamento, demais elementos e arquivos preservados.

Prova histórica deste checkpoint: `benchmarks/qualification/reports/vh1-metadata-linux-v2.json`.
Imagens imutáveis e bibliotecas da VH-04 preservadas, sem reconstrução de imagem.
Quatro execuções reais através do executor do broker com seleção/grant vinculados;
este ensaio não usa o socket nem é E2E da aplicação implantada. A qualificação
anterior do socket permanece específica ao seu escopo; não foi substituída.

| Caso | Antes, por ferramenta | Depois, por ferramenta |
|---|---|---|
| e20240086 | 22 críticos / 4 erros / 9 avisos | **14 críticos / 3 erros / 9 avisos** |
| e20240135 | 6 críticos / 0 erros / 5 avisos | **6 críticos / 0 erros / 5 avisos**, sem alteração |

No primeiro artigo desapareceram dois achados de estado, seis achados de termo/URI
CRediT e um de consistência de papéis. Nenhuma regra foi rebaixada/dispensada.
O gate compara código e quantidade de **todos** os achados antes/depois e recusa
qualquer achado novo, mesmo que a contagem total diminua. Não somar os achados
repetidos entre as duas ferramentas como defeitos distintos.

DOI/fascículo/seção continuam explicitamente positivos nas quatro execuções.
Quatro ORCIDs presentes do e20240135 positivos por ferramenta; a ausência de ORCID
no e20240086 continua pendente, não equivale a validação bem-sucedida de identidade.

Hashes finais e escopo:

- e20240086 XML: `38d64ffc016045937001883f37ca3009917b896245657dbd0d711ab81b603eb6`;
  ZIP: `31d49f07499e5ae1d09de949199d654618c209ee119ff62e695a31f406874c5c`.
- e20240135 mantém XML `1757cdb3a15b7fd44beb009e794ff812995eb59cd6e2c1eee2cabee15f9a9706`
  e ZIP `e0be244b52eb524328a3f260c426617850bb057e3bbc9ecb82c43134929950c8`.
- Plano privado: `vh1-metadata-20261005T123120Z`, SHA-256
  `97608790dff7b0180007674e68727084709d202684f61acac39e1490bd699003`.
  Área VPS: `/opt/idml-platform/private/qualification/vh1-metadata-20261005T123120Z`.
  Relatórios anteriores não sobrescritos; fontes de autoridade rebinding por hash,
  sem modificar dados nem renovar a data original de coleta.

Grants com empresa/artigo sintéticos, exclusivos do laboratório, sob a autorização
já registrada. Não são grants de produção. Scratch/grants temporários removidos
ao terminar; fontes e provas privadas preservadas. Aplicação/serviços existentes
não reiniciados; API/worker na imagem `4fcf4766…`, banco/Redis e readiness saudáveis.

## Experimento rejeitado: publicação somente com ano no histórico

A primeira tentativa adicionou `history/date[@date-type='pub']/year` com o ano
já conhecido, sem inventar dia/mês. Passou no teste offline, mas nos dois runtimes
nativos produziu um achado adicional de formato e outro de ordenação. Remover uma
ausência não compensava introduzir outros problemas. **Essa alteração foi retirada
do código e da candidata final**; o ano conhecido permanece somente onde já estava.

`vh1-metadata-linux-v1.json` preserva o ensaio rejeitado, com 15 críticos/3 erros no
primeiro artigo; não é prova de aceite atual. O gate novo possui contraprova que
rejeita esse relatório. A candidata final v2 tem 14 críticos/3 erros e nenhum achado
novo. Dia/mês, datas de revisão e qualquer alteração na data de aceite continuam
proibidos sem fonte e análise da regra. Nenhuma severidade foi reduzida.

## Pendências classificadas — permanecem nos IDs existentes

| Pendência | Evidência/causa atual | Continuidade |
|---|---|---|
| Estados ausentes: um no e20240086 e quatro no e20240135 | Não há UF/estado explícito nas respectivas afiliações do IDML | VH-05: fonte institucional/autoritativa vinculada ou aplicabilidade documentada; não completar por semelhança |
| Publicação completa/histórico/cronologia do e20240086 | Autoridade atual só informa ano; regra exige precisão maior e há achado de valor/cronologia de aceite a investigar | VH-05: obter fonte de publicação com precisão adequada e reproduzir a regra fixada; não inverter datas para silenciar o resultado |
| `rev-request` / `rev-recd` nos dois artigos | Ausentes na candidata; o runtime configurado os exige | VH-05: verificar fonte e aplicabilidade SPS 1.10/ESA; ausência não prova que o evento não ocorreu |
| ORCID de três autores do e20240086 | Não há identificador na candidata | VH-05: somente associação verificável com autor/obra, nunca busca aproximada por nome |
| Financiamento do e20240086 | Declaração literal preserva várias organizações, projeto e identificador; estrutura atual captura só a primeira agência e não vincula o auxílio | VH-05: definir decomposição/vínculo com evidência e contraprovas; não atribuir o mesmo auxílio a todos por inferência |
| Três vínculos de fórmulas do e20240086 | Erros de referência a objetos, sem alteração neste incremento | VH-06 |
| Avisos de referências/seções/apêndice/orgdiv2 | Não desapareceram nem foram dispensados | VH-05/06/07: classificar na validação final |
| XPM, operação, IA, UI e E2E | Fora da alteração de parser/builder deste checkpoint | VH-02 e demais itens já existentes da lista única |

O próximo desenvolvimento permanece **VH-05**, começando pela precisão de datas
e pela estrutura de financiamento. Não marcar VH-05/07 concluídos nem tratar
dados não encontrados como “não aplicáveis” sem demonstração.

## Testes e evidências de regressão

- Suíte integral: **981 testes aprovados**, três avisos, cobertura **88,13%** das
  linhas de `src/idml_foundation`. Não mede conformidade SciELO nem inclui `ops`.
  Os 73 focados e os 12 testes do gate estão incluídos no total, não são adicionais.
  Artefatos: `tmp/vh1-metadata-all-tests.xml`, `tmp/vh1-metadata-coverage.json` e
  `tmp/vh1-metadata-focused.xml`.
- 73 testes focados aprovados, incluindo nove de robustez V11. Casos negativos:
  UF ausente/desconhecida/ambígua/país errado, papéis desconhecidos/qualificados,
  precisão de data sem invenção, XML com mudança fora da lista permitida.
- V11 requalificado após a alteração de mapper/builder: novo relatório
  `v11-robustness-mutation-vh1-metadata-v2.json`; o v1 desse incremento corresponde
  ao experimento anterior e não é a referência ativa. V10 continua aprovado.
- Gate `python -m ops.gate_vh1_metadata`, incluído no CI, vincula o aceite deste
  incremento à fonte, imagens, hashes dos candidatos, evidências e ausência de
  novos achados. Testa também relatório antigo, adulteração e evidência incompleta.
- Ruff/formatação dos dez arquivos envolvidos e tipagem dos três módulos de
  aplicação aprovados. Pendência antiga de formatação global registrada em VH-17
  não foi alterada neste incremento.

## Fontes conferidas em 2026-10-05 e limites normativos

- [IBGE — UFs](https://servicodados.ibge.gov.br/api/v1/localidades/estados): apenas
  lista de siglas válidas, não fonte para inferir estado de uma cidade/instituição.
- NISO CRediT: [Writing – original draft](https://credit.niso.org/contributor-roles/writing-original-draft/)
  e [Writing – review & editing](https://credit.niso.org/contributor-roles/writing-review-editing/),
  para a representação dos papéis que já estavam atribuídos na fonte.
- Documentação SciELO de [afiliação](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-aff.html),
  [histórico](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-history.html)
  e [datas](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-date.html).
  As páginas servidas identificam-se como versão 1.7; **não são comprovação de
  dispensa de exigência SPS 1.10**. A referência Google Docs citada pelo código
  de histórico não pôde ser lida pela ferramenta de consulta nesta execução.
  Não se concluiu daí que inexiste especificação atual ou que a regra seja falsa.
