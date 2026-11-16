# VH-02/05/07 — cadastro da revista e primeiras regras de compatibilidade

Checkpoint: 2026-10-16; fechamento da regressão conferido em 2026-10-17.
**VH-05 concluída na candidata; VH-02/07 parciais.**
Não há aprovação integral do XML, G-HOMOLOG, publicação ou implantação da aplicação.
Este incremento executa a entrega 1 da seção 29 do plano único; não cria fase nova.

## Implementação

`JournalMetadataCatalog` corrige exclusivamente título do periódico e editora do
perfil ESA 1.1, usando o catálogo SciELO fixado por SHA-256 e uma linha única
identificada por coleção, sigla e dois ISSNs. Título do artigo, DOI, conteúdo
científico e anexos não são alterados. A grafia oficial do periódico é
`Engenharia Sanitaria e Ambiental`; a editora inclui o sufixo `- ABES`.

O catálogo armazena o estado anterior integral do periódico, fonte, coleta, hash,
perfil e IDML. Alteração editorial concorrente, conflito, ambiguidade e fonte
divergente são recusados. Idempotência exige também proveniência e estado completo,
não apenas igualdade de dois textos. Evidências anteriores são preservadas e é
acrescentado marcador de revisão humana.

Integração realizada no pipeline e no carregador de enriquecimentos utilizado
pelo worker candidato. O grant administrativo vincula empresa/artigo/destino,
hash da fonte, validade de sete dias, expiração e revogação. Não há permissão
concedida por saída de IA, arquivo enviado pelo usuário ou caminho arbitrário.
O perfil existente e os catálogos históricos não foram sobrescritos.

Primeiro contrato `xpm-compatibility-evidence-1.0` e avaliação derivada
`xpm-homologation-compatibility-1.0` implementados, com duas regras fechadas:

- `xpm-doi-journal-exact-1.0`: periódico exatamente igual ao registro DOI.
- `xpm-doi-article-exact-1.0`: título do artigo exatamente igual ao registro DOI.

Exigem XPM 4.0.096, ZIP oficial/imagem/módulo fixados, relatório atestado, XML real
dentro do ZIP, empresa/artigo/IDML/perfil vinculados, Crossref do DOI e ISSN corretos,
hash e coleta válidos. A mensagem precisa corresponder à estrutura original e a
uma ocorrência única. Só há normalização de espaços; sem igualdade por aproximação,
remoção de acentos, mudança de caixa ou decisão do modelo.

O `XpmResult` original e sua propriedade `passed` permanecem intactos. Exceções e
contagens ainda não resolvidas ficam separadas. Nesta versão, `homologation_ready`
e `release_approved` são obrigatoriamente falsos. A avaliação ainda não está
integrada ao serviço supervisionado/UI; não altera a Release Policy.

## Prova real na mesma VPS

Reconstrução final: `benchmarks/private/output/vh1-journal-metadata-20261016T165920Z`.
Plano: `478ea3ee76e7ccee3db39d0d05c5d6c84fb8f643a703cdd0de9665afa64ba784`.
Mesmo diretório em `/opt/idml-platform/private/qualification` na VPS.

Antes de corrigir, o pipeline reproduziu exatamente os XMLs/ZIPs anteriores.
Depois da correção, conversão e empacotamento foram repetidos com saída idêntica.
Comparação integral permite apenas dois textos no e86 e um no e135; todos os
demais nós XML e bytes dos PDFs/imagens permaneceram iguais. Gold não é entrada.
Fontes externas e grants foram renovados para os novos hashes.

| Artigo | SHA-256 XML | SHA-256 ZIP |
|---|---|---|
| e20240086 | `414de2ea7329379b98d06f5018839f7de7ac9487501f1b1b2eea44ed2019264f` | `2f9c5b6529fb193a38b965d366fec1cda5afcaf89e1d8a3eb146022969f1bfee` |
| e20240135 | `31224a085f49ce7d570069f8d266993979dd46beed720c7edc22324e1c11f1e5` | `54f71f50669cacdda2ff7323777574c82e6f4bedf85cd7743abe4d6de5e90ea3` |

Packtools e SPSValidator: quatro execuções nativas, **zero críticos/erros e cinco
avisos por ferramenta/artigo**, iguais aos avisos do checkpoint anterior.
Prova: `benchmarks/qualification/reports/vh1-journal-metadata-linux-v1.json`.
Hash canônico JSON: `61c57c43c081a537fc95d12c1c1e802a092cbf5ee3a26c093debcfb89d3ad66a`.
O gate verifica também código atual, antecessor, ativos, regras, fontes e escopo.

XPM original: execução `20261016T214400Z`, imagem
`sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63`.
Dois pacotes corrigidos e um controle com imagem removida; todos com relatório
nativo. Nenhuma modificação do vendor ou promoção do XML reempacotado pelo XPM.

| Caso | Bloqueios brutos | Fatais brutos | Erros brutos | Avisos | Exceções DOI exatas | Erros ainda não resolvidos |
|---|---:|---:|---:|---:|---:|---:|
| e20240086 | 3 | 1 | 4 | 2 | 2 | 2 |
| e20240135 | 3 | 1 | 4 | 3 | 2 | 2 |
| e20240086 sem imagem | 4 | 1 | 4 | 2 | Não aplicada | 4 |

As correções cadastrais removeram um fatal e um erro do e86, e um erro do e135.
As duas exceções por artigo **não reduzem as contagens brutas**. Bloqueios, fatal,
avisos e consultas pendentes não foram dispensados. O controle sem imagem falhou.

Prova: `benchmarks/qualification/reports/vh1-journal-xpm-compatibility-v1.json`,
SHA-256 dos bytes `9eb3a0e724a8f2de6d2773661c29f4d00cf444696d463966e1da0a2c149dbf41`.
HTML/XML/logs/CSV privados estão em `xpm-evidence` local e
`xpm-native/vh1-xpm-online-20261016T214400Z` no diretório remoto final.

Contraprova independente: oito chamadas aos métodos originais de comparação DOI,
sem rede nem alteração do código. Igualdade exata e quase igualdade geram ERROR;
diferença real gera FATAL. A implementação só admite a primeira, não a quase
igualdade. Prova `vh1-xpm-doi-comparisons-v1.json`, hash
`8144b908b87826e15d1287152ffcfea8e9fa32712df762f6a58e178e2cc38c3a`.

Catálogo HTTPS verificado nas três execuções, três contraprovas de rede aprovadas,
25 serviços preservados, banco/Redis saudáveis. Dez consultas Wayta continuam
recusadas; túneis TLS Crossref/ORCID não provam por si só conclusão semântica de
todas as consultas. Containers/redes temporários encerrados; sem porta pública,
upgrade, ativação IA ou alteração dos serviços ativos.

## Regressão e continuidade de evidências

170 testes direcionados aprovados, incluindo 48 dos novos contratos/catálogos,
35 dos novos gates, worker real de teste, autorização e isolamento. V10/V11
reexecutados e publicados como `*-vh1-journal-metadata-v2.json`; v1 preservada.
Provas anteriores
não foram reescritas: a cadeia aceita mudança de fonte somente com o sucessor
nativo fixado e todos os seus checks, nunca apenas com uma lista de hashes.

A regressão detectou repetição de avaliações na cadeia histórica. O gate novo
agora reaproveita somente avaliações puras vinculadas a todos os bytes atuais
das fontes e provas, com cache limitado a duas entradas. A leitura atual não é
dispensada. Dois testes adicionais demonstram que troca de fonte ou relatório
invalida sucesso anterior, inclusive usando a mesma função de leitura. A primeira
suíte integral deste fechamento foi interrompida para aplicar essa correção;
não conta como aprovada. A suíte final, repetida com a fonte definitiva, terminou
em 2026-10-16 às 19:13 (America/Sao_Paulo): **2.166 testes aprovados, nenhuma
falha/erro/skip, cinco avisos e cobertura de linhas de 89,33%** (11.616 de 13.004
instruções medidas). Duração: 17min02s. Resultado conferido em 2026-10-17.

Ruff global, tipagem de 114 módulos e formatação dos 20 arquivos do incremento
aprovados. A formatação global ainda aponta os dois scripts antigos
`qualify_doi_socket_linux.py` e `qualify_doi_transport_linux.py`; pendência de VH-17
preservada, sem reformatar evidências históricas fora deste escopo.

Gates adicionados ao CI: `python -m ops.gate_vh1_journal_metadata` e
`python -m ops.gate_vh1_journal_xpm`. Relatórios de teste integral e cobertura do
fechamento: `tmp/vh1-journal-final-tests.xml` e `tmp/vh1-journal-final-coverage.json`.
O resultado está registrado na seção 30 do plano único. A aprovação desta suíte
local não significa aprovação global do CI: V09/formatação históricos continuam
pendentes e o job atual limita a execução completa a 15 minutos. VH-17 deverá
medir o tempo no runner de CI e ajustar desempenho/divisão do job ou justificar
seu orçamento de execução; não se inferiu o tempo do Linux a partir do Windows,
nem se ampliou o timeout sem essa verificação.

Ensaios intermediários `...T165208Z` (parcial) e `...T165250Z` preservados como
diagnóstico, não são a referência final. A primeira tentativa remota recusou as
permissões herdadas do arquivo TAR gerado no Windows; o diretório de ensaio recebeu permissões
restritas e o executor original foi repetido sem relaxar sua verificação.

## Próximo incremento delimitado

Atualização de 17/10: SPS/pub-date implementados e análise DOCTYPE registrada em
`VH1_SPS_DATE_COMPATIBILITY.md`; os itens abaixo descrevem o encaminhamento original.

Continuar **VH-02/07**, sem reabrir VH-05/conteúdo científico:

1. Qualificar regras legadas de versão SPS e `pub-date`, com condição exata,
   fonte normativa, validação independente e negativos; não mudar datas corretas
   ou adicionar atributos legados apenas para satisfazer o XPM.
2. Concluir a análise específica de DOCTYPE/JATS 1.3. A autorização da ADR-019
   não permite ignorar o fatal automaticamente.
3. Resolver o transporte/resultado obrigatório de Wayta ou registrar dependência
   específica, mantendo falha visível; indisponibilidade não se torna aprovação.
4. Revalidar os mesmos pacotes para encerrar o restante da entrega 1. Se depender
   de orientação externa, avançar nos itens independentes VH-08/11 previstos.

Depois permanecem as entregas 2–5: automação IA segura, fluxo web, implantação na
VPS atual e testes/entrega ao especialista. Sem nova autorização geral necessária.
