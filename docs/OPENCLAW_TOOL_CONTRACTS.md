# Contratos de ferramentas OpenClaw — Fase 6

Status: implementado, não habilitado na VPS. Versão: `openclaw-idml-policy-1.0`.

## Limite de confiança

O backend IDML é a única autoridade de autenticação, empresa, job, recurso, item de revisão e
snapshot. O OpenClaw recebe apenas um envelope mínimo e não recebe credenciais de banco, caminho
de artefato, token da aplicação ou acesso direto ao gateway por usuários do produto. Conteúdo de
IDML/PDF é sempre marcado como `UNTRUSTED_ARTICLE_CONTENT`.

O agente existente na VPS não pode ser reutilizado para conteúdo hostil: ele tem capacidades mais
amplas e segue o modelo de confiança de assistente pessoal. A ativação exige um agente dedicado e
uma atestação que comprove todas as restrições abaixo. O OpenClaw documenta que `tools.deny`
prevalece sobre `tools.allow`, que grupos como `group:fs` podem ser negados e que plugins podem
declarar `outputSchema` validado: [política de ferramentas](https://docs.openclaw.ai/gateway/config-tools),
[plugins e schemas](https://docs.openclaw.ai/plugins/building-plugins).

## Escopo obrigatório

Toda invocação carrega e confere:

- `organization_id`;
- `job_id` (inclusive `null`, que só corresponde a item sem job);
- `resource_id`;
- `review_item_id` e sua versão esperada;
- `base_snapshot_id` canônico;
- domínio assistido.

Inconsistência de qualquer identificador encerra a chamada antes de preparar o envelope. Não há
consulta livre; as consultas SQL estão encapsuladas e sempre incluem a empresa e os objetos do
escopo.

## Allowlist fechada

| Ferramenta | Acesso | Efeito |
|---|---|---|
| `idml_read_review_item` | item exato | leitura sanitizada |
| `idml_read_canonical_fragment` | campo do item; contexto `RichText` acoplado quando aplicável | leitura sanitizada |
| `idml_read_evidence` | evidência do item | leitura, locator e hash |
| `idml_read_validation_issues` | evidência de validação do item | leitura |
| `idml_propose_patch` | saída fechada do domínio | proposta, sem gravação canônica |
| `idml_validate_patch` | item/snapshot/version exatos | build e validação em memória |

São proibidos shell/exec, filesystem global, SQL livre, browser, rede, elevated, release e criação
de agentes. O template auditável está em `config/openclaw-idml-agent-policy-v1.json`; ele permanece
com `enabled=false` e nenhuma Skill carregada.

## Fluxo e invariantes

1. O backend lê e sanitiza somente o recorte autorizado.
2. O backend monta `assistive-input-1.1` para evidência curta legada, `assistive-input-1.2` para
   evidência segmentada, sem IDs de snapshot repetidos nem cópia separada das validações já presentes
   em evidências, ou `assistive-input-1.3` para a transição atômica de fórmula. Conteúdo longo não é
   truncado: cada segmento e o conjunto completo são autenticados, e estouro do limite total falha fechado.
3. O provider recebe prompt e JSON Schema versionados, allowlist e timeout.
4. A saída é validada novamente pelo backend.
5. Cada referência de evidência deve coincidir em ID, tipo, locator e hash legado ou conjunto
   ordenado de hashes individuais mais hash agregado; cada operação declara quais evidências a sustentam.
6. O patch deve ficar no domínio e no campo do item de revisão.
7. Uma alteração em `RichText` deve substituir `plain.value` e o array completo `inlines` na mesma
   proposta; patch escalar, parcial ou com caminhos duplicados é rejeitado antes do build.
8. Uma fórmula deve substituir `source.value` e `representation` na mesma proposta; MathML aceita
   somente elementos de apresentação permitidos, tamanho limitado, `display` compatível e nenhum DTD,
   entidade externa, script ou atributo de navegação.
9. O snapshot deve continuar sendo a ponta atual da linhagem.
10. O JATS candidato é construído e validado sem persistir a alteração.
11. Uma `AgentProposal` imutável é encaminhada para revisão humana.

Não existe ferramenta de aplicar patch ou aprovar release. O endpoint público desta fase é
consultivo: capacidades, runs e leitura tenant-bound de propostas. A CLI oficial também expõe
timeout e saída JSON, mas isso não substitui as verificações no backend:
[CLI do gateway](https://docs.openclaw.ai/cli/gateway).

## Ativação futura

A configuração live deve ser confrontada com o schema da versão instalada (`openclaw config
schema`), conforme recomendado na
[referência de configuração](https://docs.openclaw.ai/gateway/configuration-reference). A feature
somente poderá ser habilitada após: plugin interno com `outputSchema`, agente dedicado, atestação
completa, benchmark real por domínio, teste de injeção e orçamento aprovados.
