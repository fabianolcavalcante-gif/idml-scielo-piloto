# H1 — Países das afiliações e triagem do front

2026-09-30. Continuação da qualificação de PDF. Candidata de laboratório,
sem troca do perfil padrão, implantação ou liberação para o especialista.

## Defeito confirmado e corrigido

O IDML do e20240086 explicita países nas três afiliações: Brasil, Japão, Brasil.
O mapper preservava os nomes, mas o perfil 1.0 só mapeava India → IN. O XML ficava
sem os três atributos `country`, denunciados pelos dois validadores externos.

Novo `profiles/esa-aop-1.1.json`: adiciona Brazil/Brasil → BR e Japan → JP,
mantendo India → IN. Correspondência exata; nome desconhecido ou ambíguo não gera
código inferido. O perfil padrão 1.0 permanece intacto até a promoção H2/H3.

Base consultada: [marcação de afiliação SciELO](https://scielo.readthedocs.io/projects/scielo-publishing-schema/pt-br/latest/tagset/elemento-aff.html),
[tabela de países SciELO](https://scielo.readthedocs.io/projects/scielo-pc-programs/en/latest/markup_tags.html)
e [ISO 3166](https://www.iso.org/iso-3166-country-codes.html). Consulta restrita a
códigos de país; não significa qualificação de todas as regras SPS atuais.

## Proveniência e escopo

`ops/qualify_h1_country_codes.py` exige que a diferença de perfil seja exatamente
o mapa aprovado e sua versão. Revalida os catálogos existentes, preserva valores,
fonte e evidências, gera cópias com novo vínculo de perfil e recalcula seus IDs.
Essa migração é explícita e de laboratório: os catálogos antigos e os bundles do
worker não são alterados. A trilha before/after está no relatório público.
Não há nova leitura do gold nem consulta externa de metadados neste incremento.
Os catálogos preexistentes mantêm sua proveniência e suas limitações anteriores.

A execução anterior é reconstruída e conferida contra seu hash. Uma guarda
compara o XML inteiro e recusa qualquer diferença que não seja a adição dos
códigos autorizados em `article-meta/aff/country`.

- e20240086: exatamente três atributos adicionados; nenhum texto modificado.
- e20240135: XML idêntico; ZIP muda por incluir o novo ID de perfil no manifesto.
- Ambos os pacotes determinísticos, usando PDF/imagens conferidos por manifesto.
- País ausente/desconhecido e associações ambíguas não são inventados.

Artefatos privados novos: `benchmarks/private/output/h1-country-codes-v1`.
Relatório: `benchmarks/qualification/reports/h1-country-codes-v1.json`.

## Qualificação externa

Primeiro artigo: Packtools e SPSValidator completed, 25 críticos, 4 erros,
12 avisos cada. Antes: 28 críticos, 4 erros, 12 avisos. A regra de código de país
desapareceu; nenhum achado foi dispensado. Continua reprovado.

Segundo artigo: ambos completed, 10 críticos/4 erros/8 avisos, sem regressão.
Prova: `benchmarks/qualification/reports/h1-country-linux-v1.json`.
As quatro execuções preservaram os serviços existentes. Scratch e sockets limpos;
quatro cópias privadas removidas da VPS, originais locais preservados. Banco e
Redis OK ao finalizar. Imagem de laboratório da rodada PDF mantida, sem promoção.

Regressão local: 696 testes, 3 avisos, cobertura 88,00% da aplicação.
Arquivos `tmp/h1-country-codes-tests.xml` e `tmp/h1-country-codes-coverage.json`.
16 testes novos cobrem países conhecidos/desconhecidos/ambíguos, proveniência,
perfil padrão intacto e rejeição de alterações fora do escopo. Ruff aprovado.

## Triagem e próximos passos

Os dois XMLs têm um xref de afiliação por autor. Assim, não se deve adicionar
vínculos artificiais apenas para silenciar a regra de afiliação: é necessário
comparar a resolução do modelo e a regra no runtime fixado, com caso positivo e
negativo. Essa comparação sintética foi executada na imagem Packtools fixada:
regra direta com afiliação → OK, sem afiliação → ERROR. No caminho XML,
`XMLContribs` resolve 1 afiliação válida, mas `TextContribsValidation` ainda retorna
ERROR; com rid inexistente, resolve 0 e retorna ERROR. O código local inspecionado
mostra que esse caminho valida itens de `TextContribs` sem o enriquecimento `affs`
feito por `XMLContribs`. Evidência da falha de integração na ferramenta, não uma
autorização para ignorar toda a regra. Não houve waiver nem alteração do adaptador.

Próxima implementação: compatibilidade estreita da resolução de afiliações no
adaptador candidato; testar destino válido, ausente, duplicado, tipo de referência
incorreto e escopo de subartigo. Preservar ERROR para links não resolvidos e só
promover após prova nos dois validadores. Não editar XML correto para contornar
o defeito da ferramenta.

O primeiro artigo não contém ORCID de autores na candidata; não buscar
nem associar identificadores por semelhança de nomes.

Sequência: investigar regra de afiliação e consultas de registro DOI/ORCID;
classificar datas/histórico, CRediT, financiamento, referências e fórmulas contra
fontes; corrigir cada defeito comprovado. XPM e prova do fluxo implantado continuam
pendentes. Contagem de achados não equivale a contagem de defeitos reais nem a um
percentual de conformidade SciELO.
