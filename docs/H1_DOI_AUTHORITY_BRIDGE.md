# H1 — DOI: diagnóstico de transporte e ponte local de autoridade

2026-09-30. Incremento candidato, sem implantação nem aprovação XML.

## Causa confirmada

Prova no runtime Packtools fixado, com o XML e20240086: a consulta retornou
`tenacity.RetryError`, nenhum registro e WARNING. O requester fixado repete
falhas de conexão/timeout e HTTP 5xx; esgotamento é uma falha de consulta, não
prova de inexistência do DOI. HTTP 4xx/URL inválida seguem outro ramo e não foram
incluídos nessa classificação. O diagnóstico imprime só classe permitida e hashes.

`external_verification.py` reconhece o nome de classe completo dessa exceção,
na regra de registro DOI e sem resposta positiva/registro divergente retornado.
Texto genérico contendo RetryError não basta. A severidade original permanece e
o bloqueio adicional `external-verification-unavailable-doi-registry` é emitido.

Imagens novas, somente de laboratório:

- Packtools `sha256:4a35ec1dba3c62a8fa52cfdda87b3908c873c02034371fb7809a0fed1ca5ad61`.
- SPSValidator `sha256:372a13a1ad2dcbf94391559c20db4f63c1fbf3ab13453bf38e9e43ec1d34db77`.

## Ponte de autoridade implementada localmente

`release/doi_snapshot.py` recebe hashes e data de obtenção de um manifesto
confiável do servidor — não de campos enviados pelo usuário. Exige:

- hashes exatos do XML e da resposta;
- resposta Crossref bem-sucedida com DOI único correspondente e ISSN em comum;
- instante com fuso, não futuro, e idade máxima de sete dias;
- nova conferência de prazo, DOI e hash do candidato em cada consulta;
- cópia independente do JSON para impedir mutação do snapshot vinculado.

Sete dias é limite de engenharia desta candidata, não regra atribuída à SciELO.
O hash assegura integridade/vínculo, não autenticidade de uma origem não confiável:
por isso o manifesto precisa vir do coletor administrativo. O módulo não cria
`valid=True` nem substitui comparação de título/autores feita pela ferramenta.

Uma resposta Crossref nova foi obtida por HTTPS para o primeiro artigo, no
coletor local, sem gold. Hash igual ao snapshot anterior, com nova data de obtenção
registrada. A regra nativa local aprovou o DOI; ao substituir título/autores por
dados sintéticos alheios, a mesma regra rejeitou. XML não alterado.

Evidência: `benchmarks/qualification/reports/h1-doi-snapshot-local-v1.json`.
Dados privados novos em `benchmarks/private/output/h1-doi-snapshot-v1`.
Nenhum snapshot ou catálogo foi enviado à VPS. A prova é da regra DOI local,
não do pacote inteiro, da imagem Linux ou do fluxo API/worker/UI com autoridade.

## Repetição isolada na VPS

Packtools e SPSValidator concluíram as execuções nos dois artigos, ambos sem
aprovação formal. Cada ferramenta retornou os seguintes totais:

| Artigo | Blocking | Critical | Error | Warning |
|---|---:|---:|---:|---:|
| e20240086 | 3 | 22 | 4 | 12 |
| e20240135 | 4 | 6 | 4 | 8 |

Os bloqueios identificam DOI/fascículo/seção indisponíveis e, no segundo artigo,
também ORCID. Os achados e severidades nativos não foram dispensados. O aumento
de bloqueios torna a indisponibilidade visível; não representa piora do XML.

As quatro cópias privadas temporárias foram removidas da VPS, com originais
locais preservados. Banco e Redis saudáveis após a limpeza; memória disponível
960804 KiB. Serviços existentes não reiniciados nem substituídos.
Evidência: `benchmarks/qualification/reports/h1-doi-retry-linux-v1.json`.

Regressão final: 736 testes aprovados, três avisos e cobertura de linhas 88,02%.
Ruff dos arquivos deste incremento e mypy do módulo de snapshot aprovados.
Os 59 testes focados e quatro contratos API/jobs/package/interface foram
reexecutados; evidência vinculada ao código em
`benchmarks/qualification/reports/v10-operational-workflow-h1-doi-v1.json`.
Esse gate operacional não aprova o conteúdo XML nem substitui G-HOMOLOG.

## Próximo incremento

Atualização: transporte candidato Packtools implementado e regra nativa
qualificada na VPS com dados sintéticos positivos/negativos. O fluxo completo e
SPS ainda pendentes; sequência detalhada em `H1_DOI_TRANSPORT.md`.

Integrar essa ponte ao transporte isolado usando manifesto confiável, montagem
somente leitura, limites de tamanho, validade e vínculo de candidato. Qualificar
primeiro com dados sintéticos; qualquer transferência real de snapshot/catálogo
deve respeitar o escopo de corpus autorizado (a exceção atual cobre derivados,
não envio indiscriminado de catálogos). Depois repetir a regra no runtime fixado.

Seção/fascículo precisam de autoridade editorial própria; não inferir seus
cadastros do simples registro Crossref. ORCID, demais achados de conteúdo, XPM
e prova do sistema implantado permanecem no plano. G-HOMOLOG não liberado.
