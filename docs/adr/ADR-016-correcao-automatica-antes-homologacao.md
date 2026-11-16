# ADR-016 — Correção automática restrita antes da avaliação humana

- Data: 2026-10-01.
- Status: direção autorizada; política VH-08 implementada/qualificada em 2026-10-19;
  executor, ciclo real, integração e implantação pendentes.
- Complementa ADR-015 e os contratos assistivos anteriores.

## Decisão

Incluir na versão de homologação um ciclo de propostas IA com aplicação automática
de operações explicitamente elegíveis, controlada por executor determinístico,
e revalidação antes da avaliação final do especialista. Não exigir decisão humana
individual para cada operação elegível; manter as ambíguas como pendências.

A IA continua sem autoridade para editar XML arbitrariamente, dispensar regras,
aprovar release ou publicar. Evidência insuficiente, confiança ou consenso não
autorizam aplicação. Cada mudança tem versão, autoria de serviço, evidências,
before/after, validação e reversão. Decisões humanas não podem ser sobrescritas.

## Consequências

H1-A1–A5 tornam-se requisitos de G-HOMOLOG desta entrega. A assistência deixa de
ser opcional no escopo prometido: ausência de qualificação exige replanejamento
explícito com o responsável, não anunciar um piloto determinístico como IA ativa.
O modo sem IA permanece como recuperação e teste.

Contratos/relatórios assistivos históricos continuam válidos no seu escopo e não
devem ter `needs_human` ou permissões simplesmente invertidos. Não ativar flags
atuais como atalho. Produção e aceite humano final permanecem separados.

Escopo, allowlist inicial, restrições e aceites em
`docs/AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`. Nenhuma implantação autorizada por
este registro isoladamente, nem ampliação do corpus ou das permissões dos agentes.

## Primeiro incremento — 2026-10-19

Contratos novos, sem converter propostas assistivas antigas em autorizações.
Política inicial admite somente preencher campo ausente por três operações
enumeradas, nunca alterar um valor existente ou estado humano. Elegibilidade é
separada de aplicação, revalidação e aprovação editorial. Fonte/escopo/grant e
limites verificáveis; sem autoridade por confiança ou consenso do modelo.

Prova: `vh08-autocorrection-policy-v1.json`, 102 testes da política e 223 na regressão
direcionada. Mapa exato, caminhos, fronteira de confiança e trabalho do executor
em `VH08_AUTOCORRECTION_POLICY.md`. Sem migração de banco, IA ativa ou deploy.
