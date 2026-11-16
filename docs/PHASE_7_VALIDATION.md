# Fase 7 — Homologação automatizada e piloto simulado

Data inicial: 2026-09-04. Estado: **EM EXECUÇÃO — 7C-08 APROVADA; V-12 EM ANDAMENTO**.

Prioridade revisada em 2026-09-25: H0–H4/G-HOMOLOG para avaliação funcional antecipada pelo
especialista, conforme `EXPERT_TEST_READINESS_PLAN.md` e ADR-015. V-12 a V-15 permanecem
obrigatórios para produção, não integralmente para a primeira avaliação restrita.

## Estado das famílias V-01 a V-11

| Família | Estado | Evidência atual |
|---|---|---|
| V-01 Proveniência e integridade | PASSOU | catálogo e gate reproduzível |
| V-02 Segurança da ingestão | PASSOU | matriz negativa, regressão e VPS |
| V-03 Leitura e fidelidade IDML | PASSOU | conservação textual, estrutura e VPS |
| V-04 Canonical Article Model | PASSOU | schemas, invariantes, migrations e round-trip |
| V-05 Construção XML JATS/SPS | PASSOU | builder determinístico, DTD, SPS e referências |
| V-06 Validadores formais | PASSOU COM RESTRIÇÃO | 4 contêineres qualificados; XPM SPS 1.10 aguarda worker Windows |
| V-07 Fidelidade comparativa | PASSOU NO CORPUS ATUAL | dois artigos requalificados, zero bloqueio semântico; sem garantia universal |
| V-08 OpenClaw assistivo | PASSOU | seis domínios, evidência viva, matriz adversarial e contratos fail-closed |
| V-09 Segurança e multiempresa | PASSOU | identidade, RBAC, isolamento, entradas hostis e segredos |
| V-10 Fluxo ponta a ponta | PASSOU | fluxo operacional, idempotência, recuperação, UI e VPS |
| V-11 Robustez e mutações | PASSOU | fuzz determinístico, propriedades, metamorfismos, mutações e VPS |

## V-01 — Proveniência e integridade do corpus

O gate `ops/gate_phase7_v01.py` consolida os seis manifestos e falha fechado em caso de:

- ID de corpus ou caminho lógico duplicado;
- mesmo SHA-256 reutilizado entre corpus ou splits;
- classificação de artefato mais fraca que a do corpus;
- redistribuição ou exclusão insegura de conteúdo restrito;
- arquivo restrito idêntico presente no conjunto versionável;
- nome, ID ou hash do holdout presente em prompts, testes ou material de benchmark executável;
- caminho de source root inseguro;
- arquivo privado ausente, truncado, substituído, em symlink ou com hash divergente.

A execução local verificou 21/21 artefatos nos roots privados autorizados sem emitir conteúdo. O
catálogo contém seis manifestos, um holdout e zero duplicata, contaminação entre splits ou falha de
classificação. A varredura local calculou hash de 404 arquivos versionados/versionáveis e inspecionou
88 arquivos textuais de execução; nenhum binário restrito ou token do holdout foi encontrado.

O fingerprint canônico do catálogo é
`6869ea39c818a9036f8f949a79a616f8f407195464b18bdfcd98e3b11e21207d`. A mesma verificação de
metadados foi reproduzida na VPS em container read-only e sem rede, com fingerprint idêntico. A CI
executará o gate a cada mudança. Os binários privados não foram copiados para a VPS nem para a CI.

A suíte completa terminou com 199 testes, cobertura de 84,89%, Ruff e mypy strict aprovados. O
relatório sanitizado está em
`benchmarks/qualification/reports/v01-corpus-integrity-v1.json`.

Antes do deploy, o backup `/opt/idml-platform/backups/20260904T200455Z` passou no restore isolado.
A imagem `idml-foundation:phase7-v01-corpus-integrity-v1`
(`sha256:9a3c733134a52cfcd82bf8796c8915e53f179235286505008ab681e0af82471d`)
foi implantada com API, worker e OpenClaw saudáveis. As flags OpenClaw/Swarm permanecem falsas.

## V-02 — Segurança da ingestão IDML

A ingestão passou a validar o ZIP inteiro antes do parser e a falhar fechado para caminhos absolutos
ou ambíguos, travessia, colisões Unicode/casefold, arquivos e diretórios sobrepostos, symlinks,
entradas especiais ou criptografadas, arquivos executáveis e archives aninhados. Limites explícitos
protegem quantidade de entradas, tamanho total expandido, compressão, profundidade e comprimento de
caminho; CRC e mimetype também são conferidos antes da leitura do XML.

O parser XML bloqueia DTD, entidades, resolução externa, documentos malformados e XML individual
acima de 32 MiB. IDML incompleto não falha silenciosamente: referências ausentes no `StoryList`,
frames ligados a stories inexistentes, links de thread quebrados e stories sem frame são
classificados em `reading_order_issues` com evidência quando disponível.

Cancelamento e excesso de tamanho interrompem o upload antes da persistência. Falhas no movimento
atômico removem temporários. O protocolo ClamAV foi testado para resposta limpa, malware, timeout e
resposta indeterminada; indisponibilidade resulta em 503 sanitizado. O ClamAV permanece desligado na
VPS de desenvolvimento e sua ativação operacional será tratada no gate de segurança de produção.

O gate `ops/gate_phase7_v02.py` aprovou 26/26 casos sintéticos e 6/6 IDML reais autorizados sem
emitir conteúdo restrito. A VPS reproduziu os 26 casos em container read-only, sem rede e sem receber
o corpus privado. A suíte integral aprovou 226 testes com 85,29% de cobertura; Ruff e mypy strict
passaram. O relatório sanitizado está em
`benchmarks/qualification/reports/v02-ingestion-security-v1.json`.

Antes do deploy, o backup `/opt/idml-platform/backups/20260908T125309Z` passou no restore isolado
com 21 tabelas públicas, 1 artefato e 14 arquivos do estado OpenClaw. A imagem
`idml-foundation:phase7-v02-ingest-security-v1`
(`sha256:8807135f2d0df6f98a9fe83177ae6cced08c25b7e4ddd4641bf67f08bd59ec15`) deixou API, worker e
OpenClaw saudáveis. As flags OpenClaw, swarm e ClamAV permanecem falsas.

## V-03 — Leitura e fidelidade do IDML

O parser passou a seguir a sequência de spreads declarada no `designmap.xml` e a determinar página
e coluna pela geometria transformada dos pages e frames. A chave de leitura combina página, coluna,
posição vertical/horizontal, thread e `StoryList`, mantendo classificação explícita para referências
incompletas. O modelo Raw preserva as propriedades diretas de parágrafo e caractere, inclusive
negrito, itálico, combinações, sobrescrito e subscrito.

Conteúdo de `Footnote`/`Note`, inclusive texto após processing instructions ACE, agora é separado do
corpo sem duplicação e emitido como `fn-group`. Hyperlinks são associados a todos os runs abrangidos,
inclusive quando o `HyperlinkTextSource` envolve os ranges. O Raw conserva a URL original; na
normalização canônica somente `http`, `https` e `mailto` bem formados viram `ext-link`. Outros
esquemas permanecem auditáveis como texto e geram motivo de revisão. `Bold Italic` vira elementos
JATS aninhados e os valores exatos `BulletList`/`NumberedList` viram listas. Parágrafos e células
vazios permanecem no Raw; a ausência de conteúdo semântico não produz elemento JATS vazio.

O gate `ops/gate_phase7_v03.py` aprovou 10 verificações sintéticas e os seis IDMLs autorizados. A
reconstituição independente do fluxo textual foi exata em 209/209 stories, sem `SequenceMatcher`,
sem chamadas de rede e sem emitir conteúdo restrito. Foram conferidas também páginas, tabelas,
spans, células vazias, notas e cobertura de hyperlinks. A suíte integral aprovou 229 testes, com
85,68% de cobertura, Ruff e mypy strict aprovados. O relatório sanitizado está em
`benchmarks/qualification/reports/v03-idml-fidelity-v1.json`.

Antes do deploy, o backup `/opt/idml-platform/backups/20260908T143455Z` passou no restore isolado
com 21 tabelas públicas, 1 artefato e 14 arquivos do estado OpenClaw. O gate sintético foi
reproduzido na VPS em container read-only e sem rede. A imagem
`idml-foundation:phase7-v03-idml-fidelity-v1`
(`sha256:e614f5dde04a286a896cf837c411df277b497f25533a57c3f265d170e51802b6`)
deixou API, worker e OpenClaw saudáveis. As flags OpenClaw, swarm e ClamAV permanecem falsas.

## V-04 — Canonical Article Model

Os contratos evoluíram para Raw Article 1.3.0 e Canonical Article 1.2.0. As versões anteriores dos
schemas permanecem versionadas e as migrations 1.2→1.3 e 1.1→1.2 são explícitas, não alteram o
objeto de entrada e verificam que cada passo chegou exatamente à versão declarada. Células de tabela
agora têm ID estável; estilos referenciados sem definição no IDML são materializados como
placeholders `unresolved`, preservando o nome da origem sem inventar propriedades.

O Raw rejeita IDs duplicados/vazios, posições de run inválidas, runs ligados a outro story, styles,
frames, tables, cells, notes, objects ou links pendentes, páginas não contíguas, frames sem spread,
thread entre stories e células sobrepostas. A ordem de leitura deve cobrir todos os stories. O
Canonical rejeita campos inline incompatíveis, divergência entre `RichText.plain` e `inlines`, ORCID
com checksum inválido, contributor person/group ambíguo, afiliação duplicada, referência cruzada com
tipo/alvo incorreto, lista/tabela vazia e seção raiz fora do nível 1. IDs inline segmentados passaram
a usar o ID do run, evitando colisão ao redor de fórmulas de bloco.

O gate `ops/gate_phase7_v04.py` aprovou 13 mutações negativas, 128 propriedades Unicode, duas rotas
de migration e round-trip de Raw/Canonical nos seis IDMLs autorizados. O ESA gerou sete seções
canônicas; os cinco RBEdu permaneceram com zero seção sob o profile ESA e motivos explícitos de
revisão, como esperado para corpus de contraste, sem serem promovidos silenciosamente. A suíte
integral aprovou 236 testes com 85,63% de cobertura; Ruff e mypy strict passaram. Relatório:
`benchmarks/qualification/reports/v04-domain-model-integrity-v1.json`.

O backup `/opt/idml-platform/backups/20260908T182615Z` passou no restore isolado com 21 tabelas
públicas, 1 artefato e 14 arquivos OpenClaw. O gate foi reproduzido em container read-only e sem
rede. A imagem `idml-foundation:phase7-v04-model-integrity-v1`
(`sha256:4f46504912f4c5ccfdf46542b2afe28cfe355dfce2875a880d611f9f4834d310`) deixou API, worker e
OpenClaw saudáveis, com OpenClaw, swarm e ClamAV desativados.

## V-05 — Construção XML JATS/SPS

O builder passou a emitir o contrato editorial disponível no Canonical Article: ORCID, prefixo e
sufixo de nome, papéis, e-mail e correspondência ligada por `xref`; afiliação estruturada com
departamento, instituição, ROR e endereço; data ISO estruturada, volume, fascículo, licença e
financiamento; agradecimentos, contribuições, disponibilidade de dados, conflitos, notas e
referências em forma mista e estruturada. O tipo de cada `xref` agora é derivado do alvo registrado,
não de um atributo livre. Declaração UTF-8, DOCTYPE público/sistema e SPS 1.10 são fixos.

O Canonical Article evoluiu para 1.3.0 com `TableCellSpan` e migration aditiva desde 1.2.0. O mapper
leva os spans preservados no Raw até o JATS e o builder gera `rowspan`/`colspan` sem células cobertas
duplicadas. Controles bidirecionais, BOM interno, zero-width space e word joiner permanecem no
Canonical auditável, mas são removidos da serialização para não contaminar o XML.

O validador offline passou a verificar declaração, DOCTYPE, namespaces, idioma, metadados mínimos,
ISSN/DOI, cardinalidade do publisher-id, compatibilidade entre `ref-type` e alvo, gráficos inline e
de bloco, links externos e caracteres invisíveis. O gate `ops/gate_phase7_v05.py` rejeitou 13
mutações negativas, confirmou duas construções idênticas e validou o ESA real com JATS/SPS, zero
referência quebrada e 13 spans preservados. Os cinco RBEdu foram exercitados como contraste: são
bem formados e determinísticos, permanecem reprovados sob o profile ESA e possuem motivos de
revisão explícitos. A suíte integral aprovou 249 testes com 86,11% de cobertura; Ruff passou e mypy
strict foi revalidado após os ajustes finais. Relatório:
`benchmarks/qualification/reports/v05-jats-construction-v1.json`.

O backup `/opt/idml-platform/backups/20260908T195957Z` passou no restore isolado com 21 tabelas
públicas, 1 artefato e 14 arquivos OpenClaw. O gate sintético foi reproduzido na própria imagem em
container read-only, sem rede e sem dependência de `pytest`. A imagem
`idml-foundation:phase7-v05-jats-construction-v1`
(`sha256:5ef4a27be69a7d90c91e1717f38b998473821ccf7b3d52d677e7e080ad2ec4e6`) deixou API, worker,
PostgreSQL, Redis e OpenClaw saudáveis. As flags OpenClaw, swarm e ClamAV permanecem falsas, com
zero `agent_runs`, `agent_proposals` e sessões OpenClaw.

## V-06 — Validadores formais e regras editoriais

Packtools e SPSValidator foram fixados por commit e empacotados em imagens separadas para os canais
ativo e rollback. O registro versionado fixa versão declarada, revisão de origem, ID imutável da
imagem, perfil, comando, timeout e limite de saída. As quatro execuções usam usuário sem privilégio,
filesystem read-only, rede desativada, limites de CPU/memória/processos e `cap-drop=ALL`.

O adaptador aceita somente XML/ZIP limitado, faz parsing seguro, emite um contrato JSON canônico e
sanitiza conteúdo do artigo: permanecem apenas severidades, identidades estáveis das regras,
localizadores em hash, contagens e hashes de evidência. O motor falha fechado para timeout, saída
excessiva ou não UTF-8, JSON inválido, versão/perfil/hash divergentes, severidade desconhecida e
qualquer exceção do validador. Warnings somente podem ser liberados por aceite explícito ligado ao
validador, versão, candidato e código exatos.

O Canonical Article evoluiu para 1.4.0 e o builder passou a representar editora, licença ligada por
URL HTTPS, texto original e código ISO da afiliação, papéis CRediT, histórico editorial, datas de
publicação/coleção, `elocation-id` e modo de disponibilidade dos dados. Isso eliminou as duas
exceções que o SPSValidator inicialmente produzia por ausência de editora e código de licença e
reduziu o candidato sintético de 27 para 1 achado crítico.

As versões ativa e rollback de ambos os validadores concluíram sem exceção. O único crítico
remanescente é um falso positivo reproduzível do próprio Packtools/SPSValidator: a validação de
contribuintes usa o extrator sem enriquecimento de afiliações, embora o mesmo runtime resolva o
`xref/@rid` e a afiliação ao usar `XMLContribs`. Ele permanece visível e **não é dispensado para
release**. Os dois erros remanescentes são verificações externas/semânticas intencionais da fixture
(registro ORCID sem rede e autor de referência ainda não estruturado); nove warnings também não
foram aceitos automaticamente.

O gate `ops/gate_phase7_v06.py` aprovou o registro, atualização/rollback, DTD/SPS offline, contrato
positivo e três mutações negativas, sanitização, empacotamento de gráfico inline, quatro execuções
externas e ingestão do relatório XPM histórico. O XPM 4.0.096 disponível é compatível apenas com SPS
1.9, seu HTML exigiu recuperação controlada e não foi atestado para o candidato; portanto não pode
aprovar release SPS 1.10. A integração definitiva segue reservada ao worker Windows dedicado.
Relatório sanitizado: `benchmarks/qualification/reports/v06-formal-validators-v1.json`.

A suíte integral aprovou 257 testes com 86,44% de cobertura; Ruff, formatação e mypy strict
passaram. Nenhum corpus privado foi enviado à VPS: as execuções externas usaram somente a fixture
sintética sem conteúdo restrito.

O backup `/opt/idml-platform/backups/20260909T134128Z` passou no restore isolado com 21 tabelas
públicas, 1 artefato e 14 arquivos OpenClaw. O gate com as quatro evidências externas foi
reproduzido na VPS em container read-only e sem rede. A imagem
`idml-foundation:phase7-v06-formal-validators-v1`
(`sha256:998e00c388f66a326812d85543b4a246c27e05c55c4fd195e34474d46e0baf65`) deixou API, worker,
PostgreSQL, Redis e OpenClaw saudáveis. OpenClaw, swarm e ClamAV permanecem desativados, com zero
`agent_runs` e `agent_proposals`.

## V-07 — Fidelidade e comparação semântica

Foi introduzido um comparador determinístico e seguro de XML aprovado versus XML candidato. O
relatório separa metadados, autores, afiliações, estrutura, fluxo textual do corpo, referências,
figuras, tabelas, identidade e conteúdo de fórmulas, notas e mídia. Para cada domínio ele registra
hashes, posições, precisão, recall, F1 e fidelidade textual, sem copiar conteúdo restrito. O fluxo do
corpo é comparado por tokens, independentemente das quebras de parágrafo, enquanto elementos cuja
ordem é semântica continuam sujeitos a alinhamento ordenado.

O gate `ops/gate_phase7_v07.py` detecta e bloqueia omissão, invenção, alteração, duplicação e
deslocamento, aceita somente normalização segura e falha se a evidência visual não cobrir todas as
páginas. Os testes sintéticos aprovaram dois casos positivos e cinco mutações negativas. O PDF de
referência foi renderizado a 110 DPI e suas 10/10 páginas foram inspecionadas quanto a legibilidade,
fluxo em duas colunas, figuras, tabelas, fórmulas, referências, cabeçalhos e rodapés, sem anomalia
visual. Somente hashes, contagens e a decisão foram persistidos.

No artigo ESA de desenvolvimento, autores, afiliações, referências e ativos de figuras atingiram
precisão e recall 1,0. O corpo atingiu recall de tokens 0,999269, precisão 0,989683, F1 0,994453 e
fidelidade sequencial 0,991692. O primeiro lote de correções passou a extrair o DOI diretamente do
estilo fonte `0.1.doi`, separou rótulo e texto de caption e ordenou figuras numeradas sem alterar a
intercalação com tabelas. Com isso, o DOI passou a ser correspondência exata e figuras passaram a
precisão/recall 1,0, sem deslocamentos. O segundo lote passou a interpretar o bloco fonte de
correspondência: e-mail ligado ao autor marcado, datas de recebimento e aceite em ISO 8601,
financiamento, conflito de interesse e notas dos editores. O comparador também passou a tratar como
equivalentes as representações por `fn`, `funding-group` e seção de conflito, preservando rótulos
semânticos e eliminando duplicidades. As quatro notas agora estão presentes: conflito e
financiamento são exatos; as duas notas editoriais permanecem alteradas apenas pelos ORCIDs que não
existem no texto nem nos hyperlinks do IDML e ficaram marcados para enriquecimento. O terceiro lote
preservou os estilos inline das células, reposicionou figuras e tabelas após sua primeira menção
textual e transferiu contribuições de autoria e disponibilidade de dados do corpo para o `back`. O
comparador deixou de introduzir espaços artificiais em células e passou a avaliar o conteúdo de
fórmulas exclusivamente em seu domínio próprio. Estrutura, corpo e tabelas atingiram precisão,
recall e F1 1,0; o corpo contém os mesmos 5.466 tokens sem omissão, invenção, duplicação ou
deslocamento. O baseline caiu sucessivamente de 39 para 37, 35 e 25 achados bloqueadores.
Permanecem quatro desvios de metadados, as duas fórmulas inline ausentes, a transcrição semântica das
17 fórmulas e os dois ORCIDs editoriais. Portanto, o mecanismo V-07 está qualificado, mas o candidato
e a família V-07 **não estão aprovados**. Relatório:
`benchmarks/qualification/reports/v07-semantic-fidelity-v1.json`.

A suíte integral aprovou 272 testes com 86,40% de cobertura. Após backup e restore isolado, a imagem
`idml-foundation:phase7-v07-semantic-fidelity-v1`
(`sha256:95ec8c7cc6c1a862c353f7129363fc69c657d3a2013a34106eb310f94dafd905`) foi implantada. O gate
sintético passou na VPS em container read-only e sem rede; o corpus restrito permaneceu local. API,
worker, PostgreSQL, Redis e OpenClaw ficaram saudáveis, as três flags permaneceram falsas e as
tabelas registraram zero execuções e zero propostas de agentes.

O primeiro lote corretivo foi implantado como
`idml-foundation:phase7-v07-deterministic-fixes-v1`
(`sha256:e185f4ffe5be5b94a407ad6b97f847b2f19a0f65c46d35c957d409f7abb83667`) após novo backup/restore.
O gate sintético voltou a passar sem rede, API e worker ficaram saudáveis, as flags permaneceram
falsas e não houve execução nem proposta de agente.

O segundo lote corretivo aprovou 274 testes com 86,32% de cobertura e foi implantado como
`idml-foundation:phase7-v07-correspondence-v1`
(`sha256:23c26409962c93c8162a8c5bd443d69c21a8ebe56fe3154167c587ff8e3966ac`). O backup
`/opt/idml-platform/backups/20260909T204841Z` passou no restore isolado com 21 tabelas públicas, um
artefato e 14 arquivos do OpenClaw. O gate sintético passou novamente em container read-only e sem
rede. API, worker, PostgreSQL, Redis e OpenClaw ficaram saudáveis; as três flags continuaram falsas
e o banco permaneceu com zero execuções e zero propostas de agentes. O corpus restrito não foi
transferido para a VPS.

O terceiro lote corretivo aprovou 278 testes com 86,61% de cobertura e foi implantado como
`idml-foundation:phase7-v07-structure-tables-v1`
(`sha256:19141d0651f4b60fed2812e4a3e051d094b2bd0a0ef8f1862f8d352f8e694636`). O backup
`/opt/idml-platform/backups/20260910T115239Z` passou em checksums e restore isolado com 21 tabelas,
um artefato e 14 arquivos do OpenClaw. O gate sintético passou sem rede e em modo read-only. API,
worker, PostgreSQL, Redis e OpenClaw permaneceram saudáveis; as flags de OpenClaw, swarm e ClamAV
continuaram falsas, com zero execuções e zero propostas de agentes. O corpus restrito permaneceu
exclusivamente local.

O quarto lote completou as 17 fórmulas do artigo: 15 display e duas inline. Cinco janelas aceitas do
laboratório visual totalizaram 485.431 micro-USD, com 34 pareceres críticos `pass`, 16 aceitações do
adjudicador e uma abstenção controlada por risco de consenso correlacionado. O catálogo privado
`formula-transcription-catalog-1.0` é content-addressed, ligado aos hashes do IDML, PDF, recortes,
dataset, propostas e XML aprovado. Onze transcrições privilegiam a evidência visual sobre diferenças
do XML histórico; seis dessas diferenças aparecem como alterações no comparador e somente deixam de
ser bloqueadoras quando o catálogo completo e exato está aplicado. Revisão humana continua
obrigatória.

Um segundo catálogo privado recuperou do XML aprovado o identificador editorial `other` e os dois
ORCIDs que não existem no IDML. A aplicação exige hash exato do artigo e do valor atual, adiciona
evidência ao Canonical Article e mantém `editorial_enrichment_pending_human`. O builder passou a
usar o identificador `other` como identidade editorial quando presente e preserva o identificador
eletrônico como `elocation-id`, evitando duplicação. As quatro notas ficaram exatas.

As duas diferenças finais de metadados foram qualificadas contra suas autoridades independentes: o
título do periódico vem do Journal Profile e o título do artigo vem do próprio IDML. As seis
divergências bibliográficas já auditadas foram vinculadas, por hashes exatos, ao relatório
independente do resolvedor que não usa o XML aprovado em runtime. Nenhuma exceção genérica foi
criada: qualquer alteração de posição, hash, contagem ou alvo volta a falhar fechado.

O gate real `v07-semantic-fidelity-v2` terminou com 0 bloqueios, todos os 12 domínios aprovados e
cross-references em `source_qualified`. O candidato tem SHA-256
`1fa91b9df2cb03f3e9a10337c24489130e3c0711634085f24ee1e9b1c96846ab`. A suíte integral aprovou
287 testes com 86,68% de cobertura; Ruff e mypy strict passaram. Os relatórios públicos são
`benchmarks/agents/reports/formula-transcription-qualification-v1.json`,
`benchmarks/qualification/reports/editorial-enrichment-qualification-v1.json`,
`benchmarks/qualification/reports/source-authority-qualification-v1.json` e
`benchmarks/qualification/reports/v07-semantic-fidelity-v2.json`.

O backup `/opt/idml-platform/backups/20260910T203543Z` passou em checksums e restore isolado com 21
tabelas, um artefato e 14 arquivos OpenClaw. A imagem `idml-foundation:phase7-v07-qualified-v1`
(`sha256:f7acbcb95994b5c24687bb7dac2aeddb3039d1afe19b9882aca1ae2d307d608f`) deixou API, worker,
PostgreSQL, Redis e OpenClaw saudáveis. O gate sintético passou em container read-only e sem rede;
flags de OpenClaw, swarm e ClamAV permaneceram falsas e o banco ficou em `0|0`. Provider, chave e
proxy permaneceram ausentes. Catálogos e corpus privados não foram enviados à VPS.

## V-08 — Validação assistiva OpenClaw

O gate `ops/gate_phase7_v08.py` consolida a matriz adversarial dos seis domínios, sete mutações
explícitas de contrato, controles de custo/timeout/retry e as evidências content-addressed das
execuções reais. O gate reexecuta localmente 30 casos adversariais e 84 papéis simulados, cobrindo
positivo, invenção, ambiguidade, abstenção, falso consenso e prompt injection sem provider ou rede.
Hash incorreto, path proibido, campo extra, patch parcial de `RichText`, DOI/autor inventados e
expansão sem suporte são rejeitados antes dos críticos.

A janela real `phase7-v08-positive-v1` diagnosticou cópia incompleta da evidência e inconsistência
atômica em sete de dez casos. O contrato passou então a usar `agent-proposal-intent-1.0` para toda
evidência textual segmentada que possa ser materializada com segurança: o agente escolhe somente
domínio, paths e evidence ID, e o backend autenticado materializa o texto integral e preserva os
metadados de um inline textual. A matriz adversarial mantém intencionalmente o caminho literal para
continuar exercitando os guardrails contra invenção.

Na janela corretiva `phase7-v08-positive-v2`, as dez propostas foram exatas, melhoraram o baseline,
passaram os oito checks determinísticos e foram materializadas por evidência. Foram 40 papéis, zero
tools/Skills/retries e custo de 276.045 micro-USD. Oito casos foram aceitos apenas para revisão
humana; um caso de afiliação foi corretamente rejeitado pelo crítico XML por duplicação presente no
proxy histórico; e um caso de figura falhou fechado porque o adjudicador declarou `insufficient`
apesar de dois críticos `pass`.

O prompt `adjudicator-1.1.md` tornou a classificação de agreement mecânica e independente da decisão
final. A regressão isolada `phase7-v08-adjudicator-v1` repetiu o caso afetado: candidato exato, dois
críticos `pass`, `unanimous_accept`, aceite somente para revisão humana e custo de 21.827 micro-USD.
Assim, o conjunto efetivo tem nove aceites assistivos e uma rejeição semântica segura, com zero
violação de contrato aberta. O custo novo total da V-08 foi 297.872 micro-USD.

Estrutura permanece ligada à execução real content-addressed de dois domínios; matemática usa o
catálogo completo de 17 fórmulas, 34 pareceres críticos, 16 aceites e uma abstenção controlada. Os
papéis usam o mesmo modelo, logo não constituem independência entre modelos e jamais autorizam
release. O relatório público é
`benchmarks/agents/reports/v08-assistive-validation-v1.json`; os relatórios brutos e sanitizados da
janela permanecem privados na VPS.

Os backups `/opt/idml-platform/backups/20260911T113832Z` e
`/opt/idml-platform/backups/20260911T114816Z` passaram em checksum e restore isolado antes das
janelas. Ao final, chave, proxy e redes transitórias estavam ausentes, as flags continuavam falsas e
o banco permaneceu com zero `agent_runs` e zero `agent_proposals`.

A implantação qualificada foi concluída na VPS com a imagem
`idml-foundation:phase7-v08-assistive-v1`
(`sha256:3d36b16cb9d0ef9ca2af78071bed33e4d533c30737ed7cf785bf7980eda72db3`). Antes do deploy, o
backup `/opt/idml-platform/backups/20260911T115935Z` passou em checksum e restore isolado com 21
tabelas, um artefato e 14 arquivos OpenClaw. A migração foi reaplicada sem alterações pendentes; API,
worker, PostgreSQL, Redis e OpenClaw ficaram saudáveis. O gate V-08 foi repetido dentro da imagem,
read-only e sem rede, incluindo os dois relatórios privados por hash, e foi aprovado. As flags
`IDML_FEATURE_OPENCLAW` e `IDML_FEATURE_AI_SWARM` permaneceram falsas, o banco ficou em `0|0` e
provider, chave e proxy temporários permaneceram ausentes.

## V-09 — Segurança, identidade e multiempresa

A V-09 tomou como base o OWASP ASVS 5.0.0 e o OWASP API Security Top 10 2023. A suíte dedicada
passou com 35 testes de segurança; a suíte completa passou com 305 testes e cobertura de 87,02%.
O gate `ops/gate_phase7_v09.py`, executado sem rede, confirmou 40 operações autenticadas, 30
operações com `X-Organization-ID`, quatro papéis, 11 permissões e 15 contratos de escrita que
rejeitam campos desconhecidos. O teste cruzado percorreu organizações, recursos, jobs/eventos,
artefatos, revisões, snapshots, releases, auditoria e registros/propostas de agentes sem encontrar
vazamento conhecido entre empresas.

Foram corrigidos cinco achados durante a própria família. Login e recuperação agora possuem
limitação distribuída em Redis, com chaves HMAC que não armazenam e-mail ou IP em claro e falha
fechada quando o limitador não está disponível. O login executa a mesma verificação Argon2 para
contas existentes, inativas e inexistentes; sucesso limpa os contadores. Falhas de autenticação são
persistidas na auditoria antes do rollback HTTP. Contratos de escrita rejeitam mass assignment no
topo, e a sanitização de logs passou a remover credenciais também quando aparecem na própria
mensagem ou exceção.

Também foram verificados expiração, logout, recuperação de uso único, invalidação de sessões, MFA,
replay de código, autenticação recente, não enumeração por IDOR, matriz exata de RBAC, CSRF com
Bearer sem cookie, CORS default-deny, CSP/escape de XSS, injeção SQL, XXE, ZIP/path/bomb, upload e
prompt injection em IDML, PDF, XML, metadados e evidências. Cabeçalhos de frame, permissões e
isolamento de opener foram reforçados.

O backup `/opt/idml-platform/backups/20260911T130919Z` passou em checksum e restore isolado com 21
tabelas, um artefato e 14 arquivos OpenClaw. A imagem `idml-foundation:phase7-v09-security-v1`
(`sha256:4c618326fed15652eb9ef5c367b899320fb9c1a1155f637eafe4f461c7c18ad1`) foi implantada; API,
worker, PostgreSQL, Redis e OpenClaw ficaram saudáveis. O limitador Redis foi exercitado e limpo com
uma chave sintética; `.env` permaneceu em modo `600`, artefatos em `640`, e flags de agentes,
provider, proxy e redes transitórias permaneceram desligados/ausentes. O banco continuou com zero
`agent_runs` e `agent_proposals`. O gate V-09 passou novamente dentro da imagem, read-only e sem
rede. Relatório público: `benchmarks/security/v09-security-validation-v1.json`.

## V-10 — Fluxo ponta a ponta e experiência operacional

A V-10 conectou ao worker os jobs duráveis `idml.process` e `scielo.package`. O primeiro lê o
artefato com conferência de SHA-256, executa o pipeline determinístico, persiste snapshots raw e
canônico e publica o XML gerado como artefato íntegro. O segundo reconstrói e valida o JATS a partir
da revisão escolhida, resolve nomes de assets e produz ZIP determinístico com
`ConversionManifest`. As escritas de cada tentativa usam savepoint: falha de parser ou pacote não
deixa snapshots, efeitos ou registros de artefato parcialmente confirmados.

O contrato idempotente passou a rejeitar com 409 a reutilização da mesma chave para uma requisição
diferente. A repetição exata retorna o job já existente sem duplicar job, efeito, artefato,
snapshot ou auditoria de criação. Foram adicionados cancelamento de job enfileirado, retry manual
com wake-up Redis e recuperação automática de falha transitória, todos com versão otimista,
timeline e auditoria. O download de qualquer artefato relê o conteúdo e confere seu hash antes de
responder.

O ensaio completo criou recurso e usuários com papéis distintos; enviou IDML, PDF e imagem;
converteu e baixou XML; aplicou revisão com nova versão e revalidação; montou e baixou o pacote;
comparou o ZIP, manifesto, tamanhos, hashes de cada membro e candidate set; e concluiu duas
aprovações editoriais independentes com MFA. O mesmo cenário terminou com OpenClaw/swarm
desligados e zero `agent_runs`/`agent_proposals`. O IDML ESA autorizado também foi processado pelo
pipeline local sem emitir texto do artigo: válido, fonte
`8ce185f5dd03f5403a36ca7b60d9d708b95e2b334e731327dd0b568b0cd44d2c` e XML
`4059767d2f72e129d648db5a51ba82bfe26b66603319c2ba40c3e26d201454ad`.

A interface agora expõe criação de artigo, IDs completos, conversão, pacote, criação de pendência,
resultado/erro dos jobs, timeline, cancelamento e retry. A sintaxe JavaScript foi conferida com
Node. A suíte dedicada passou com três testes e a suíte completa com 308 testes e 87,44% de
cobertura. O gate `ops/gate_phase7_v10.py` passou localmente e na VPS dentro da imagem, read-only e
sem rede. Relatório público:
`benchmarks/qualification/reports/v10-operational-workflow-v1.json`.

Antes do deploy, `/opt/idml-platform/backups/20260911T155705Z` passou em checksum e restore isolado
com 21 tabelas, um artefato e 14 arquivos OpenClaw; o código anterior foi preservado em
`source-phase7-pre-v10-20260911T155705Z.tar.gz`. A imagem
`idml-foundation:phase7-v10-operational-v1`
(`sha256:2df693031dbcce186e1c9deaf86aeaf3a48f79396c83d99155e534be67a47605`) foi implantada. API,
worker, PostgreSQL, Redis e OpenClaw ficaram saudáveis; migration permaneceu em
`f7b8c9d0e1f2`; `.env` ficou em modo 600, artefatos em 640, flags de agentes falsas e banco em
`0|0`. A UI e os novos endpoints responderam no loopback sem erro nos logs.

A V-10 qualifica cancelamento antes da execução. Interrupção cooperativa durante uma conversão já
iniciada pertence à V-13. Aprovação editorial continua distinta de `READY_FOR_SCIELO`; XPM do
candidato e homologação humana final permanecem pendentes.

## V-11 — Robustez, propriedades e mutações

A V-11 submeteu as fronteiras críticas a 121 entradas binárias arbitrárias, 128 mutações
determinísticas de um bit em ZIPs e cinco formas hostis de XML. Todas as entradas inválidas foram
rejeitadas de maneira controlada. Esse trabalho revelou uma falha real: um ZIP corrompido podia
fazer `ZipFile.testzip()` propagar `zlib.error` fora do contrato de ingestão. A fronteira
`safe_zip` agora normaliza também essa exceção e o caso permanece coberto por regressão.

As propriedades de conservação foram exercitadas com Unicode, conteúdo misto, fórmulas, tabelas e
estilos inline. Reordenação e rotação dos membros do IDML, variação de espaços em XML e renomeação
dos IDs de origem preservaram a semântica esperada. O empacotamento permaneceu invariável à ordem
de entrada e qualquer alteração de membro mudou os hashes vinculados ao manifesto.

A matriz de mutações comportamentais matou 13 de 13 mutantes nos módulos críticos, resultado de
100%, acima das metas iniciais de 85% por módulo e 90% no agregado. Essa métrica mede a força dos
cenários contra comportamentos defeituosos deliberados; não substitui uma futura campanha de
mutação sintática abrangente em todo o código. A suíte dedicada contém nove testes e a suíte
integral passou com 317 testes e 87,50% de cobertura. Ruff, formatação e mypy strict também
passaram. Relatório público:
`benchmarks/qualification/reports/v11-robustness-mutation-v1.json`.

Antes do deploy, `/opt/idml-platform/backups/20260911T184435Z` passou em checksum e restore isolado
com 21 tabelas, um artefato e 14 arquivos OpenClaw. O código anterior foi preservado em
`source-phase7-pre-v11-20260911T161500Z.tar.gz`. A imagem
`idml-foundation:phase7-v11-robustness-v1`
(`sha256:af815334a42d4e3197cd85aa128d5cbae18ece9ec4dc23ba356e329de4eb5bcf`) foi implantada. O gate
`ops/gate_phase7_v11.py` passou dentro da imagem em filesystem read-only e sem rede; API,
PostgreSQL, Redis e OpenClaw responderam saudáveis, a migration permaneceu em `f7b8c9d0e1f2`, as
flags assistivas ficaram falsas e o banco permaneceu com zero `agent_runs` e `agent_proposals`.

A V-11 não autoriza RC nem produção. Os limites reais de desempenho, capacidade e custo da VPS
serão medidos na V-12; interrupção cooperativa, recuperação e continuidade pertencem à V-13; XPM
e a homologação humana final continuam pendentes.

## Requalificação corretiva 7C — artigo e20240135

Em 2026-09-11, o primeiro processamento do novo artigo `ESA_2024135_AOP.idml` foi executado duas
vezes e produziu o mesmo XML. A validação interna básica passou, mas a comparação com a referência
editorial encontrou 108 bloqueios: figuras sem mídia, 40 fórmulas gráficas contra 43 MathML,
hierarquia incompleta, notas ausentes, dois nomes compostos invertidos e uma citação bibliográfica
faltante. O Packtools 4.17.2 confirmou 108 críticos e 79 erros; o pacote recusou o primeiro ativo
inexistente. As 35 referências, cinco tabelas, quatro afiliações e o fluxo textual principal foram
preservados.

O resultado demonstra que os gates detectam a falha, mas que o pipeline ainda não generaliza para
esse segundo arranjo real do template ESA. O baseline 7C-00 está congelado, o risco de overfitting
R-21 foi materializado e as oito etapas corretivas estão em
`docs/PHASE_7_CORRECTIVE_E20240135.md`. Em 2026-09-14, G7C-01 aprovou o manifesto com 12/12
artefatos, o inventário content-addressed e a reprodução exata dos 108 bloqueios. Em 2026-09-14,
G7C-02 corrigiu a classificação dos PDFs `FigNN`, vinculou sete figuras a sete `graphic`, restaurou
a ordem global 1–7 e removeu a seção artificial. Figuras e mídia atingiram precisão, recall, F1 e
fidelidade 1,0; os bloqueios caíram para 94 e os sete JPGs finais resolveram no pré-empacotamento.
Em 2026-09-15, G7C-03 corrigiu a detecção e a posição das 43 fórmulas, classificadas em 32 inline e
11 display. Os recortes do PDF foram autenticados e avaliados por proponente, dois críticos e
adjudicador com o gold oculto; o catálogo final registrou 43 aceites para revisão humana, 86 passes
de críticos, zero abstensão incorporada e custo de 1.793.642 micro-USD. O XML candidato ficou
determinístico e válido, sem fórmula gráfica; `formulas` e `formula_content` passaram. Os bloqueios
gerais caíram para 33, agora fora do domínio de fórmulas. O corpus e o catálogo privados permanecem
exclusivamente locais.

Em 2026-09-16, G7C-04 reproduziu exatamente as 26 seções da referência nos níveis 6/11/9 e
aprovou as sete notas estruturais e dez unidades semânticas de notas. O corpo manteve os 5.814
tokens esperados sem omissão, invenção, alteração, deslocamento ou conteúdo não autenticado;
precisão 0,998969, recall 1,0 e fidelidade 0,998366. Tabelas, referências e as 43 fórmulas
permaneceram aprovadas. O gate determinístico passou sem mismatch e os bloqueios gerais caíram de
30 para 6.

Ainda em 2026-09-16, G7C-05 preservou os quatro autores e quatro ORCIDs da fonte, confirmou os
componentes dos nomes, o título do periódico e `other=00224` por autoridade Crossref independente
e content-addressed, e completou a chamada da referência ordinal 18. O gate atingiu 39/39
cross-references, corpo 5.814/5.814 sem duplicação e zero bloqueio nos 12 domínios após reconciliar
as 24 fórmulas qualificadas. O XML é determinístico e válido sem issues; a revisão humana segue
pendente. O candidato semântico geral está aprovado.

Em 2026-09-17, G7C-06 produziu um pacote byte a byte reproduzível com um XML, um PDF e sete JPEGs,
validação offline sem issues, 35 referências estruturadas e todos os vínculos resolvidos. Foram
eliminados oito erros reais de paginação e as nove divergências restantes entre citação mista e
estruturada. Os achados bloqueantes brutos do Packtools/SPSValidator ficaram restritos a códigos e
quantidades reproduzidos como defeitos de agregação, consulta externa ou ausência comprovada na
própria referência autorizada; o gate falha fechado para qualquer ocorrência nova. O relatório
registra `real_critical_errors=0`, mas mantém `release_ready=false`, pois o XPM SPS 1.10 ainda
depende de execução Windows.

Em 2026-09-17, G7C-07 reavaliou os seis domínios alterados com proponente, críticos XML/editorial e
adjudicador. Os seis casos reais controlados passaram todos os checks e ficaram exclusivamente
`accepted_for_human_review`; cinco foram exatos e a fórmula visual foi semanticamente equivalente.
Foram 24 chamadas, zero reparo, zero falso consenso candidato, zero tool/Skill e custo de 140.447
micro-USD. Os cinco controles negativos específicos falharam fechado, e a matriz adversarial
complementar passou 30/30 casos e 84 papéis sem provider. O cleanup foi confirmado na VPS com
serviços saudáveis, flags falsas e zero credencial, rede transitória, sessão, run ou proposta. Como
os papéis usam o mesmo modelo, `role_models_independent=false` permanece explícito e não autoriza
release.

## Decisão

V-01 a V-11 qualificaram seus mecanismos, com as restrições explícitas de XPM/Windows, do defeito
conhecido do validador externo e da homologação humana ainda pendente. O novo artigo e20240135
reabriu a qualificação de corpus de V-07: o comparador encontrou 108 bloqueios e impediu corretamente
o pacote. G7C-02 eliminou os bloqueios de figuras/mídia, G7C-03 aprovou as 43 fórmulas MathML e
G7C-04 aprovou hierarquia, fluxo e notas, G7C-05 zerou os bloqueios semânticos, aprovou os quatro
autores/metadados e completou 39/39 cross-references, G7C-06 aprovou o pacote formal íntegro e
reproduzível sem retirar o bloqueio do XPM, e G7C-07 aprovou a auditoria assistiva dos seis domínios
sem aplicação automática. Em 2026-09-21, G7C-08 requalificou os dois artigos, incluindo o XML
formal final, e implantou a imagem `phase7-7c08-v1` com rollback comprovado. A suíte passou
380 testes/87,31%; 18 gates foram reproduzidos na VPS sem rede e em filesystem read-only.
V-07 está **PASSOU NO CORPUS ATUAL**. Evidências e rastreabilidade estão em
`docs/PHASE_7C08_REQUALIFICATION.md`. A próxima ação é V-12; o Pacote 7.1 completo,
o G7-T, a RC e a ativação de produção continuam não aprovados.
