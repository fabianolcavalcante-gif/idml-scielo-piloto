# H1 — Verificação externa indisponível não é defeito XML comprovado

2026-09-30. Diagnóstico candidato; não há consultas novas de autoridade, abertura
de rede dos validadores, promoção da aplicação ou liberação de G-HOMOLOG.

## Implementação

`ops/external_verification.py` reconhece ramos explícitos dos resultados upstream,
sem concluir pela severidade ou pelo título da regra isoladamente:

- ORCID: estado nativo e valor obtido `unknown` na regra de registro.
- DOI: falha de transporte reconhecida (ConnectionError/Timeout/URLError), sem
  registro retornado e sem resultado positivo. HTTPError genérico, divergência
  de metadados e respostas desconhecidas não são dispensados nem reclassificados.
- Volume/fascículo: ramo que declara não ter podido consultar o registro.
- Seção editorial: seção presente, lista esperada vazia e declaração explícita
  de impossibilidade de conferência. Seção ausente ou divergente de lista conhecida
  não é tratada como consulta indisponível.

O normalizador preserva códigos e severidades originais e acrescenta um bloqueio
por dependência ausente, deduplicado. Os bloqueios têm código
`external-verification-unavailable-*` e não podem ser aceitos como avisos.
Isso evita aprovação acidental quando a ferramenta emite somente WARNING para
uma conferência externa que não ocorreu.

O motor local classifica esses bloqueios como sistema; o diagnóstico do pacote
expõe `unavailable_external_checks` e o motivo `external-verification-unavailable`.
Execução `completed` significa processo concluído, não verificação externa feita.
O pacote continua `blocked`; o XPM permanece explicitamente indisponível.

## Privacidade e compatibilidade

A prova inicial revelou que dados internos de regras nativas podiam entrar na
identidade pública (título/seção do artigo). Agora só metadados de regras dentro
do envelope SPS são considerados como regra aninhada. Dados do artigo não entram
nos códigos por esse caminho. Teste de regressão específico incluído.

Imagens finais v2 usam as bases de compatibilidade de afiliação anteriores:

- Packtools: `sha256:b74b0974a6b8bdd891a1f7b51deeaccbfd4e109fe67f56abf456a1aec9255bed`.
- SPSValidator: `sha256:6f463a1b2879f3d4b961914927310503c38efab84b5e963c0069892a73b156ec`.

Registro dedicado: `h1-external-verification-registry.json`. V1 foi uma rodada
intermediária não promovida. O cliente da imagem atual já conserva os novos
bloqueios pelo contrato existente; a categoria de sistema e os campos adicionais
do diagnóstico foram verificados no código local, ainda não implantado.

## Requalificação de evidências

A primeira regressão falhou corretamente no hash do relatório V10 antigo após
alteração do código. Não se editou nem se ignorou essa evidência histórica.
Foram reexecutados 48 testes direcionados (workflow, transporte, diagnóstico e
novos casos), além dos quatro contratos API/jobs/pacote/interface. Novo relatório:
`v10-operational-workflow-h1-external-v1.json`; o gate V10 aponta para ele.
O relatório mantém a aprovação restrita do fluxo local; não aprova o XML nem a
implantação. A regressão completa é registrada separadamente, não copiada da antiga.

Regressão final: **725 testes aprovados**, três avisos, cobertura **88,00%** do
pacote da aplicação. Artefatos: `tmp/h1-external-final-tests.xml` e
`tmp/h1-external-final-coverage.json`. O percentual não mede conformidade XML nem
cobertura dos scripts ops. Ruff aprovado nos arquivos alterados deste incremento.

## Resultado nos candidatos reais

Hashes de XML/ZIP iguais aos da rodada anterior; processos concluídos nas duas
ferramentas. Contagens por ferramenta:

| Artigo | Bloqueios adicionais de consulta | Críticos / erros / avisos preservados |
|---|---|---|
| e20240086 | 2: fascículo/volume e seção | 22 / 4 / 12 |
| e20240135 | 3: fascículo/volume, seção e ORCID | 6 / 4 / 8 |

São diagnósticos adicionais, não novos defeitos introduzidos no XML nem redução de
severidade. A consulta DOI real não correspondeu aos ramos explícitos reconhecidos;
seu achado permaneceu sem dispensa e exige investigação adicional.

Nove contraprovas nativas por imagem final (18 ao todo) aprovadas, distinguindo
registro divergente de contexto indisponível. Relatório completo:
`benchmarks/qualification/reports/h1-external-verification-linux-v1.json`.
Serviços sem reinício, scratch/socket limpos, quatro cópias privadas remotas
removidas e originais locais preservados. Banco/Redis OK; MemAvailable final
943.068 KiB. G-HOMOLOG e aprovação dos XMLs continuam pendentes.

## Próximo incremento

1. Investigar de forma segura o retorno real da consulta DOI ainda não classificado.
   Não deduzir indisponibilidade simplesmente porque o contêiner está sem rede.
2. Conectar fontes de autoridade verificadas e versionadas para seção/fascículo
   e identificadores: evidência vinculada ao periódico/artigo e candidato exatos,
   com negativos para cadastro divergente, ausente e desatualizado.
3. Preservar verificações de formato e identidade separadas da existência de
   registro. Nunca preencher nomes, ORCID, datas ou seções por suposição.
4. Continuar os defeitos de conteúdo remanescentes e XPM; depois H2/H3 e G-HOMOLOG.
