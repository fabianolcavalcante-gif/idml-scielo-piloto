# Autoavaliação técnica do corpus inicial e da amostra ESA

Data: 2026-08-26. Estado: **evidência técnica provisória; não substitui revisão humana**.

## Escopo e proteção dos dados

A avaliação usou os seis IDMLs autorizados do corpus inicial e a amostra ESA colocada em
`C:\IDML\tmp\sample`. Conteúdo integral, valores editoriais e respostas brutas do modelo não foram
versionados. A VPS recebeu apenas sete fragmentos minimizados, em diretório privado e modo 600.
Relatórios versionáveis contêm somente hashes, contagens, métricas e códigos de falha. O artigo de
holdout foi executado uma única vez para medição final e não foi usado para ajustar prompt.

## Integridade e leitura da amostra ESA

Os dez arquivos fornecidos conferem por tamanho e SHA-256 com o manifesto `esa-e20240086`. O ZIP
da entrega, presente no manifesto, não veio nesta cópia da amostra e não foi necessário para a
inspeção. O PDF tem dez páginas, camada textual, cinco figuras visualmente coerentes e nenhuma
figura ausente ou cortada observada. Os cinco nomes de `graphic/@xlink:href` do XML correspondem
exatamente aos cinco JPEGs.

| Componente | Referência aprovada |
|---|---:|
| Stories / frames do IDML | 46 / 55 |
| Seções de primeiro nível / todas as seções | 4 / 11 |
| Parágrafos do corpo | 78 |
| Autores / afiliações | 3 / 3 |
| Figuras / tabelas | 5 / 3 |
| Fórmulas inline / display | 2 / 15 |
| Referências / notas | 52 / 4 |
| Páginas | 10 |

A planilha `falsos positivos.xlsx` possui uma única linha e registra `Nenhum` falso positivo. Isso
não significa zero erro: o relatório XPM 4.0.096 contém 0 blocking, 0 fatal, 1 error e 119 warnings.
O erro é uma referência `B37` existente na lista, mas não citada por nenhum `xref` bibliográfico.
A nova regra offline `uncited-reference` reproduz exatamente essa ocorrência como warning local;
o XPM do candidato continua sendo o gate externo bloqueador.

## Comparação determinística

O Gate G3 passou na amostra relocalizada. O Gate G4 também encontrou os assets por hash na nova
subpasta, construiu pacote byte-determinístico e obteve fidelidade aprovada:

| Componente | PDF recall | XML recall |
|---|---:|---:|
| Títulos | 1,000000 | 1,000000 |
| Autores | 1,000000 | 1,000000 |
| Corpo | 0,989725 | 0,998165 |
| Referências | 0,999454 | 1,000000 |
| Figuras e tabelas | 1,000000 | 1,000000 |

O release continua bloqueado porque SPSValidator e XPM não foram executados contra o pacote novo.
O incremento posterior de citações passou a gerar 81 `xref` bibliográficos, cobrindo as 52
referências, inclusive citações presentes em tabelas. O XML permanece válido offline e sem warning
`uncited-reference`. O XML aprovado possui 78 vínculos, 51 referências citadas e uma não citada.

A comparação bruta de alvos contra o XML aprovado obteve precisão 0,925926, recall 0,961538 e F1
0,943396, portanto continua `needs_review` diante do target de 100%. As seis diferenças estão
concentradas em dois casos verificáveis: três citações autor-ano de Boyd, Torrans e Tucker (2018)
apontam no aprovado para as referências 10/11, mas o resolvedor aponta para a referência 13; e três
citações de P. et al. (2018) apontam para a referência 37, que existe no aprovado, mas não recebeu
nenhum `xref` e originou o erro XPM já registrado. Sem revisor humano, essas correções permanecem
candidatas técnicas e não substituem o baseline aprovado. A evidência sanitizada está em
`benchmarks/agents/reports/esa-crossrefs-v1-report.json`.

A comparação textual exata contra o XML aprovado deve ser tratada como proxy técnico, não como
qualidade semântica: text fidelity foi 0,94218; autores tiveram F1 1,0; estrutura F1 0,88; as demais
comparações exatas foram penalizadas por diferenças de representação e formatação. A contagem
estrutural, o PDF e a validação devem ser considerados em conjunto.

## Generalização para os outros artigos iniciais

Os cinco documentos RBEdu foram abertos de forma segura e tiveram Stories, frames e spreads
extraídos, mas o perfil ESA não reconheceu seus estilos: autores, afiliações, seções e referências
canônicas ficaram em zero e a validação falhou. Isso confirma que o sistema é, por enquanto,
específico do template ESA. O holdout RBEdu confirmou a mesma falha de generalização e não foi
usado para mudanças posteriores.

## Benchmark OpenClaw corrigido — v1.1

A primeira rodada com dez casos revelou que três patches exatos de legendas não podiam ser
aplicados porque alteravam `plain.value` sem atualizar os `inlines`. O construtor do benchmark foi
corrigido para excluir esses caminhos escalares acoplados. A versão 1.1 contém sete casos
aplicáveis e registra oito legendas (cinco figuras e três tabelas) como cobertura pendente.

Resultado do agente dedicado `idml-evaluator` com `openai/gpt-5.4-mini`:

| Métrica | Resultado |
|---|---:|
| Casos | 7 |
| Schema e evidência válidos | 5/7 (71,43%) |
| Patch exato no contrato | 1/7 (14,29%) |
| Canônico e JATS válidos | 5/7 (71,43%) |
| Casos com melhora mensurável | 2/7 (28,57%) |
| Casos exatos e aplicáveis | 1/7 (14,29%) |
| Conformidade com orçamento de tokens | 7/7 |
| Tokens médios de entrada / saída | 8.828,43 / 454,86 |
| Latência média | 6,88 s |

Um caso de metadados retornou saída OpenClaw inválida. Um caso de referências produziu hash de
evidência fora do schema. Os três casos de afiliação conservaram o valor original, sem melhora. Um
caso de referência foi corrigido exatamente e outro melhorou apenas 0,00118 de similaridade. Entre
os cinco casos comparáveis, a similaridade média subiu de 0,68071 para 0,74210, mas o resultado é
dominado por um único acerto e não comprova ganho editorial generalizável.

## Preparação do benchmark v1.2 — sem execução de agentes

O contrato de patch atômico foi implementado após a medição v1.1. O backend agora entrega o
contexto `RichText` mínimo, exige a substituição conjunta de `plain.value` e do array completo
`inlines`, rejeita caminhos duplicados ou alterações parciais e valida o canônico/JATS em memória.
Os prompts versionados passaram a `1.1`, e o construtor, runner, scorer e validador do benchmark
foram preparados para o dataset `idml-agent-initial-corpus-eval-1.2`. As oito legendas antes
excluídas podem voltar a compor a avaliação.

Nenhum agente foi executado e nenhuma nova métrica de qualidade foi produzida neste incremento.
As flags de OpenClaw e Swarm permanecem desligadas; o v1.2 será executado somente na etapa futura
de testes com agentes autorizada pelo responsável do projeto.

## Preparação do benchmark v1.3 — sem execução de agentes

Antes de executar o v1.2, o contrato foi endurecido e o dataset preparado passou a v1.3. O schema
ativo `agent-proposal-1.1` exige `evidence_ids` em cada operação e igualdade exata entre o conjunto
de evidências declarado e o efetivamente usado. Operações atômicas do mesmo `RichText` devem citar
a mesma evidência. O hash é recalculado sobre o trecho sanitizado entregue, em vez de aceitar um
hash informado no item.

O envelope `assistive-input-1.1` remove cópias de snapshot e validações redundantes, limita a vinte
evidências, 1.200 caracteres por trecho, dez alternativas de 500 caracteres e registra o tamanho
canônico enviado. O contexto atômico deixou de repetir `plain` e carrega somente os inlines
necessários. Prompts 1.2, configuração 1.1 e bundle de instruções 1.1 foram versionados.

O contrato posterior `assistive-input-1.2` substitui esse limite truncante para valores longos:
transporta até 8.000 caracteres em segmentos lossless de 500, com hashes individuais e agregado.
Prompts 1.3 instruem a remontagem ordenada. Valores curtos preservam o formato 1.1 por compatibilidade.

Essa redução se aplica ao conteúdo controlado pela aplicação; o overhead do system prompt interno
do OpenClaw só poderá ser medido quando os testes de agentes forem retomados. Nenhum agente foi
executado neste incremento, e o v1.2 foi substituído pelo v1.3 antes de qualquer medição.

Em 2026-08-31 o dataset v1.3 foi reconstruído a partir da amostra ESA autorizada. Dez casos ficaram
elegíveis; o primeiro protocolo controlado selecionou apenas um caso de metadados e um de
referências para respeitar o teto agregado por artigo. O manifesto foi reproduzido localmente e na
VPS sem subir provider ou executar agente. Detalhes em `docs/OPENCLAW_CONTROLLED_BENCHMARK.md`.

## Qualificação posterior de estrutura e matemática

O artigo ESA autorizado contém 15 fórmulas display no XML aprovado, 15 objetos de fórmula ancorados
como PDFs no IDML e duas fórmulas inline apenas no XML aprovado. A correção determinística preserva
as 15 fórmulas-imagem, sua ordem/rótulos e as sete subseções de nível 2; a correspondência display
ficou 15/15. O contrato atômico MathML e o JATS candidato já são válidos, e as duas lacunas inline
são detectadas. Três recortes autenticados do PDF foram transcritos sem expor o XML aprovado aos
agentes: uma fórmula display e as duas fórmulas inline ausentes.

O laboratório V9 avaliou uma omissão controlada de estrutura e uma lacuna real de transcrição
matemática. A V9 foi exata; a V10 tornou o caso matemático aplicável e passou os checks/críticos,
mas o adjudicador se absteve por correlação entre papéis. Métricas sem conteúdo do artigo estão em
`benchmarks/agents/reports/real-domain-validation-v1.json` e
`benchmarks/agents/reports/atomic-mathml-validation-v1.json`.

## Decisão e próximos incrementos

Os resultados mantêm `IDML_FEATURE_OPENCLAW=false` e `IDML_FEATURE_AI_SWARM=false`. G6 permanece
bloqueado e a Fase 7 não deve começar. Ordem recomendada de desenvolvimento:

1. [concluído] qualificar casos autorizados de estrutura e matemática, preservando hierarquia e
   fórmulas-imagem sem promover a transcrição a aplicação;
2. [concluído] implementar a transição atômica e validada de fórmula-imagem para MathML, preservar
   fórmula inline quando ancorada e detectar lacunas inline;
3. [concluído] definir patch atômico para `RichText`, preservando `plain` e `inlines` juntos;
4. [concluído] reforçar structured output/evidence binding e substituir truncamento por evidência
   segmentada completa, com hash individual e agregado; o corpus v1.4 passou 10/10 alvos offline;
5. [concluído] observar/bloquear custo por tarifa oficial exata, cache, preflight e teto agregado;
   manter agentes desligados até existir gateway dedicado/restrito;
6. [concluído] extrair/transcrever as fontes visuais, preencher as duas lacunas inline e mitigar o
   consenso correlacionado antes de decidir o G6-T;
7. criar profile/style mapping RBEdu somente quando a expansão de template for autorizada;
8. reservar a adjudicação das seis divergências bibliográficas e o baseline humano para quando os
   revisores estiverem disponíveis, conforme a estratégia de homologação final.

O resolvedor bibliográfico determinístico e a correção da associação das células de tabela foram
concluídos sem IA e sem dependência do XML aprovado em runtime. O gold é carregado somente pelo
Gate G3 para avaliação.

## Evidência de implantação na VPS

O código e o relatório sanitizado foram implantados na imagem
`idml-foundation:phase6-corpus-v1.1`, ID
`sha256:e1d56c0de344a0210872fb55b639603dde66370418559f8f16543935a982e146`. API e
worker ficaram healthy; PostgreSQL e Redis foram preservados. A migration permanece em
`d5f6a7b8c9d0`, com zero `agent_runs` e zero `agent_proposals`. As flags
`feature_openclaw` e `feature_ai_swarm` continuam `false` e os seis perfis de agente carregam.

O backup `/opt/idml-platform/backups/20260826T205408Z` passou no restore isolado com 21 tabelas e
um artefato. O código anterior está em
`/opt/idml-platform/backups/source-phase6-pre-corpus-20260826T205412Z.tar.gz`; a imagem de rollback
é `idml-foundation:phase6-pre-corpus`, ID
`sha256:538fee6c33936b57db1fc926338753e0aea5f6d8a34a6a5c3b281bedf466e6df`. OpenClaw e
os serviços Mapalead permaneceram healthy.

## Implantação do resolvedor bibliográfico

Em 2026-08-27, o incremento foi implantado na imagem
`idml-foundation:phase6-crossrefs-v1`, ID
`sha256:667c5faff1f8406659f1deddae03680eb1d0edab56e13e25398040d57ad6e893`. A
imagem anterior foi preservada como `idml-foundation:phase6-pre-crossrefs`, ID
`sha256:e1d56c0de344a0210872fb55b639603dde66370418559f8f16543935a982e146`.

O backup `/opt/idml-platform/backups/20260826T212034Z` passou no restore isolado com 21 tabelas e
um artefato; o código anterior está em
`/opt/idml-platform/backups/source-phase6-pre-crossrefs-20260826T212034Z.tar.gz`. API, worker,
PostgreSQL e Redis ficaram healthy; a migration permaneceu em `d5f6a7b8c9d0`, com zero
`agent_runs` e zero `agent_proposals`. As flags de IA permaneceram desligadas, e OpenClaw e
Mapalead continuaram healthy.
