# VH-06 — campos bibliográficos e adjudicação de citações

Checkpoint: 2026-10-09. **23 campos corrigidos em 13 referências; seis diferenças
de citações adjudicadas por fonte. VH-06 permanece parcial.** Mesmo lote 2 e lista
VH-01–20, sem implantação, ativação IA ou liberação G-HOMOLOG.

## Correção implementada

O fallback sem volume podia interpretar páginas, número de fascículo ou a data
de acesso como fonte, incorporando periódico e URL ao título. Também deslocava
iniciais do último autor para o título e confundia editores de capítulos com autores.

`pipeline/reference_parser.py`, chamado por `canonical_mapper.py`, agora delimita
o fim bibliográfico pelo ano de publicação e separa marcadores de extensão antes
de extrair título/fonte. Mantém iniciais consecutivas e determina a fronteira de
autores antes de considerar os ponto-e-vírgulas presentes no título/capítulo.
Não expande nomes, consulta IA ou inventa valores. O ramo com volume não mudou.

| Candidata | Referências afetadas | Campos corrigidos |
|---|---:|---|
| e20240086 | 12 | 8 grupos de autores, 8 títulos, 5 fontes |
| e20240135 | 1 | 1 título, 1 fonte |

O texto integral das 87 referências, DOI, ano, páginas, IDs e vínculos permanecem
exatamente iguais. As alterações estruturadas são trechos literais da fonte,
registrados por offsets/hashes em contrato revisado antes da execução definitiva.
Isso não qualifica qualquer formato bibliográfico nem resolve o tipo de publicação.

## Preservação e validação nativa

Reconversão dupla dos dois IDMLs autorizados, DTD válida e XML/ZIP determinísticos.
Comparação C14N aceita **somente os 23 campos revisados**; todo o restante do XML,
inclusive texto, fórmulas, seções, tabelas, figuras, xrefs e catálogos, é preservado.
PDF/imagens e membros ZIP intactos; gold não entra na conversão.

Quatro execuções sequenciais na VPS, com as mesmas imagens fixadas de Packtools e
SPSValidator, novas consultas reais de autoridades e grants exclusivos de laboratório:

| Artigo | Packtools | SPSValidator |
|---|---|---|
| e20240086 | 0 críticos / 0 erros / 9 avisos | 0 críticos / 0 erros / 9 avisos |
| e20240135 | 0 críticos / 0 erros / 6 avisos | 0 críticos / 0 erros / 6 avisos |

Há **um aviso adicional por ferramenta no segundo artigo**, não uma regressão
omitida. A referência 31 mantém a data de acesso no texto original, mas ainda não
tem `date-in-citation`. Antes a data era absorvida indevidamente pelo título/fonte,
ocultando a ausência da marcação. A regra nativa `validate_not_marked` foi executada
isoladamente nos XMLs anterior/novo e confirmou 0 → 1 aviso, sem alterar regra ou
severidade. Prova: `vh1-reference-access-date-diagnostic-v1.json`.

O gate permite exatamente esse achado conhecido e mantém o estado **não aprovado
integralmente**; não libera XML, publicação, indexação ou homologação. A correção
da marcação de acesso está no próximo incremento bibliográfico da própria VH-06.

## Seis diferenças de citações explicadas

Após congelar os XMLs por hash, o comparador foi reexecutado com gold somente como
referência de avaliação. A adjudicação verifica ocorrências no IDML e na candidata,
referências literais, anos e destinos; publica apenas hashes/contagens.

- Três chamadas de 2018 no gold apontam para referências de 1998/2010. A candidata
  aponta para a referência 13 de 2018, correspondente aos autores citados.
- Três chamadas à referência 37 aparecem no IDML e estão vinculadas na candidata,
  mas sem vínculo no gold. Seu texto e referência de destino foram preservados.
- No segundo artigo, as 39 chamadas bibliográficas continuam coincidentes.

Não houve alteração de vínculos neste incremento. O resultado bruto do comparador
continua intacto (`needs_review` no primeiro); a adjudicação separada registra
`source_qualified_development`, não aceite humano ou dispensa formal.

Os sete achados integrais brutos do primeiro artigo (dois metadados/cinco fórmulas)
e os 23 de fórmulas do segundo continuam visíveis para triagem com provas anteriores.
Não são 30 novos defeitos nem foram automaticamente aceitos. Contagens/estrutura de
seções, referências, figuras, tabelas, notas e mídias continuam preservadas.

## Evidências e testes

- Contrato: `benchmarks/qualification/contracts/vh1-reference-field-delta-v1.json`.
- Provas públicas: `vh1-references-linux-v1.json`, `vh1-reference-audit-v1.json`
  e `vh1-reference-access-date-diagnostic-v1.json`, em `benchmarks/qualification/reports/`.
- Execução definitiva: `benchmarks/private/output/vh1-references-20261009T104259Z`,
  também em `/opt/idml-platform/private/qualification/` com acesso privado.
  Plano SHA-256: `59153bcd5b79be67dd456f586c80cec95423bdeff7e9838d72098844c5eca564`.
  Inspeção `103949Z` e tentativa local `104216Z` preservadas, sem qualificação nativa.
- e20240086 XML: `aeaac3caa534d442b13d67881b67a650bb42c5c93f6184dee8fc4a1225e54e63`;
  ZIP: `2c53550ad878f459356505f407567b25b368176114018e0eca9e6b91328cf55b`.
- e20240135 XML: `ccc0553baa5c11d17b7ce1fd47d7e4da766a59543c2ae8e2bc41d2269ff51992`;
  ZIP: `146f934528744f5c048b5e5282018f4cf840bd5fb74fb24e9948ba71c173e025`.
- **95 testes novos**: 32 de parsing/pipeline, 16 de diferença integral, 32 do gate,
  7 de evolução de evidências e 8 de adjudicação. **150 focados aprovados**, JUnit
  `tmp/vh1-reference-focused.xml`; V03 real mantém 106/106 stories.
- Regressão final após o ajuste do gate histórico: **1.635 testes aprovados,
  cobertura de linhas 88,99%** (11.189/12.573), sem falhas, erros ou testes
  ignorados. Provas: `tmp/vh1-reference-final-tests-v2.xml` e
  `tmp/vh1-reference-final-coverage-v2.json`. Os 41 testes do gate de histórico
  também foram reexecutados separadamente e passaram.
- V10/V11 reexecutados em `v10-operational-workflow-vh1-references-v1.json` e
  `v11-robustness-mutation-vh1-references-v1.json`. Esses relatórios são focados,
  anteriores à regressão completa; seus campos de total/cobertura permanecem nulos,
  sem copiar resultados futuros ou modificar a evidência emitida.
- Ruff global, mypy (109 arquivos), formatação do incremento e gates específicos
  passam. Varredura 7C-08 conserva somente a falha histórica V09 em VH-17;
  formatação dos dois scripts históricos também permanece ali. CI global não aprovado.

As provas nativas antigas não foram reescritas para substituir hashes. A evolução
do mapper só é aceita por `vh1_source_evolution.py` quando seu hash anterior coincide,
o hash atual está ligado ao novo ensaio fixado e **todas** as verificações desse
ensaio (incluindo diferença XML exata, assets, imagens e achados) passam. Fonte
alterada, relatório ausente/adulterado ou aviso removido invalidam essa continuidade.

A primeira regressão completa detectou um gate histórico que ainda exigia o hash
antigo do mapper. Sua ligação ao mesmo mecanismo de requalificação foi corrigida;
o resultado inicial com uma falha permanece preservado, sem ser anunciado como aprovado.

VPS após ensaio: API/worker na imagem anterior `4fcf4766…`, readiness/banco/Redis
saudáveis, 1.126 MiB disponíveis e 15 GiB livres; temporários do executor removidos.
Nenhuma chamada OpenClaw, ativação, implantação ou interferência no outro sistema.

## Próximo incremento delimitado — ainda VH-06

1. Marcar datas de acesso explícitas e separar publicação de acesso, sem inferir datas.
2. Tratar referências de livros, capítulos, tese e recurso online pelo tipo correto,
   incluindo título de capítulo, fonte, editora/edição ou grau quando comprovados.
   O builder ainda usa `publication-type="journal"` para todas; o texto composto de
   capítulos/edições não equivale a segmentação final desses campos.
3. Conferir os campos estruturados das 87 referências, com testes negativos e
   abstenção para formato não suportado, mantendo texto original e evidência.
4. Encerrar a triagem dos achados brutos com as correções de fonte já comprovadas;
   depois consolidar VH-07 (validadores aplicáveis e avisos). A única dúvida de glifo
   permanece explicitamente para o especialista, sem nova pesquisa indefinida.

Esses pontos pertencem à entrega de referências/conteúdo já prevista na VH-06;
não ampliam o escopo para um parser bibliográfico universal nem abrem nova fase.
