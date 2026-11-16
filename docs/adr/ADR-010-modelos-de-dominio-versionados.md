# ADR-010 — Modelos de domínio versionados

- Status: aceito
- Data: 2026-08-24

## Decisão

Separar Raw Article Model, fiel ao IDML, de Canonical Article Model, semântico e
independente de formato. Ambos usam Pydantic estrito, JSON Schema, versão
semântica, JSON canônico, IDs UUIDv5 e referências explícitas a Evidence.

Snapshots são imutáveis e tenant-bound no PostgreSQL. Migrations de payload são
funções explícitas e versões desconhecidas falham de forma fechada.

## Consequências

Parser, IA e builder não compartilham estruturas informais. Há custo de manter
schemas/migrations, compensado por reprodutibilidade, auditoria e evolução segura.
