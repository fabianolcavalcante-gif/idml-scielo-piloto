# V-12.2 — Quotas e margem de armazenamento definitivo

Data: 2026-09-24. Implementado na candidata; não implantado nos serviços existentes.

## Política e abrangência

Todos os caminhos de persistência usam o mesmo controle: upload de IDML, PDF/imagens,
XML gerado e pacote ZIP gerado pelo worker. Valores iniciais configuráveis por ambiente:

| Variável | Padrão |
|---|---:|
| `IDML_ARTIFACT_TENANT_QUOTA_BYTES` | 2 GiB por empresa |
| `IDML_ARTIFACT_TENANT_MAX_FILES` | 10.000 arquivos por empresa |
| `IDML_ARTIFACT_DISK_RESERVE_BYTES` | 5 GiB livres no filesystem dos artefatos |

Cada empresa tem contagem independente; o limite configurado é comum a todas. Não há ainda
tela para contratar/alterar uma quota individual. Os padrões são limites operacionais iniciais,
não capacidade de produção homologada nem promessa de retenção ilimitada.

A contagem considera bytes lógicos dos arquivos fisicamente existentes no diretório da empresa,
inclusive órfãos e temporários abandonados. Não depende de uma soma de linhas do banco, que
deixaria de contar arquivos após rollback. A caminhada tem orçamento de entradas, rejeita
links simbólicos e estruturas inesperadas; IDs de empresa devem ser UUIDs canônicos.

## Concorrência, transação e recuperação

- `.storage-budget.lock`, no volume compartilhado, serializa escritores da API e do worker.
  É uma trava não bloqueante do sistema operacional; quando ocupada, a chamada recebe 503.
- A sessão mantém a trava até o fim da transação externa: commit, rollback ou fechamento.
  Flush e savepoints não liberam a trava. Uma segunda gravação da mesma sessão pode reutilizá-la.
- Sob essa trava, a aplicação confere quota e espaço, grava em temporário, faz fsync do arquivo
  e renomeia atomicamente. O arquivo de lock é permanente: não removê-lo para liberar acesso.
- Dados idênticos não duplicam bytes/contagem. Antes de reutilizar conteúdo registrado ou órfão,
  são conferidos tamanho e SHA-256 com leitura em blocos. Conteúdo ausente/corrompido não é
  silenciosamente adotado nem sobrescrito.
- Se o banco reverter depois da publicação do arquivo, o conteúdo fica preservado e continua
  consumindo quota. Nova tentativa com o mesmo conteúdo pode recuperá-lo. Não há exclusão
  automática de órfãos: isso exige reconciliação e política de retenção posterior.
- Não se promete transação atômica entre banco e filesystem nem recuperação de queda de energia
  nesta etapa. Esses cenários integram backup/restore e continuidade. Falha da publicação remove
  o temporário sempre que o filesystem permite a limpeza.

API: quota excedida retorna 409 (`artifact_quota_exceeded`); contenção, disco insuficiente ou
indisponível retornam 503; integridade inválida retorna 409. Respostas não expõem caminhos locais.
Worker: quota/indisponibilidade geram retry com espera e limite de tentativas já existentes;
integridade gera falha permanente. O motivo fica na trilha de eventos/auditoria, mesmo quando
o estado volta para `queued` e o código corrente do job é limpo pelo fluxo de retry existente.

Todos os escritores devem compartilhar o mesmo volume e configuração. O controle é para a
VPS atual com filesystem local, não NFS/múltiplos hosts. A margem é uma verificação conservadora
antes de cada gravação, não pré-alocação nem quota do sistema operacional: outros aplicativos
da VPS podem consumir disco independentemente. Alertas de disco continuam necessários.

## Validação local e requalificação

- 21 testes novos de armazenamento: limites exatos, quantidade de arquivos, isolamento entre
  empresas, deduplicação, órfãos/rollback, corrupção, falha de gravação, locks entre sessões e
  processos, savepoints, códigos HTTP e tratamento do worker.
- Sete testes novos do gate: exige comprovação de concorrência, quota de órfãos, recuperação,
  deduplicação e preservação dos serviços; nunca aprova produção automaticamente.
- Regressão completa: **530 testes aprovados, três avisos, cobertura 87,72%**.
- Evidências: `tmp/phase7-v12-storage-tests-final.xml`,
  `tmp/phase7-v12-storage-coverage-final.json`.
- Requalificação consolidada aprovada em
  `benchmarks/qualification/reports/v12-storage-requalification-v1.json`: 18 gates e controles
  dos dois artigos aprovados; hashes XML preservados e zero bloqueios semânticos detectados.
  Validadores externos continuam em replay vinculado por hash, sem nova execução externa.
- Relatórios V-09 e V-10 versionados novamente; relatórios anteriores preservados.

## Ensaios na VPS

Diretório isolado: `/opt/idml-platform/qualification/v12-storage-v1`. Nenhuma chave/corpus privado
copiado; dados sintéticos e zero inferências pagas. Sem implantação ou restart dos serviços existentes.

HTTP repetido e aprovado (100 MiB com/sem Content-Length, limites, desconexão, admissão/timeout)
em `v12-http-observation-v3.json`; oito casos de ingestão repetidos e aprovados em
`v12-ingest-observation-after-v3.json`. Gates v3 aprovados para os hashes atuais.

As duas primeiras tentativas da fila foram interrompidas antes de criar containers por falta
da margem exigida: `v12-storage-queue-attempt1.json` e `v12-storage-queue-attempt2.json`.
Uma terceira tentativa com PostgreSQL de 64 MiB sofreu OOM somente nesse container de
laboratório, durante inicialização; a aplicação nem chegou a iniciar. Evidência preservada em
`v12-storage-queue-attempt3.json`, serviços existentes intactos e limpeza completa.
Para a repetição, somente o laboratório foi redimensionado para 336 MiB (aplicação 224,
PostgreSQL 96, Redis 16), mantendo a reserva do host em 512 MiB. Não é mudança de hardware
nem de limites dos serviços existentes. O watchdog continua abortando sob falta de recursos.

Na quarta tentativa faltava no pacote do laboratório o módulo público que gera o IDML sintético;
a aplicação de prova encerrou antes dos cenários. O pacote foi completado com
`tests/phase3_helpers.py` e `tests/__init__.py`, sem corpus privado. A evidência da tentativa
também foi preservada (`v12-storage-queue-attempt4.json`), sem OOM e com limpeza completa.

A quinta execução foi **aprovada**: `v12-real-queue-observation-v3.json`,
`v12-real-queue-gate-v3.json` e `v12-storage-gate-v1.json`. São 24 conversões nos quatro
cenários da fila e cinco verificações de armazenamento com PostgreSQL/processos separados:
contenção da trava, preservação do órfão após rollback, quota contando esse órfão, recuperação
do mesmo conteúdo e deduplicação após commit. Todos aprovados, sem OOM na rodada final.

Foram 58 amostras: memória disponível mínima de 664.625.152 bytes e readiness máximo de
41,986 ms. Os 25 serviços existentes permaneceram inalterados; containers e rede descartáveis
foram removidos. A imagem anterior recebeu os módulos candidatos por montagem somente leitura;
não houve implantação. Quota de 4 bytes no cenário negativo, reserva de disco de 1 MiB e
upload máximo de 4 MiB eram configurações **exclusivas desse laboratório com tmpfs de 32 MiB**.
Não aplicar esses valores reduzidos à VPS em uso. A CI verifica os relatórios e hashes,
sem repetir carga remota automaticamente.

## Próximos passos

Atualização: os perfis volumétricos do item 1 foram ensaiados em 2026-09-24; seis casos
aprovados na candidata, sem qualificação geral de produção. Ver `PHASE_7_V12_VOLUME_PROFILES.md`.

1. Medir armazenamento e pipeline completo próximo aos limites, incluindo pressão de disco e
   perfil com muitos artefatos. A conversão geral de IDML 100 MiB/ZIP expandido 500 MiB continua
   não qualificada; o ensaio HTTP não substitui essa validação.
2. Alertas e reconciliação de uso/órfãos, retenção recuperável de backups, rotação de logs do
   OpenClaw dedicado; requalificação, backup/restore e implantação controlada com rollback.
   Antes da implantação, inventariar o uso existente e conferir a quota configurada, sem
   excluir conteúdo para adequá-lo automaticamente ao limite.

`v12_2_complete=false`, `production_capacity_qualified=false`, `release_ready=false`.
