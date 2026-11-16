# H1 — Identificação de regras e triagem inicial

Incremento de 2026-09-29. H1 continua em andamento, sem liberação de XML.

## Defeito confirmado e ajuste qualificado

Inspeção da imagem SPSValidator ativa (`2806ed5e…`) mostrou um adaptador antigo:
ele não lia `subject` nem os metadados de regra no campo `data`. O código local
já possuía esse suporte, mas a imagem não. Isso explica os códigos `rule-N`.

Foi criada imagem de qualificação `idml-spsvalidator:h1-adapter-refresh-v1`, digest
`sha256:48b91db1bc1ab1d96ab003c357231b5d2f6e8fd1ae1cd16543ca9b64e767eefd`,
reutilizando exatamente a imagem base anterior e substituindo apenas o adaptador.
Sem atualizar dependências. O registro de produção não foi alterado; o registro
de ensaio está em `benchmarks/qualification/contracts/h1-adapter-refresh-registry.json`.
O cliente de laboratório agora lê esse registro, em vez do registro embutido na
imagem da aplicação. O broker continua conferindo hash, ferramenta e perfil.

No e20240086, os mesmos bytes retornaram as mesmas contagens SPSValidator:
29 críticos, 5 erros, 9 avisos; status failed. Os códigos genéricos foram
substituídos por regras identificáveis (datas, referências, afiliações, renditions,
licença etc.). Relatório SHA-256:
`d9a03d46f03d28ae24c7eef41465015cfc8a1b0b97e2489dda4ade32dfcb62c8`.
Não houve redução artificial de severidades nem aprovação.

## Exceções e primeira classificação

Diagnóstico com saída restrita a classes conhecidas confirmou `ValueError` na
família `reference`; não identificou marcadores de falha de rede nessa exceção.
Outra exceção ainda não teve causa classificada. Não se publicou traceback bruto.

Inspeção dos candidatos locais confirmou:

| Artigo | pub-date | pub-date/year | dtd-version | Traduções completas |
|---|---:|---:|---|---:|
| e20240086 | 0 | 0 | 1.3 | 0 |
| e20240135 | 2 | 2 | 1.3 | 0 |

A ausência de data/ano de publicação no primeiro candidato é confirmada. O código
local de referência do Packtools lança ValueError se faltar o ano do artigo citante;
isso é uma hipótese consistente para a exceção, mas ainda requer reprodução mínima
na versão fixada. Não foi inventada data nem alterado o gold.

O achado `renditions` nos dois ensaios anteriores não pode ser atribuído automaticamente
a tradução sem PDF: nenhum candidato contém sub-article de tradução. Investigar
nome esperado versus nome empacotado no runtime fixado antes de mudar o conteúdo.
Consultas DOI/ORCID/registro editorial continuam sem comprovação no modo sem rede.

## Limite do ensaio e limpeza

A saída da primeira tentativa de repetição do e20240135 não foi recuperada após
interrupção da sessão. Na retomada, não havia contêiner de ensaio nem socket ativo.
Nova tentativa foi recusada pela reserva de memória antes de executar validadores.
Não reduzir limites nem anunciar qualificação desse segundo artigo com a nova imagem.

Quatro cópias privadas remotas removidas pelo script restrito de limpeza; originais
locais preservados. Scratch/socket vazios e saúde banco/Redis OK. A aplicação e
os registros ativos não foram substituídos. Imagem/scripts de laboratório preservados.

Regressão completa executada antes da interrupção: **651 testes aprovados, três
avisos, cobertura 87,83%**; `tmp/h1-adapter-tests.xml` e `tmp/h1-adapter-coverage.json`.
Dois novos testes confirmam identidade de regra estável com reordenação, ausência
de valores privados e preservação de exceções. Três testes focados aprovados.

## Próxima execução

1. Confirmar fonte/autoridade para data/ano do e20240086 e reproduzir a exceção mínima;
   se faltar dado autorizado, apresentar pendência editorial, nunca preenchimento inventado.
2. Diagnosticar o nome de PDF esperado por `renditions` e corrigir causa confirmada.
3. Repetir ambos no mesmo envelope seguro e só então promover adaptador mediante
   atualização rastreável do registro e requalificação das evidências afetadas.
4. Prosseguir na matriz de regras, XPM e demais etapas do plano de fechamento.
