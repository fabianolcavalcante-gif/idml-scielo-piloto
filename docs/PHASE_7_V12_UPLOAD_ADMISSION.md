# V-12.2 — Admissão de uploads e clientes lentos

Data: 2026-09-24. Implementado na candidata; **não implantado nos serviços existentes**.
Complementa a recepção limitada em `PHASE_7_V12_HTTP_UPLOAD.md`; não conclui V-12.2.

## Contrato implementado

- Uma vaga por padrão, compartilhada entre processos pelo filesystem local do artifact root.
  Autenticação continua anterior à admissão. Sem vaga, retorna 503 com `Retry-After: 5`,
  sem enfileirar a requisição e sem criar temporário multipart.
- Locks não bloqueantes do sistema operacional (Linux flock; Windows locking). Arquivos
  `.upload-admission/slot-N.lock` são permanentes e não devem ser apagados para liberar vagas.
  Fechar o descritor/processo libera a trava. Timeout não usa lease que expire com upload ativo.
- Verifica o espaço livre no diretório temporário efetivamente escolhido pelo Python:
  reserva configurada + número de vagas × limite máximo por arquivo. Na configuração padrão,
  exige pelo menos 356 MiB livres. Falha de acesso/verificação e falta de espaço retornam 503.
- Inatividade entre leituras: 30 segundos; duração total da recepção multipart: 300 segundos.
  Ambos retornam 408. O prazo total impede que pequenos envios periódicos renovem indefinidamente
  a ocupação. Os prazos não abrangem processamento posterior do artigo.
- A vaga continua ocupada durante o consumo do upload pela rota; os temporários são fechados
  antes de liberar a vaga, inclusive em cancelamento, desconexão, erro e timeout.

Configuração em `.env.example`: `IDML_UPLOAD_MAX_CONCURRENCY` (1–4),
`IDML_UPLOAD_TEMP_RESERVE_BYTES`, `IDML_UPLOAD_IDLE_TIMEOUT_SECONDS` e
`IDML_UPLOAD_TOTAL_TIMEOUT_SECONDS`. Aumentar vagas exige novo ensaio de capacidade.

Todos os processos/containers participantes devem compartilhar o mesmo artifact root e a mesma
configuração de vagas. Esta solução é para filesystem local compartilhado na VPS atual, não um
semáforo distribuído para múltiplas máquinas/NFS. A checagem de espaço é conservadora, **não uma
quota de disco do sistema operacional**: gravações externas ainda podem consumir o espaço livre.
Os temporários não são armazenados nos arquivos de lock. Não há garantia de espaço para os
artefatos definitivos nesta etapa.

## Ensaio real isolado na VPS

Diretório: `/opt/idml-platform/qualification/v12-http-v2`. Container de laboratório de 256 MiB,
0,25 CPU, rede externa desativada, sem portas publicadas, tmpfs 128 MiB. Somente nele foram
usados reserva temporária de 8 MiB e timeout ocioso de 2 segundos para exercitar os limites;
esses valores **não são a configuração recomendada de produção**.

- Repetidos os cinco cenários anteriores, incluindo 100 MiB com e sem Content-Length.
- Upload incompleto de 2 MiB ocupou a vaga; segundo upload recebeu 503.
- O primeiro recebeu 408 após inatividade, sem temporários abertos; novo upload recebeu 200.
- 18 amostras do host; memória disponível mínima 740.118.528 bytes; readiness máximo 15,396 ms.
- RSS máximo observado do servidor: 54.251.520 bytes, excluindo cliente e tmpfs.
- Sem OOM, 25 serviços preservados, container removido, nenhuma inferência paga.

São medições de recepção por loopback, não throughput de internet, disco físico ou conversão.
Os dados enviados são sintéticos; nenhum artigo privado/chave foi copiado para o laboratório.

Evidências: `benchmarks/qualification/reports/v12-http-observation-v2.json` e
`v12-http-gate-v2.json`. A CI verifica a matriz, admissão/timeout e hashes dos módulos e driver.
As evidências v1 foram preservadas como históricas; não qualificam o código atual.

## Validação automatizada

Regressão local: **502 testes aprovados, três avisos, cobertura 87,68%**. São 12 testes novos
de admissão/timeout e um novo teste negativo do gate, além da regressão anterior. Incluem
concorrência entre processos reais, limite de vagas, falta/falha de espaço, limpeza após timeout
ocioso/total e cancelamento, recusa antes de spooling e preservação do processamento posterior.
Evidências: `tmp/phase7-v12-admission-tests.xml` e `tmp/phase7-v12-admission-coverage.json`.

Ruff e formatação aprovados; mypy aprovado nos 93 módulos com plataformas Windows e Linux.
Os relatórios de segurança V-09 e fluxo V-10 receberam novas versões vinculadas aos hashes
da candidata, preservando as versões anteriores. A primeira requalificação consolidada
(`v12-admission-requalification-v1.json`) recusou corretamente o hash antigo de Settings no
relatório V-09; não houve falha nos cenários de segurança nem mudança dos dois XMLs.

A nova execução consolidada (`v12-admission-requalification-v2.json`) foi aprovada: 18 gates
sintéticos e os controles dos dois artigos passaram, sem bloqueios semânticos, mantendo os
hashes XML anteriores. Os validadores externos continuam com evidência reaplicada por hash,
sem nova execução externa. A homologação humana final e XPM continuam pendentes pelo plano.

## Próximo bloco

Atualização: o item 1 foi implementado e validado na candidata em 2026-09-24.
Estado atual e evidências em `PHASE_7_V12_STORAGE_BUDGET.md`; ainda sem implantação.

1. Quotas por empresa e reserva de espaço para gravações definitivas concorrentes, incluindo
   os XMLs/pacotes gerados pelo worker. Definir tratamento de deduplicação, rollback, arquivos
   órfãos e contabilização sem permitir corrida entre upload e geração.
2. Ensaiar armazenamento e pipeline completo próximo dos limites; manter 100/500 MiB como
   limites não qualificados para conversão geral até esses ensaios.
3. Alertas, rotação de logs e retenção recuperável de backups; requalificação final,
   backup/restore e implantação controlada com rollback.

`v12_2_complete=false`, `production_capacity_qualified=false`, `release_ready=false`.
