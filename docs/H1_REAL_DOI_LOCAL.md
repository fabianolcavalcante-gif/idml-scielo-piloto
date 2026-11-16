# H1 — Revalidação DOI dos dois artigos reais

2026-10-01. Qualificação local, sem envio de corpus ou autoridades à VPS.

## Resultado confirmado

Os candidatos ESA e20240086/e20240135 foram conferidos por SHA-256 e seus ZIPs
foram vinculados ao XML interno. Consultas Crossref novas, por HTTPS, foram
armazenadas somente na área privada local, com hash e instante da coleta.
O coletor rejeita redirecionamento inesperado. Gold não foi lido; XMLs intactos.

Nos dois artigos, a comparação nativa DOI passou tanto no Packtools quanto no
SPSValidator. São quatro comparações observadas explicitamente, não inferidas
da ausência de erros. SPS omite linhas OK no relatório final; o novo observador
registra somente o booleano retornado pela função nativa, sem modificar seu
resultado, seus argumentos ou o critério de similaridade. Restaura a função ao sair,
inclusive em erro. Quando não há comparação, a evidência não marca aprovação.

Durante a validação, conexões/DNS Python foram bloqueados; a consulta DOI usa
o snapshot vinculado. Essa guarda não equivale ao isolamento Docker da VPS.
Indisponibilidade de outras consultas continua gerando os achados nativos.

## Pendências preservadas

Contagens por ferramenta, neste runtime local:

| Artigo | Blocking | Critical | Error | Warning |
|---|---:|---:|---:|---:|
| e20240086 | 2 | 22 | 4 | 11 |
| e20240135 | 3 | 10 | 4 | 7 |

Bloqueios: contexto de fascículo/seção nos dois artigos e ORCID no segundo.
Também permanecem achados sobre estados de afiliação, CRediT, datas/histórico,
financiamento, referências e vínculos de fórmulas, conforme o artigo. A contagem
é de achados de regras, não de defeitos editoriais únicos comprovados.

Importante: runtime local Packtools `4.16.9rc20260916`, SPSValidator `0.3.0`;
as imagens Linux candidatas usam outra revisão fixada de Packtools. As quatro
ocorrências críticas adicionais no segundo artigo, em relação à rodada Linux
anterior, não são prova de regressão do XML, que tem o mesmo hash. Não comparar
contagens como equivalentes antes de alinhar versões/configurações.

Evidência de comparação explícita:
`benchmarks/qualification/reports/h1-real-doi-local-20261001T113558Z.json`.
As rodadas exploratórias anteriores permanecem como histórico: a primeira não
registrava o positivo explicitamente; a segunda mostrava zero linhas DOI no SPS
por omissão de OK. Não usar esses zeros como aprovação ou rejeição do DOI.

Dados privados em `benchmarks/private/output/h1-real-doi-local`; não enviados,
não incluídos em imagens, CI ou Git. Nenhuma mudança no ambiente ativo.

## Sequência atualizada

Verificação: regressão de 770 testes aprovada (três avisos, cobertura 88,02% de
`src/idml_foundation`). Após acrescentar o observador explícito, 31 testes focados
passaram, incluindo restauração da função em erro e preservação da identidade
do resultado nativo. Scripts ops não fazem parte desse percentual de cobertura.
Ruff aprovado. Não somar os 31 testes aos 770, pois há sobreposição.

1. Alinhar a execução real ao runtime fixado, preferencialmente local, ou obter
   escopo explícito para a coleta/uso de autoridades na VPS. A exceção atual de
   corpus permite derivados, mas não transferência indiscriminada de catálogos.
2. Fechar contexto editorial de seção/fascículo e ORCID com fontes verificadas;
   não inferir cadastro editorial de dados Crossref nem associar ORCID por nome.
3. Confirmar cada achado de conteúdo contra fontes autorizadas e a regra aplicável;
   corrigir com contraprovas, sem inventar datas, papéis de autor ou financiamento.
4. Concluir XPM e, depois, implantação reversível/provas API/worker/UI.

DOI verificado não equivale a XML integralmente aprovado, indexação SciELO ou
G-HOMOLOG. A homologação humana continua pendente.
