# VH-06 — transcrições revisadas por fonte

Checkpoint: 2026-10-08. **Quatorze transcrições corrigidas no desenvolvimento
candidato; VH-06 ainda parcial. Sem implantação ou liberação G-HOMOLOG.**
Continua o lote 2 da lista única VH-01–20, não uma fase adicional. Sucede a prova
de vínculos em `VH1_FORMULA_LINKS_AND_FIDELITY.md`, preservada integralmente.

Checkpoint histórico: sucedido por `VH1_GLYPHS_AND_CONTENT_AUDIT.md`, consolidado
em 2026-10-09. Quatro das cinco revisões seguintes foram resolvidas e uma recebeu
abstenção explícita; os resultados e catálogos deste checkpoint permanecem intactos.

## Escopo da conferência

Foram confrontados visualmente com páginas do PDF autorizado os 60 registros dos
dois catálogos de fórmulas. Esse número não significa todas as expressões matemáticas
dos artigos: há também símbolos em texto formatado fora do MathML catalogado.
Nenhum XML gold foi usado como entrada e não houve chamada de IA neste incremento.

| Artigo | Registros | Correções confirmadas | Sem defeito de transcrição confirmado nesta inspeção | Revisões de glifo/estilo pendentes |
|---|---:|---:|---:|---:|
| e20240086 | 17 | 3 | 14 | 0 |
| e20240135 | 43 | 11 | 27 | 5 |

Ausência de defeito confirmado não é homologação científica. As cinco pendências
também não são cinco erros comprovados. A matemática publicada é preservada,
inclusive quando parece incomum; não se corrige a ciência por conhecimento inferido.

As três correções do primeiro artigo são: agrupamento do índice na fórmula 5,
índice omitido na fórmula 12 e troca indevida de `g` por `a` na fórmula 15.
No segundo foram corrigidos limite de somatório, posição de expoente, argumentos
indevidamente subscritos, símbolo de entrada, cinco fragmentos de algoritmos e duas
barras superiores omitidas. Nestes fragmentos, funções/setas já existentes no texto
vizinho não foram duplicadas dentro do MathML. Expressões e recortes ficam privados.

Fontes preservadas:

- Primeiro PDF: `tmp/sample/1809-4457-esa-30-0825/1809-4457-esa-30-e20240086.pdf`,
  SHA-256 `232fb2428bbdf344af192d24865a4e39848fd4e4fae20f2325aa9ecef6ff2496`.
- Segundo PDF: `tmp/ARQUIVOS TESTE/1809-4457-esa-30-1725/1809-4457-esa-30-e20240135.pdf`,
  SHA-256 `d997b54fdac501397b80e7a4526d6fff705509a99b52e90bd70310d8cdba6157`.

## Implementação e limites de autorização

O contrato `formula-transcription-catalog-1.1` permite a revisão administrativa
rastreável de um catálogo 1.0. Preserva a versão original, MathML/hash anterior,
qualificação IA histórica, IDs, demais campos e decisões. A nova evidência identifica
IDML/PDF, página, região, hash do recorte, horário e motivo da revisão.

`revise_formula_catalog` rejeita fonte/caso/recorte divergente, alteração de campos
fora do escopo, revisão vazia e reaplicação sobre 1.1. É deliberadamente uma revisão
de uma versão 1.0, não um editor genérico nem uma cadeia ilimitada de revisões.
Os catálogos antigos continuam compatíveis. O fluxo existente de enriquecimento
carrega a versão nova, mas mantém suas exigências de autorização/escopo.

A transformação `source-revised-visual-mathml` distingue revisão por fonte de
consenso IA. `human_review_required` permanece verdadeiro; não cria endpoint de
edição pública, não concede alteração autônoma e não amplia a allowlist IA.
O especialista ainda avaliará essas alterações na homologação final.

## Preservação e revalidação

- Os dois IDMLs foram reconvertidos duas vezes: XML/ZIP determinísticos, DTD válida.
- A comparação integral C14N exige exatamente os 14 pares MathML anterior/novo
  autorizados. Restaurando somente esses fragmentos, todo o XML deve ser idêntico
  à candidata anterior. IDs, vínculos, texto, ordem e metadados foram preservados.
- Todos os nomes do pacote e bytes de PDF/imagens permanecem iguais; apenas XML e
  manifesto podem mudar. Testes negativos rejeitam diferenças fora desse escopo.
- Crossref, registros ORCID e catálogo do periódico foram efetivamente consultados
  novamente em 2026-10-08. Os bytes coincidem com os anteriores, mas os horários
  refletem novas respostas HTTP, não renovação artificial. A validade continua
  limitada: novas execuções devem respeitar TTL, escopo e revogação.
- Quatro execuções nativas completas na VPS, uma por vez, com Packtools/SPSValidator
  e política de histórico fixados. Não é E2E da aplicação ativa.

| Artigo | Packtools | SPSValidator |
|---|---|---|
| e20240086 | 0 críticos / 0 erros / 9 avisos | 0 críticos / 0 erros / 9 avisos |
| e20240135 | 0 críticos / 0 erros / 5 avisos | 0 críticos / 0 erros / 5 avisos |

Os achados são exatamente os mesmos do checkpoint de vínculos, sem novos achados
ou avisos removidos. Autoridades positivas e auditoria de histórico preservadas.
Zero erros nestas ferramentas **não comprova fidelidade integral, XPM concluído,
aceite SciELO ou liberação para especialista**.

## Evidências e reprodução

- Relatório público sem texto científico:
  `benchmarks/qualification/reports/vh1-formula-revisions-linux-v1.json`.
- Gate: `python -m ops.gate_vh1_formula_revisions`, integrado ao CI. Confere fontes,
  plano, código, imagens, pares de alterações e resultados nativos. Não concede
  aprovação científica ou de release.
- Qualificador: `ops/qualify_vh1_formula_revisions.py --audit <auditoria-privada>`.
  A auditoria está em `benchmarks/private/formula-review-20261008/corrections.json`;
  requer fontes originais e conectividade aos serviços explicitamente permitidos.
- Execução qualificada: `benchmarks/private/output/vh1-formula-revisions-20261008T131739Z`,
  também em `/opt/idml-platform/private/qualification/`, diretório 0700.
  SHA-256 do plano: `939dcee8ad1b50d09ee22abf51da6301ab7d2bfbb79675416fe2b7c71df88c82`.
  A tentativa local anterior `20261008T131612Z` não é qualificada nem foi enviada
  à VPS; foi preservada como histórico, sem substituir a prova definitiva.
- e20240086 XML: `e0eb4cb4989a1d7ff2c6059f3b57b687fdca40bdf56664dafa4f342b4e772bbe`;
  ZIP: `32e4866803d5b8120453b98b1e1044bfbbd27316b3049ecb227946e3947ec0d8`.
- e20240135 XML: `875dc7ff6d66d14dcc4fa125dad6a7db001e44444c75c5f31a4cbe49f5a1f0c7`;
  ZIP: `1ccac72fffebcf7793e59035ee5a02b3f0177b319f2802f95a1041cea8e91546`.
- Registro: `config/validator-registry-vh1-history.json`, sem alteração.
- V10/V11 reexecutados, com provas novas imutáveis:
  `v10-operational-workflow-vh1-formula-revisions-v1.json` e
  `v11-robustness-mutation-vh1-formula-revisions-v1.json`.

São 82 testes novos: 35 do contrato/construtor, 12 de diferenças XML e 35 do gate.
Os 131 testes focados passaram. Regressão completa: **1.469 testes aprovados,
zero falhas/erros/skip e 88,81% de cobertura de linhas** (11.138/12.542 linhas de
`src`). Evidências locais: `tmp/vh1-formula-revisions-final-tests.xml` e
`tmp/vh1-formula-revisions-final-coverage.json`. Cobertura mede código executado,
não percentual de fórmulas corretas. Não alterar relatórios anteriores para copiar
essa métrica; as provas focadas antecedem a suíte completa.

## Próximo trabalho na mesma VH-06

1. Resolver as cinco revisões de glifo/estilo do e20240135, casos
   `esa-math-notes-inline-005`, `008`, `011`, `016` e `017`, confrontando PDF e
   objetos/fontes do IDML. Registrar correção comprovada ou abstenção justificada;
   não decidir pela aparência de uma fórmula matematicamente mais convencional.
2. Conferir os símbolos dos dois algoritmos em texto formatado fora do MathML:
   pertinência, setas e subscritos. Os 14 reparos acima não alteraram esses nós.
   Não reescrever o algoritmo; corrigir somente divergência demonstrável da fonte.
3. Fechar a conferência de referências, seções, objetos e arquivos já prevista na
   VH-06. Revalidar o pacote final; depois VH-07 consolida resultados e classifica
   avisos. XPM continua VH-02; IA/UI/operação/E2E mantêm seus IDs existentes.

## Ambiente e pendências transversais

API/worker preservados na imagem
`sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`;
readiness/banco/Redis saudáveis antes e depois. Pós-teste: 842 MiB disponíveis,
15 GiB livres em disco e temporários do executor removidos. O teste usou executor
isolado limitado a 192 MiB/0,25 CPU, uma execução por vez.

Ruff global, formatação do incremento, mypy e gates deste incremento passam.
V09 conserva evidência histórica desatualizada e dois scripts históricos ainda
exigem formatação, pendências já atribuídas à VH-17; **CI global não aprovado**.
Sem implantação, ativação IA, edição de decisões humanas ou publicação.
