# Integração da aplicação com o gateway OpenClaw

Data: 2026-08-28. Estado: gateway dedicado implantado; rota do provider preparada e desligada;
inferência e agentes desativados.

## Contrato escolhido

A aplicação usa o endpoint OpenResponses `POST /v1/responses`, nunca CLI interativo ou acesso ao
workspace. O cliente `OpenClawResponsesClient`:

- fixa o agente com `x-openclaw-agent-id`;
- fixa o backend `openai/gpt-5.4-mini` com `x-openclaw-model`;
- usa chave de sessão tenant-bound;
- envia envelope canônico minimizado e schema fechado;
- não segue redirects e aceita somente JSON até 2 MiB;
- força exatamente uma chamada à função terminal não executável
  `submit_idml_structured_output`, sem texto adjacente, e revalida seus argumentos pelo schema
  completo; JSON textual exato permanece apenas como compatibilidade legada;
- rejeita ausência/invalidade de usage, token negativo e cache maior que a entrada;
- não registra token do gateway nem conteúdo bruto em mensagens de erro.

O gateway não recebe ferramentas nativas ou executáveis. Ele recebe somente a função terminal de
saída estruturada, que não é executada e não concede capacidade. As leituras tenant-bound já foram
realizadas pelo backend e estão no envelope; a proposta retornada continua passando pelo schema e
pelos validadores determinísticos da aplicação.

## Uso e custo

O OpenClaw normaliza contadores OpenAI em `usage.input_tokens`, `usage.output_tokens` e
`usage.input_tokens_details.cached_tokens` quando o provider entrega esses dados. A aplicação
persiste os três contadores e calcula o custo pelo catálogo próprio, sem depender da estimativa
visual do OpenClaw.

O modelo foi fixado no registro `agent-config-1.3`. A tarifa oficial verificada está em
`agent-pricing-1.1`: US$ 0,75/M entrada, US$ 0,075/M entrada em cache e US$ 4,50/M saída. Com os
limite de 12 mil tokens de entrada e saída entre 1 mil e 4 mil por papel, cada janela calcula seu
preflight conservador antes da chamada. O agente dedicado usa 32 mil tokens de contexto operacional
para acomodar a reserva interna do OpenClaw, sem ampliar os limites monetários ou de entrada.

O preflight ocorre antes da chamada e assume zero cache. O serviço bloqueia novos runs quando a
soma append-only do artigo consumiu o teto; a linha do recurso é bloqueada na transação para evitar
duas reservas concorrentes. Custos reais de runs falhos também entram na soma quando conhecidos.

## Fronteira de segurança da VPS

O OpenClaw compartilhado do Mapalead não faz parte da integração. Segundo o contrato do gateway,
seu segredo compartilhado restaura o conjunto completo de escopos de operador, mesmo quando o
cliente pede escopos menores. A inspeção também encontrou esse segredo no comando persistido do
container legado. A rotação exige janela própria do sistema existente e não foi feita neste
incremento para evitar interrupção.

A instância `openclaw-idml` agora implementa a fronteira dedicada:

- imagem 2026.6.11 fixada pelo digest `sha256:3814fb1f62f9cfc5944de088c5817c68c88b5d721feebe36420b666a90a61ce7`;
- configuração e workspace no volume exclusivo `idml_development_openclaw_state`;
- token aleatório independente, injetado por ambiente e não gravado no JSON;
- rede `idml_development_openclaw` marcada como interna, sem egress e sem porta publicada;
- root filesystem read-only, capabilities removidas, 384 MiB, 0,35 CPU e 120 PIDs;
- somente `/v1/responses` habilitado; Chat Completions e Control UI desligados;
- único agente `idml-evaluator`, modelo fixo, sem fallback, tools/Skills/plugins/canais vazios;
- heartbeat desabilitado com `every: 0m` no default e no agente;
- nenhuma `OPENAI_API_KEY` ou outra credencial de provider.

API e worker alcançam apenas essa rede dedicada. `IDML_FEATURE_OPENCLAW=false` e
`IDML_FEATURE_AI_SWARM=false` continuam fixos no Compose. Ter URL e token configurados não autoriza
execução: o gateway também não possui rota de saída nem credencial de modelo.

O provider/egress já pode ser preparado sob controle explícito pelo procedimento
`docs/OPENCLAW_PROVIDER_ACTIVATION.md`, sem habilitar flags nem executar agentes. Antes da primeira
inferência ainda é obrigatório validar orçamento e observabilidade e aprovar um protocolo de teste. Enquanto a instância
estiver inerte, o smoke operacional deve usar apenas `/healthz`, `/readyz` e `config validate`. O
endpoint `/v1/responses` fica reservado ao protocolo controlado de ativação.

## Evidência de implantação

A imagem `idml-foundation:phase6-gateway-v1`, ID
`sha256:1bcd5223601bdbedc655aa113903adb87aabf0e8ed98c1be5c3655e2931847bd`, foi implantada com
API/worker healthy e migration `f7b8c9d0e1f2`. O smoke confirmou `agent-config-1.2`,
`agent-pricing-1.1`, modelo único `openai/gpt-5.4-mini`, preflight 18.000 micro-USD, token ausente,
flags falsas e zero runs/propostas. API e worker permaneceram apenas nas redes internas do IDML;
OpenResponses ficou desativado/ausente no gateway compartilhado.

O rollback é `idml-foundation:phase6-pre-gateway`, ID
`sha256:c6e0ef73c9e2ce9374381155460c4c04fd72246930295120c404cd880045d775`. O backup
`/opt/idml-platform/backups/20260827T204747Z` passou no restore isolado; o snapshot anterior está em
`/opt/idml-platform/backups/source-phase6-pre-gateway-20260827T204747Z.tar.gz`. OpenClaw e Mapalead
continuaram healthy, a interface respondeu HTTP 200 e o volume raiz permaneceu em 79%.

O incremento de evidência segmentada posterior atualizou o registro ativo para
`agent-config-1.3` e prompts 1.3, mantendo modelo, tarifa e flags. Em 2026-09-02, API e worker foram
implantados na imagem `idml-foundation:phase6-segmented-v1`; os gateways dedicado e compartilhado
não foram recriados e permaneceram healthy com restart zero.

## Evidência da instância dedicada

O Compose e o schema da imagem foram validados antes do deploy. Na VPS, `openclaw-idml`, API,
worker, PostgreSQL e Redis ficaram healthy; a migration permaneceu em `f7b8c9d0e1f2` e API/worker
continuaram na imagem `idml-foundation:phase6-gateway-v1`, ID
`sha256:1bcd5223601bdbedc655aa113903adb87aabf0e8ed98c1be5c3655e2931847bd`.

O teste confirmou rede interna sem egress, nenhuma porta publicada, ausência de provider key,
configuração modo 600, root filesystem read-only, token dedicado com 64 caracteres sem exibi-lo e
zero linhas em `agent_runs`/`agent_proposals`. A verificação prolongada detectou que o heartbeat
padrão do OpenClaw criava uma sessão e tentava resolver o modelo; não houve inferência ou tráfego ao
provider. O heartbeat foi desabilitado em dois níveis, seu arquivo ficou inerte e o volume novo foi
removido e recriado de forma controlada. Uma observação contínua de 105 segundos confirmou saúde,
zero sessões e zero erros de modelo.

O backup pós-deploy `/opt/idml-platform/backups/20260827T212619Z` contém banco, artefatos e estado
OpenClaw; checksums, restore isolado e integridade SQLite passaram. O snapshot anterior do código é
`/opt/idml-platform/backups/source-phase6-pre-dedicated-openclaw-20260827T210633Z.tar.gz`. O
OpenClaw compartilhado manteve o mesmo container, restart count zero e health saudável; os serviços
Mapalead permaneceram em execução. A raiz continuou em 79%, com 21 GiB livres.

## Evidência do staging controlado do provider

Em 2026-08-28 foi adicionado um overlay opt-in com provider OpenAI fixado em
`openai/gpt-5.4-mini` e proxy de ambiente do Node direcionado ao Squid allowlist. O gateway recebe a credencial somente no staging; API e
worker nunca a recebem. A rede gateway/proxy é interna e apenas o proxy entra em uma rede com
egress. A ACL aceita somente `CONNECT api.openai.com:443`; não há porta publicada.

A credencial já usada pelo OpenClaw compartilhado foi reutilizada por autorização explícita do
usuário e armazenada como `IDML_OPENAI_API_KEY` no `.env` modo 600, sem exposição. Isso não conecta
os dois gateways, mas acopla a futura rotação da credencial e está registrado no ADR-013 e no risco
R-17.

O script de staging comprovou o túnel permitido, a recusa 403 fora da allowlist e o bloqueio da
saída direta. O catálogo exibiu somente `openai/gpt-5.4-mini`; não houve autenticação na API,
inferência ou chamada a `/v1/responses`. Após observação, permaneceram zero sessões, runs e
propostas. O kill switch foi executado e o estado final ficou sem proxy/redes de provider e sem
chave em gateway/API/worker. Backup e restore passaram em
`/opt/idml-platform/backups/20260828T202601Z`.
