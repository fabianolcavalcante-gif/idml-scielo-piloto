# V-12.2 — Recepção HTTP/multipart limitada

Conferência final: 2026-09-24. Estado: **implementado na candidata e validado em laboratório**.
A implantação nos serviços existentes continua planejada após o fechamento técnico da V-12.2,
com requalificação, backup/restore e rollback. Este bloco não autoriza liberação para produção.

## Proteções implementadas

Os endpoints `/v1/artifacts/idml` e `/v1/artifacts/assets` agora usam a dependência
`bounded_upload`, em vez de deixar o framework processar o formulário inteiro antes de aplicar
o limite. Autenticação/permissão precedem essa dependência; o contrato multipart e o campo
binário `upload` permanecem documentados no OpenAPI.

- Tamanho de arquivo limitado ao `upload_max_bytes` configurado, durante a recepção e antes
  de encaminhar os bytes excedentes à gravação temporária.
- Corpo HTTP limitado a esse valor mais 64 KiB para o envelope multipart; essa margem não
  aumenta o tamanho permitido ao arquivo. Verificação também sem Content-Length.
- Content-Length inválido, repetido, conflitante com Transfer-Encoding ou divergente do corpo
  é recusado. Valor declarado acima do limite retorna 413 antes de ler o corpo.
- Somente um arquivo chamado `upload`; campos extras, múltiplos arquivos e multipart incompleto
  são recusados. Cabeçalhos internos têm orçamento de 4 KiB e Content-Type até 512 caracteres.
- Blocos entregues ao parser limitados a 64 KiB; isso limita as filas internas de escrita,
  mas não desfaz a alocação que um servidor ASGI já tenha feito para uma mensagem recebida.
- Temporários próprios são fechados em sucesso, erro, desconexão e cancelamento. A limpeza
  não depende de uma operação assíncrona que possa ser interrompida pelo cancelamento.

Erros de tamanho retornam 413; problemas de formato/enquadramento retornam 400; requisições
não autenticadas continuam retornando 401 sem criar arquivos de upload. A biblioteca multipart
também pode recusar cabeçalhos malformados antes do limite adicional da aplicação.

## Ensaio HTTP real isolado

`ops/probe_phase7_v12_http.py` executa Uvicorn e um cliente HTTP em processos separados,
conectados somente por loopback dentro do container. Usa a dependência de produção, mas uma
rota de laboratório que calcula tamanho e SHA-256 em blocos: não grava artefatos definitivos,
não acessa banco e não converte IDML. Nenhuma chave ou corpus privado foi copiado.

Limites: 256 MiB para o container completo, 0,25 CPU, sem rede externa/portas publicadas,
filesystem somente leitura e `/tmp` em tmpfs de 128 MiB. A imagem anterior recebe apenas
o módulo candidato por montagem read-only; não houve implantação ou restart de serviços.

| Cenário | Resultado |
|---|---|
| 2 MiB com Content-Length | 200, tamanho/hash corretos, temporário fechado |
| 100 MiB com Content-Length | 200, tamanho/hash corretos, temporário fechado |
| 100 MiB chunked, sem Content-Length | 200, tamanho/hash corretos, temporário fechado |
| Desconexão após 2 MiB | Temporário criado, transferido ao filesystem e fechado |
| Declaração de 101 MiB, sem enviar o corpo | 413 |

O pico RSS observado do **processo servidor** foi 53.940.224 bytes (aproximadamente 51,44 MiB).
Isso não inclui toda a memória do cliente nem o tmpfs. O limite de 256 MiB aplica-se ao conjunto;
não houve OOM. Foram coletadas 15 amostras do host, RAM disponível mínima de aproximadamente
782 MiB e readiness máximo de 15,021 ms. Os 25 serviços existentes foram preservados.
O container e seus temporários sintéticos foram removidos ao final.

Os envios de 100 MiB levaram 1,541 e 1,416 segundos no loopback. **Não são SLA, velocidade de
internet nem benchmark de disco:** os arquivos temporários estavam em tmpfs. Apenas um upload
era executado por vez; concorrência, clientes lentos e limite global de temporários ainda precisam
ser tratados na etapa de quotas/admissão.

## Evidências e controles de regressão

- `benchmarks/qualification/reports/v12-http-observation-v1.json`
- `benchmarks/qualification/reports/v12-http-gate-v1.json`
- `tests/test_phase7_v12_http_upload.py`: 27 testes de recepção, enquadramento, autenticação,
  contrato OpenAPI e limpeza, incluindo cancelamento após spooling.
- `tests/test_phase7_v12_http_gate.py`: nove testes de evidências incompletas, arquivos abertos,
  memória, OOM, HTTP indevido e mudança dos serviços existentes.
- Gate na CI confere a evidência e os hashes do módulo/driver; não dispara carga contra a VPS.

O relatório V-10 anterior foi preservado. A requalificação da integração com as rotas usa
`v10-operational-workflow-v12-http-v1.json`, sem alterar os relatórios históricos.

Regressão completa conferida em 2026-09-24: **489 testes aprovados, três avisos, cobertura
87,65%**; Ruff, formatação e mypy aprovados (92 módulos). Evidências locais:
`tmp/phase7-v12-http-tests.xml` e `tmp/phase7-v12-http-coverage.json`.

A requalificação consolidada também foi aprovada: 18 gates sintéticos passaram e os dois
artigos de referência mantiveram seus hashes XML, sem bloqueios semânticos nos controles
executados. Evidência: `benchmarks/qualification/reports/v12-http-requalification-v1.json`.
Os resultados dos validadores externos foram reutilizados com vínculo por hash; esta rodada
não representa uma nova execução desses validadores nem substitui a homologação humana final.

## Próximo bloco e implantação

Atualização de 2026-09-24: a admissão concorrente, verificação de espaço temporário e proteção
contra clientes lentos foram implementadas e ensaiadas na candidata. O registro abaixo é a
sequência original; o estado atualizado está em `PHASE_7_V12_UPLOAD_ADMISSION.md`. Quotas por
empresa e reserva do armazenamento definitivo continuam pendentes.

1. Quotas por empresa e reserva de disco, com proteção contra gravações simultâneas; limite
   global/concorrente dos temporários e proteção contra clientes lentos.
2. Medir armazenamento definitivo e pipeline completo próximo dos limites. Não presumir que
   o resultado da recepção autorize conversão geral de IDML com 100 MiB ou ZIP expandido de 500 MiB.
3. Alertas, rotação do OpenClaw dedicado e retenção recuperável de backups, sem exclusão automática
   dos backups históricos existentes.
4. Requalificar o conjunto, executar backup/restore e implantar a candidata em janela controlada,
   verificando saúde e rollback. Até essa implantação, os serviços existentes mantêm o código anterior.

`v12_2_complete=false`, `production_capacity_qualified=false`, `release_ready=false`.
