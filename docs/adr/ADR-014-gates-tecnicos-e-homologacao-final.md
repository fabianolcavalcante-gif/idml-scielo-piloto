# ADR-014 — Gates técnicos, RC e homologação humana final

- Status: aceito
- Data: 2026-09-04

Atualização em 2026-09-25: ADR-015 substitui a exigência de prontidão completa antes da
primeira avaliação humana. G-HOMOLOG permite VH restrita; G8-H e requisitos de produção
permanecem. O texto abaixo registra a decisão original.

## Contexto

A indisponibilidade temporária de revisores humanos não deve interromper o desenvolvimento e a
validação técnica, mas consenso entre agentes que usam o mesmo modelo não constitui independência
nem pode autorizar publicação. O especialista em XML deve avaliar uma Release Candidate completa,
e não incrementos parciais que ainda serão alterados.

## Decisão

O fluxo passa a ter quatro decisões distintas:

1. `G6-T` encerra a implementação assistiva quando contratos, segurança, corpus técnico,
   equivalência semântica, abstenção e limites de custo/reparo estiverem comprovados;
2. `G7-T` encerra a homologação automatizada e o piloto editorial simulado;
3. `G8-RC` congela a candidata completa e operacionalmente pronta, ainda sem tráfego real;
4. `G8-H` é o gate humano final, executado pelo especialista em XML, e é o único que pode liberar o
   rollout de produção em conjunto com os critérios operacionais.

Os agentes OpenClaw podem propor, criticar, adjudicar e solicitar reparo semântico limitado, mas não
podem aplicar patches, aprovar release nem conhecer os alvos ocultos do holdout. Validação
determinística sempre prevalece. Incerteza, indisponibilidade, falta de evidência, violação de
política, repetição sem progresso ou esgotamento de ciclos produzem abstenção/rejeição fail-closed.

## Consequências

A Fase 7 pode começar após o `G6-T` sem esperar o especialista. Isso não habilita as flags de IA,
não muda a autoridade de release e não autoriza produção. Todo apontamento posterior do especialista
gera correção, fixture de regressão e repetição dos gates aplicáveis antes de uma nova decisão
`G8-H`.

Os critérios e as evidências obrigatórias permanecem centralizados em
`docs/XML_VALIDATION_MASTER_PLAN.md` e `PLANO_DESENVOLVIMENTO_POR_FASES.md`.
