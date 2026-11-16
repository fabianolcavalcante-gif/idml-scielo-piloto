# Ativação controlada do provider OpenClaw

Data: 2026-09-01. Estado operacional: **desligado após benchmark controlado**.

## Finalidade e fronteira

Este procedimento prepara a rota do modelo sem habilitar a aplicação. O Compose base mantém o
gateway dedicado sem chave e apenas na rede interna. O overlay
`deploy/docker-compose.openclaw-provider.yml` adiciona temporariamente:

- `OPENAI_API_KEY` somente ao `openclaw-idml`, a partir de `IDML_OPENAI_API_KEY` no `.env` modo 600;
- `NODE_USE_ENV_PROXY=1` e `HTTPS_PROXY` somente ao gateway durante a janela;
- rede interna exclusiva entre gateway e proxy;
- Squid read-only, sem capabilities ou porta publicada;
- rede de egress presente somente no proxy;
- allowlist exata de `api.openai.com:443`.

API e worker não recebem a credencial. As flags `IDML_FEATURE_OPENCLAW` e
`IDML_FEATURE_AI_SWARM` permanecem falsas. O staging não acessa `/v1/responses`, não autentica na
OpenAI e não cria sessão, run ou proposta.

## Staging sem inferência

Pré-condições: `.env` modo 600 com `IDML_OPENCLAW_GATEWAY_TOKEN` e `IDML_OPENAI_API_KEY`; não
imprimir nem renderizar esse arquivo. Executar:

```sh
cd /opt/idml-platform
ops/openclaw-provider-stage.sh
```

O script valida configuração e Compose sem exibir segredos, constrói o proxy e confirma:

1. API/worker sem `OPENAI_API_KEY` e flags falsas;
2. gateway e proxy saudáveis e sem portas publicadas;
3. gateway apenas nas redes internas; somente o proxy possui rede de egress;
4. túnel TCP permitido para `api.openai.com:443`, sem autenticação ou requisição de inferência;
5. túnel para domínio fora da allowlist recusado com 403;
6. conexão direta do gateway ao provider bloqueada;
7. zero sessões OpenClaw.

O comando prepara conectividade, mas não autoriza isoladamente testes de agentes nem produção.

## Kill switch

Desligar imediatamente com:

```sh
cd /opt/idml-platform
ops/openclaw-provider-disable.sh
```

O script recria o gateway com o Compose base, remove o proxy e as redes de provider, confirma a
ausência da chave no gateway e exige zero sessões. A chave permanece armazenada no `.env`, mas não
fica anexada a nenhum contêiner IDML.

## Ativação futura de agentes

Exige protocolo separado, janela observada e autorização explícita. Antes da primeira inferência:

- registrar corpus/casos e critérios de comparação;
- criar backup e executar restore test;
- fixar limites monetários, tokens, concorrência 1 e timeout;
- confirmar zero runs/propostas e capturar métricas iniciais;
- executar primeiro caso sem release automático;
- desligar pelo kill switch ao exceder orçamento, ocorrer erro de schema, egress inesperado ou
  impacto na VPS.

A primeira janela autorizada foi executada em 2026-09-01 e está documentada no relatório sanitizado.
O gate técnico G6-T depende agora de ganho mensurável e cobertura multiagente; a homologação humana
obrigatória ocorrerá no G8-H, após a RC completa e antes da produção.

O harness da primeira janela está descrito em `docs/OPENCLAW_CONTROLLED_BENCHMARK.md`. A preparação
desse harness não autoriza novas execuções: o comando exige confirmação transitória explícita e
encerra sempre com o kill switch e reset do estado dedicado.

O laboratório com proponente, dois críticos e adjudicador está descrito em
`docs/OPENCLAW_MULTI_AGENT_LAB.md`. Ele mantém sessões independentes, oculta o alvo automático dos
agentes e submete qualquer consenso ao juiz determinístico local.

A janela v2 executou os dez casos ESA disponíveis com custo de 218.200 micro-USD e terminou pelo
kill switch. Nove casos foram rejeitados de forma fechada por saída não JSON. O estado final manteve
flags falsas, zero runs/propostas/sessões, gateway sem chave do provider e redes transitórias
ausentes. O token do gateway dedicado foi rotacionado depois da auditoria e os três serviços do
projeto voltaram saudáveis; o OpenClaw compartilhado permaneceu saudável e não foi reiniciado.

## Evidência da primeira janela — 2026-09-01

O modo de proxy explícito na configuração do provider causou timeout upstream tanto no OpenClaw
fixado quanto em uma versão estável candidata. A conectividade, a chave e o modelo foram validados
separadamente. O transporte foi corrigido para o proxy nativo por variáveis de ambiente do Node,
mantendo o Squid allowlist como único ponto de egress e preservando `allowPrivateNetwork=false`.

A janela final concluiu dois casos com custo contabilizado de 13.024 micro-USD, resposta válida e
revisão humana obrigatória. O kill switch removeu chave, variáveis de proxy, contêiner e redes de
provider; o gateway dedicado foi recriado com zero sessões. O resultado bruto permanece privado.

## Evidência de 2026-08-28

O staging foi executado duas vezes de forma reprodutível. Modelo catalogado:
`openai/gpt-5.4-mini`. Os testes observaram 200 para o túnel permitido, 403 para domínio negado e
falha da saída direta. Gateway/proxy permaneceram healthy; o health check não gerou ruído; banco e
estado ficaram com zero sessões, runs e propostas. Nenhuma chamada autenticada ou inferência foi
feita.

O kill switch foi testado e deixou proxy/duas redes ausentes, gateway saudável apenas em
`idml_development_openclaw` e nenhuma chave em gateway/API/worker. O OpenClaw compartilhado ficou
healthy, com zero reinicializações. O backup pós-teste
`/opt/idml-platform/backups/20260828T202601Z` passou checksums e restore isolado com 21 tabelas, um
artefato e 14 arquivos de estado OpenClaw.
