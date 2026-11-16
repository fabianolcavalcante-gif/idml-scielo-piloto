# Baseline do ambiente — VPS HostGator

## Registro

- Data da inspeção: 2026-08-24, fuso America/Sao_Paulo.
- Escopo: inspeção somente leitura do host, Docker, rede, backups e OpenClaw; os únicos efeitos foram containers descartáveis dos spikes da Fase 0.
- VPS: `vps-15451295.vpsbr-15451295.vpshostgator.com.br`.
- Decisão: `GO_WITH_CONSTRAINTS` para desenvolvimento inicial e piloto na VPS atual.

Nenhum segredo, token ou valor de variável de ambiente foi copiado para este documento.

## Capacidade observada

| Item | Baseline |
|---|---|
| SO | Ubuntu 22.04.5 LTS |
| Kernel/arquitetura | Linux 6.8.0-136-generic, x86_64 |
| Virtualização | KVM/OpenStack |
| CPU | 2 vCPU |
| RAM | 3,8 GiB; aproximadamente 1,3 GiB disponíveis no instante da inspeção |
| Swap | 4 GiB; aproximadamente 1,3 GiB em uso |
| Disco raiz | 98 GiB; 73 GiB usados; 21 GiB livres; 78% de ocupação |
| Inodes | 31% utilizados |
| Docker | 29.5.3 |
| Docker Compose | v5.1.4 |
| Python no host | 3.10.12 |
| Node/npm no host | não instalados; runtimes existem nos containers |

O uso de swap e a margem de disco impedem concorrência irrestrita. Desenvolvimento, validação e agentes deverão operar com limites e baixa concorrência até que medições justifiquem mudança.

## Serviços existentes

Foram encontrados 20 containers ativos, distribuídos nos seguintes projetos Compose:

| Projeto | Arquivo/escopo observado | Containers | Função |
|---|---|---:|---|
| `mapalead` | `/opt/mapalead/deploy/vps/docker-compose.yml` | 16 | aplicação, API, workers e PostgreSQL 16 |
| `mapalead-labs-evolution` | projeto isolado | 3 | Evolution API, PostgreSQL 15 e Redis 7 |
| `moltbot` | `/docker/moltbot/docker-compose.yml` | 1 | OpenClaw |

As redes Docker existentes são distintas: `mapalead_default`, `mapalead_labs_evolution` e `moltbot_default`. O novo projeto não deverá aderir a elas por padrão.

O consumo Docker observado foi:

- imagens: 52,62 GB, com 13,54 GB potencialmente recuperáveis;
- build cache: 46,05 GB, com 32,59 GB potencialmente recuperáveis;
- 13 volumes locais: 2,38 GB.

Não foi executado `docker system prune`: imagens, caches e volumes existentes pertencem aos projetos em operação e só poderão ser limpos por procedimento específico.

## Rede e exposição

- Nginx está ativo e atende `mapalead.net`, `www.mapalead.net` e `app.mapalead.net`.
- TLS é gerenciado pelo Certbot. Na inspeção, os certificados de `app.mapalead.net` e `mapalead.net`/`www.mapalead.net` estavam válidos até 2026-11-02 e 2026-11-03, respectivamente.
- Portas públicas observadas: HTTP 80, HTTPS 443 e SSH 22022.
- Portas internas de aplicações e do OpenClaw estão vinculadas ao loopback.
- UFW está inativo. A exposição efetiva depende das regras da hospedagem e dos bindings dos serviços; isso é um risco operacional a corrigir sem interromper o ambiente atual.
- Nenhum serviço do novo projeto deve publicar porta diretamente em `0.0.0.0`. A exposição futura deverá ocorrer por Nginx, TLS e autenticação.

## Persistência, backup e recuperação

- `mapalead-backup.timer` e `mapalead-backup-health.timer` estão habilitados.
- O backup diário mais recente observado em 2026-08-24 03:20 concluiu PostgreSQL, Evolution e dados de runtime.
- A verificação de saúde de 2026-08-24 09:35 retornou `ok`, sem issues.
- O relatório operacional existente `RELATORIO_BCA9_2_BACKUP_RESTAURACAO_2026_07_14.md` registra restauração aprovada no escopo local da VPS.

Essas evidências cobrem o ambiente atual. Na Fase 1 o novo projeto precisará de política, retenção e teste de restauração próprios.

## OpenClaw

| Item | Resultado |
|---|---|
| Imagem/versão | `ghcr.io/openclaw/openclaw:2026.6.11` |
| Estado | saudável |
| Binding | `127.0.0.1:47716` |
| Restart policy | `unless-stopped` |
| Volumes | configuração em `/home/node/.openclaw`; workspace em `/home/node/clawd` |
| Gateway | loopback, autenticação por token, health e configuração válidos |
| Agentes | 10 configurados |
| Sessões | 90 ativas no instante da inspeção |
| Skills | 16 de 54 prontas |
| Auditoria | 0 critical, 1 warning e 2 info |

O container executa como root, não é privilegiado, não é read-only e não possui limites explícitos de CPU/RAM. A advertência principal é ausência de `trustedProxies` caso o gateway seja colocado atrás de proxy. O próprio modelo de segurança é de assistente pessoal, não de serviço multiempresa hostil. Por isso, o novo sistema não poderá expor o OpenClaw diretamente aos usuários nem usá-lo como fronteira de autorização.

### OpenClaw dedicado ao IDML — atualização de 2026-08-27

| Item | Resultado |
|---|---|
| Imagem | 2026.6.11 fixada pelo digest `sha256:3814fb...a61ce7` |
| Serviço | `idml-development-openclaw-idml-1`, saudável |
| Rede | `idml_development_openclaw`, interna e sem porta publicada |
| Estado | volume exclusivo, configuração modo 600 e backup/restore testado |
| Limites | 384 MiB, 0,35 CPU, 120 PIDs, root filesystem read-only, capabilities removidas |
| Superfície | `/v1/responses`; UI, Chat Completions, tools, Skills, plugins e canais desligados |
| Inferência | bloqueada por flags falsas, heartbeat em `0m`, ausência de provider key e de egress |

Essa instância não reutiliza redes, volumes ou credenciais do OpenClaw compartilhado.

## Condições para coexistência

O ambiente inicial do novo projeto deverá:

1. usar diretório, projeto Compose, network, volumes, banco e Redis exclusivos;
2. ter limites explícitos de CPU, memória, PIDs, concorrência e tamanho de logs;
3. manter serviços internos no loopback ou em rede Docker não publicada;
4. usar credenciais próprias e sem compartilhamento com Mapalead/OpenClaw;
5. preservar reserva operacional para os serviços atuais;
6. monitorar RAM, swap, CPU, disco, latência e reinícios;
7. executar jobs pesados em fila com concorrência inicial igual a 1;
8. armazenar artefatos com quota e retenção;
9. não realizar upgrade automático nem limpeza global de Docker.

## Limiares iniciais para reavaliar hardware

Os valores definitivos serão calibrados na Fase 1, mas qualquer uma destas condições abre a revisão de hardware:

- memória disponível abaixo de 512 MiB ou crescimento recorrente de swap durante jobs;
- CPU sustentada acima de 80% com degradação dos serviços existentes;
- disco acima de 85% ou previsão de atingir esse valor antes da próxima janela de manutenção;
- OOM, reinícios não planejados ou filas sem cumprimento do tempo-alvo;
- impossibilidade de manter banco, fila e workers isolados com os limites mínimos.

## Higiene dos spikes

Após a captura das evidências foram removidos apenas os artefatos descartáveis criados pela Fase 0:

- `/venv` acidental e vazio;
- `/tmp/idml-packtools-*`, `/tmp/idml-sps-schema-*` e `/tmp/idml-xpm-spike-*`;
- imagens `python:3.8-slim` e `python:3.11-slim`, sem containers dependentes.

Esses itens eram reproduzíveis. Nenhum container, volume, imagem ou cache dos projetos existentes foi removido.
