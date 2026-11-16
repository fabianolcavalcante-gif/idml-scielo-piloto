# ADR-006 — Storage de artefatos

- Status: aceito
- Data: 2026-08-24

## Decisão

Usar volume filesystem content-addressed por SHA-256 e tenant na VPS inicial. Escrita atômica e metadados no PostgreSQL. Definir uma porta para migração futura a S3 compatível.

## Consequências

Menor consumo que MinIO na VPS atual. Backup precisa cobrir volume e banco de forma coordenada. O volume não é público e nomes enviados não determinam paths.

## Complemento V-12.2 — 2026-09-24

Na candidata, quotas por empresa consideram arquivos existentes, inclusive órfãos após rollback.
Escritores compartilham trava de filesystem até o fim da transação externa; deduplicação verifica
tamanho e hash antes de reutilizar conteúdo. Margem livre de disco é checada antes da gravação,
sem prometer reserva de espaço contra escritores externos. Nenhum órfão é excluído automaticamente.
Detalhes e limitações: `docs/PHASE_7_V12_STORAGE_BUDGET.md`.
