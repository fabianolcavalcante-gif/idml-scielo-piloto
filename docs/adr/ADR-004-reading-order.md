# ADR-004 — Reconstrução da ordem de leitura

- Status: aceito e implementado na Fase 3
- Data: 2026-08-24

## Contexto

IDML separa conteúdo em Stories e posicionamento em Spreads. Ordem do ZIP, nome de Story e `StoryList` isolados não reproduzem artigos em duas colunas com objetos ancorados.

## Decisão

Combinar encadeamento `PreviousTextFrame/NextTextFrame`, sequência interna de
Story, página/coluna/geometria transformada, estilos do template e âncoras.
Precedência: thread explícito, âncora inline, Story, geometria, estilo e
heurística textual.

O parser valida início único, reciprocidade dos links, ciclos e componentes
desconectados. Stories sem frame permanecem no Raw e usam `StoryList` como
fallback auditável; não são descartadas.

## Consequências

Conflitos geram ReviewItems. O algoritmo será testado contra PDF/XML gold e terá métricas de cobertura e ordem. IA não reordenará conteúdo silenciosamente.
