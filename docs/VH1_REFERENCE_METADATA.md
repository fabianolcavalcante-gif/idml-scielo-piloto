# VH-06 — tipos bibliográficos e datas de acesso

Checkpoint consolidado em 2026-10-13, com qualificação nativa executada em
2026-10-09. **Incremento bibliográfico entregue no código candidato; VH-06 parcial.**
Mesmo lote 2 e lista VH-01–20. Sem implantação, ativação IA ou liberação G-HOMOLOG.

Checkpoint histórico, sucedido em 14/10 por `VH1_REFERENCE_TYPES_AND_CONTENT_TRIAGE.md`.
Os três tipos pendentes receberam classificação com fonte; a triagem integral foi
registrada separadamente, preservando os resultados e limites deste checkpoint.

## Implementação

O gerador deixava todas as referências como `journal`, mesmo quando a fonte
descrevia livros, capítulos ou tese. O parser de metadados agora interpreta padrões
literais da bibliografia ESA e o modelo canônico 1.5.0 conserva os novos campos e
sua evidência: tipo, título de parte, editores, editora/local, edição, descrição e
data de acesso. O schema 1.4.0 foi preservado; a migração não inventa classificação
nem novos dados para snapshots antigos.

Foram ajustadas 15 referências: 14 no e20240086 e uma no e20240135. Há quatro datas
de acesso, quatro edições e dois intervalos de páginas de capítulos agora marcados.
Os títulos de livros/teses passam para `source`; capítulos usam `part-title` e
editores pessoais separados dos autores. Um organizador institucional permanece
literal em `comment`, sem fingir ser pessoa física ou atribuir-lhe autoria.

| Tipo na candidata | e20240086 | e20240135 |
|---|---:|---:|
| Artigo de periódico | 38 | 34 |
| Livro, incluindo capítulos | 11 | 0 |
| Tese | 1 | 0 |
| Tipo ainda não resolvido (`other` + revisão) | 2 | 1 |

Padrões sintáticos são limitados ao layout qualificado, não uma base bibliográfica
universal. URL sozinha não determina tipo. As referências 44/49 do primeiro artigo
e 31 do segundo continuam com `reference_type_unresolved`, propagado ao estado de
revisão do artigo. Não são declaradas páginas web nem aprovadas semanticamente.

Datas de acesso só são marcadas quando explícitas, únicas e válidas no calendário.
Datas ambíguas, impossíveis, repetidas ou em formato não suportado geram motivo de
revisão, sem preenchimento por inferência. O texto original e a expressão de acesso
não são traduzidos. Referência sem campos reconhecidos não produz `element-citation`
vazio: conserva o texto e a pendência, sem alegar que atende à marcação SPS completa.

## Base normativa e preservação

A [especificação oficial SPS 1.10](https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit)
determina `part-title` para capítulos, `source` para livros e
`date-in-citation content-type="access-date"`, sem atributo adicional nessa data.
A cópia textual previamente qualificada tem SHA-256
`09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef`.
Não foi usada a orientação antiga de `chapter-title` da documentação SPS 1.7.

Reconversão dupla dos dois IDMLs autorizados, DTD válida e XML/ZIP determinísticos.
O contrato revisado permite somente as 15 citações estruturadas, com hashes e
offsets literais. Após revertê-las, todo o XML deve ser idêntico por C14N.
Texto integral das 87 referências, IDs, autoria, ano, DOI, URLs, xrefs, fórmulas,
seções, tabelas, figuras, PDF/imagens e catálogos anteriores foram preservados.

A auditoria das 87 referências confrontou os textos com stories do IDML e verificou
a presença literal de todos os valores estruturados. Isso prova rastreabilidade
textual, **não** que cada valor foi atribuído ao papel bibliográfico correto.
Gold foi lido somente após congelar as candidatas, para comparação posterior.
Os sete/23 achados brutos integrais e as seis adjudicações anteriores permanecem
visíveis; nenhuma divergência científica foi apagada ou aprovada automaticamente.

## Validação na VPS

Mesmas imagens fixadas de Packtools/SPSValidator e registro de histórico, consultas
reais de autoridades e grants exclusivos de laboratório; execuções sequenciais,
limitadas, sem mudar a aplicação ativa.

| Artigo | Antes, por ferramenta | Depois, por ferramenta |
|---|---|---|
| e20240086 | 0 críticos / 0 erros / 9 avisos | 0 / 0 / 6 |
| e20240135 | 0 críticos / 0 erros / 6 avisos | 0 / 0 / 5 |

Exatamente quatro avisos de texto sem marcação desapareceram por ferramenta;
nenhum achado novo, suprimido ou rebaixado. O gate verifica a diferença com
multiplicidade, as candidatas, autoridades, fontes e todos os achados restantes.
Zero erro formal não equivale a aprovação científica, indexação ou liberação.

Execução final: `benchmarks/private/output/vh1-reference-metadata-20261009T195009Z`,
também em `/opt/idml-platform/private/qualification/`, com permissões privadas.
Plano SHA-256: `1af84936d5111f50e96babdaa2939e1a829abd8e07814c0383b892de1a2c7857`.
Os grants foram válidos no ensaio de 09/10; não autorizam novas execuções após vencer.
Inspeção `194458Z`, tentativa local `194708Z` e ensaio anterior `194746Z` não são
substitutos da prova final e permanecem preservados quando existentes.

Hashes finais:

- e20240086 XML: `72886a9fb15a374459779ad2c3c97f1ee3ef90adeec1809d3dde53a4700d3c55`;
  ZIP: `dca147fb06dd8a07d164e3df75f38a254f33b895aa49950cc70097d4f8e7b4c1`.
- e20240135 XML: `e0ad6a89cbcfee6ba4b924cf1c1b2d13c2ca30c162aadf5ca707d0af54533239`;
  ZIP: `cf410d72179431e2eebb7b66b78d7caec92846db0031a8bbb83ebded3bf5a6b3`.

## Testes e evidências

- 109 testes novos: 49 de parsing/pipeline/migração, 16 de diferença XML,
  36 do gate e oito de auditoria; 259 direcionados aprovados.
- Relatórios imutáveis: `vh1-reference-metadata-linux-v1.json` e
  `vh1-reference-metadata-audit-v1.json`, em `benchmarks/qualification/reports/`.
- Contrato: `benchmarks/qualification/contracts/vh1-reference-metadata-delta-v1.json`.
- V10/V11 reexecutados, com sucessores `*-vh1-reference-metadata-v1.json`, ligados
  ao JUnit `tmp/vh1-reference-metadata-focused-final.xml`. Totais de regressão e
  cobertura ficam nulos nesses relatórios focados; não reutilizam números antigos.
- Regressão integral final: **1.744 testes aprovados, 89,10% de cobertura de linhas**
  (11.297/12.679), sem falhas, erros ou testes ignorados. Evidências:
  `tmp/vh1-reference-metadata-full-tests-v2.xml` e
  `tmp/vh1-reference-metadata-full-coverage-v2.json`. A execução anterior teve
  1.730 aprovações e duas falhas de relatórios V10/V11 desatualizados; evidência
  preservada. Também foi corrigida, antes do ensaio nativo final, a emissão de
  citação estruturada vazia identificada nos testes sintéticos iniciais.
- V03 confirma 106/106 stories nos dois IDMLs; Ruff global, mypy (110 módulos),
  formatação do incremento e gates VH anteriores/atual passam. Requalificação
  `tmp/vh1-reference-metadata-7c08.json`: apenas V09 histórico continua falhando;
  demais gates dessa matriz passam. Não é aprovação global de CI.
- Gate novo integrado ao CI. Provas históricas só aceitam evolução de fonte pela
  sucessora nativa fixada; não foram regravadas nem receberam dispensa de hashes.
- Aplicação ativa, banco/Redis e readiness verificados em 13/10: saudáveis, imagens
  API/worker preservadas. Sem chamadas de IA, deploy ou alteração de hardware.

## Restante delimitado da VH-06

1. Resolver os três tipos pendentes com fonte/decisão bibliográfica qualificada;
   não ampliar o parser a todos os formatos de referência.
2. Consolidar a triagem dos sete/23 achados brutos com as provas existentes,
   separando defeito real, diferença de representação e abstenção científica.
3. Preservar a única dúvida de glifo para o especialista, sem pesquisa indefinida.

Depois, VH-07 consolida validadores aplicáveis e avisos. XPM, IA, interface,
implantação, segurança e E2E continuam nos IDs já aprovados. V09/formatação
históricos permanecem VH-17; este incremento não aprova o CI global ou G-HOMOLOG.
