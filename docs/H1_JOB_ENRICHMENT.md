# H1-01 — catálogos qualificados no processador de jobs

Data: 2026-09-28. Integração local implementada e paridade dos dois artigos comprovada.
Não implantada. Não libera G-HOMOLOG, nem validação formal externa, nem produção.

## Implementação

O worker seleciona catálogos opcionais antes de converter o IDML, usando empresa, artigo,
hash verificado do arquivo de origem e profile. Nenhum caminho ou catálogo é aceito do payload
do job. O resultado persistido inclui hashes de manifesto/catálogos e revisão humana requerida,
sem copiar o conteúdo dos catálogos para logs ou para o resultado público do job.

`services/enrichment.py` carrega os quatro contratos existentes e os entrega ao mesmo
`DeterministicPipeline` usado na qualificação: fórmulas, Crossref, metadados formais e
enriquecimento editorial. Os validadores de conteúdo/proveniência de cada contrato permanecem.
Não há inferência nova, geração de catálogo automática ou consulta ao XML gold.

Sem configuração: `not_configured`. Sem bundle correspondente: `no_matching_bundle`, conversão
determinística sem enriquecimento. Isso NÃO significa que o resultado está completo ou aprovado
para SciELO. Se uma pasta correspondente existir, mas o bundle for inválido/incompleto, o job
falha fechado, sem fallback silencioso para o resultado não enriquecido.

## Provisionamento exigido antes de H2/H3

1. Criar área privada administrada pelo operador, separada de uploads e do código.
2. Disponibilizar somente catálogos autorizados para a empresa e artigo exatos, validados
   previamente. Usuários da aplicação não podem escrever nessa área.
3. Usar `bundle_path(organization_id, resource_id, source_sha256)`: SHA-256 da concatenação
   ASCII `empresa:artigo:hash`. A pasta curta evita limites de caminhos no Windows.
4. Colocar `manifest.json` com `version=enrichment-bundle-1.0`, `organization_id`, `resource_id`,
   `source_idml_sha256`, `profile_id` e `catalogs` (tipo → SHA-256 dos bytes do JSON).
5. Arquivos permitidos: `formula_catalog.json`, `crossref_metadata_catalog.json`,
   `formal_metadata_catalog.json`, `editorial_enrichment_catalog.json`. Não aceitar nomes livres.
6. Limites: manifesto 16 KiB; até quatro catálogos de 8 MiB cada. Hashes conferidos antes do
   parse; conteúdo validado pelo contrato; recusar symlinks/escapes e escopo divergente.
7. Montar a área somente leitura no worker e configurar `IDML_ENRICHMENT_ROOT`. A configuração
   Compose e a montagem NÃO foram aplicadas nesta etapa. Não colocar arquivos privados na imagem.
8. Não substituir bundles enquanto jobs estiverem em fila/execução; cada versão de homologação
   deve congelar essa configuração. Até concluir governança de atualização, alteração exige
   janela controlada e requalificação. Hash não é assinatura: a confiança depende do operador
   e das permissões da área; manifesto não é autorização editorial por si só.

## Prova local

`ops/qualify_h1_enrichment.py` provisionou cópias temporárias dos catálogos privados existentes,
criou empresas/artigos/artefatos/jobs isolados e chamou `process_job` real com SQLite local.
Os dois jobs terminaram em `succeeded`, registraram proveniência e reproduziram os hashes:

- esa-e20240086: `15287f774bed60a62f0c5734aa7082234cbc7b69b86effeecc7a1e9ea991bc20` (2 catálogos).
- esa-e20240135: `20a03a91496ac0b447bd2abe589c2be6c231547793dcf5289bd3e66cc1990880` (3 catálogos).

Evidência: `benchmarks/qualification/reports/h1-job-parity-v1.json`.
Sem Redis, HTTP, browser, provider ou validadores externos nesta prova. Scanner `policy_only`
no ensaio local, não comprovação de antivírus. As cópias temporárias foram removidas; fontes
originais preservadas. Não houve transferência de corpus à VPS ou mudança da versão ativa.

Testes focados cobrem equivalência sintética, empresa/artigo/origem distintos, hash corrompido,
catálogo ausente, tipo/caminho proibido, profile divergente, tamanho de manifesto e modo desligado.
Houve ajuste do layout de pastas por limite de caminho Windows antes da execução aprovada.

## Continuação

Verificação final: **597 testes aprovados, três avisos, cobertura 87,76%**; módulo novo com
93% de cobertura. Ruff, formatação e mypy (95 arquivos de fonte) aprovados. Evidências:
`tmp/h1-enrichment-tests-final.xml` e `tmp/h1-enrichment-coverage-final.json`.
A primeira execução detectou relatório V-10 vinculado ao worker antigo; após repetir os testes
operacionais, foi criado `v10-operational-workflow-h1-enrichment-v1.json`, preservando o histórico.
O gate V-10 passou e a suíte final confirmou a rotação da evidência. Nenhum check foi removido.

- H1-01: integração e paridade local concluídas; instalação dos bundles autorizados e prova
  ponta a ponta pela interface/Redis continuam em H2/H3.
- Próximo: H1-02/H1-04, validação externa integrada e distinção clara entre pacote candidato,
  aprovação editorial e aprovação formal. H1-03 (XPM) permanece pendente.
- Renovar gates vinculados ao fonte alterado antes da implantação. Relatórios anteriores V-12
  não são prova válida desta nova candidata apenas porque os XMLs mantiveram os hashes.
- H4 (acesso individual/material) e G-HOMOLOG ainda não aprovados.
