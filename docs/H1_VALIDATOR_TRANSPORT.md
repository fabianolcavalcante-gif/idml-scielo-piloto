# H1 — Transporte isolado dos validadores

Status em 2026-09-28: implementação candidata e smoke sintético Linux executados;
não implantado na aplicação e não suficiente para concluir H1 ou G-HOMOLOG.

O worker pode usar `IDML_VALIDATOR_SOCKET` para enviar o XML exato ao Packtools e
o ZIP exato ao SPSValidator. Sem a configuração, permanece indisponível, sem
aprovação presumida. O cliente verifica UID root do broker, limites e envelope
vinculado ao SHA-256, ferramenta, versão e perfil. XPM continua não integrado.

`ops/validator_broker.py` executa uma solicitação por vez, aceita apenas UID 10001
e ferramentas/imagens fixadas no registro confiável. A aplicação não recebe socket
Docker. Contêineres validadores: sem rede, raiz somente leitura, usuário não root,
sem capabilities, 192 MiB de RAM, 0,25 CPU, 64 processos e prazo limitado.
Admissão exige 768 MiB disponíveis; execução verifica reserva de 512 MiB e disco.
Entrada limitada a 100 MiB; saída limitada pelo registro; temporários são removidos.

## Evidência na VPS

`ops/observe_validator_socket.py` testou sequencialmente ambas as ferramentas em
contêiner cliente isolado, usando somente XML/ZIP sintéticos incompletos. Ambos
retornaram envelopes vinculados à entrada. Packtools concluiu com achados;
SPSValidator retornou `validator-exception-or-invalid-output`. **Nenhum XML foi
aprovado**. A falha do SPSValidator ainda exige investigação com pacote completo;
o caso incompleto não demonstra qualificação positiva desse validador.

Serviços existentes mantiveram identidades, horários de início e contadores de
reinício; socket e temporários removidos. Não houve implantação, reinício da
aplicação, uso de corpus privado ou ativação de produção. A comparação de serviços
não equivale a um teste prolongado de disponibilidade.

O smoke distingue `transport_completed` de `passed`: receber relatório íntegro,
inclusive falha formal, não equivale a aprovar o XML. Scripts permanecem no diretório
de qualificação da VPS; não há daemon instalado ou habilitado.

## Próxima sequência

Pacote sintético completo executado em 2026-09-29: ambos os validadores concluíram
sem exceção, com erros editoriais; ver `H1_COMPLETE_PACKAGE_QUALIFICATION.md`.
Qualificação de pacotes reais e integração XPM continuam pendentes.

Atualização de 2026-09-29: matriz local de falhas adicionada e prazo zero corrigido;
ver `H1_BROKER_FAILURE_QUALIFICATION.md`. A qualificação positiva de pacotes completos,
falhas reais Linux e XPM continuam pendentes. O smoke abaixo é histórico, não uma
reexecução da versão atualizada do broker.

Regressão local: **625 testes aprovados, três avisos, cobertura 87,83%** da aplicação.
31 testes direcionados aprovados; Ruff/formatação aprovados e Mypy sem erros em
97 arquivos. Evidências locais: `tmp/h1-transport-tests.xml` e
`tmp/h1-transport-coverage.json`. V-10 renovado em
`benchmarks/qualification/reports/v10-operational-workflow-h1-transport-v1.json`;
outros gates vinculados ao fonte não foram renovados neste incremento.
Smoke registrado em `benchmarks/qualification/reports/h1-validator-socket-smoke-v1.json`.

1. Qualificar execução positiva/negativa com pacote sintético completo e pacotes
   reais autorizados, sem copiar corpus privado para a VPS sem governança específica.
2. Completar testes do broker: prazo, OOM, disco/RAM, desconexão e limpeza em falhas.
3. Integrar executor XPM compatível e consolidar política formal no candidato final.
4. Preparar implantação H2: serviço supervisionado, registro root-owned somente
   leitura, diretório de trabalho root 0700, diretório de socket root sem escrita
   por grupo/outros, socket root:10001 0660. Montar apenas o diretório de socket no
   worker, nunca diretório de trabalho nem Docker socket; manter opção desativada
   até os testes, backup e rollback. Atualizar evidências source-bound afetadas.
5. Executar H3/H4 e decidir G-HOMOLOG; aprovação editorial não substitui validação.

Limitação: smoke não cobre carga concorrente, disponibilidade prolongada nem todos
os caminhos de falha. Cobertura Python da aplicação não mede cobertura do broker
operacional. Este incremento não autoriza READY_FOR_SCIELO nem produção.
