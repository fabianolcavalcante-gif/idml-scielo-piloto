# H1 — Correção rastreável do ano de publicação

Incremento de 2026-09-29. Candidata local, sem implantação nem aprovação SciELO.

## Correção aplicada e origem

`ops/qualify_h1_publication_metadata.py` reconstrói o e20240086 com os dois
catálogos anteriores, confirma seu hash e consulta somente o DOI identificado na
fonte, em HTTPS no Crossref. O contrato existente confere DOI, consistência do ano,
volume e licença e gera catálogo com hash/proveniência e revisão humana exigida.
Nenhum XML gold foi lido e nenhuma data foi inventada.

A nova candidata contém publicação e coleção com precisão de ano, sem dia/mês.
Também recebe volume/licença do mesmo contrato. Snapshot, catálogo e XML ficam
em `benchmarks/private/output/h1-publication-metadata-v1`, somente localmente.
Não substituem os catálogos/hashes históricos nem são automaticamente instalados
no worker. Antes de H2, qualificar e provisionar um bundle novo para o artigo.

- XML anterior: `15287f774bed60a62f0c5734aa7082234cbc7b69b86effeecc7a1e9ea991bc20`.
- XML corrigido: `183dd2595a3b7d115075b426b7542acaac75dbfae2c785a3a64c41d8a291f61a`.
- Catálogo: `b805907f033904d56a89e3e641d4cb7e295c1c47a23285727919941201bc4fae`.
- Resposta de autoridade: `4912fa3aa1ff64288d3cadab4a9767976a82a87d086b5f2368c07e6cc18e6fb3`.

Validação offline da candidata: válida. Evidência pública:
`benchmarks/qualification/reports/h1-publication-metadata-v1.json`.

## Reprodução da exceção de referências

`ops/probe_h1_reference_year.py`, no runtime local de diagnóstico Packtools,
executa somente `ReferenceValidation.validate_year`, sem consultas de rede:

| Candidata | Referências | ValueError | Achados não OK da regra |
|---|---:|---:|---:|
| anterior | 52 | 52 | 0 |
| corrigida | 52 | 0 | 0 |

Os zero achados anteriores NÃO eram sucesso: a regra era interrompida por exceção.
O teste confirma a precondição do ano e sua correção nessa regra local, não a
aprovação integral do pacote pelos validadores da VPS. A candidata nova ainda
precisa ser empacotada e testada externamente; outros achados continuam abertos.

Teste de regressão sintético adicionado: autoridade de ano único produz pub/collection
sem inventar dia/mês. Os testes existentes preservam rejeição de hash adulterado.

Regressão completa: **652 testes aprovados, três avisos, cobertura 87,86%** da
aplicação (`tmp/h1-dates-tests.xml`, `tmp/h1-dates-coverage.json`). Ruff aprovado
nos arquivos alterados e Mypy aprovado em 97 arquivos. Não renovados os gates de
implantação; a nova candidata não foi enviada à VPS neste incremento.

## Diagnóstico PDF — não confundir divergência com ausência

O runtime local encontrou um PDF no pacote e nenhuma tradução completa. Para o
e20240135, espera `1809-4457-esa-30-e20240135_00224.pdf`, mas existe
`1809-4457-esa-30-e20240135.pdf`. A imagem fixada de qualificação da VPS confirma
que `renditions` constrói esse nome a partir de `sps_pkg_name`, não do basename
do XML. Assim, o erro não demonstra que o PDF não foi enviado.

Não renomear automaticamente para satisfazer o validador: primeiro conciliar a
regra normativa e a estratégia de nomeação do runtime, incluindo `other`. O guia
de entrega já registrado no plano proíbe underscore na nomeação. Não foi aplicado
waiver, criado PDF duplicado nem removido idioma. A compatibilidade permanece aberta.

## Próximo passo

1. Construir pacote da candidata corrigida e repetir validadores na VPS quando
   a reserva de recursos admitir execução, mantendo hashes antigos como histórico.
2. Resolver a divergência de nome de PDF com teste isolado positivo/negativo e
   evidência normativa; não mascarar arquivos realmente ausentes.
3. Promover catálogo/adaptador apenas após requalificação, atualizar provas do job
   integrado e seguir XPM/fechamento formal/H2–H4.
