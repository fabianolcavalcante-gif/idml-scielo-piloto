# ADR-011 — Governança do corpus e holdout

- Status: aceito
- Data: 2026-08-24

## Decisão

Não versionar binários ou texto integral. Versionar manifestos com hashes,
classificação, retenção, split e expectativas. ESA e20240086 é gold de
desenvolvimento; quatro pares RBEdu são contraste; RBEdu 0272965 AOP é holdout e
não orientará regras.

## Consequências

CI usa fixtures sintéticas. Execuções com corpus real exigem root local
autorizado. O holdout RBEdu não substitui um conjunto futuro de homologação ESA.
Mudança de split ou contaminação exige ADR e nova baseline.
