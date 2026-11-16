# H1 — Resolução de afiliações no runtime fixado

2026-09-30. Correção candidata, sem promoção da aplicação ou dos validadores ativos.
Continua a investigação registrada em `H1_COUNTRY_CODES_AND_FRONT_TRIAGE.md`.

## Correção

O caminho `TextContribsValidation` não recebia os vínculos resolvidos (`affs`),
embora o XML tivesse xref válido e o modelo `XMLContribs` resolvesse o destino.
`ops/affiliation_compat.py` substitui apenas a ligação do modelo de texto no módulo
de validação por uma visão que fornece os IDs efetivamente resolvidos.
As regras nativas, severidades, demais campos e XML permanecem intactos.

Só referências `ref-type=aff` com destinos de tipo `aff`, únicos no documento e
presentes no front do mesmo artigo/subartigo são aceitas. Todos os destinos de
cada referência devem resolver; um alvo válido não encobre outro inválido.
Lista de IDs é suportada; referências repetidas são deduplicadas. Não se empresta
afiliação de outro escopo. Casos fora desse suporte permanecem bloqueados, sem
afirmar que toda referência entre escopos é normativamente proibida.

Wrappers separados preservam contrato e caminho fixo do broker. SPSValidator
mantém a compatibilidade PDF anterior. Não há filtros de mensagens/waivers,
modificação do XML ou atualização das dependências upstream.

## Imagens de laboratório

- Packtools: `sha256:c1fcc21b4e6e26136aa33543c239ec37bee1cc613c3356f310f223a10acb882e`.
- SPSValidator: `sha256:e2a57de6c2f6d8bb5fa466fbe4fa375caa4a893769d8d22c496c958a0d57fab4`.

Bases: Packtools `412a7502…` e SPSValidator/PDF `3d3f136c…`, sem downloads no build.
Registro: `benchmarks/qualification/contracts/h1-affiliation-compat-registry.json`.
Registro ativo e perfis padrão da aplicação não foram substituídos.

## Contraprovas

Doze testes locais do resolvedor: referência simples, lista, repetição, alvo
ausente, tipo incorreto, destino não aff, duplicação, rid vazio, escopo e mistura
de alvos válidos/inválidos. O XML e os dados de entrada não são modificados.

Matriz sintética executada nas duas imagens Linux: dez casos por imagem, todos
com resposta esperada e decisões das demais regras inalteradas. Afiliação válida
e lista válida → OK; oito casos negativos → ERROR. A instalação é idempotente.
Não é prova de cobertura de todos os templates, colaborações ou subartigos.

Regressão local completa: 708 testes aprovados, 3 avisos e 88,00% de cobertura
do pacote da aplicação (esse percentual não cobre scripts ops nem mede conformidade
SciELO). Evidências: `tmp/h1-affiliation-tests.xml` e
`tmp/h1-affiliation-coverage.json`. Ruff aprovado nos cinco arquivos Python.

## Resultado nos artigos reais

Os mesmos XMLs e ZIPs da qualificação de países foram reutilizados, com hashes
inalterados. Ambos completaram Packtools e SPSValidator:

| Artigo | Antes: críticos / erros / avisos | Agora: críticos / erros / avisos |
|---|---|---|
| e20240086 | 25 / 4 / 12 | 22 / 4 / 12 |
| e20240135 | 10 / 4 / 8 | 6 / 4 / 8 |

Contagens iguais entre as duas ferramentas. A regra de afiliação desapareceu
dos achados; demais códigos/erros/avisos preservados. Os sete alertas indevidos
foram resolvidos por fornecer os vínculos reais à regra nativa, não por dispensá-la.
Os dois candidatos continuam reprovados. Evidência:
`benchmarks/qualification/reports/h1-affiliation-linux-v1.json`.

Serviços existentes sem reinício; scratch e sockets limpos. Quatro cópias privadas
remotas removidas, originais locais preservados. Readiness: banco/Redis OK;
MemAvailable final 1.092.176 KiB. Não houve promoção de imagem/registro ativo.

## Próximo incremento

Separar consultas de registro DOI/ORCID/volume/seção não disponíveis no runtime
isolado de defeitos de conteúdo, mantendo reprovação/indisponibilidade explícita.
Não usar ausência de consulta como prova de identificador inexistente nem como
aprovação. Depois corrigir os demais achados com fonte, completar XPM e executar
H2/H3 (promoção com rollback e fluxo API/worker/UI). G-HOMOLOG permanece pendente.
