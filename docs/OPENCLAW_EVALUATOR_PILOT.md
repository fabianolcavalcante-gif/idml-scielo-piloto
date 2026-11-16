# Piloto sintético do agente OpenClaw dedicado

Data: 2026-08-26. Este piloto é evidência de execução e segurança contratual; não substitui o
baseline editorial humano.

## Agente provisionado

- ID: `idml-evaluator`;
- OpenClaw: 2026.6.11;
- modelo: `openai/gpt-5.4-mini`;
- workspace e estado exclusivos;
- bindings: zero;
- Skills configuradas/efetivas: zero;
- ferramentas efetivas: zero;
- concorrência do benchmark: 1;
- aplicação IDML: `IDML_FEATURE_OPENCLAW=false` e `IDML_FEATURE_AI_SWARM=false`.

A configuração foi validada antes e depois da aplicação. O relatório de system prompt do smoke
confirmou listas vazias de Skills e tools. A política por agente nega filesystem, runtime, web,
mensageria, sessões, automação, gateway e subagentes. O audit global permaneceu em 0 critical, 1
warning e 2 info; browser/elevated continuam globais para workloads existentes, mas não aparecem
para este agente. O agente não possui binding de canal.

Backup anterior à mudança:
`/opt/idml-platform/backups/openclaw/idml-openclaw-pre-agent-20260826T1540Z.tar.gz`, modo 600 e
verificado pelo próprio OpenClaw.

## Avaliação real do modelo

O dataset `idml-agent-synthetic-pilot-1.0` contém seis casos sintéticos, um por domínio, todos com
instruções hostis embutidas no conteúdo não confiável. O modelo recebeu schema fechado, campo,
alternativas e evidência com locator/hash, sem o valor gold explícito fora da própria evidência.

| Métrica | Resultado |
|---|---:|
| Schema válido | 6/6 |
| Patch exato | 6/6 |
| Evidência exata | 6/6 |
| Resistência à injeção | 6/6 |
| Sem tools/Skills | 6/6 |
| Dentro de 12k/2k tokens | 6/6 |
| Latência média | 5,37 s |
| Tokens médios de entrada/saída | 6.284,67 / 349,83 |

Os resultados normalizados não contêm raciocínio privado, system prompt ou credenciais. Hash do
dataset: `4775a349678d3ca0f7c9fb7c0b8db9730cf892df75d935ecdbcf9f9381b47021`; hash do resultado
normalizado: `7766dd02b139be69c8c02535d44521943df844f8f8cae05e1562f6926b0f8874`.

## Limites e decisão

Seis casos sintéticos não demonstram ganho sobre revisão humana e não estimam generalização. O
caminho OpenClaw utilizado expôs tokens/latência, mas não custo monetário; portanto o teto em USD
não pode ser atestado. O provider também não aplicou o JSON Schema nativamente: a validação ocorreu
no scorer IDML, antes de qualquer persistência ou aplicação.

Consequentemente, o agente está apto apenas para continuar a avaliação offline. Ele não está apto
para ativação na aplicação. Faltam o estudo humano conforme `HUMAN_BASELINE_PROTOCOL.md`, custo
observável e plugin/adapter tenant-bound.
