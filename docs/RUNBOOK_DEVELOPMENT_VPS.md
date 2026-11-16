# Runbook — ambiente de desenvolvimento na VPS

## Localização e isolamento

- diretório: `/opt/idml-platform`;
- Compose project: `idml-development`;
- rede interna: `idml_development_internal`;
- volumes: `idml_development_postgres`, `idml_development_redis`, `idml_development_artifacts`;
- API: `127.0.0.1:18080`; não publicar externamente.

## Subir/atualizar

```bash
cd /opt/idml-platform
docker compose --env-file .env -f deploy/docker-compose.dev.yml config --quiet
docker compose --env-file .env -f deploy/docker-compose.dev.yml build
docker compose --env-file .env -f deploy/docker-compose.dev.yml up -d
ops/verify-stack.sh
```

O serviço `migrate` precisa terminar com sucesso antes de API/worker. Não use `docker system prune`.
Em atualização rotineira, não use `--force-recreate` sobre toda a stack: recrie
somente `migrate`, `api`, `worker` e inicializadores necessários. PostgreSQL e
Redis só devem ser recriados em manutenção planejada, preservando os volumes.

## Verificar

```bash
docker compose --env-file .env -f deploy/docker-compose.dev.yml ps
curl --fail http://127.0.0.1:18080/health/ready
docker compose --env-file .env -f deploy/docker-compose.dev.yml logs --tail=100 api worker
```

## Backup e restore

```bash
backup_dir=$(ops/backup.sh)
ops/restore-test.sh "$backup_dir"
```

Os scripts carregam `/opt/idml-platform/.env` sem imprimir seu conteúdo. Backups
ficam fora dos volumes Docker, em `/opt/idml-platform/backups`, modo 600 e com
SHA-256. Restore de produção exige janela, aprovação e destino novo; nunca
sobrescrever banco ativo durante teste.

O timer `idml-development-backup.timer` executa o backup diariamente às 04:40 no
fuso `America/Sao_Paulo`, com atraso aleatório de até 10 minutos. Verifique com:

```bash
systemctl status idml-development-backup.timer
systemctl status idml-development-backup.service
```

## Incidentes

1. registrar horário e correlation/job ID sem copiar secrets;
2. verificar health, `docker stats --no-stream`, disco e eventos OOM;
3. pausar entrada de novos jobs antes de reiniciar worker;
4. preservar banco, volumes e logs;
5. rollback de imagem por tag anterior; migrations destrutivas são proibidas sem plano expand/contract;
6. testar restore em banco alternativo.

## Fase 4 — validadores externos

O runtime principal contém apenas validação offline e contratos da Fase 4. O
Packtools/SPSValidator roda em ambiente isolado. Atualização 2026-10-15: o XPM
oficial executou headless em container Linux na mesma VPS (ADR-002 revisada),
sem Windows; integração ao worker ativo e compatibilidade continuam pendentes.
Ausência de executor/relatório válido produz `VALIDATION_UNAVAILABLE`, nunca sucesso.

Exceção autorizada ao bloqueio histórico de corpus abaixo: somente fontes e
derivados abrangidos por `authorizations/VH1_VPS_DATA_20261001.md` podem permanecer
na área privada `/opt/idml-platform/private`, sem exposição pública. O ensaio XPM
usa essa autorização e a de instalação recebida em 2026-10-15. Relatórios HTML
contêm conteúdo do artigo; não servi-los publicamente nem como HTML irrestrito
na origem autenticada da aplicação. Evidência: `VH1_XPM_LINUX_QUALIFICATION.md`.

Não copie IDML, PDF, XML real, assets, relatórios XPM ou ZIP candidato para
`/opt/idml-platform`. Smoke tests na VPS usam apenas o IDML sintético dos testes. Benchmarks
explicitamente autorizados podem usar somente fragmentos minimizados em
`benchmarks/private`, modo 600; respostas brutas permanecem privadas e apenas métricas
sanitizadas podem ser versionadas.
Rollback da aplicação permanece pela tag anterior (`phase3`).

## Fase 5 — identidade e revisão humana

`IDML_MFA_ENCRYPTION_KEY` é obrigatório no Compose, deve conter segredo aleatório
independente do session pepper e permanecer modo 600 em `.env`. Não imprimir a
chave em verificações; validar somente presença/comprimento. A rotação exige
procedimento próprio porque os segredos TOTP persistidos dependem dela.

A UI permanece acessível somente pelo bind loopback da API. Antes de exposição
pública, adicionar proxy TLS e rate limiting distribuído. A aprovação de duas
pessoas resulta em `editorially_approved` e não substitui a Release Policy nem
concede `READY_FOR_SCIELO`.

Na atualização da Fase 5, preservar a tag `phase4`, executar backup/restore test,
aplicar a migration `c4e5f6a7b8c9` e recriar somente `api` e `worker`. A migration
é aditiva e a imagem anterior pode ser usada para rollback da aplicação enquanto
se investiga um incidente.

## Fase 6 — gateway dedicado com IA desativada

A fundação da Fase 6 deve operar com `IDML_FEATURE_OPENCLAW=false` e
`IDML_FEATURE_AI_SWARM=false`. Não conectar o agente pessoal existente ao conteúdo de artigos. O
agente dedicado `idml-evaluator` é exclusivo para avaliação offline, sem bindings, Skills ou
ferramentas efetivas. Uma ativação futura exige plugin de ferramentas tenant-bound, atestação
completa, custo observável e benchmark real aprovado no Gate G6.

O custo segue `docs/AGENT_COST_POLICY.md`; a integração segue
`docs/OPENCLAW_GATEWAY_INTEGRATION.md`. O catálogo deve expor somente o modelo exato verificado.
Nunca preencher preço por aproximação de família ou alias: modelo divergente ou sem tarifa deve
falhar fechado.

Não conectar API/worker ao OpenClaw compartilhado do Mapalead. O serviço `openclaw-idml` usa imagem
fixada por digest, estado próprio, token aleatório próprio e somente a rede interna
`idml_development_openclaw`. O token deve existir em `.env`, com modo 600, mas nunca deve ser
impresso. As duas flags continuam falsas; no Compose base o gateway permanece sem provider key e
sem egress.

Antes de subir o Compose pela primeira vez, gerar o segredo na própria VPS:

```sh
umask 077
printf 'IDML_OPENCLAW_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)" >> .env
```

Validar sem chamar o endpoint de agentes:

```sh
docker compose --env-file .env -f deploy/docker-compose.dev.yml exec -T openclaw-idml \
  node openclaw.mjs config validate --json
docker compose --env-file .env -f deploy/docker-compose.dev.yml exec -T openclaw-idml \
  node -e "fetch('http://127.0.0.1:47716/readyz').then(r=>process.exit(r.ok?0:1))"
```

O backup pausa brevemente apenas `openclaw-idml`, arquiva o volume consistente, retoma o serviço e
aguarda health saudável. O restore test verifica checksum, presença da configuração e
`PRAGMA integrity_check` do SQLite. Confirmar `agents.defaults.heartbeat.every=0m` e o mesmo valor no
agente dedicado. Não usar `/v1/responses` em smoke enquanto o provider estiver desabilitado.

Em deploy, validar dentro da imagem que `load_registry()` encontra seis perfis e que todos os
prompts carregam. Validar também `load_pricing_catalog()`, executar backup/restore, aplicar a
migration `f7b8c9d0e1f2` e recriar somente API
e worker. Preservar `phase5` como rollback da aplicação; a migration é aditiva e pode permanecer
enquanto um incidente é investigado. Confirmar zero `agent_runs`/`agent_proposals` e zero sessões
OpenClaw enquanto as features estiverem desabilitadas.

### Staging controlado do provider, sem agentes

O procedimento completo está em `docs/OPENCLAW_PROVIDER_ACTIVATION.md`. A chave reutilizada por
autorização do usuário fica somente em `IDML_OPENAI_API_KEY` no `.env` modo 600. Não copiá-la para o
JSON, a aplicação, comandos de diagnóstico ou logs.

Preparar a rota, mantendo flags falsas e sem acessar `/v1/responses`:

```sh
cd /opt/idml-platform
ops/openclaw-provider-stage.sh
```

Desligar e remover imediatamente chave, proxy e redes do runtime IDML:

```sh
cd /opt/idml-platform
ops/openclaw-provider-disable.sh
```

Ao terminar qualquer diagnóstico, deixar o estado desligado e confirmar zero sessões,
`agent_runs` e `agent_proposals`.

### Laboratório multiagente controlado

O procedimento completo está em `docs/OPENCLAW_MULTI_AGENT_LAB.md`. Ele usa quatro sessões isoladas,
não envia o alvo esperado aos agentes, não aplica patches e mantém revisão humana obrigatória.

Validar sem inferência:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-first-window
```

Em uma janela já autorizada, executar com a confirmação transitória exata:

```sh
cd /opt/idml-platform
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V1 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-first-window
```

Para os dez casos ESA disponíveis, selecionar explicitamente a versão v2:

```sh
cd /opt/idml-platform
./ops/openclaw-multi-agent-lab.sh prepare multi-agent-full-corpus v2
IDML_CONFIRM_AGENT_EXECUTION=RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V2 \
  ./ops/openclaw-multi-agent-lab.sh execute multi-agent-full-corpus v2
```

Falha de contrato de saída rejeita o caso e contabiliza o limite superior preflight do papel. Falha
operacional ou de política interrompe a janela. Em ambos os casos o encerramento executa o kill
switch e o reset do estado dedicado.

O encerramento, inclusive em erro, deve executar `ops/openclaw-provider-disable.sh`. Não copiar a
saída bruta para documentação ou logs públicos; publicar somente o relatório sanitizado.

### Marco 7C-08 — 2026-09-21

API/worker usam `idml-foundation:phase7-7c08-v1`; o `.env` foi sincronizado com esse tag.
O rollback real para `phase7-v11-robustness-v1` e a reaplicação passaram. Não há migration nova.
Backup restaurado em teste: `/opt/idml-platform/backups/20260921T121706Z`.
Arquivos operacionais preservados: `/opt/idml-platform/releases/phase7-7c08-v1/`.

`ops/build_phase7_7c08_source.py` gera um arquivo allowlisted, sem corpus privado; `.dockerignore`
exclui também cópias de segredos, backups e arquivos compactados do contexto de build.
`ops/deploy_phase7_7c08.sh` registra as ações prepare/build/qualify/activate deste marco.
Ele é específico dessa transição: não repetir `prepare` ou `activate` numa instalação já atualizada.
Para conferir o estado atual sem mutação, executar `python3 ops/phase7_7c08_vps.py after`.

O pós-check exige 282 arquivos de runtime idênticos às fontes qualificadas, cinco serviços
saudáveis, flags falsas, ausência de credencial no gateway, zero sessões/runs/propostas e ausência
de redes de provider. Os demais serviços devem conservar IDs, início e contadores de reinício.
Ver `docs/PHASE_7C08_REQUALIFICATION.md` para evidências, limitações e preparação da V-12.

### Benchmark controlado

Seguir `docs/OPENCLAW_CONTROLLED_BENCHMARK.md`. O modo padrão é somente preparação:

```sh
cd /opt/idml-platform
ops/openclaw-controlled-benchmark.sh prepare controlled-first-window
```

Ele deve deixar proxy e redes de provider ausentes, gateway sem chave, flags falsas e zero sessões,
runs e propostas. O modo `execute` é bloqueado sem confirmação explícita na mesma invocação. A
primeira janela foi concluída em 2026-09-01; qualquer nova janela deve manter os mesmos limites,
produzir relatório sanitizado e terminar pelo kill switch.

### Atualização intermediária VH-09 — 2026-10-20

Estado histórico de 20/10, substituído pelo checkpoint de 22/10 abaixo: API/worker em
`idml-foundation:vh09-20261020-v1`, banco em `b9d0e1f20314`. Flags IA desligadas.
Não é RC final nem liberação de homologação. Não reexecutar o script de pós-check
7C-08 contra esta imagem: a lista/hash de runtime desse marco antigo é histórica.

Backup restaurado em banco isolado:
`/opt/idml-platform/backups/20261020T183258Z`.
Registros sanitizados em `/opt/idml-platform/releases/vh09-20261020-v1/`:
`deployment.json`, `qualification.json`, `linux-tests.log`, `postgres-tests.log`.
Retorno real à imagem `phase7-7c08-v1` e reaplicação comprovados. Contagens dos
dados existentes e demais serviços preservados. Nenhum backup foi apagado.

`ops/build_vh09_source.py` normaliza permissões do arquivo allowlisted para
0644/0755; o pós-check exige fontes não graváveis pelo usuário da aplicação.
`ops/deploy_vh09.py` é específico dessa transição, não um atualizador recorrente:
**não repetir prepare/activate nesta instalação já atualizada**. Para a próxima
implantação, usar novo identificador, novo backup e manifesto correspondente.
`ops/qualify_vh09_postgres.py` ensaia migração/concorrência em banco descartável,
nunca usando dados ativos como fixtures. A imagem de qualificação contém
dependências de testes que não são acrescentadas ao runtime de produção.

Rollback operacional conserva as tabelas aditivas: não executar downgrade no
banco ativo. Não confundir rollback de imagem com restauração de artigo.
Ambiente privado de recuperação contém segredos: não imprimir nem anexar.
Detalhes, hashes e lacunas: `VH09_REVALIDATION_HISTORY_AND_DEPLOY.md`.

### Estado ativo — VH-09, linhagem de trabalho, 2026-10-22

API/worker: `idml-foundation:vh09-heads-20261021-v1`; banco: `c0e1f2031425`.
A release foi preparada/qualificada em 21/10 e ativada em 22/10. 324 arquivos de
runtime conferidos por hash e não graváveis pelo UID da aplicação. Cinco serviços
IDML saudáveis; contagens dos dados e demais serviços preservados. Flags IA falsas,
sem credencial de provider na API/worker. Continua versão intermediária, não RC.

Backup novo antes da ativação: `/opt/idml-platform/backups/20261022T120540Z`,
com restauração isolada aprovada (26 tabelas, um arquivo de artefato e 14 arquivos
de estado OpenClaw). Backup de preparação de 21/10 e backups anteriores mantidos.
Nenhum banco ativo foi restaurado/substituído pelo ensaio.

Evidências em `/opt/idml-platform/releases/vh09-heads-20261021-v1/`:
`deployment.json`, `qualification.json`, `preactivation-20261022.json`,
`postcheck-20261022.json`, `linux-tests.log` e `postgres-tests.log`.
`source.tar.gz` e seu manifesto permanecem congelados; atualizações documentais
de fechamento ficam no checkout `/opt/idml-platform`, não dentro da release.
Arquivos de recuperação `rollback.env` e `rollback-source.tar.gz`: modo 0600;
não abrir, imprimir ou compartilhar seu conteúdo como evidência pública.

`ops/deploy_vh09_heads.py` é específico dessa transição já concluída: **não repetir
prepare/activate**. O rollback real à imagem de 20/10 foi testado antes de existir
qualquer evento em `canonical_head_events`. Após transições de linhagem, uma
imagem antiga que ignora essa tabela não é rollback seguro: manter imagem que
entenda o seletor atual ou qualificar recuperação específica. Nunca fazer downgrade
do banco ativo nem apagar eventos para permitir o retorno da imagem antiga.

Smoke: `/health/ready` e `/app` 200, `/v1/resources` sem autenticação 401, CSP e
nosniff presentes. Não é E2E autenticado, aprovação XML ou G-HOMOLOG. Estado e
limites funcionais em `VH09_CANONICAL_HEAD_AND_RESTORE.md` e seção 37 do plano VH1.
Registro consolidado: `benchmarks/qualification/reports/vh09-head-vps-v1.json`,
incluindo os 2.654 testes locais aprovados e 90,04% de cobertura de linhas.

### Estado ativo — worker/validadores, 2026-10-30

API/worker: `idml-foundation:vh10-worker-20261030-v1`; banco `d1f203142536`.
Este registro substitui os estados ativos históricos acima. Dois brokers systemd:
`idml-validation-modern-vh1.service` e `idml-validation-xpm-vh1.service`.
Fontes fixadas em `/opt/idml-platform/releases/vh10-worker-20261030-v1`.
Estado privado em `/var/lib/idml-validation-vh1` (0700), sem grants reais instalados.
Detalhes, recuperação testada e limites: `VH10_WORKER_VALIDATION.md`.

Para manter a configuração de validadores, comandos Compose devem incluir os
dois arquivos; usar apenas o Compose base removeria a conexão do worker:

```sh
cd /opt/idml-platform
docker compose --env-file .env -f deploy/docker-compose.dev.yml -f deploy/docker-compose.validators.yml ps
systemctl is-active idml-validation-modern-vh1.service idml-validation-xpm-vh1.service
```

Reinício via systemctl preserva o diretório montado no worker. A limpeza inicial
aceita apenas socket root:10001 no caminho fixo; não substituir arquivos manualmente
nem abrir permissões. Reinício após SIGKILL/reconexão comprovados. Os serviços têm
limites e retenção finita de execuções; incorporar backup/gestão dessa área privada
no fechamento operacional antes do piloto. Não usar grants do laboratório como
autorização da empresa real. Falta fonte autorizada => validação indisponível.

Backup pré-migração: `/opt/idml-platform/backups/20261030T115545Z`; restore isolado
aprovado. Rollback/reaplicação de imagem testados, mantendo a migração aditiva.
Não executar downgrade no banco ativo. Driver desta transição não deve ser
reexecutado como atualizador genérico. Manifesto/arquivo fonte congelados; docs
de fechamento no checkout ativo. IA desativada, homologação ainda não liberada.

### Estado ativo — fontes públicas por artigo, 2026-10-30

API/worker: `idml-foundation:vh10-sources-20261030-v1`; banco `e2f314253647`.
Substitui o estado ativo anterior desta data. Ambos os brokers apontam para a nova
release congelada e possuem `runtime_article_authorization=true` nos registros
administrativos. A API não recebe socket Docker; os brokers consultam o resolver
fixo no container da API. Nunca tornar esse destino um campo de requisição.
Comandos Compose continuam exigindo `docker-compose.dev.yml` e
`docker-compose.validators.yml`, conforme instruções acima.

Uso: entrar como administrador → Fontes públicas → selecionar artigo já convertido
no perfil qualificado → autorizar/renovar por 7/30 dias; depois gerar novo pacote.
Revogação é imediata para novas execuções e conferida antes de aceitar uma execução
em andamento. Operadores apenas consultam o estado. Nenhuma decisão real foi criada
pelo deployment. Consultas não autorizam editar conteúdo ou publicar XML.

Backup: `/opt/idml-platform/backups/20261030T175647Z`; restore isolado e
rollback/reaplicação de imagem comprovados. Não fazer downgrade no banco ativo.
O rollback à imagem anterior foi exercitado antes de habilitar o novo resolver;
depois da habilitação, uma API sem esse módulo faz os brokers recusarem consultas.
Restaurar versões compatíveis da API e dos brokers; não desativar a conferência de
consentimento como recuperação. Backups de units/registries no diretório da release
(`previous-broker-*.bin`, privados). Não repetir o driver específico desta transição.

Retenção/backup da área privada continua tarefa de VH-14/15 antes do piloto; limites
recusam novas execuções sem apagar evidências. Detalhes, testes e hashes na seção 53
do plano e `VH10_ARTICLE_PUBLIC_SOURCES.md`. IA desativada; não liberado ao especialista.

## Implantação de 31/10 — evidências da conversão e pacotes reconstruídos

API e worker executam `vh10-evidence-20261031-v1`. Os brokers continuam na fonte congelada `vh10-sources-20261030-v1` com consentimento obrigatório. Usar ambos os arquivos Compose. A migração continua `e2f314253647`. O backup `/opt/idml-platform/backups/20261031T170719Z` passou por restore isolado. O rollback de imagem e a reaplicação foram verificados com a fila livre.

Para consultar um resultado novo, abrir o Dashboard de jobs, selecionar **Diagnóstico de validação** no job de conversão e procurar **Evidências do IDML para correção automática**. O painel informa quantos vínculos foram encontrados e recusados. Jobs históricos anteriores à implantação podem não ter esse registro. A preparação não executa o agente e não concede autorização de edição.

O relatório `vh10-worker-evidence-v1.json` identifica a imagem, os testes e os ensaios isolados. A seção 54 do plano VH1 registra os critérios de varredura, vínculo de figuras e autorização para a próxima etapa. Arquivos dos ensaios permanecem somente no diretório privado de qualificação da VPS.

## Varredura de entradas na VPS

O socket privado `/run/idml-clamav-vh1/scan.sock` é criado pelo systemd. O serviço de cada conexão aceita o UID 10001 e a API verifica o UID do servidor. Só a API precisa montar esse diretório. O worker recebe o resultado persistido pela API e verifica os hashes ao montar o pacote. Os serviços continuam usando os dois arquivos Compose de desenvolvimento e validadores.

Para verificar o estado, executar `systemctl status idml-clamav-vh1.socket idml-freshclam-vh1.timer`. Para atualizar as assinaturas antes do horário diário, usar `systemctl start idml-freshclam-vh1.service`. Consultar o resultado em `journalctl -u idml-freshclam-vh1.service`. As assinaturas oficiais ficam no volume `idml_vh1_clamav_signatures`. Atualização e leitura do motor compartilham uma trava. Em caso de indisponibilidade, normalizar o serviço e repetir **Verificar arquivo** no portal. A quarentena exige investigação administrativa.

Os arquivos de unidade e configuração estão em `deploy/idml-clamav-vh1.socket`, `deploy/idml-clamav-vh1@.service`, `deploy/idml-freshclam-vh1.service`, `deploy/idml-freshclam-vh1.timer` e `deploy/idml-freshclam.conf`. Os serviços apontam para a release congelada `vh10-scan-20261031-v1`. O digest da imagem oficial é fixado tanto no broker quanto no atualizador. Em uma reinstalação, baixar esse digest e inicializar o volume a partir da imagem oficial com as bases antes de iniciar a unidade de atualização. Instalar as unidades no systemd, recarregar, habilitar o socket e o timer e executar uma atualização. Verificar o socket (root, grupo numérico 10001, modo 0660), o teste EICAR e um arquivo limpo antes de usar a configuração Compose da release.

O limite global do upload também se aplica à releitura de históricos. Esperar a varredura em andamento terminar antes de repetir um pedido que recebeu 503. A base é verificada em cada invocação. A política de aplicação exige `clamav_clean` para os arquivos do fluxo de autocorreção.

## Verificação prévia da edição por revisão

O operador pode solicitar o job `autocorrection.preflight` pelo endpoint autenticado `POST /v1/jobs`, com a permissão `JOB_CREATE` na empresa selecionada. O payload aceita `resource_id`, `canonical_snapshot_id`, `review_version` e, quando houver decisão, `authorization_id`. O diagnóstico do job informa a abstenção, a necessidade de intervenção ou a criação de um candidato que passou na validação offline. O resultado é histórico e identifica a revisão que foi examinada.

O administrador guarda as decisões em `/var/lib/idml-vh1-edit-decisions/autocorrection-authorizations/<UUID>.json`. Só o worker monta o diretório e tem acesso de leitura. A API e os agentes não podem criar essas decisões. Manter os diretórios como root:10001, modo 0750, e os registros como root:10001, modo 0640. Para instalar ou revogar, gravar o JSON em arquivo temporário protegido no mesmo diretório e substituir o destino por renomeação atômica.

Usar o contrato `RevisionEditAuthorization`, versão `autocorrection-batch-authorization-2.0`. A decisão identifica empresa, recurso, ID e SHA-256 do snapshot, revisão editorial, SHA-256 do IDML, perfil ESA 1.1 e SHA-256 do catálogo recalculado. Os hashes de conteúdo e catálogo vêm do resultado `field_evidence` da conversão. O ID e a versão editorial precisam corresponder ao estado corrente do artigo. Registrar a evidência administrativa que originou a decisão e seu SHA-256, o destino `vps`, o estado e as datas com fuso horário. O período máximo entre coleta e vencimento é de 30 dias. Para revogar, substituir o registro mantendo os identificadores e usando `status=revoked`. Uma revisão editorial posterior exige outra decisão.

O ensaio do especialista deverá usar decisões específicas para o corpus autorizado. O ensaio de desenvolvimento cria decisões temporárias apenas para o artigo sintético, em banco isolado. O comando de reprodução no release é `python3 -m ops.deploy_edit_preflight native`. Ele utiliza o ClamAV da VPS, a imagem de qualificação sem rede e os dois IDMLs do laboratório.

## Ciclo de avaliação do OpenClaw em laboratório

O ciclo VH-10 usa a imagem de qualificação da versão `vh10-edit-20261101-v2` e um banco SQLite próprio. O operador deve usar uma pasta privada nova em `/var/lib/idml-vh1-qualification`. Nela, copiar os cinco scripts de `ops/` chamados `run_vps_edit_cycle.py`, `qualify_edit_cycle.py`, `edit_cycle_lab.py`, `qualify_edit_preflight.py` e `qualify_real_edit_abstention.py`. Executar os comandos pelo mesmo usuário de administração usado nas qualificações anteriores.

1. Executar `flock -n /run/lock/idml-edit-cycle-lab.lock python3 run_vps_edit_cycle.py`. A preparação lê a afiliação no IDML sintético, verifica o IDML e o PDF e cria um candidato separado. O processo só envia ao gateway a evidência sintética e os dados necessários para conferir o campo e o hash do XML. Um arquivo `private/STOP` interrompe o ciclo na próxima verificação, inclusive após uma resposta em andamento.
2. Conferir `private/votes.json` e `disable.log`. O recibo registra papel, rodada, uso e custo em milionésimos de dólar. Uma chamada sem uso confirmado conserva a reserva no recibo. A conclusão desativa o provedor, remove a rede de saída e limpa as sessões temporárias do gateway dedicado. Os serviços web continuam com as funções de IA desativadas.
3. Conferir `controlled-result.json` e `validate-result.json`. O primeiro usa respostas formais controladas e desfaz a transação depois do ensaio. O segundo usa os validadores nativos e uma decisão de consulta pública restrita ao artigo sintético. Ao restaurar, o sistema reconstrói o pacote e compara o hash do XML com o da revisão inicial. A aprovação dos agentes autoriza apenas a tentativa de revalidação.
4. Se um validador estiver indisponível por falta de memória, aguardar o fim das varreduras e executar o mesmo comando com `--revalidate`. Essa opção utiliza o candidato e os votos preservados, cria outro diretório de resultados e mantém os limites da VPS. Executar `--real-abstention` separadamente para conferir os dois IDMLs reais em um container sem rede e com os arquivos de origem montados somente para leitura.

## Repetição do ensaio com o artigo e20240086

A qualificação usa o IDML fornecido, o XML de referência autorizado, o PDF, os cinco JPGs e a versão canônica enriquecida previamente qualificada do mesmo artigo. O manifesto do corpus fixa os hashes dos arquivos fornecidos. No laboratório, cada figura recebe o hash da sua versão publicada somente depois da conferência do nome no XML de referência e da igualdade de bytes com o ZIP qualificado. Os arquivos originais de vínculo do InDesign continuam fora desse aceite.

Preparar um diretório novo e privado de ensaio em `/var/lib/idml-vh1-qualification/vh10-reference-20261103-v2`. Em `inputs`, colocar o IDML, o XML de referência, o PDF, os JPGs e o `canonical.json` do e20240086. Em `reference`, colocar `scope.json` e `candidate.zip` da referência qualificada. Os dois diretórios são montados somente para leitura. O caminho de produção das decisões de edição deve continuar separado.

O comando da release é `python3 -m ops.deploy_reference_edit native`. O ensaio cria um banco descartável, omite o texto original de uma afiliação na cópia de trabalho e autoriza a edição somente nessa revisão. O pacote de entrada com o campo omitido tem um hash próprio. O candidato tem de reproduzir os hashes de XML e ZIP da referência completa, e a restauração tem de reproduzir os hashes da cópia anterior à correção. Os validadores emitem resultados novos para cada operação. Os quatro papéis do OpenClaw recebem apenas a evidência institucional necessária para a decisão. O botão de liberação para publicação não faz parte desse ensaio.

## Avaliação do XML pelo portal — execução restrita por revisão

Em **Avaliação do XML**, o operador seleciona artigo e revisão e usa **Iniciar avaliação**. O portal envia somente `resource_id`, `canonical_snapshot_id` e `review_version` em um job `autocorrection.evaluate`. O revisor consulta diferenças, diagnósticos e restaurações; não inicia jobs. Revisões históricas permanecem disponíveis para consulta. A tela não concede aprovação de publicação.

A execução com provedor exige, além da autorização administrativa de edição, um seletor `WebEditDecision` em `web-edit-decisions/<empresa>/<artigo>/<snapshot>/<review_version>.json`, sob o mesmo diretório privado de decisões do worker. O contrato está em `src/idml_foundation/services/web_edit_cycle.py`. Ele fixa a operação de afiliação original, modelo, autorização pai, hash do literal do IDML e ID/hash do PDF. Aplicam-se as permissões e a instalação atômica descritas acima. Não aceitar esses campos de um formulário do usuário. Cada revisão nova exige nova decisão; revogação e expiração são verificadas durante o ciclo.

`IDML_FEATURE_WEB_EDIT_PROVIDER` é falso por padrão. Sem seleção autorizada, a verificação prévia pode abster-se ou recusar a edição; com candidato e janela fechada, informa `provider_window_closed`. Não habilitar apenas a flag: a janela também exige o gateway dedicado, os sockets dos validadores e as fontes autorizadas do artigo. A API não recebe a chave do provedor. Fechar a janela e desconectar o provedor ao concluir o ensaio.

O worker registra uma reserva exclusiva em `.web-edit-runs/<empresa>/<authorization_id>` dentro da área de artefatos, antes da primeira chamada. Os checkpoints conservam votos, hashes e custo, sem o literal. Uma repetição com a mesma decisão é recusada para evitar cobrança duplicada, inclusive após falha de transação. Não apagar a reserva para forçar repetição; investigar o resultado persistido primeiro. Esse diretório integra a retenção e o backup privados de VH-14/15.

O driver `ops.deploy_web_edit` prepara uma RC com banco isolado e porta HTTP publicada apenas em `127.0.0.1:18127`. O navegador acessa a RC por túnel SSH. As contas descartáveis não pertencem ao banco ativo. O ciclo usa quatro papéis do OpenClaw, revalida o pacote, restaura a revisão incompleta e recupera a revisão íntegra. O aceite automatizado do perfil de revisor comprova a interface; não substitui o parecer de um especialista humano. Remover o container HTTP descartável antes do backup de implantação.

## Fila do scanner — 04/11

O socket aceita no máximo quatro conexões e o broker espera até 130 segundos pela trava compartilhada com o freshclam. Só uma varredura pode executar por vez. O motor mantém o limite de 850 MiB de RAM, 1.400 MiB com swap e 0,7 CPU. O recebimento é limitado a 25 segundos e 100 MiB por conexão. O cliente Unix e RuntimeMaxSec usam 300 segundos. Capacidade esgotada ou scanner indisponível continuam retornando erro; não marcar arquivos como limpos nesses casos. A admissão global de uploads da API permanece separada e pode responder 503/Retry-After quando ocupada.

As unidades ativas apontam para a release congelada vh11-scan-queue-20261104-v1. O atualizador de assinaturas continua usando a mesma trava e a configuração anterior. O driver ops.deploy_scanner_queue preserva os bytes das duas unidades anteriores em previous-idml-clamav-vh1.socket e previous-idml-clamav-vh1@.service na pasta da release. Antes de trocar unidades, aguardar as conexões ativas terminarem, interromper a admissão do socket, instalar os arquivos e executar daemon-reload/start. Em recuperação, usar os arquivos preservados e conferir um arquivo limpo antes de liberar uploads. Não remover o arquivo de trava para desbloquear um serviço.

A qualificação usa um socket systemd separado e os mesmos limites do motor. Os bancos de ensaio não pertencem à aplicação ativa. Os arquivos privados dos dois artigos permanecem montados somente para leitura. A etapa HTTP de comparação usa snapshots enriquecidos pré-qualificados e não substitui o aceite do fluxo normal com catálogos.

## Catálogos do worker e consulta dos pacotes de qualificação

O worker monta /var/lib/idml-vh1-enrichment/runtime como /run/idml-enrichment em modo de leitura, com destino vps e perfil ESA. A API serve os arquivos de avaliação pelas rotas autenticadas com escopo de empresa. O diretório authorizations contém permissões por artigo e o diretório de cada conjunto é derivado de empresa, recurso e hash do IDML. Conferir o hash do material e o da decisão administrativa antes da instalação. Para as duas amostras ESA, os utilitários collect_esa_runtime_catalog_sources, prepare_esa_runtime_catalogs e bind_esa_qualification_catalogs separam consulta, verificação dos bytes e instalação. O instalador é administrativo e exige uma autorização datada, hashes das fontes e um escopo explícito. Rodar a instalação no container administrativo como UID 0 e GID 10001 com a árvore de entrada somente leitura. As permissões de leitura do worker devem estar presentes no instante em que o diretório preparado for publicado.

O ensaio de 05/11 emitiu autorizações por dois dias. A cópia de um registro preserva a data de coleta. A renovação exige conferir a fonte e emitir uma nova decisão para o escopo correto. Depois da expiração, as saídas anteriores permanecem no histórico para consulta. Preservar concessões e versões históricas ao preparar novos artigos. O backup pareado desta entrega inclui o banco, os artefatos, a árvore de catálogos, as decisões de edição, a autoridade dos validadores, os dois registros do broker, o cofre de fontes e a coleta privada deste ensaio. Os hashes do arquivo privado integram SHA256SUMS. A restauração foi ensaiada em diretório temporário e comparou conteúdo, dono, grupo e modo de cada entrada.

Para consultar, escolher **Qualificação ESA — catálogos** no portal e abrir **Jobs**. Usar **Baixar ZIP de avaliação** no job de pacote ou **Baixar XML da conversão** no job de conversão. Os IDs dos resultados finais estão no registro operacional privado do ensaio. O acesso de revisor permite a consulta pelo proprietário. Os jobs de pacote finais começam com 47f44312 para e20240086 e 944cb7a4 para e20240135.


## OpenClaw no piloto web

A release do piloto usa a chave existente do gateway dedicado. O operador da aplicação confirma a correção em **Avaliação do XML** para cada revisão. O worker aceita somente a recuperação de uma afiliação literal comprovada no IDML e envia o trecho correspondente aos agentes. O PDF vem do último pacote concluído da mesma revisão, empresa e IDML. A confirmação identifica o usuário e expira após duas horas. A aplicação confere o vínculo ativo do usuário durante a avaliação. A revalidação formal determina se o rascunho corrigido pode virar a revisão atual.

No diretório de implantação, use `python3 ops/web_provider_runtime.py status` para consultar o serviço e `python3 ops/web_provider_runtime.py enable` para ativar ou reconciliar o piloto. O comando configura a rota do gateway, o proxy e a preferência persistente do worker. Os contêineres têm política de reinício automático. Use `python3 ops/web_provider_runtime.py disable` para interromper as novas chamadas e voltar ao gateway base. Em manutenções que recriem o gateway, preserve a composição do provedor ou execute a reconciliação. Guarde o histórico do gateway no backup privado.

Os scripts de janelas temporárias anteriores são usados nos respectivos laboratórios. Na instalação do piloto, a operação normal usa os comandos deste item e a confirmação pelo portal.
