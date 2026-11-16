# Schemas de saída dos agentes — Fase 6

Versão canônica do contrato: `agent-proposal-1.1`. A versão 1.0 permanece somente como artefato
histórico e não é aceita em novas execuções assistivas. O laboratório também admite o contrato de
transporte restrito `agent-proposal-intent-1.0`, sempre convertido e revalidado pelo backend para a
versão canônica antes dos críticos.

Há um schema fechado comum e uma especialização por domínio em `schemas/agents/`. Em runtime, o
backend gera o schema inline a partir do mesmo modelo Pydantic e fixa `domain` no valor da tarefa.
Propriedades adicionais são rejeitadas.

## Campos obrigatórios

| Campo | Regra |
|---|---|
| `schema_version` | valor exato `agent-proposal-1.1` |
| `domain` | um dos seis domínios configurados e igual à tarefa |
| `patch` | 1–5 operações `replace`; cada uma contém `evidence_ids`, caminho existente, escopado e sem duplicação |
| `confidence` | número entre 0 e 1 |
| `evidence` | 1–20 referências existentes no item |
| `alternatives` | 1–10 alternativas explícitas |
| `reason` | 20–2000 caracteres, sem instruções para mudar política/release |
| `needs_human` | obrigatório; deve ser verdadeiro abaixo de 0,85 |

Uma referência usa `evidence_id`, `source_kind` e `locator`, mais exatamente uma representação:
`excerpt_sha256` para evidência histórica curta; ou `segments` ordenados com `segment_id`, `position`
e `text_sha256`, acompanhados de `aggregate_sha256`. Não basta o formato ser válido: todos os valores
são comparados com a evidência tenant-bound entregue pelo backend. Segmentos devem ser contíguos,
únicos e completos; o hash agregado vincula metadados, ordem, contagem, tamanho e hashes individuais.
O conjunto de IDs citado nas operações deve ser exatamente igual ao conjunto declarado em
`evidence`: evidência ausente, externa, duplicada ou declarada sem uso rejeita toda a proposta.
Os hashes são recalculados pelo backend sobre o conteúdo sanitizado efetivamente entregue ao agente.

## Domínios e caminhos

| Domínio | Prefixos permitidos |
|---|---|
| `metadata` | `/front` |
| `contributors_affiliations` | `/front/contributors`, `/front/affiliations` |
| `structure` | `/body` |
| `references` | `/back/references` |
| `figures_tables` | `/body`, `/assets` |
| `math_notes` | `/body`, `/back/notes`; piloto somente |

O prefixo do domínio é uma primeira barreira. A operação também precisa estar no campo do
`ReviewItem`, atingir um caminho existente, produzir mudança real, preservar o modelo canônico e
passar pelo build e validação JATS determinísticos.

Para `RichText`, `plain.value` e `inlines` formam um único valor semântico. Se o fragmento trouxer
`atomic_rich_text`, a proposta deve conter as duas operações indicadas: uma substitui o texto
simples e a outra substitui o array completo de inlines. A concatenação de `inline.text` deve ser
exatamente igual a `plain.value`; não é permitido alterar somente um inline individual.
As duas operações do mesmo `RichText` também devem citar a mesma lista de evidências.

## Intent de evidência para RichText longo

Quando uma evidência possui mais de um segmento autenticado, o alvo é `RichText` atômico e
`current_inlines` está vazio, o proponente não precisa recopiar o texto longo. Ele retorna
`agent-proposal-intent-1.0`, com uma operação por path e `value_source` fixado em
`authorized_evidence` mais o `evidence_id` já declarado. Valor literal não existe nesse schema.

O backend exige exatamente a referência de evidência entregue ao agente, incluindo locator, hashes,
ordem e hash agregado; confere domínio, paths, revisão humana e ausência de override de política;
remonta os segmentos e materializa de forma sincronizada `/plain/value` e `/inlines`. Os hashes da
saída do provider e da proposta materializada são registrados separadamente. Evidência de um único
segmento, inline preexistente ou template com mais de um inline permanece no contrato literal
`agent-proposal-1.1`, evitando reconstrução automática de formatação editorial.

## Rejeição

Saídas sem evidência, com campo extra, domínio divergente, tipo incorreto, política embutida,
locator/hash divergente, versão atrasada, snapshot fora da ponta ou custo excedido não geram
proposta aplicável. O run imutável registra somente hashes, provider/modelo, versões, tokens, custo,
latência, tentativas e código normalizado; raciocínio privado e mensagem bruta de exceção não são
persistidos.
