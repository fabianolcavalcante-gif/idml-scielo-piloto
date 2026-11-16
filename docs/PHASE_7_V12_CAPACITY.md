# V-12 — Desempenho, capacidade e custo

Atualização: 2026-09-22. Estado: **V-12.1 APROVADA; V-12.2 EM EXECUÇÃO; V-12.3 PENDENTE**.
A imagem da aplicação continua `phase7-7c08-v1`.
Não houve upgrade, ativação de agentes, mudança de dados editoriais ou cópia de corpus para a VPS.

## Etapas e critérios

1. **V-12.1 — Capacidade inicial controlada:** baseline, ferramentas, matriz sintética,
   janela de cinco minutos, tempos locais dos artigos e contabilidade histórica de IA.
2. **V-12.2 — Fila durável e limites operacionais:** medir API/Redis/worker em ambiente isolado,
   tempo de espera, saturação, upload/descompactação, quotas de artefatos e logs/backups.
3. **V-12.3 — Capacidade integrada:** janela prolongada, comportamento com IA, custo por perfil,
   metas operacionais e requalificação antes de declarar V-12 concluída.

`ops/gate_phase7_v12.py` aprova somente V-12.1 e mantém explicitamente `v12_complete=false`,
`production_throughput_qualified=false` e `release_ready=false`. Não avançar oficialmente para
V-13 até fechar V-12.2/V-12.3. Cinco minutos não comprovam ausência de vazamento em operação longa.

## Instrumentação implementada

- `ops/benchmark_phase7_v12.py`: IDML sintético com 16/128/512 parágrafos; concorrência em threads
  de 1 e 2; três repetições por célula; duração por parse/map/build/validate e espera na fila
  sintética; digest do XML; ZIP patológico de alta compressão rejeitado; RSS antes/depois da janela.
- `ops/observe_phase7_v12.py`: observador externo ao container, baseline de dez amostras,
  verificação a cada dois segundos e comparação de identidade/saúde dos serviços existentes.
- `ops/benchmark_phase7_v12_corpus.py`: somente local; três conversões de cada artigo e três
  empacotamentos do novo artigo, preservando os hashes qualificados em 7C-08/7C-06.
- `ops/inventory_phase7_v12.py`: inventário somente leitura de recursos IDML, sem expor segredos.
- `tests/test_phase7_v12_performance.py`: 27 testes de reservas, percentis, rejeição, fidelidade,
  desmontagem dos temporizadores e recusa de evidências incompletas ou adulteradas.

Os tempos locais de conversão excluem leitura dos arquivos, construção do pipeline/carregamento
da DTD, carregamento dos catálogos, IA e validadores externos. O total inclui enriquecimento e
resolução de referências; portanto não é apenas a soma das quatro etapas instrumentadas.
O benchmark sintético inclui a construção do pipeline. Não comparar diretamente ambientes nem
tratar `p95` com três amostras (máximo observado) como percentil estatístico de produção.

## Proteções da janela VPS

- Container `idml-v12-benchmark`, com 256 MiB, sem swap adicional, 0,25 CPU e 64 PIDs.
- Rede desabilitada, filesystem somente leitura, capabilities removidas e tmpfs de 32 MiB.
- Parada se RAM disponível ficar abaixo de 512 MiB; disco atingir 90% ou menos de 5 GiB livres;
  CPU do host superar 85% entre amostras; readiness falhar ou ultrapassar 500 ms; ou algum serviço
  mudar identidade, início, reinícios ou estado de saúde.
- Prazo máximo de janela solicitada + 180 segundos; remoção apenas do container criado pela
  própria execução. Nenhum restart de API, worker, banco, Redis ou OpenClaw faz parte deste teste.

As verificações de saúde e identidade não medem a latência de todas as operações do outro sistema.
A fila aqui é em memória/threads, não a fila durável da aplicação. V-12.2 deve medir esta última.

## Diagnóstico da primeira tentativa

`v12-vps-observation-attempt1.json` registra reprovação, 162 amostras e serviços preservados.
O evento Docker registrou término normal do programa com exit code 2 após 310 segundos,
não encerramento por falta de memória. A primeira versão do observador não preservou o JSON
interno quando o benchmark reprovava; por isso a causa exata dessa reprovação não pode ser
reconstruída a partir desse relatório.

Foi identificado e corrigido um defeito comprovável nos temporizadores: a substituição de métodos
podia formar ciclos de referência entre objeto, wrapper e método vinculado. A instrumentação agora
é desmontada em `finally`, tanto em sucesso quanto na rejeição da entrada. Duas regressões
comprovam que nenhum método substituído permanece. O observador também preserva o relatório
estruturado e o código de saída quando uma execução reprova. Os limites não foram relaxados.

## Inventário e pendências operacionais

Baseline inicial: aproximadamente 878 MiB disponíveis dos 3.915 MiB de RAM; swap usada 1.932 MiB;
disco em 84%, com aproximadamente 15 GiB livres. A VPS atual foi mantida.

| Item | Observado | Ação V-12.2 |
|---|---|---|
| API e worker | 256 MiB e 0,5 CPU cada | Medir fila real sem aumentar concorrência antecipadamente |
| Upload / ZIP expandido | 100 MiB / 500 MiB, razão máxima 100, 5.000 entradas | Qualificar amplificação de memória e ajustar limites com evidência |
| Logs API/worker/Postgres/Redis | 3 arquivos × 10 MB por container | Confirmar rotação efetiva e alertas |
| Logs OpenClaw dedicado | `json-file` sem rotação explícita | Aplicar política limitada em janela própria; preservar OpenClaw compartilhado |
| Backups IDML | 106 diretórios, aproximadamente 45 MiB | Definir retenção recuperável; nenhum backup foi excluído |
| Artefatos / banco / OpenClaw | Cerca de 12 KiB / 63 MiB / 3,3 MiB | Definir orçamento e alerta de crescimento; não são a causa principal dos 84% do host |

Não foi comprovado que um upload no limite máximo é seguro com a memória atual. Tampouco há
justificativa para upgrade somente a partir desse inventário. A concorrência real permanece uma
execução por worker; nenhum limite de produção foi aumentado.

## Custo histórico, sem novas inferências

`v12-historical-cost-v1.json` agrega 21 relatórios privados autenticados por SHA-256: vinte janelas
de desenvolvimento de fórmulas e uma de auditoria assistiva. Total registrado: 2.677.241 micro-USD
(US$ 2,677241), incluindo 220.500 micro-USD atribuídos a papéis que falharam. A contabilização pode
usar estimativas conservadoras em falhas; não é conciliação de fatura nem preço recorrente por artigo.

A auditoria de seis domínios registrou 140.447 micro-USD: metadados 21.703; autores/afiliações
22.309; estrutura 22.409; referências 25.797; figuras/tabelas 22.097; matemática/notas 26.132.
Custos e contagens de chamadas de reparo estão discriminados por janela. O catálogo de 43 fórmulas
qualificadas registrava 1.793.642 micro-USD, escopo diferente do total de tentativas de desenvolvimento.
Nenhuma chamada nova ao provider foi necessária para esta etapa.

Na consolidação, 13 somas vazias de papéis com falha foram serializadas como `null`.
Foram corrigidas para zero somente nas janelas com `failed_roles=0`; os totais não mudaram.
O gate agora recusa custos ausentes, negativos, fracionários, booleanos ou não finitos,
sem presumir que valores desconhecidos sejam gratuitos. Sete regressões cobrem esses casos.

## Fechamento V-12.1

A janela corrigida de 2026-09-21 foi aprovada e conferida em 2026-09-22:

- 728 conversões sintéticas em 300,092 segundos; 162 amostras do host.
- RSS de 103.723.008 para 103.284.736 bytes: sem crescimento observado nessa janela.
- RAM disponível mínima de aproximadamente 673 MiB; readiness máximo de 61,526 ms.
- 25 containers existentes preservados; container temporário removido, saída 0, sem OOM.
- Seis combinações tamanho/concorrência válidas e determinísticas; ZIP patológico rejeitado.
- Dois artigos locais mantiveram os hashes qualificados; nenhuma inferência nova foi cobrada.
- Regressão local: 407 testes aprovados, três avisos, cobertura de 87,31%; Ruff e mypy aprovados.
- Readiness da VPS reconferido em 2026-09-22: banco/Redis OK, cinco serviços IDML saudáveis.

O contador de disco do observador usa bytes usados/total (máximo 80,38%), enquanto `df`
considera o espaço reservado ao calcular sua porcentagem (84% no baseline). São denominadores
diferentes, não redução do uso de disco. A reserva adicional de 5 GiB também foi monitorada.

Com 0,25 CPU, duas threads aumentaram a latência individual; isso não justifica aumentar
a concorrência de produção. A fila durável continua não qualificada. O gate consolidado
aprovou V-12.1, mantendo a fase completa e a liberação para produção bloqueadas.

## Evidências

- `benchmarks/qualification/reports/v12-resource-inventory-v1.json`
- `benchmarks/qualification/reports/v12-local-corpus-v1.json`
- `benchmarks/qualification/reports/v12-historical-cost-v1.json`
- `benchmarks/qualification/reports/v12-vps-observation-attempt1.json`
- `benchmarks/qualification/reports/v12-vps-observation-v1.json`
- `benchmarks/qualification/reports/v12-initial-capacity-gate-v1.json`
- JUnit/cobertura locais: `tmp/phase7-v12-tests.xml`, `tmp/phase7-v12-coverage.json`.

As evidências das tentativas devem permanecer separadas. Um experimento reprovado não pode ser
apagado ou reapresentado como aprovado.

## V-12.2 — Correções locais do agendamento

Na inspeção da fila foi encontrado um desvio real: `find_queued_job` respeitava `available_at`,
mas `process_job` não verificava esse horário. Assim, uma notificação Redis atrasada/duplicada
podia antecipar um retry. A consulta transacional do processador agora também exige tarefa vencida.

O loop agora consulta a fila durável antes de esperar por Redis. Com trabalho pendente, consome
um aviso sem espera bloqueante; quando ocioso, espera o aviso e consulta novamente o banco.
O identificador recebido no aviso não escolhe a tarefa: a ordem continua definida pelo banco.
Isso evita adiar trabalho recuperável atrás de uma sequência de notificações inúteis e elimina
a espera de dois segundos entre tarefas quando os avisos se perderam. Não altera a concorrência.

A notificação feita pela API agora usa timeouts de conexão e leitura de dois segundos. O commit
continua anterior à notificação e a recuperação pelo banco permanece disponível em falha Redis.
Esses timeouts são por operação de rede, não uma promessa de latência total de dois segundos.

`tests/test_phase7_v12_queue.py` cobre oito cenários: execução antecipada recusada; três rajadas
de vinte tarefas com avisos perdidos, repetidos e Redis indisponível; três retomadas após espera
ociosa; e timeouts da API. Usa o processador e transações reais sobre SQLite, mas Redis simulado.
Não qualifica locks concorrentes de PostgreSQL, rede, vazão de conversão XML nem capacidade da VPS.

Regressão local de 2026-09-22: **415 testes aprovados, três avisos, cobertura 87,53%**;
Ruff, formatação e mypy aprovados. Evidências: `tmp/phase7-v12-queue-tests.xml` e
`tmp/phase7-v12-queue-coverage.json`. A primeira rodada detectou corretamente a divergência
dos hashes V-10 após alterar os fontes; a rodada final passou usando o novo relatório
`benchmarks/qualification/reports/v10-operational-workflow-v12-queue-v1.json`.

Requalificação local adicional aprovada em
`benchmarks/qualification/reports/v12-queue-requalification-v1.json`: 18/18 gates,
106/106 stories preservadas nos dois IDMLs; ambos os artigos com zero bloqueio semântico
e os mesmos hashes de XML da qualificação anterior. Os validadores externos foram conferidos
por replay vinculado ao hash do candidato, não executados novamente. Nenhuma inferência nova.

As alterações estão locais; a VPS permanece na imagem anterior. A evidência V-10 anterior é
preservada e a requalificação local recebe relatório próprio, sem reapresentar dados históricos
como uma nova execução de artigo. V-12.1 continua evidência da imagem testada, não desta candidata.

### Laboratório real da fila — V-12.2

Implementados `ops/lab_phase7_v12_queue.py`, `ops/observe_phase7_v12_queue.py` e
`ops/gate_phase7_v12_queue.py`. O laboratório usa PostgreSQL 16/Redis 7 reais e migrações
da aplicação; API HTTP, driver e worker são processos separados em um container limitado.
Somente dados sintéticos e uma sessão efêmera de teste são criados. Não copia usuários,
credenciais ou volumes do sistema existente.

Limites: 256 MiB/0,25 CPU para aplicação + driver, 96 MiB/0,15 CPU PostgreSQL e
32 MiB/0,10 CPU Redis; sem swap adicional, sem portas publicadas, rede Docker interna,
filesystems somente leitura e dados em tmpfs. A soma de 384 MiB exige pelo menos
896 MiB disponíveis antes da criação (inclui a reserva de 512 MiB do host).
O observador externo interrompe por pressão de memória/CPU/disco, degradação do readiness
ou mudança dos serviços existentes. O disco usa o denominador de `df`, excluindo espaço reservado.

A imagem base permanece `phase7-7c08-v1`; apenas `worker.py` e `routers/jobs.py` candidatos
são montados read-only no container de laboratório. A imagem e os fontes são identificados
por SHA-256 no relatório. **Não é uma implantação da candidata nos serviços IDML existentes.**

Matriz: seis conversões por cenário, com operação normal, avisos repetidos/inválidos,
avisos apagados antes de iniciar o worker e desligamento real do Redis dedicado ao laboratório.
Cada cenário repete uma requisição idempotente, confere seis efeitos e dezoito eventos,
valida o XML e compara o download por hash. A espera inclui a inicialização do worker e
o atraso intencional da tarefa; não é um SLO de produção nem comparação com worker aquecido.
Não foi medido blackhole de rede, reinício de Redis após a falha, múltiplos workers ou saturação.

A primeira execução aprovou 24 conversões, mas o atraso de seis segundos era próximo ao tempo
de inicialização do worker. Seu relatório foi preservado como `v12-real-queue-observation-v1.json`.
A execução reforçada usa atraso de doze segundos e exige observar a tarefa ainda `queued`,
antes do horário previsto, enquanto as outras cinco já terminaram. O gate 1.1 recusa evidência
sem essa observação explícita; não basta o timestamp final ser posterior ao prazo.

**Resultado em 2026-09-22: laboratório real da fila aprovado.** A execução reforçada completou
24 conversões (seis por modo), com espera do agendamento observada nos quatro modos, seis
efeitos e dezoito eventos por modo e o mesmo hash de XML. Foram coletadas 48 amostras do host;
RAM disponível mínima de aproximadamente 654 MiB, readiness máximo de 28,34 ms,
nenhum OOM e 25 serviços existentes preservados. Todos os containers e a rede temporários
foram removidos; somente os dados sintéticos efêmeros do laboratório foram descartados.

Os 13 testes locais novos cobrem a reserva prévia e rejeições por evidência incompleta,
OOM, mudança de serviço, duplicação, antecipação, falta de observação da espera e exposição de porta.
Suíte completa: **428 aprovados, três avisos, cobertura 87,53%**, Ruff/mypy/formatação aprovados.
O gate 1.1 foi incluído na CI, sem executar cargas contra a VPS a partir da CI.

Evidências atuais:

- `benchmarks/qualification/reports/v12-real-queue-observation-v2.json`
- `benchmarks/qualification/reports/v12-real-queue-gate-v2.json`
- `tmp/phase7-v12-real-queue-tests.xml` e `tmp/phase7-v12-real-queue-coverage.json`

A primeira execução e seu gate permanecem separados (`v12-real-queue-*-v1.json`).
O driver/API/worker dividem 256 MiB/0,25 CPU no laboratório, enquanto a implantação tem limites
separados; os resultados não definem a capacidade máxima dessa implantação. Não houve uso de IA,
upgrade de hardware nem alteração de limites ou reinício dos serviços existentes.

### Sequência restante para fechar V-12.2

Ingestão XML limitada concluída em laboratório: OOM sintético reproduzido e corrigido;
oito casos VPS aprovados, 453 testes/87,57%. Detalhes e limitações em
`docs/PHASE_7_V12_INGESTION.md`. A candidata não foi implantada nos serviços existentes.

Recepção HTTP/multipart concluída na candidata em 2026-09-24: 100 MiB com/sem Content-Length
passaram em laboratório e os temporários foram fechados; 489 testes/87,65%.
Ver `docs/PHASE_7_V12_HTTP_UPLOAD.md`. Isso não qualifica a conversão completa desse volume.

Admissão concorrente e prazos de recepção aprovados na candidata em 2026-09-24, incluindo
verificação de espaço para temporários. Ver `docs/PHASE_7_V12_UPLOAD_ADMISSION.md`.

Quotas e controle concorrente do armazenamento definitivo aprovados na candidata em 2026-09-24:
530 testes/87,72%, fila repetida e cinco verificações com PostgreSQL. Laboratório final de
336 MiB (224 aplicação, 96 PostgreSQL, 16 Redis), reserva do host de 512 MiB, 25 serviços
preservados. Tentativas anteriores e limitações em `docs/PHASE_7_V12_STORAGE_BUDGET.md`.

1. Perfis volumétricos ensaiados: seis casos aprovados, incluindo gravação/conversão de 100 MiB,
   expansão binária de 500 MiB, texto de 14 MiB, muitos arquivos e pressão de disco isolada.
   Ver `docs/PHASE_7_V12_VOLUME_PROFILES.md`; 100/500 MiB continuam sem qualificação geral.
2. Auditoria e plano de retenção implementados/testados, sem exclusões; observação real e
   pendências em `docs/PHASE_7_V12_OPERATIONS.md`. Agendamento e rotação ainda não ativados.
3. Restore isolado do backup existente aprovado (`docs/PHASE_7_V12_BACKUP_RESTORE.md`).
   Próximos: backup novo coordenado, restore, gates e implantação em janela controlada.

Reaplicar o monitor e a reserva de recursos em cada janela. `v12_complete=false`,
`release_ready=false`: o laboratório real da fila não aprova esses itens restantes.
