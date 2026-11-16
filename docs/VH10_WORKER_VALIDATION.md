# VH-10/14 — Validadores no job de pacote

Data: 2026-10-30. Integração qualificada e implantada; ciclo IA e homologação pendentes.

O job existente `scielo.package` executa Packtools, SPS Validator e XPM sobre o
mesmo XML/ZIP e escopo de empresa/artigo/fonte/perfil. O worker constrói esse
escopo; o payload do usuário não escolhe sockets nem autoriza fontes. Erros,
indisponibilidade, avisos e consultas pendentes permanecem no diagnóstico.
Sucesso do job não significa aprovação editorial ou liberação SciELO.

A revisão humana utiliza o mesmo perfil configurado no worker. A API não recebe
socket de executor; somente o worker acessa dois sockets privados. Nenhum dos
dois recebe o socket Docker. Serviços administrativos separados executam os
validadores com as imagens já fixadas, limites de recursos e reinício automático.
O diretório do socket persiste para preservar o bind mount durante reinícios;
a limpeza de socket abandonado recusa arquivo comum, symlink e dono incorreto.

## Evidência real

`benchmarks/qualification/reports/vh10-worker-native-v1.json` registra dois jobs
reais em banco isolado, usando os canônicos e os ativos previamente qualificados.
Não é um novo ensaio de ingestão IDML, execução IA ou fluxo web completo.
Os XMLs e ativos ficaram idênticos. O ZIP ganhou a versão do validador offline no
manifesto; foram obtidas fontes públicas e autorizações laboratoriais novas,
vinculadas aos novos hashes. Relatórios do ZIP anterior não foram reaproveitados.

Packtools e SPS Validator concluíram com zero erros/críticos e cinco avisos por
ferramenta/artigo. O XPM concluiu preservando seus achados brutos; a política de
compatibilidade autorizada resolveu os erros técnicos reconhecidos, mantendo
dois/três avisos e consultas incompletas. Ambos os pacotes continuam bloqueados
para publicação. Falhas preparatórias do laboratório estão preservadas nos logs
privados: permissões, inclusão indevida do manifesto como ativo e recusa correta
de autorizações vinculadas ao ZIP anterior.

## Operação implantada

Release ativa: `vh10-worker-20261030-v1`. Etapas `prepare`, `build`, `qualify`,
instalação dos serviços e `activate` concluídas. O driver
`ops/deploy_vh10_worker.py` é específico desta transição: não repetir
prepare/activate na mesma release. Para outra atualização, criar identificador
e backup novos, preservando os dois arquivos Compose.
O instalador `ops/install_worker_validators.py --source <release congelada>`
verifica hashes e dono/permissões, recusa sobrescrever instalação existente e
cria serviços `idml-validation-modern-vh1` e `idml-validation-xpm-vh1`.

Operações Compose com os validadores precisam dos dois arquivos:

```sh
cd /opt/idml-platform
docker compose --env-file .env -f deploy/docker-compose.dev.yml -f deploy/docker-compose.validators.yml ps
```

O driver mantém backup/restore, teste da imagem anterior e reaplicação. A migração
aditiva `d1f203142536` foi aplicada sem backfill de aprovações. Os dados privados
dos brokers ficam em `/var/lib/idml-validation-vh1`, separados da aplicação.
Não apagar registros para contornar limites; política de retenção/backup dessa
área deverá integrar o fechamento operacional antes do piloto.

## Limite explícito e próxima entrega

O instalador não concede autorizações por artigo. O diretório administrativo de
autoridades começa vazio; solicitações sem fonte autorizada falham de forma
explícita. As autorizações laboratoriais não serão instaladas como autorização
de usuários reais. A integração administrativa por empresa/artigo, incluindo
renovação/revogação e catálogo editorial, ainda precisa entrar no fluxo normal.

O próximo trabalho de VH-10/14 é conectar essas fontes e os serviços de
promoção/restauração ao ciclo limitado de correção, com autorização, idempotência
e revalidação. Depois concluir VH-11–13 (fluxo web) e os ensaios finais VH-14–20.
Não criar nova fase. Os agentes continuam desativados no sistema ativo até esse
ciclo estar integrado e testado. Homologação e publicação não foram liberadas.

## Fechamento verificado

242 testes locais (25 novos), 465 Linux e ensaios isolados de PostgreSQL aprovados.
Ruff/mypy aprovados. Backup/restore e retorno real à imagem anterior/reaplicação
comprovados; 340 arquivos de runtime conferidos em cada container. 25 containers
e contagens preservados. `/health/ready` e `/app` 200, rota privada 401.
Ambos os brokers recuperaram falha SIGKILL mantendo o bind mount e a conexão do
worker; UID não autorizado recusado. Prova completa em
`benchmarks/qualification/reports/vh10-worker-deployment-v1.json`.
O manifesto e arquivo fonte da release permanecem congelados; estes textos de
fechamento ficam no checkout ativo, separados das fontes construídas.
