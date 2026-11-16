# H1 — Qualificação das falhas do broker

Incremento de 2026-09-29. Não encerra H1 nem autoriza implantação ou G-HOMOLOG.

Foram adicionados 19 testes determinísticos em
`tests/test_validator_broker_failures.py`, sem executar Docker, esgotar recursos
do host ou utilizar artigos privados. Junto aos 16 testes anteriores de transporte,
35 testes direcionados passaram.

## Cenários comprovados por injeção de falhas

- UID não autorizado, cabeçalho excessivo, entrada truncada e hash divergente:
  recusados antes de executar validador; nenhum arquivo temporário remanescente.
- Erro do executor e desconexão ao enviar resposta: arquivo temporário removido.
- RAM abaixo da reserva inicial/de execução e disco insuficiente: admissão negada;
  limites exatos de memória também exercitados.
- Prazo vencido, excesso de saída, OOM, saída não zero e queda da reserva de RAM:
  execução falha, remoção solicitada somente para o contêiner criado pelo teste,
  processo cliente encerrado e pipe fechado.
- Falha da remoção Docker: propagada como erro, sem impedir encerramento do cliente.
  Isso NÃO comprova remoção do contêiner quando o daemon Docker falha.
- Caminho sem falha: retorno e limpeza exercitados com processo simulado.

## Correção encontrada

`receive` usava `deadline or novo_prazo`, tratando prazo explícito zero como ausente.
Agora somente `None` inicia prazo novo; prazo já vencido não é renovado. O teste
reproduziu a falha antes da correção e passou depois.

## Evidências e limites

Regressão completa: **644 testes aprovados, três avisos**. Artefatos:
`tmp/h1-broker-faults-tests.xml` e `tmp/h1-broker-faults-coverage.json`.
Cobertura das linhas da aplicação: 87,83%; relatório combinado com o broker:
87,60%. A diferença é de escopo de medição, não perda de cobertura da aplicação.
Ruff/formatação aprovados; Mypy aprovado em 97 arquivos da aplicação.
Gate V-10 repetido e aprovado no seu escopo; evidência histórica preservada porque
os fontes da aplicação vinculados a ela não foram alterados neste incremento.

`tmp/h1-broker-only-tests.xml` e `tmp/h1-broker-only-coverage.json`: 35 aprovados,
um aviso, 123/171 linhas do broker cobertas (71,93%). Medição direcionada separada
da cobertura da aplicação; não usa esse percentual para aprovar o broker completo.
O teste do comando principal, permissões reais Linux, sinais e falhas reais do
daemon ainda não estão cobertos por essa matriz local Windows.

O smoke Linux anterior permanece histórico da versão de 2026-09-28; esta correção
ainda não foi enviada à VPS. Não houve nova chamada de IA, implantação ou reinício.

Próximo: executar pacote sintético completo no broker Linux atualizado, investigar
a falha SPSValidator, qualificar pacotes reais sob governança do corpus e integrar
XPM compatível. O registro ainda informa XPM 4.0.096/SPS 1.9, worker pendente;
isso não atende ao perfil SPS 1.10 e não pode ser tratado como aprovação.
