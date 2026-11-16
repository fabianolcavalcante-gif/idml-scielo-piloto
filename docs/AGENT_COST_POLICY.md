# Política de custo monetário dos agentes

Data: 2026-08-27. Versão do catálogo: `agent-pricing-1.1`.

## Regra operacional

Cada resposta de provedor deve ter seu custo resolvido antes de ser aceita como proposta:

1. custo em micro-USD informado pelo provedor é a fonte prioritária (`provider`);
2. sem custo informado, a aplicação aceita somente estimativa calculada por uma tarifa exata de
   `provider/model` no catálogo versionado (`estimated`);
3. sem uma dessas fontes, a execução termina em `COST_UNAVAILABLE`, sem aceitar o payload do
   agente (`unavailable`).

O cálculo separa entrada sem cache, entrada em cache e saída, usa tarifas em USD por milhão de
tokens e arredonda para cima até o micro-USD. O teto `max_cost_microusd` é aplicado ao custo
resolvido. Tokens, cache, provider, modelo, fonte do custo, versão do catálogo e chave tarifária são
preservados no `AgentRun` append-only, inclusive quando o teto bloqueia a proposta.

O modelo efetivo agora é fixado antes da execução. Um preflight assume zero cache e calcula o pior
caso pelos limites de tokens; se ele exceder o saldo do artigo, nenhuma chamada é feita. Depois da
resposta, o custo real/estimado é novamente validado. O orçamento é agregado por artigo e
serializado por lock do recurso, não apenas aplicado isoladamente a cada chamada.

## Catálogo de produção

O arquivo `config/agent-pricing-v1.json` é a fonte versionada. Chaves devem ser exatas e
normalizadas no formato `provider/model`; não há fallback por família, alias ou aproximação.
Cada tarifa exige fonte e data de vigência.

O modelo observado e fixado é `openai/gpt-5.4-mini`. Em 2026-08-27, a documentação oficial da
OpenAI confirmou US$ 0,75 por milhão de tokens de entrada, US$ 0,075 por milhão de tokens de entrada
em cache e US$ 4,50 por milhão de tokens de saída. A fonte exata consta no catálogo; não há fallback
por família ou outro alias.

Apesar de a fonte monetária estar resolvida, a integração permanece desativada até existir gateway
dedicado/restrito e o Gate G6 de qualidade ser aprovado:

- `IDML_FEATURE_OPENCLAW=false`;
- `IDML_FEATURE_AI_SWARM=false`;
- qualquer modelo diferente do fixado ou sem tarifa falha fechado;
- o Gate G6 continua bloqueado pelo baseline/qualidade, não mais pela tarifa.

## Alteração de tarifa

Uma alteração exige nova versão do catálogo, fonte oficial verificável, data de vigência, testes
de cálculo/limite, revisão do teto por artigo e implantação com flags desligadas. Registros antigos
mantêm `pricing_version` e `pricing_model_key`, portanto não são reinterpretados por preços novos.
