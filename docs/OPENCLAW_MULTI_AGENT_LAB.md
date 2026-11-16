# Laboratório multiagente OpenClaw

## Objetivo

O laboratório mede a qualidade de propostas XML antes da homologação humana final. Ele não altera
artigos, não persiste propostas na aplicação e não autoriza release. Toda conclusão permanece
provisória com `needs_human=true` até o Gate Humano Final G8-H.

## Papéis e isolamento

Cada caso usa quatro sessões OpenClaw distintas, sem ferramentas ou Skills:

1. `proposer`: produz uma proposta estruturada a partir da evidência autorizada;
2. `xml_critic`: verifica contrato, evidência, paths e integridade XML/JATS;
3. `editorial_critic`: verifica fidelidade semântica, omissão, invenção e normalização;
4. `adjudicator`: consolida apenas as saídas estruturadas anteriores.

O alvo automático (`expected_value`) nunca é enviado aos agentes. Raciocínio privado não é
compartilhado entre sessões; críticos recebem somente o caso minimizado e a proposta, e o
adjudicador recebe somente proposta e críticas. Prompts e schemas são versionados e incluídos por
hash no manifesto.

## Precedência determinística

O juiz local valida novamente hashes, paths, atomicidade de `RichText`, escopo, política, injeção e
vínculos entre as quatro saídas. Concordância dos agentes não substitui evidência. Se houver consenso
positivo sem ganho sobre o baseline automático, o resultado final é `abstained` com risco de falso
consenso. Erro operacional encerra a janela; violação de contrato rejeita o caso.

## Janela v1

A configuração `config/openclaw-multi-agent-lab-v1.json` seleciona inicialmente os casos ESA de
metadados e referências. São oito chamadas sequenciais, tentativa única, timeout de 45 segundos por
papel e teto agregado de 150.000 micro-USD (US$ 0,15). As flags
`IDML_FEATURE_OPENCLAW` e `IDML_FEATURE_AI_SWARM` devem permanecer falsas.

## Janela v2 — corpus ESA disponível

A configuração `config/openclaw-multi-agent-lab-v2.json` seleciona os dez casos reais disponíveis:
metadados, autores/afiliações, referências e figuras/tabelas. São no máximo 40 chamadas sequenciais,
tentativa única, timeout de 45 segundos por papel e teto agregado de 585.000 micro-USD. O contrato
atômico de `RichText` fornece template completo, exige inlines não vazios, preserva todos os campos e
IDs e permite alterar somente o texto, cuja concatenação deve reproduzir exatamente o valor plain.

O endpoint OpenResponses da versão OpenClaw fixada não aceita o campo `text.format` do Responses API.
O cliente passou então a fornecer uma única função terminal não executável,
`submit_idml_structured_output`, e força `tool_choice` para essa função. O schema completo permanece
nas instruções e na revalidação Pydantic do backend; o schema entregue ao provider usa somente o
subconjunto conservador aceito por function calling. Exatamente uma chamada, sem texto adjacente, é
aceita. JSON puro ou um único fence exato continuam disponíveis apenas para compatibilidade legada.
Falha de contrato rejeita apenas o caso e reserva o custo máximo do papel; falha operacional ou de
política encerra a janela inteira.

O dataset e o manifesto ficam privados em `benchmarks/private/input`; resultados brutos e relatório
sanitizado ficam em `benchmarks/private/output`, todos em modo 600. O relatório público contém apenas
métricas, códigos de decisão, hashes e custo — nunca trechos, valores propostos ou respostas brutas.

## Janela v3 — evidência completa segmentada

A configuração `config/openclaw-multi-agent-lab-v3.json` usa os mesmos dez casos reais com o dataset
privado v1.4. Cada evidência é dividida em segmentos de até 500 caracteres, limitada a 16 segmentos
e 8.000 caracteres. Cada segmento tem hash próprio; o hash agregado vincula identidade, locator,
ordem, contagem, tamanho e todos os hashes. A remontagem é sem separadores e deve reproduzir o texto
integral. Ausência, reordenação, alteração, mistura com o formato legado ou estouro do limite falha
antes de qualquer chamada ao agente.

## Janelas v4–v6 — saída estruturada real

As janelas v4 e v5 isolaram as duas referências longas e o maior caso, respectivamente. O diagnóstico
do primeiro V5 mostrou que o OpenClaw reservava internamente 16.384 tokens para geração: com
`contextTokens=12000`, restavam apenas 6.000 para um prompt estimado em 6.903. O agente dedicado foi
ajustado para 32.000 tokens de contexto operacional, mantendo 12.000 como limite de entrada do
laboratório, 4.000 como maior saída por papel e 400.000 como janela declarada do modelo.

A janela v6 seleciona o caso curto real de metadados para comprovar o novo canal nos quatro papéis.
Ela permite no máximo quatro chamadas, tentativa única e 58.500 micro-USD. Nenhuma função operacional,
ferramenta nativa ou Skill é exposta; a única função é um envelope terminal sem execução.

## Janelas v7–v8 — intent autenticado para referência longa

As janelas v7 e v8 selecionam a referência real de 734 caracteres. Para evidência com múltiplos
segmentos, `RichText` atômico e nenhum inline preexistente, o proponente retorna somente a seleção da
evidência e dos paths no schema fechado `agent-proposal-intent-1.0`. O backend revalida a referência,
remonta os segmentos autenticados e produz `plain.value` e `inlines` sincronizados no contrato
`agent-proposal-1.1`. O provider não pode fornecer valor literal nesse modo. Hashes distintos preservam
a proveniência da intenção original e da proposta materializada.

A v7 comprovou fidelidade exata, mas revelou que os dois críticos interpretavam as representações
paralelas de `RichText` como duplicação ou normalização divergente. A v8 passa aos críticos a
proveniência da materialização e explicita que os checks determinísticos do backend são
autoritativos; ela não relaxa nenhum check nem altera o conteúdo.

## Janela v9 — estrutura e matemática do artigo autorizado

A v9 usa o dataset privado `idml-agent-real-domain-eval-1.0`. O caso de estrutura aplica uma omissão
controlada a um título real de subseção, sem inventar um cenário editorial. O caso de matemática
registra a lacuna observada entre um recorte PDF ancorado no IDML e a fórmula aprovada. Esse segundo
caso é exclusivamente avaliativo e carrega `application_ready=false`: aceitar a transcrição no
laboratório não autoriza gravá-la no Canonical Model nem tratá-la como MathML nativo.

São dois casos, quatro papéis por caso, tentativa única e teto de 117.000 micro-USD. O manifesto,
dataset e relatório bruto permanecem privados em modo 600; somente métricas sanitizadas podem ser
versionadas.

## Operação na VPS

Preparar e validar o manifesto, sem inferência:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-first-window
```

Executar somente em janela autorizada:

```sh
cd /opt/idml-platform
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V1 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-first-window
```

Preparar ou executar a janela v2 requer o terceiro argumento e a confirmação própria:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-full-corpus v2
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V2 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-full-corpus v2
```

A janela v3 usa dataset v1.4 e confirmação distinta:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-segmented-corpus v3
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V3 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-segmented-corpus v3
```

A comprovação estruturada dos quatro papéis usa a janela v6:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-structured-all-roles v6
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V6 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-structured-all-roles v6
```

A comprovação da referência longa e dos críticos alinhados usa a janela v8:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-evidence-intent-critics-v2 v8
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V8 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-evidence-intent-critics-v2 v8
```

A qualificação controlada de estrutura e matemática usa a janela v9:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-real-domains-v1 v9
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V9 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-real-domains-v1 v9
```

O script verifica zero `agent_runs`/`agent_proposals`, faz backup e restore test, ativa o provider
somente durante a janela e sempre chama o kill switch no encerramento. O pós-teste deve confirmar
flags falsas, zero sessões, ausência do proxy/redes transitórias e saúde da aplicação, do gateway
dedicado e do OpenClaw compartilhado.

## Critério para ampliar o corpus

A primeira janela valida o mecanismo, não o Gate G6-T. A expansão exige casos positivos, negativos,
ambíguos, de abstenção e injeção para cada domínio; toda falha confirmada vira fixture. O G6-T só pode
ser aprovado após cobertura integral, metas técnicas satisfeitas e relatório por domínio, sem
antecipar a homologação do especialista em XML.

## Evidência da primeira janela

Em 2026-09-01, `multi-agent-first-window-v1` concluiu os dois casos por 32.824 micro-USD. Metadados
foi exato e aceito somente para futura revisão humana. Referências foi rejeitado pelo juiz local antes
dos críticos porque as duas representações atômicas de `RichText` divergiram. O caso foi convertido
em teste de regressão. O relatório sanitizado está em
`benchmarks/agents/reports/multi-agent-first-window-v1.json`; o resultado bruto permanece privado.

## Evidência da janela v2

Em 2026-09-01, `multi-agent-full-corpus-v2r2` concluiu os dez casos e 26 chamadas por 218.200
micro-USD. Metadados passou nas sete verificações determinísticas, foi exato contra o alvo automático
e ficou aceito somente para a futura revisão humana. Os nove casos restantes foram rejeitados por
`AGENT_OUTPUT_NOT_JSON`: duas falhas no proponente, quatro no crítico XML e três no adjudicador. A
aceitação do fence JSON exato não alterou a taxa da janela anterior, portanto saída estruturada
confiável continua uma pendência técnica do gateway/modelo, e não deve ser contornada extraindo JSON
de prosa arbitrária.

O custo conservador acumulado das janelas deste artigo ficou em 528.995 micro-USD. O relatório
público sanitizado está em `benchmarks/agents/reports/multi-agent-full-corpus-v2.json`; resultados
brutos permanecem privados em modo 600. O pós-teste confirmou flags falsas, zero
runs/propostas/sessões, ausência de chave do provider no gateway, proxy e redes transitórias
ausentes, API/interface em HTTP 200 e os dois OpenClaw saudáveis sem reinicialização do compartilhado.
O token do gateway dedicado foi rotacionado após a auditoria, sem registrar o valor anterior ou o
novo. O G6-T continua pendente.

## Matriz adversarial local v1

O arquivo `benchmarks/agents/adversarial-matrix-v1.json` congela cinco cenários para cada um dos seis
domínios: positivo, negativo por valor inventado, evidência ambígua, falso consenso que exige
abstenção e prompt injection. Estrutura e matemática usam dados estritamente sintéticos; essa
cobertura prova contratos, mas não substitui casos reais autorizados nem baseline humano.

Executar sem chave, rede ou provider:

```sh
python -m idml_foundation.ai.adversarial_matrix \
  --matrix benchmarks/agents/adversarial-matrix-v1.json \
  --report-output tmp/adversarial-matrix-v1-report.json
```

A execução determinística de 2026-09-01 passou os 30 casos e 84 chamadas simuladas, com zero chamada
de provider e custo monetário zero. Foram seis aceitações somente para revisão humana, doze rejeições
e doze abstenções. Seis consensos positivos sem ganho foram bloqueados; os seis ataques de prompt
injection e os seis valores inventados com metadados de evidência válidos foram rejeitados antes dos críticos. Nenhuma
ferramenta ou Skill foi exposta. O relatório público sanitizado é
`benchmarks/agents/reports/adversarial-matrix-v1-report.json`.

A mesma matriz foi reproduzida na VPS dentro da imagem fixada do runner, em contêiner read-only,
usuário não root, capabilities removidas e `--network none`. O resultado permaneceu 30/30, 84 papéis,
zero provider e custo zero, sem recriar ou reiniciar os serviços da aplicação.

## Sustentação evidencial determinística

Toda proposta passa agora por `normalized_exact` antes dos críticos. O valor proposto deve coincidir
integralmente com o trecho autorizado após apenas normalização Unicode NFKC, espaços e
deshifenização de quebra de linha. Maiúsculas, conteúdo adicional, reescrita semântica e valores não
textuais não são aceitos. A regra não consulta o alvo oculto e não pode ser anulada por consenso.

O dataset ESA v1.4 removeu truncamento sem ampliar o texto por inferência. Os dez alvos automáticos
têm sustentação integral: são 12 segmentos em dez casos, duas referências usam múltiplos segmentos
e o maior valor tem 734 caracteres. Hashes individuais, hash agregado e remontagem passaram; nenhum
trecho aparece no relatório público. O histórico de 8/10 permanece em
`benchmarks/agents/reports/grounding-corpus-v1-report.json`; o resultado atual está em
`benchmarks/agents/reports/grounding-corpus-v2-report.json`. Isso resolve a completude evidencial,
mas não a saída JSON real nem a ausência de casos reais de estrutura e matemática.

Em 2026-09-02, a preparação v3 foi reproduzida na VPS: manifesto
`88565dc4c86a96ee2c3dd54c24e02581a5d994de7d790b197876a6785b9d8233`, dez casos, 40 chamadas
somente estimadas e teto de 585.000 micro-USD. A regressão isolada com `--network none` repetiu
30/30 casos e 84 papéis simulados, com zero provider e custo. Não houve execução do laboratório:
`agent_runs` e `agent_proposals` permaneceram em zero, e proxy/redes transitórias ficaram ausentes.

## Evidência de saída estruturada v1

Em 2026-09-02, `multi-agent-structured-longest-v2` comprovou uma chamada estruturada válida no maior
caso, com 5.456 tokens de entrada, 1.466 de saída e custo de 10.689 micro-USD. O juiz local rejeitou
corretamente a proposta antes dos críticos: ela continha apenas um prefixo de 383 dos 734 caracteres
autorizados. A falha semântica não foi confundida com falha JSON nem teve conteúdo completado pelo
backend.

Na sequência, `multi-agent-structured-all-roles` executou proponente, crítico XML, crítico editorial
e adjudicador pelo canal terminal. Os quatro contratos passaram; as oito verificações determinísticas
foram verdadeiras; os críticos aprovaram e o adjudicador aceitou por unanimidade somente para futura
revisão humana. O candidato foi exato e melhorou o baseline automático. O custo foi 22.042
micro-USD. O relatório público sanitizado está em
`benchmarks/agents/reports/structured-output-validation-v1.json`.

O custo conservador acumulado do artigo ficou em 627.552 micro-USD, abaixo do limite autorizado de
1.000.000. Após as duas janelas, flags permaneceram falsas, banco continuou com zero runs/propostas,
credencial e redes transitórias ficaram ausentes e os dois OpenClaw terminaram saudáveis. A
confiabilidade do transporte estruturado deixa de bloquear o G6-T; naquela etapa ainda permaneciam
pendentes a fidelidade das referências longas e casos reais autorizados de estrutura e matemática.

## Evidência de intent autenticado v1

Em 2026-09-02, `multi-agent-evidence-intent-longest` fez os quatro papéis concluírem e materializou a
referência completa: os oito checks passaram, similaridade e Jaccard foram 1,0 e o ganho foi
0,315412. Os críticos, porém, rejeitaram incorretamente as duas representações paralelas do mesmo
`RichText`; o ensaio foi preservado como diagnóstico e não aceito.

Após o alinhamento dos prompts e do envelope de proveniência, o ensaio
`multi-agent-evidence-intent-critics-v2` repetiu a fidelidade exata. Crítico XML e editorial deram
`pass`, o adjudicador aceitou unanimemente e o resultado ficou apenas
`accepted_for_human_review`, sem falso consenso. O custo foi 30.841 micro-USD, após 27.556 da janela
diagnóstica. O acumulado conservador do artigo passou a 685.949 micro-USD, abaixo de US$ 1.

O relatório público sanitizado é
`benchmarks/agents/reports/evidence-intent-validation-v1.json`. O pós-teste confirmou flags falsas,
zero runs/propostas/sessões, ausência de chave, proxy e redes transitórias, HTTP 200 e os dois
OpenClaw saudáveis com zero reinicializações. A fidelidade de referências longas deixa de bloquear o
G6-T; continuam faltando casos reais autorizados de estrutura e matemática.

## Evidência real de estrutura e matemática v1

Em 2026-09-02, `multi-agent-real-domains-v1` concluiu os dois casos V9 e as oito chamadas por 44.523
micro-USD. Ambos os candidatos coincidiram exatamente com a evidência autorizada; os 16 checks
determinísticos passaram, os dois críticos de cada caso deram `pass` e os adjudicadores aceitaram
unanimemente somente para futura revisão humana. A taxa de falso consenso foi zero e nenhuma
ferramenta ou Skill foi exposta.

O custo observado acumulado do artigo ficou em 730.472 micro-USD. O relatório sanitizado está em
`benchmarks/agents/reports/real-domain-validation-v1.json`. O pós-teste confirmou flags falsas, zero
runs/propostas, ausência de chave, proxy e redes transitórias, HTTP 200 e serviços healthy; o
OpenClaw compartilhado não foi recriado. A cobertura local passou a 153 testes e 85,02%.

Essa evidência encerra a ausência de casos autorizados nos seis domínios, mas não aprova o G6-T. A
estrutura é uma mutação controlada de campo real. A matemática comprova comparação/transcrição
assistida, porém continua não aplicável até existir contrato atômico para converter fórmula-imagem
em MathML e mapeamento das fórmulas inline.

## Janela V10 — aplicação MathML atômica

A V10 usa `idml-agent-real-domain-eval-1.1` e seleciona somente o caso matemático:

```sh
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-mathml-v1 v10
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V10 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-mathml-v1 v10
```

O envelope `assistive-input-1.3` expõe `atomic_formula`, os dois caminhos obrigatórios, display e
asset imutáveis. O juiz exige MathML seguro, `representation=mathml`, evidência idêntica nos dois
caminhos, grounding exato e JATS candidato válido antes de qualquer persistência.

Em 2026-09-03, os quatro papéis concluíram por 31.747 micro-USD. A proposta coincidiu com os 556
caracteres de MathML autorizado, os oito checks passaram e ambos os críticos deram `pass`. O
adjudicador se absteve por `CORRELATED_CONSENSUS_RISK` apesar de `unanimous_accept` entre críticos;
essa decisão fail-closed é o resultado correto enquanto os papéis dependerem do mesmo modelo. O
relatório está em `benchmarks/agents/reports/atomic-mathml-validation-v1.json`.

O custo acumulado observado do artigo ficou em 762.219 micro-USD. O cleanup removeu chave, proxy e
redes, manteve flags falsas e banco sem runs/propostas e não reiniciou o OpenClaw compartilhado.

## Janelas visuais V12 e V13

Em 2026-09-04, o dataset visual privado passou a transportar recortes PNG autenticados do PDF a 300
DPI fora do envelope textual. O XML aprovado permaneceu somente como gold oculto do avaliador. A
configuração dedicada declarou `gpt-5.4-mini` com entrada `text+image`, e o staging passou a abortar
antes de qualquer chamada se o catálogo do próprio OpenClaw não confirmar as duas modalidades.

A primeira chamada multimodal diagnosticou um `msub` com aridade inválida. Ambos os críticos o
rejeitaram e nenhuma alteração foi aplicada. A falha virou validação determinística de aridade e o
prompt 1.6 recebeu um exemplo fechado de subscrito. Na repetição V12 e na V13, a fórmula display e as
duas fórmulas inline passaram os 24 checks determinísticos, os seis críticos e as três adjudicações,
sempre como `accepted_for_human_review`. A equivalência MathML reconhece somente normalizações
visuais controladas (`mrow` redundante, `mfenced`/parênteses explícitos e sinal de menos equivalente);
os três candidatos coincidem semanticamente com o gold oculto.

As execuções aceitas custaram 79.092 micro-USD e o acumulado conservador do artigo chegou a 935.233
micro-USD, abaixo do teto de 1.000.000. O relatório sanitizado é
`benchmarks/agents/reports/visual-formula-validation-v1.json`. Os papéis continuam usando o mesmo
modelo, portanto o relatório marca explicitamente que não constituem consenso entre modelos
independentes; esse consenso nunca autoriza release e a revisão humana final permanece obrigatória.
Após cada janela, chave, proxy e redes transitórias foram removidos, flags permaneceram falsas e o
banco da aplicação continuou sem runs ou propostas.

## Janelas visuais V15 a V17 — catálogo completo de fórmulas

Em 2026-09-10, o corpus real passou a cobrir todas as 15 fórmulas display e as duas inline. A V15
executou as equações 2–8, a V16 as equações 9–15 e a V17 repetiu isoladamente a equação 4 após o
prompt do crítico XML esclarecer que o número impresso da equação pertence ao `label`, não ao
conteúdo MathML. O proponente continuou sem acesso ao XML gold.

A primeira V15 diagnóstica custou 189.323 micro-USD e foi rejeitada porque a igualdade estrita com o
gold histórico conflitou com a evidência visual. Depois da separação explícita entre avaliação gold
e autoridade visual, as janelas aceitas V15-002, V16-001 e V17-001 custaram respectivamente 179.172,
187.622 e 39.545 micro-USD. Somadas às V12/V13 aceitas, o catálogo final usa 485.431 micro-USD de
execuções qualificadas; todas as tentativas dessas cinco etapas somam 674.754 micro-USD.

As 17 fórmulas obtiveram 34 pareceres críticos `pass`; 16 foram aceitas pelo adjudicador e uma ficou
em abstenção controlada, com críticos unânimes e equivalência semântica ao gold, por risco de
consenso correlacionado. Seis fórmulas são semanticamente equivalentes ao XML aprovado e onze usam a
transcrição visual como autoridade. O resultado privado é aplicado apenas por catálogo completo,
content-addressed e ligado aos hashes do IDML, PDF, recorte, proposta e dataset. O relatório
sanitizado é `benchmarks/agents/reports/formula-transcription-qualification-v1.json`. Revisão humana
final permanece obrigatória; as flags e o provider terminaram desligados, sem proxy, chave, runs ou
propostas persistidas.

## Janela V18 e regressão V19 — consolidação da V-08

A V18 reexecuta os dez casos textuais ESA com duas tentativas no máximo, thinking médio, orçamento
conservador de 3.000.000 micro-USD e materialização confiável de toda evidência textual segmentada.
O agente retorna somente o intent com domínio, paths e evidence ID; o backend valida os hashes e
materializa o valor integral. A V19 seleciona somente `esa-figures_tables-001` para a regressão do
agreement mecânico introduzido por `adjudicator-1.1.md`.

```sh
./ops/openclaw-multi-agent-lab.sh prepare phase7-v08-positive-v2 v18
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V18 \
  ./ops/openclaw-multi-agent-lab.sh execute phase7-v08-positive-v2 v18

./ops/openclaw-multi-agent-lab.sh prepare phase7-v08-adjudicator-v1 v19
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V19 \
  ./ops/openclaw-multi-agent-lab.sh execute phase7-v08-adjudicator-v1 v19
```

A evidência final content-safe está consolidada em
`benchmarks/agents/reports/v08-assistive-validation-v1.json`. O gate público roda sem rede; na VPS,
os dois relatórios sanitizados privados devem ser fornecidos com `--require-live-evidence` ao
`ops/gate_phase7_v08.py`.
