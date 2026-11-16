# 7C-08 — Requalificação e implantação controlada

Data: 2026-09-21. Resultado: **APROVADO NO CORPUS ATUAL**. Próxima etapa: V-12.
Esta aprovação não autoriza publicação SciELO nem substitui o especialista XML.

## Evidências de qualidade

- 380 testes aprovados; cobertura de linhas 87,31% (9.692/11.101 linhas executáveis).
- Ruff, formatação, mypy (91 módulos) e `git diff --check` aprovados.
- V-01 a V-11 e contratos 7C-01 a 7C-07: 18 gates aprovados localmente e em container
  read-only, sem rede, sem capabilities, com 512 MiB/0,5 CPU na VPS.
- Evidência privada 7C-07 reautenticada localmente, com seis casos vivos históricos,
  cinco controles negativos e matriz adversarial 30/30; nenhuma nova chamada ao provider.
- Leitura IDML: 106/106 stories reconstruídas (46 no artigo anterior, 60 no novo).
- e20240086: zero bloqueio após catálogos e qualificação de autoridade já autenticados.
  SHA-256: `15287f774bed60a62f0c5734aa7082234cbc7b69b86effeecc7a1e9ea991bc20`.
- e20240135: XML formal final determinístico; 12/12 domínios aprovados, zero bloqueio,
  zero issue offline, 24 equivalências de fórmula qualificadas e 12/12 artefatos conferidos.
  SHA-256: `20a03a91496ac0b447bd2abe589c2be6c231547793dcf5289bd3e66cc1990880`.
- O pacote formal preserva o SHA-256
  `e86f51a83a1f5d7cc869e51f4e13d18bb68fcf6c758016dd99bead032b0559ee`.
  As evidências Packtools/SPSValidator foram revalidadas por hash exato, não apresentadas como
  nova execução externa. Códigos e quantidades excepcionados continuam fechados no contrato 7C-06.

Os catálogos privados continuam necessários para os enriquecimentos qualificados; não foram
copiados para a VPS. Um upload comum não passa a incorporar automaticamente essas transcrições.
A aprovação destes dois artigos não representa um corpus independente de generalização.

## Rastreabilidade

| Requisito / defeito | Correção | Teste / evidência |
|---|---|---|
| Preservar figuras, assets e ordem | Resolução determinística, sem regra por artigo | G7C-02; `test_phase7_7c02_figures.py`; gate final |
| Preservar matemática inline/display | 43 fórmulas e catálogo autenticado | G7C-03; `test_phase7_7c03_formulas.py`; 12 domínios finais |
| Hierarquia, listas e notas | 26 seções e notas estruturadas | G7C-04; `test_phase7_7c04_structure_notes.py` |
| Autores, metadados e referências | Autoridade rastreável e chamadas resolvidas | G7C-05; `test_crossref_authority.py`; gate final |
| Pacote completo e SPS | Metadados formais e referências estruturadas | G7C-06; `test_formal_metadata.py`; hash do pacote |
| Assistência sem falso consenso aceito | Evidência e controles negativos, sem release automático | G7C-07; `test_corrective_7c07.py` |
| ORCID de um parágrafo com dois editores era atribuído a ambos | Abstenção por ambiguidade e enriquecimento autenticado | `test_paragraph_scoped_orcid_is_not_assigned_to_multiple_editors`; artigo anterior |
| Catálogo legado tinha label dentro do texto | Compatibilidade exata por hash e remoção do label duplicado | `test_legacy_labeled_editorial_catalog_is_applied_without_duplicate_label` |
| Gate V-03 duplicava labels de equação em outro estilo | Reconstruir somente label consumido pelo parser | `test_reading_gate_does_not_duplicate_separately_styled_formula_label`; 106/106 stories |
| Teste assistivo dependia de corpus privado | Evidências sintéticas completas e caso `quality=null` fail-closed | `test_phase7_7c07_gate.py` |
| Gates V-10/V-11 apontavam hashes históricos | Novos relatórios após reexecução, sem sobrescrever os históricos | `test_requalified_evidence_rejects_source_tampering` |
| Implantação não incluía relatório público V-09 | Allowlist inclui `benchmarks/security`; corpus continua excluído | 18 gates aprovados no container |

## Implantação e recuperação

Imagem: `idml-foundation:phase7-7c08-v1`, digest
`sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`.

Backup: `/opt/idml-platform/backups/20260921T121706Z`. Os três checksums passaram. Restauração
isolada validou 21 tabelas, um arquivo de artefato e 14 arquivos do OpenClaw, incluindo SQLite.
A base temporária e o diretório temporário desse teste foram removidos pelo cleanup; o backup
original permanece disponível. O OpenClaw dedicado foi pausado brevemente para cópia consistente.

Somente API e worker foram recriados. A sequência candidata → imagem anterior
`phase7-v11-robustness-v1` → candidata passou em health/readiness em todas as transições.
Não houve migration nova. A imagem e o arquivo de fontes anteriores foram preservados em
`/opt/idml-platform/releases/phase7-7c08-v1/`; o `.env` continua modo 600 e seu tag foi sincronizado.

No pós-teste: cinco serviços IDML saudáveis, 23 serviços não recriados/reiniciados, flags falsas,
provider sem credencial, zero sessão/run/proposta e zero rede transitória de provider.
Foram comparados por hash 282 arquivos de runtime da imagem com as fontes qualificadas.

VPS sem upgrade: 3.915 MiB RAM, cerca de 829 MiB disponíveis na amostra pós-deploy, swap usada
1.919 MiB/4.095 MiB e disco em 84% (15 GiB disponíveis). São amostras operacionais, não um teste
de capacidade. V-12 deve começar com baseline e limites de interrupção antes de aumentar carga.

## Arquivos de evidência

- `benchmarks/qualification/reports/phase7-7c08-requalification-v1.json`
- `benchmarks/qualification/reports/phase7-7c08-e20240086-v1.json`
- `benchmarks/qualification/reports/phase7-7c08-e20240135-v1.json`
- `benchmarks/qualification/reports/phase7-7c08-vps-gates-v1.json`
- `benchmarks/qualification/reports/phase7-7c08-vps-postcheck-v1.json`
- `benchmarks/qualification/reports/phase7-7c08-assistive-replay-v1.json`
- Relatórios V-10/V-11 sufixados `7c08-v1`; relatórios anteriores preservados.
- Saídas locais JUnit e cobertura em `tmp/phase7-7c08-tests.xml` e `tmp/phase7-7c08-coverage.json`.

## Restrições e próxima ação

`release_ready=false`. Continuam pendentes XPM SPS 1.10 no Windows, V-12 a V-15, fechamento
dos demais pacotes de homologação e Gate Humano Final G8-H. Nenhuma nova inferência paga foi
necessária nesta etapa. Próxima ação: instrumentar desempenho/capacidade/custo na VPS atual,
com corpus sintético no servidor e conteúdo autorizado real somente local.
