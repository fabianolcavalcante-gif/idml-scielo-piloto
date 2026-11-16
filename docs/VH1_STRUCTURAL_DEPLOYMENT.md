# Ativação da candidata acumulada — 29/10/2026

API e worker da VPS estão em `idml-foundation:vh1-structural-20261028-v1`,
imagem `sha256:c174d22a596ca65f8d2d280bf5900bc5639f9b29e4230269831cf7b7cb1d3568`.
A imagem anterior `vh09-heads-20261021-v1` foi preservada e seu retorno foi
testado antes da reaplicação da nova versão. A configuração persistida aponta
para a imagem efetivamente ativa. Não houve mudança de esquema: `c0e1f2031425`.

## O que foi implantado

As alterações acumuladas incluem o cabeçalho correto JATS 1.3 MathML3, diagnóstico
web de validação em Jobs, ações para avisos/consultas e o compositor de
compatibilidade DOI/SPS/data/Wayta/JATS/Style Checker. Incluem também a ponte
XPM interna da revalidação privada e os contratos de evidências por escopo.

Ter o código na imagem não conecta automaticamente os executores ao worker.
O processamento comum ainda precisa da ligação supervisionada XPM/validadores;
não foram habilitados sockets, grants ou flags de IA por esta implantação.
Resultados antigos dos jobs não são recalculados nem recebem aprovação retroativa.

## Verificação e recuperação

- 625 testes direcionados aprovados na imagem Linux final; três warnings conhecidos.
  São testes de regressão, não uma nova suíte integral ou medição de cobertura.
- PostgreSQL isolado: concorrência com duas sessões, idempotência de restauração,
  conflito entre pedidos, proteção de claim humano, rollback externo e dois
  controles de imutabilidade SQL aprovados. Fixtures não foram inseridas no banco ativo.
- Reprodução dos relatórios nativos selados dos dois artigos dentro da nova imagem,
  no instante original dos recibos: regras mantêm zero erros técnicos derivados;
  controles negativos e erro adicional continuam recusados. Não é nova execução
  online nem renovação de consulta ou autorização.
- Backup de preparação de 28/10 preservado. Backup novo de 29/10 em
  `/opt/idml-platform/backups/20261029T114636Z`, com checksums e restauração
  isolada aprovados antes da ativação.
- Troca da API/worker, retorno real à imagem anterior e reaplicação aprovados.
  334 arquivos de runtime conferidos por hash em **cada** container, sem escrita
  pelo usuário da aplicação. 1.206 arquivos da candidata congelada conferidos.
- Cinco serviços IDML saudáveis; os outros 23 containers mantiveram identidade,
  início e contagem de reinícios. Contagens dos dados existentes preservadas.
- `/health/ready`, `/app` e JavaScript retornam 200. Recursos e diagnóstico sem
  autenticação retornam 401. HTML/JS do diagnóstico presentes; CSP e nosniff
  presentes. Isso é smoke HTTP, não E2E autenticado em navegador.

O primeiro ensaio ampliado teve um teste de upload recusado porque o tmpfs do
laboratório tinha 256 MiB, igual à reserva mínima configurada. O limite desse
filesystem de teste passou a 512 MiB; a repetição aprovou os 625 testes. A reserva
de upload e os limites da aplicação não foram reduzidos. O log da tentativa
inicial foi preservado e não foi somado à execução final.

Evidência pública: `benchmarks/qualification/reports/vh1-structural-deployment-v1.json`,
SHA-256 `3c6a0c5f8118e50232f4542dcafaa6665a452b3c75a54b3a95a773100ac728c3`.
Logs privados de build, testes, backup e implantação permanecem na pasta da
release, com acesso restrito. O driver operacional é `ops/deploy_vh1_structural.py`.

## Próximo trabalho no VH-09

A ativação acumulada está concluída. A inspeção do fluxo confirma duas funções
ainda ausentes, que devem ser implementadas dentro do VH-09 existente:

1. **Promoção da candidata revalidada:** decidir prontidão técnica para uma versão
   de trabalho com regras explícitas para erros, compatibilidade, avisos e consultas;
   transacionar a nova versão somente com evidência atual, fonte autorizada e
   proteção de estado humano. Não converter a leitura de recibo histórico em aprovação.
2. **Pacote da versão restaurada:** reconstruir e revalidar o pacote dessa versão,
   com evidências novas vinculadas ao seu conteúdo. A restauração de rascunho
   existente não implementa essa revalidação nem herda aprovação anterior.

Depois, ligar worker/ciclo e executores supervisionados (VH-10/14), completar o
fluxo web e a regressão/E2E/entrega já previstos. Não acrescentar outra fase para
a mesma integração. Nenhuma IA foi chamada, aplicação automática continua
desligada e G-HOMOLOG/publicação permanecem não autorizados.
