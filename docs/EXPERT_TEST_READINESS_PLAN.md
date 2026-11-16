# Plano de liberação para o especialista — controle consolidado

Atualizado em 16/11/2026. A conta individual do especialista pode criar artigos,
enviar IDML, PDF e imagens e acompanhar a conversão e o pacote na empresa
**Homologação ESA — novos artigos**, no [portal web](https://143.95.214.8:8443/app).
Na empresa **Qualificação ESA — catálogos**, a mesma conta pode revisar os dois
exemplos de referência. O [roteiro](ROTEIRO_REVISOR_XML.md) descreve ambos os percursos.
As seções 66 e 67 do plano consolidado registram a abertura e a ampliação do piloto.

A fila única, escopo congelado, evidências e critérios de término estão em
[`HOMOLOGATION_VH1_DELIVERY.md`](HOMOLOGATION_VH1_DELIVERY.md).
São vinte itens em seis lotes; nenhum é considerado concluído apenas por existir
um ensaio de laboratório. Não abrir novas fases fora desse escopo sem decisão explícita.

Checkpoint histórico — 2026-10-16 / VH-02: consultas restritas na VPS e cadastro real
qualificados; três casos nativos, 111 testes direcionados, 25 serviços preservados.
Não há aprovação XML; Wayta continua recusado e as regras legadas exigem decisão
pontual de compatibilidade. VH-05 reaberta apenas para título do periódico/editora,
próxima correção delimitada; VH-07 revalidará novos pacotes. Sem implantação/IA
ativada. Detalhes: `VH1_XPM_ONLINE_AND_COMPATIBILITY.md`. A proposta de exceções
foi autorizada posteriormente em 16/10 (ADR-019), mas não implementada/ativada
e não autoriza publicação. Sequência restante na seção 29 do plano único:
XML/compatibilidade → IA → fluxo web → implantação VPS → testes finais/entrega.
Checkpoints seguintes são históricos.

Checkpoint — 2026-10-15 / VH-02: XPM original executado sem interface gráfica
na mesma VPS, por autorização do proprietário, com dois artigos e três negativos
detectados. Cinco relatórios reais, 49 testes direcionados e serviços preservados.
ADR-002 revisada: não exigir Windows. Restam compatibilidade SPS 1.10/JATS 1.3,
consultas externas e integração supervisionada/web; XML/release ainda não aprovados.
Detalhes: `VH1_XPM_LINUX_QUALIFICATION.md`. VH-02/07 continuam parciais; VH-08 pode
avançar independentemente. Checkpoints abaixo são históricos.

Checkpoint — 2026-10-14 / VH-07: consolidação dos pacotes e triagem entregues,
uma hierarquia institucional corrigida. Dois artigos: **0 críticos/0 erros/5 avisos
por ferramenta**, consultas completas no ensaio nativo; avisos preservados e
classificados. 103 testes novos, regressão focada; não é nova suíte integral.
VH-07 parcial por XPM: definir executor Windows isolado e qualificar SPS 1.10,
sem dispensar o requisito. Enquanto depende da definição de ambiente, VH-08 pode
avançar conforme o plano único. Sem implantação/liberação. Evidência atual:
`VH1_FINAL_VALIDATION_AND_WARNINGS.md`. Checkpoints abaixo são históricos.

Checkpoint 2026-10-01: VH-01/03 entregues; XPM oficial e fontes autorizadas já estão
na área privada da VPS. VH-02 parcial: ainda faltam executor/compatibilidade, não
download ou consentimento. Lote 1 ainda não encerrado integralmente. Detalhes:
`VH1_LOT1_BASE_AND_SOURCES.md`. Última suíte completa: 803 aprovados, 88,07%; depois,
60 testes direcionados para download/armazenamento/autorização aprovados. Sem
implantação da candidata, ativação dos bundles ou aprovação formal do XML.

Checkpoint posterior — VH-04: DOI/fascículo/seção e os quatro ORCIDs presentes
passaram na qualificação nativa das duas imagens Linux fixadas, com contraprovas.
O checkpoint nativo está preservado em `VH1_LOT2_EDITORIAL_AUTHORITIES.md`.

Checkpoint — 2026-10-03: **VH-04 concluído no desenvolvimento candidato**.
Adapters/broker/worker integram autoridades vinculadas à empresa/artigo/candidato,
com validade/revogação e instalação atômica. Quatro execuções Linux pelo socket
e contraprovas qualificadas; escopos de laboratório sintéticos, sem implantação.
**938 testes aprovados, cobertura 88,09%**. Detalhes e limitações:
`VH1_SCOPED_VALIDATOR_INTEGRATION.md`. Próximo ID: **VH-05 (metadados)**;
depois VH-06/07. XPM em VH-02 e ativação com IDs reais em VH-14/16 permanecem
pendentes. Nenhuma alteração na aplicação ativa ou aprovação integral de XML.

Checkpoint — 2026-10-05: **VH-05 parcial**. Além de UFs/CRediT,
importação conserva precisão de datas e recusa conflitos. Financiamento explícito
é estruturado; texto ambíguo não é truncado nem tem auxílio atribuído por inferência.
Primeiro artigo: 13 críticos/3 erros por ferramenta; segundo: 6/0, sem novos achados.
A redução de um crítico pela retirada do grupo incompleto **não resolve o financiamento**.
**1.042 testes aprovados, 88,32% de cobertura**. V09 com hash de `settings.py`
desatualizado e duas pendências de formatação ficam em VH-17; CI global não aprovado.
Próximo passo permanece VH-05: fontes editoriais para datas/histórico e vínculos de
financiamento, estados e ORCID ausentes. Sem implantação ou ativação IA.
`VH1_METADATA_CORRECTIONS.md` registra causas, evidências e limites.

Checkpoint — 2026-10-06: **VH-05 parcial, datas ArticleMeta qualificadas**.
Fonte oficial confirmou publicação completa e resolveu a interpretação ambígua
de recebimento/aceite do e20240086. Catálogo vinculado à fonte e ao artigo, com
autorização/validade e revisão humana preservadas, integrado ao worker candidato.
Quatro execuções nativas: primeiro artigo **8 críticos/3 erros/9 avisos**, contra
13 críticos anteriormente; segundo **6 críticos/0 erros/5 avisos**, inalterado.
**1.088 testes aprovados, 88,41% de cobertura**; V10/V11 requalificados e gates
desse incremento passam. V09/formatação históricos continuam pendentes em VH-17.
Próximo: verificar/integrar ORCIDs ausentes, ainda em VH-05, além de estados,
financiamento e revisões/aplicabilidade. Depois VH-06/07. Sem novos lotes,
implantação, ativação IA, aprovação integral de XML ou liberação G-HOMOLOG.

Checkpoint — 2026-10-06, ORCIDs: **VH-05 parcial**. Três identificadores
recuperados com associação exata no ArticleMeta e nome confirmado no registro
público ORCID, sem alegar autenticação pelo autor. Catálogo integrado ao worker
candidato e quatro execuções nativas na VPS: primeiro artigo **5 críticos/3 erros/9
avisos**; segundo permanece **6 críticos/0 erros/5 avisos**. Sem achados novos.
**1.139 testes aprovados, cobertura 88,52%**, gates do incremento e V10/V11 passam;
V09/formatação históricos seguem em VH-17. Próximo: estados/províncias, ainda em
VH-05, seguidos de financiamento e revisões/aplicabilidade; depois VH-06/07.
Aplicação ativa preservada. Não é implantação ou aprovação integral/G-HOMOLOG.

Checkpoint — 2026-10-06, estados/províncias: **VH-05 parcial**. Cinco
afiliações agora possuem estado confirmado por seis fontes institucionais ou
governamentais. Catálogo administrativo integrado ao worker candidato, com
correspondência exata, evidência, autorização e bloqueio para fonte alterada.
Somente o estado ausente é acrescentado; não há inferência geográfica nem edição
científica. Tokyo não foi confundida com a região Kanto.
Quatro execuções nativas na VPS: e20240086 **4 críticos/3 erros/9 avisos**;
e20240135 **2 críticos/0 erros/5 avisos**. Sem achados novos; cinco ocorrências
críticas de afiliação eliminadas por ferramenta. **1.190 testes/88,62%**;
gates do incremento e V10/V11 aprovados, V09/formatação históricos em VH-17.
Próximo: financiamento e revisões/aplicabilidade, ainda na VH-05; depois VH-06/07.
Detalhes/fontes/limites: `VH1_METADATA_CORRECTIONS.md`, relatório nativo v6.
Aplicação ativa preservada, sem ativação IA, implantação ou aprovação G-HOMOLOG.

Checkpoint — 2026-10-06, financiamento: **VH-05 parcial**. Par agência/auxílio
do e20240086 estruturado após comprovação em publicação institucional da Embrapa,
mantendo integralmente a declaração e os demais apoiadores. Catálogo administrativo
com evidência do IDML/PDF, escopo e autorização, sem copiar contratos de outros artigos.
Quatro execuções nativas na VPS: e20240086 **2 críticos/3 erros/9 avisos**;
e20240135 permanece **2 críticos/0 erros/5 avisos**, inclusive XML/ZIP. Sem novos
achados; eliminadas duas ocorrências críticas de financiamento por ferramenta.
**1.235 testes/88,69%**, gates do incremento e V10/V11 passam; V09/formatação
históricos seguem VH-17. Próximo: datas de revisão/aplicabilidade com fonte
editorial/normativa 1.10; depois os três vínculos de fórmulas na VH-06 e VH-07.
Não alterar regras apenas para zerar contagens. Fontes/provas: `VH1_METADATA_CORRECTIONS.md`,
relatório nativo v7. Aplicação ativa preservada; sem ativação IA ou G-HOMOLOG.

Checkpoint — 2026-10-07, histórico: **VH-05 concluída no desenvolvimento
candidato**. Especificação 1.10 obtida confirmou divergência na obrigatoriedade
universal de revisão da configuração nativa. Correção restrita e auditada, sem
inventar datas, inferir ausência de revisão, rebaixar severidades ou editar XML.
Bibliotecas intactas, imagens/registro separados; resultados originais preservados.
Quatro execuções completas na VPS: e20240086 **0 críticos/3 erros/9 avisos**;
e20240135 **0 críticos/0 erros/5 avisos**, por ferramenta. Nenhum achado novo;
os três erros restantes são vínculos de fórmulas da VH-06. Treze contraprovas
nativas por imagem e 62 testes locais novos, gate integrado ao CI.
Regressão completa: **1.297 testes aprovados, cobertura 88,69%**, sem falhas/skip;
V09/formatação históricos continuam em VH-17, sem alegação de CI global verde.
Detalhes e fundamento: `VH1_METADATA_CORRECTIONS.md` e ADR-018.
**Próximo: VH-06, depois VH-07.** Fonte/versão integrada, IA, UI, XPM, operação e
E2E continuam nos IDs existentes. Sem implantação, ativação IA ou G-HOMOLOG;
enriquecimentos continuam sujeitos à avaliação humana final.

Checkpoint — 2026-10-07, vínculos: **VH-06 parcial**. Cinco vínculos de
fórmulas corrigidos sem mudar texto, MathML ou arquivos de apoio. Quatro execuções
nativas confirmam e20240086 **0 críticos/0 erros/9 avisos** e e20240135 **0/0/5**,
sem novos achados. 90 testes novos, 136 focados e V10/V11 requalificados; gate
de evidência integrado ao CI. **1.387 testes/88,76%** na regressão final,
sem falhas/erros/skip. V09/formatação históricos seguem em VH-17; CI global não aprovado.

A inspeção visual do PDF detectou divergência preexistente `g`/`a` na fórmula 15;
ela permanece aberta, não encoberta pelo zero de erros formais. **Próximo: corrigir
a transcrição em versão rastreável e conferir fidelidade ainda na VH-06**; fechar
referências/seções/objetos e então consolidar VH-07. XPM e os demais itens mantêm
a sequência/escopo fechado. Evidências: `VH1_FORMULA_LINKS_AND_FIDELITY.md`.
Aplicação ativa preservada; não houve implantação, ativação IA ou G-HOMOLOG.

Checkpoint — 2026-10-08, transcrições: **VH-06 parcial**. Corrigidas 14
transcrições com fonte visual, incluindo a divergência da fórmula 15. Catálogo 1.1
preserva a versão anterior, qualificação IA histórica e revisão humana futura.
Conferência de 60 registros: 14 corrigidos, 41 sem defeito confirmado e 5 revisões
de glifo/estilo pendentes. Zero erro formal não equivale a fidelidade científica.
Reconversões determinísticas e comparação integral confirmam que somente os 14
fragmentos MathML mudaram; PDF/imagens e demais nós XML foram preservados.

Novas consultas externas e quatro execuções nativas na VPS: e20240086 **0 críticos/
0 erros/9 avisos**, e20240135 **0/0/5**, por ferramenta e sem novos achados.
**1.469 testes aprovados/88,81%**, incluindo 82 novos; V10/V11 requalificados.
V09/formatação históricos continuam em VH-17; CI global não aprovado.
**Próximo: resolver as cinco revisões, conferir símbolos em texto dos algoritmos
e fechar referências/seções/objetos na VH-06; depois VH-07.** Não são novos itens
da fila. XPM/IA/UI/operação/E2E permanecem no escopo congelado.
Detalhes: `VH1_FORMULA_SOURCE_REVISIONS.md`. Sem implantação, ativação IA ou
liberação G-HOMOLOG; aplicação ativa preservada.

Checkpoint — 2026-10-09, glifos e conteúdo (ensaios de 2026-10-08):
**VH-06 parcial**. Mais quatro fórmulas corrigidas por fonte, totalizando 18;
14 posições de símbolos corrigidas pelo importador, respeitando a propriedade
explícita do IDML. Uma dúvida científica permanece com abstenção para o especialista.
Primeiro XML/ZIP inalterado; segundo muda somente nos quatro MathML e 14 posições
comprovados. Catálogos anteriores, evidências e revisão humana preservados.

Quatro execuções nativas na VPS: e20240086 **0 críticos/0 erros/9 avisos**;
e20240135 **0/0/5**, sem novos achados. **1.540 testes/88,81%**, sem falhas/skip,
incluindo 71 novos; V03 confirma 106/106 stories, V10/V11 requalificados.
V09/formatação históricos seguem VH-17; sem aprovação global de CI.

A auditoria pós-conversão confere seções/referências/objetos, mas identifica
segmentação bibliográfica sem volume a corrigir e diferenças de citações a adjudicar
contra a fonte, inclusive inconsistências no gold. Achados integrais brutos
permanecem visíveis. **Próximo: corrigir os subcampos de referências e fechar a
triagem/adjudicação na VH-06; depois VH-07.** Não abrir nova fase nem repetir
indefinidamente a pesquisa do glifo ambíguo. Detalhes: `VH1_GLYPHS_AND_CONTENT_AUDIT.md`.
Aplicação ativa preservada; sem implantação, ativação IA ou liberação G-HOMOLOG.

Checkpoint histórico — 2026-10-09, referências: **VH-06 parcial**. Corrigidos 23 campos
em 13 referências; citações integrais, xrefs, fórmulas e assets preservados.
Seis diferenças de citações do primeiro artigo adjudicadas com fonte: três destinos
de outro ano no gold e três vínculos ausentes; não são seis defeitos da candidata.
No segundo, 39/39 chamadas coincidentes. Achados integrais brutos continuam visíveis.

Quatro execuções nativas: **0 críticos/0 erros/9 avisos** no primeiro artigo e
**0/0/6** no segundo. O novo aviso de data de acesso é real e foi diagnosticado;
antes o trecho era absorvido indevidamente pelo título/fonte. 95 testes novos,
150 focados aprovados, V03 real 106/106 stories e V10/V11 requalificados.
Regressão final: **1.635 testes aprovados/88,99%**, sem falhas/erros/skip, após
corrigir a ligação de um gate histórico à nova prova; tentativa inicial preservada.
Detalhes e regressão final: `VH1_REFERENCE_FIELDS_AND_AUDIT.md`.

**Próximo: datas de acesso explícitas, tipos/campos de livros/capítulos/tese/web,
conferência das 87 referências e triagem final na VH-06; depois VH-07.** Mesmo
escopo, sem novas fases. Uma abstenção científica para o especialista mantida.
V09/formatação históricos continuam VH-17; aplicação ativa preservada e G-HOMOLOG
não liberado. Não houve chamada/ativação OpenClaw ou implantação neste incremento.

Checkpoint histórico — 2026-10-13, tipos/datas: **VH-06 parcial**. Quinze referências
ajustadas e quatro datas de acesso marcadas; livros, capítulos e tese separados de
periódicos. Schema canônico 1.5.0 e migração sem inferência. Auditoria das 87
referências verifica literalidade no IDML e preservação de texto/autores/anos/DOI/URLs.
Três tipos online continuam não resolvidos, com revisão explícita e sem classificação
automática como webpage. A presença literal não é aprovação semântica.

Qualificação nativa em 09/10: primeiro artigo **0 críticos/0 erros/6 avisos**;
segundo **0/0/5**, quatro avisos resolvidos por ferramenta, sem achados novos.
109 testes novos e 259 direcionados aprovados; **1.744 aprovados/89,10%** na
regressão integral, sem falhas/erros/skip. V03 real 106/106 stories; V10/V11
reexecutados e novo gate integrado ao CI. Evidências: `VH1_REFERENCE_METADATA.md`.
Comparador bruto conserva sete/23 achados; seis adjudicações anteriores mantidas.

**Próximo: resolver três tipos com fonte e encerrar a triagem de conteúdo na VH-06;
depois VH-07.** Dúvida única de glifo permanece para revisão especializada prevista.
Aplicação ativa e imagens preservadas; sem deploy/IA/G-HOMOLOG. V09/formatação
históricos continuam em VH-17; sem abrir outras fases ou aprovar o CI global.

Checkpoint atual — 2026-10-14: **VH-06 concluída no desenvolvimento candidato**.
As três referências restantes receberam classificação com fonte: uma página web
e dois relatórios. Os 87 textos bibliográficos foram preservados; duas URLs ainda
exigem conferência editorial. Catálogo administrativo integrado ao worker,
com escopo/validade/revogação, sem novas permissões autônomas de IA.

Triagem das 30 diferenças brutas concluída com provas históricas de fonte: duas
de grafia/fronteira de palavras, 27 ocorrências de fórmulas revisadas e uma
abstenção científica de glifo. O comparador bruto não foi aprovado nem alterado;
revisão humana continua obrigatória. Revalidação nativa na VPS em 14/10:
**0 críticos/0 erros, seis/cinco avisos por ferramenta**, exatamente como antes.

**1.892 testes aprovados, 89,20% de cobertura**, incluindo 148 novos;
407 direcionados, V03 real 106/106 stories e V10/V11 atuais. Detalhes e limites:
`VH1_REFERENCE_TYPES_AND_CONTENT_TRIAGE.md`. Aplicação ativa preservada;
sem implantação, ativação OpenClaw ou liberação G-HOMOLOG. V09/formatação
históricos permanecem VH-17; não é aprovação global de CI.

**Próximo: VH-07**, consolidar validadores aplicáveis, consultas e avisos do
pacote exato, mantendo explícita a dependência VH-02/XPM. Demais IDs inalterados.

## Mapeamento dos planos anteriores

| Frente anterior | Execução na entrega VH1 |
|---|---|
| H0 — baseline | VH-01–03: atualizar versões e resolver dependências |
| H1 — XML/autoridades/XPM | VH-02–07 |
| H1-A — automação restrita | VH-08–10,12,17–18 |
| H2 — implantação segura | VH-14–16 |
| H3 — fluxo integrado | VH-11–13,17–18 |
| H4 — acesso/roteiro | VH-19 |
| G-HOMOLOG | VH-20, depois de todos os aceites |
| H5 — feedback humano | Depois da entrega; fila separada |

## Linha de chegada preservada

- Dois artigos de referência passam pelo fluxo implantado e pelos validadores
  aplicáveis; fidelidade e ausência de erros reais impeditivos comprovadas.
- IA aplica somente operações explicitamente qualificadas, com evidência,
  revalidação, abstenção e reversão. Humano avalia resultado e pendências ao final.
- Interface utilizável sem IDs/terminal; revisão e downloads com estados honestos.
- Segurança, isolamento, limites, backup/restore e rollback mínimos comprovados.
- Versão congelada, roteiro/limitações e acesso individual preparados.

XPM compatível continua requisito enquanto a política não for formalmente revista.
G-HOMOLOG não é publicação, produção editorial, indexação SciELO ou aceite final G8-H.
Não prometer suporte universal nem condicionar o piloto à operação de produção completa.

Detalhes da automação: `AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`.
Decisões: ADR-015, ADR-016 e ADR-017. O histórico anterior, inclusive resultados e
limitações de cada etapa, foi preservado em `EXPERT_TEST_READINESS_HISTORY_20261001.md`.
As fontes originais de evidência não foram alteradas.
