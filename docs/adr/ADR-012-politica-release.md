# ADR-012 — Política determinística de release

- Status: aceito
- Data: 2026-08-24

## Contexto

Validade DTD isolada não comprova conformidade SPS, fidelidade editorial nem
integridade do pacote. O XPM é uma ferramenta externa Windows e seu resultado
precisa pertencer exatamente ao candidato avaliado. Uma decisão automatizada ou
de IA não pode transformar evidência ausente em aprovação.

## Decisão

Adotar a Release Policy `1.0.0`, com negação por padrão e quatro resultados:
`READY_FOR_SCIELO`, `NEEDS_REVIEW`, `BLOCKED` e `VALIDATION_UNAVAILABLE`.

`READY_FOR_SCIELO` exige, para o mesmo hash imutável:

- validadores obrigatórios completos e sem erro;
- fidelidade acima dos limiares do profile;
- XPM completo, sem blocking/fatal/error e ligado ao SHA-256 do ZIP;
- ausência de pendência editorial aberta.

Override humano só pode remover uma pendência editorial depois de todos os
gates técnicos passarem. O registro exige empresa, usuário aprovador,
justificativa, evidência por SHA-256 e versão da política. Override nunca ignora
erro de validador, falha de fidelidade, hash divergente ou XPM ausente.

## Consequências

- IA não concede estado de liberação;
- resultado de outro pacote não pode ser reutilizado;
- indisponibilidade externa fica distinta de reprovação;
- decisões e exceções são reproduzíveis e auditáveis.

