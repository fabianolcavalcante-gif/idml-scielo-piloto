# ADR-015 — Homologação funcional antes da prontidão completa de produção

Complemento em 2026-10-01: ADR-016 inclui aplicação automática restrita antes da
avaliação humana como requisito da VH. Mantém controle determinístico e proibição
de release/publicação automáticos; não significa ativação já realizada.

- Status: aceito pelo usuário
- Data: 2026-09-25
- Substitui parcialmente: ADR-014, apenas quanto à ordem da primeira avaliação humana.

## Decisão

Priorizar uma versão funcional de homologação (VH) após validação formal, fluxo integrado,
implantação segura mínima e preparação dos testes. Introduzir G-HOMOLOG para acesso restrito
do especialista antes da conclusão integral de V-12 a V-15 e de G7-T/G8-RC.

G-HOMOLOG não autoriza publicação, tráfego editorial real ou produção. Não dispensa XPM
aplicável, segurança multiempresa, backup atual recuperável, rollback, limites de recursos,
proveniência ou política de release. Não aprova automaticamente nenhum gate existente.

As exigências completas de produção permanecem. Feedback inicial antecipa correções editoriais
e de usabilidade; o especialista revalida a RC final para G8-H. IA continua assistiva e regras
determinísticas prevalecem. Congelamento e versionamento aplicam-se a cada entrega de teste.

## Consequências

Reduzir retrabalho ao obter avaliação editorial antes do endurecimento operacional completo.
Aceitar limitações operacionais declaradas no ambiente restrito, nunca falhas de segurança ou
falso sucesso de XML. Escopo, checklists e evidências em `docs/EXPERT_TEST_READINESS_PLAN.md`.
Esta decisão altera planejamento, não a configuração implantada nem a autoridade de release.
