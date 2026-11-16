# VH-06 — tipos bibliográficos e triagem final de conteúdo

Checkpoint: 2026-10-14. Continuação do lote 2 e da lista única VH-01–20.
**VH-06 concluída no desenvolvimento candidato, com abstenção científica explícita.**
Sucede `VH1_REFERENCE_METADATA.md`; todos os relatórios anteriores permanecem
imutáveis. Sem implantação da candidata, ativação OpenClaw ou liberação G-HOMOLOG.

## Três referências classificadas com evidência

| Artigo / posição | Tipo estruturado | Base da decisão | Limite preservado |
|---|---|---|---|
| e20240086 / 44 | `webpage` | Página institucional do SAAE com o mesmo título e instituição | A página atual não comprova a edição de 2020; ano e URL legada do IDML preservados, localizador sujeito a revisão |
| e20240086 / 49 | `report` | Publicação técnica SRAC 3700, título/autoria/data conferidos no cabeçalho do PDF oficial | Não acrescentar número ou expandir nomes ausentes da citação original |
| e20240135 / 31 | `report` | Registro oficial OMS, relatório 106 de 05/05/2020 | Associação curada por instituição, assunto, número e data, não igualdade literal de títulos; título e URL genérica originais preservados |

Fontes institucionais consultadas em 13/10:
[SAAE](https://saaesaocarlos.com.br/servicos/agua/mananciais/),
[SRAC](https://srac.msstate.edu/pdfs/Fact%20Sheets/3700%20Pond%20Aeration.pdf) e
[OMS](https://www.who.int/publications/m/item/situation-report---106).
O procedimento de PDF incluiu renderização e inspeção visual da primeira página
da publicação SRAC, não apenas extração textual. Snapshots e imagem de conferência
ficam no cofre privado `vh1-reference-sources-20261013T183201Z`.

Não foi criada uma regra “tem URL = webpage”. O parser conservador continua
abstendo-se quando não reconhece um tipo. O novo `reference-type-catalog-1.0`
é enriquecimento administrativo qualificado, não decisão autônoma de IA:

- Liga citação integral, alvo anterior, IDML, perfil, DOI e respostas institucionais
  por SHA-256. Fonte nova exige regra revisada e catálogo autorizado.
- Reatribui somente os campos literais já existentes: título para `source` e
  instituição para `publisher-name`; não traz texto do site para a citação.
- Não substitui decisões humanas, estados ambíguos ou alvos alterados. Aplicação
  atômica e idempotente; reaplicação parcial ou evidência adulterada é recusada.
- Integração ao pipeline/worker por bundle de empresa/artigo, com destino,
  validade, revogação e evidência. Registros públicos têm prazo de sete dias;
  manter bytes históricos não equivale a renovar sua validade para novos jobs.
- Três decisões continuam marcadas como pendentes de revisão humana; duas também
  conservam alerta de localizador. Não se tornam três referências “homologadas”.
- Modelo canônico 1.6.0 admite `webpage` e `report`. Migração 1.5 → 1.6 não
  classifica registros antigos nem preenche campos por inferência; schema 1.5 preservado.

As 87 referências agora somam **72 journal, 11 book, 1 thesis, 1 webpage e 2 report**.
Não resta `reference_type_unresolved` nesses dois artigos. Isso não comprova
classificação universal nem elimina os limites editoriais explicitados acima.

## Preservação e prova nativa

Reconversão dupla dos dois IDMLs, DTD válida e XML/ZIP determinísticos. A diferença
integral C14N admite somente as três citações estruturadas do contrato revisado.
Textos integrais das 87 referências, autores, anos, DOI, URLs, datas de acesso,
demais nós XML, fórmulas, xrefs, PDFs, imagens e nomes de membros ZIP preservados.
O XML gold só foi aberto depois de congelar as candidatas, para avaliação posterior.

Quatro execuções na VPS em 14/10, sequenciais, nos mesmos executores fixados
Packtools/SPSValidator, limitadas a 192 MiB e 0,25 CPU. Consultas de autoridades
renovadas com respostas HTTP reais e grants exclusivos de laboratório.

| Artigo | Packtools | SPSValidator |
|---|---|---|
| e20240086 | 0 críticos / 0 erros / 6 avisos | 0 críticos / 0 erros / 6 avisos |
| e20240135 | 0 críticos / 0 erros / 5 avisos | 0 críticos / 0 erros / 5 avisos |

Achados exatamente iguais ao checkpoint anterior: nenhum removido, rebaixado ou
acrescentado. O gate confere multiplicidade, imagens, candidatas, fontes,
autoridades e histórico. Zero erro nessas ferramentas não é aprovação científica,
conclusão do XPM, aceite SciELO ou autorização de publicação.

Execução final: `benchmarks/private/output/vh1-reference-types-20261014T104156Z`,
também em `/opt/idml-platform/private/qualification/`, com permissões privadas.
Plano SHA-256: `0c564a1e42b6d33a8bba97055319a245d971c9d65f76afe5f4ef5e4255fd7857`.
Inspeção `20261013T184419Z` e execução local `20261013T184553Z` ficam preservadas,
mas não substituem a prova final. Não reusar grants vencidos.

Hashes finais:

- e20240086 XML: `fa0d09731b268de44b51c5f80ebce5a5165e4cc400c205aca7cacee657c71048`;
  ZIP: `52561e645180a44ccc1c4bd7899f842258199f0511e5190a55ca404899c7ec01`.
- e20240135 XML: `b29d362fea52e648a3adc3930e406784732b04cdbf6efce7a0b6deea9a332c92`;
  ZIP: `2c4aad2df2b1b61316d6bf2f44795c0b4c1acbb7088fb6fd822020a974f9583f`.

## Triagem dos 30 achados brutos, sem ocultá-los

O comparador bruto continua registrando sete/23 achados bloqueantes e `passed=false`.
Um relatório separado liga **cada ocorrência** à candidata, ao hash da diferença,
à revisão visual histórica, ao catálogo exato e à fonte. Não altera o comparador,
sua severidade, o XML ou o resultado formal de release.

| Classificação da triagem | e20240086 | e20240135 |
|---|---:|---:|
| Grafia acentuada do periódico conforme perfil | 1 | 0 |
| Fronteira de palavras preservada conforme IDML | 1 | 0 |
| Fórmula revisada por fonte, sem defeito confirmado naquela inspeção, diferente do gold | 4 | 11 |
| Fórmula corrigida por fonte em checkpoint anterior, ainda diferente do gold | 1 | 11 |
| Abstenção científica de glifo | 0 | 1 |

A contagem é de ocorrências, não de novos defeitos ou correções desta execução.
O comparador textual não lê todos os atributos MathML: delimitadores em `mfenced`,
letras caligráficas em `mathvariant` e tokenização podem produzir textos diferentes.
Isso **não permite declarar automaticamente equivalência das 28 fórmulas**:
o normalizador MathML existente concorda em apenas uma delas. As demais decisões
dependem das revisões por fonte já documentadas, não da semelhança matemática.

Para cada fórmula, a auditoria verifica identidade/posição e MathML exato do
catálogo qualificado. Revisões posteriores precisam ligar transcrição anterior,
nova, PDF e exigência de revisão humana. A inspeção de 60 registros e as 18
correções históricas continuam sendo as provas de fonte; não foram repetidas
nem substituídas por uma aprovação do gold.

A única dúvida científica continua `esa-math-notes-inline-005`: glifo ambíguo e
PDF externo de equação indisponível. Mantida para o especialista, sem inferir uma
fórmula convencional. Os símbolos editoriais incomuns dos algoritmos, comprovados
no IDML/PDF, também não foram “corrigidos” por convenção. As seis adjudicações
bibliográficas anteriores permanecem no novo relatório de auditoria.

## Testes e rastreabilidade

- **148 testes novos**, incluindo classificação/bundle/worker/migração (54),
  gate nativo (39), diferença XML (17), auditoria literal (8) e triagem (30).
- **407 testes direcionados aprovados**, JUnit
  `tmp/vh1-reference-types-focused-final.xml`. V03 real: 106/106 stories preservadas.
- V10/V11 reexecutados e relatórios sucessores imutáveis `*-vh1-reference-types-v1.json`.
  Os números de regressão integral/cobertura nesses relatórios focados ficam nulos.
- Regressão integral: **1.892 testes aprovados, 89,20% de cobertura de linhas**
  (11.411/12.793), sem falhas, erros ou testes ignorados. Provas:
  `tmp/vh1-reference-types-full-tests.xml` e
  `tmp/vh1-reference-types-full-coverage.json`. Cobertura mede execução de código,
  não percentual de XMLs ou fórmulas corretos.
- Ruff global, mypy (111 módulos) e formatação dos arquivos do incremento passam.
- Novos gates nativo e de triagem integrados ao CI. Cadeia de provas aceita evolução
  de fontes apenas pela sucessora nativa fixada; relatórios antigos não foram regravados.
- Matriz `tmp/vh1-reference-types-7c08.json`: todos os gates passam, exceto V09
  histórico. V09 e formatação dos dois scripts históricos continuam sob VH-17;
  não declarar CI global aprovado.

Provas públicas, sem texto científico, em `benchmarks/qualification/reports/`:
`vh1-reference-types-linux-v1.json`, `vh1-reference-types-audit-v1.json` e
`vh1-content-triage-v1.json`. Contrato:
`benchmarks/qualification/contracts/vh1-reference-types-delta-v1.json`.
Scripts: `qualify_vh1_reference_types`, `audit_vh1_reference_types`,
`triage_vh1_content`, `gate_vh1_reference_types` e `gate_vh1_content_triage`, em `ops/`.

## Próximo item delimitado

VH-06 encerrada no desenvolvimento candidato; próximo item: **VH-07**, consolidar
os validadores aplicáveis, consultas e avisos do pacote exato.
A dependência **VH-02/XPM** continua aberta e não pode ser declarada cumprida pelo
resultado de Packtools/SPSValidator. IA, interface, operação, implantação e E2E
mantêm os IDs VH-08–20; não abrir novos lotes ou repetir pesquisa indefinida do glifo.

API/worker ativos preservados na imagem `sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`.
Readiness, banco e Redis saudáveis antes/depois do ensaio. Pós-teste: 1.184 MiB
disponíveis, 15 GiB livres e temporários do executor limpos. Sem mudança de hardware,
deploy, chamadas IA, ativação de bundles na aplicação ou publicação.
