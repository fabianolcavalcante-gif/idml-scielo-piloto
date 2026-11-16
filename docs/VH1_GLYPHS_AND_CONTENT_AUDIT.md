# VH-06 — glifos, posição de símbolos e auditoria de conteúdo

Ensaios: 2026-10-08; registro consolidado em 2026-10-09, posterior à revisão de 14 transcrições.
**Quatro fórmulas e 14 posições de símbolos corrigidas na candidata; VH-06 parcial.**
Mesmo lote 2 e lista VH-01–20; sem implantação ou liberação G-HOMOLOG.

Checkpoint histórico, sucedido por `VH1_REFERENCE_FIELDS_AND_AUDIT.md` em 2026-10-09.
Os ensaios, catálogos e resultados abaixo permanecem preservados.

## Correções concluídas

- Casos inline 008/016: letra A caligráfica; inline 011/017: letra X caligráfica.
  Quatro fórmulas, cinco letras, agora com `mathvariant="script"`. A conferência
  visual da página 4 e os glifos Cambria Math do PDF corroboram essa representação.
- O importador ignorava `Position="Normal"` quando o nome do estilo aplicado
  continha `subscrito`. A prioridade da propriedade explícita foi corrigida na
  normalização semântica do estilo local. Também foram testados conflitos entre
  Subscript/Superscript; posição desconhecida conserva o tratamento anterior.
- No segundo artigo, 14 trechos de setas e símbolos voltaram à linha normal,
  conforme IDML/PDF: sete no primeiro algoritmo, um no texto explicativo, dois na
  entrada do segundo algoritmo e quatro no seu corpo. Um décimo quinto run Normal
  já está dentro de MathML e não exigiu remoção de `sub`.
- Índices legítimos, ênfases, texto e propriedades/evidências originais preservados.
  O reparo do importador é geral para propriedades explícitas do run, não troca
  caracteres científicos por regras específicas desses artigos. Não é um novo
  resolvedor completo de herança de fontes ou estilos.

O catálogo do segundo artigo é uma nova fotografia 1.1 derivada do 1.0 original,
mantendo **exatamente** as onze revisões anteriores e suas qualificações/fontes.
Acrescenta quatro revisões e não substitui silenciosamente o catálogo intermediário.
O primeiro artigo, seu catálogo, XML e ZIP permanecem byte a byte iguais.
Total acumulado nesta frente: 18 transcrições corrigidas (3 + 15).

## Uma abstenção explícita, não aprovação fictícia

O caso `esa-math-notes-inline-005` permanece intacto. A imagem mostra um glifo
inclinado; o ToUnicode do PDF associa um código ambíguo a outra letra e repete
caracteres em outros códigos. Portanto a extração textual não resolve com segurança
a distinção entre letra e barra. O IDML remete a PDF de equação externo não presente
nos arquivos fornecidos. Não foi corrigido pela forma convencional da equação.

É uma pendência científica delimitada para o especialista, com fonte/recorte e
abstenção registrados, não cinco novos defeitos ou autorização de publicação.
Os quatro demais casos inicialmente duvidosos foram resolvidos por fonte.
As exigências de revisão humana dos catálogos e a allowlist IA permanecem intactas.
Nenhum agente OpenClaw foi chamado ou ativado neste incremento.

Nos algoritmos, os caracteres U+0404 e U+00D8 existem no IDML e no PDF, inclusive
no mapeamento da fonte. Foram conservados; não há conversão silenciosa para símbolos
matemáticos visualmente parecidos. A distinção entre defeito do conversor e questão
editorial na fonte deve continuar visível para o especialista.

## Prova de preservação e validação nativa

O comparador C14N permite somente os quatro pares MathML revisados e a remoção dos
14 elementos `sub` comprovados. Restaura texto/tail e exige identidade integral do
restante do XML: nenhuma alteração de ciência, título, metadados, IDs, vínculos,
estrutura ou outras fórmulas. PDF, imagens e nomes dos membros ZIP são idênticos.
Reconversão dupla, XML/ZIP determinísticos e DTD válida nos dois casos.

Quatro execuções completas e sequenciais na VPS com as imagens fixadas:

| Artigo | Packtools | SPSValidator |
|---|---|---|
| e20240086 | 0 críticos / 0 erros / 9 avisos | 0 críticos / 0 erros / 9 avisos |
| e20240135 | 0 críticos / 0 erros / 5 avisos | 0 críticos / 0 erros / 5 avisos |

Achados exatamente iguais aos anteriores; autoridades positivas e auditoria de
histórico preservadas. Crossref/ORCID/periódico recoletados de fato nesta execução.
Zero formal nestas ferramentas não é aprovação científica, XPM ou aceite SciELO.

## Evidências e testes

- `benchmarks/qualification/reports/vh1-glyphs-linux-v1.json` e gate
  `python -m ops.gate_vh1_glyphs`, integrado ao CI e testado com adulterações.
- Qualificador: `python -m ops.qualify_vh1_glyphs`; fontes originais restritas,
  conectividade aos serviços permitidos e Poppler são necessários.
- Execução definitiva privada: `benchmarks/private/output/vh1-glyphs-20261008T201205Z`,
  também em `/opt/idml-platform/private/qualification/` com acesso somente root.
  Plano SHA-256: `77f9b158d42d5dcc3092453b2f4c0aca0cff21b9859b0aaf10d7308df737a878`.
  Tentativa local `20261008T201045Z` preservada, não qualificada ou enviada à VPS.
- Primeiro XML/ZIP: mesmos hashes da revisão anterior.
- Segundo XML: `84ab07204bd7debff2fc9f4c1623926f1637a722d12cbe964f4d5f4b178e899e`;
  ZIP: `e355adc2e049c7fc38e9fadbda93e739efdca5b833aac6bd200d3210bafa5d10`.
- Catálogo segundo artigo: `ea1709d6d5955c7080b9584747296ed8450cd60dafe3281349c4dff8dc8dea9c`.
- 71 testes novos: 24 de propriedades locais, 18 de diferença integral e 29 do gate.
  **126 testes focados aprovados**, JUnit `tmp/vh1-glyphs-focused.xml`.
- Regressão completa: **1.540 testes aprovados, cobertura de linhas 88,81%**
  (11.145/12.549), sem falhas, erros ou testes ignorados. Provas locais:
  `tmp/vh1-glyphs-final-tests.xml` e `tmp/vh1-glyphs-final-coverage.json`.
- V03 reexecutado nos dois IDMLs: **106/106 stories preservadas** (46 + 60).
- V10/V11 reexecutados e ligados à fonte atual por provas imutáveis
  `v10-operational-workflow-vh1-glyphs-v1.json` e `v11-robustness-mutation-vh1-glyphs-v1.json`.
  Ruff global e mypy (108 arquivos) passam. Varredura 7C-08 passa em todos os
  gates exceto V09, já histórico em VH-17; não declarar CI global aprovado.

A primeira tentativa nativa foi corretamente recusada pelo controle de permissões
dos arquivos copiados. Foi repetida somente após restringir todo o novo diretório
privado a root; não houve relaxamento do controle `trusted_read` ou dos validadores.

## Conferência de referências, seções e objetos

Os XMLs candidatos foram congelados por hash antes de abrir os XMLs de referência.
`ops/audit_vh1_content.py` não invoca o conversor: usa gold somente na comparação
posterior, publica contagens/hashes e preserva diferenças sem aprová-las.
Relatório: `benchmarks/qualification/reports/vh1-content-postbuild-audit-v1.json`.

| Domínio | e20240086, referência/candidata | e20240135, referência/candidata |
|---|---:|---:|
| Estrutura de seções | 11 / 11 | 26 / 26 |
| Referências bibliográficas | 52 / 52 | 35 / 35 |
| Figuras | 5 / 5 | 7 / 7 |
| Tabelas | 3 / 3 | 5 / 5 |
| Notas | 4 / 4 | 10 / 10 |
| Arquivos de mídia referenciados | 5 / 5 | 7 / 7 |

Esses domínios passam no comparador existente, admitindo suas normalizações.
Isso **não verifica todos os subcampos bibliográficos estruturados**: o comparador
de referências considera principalmente o texto da citação. A inspeção encontrou
ao menos um caso sem volume em que periódico/páginas foram incorporados ao título
estruturado. O texto integral não foi perdido; a segmentação exige correção/teste.

As chamadas bibliográficas do segundo artigo coincidem (39/39). No primeiro,
78/81 chamadas e diferenças nos destinos 10/11/13/37 precisam de adjudicação por
fonte, não cópia automática do gold: três chamadas de 2018 na referência apontam
para obras de 1998/2010; a candidata aponta para a obra de 2018. Outras três chamadas
estão vinculadas na candidata e não na referência. São diferenças a documentar,
não seis erros automaticamente atribuídos ao conversor.

O comparador integral bruto registra sete achados bloqueantes no primeiro artigo
(dois de metadados e cinco de fórmulas) e 23 de fórmulas no segundo. Não foram
ocultados, rebaixados ou usados como contagem de defeitos únicos.
Correções já verificadas por fonte podem divergir legitimamente do gold.

## Próximo passo definido

Ainda na VH-06: corrigir/testar a segmentação dos subcampos de referências,
fechar a adjudicação das diferenças bibliográficas e a triagem do comparador
integral com evidências já existentes. A dúvida científica remanescente fica
explicitamente listada para o especialista; não repetir pesquisa indefinida do glifo.
Depois consolidar VH-07, incluindo classificação dos avisos e validadores aplicáveis.
VH-02/XPM e IA/UI/operação/E2E permanecem nos IDs e critérios existentes.

VPS preservada: API/worker na imagem `4fcf4766…`, readiness/banco/Redis saudáveis,
905 MiB disponíveis e 15 GiB livres após ensaio; temporários removidos pelo executor.
Sem implantação, publicação, ativação IA ou liberação para homologação.
