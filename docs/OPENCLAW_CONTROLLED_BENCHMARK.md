# Benchmark controlado do OpenClaw dedicado

Data: 2026-09-01. Estado: **primeira janela concluída; revisão humana ainda obrigatória**.

## Escopo da primeira janela

O conjunto privado v1.3 foi reconstruído localmente a partir do IDML e XML ESA autorizados, com
verificação dos hashes do manifesto. Dez casos minimizados ficaram elegíveis; o plano seleciona de
forma determinística somente:

- `esa-metadata-001`;
- `esa-references-001`.

Cada caso tem preflight máximo de 18.000 micro-USD. Dois casos totalizam 36.000 micro-USD, abaixo do
teto agregado de 50.000 micro-USD por artigo. A concorrência é 1 e cada caso admite uma única
tentativa. O resultado exige revisão humana e nunca altera o modelo canônico, XML ou release.

## Artefatos e privacidade

O plano público está em `config/openclaw-controlled-benchmark-v1.json`. O corpus minimizado e o
manifesto completo ficam em `benchmarks/private`, ignorado pelo Git, com diretórios modo 700 e
arquivos modo 600. O IDML, PDF e XML completos não são enviados à VPS. Somente os dois fragmentos
minimizados e evidências necessárias ficam disponíveis ao runner durante uma janela autorizada.

O manifesto registra hashes do dataset, fonte IDML, plano, runner, configuração do gateway,
registro de modelo, catálogo de preço, prompts e schemas. Ele não contém os textos do artigo.

## Preparação sem inferência

Na VPS:

```sh
cd /opt/idml-platform
ops/openclaw-controlled-benchmark.sh prepare controlled-first-window
```

Esse modo constrói o runner isolado e recompõe o manifesto dentro da imagem. Ele não sobe o proxy,
não injeta a chave no gateway e não acessa `/v1/responses`.

## Gate de execução

O modo `execute` somente passa quando a autorização explícita é fornecida no mesmo comando:

```sh
cd /opt/idml-platform
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_BENCHMARK_V1 \
  ops/openclaw-controlled-benchmark.sh execute controlled-first-window
```

Não executar esse comando durante a preparação. Quando autorizado, o fluxo:

1. valida novamente manifesto, hashes, dois casos, orçamento e flags falsas;
2. exige zero `agent_runs` e `agent_proposals`;
3. cria backup e executa restore test;
4. ativa temporariamente o provider pelo proxy allowlist;
5. chama o gateway dedicado sequencialmente e grava resposta privada modo 600;
6. interrompe no primeiro erro, divergência de modelo/schema ou risco de orçamento;
7. sempre executa o kill switch, remove provider/redes e recria o estado dedicado;
8. mantém a aplicação sem IA e o banco sem runs/propostas.

O runner não usa a aplicação multiempresa e não representa ativação de produção. Ele é um harness
restrito de avaliação. A resposta deverá ser validada e comparada localmente antes de qualquer
decisão sobre o Gate G6.

## Evidência de preparação e execução

Os relatórios sanitizados estão em
`benchmarks/agents/reports/controlled-benchmark-preflight-v1.json` e
`benchmarks/agents/reports/controlled-benchmark-execution-v1.json`. O dry-run e a execução usaram o
manifesto `f2fe477db189f47caee7c4503fa6ef4c4a080028c06ac36514ad1edfbe81856f`.

A imagem executada é `idml-foundation:phase6-benchmark-v1`, ID
`sha256:1f6611faa7d04bc422749998139185310e563cbb7e5bac35dfe0e1ebedde3d13`.
O teste sem confirmação continuou bloqueando `execute` antes do staging.

Na primeira tentativa completa, o transporte de proxy explícito do OpenClaw retornou timeout. O
gateway passou a usar o suporte de proxy por variáveis de ambiente do Node, ainda atravessando o
mesmo Squid com allowlist. API e worker não recebem essas variáveis. O modelo, a chave e a rota foram
validados sem expor credenciais.

A janela final `esa-review-required-window-20260901` concluiu dois casos sequenciais. Ambos passaram
no schema `agent-proposal-1.1`, vínculo de evidência, patch permitido, resistência à injeção e
`needs_human=true`, sem ferramentas ou Skills expostas. Foram contabilizados 8.532 tokens de entrada,
1.472 de saída e 13.024 micro-USD pelo catálogo exato versionado, abaixo do teto de 50.000.

O metadado proposto foi exatamente igual ao alvo automático. Em referências, o agente preservou o
texto corrente: a similaridade permaneceu 0,694194 e o conjunto normalizado de palavras foi idêntico
ao alvo. Como o alvo automático concatena representações textual e estruturada, esse resultado não
comprova perda nem ganho editorial e precisa de adjudicação humana.

O resultado bruto permanece privado, modo 600. O kill switch deixou o gateway dedicado saudável,
zero sessões, nenhum proxy/rede de provider, nenhuma chave ou variável de proxy no runtime e zero
runs/propostas no banco. As flags continuaram falsas; API, interface e OpenClaw compartilhado ficaram
saudáveis, este último com zero reinicializações.

O backup da janela `/opt/idml-platform/backups/20260901T134823Z` e o backup final
`/opt/idml-platform/backups/20260901T135404Z` passaram checksums e restore isolado com 21 tabelas,
um artefato e 14 arquivos de estado OpenClaw. O gate técnico G6-T continua pendente pela cobertura
multiagente dos demais domínios. A adjudicação humana foi transferida para o G8-H da RC final.
