# V-12.2 — auditoria operacional e retenção

Data: 2026-09-25. Bloco de diagnóstico implementado; implantação integrada ainda pendente.

## Implementado e testado

- `ops/audit_storage.py`: consulta somente leitura ao banco, varredura limitada por tempo,
  entradas e registros; alerta de reserva de disco, quota por empresa, arquivos ausentes,
  tamanhos divergentes, caminhos inseguros e candidatos a órfãos. Não lê conteúdo dos artigos,
  não emite identificadores privados, não corrige nem exclui dados.
- Saída JSON e códigos 0 saudável, 1 aviso, 2 crítico, 3 inconclusivo. Varredura incompleta
  não afirma ausência de problemas. Consistência best-effort: concorrência pode produzir
  achados transitórios; confirmar em janela estável antes de qualquer ação.
- `ops/plan_backup_retention.py`: inventário por metadados compatível com Python 3.10 do host.
  Protege os sete conjuntos mais recentes OU todos com até 30 dias. Entradas desconhecidas,
  incompletas ou futuras são preservadas; nenhum arquivo é movido ou removido.
- `ops/audit-storage.sh` e unidades `deploy/systemd/idml-storage-audit.*` preparados para
  execução periódica e diagnóstico no journal. NÃO instalados/ativados, sem canal externo
  de notificações configurado; validar captura dos estados não-zero antes da ativação.
- `deploy/docker-compose.logging.yml`: overlay candidato para logs Docker do OpenClaw
  dedicado, `json-file`, 10 MB por arquivo, três arquivos. Validado com `config --quiet`;
  NÃO aplicado. Não limita arquivos internos de sessões/estado do OpenClaw.

## Observação real da VPS

Scripts copiados exclusivamente para `/opt/idml-platform/qualification/v12-operations-v1`.
Auditoria executada pelo stdin do Python do container existente, com transação PostgreSQL
READ ONLY, timeout SQL de cinco segundos e limites de 10 mil registros/entradas e 15 segundos.

- Um registro e um arquivo: zero órfão candidato, ausente, tamanho divergente ou entrada insegura.
- Disco livre observado: 15.836.581.888 bytes. Nenhuma quota em aviso/crítico.
- Imagem em uso ainda não possui os novos limites: a auditoria explicitou
  `candidate_defaults_for_legacy_runtime` (2 GiB/empresa, 10 mil arquivos, reserva de 5 GiB).
  Esses valores foram usados para diagnóstico, NÃO comprovam enforcement na imagem atual.
- Backups: 90 conjuntos protegidos, 49 entradas não reconhecidas ou incompletas, zero
  candidato à revisão para expurgo. Essas 49 entradas precisam de classificação na próxima
  etapa; a contagem NÃO significa 49 backups corrompidos.
- Readiness, banco e Redis saudáveis antes/depois; início da API inalterado em
  `2026-09-21T12:25:37.56454542Z`. Nenhum comando de restart/deploy, exclusão ou provider usado.

A primeira execução do inventário falhou por `datetime.UTC` ausente no Python 3.10;
compatibilidade corrigida para `timezone.utc` e execução remota repetida com sucesso.
Não foram verificados hashes de conteúdo, checksums de backup nem restauração nesta etapa.
Nenhuma inferência paga ou alteração do XML.

## Verificação e limitações

566 testes locais aprovados, três avisos; cobertura de 87,72% do pacote `idml_foundation`
(a métrica não inclui os scripts em `ops`). Vinte novos testes cobrem auditoria e retenção.
Ruff e formatação aprovados. Evidências locais: `tmp/phase7-v12-operations-tests.xml` e
`tmp/phase7-v12-operations-coverage.json`. Registro sanitizado da VPS:
`benchmarks/qualification/reports/v12-operations-observation-v1.json`.

Requalificação consolidada aprovada em `v12-operations-requalification-v1.json`: 18 gates
e verificações dos dois artigos aprovados, XMLs com hashes preservados e zero bloqueio
semântico detectado no corpus atual. Validadores externos em replay vinculado por hash,
sem nova execução externa. Isso não substitui homologação humana nem libera produção.

## Próxima etapa e critérios de conclusão

Atualização: classificação e restore isolado do backup existente concluídos; 34 nomes não
canônicos preservados e 15 conjuntos sem estado OpenClaw identificados. Ver
`PHASE_7_V12_BACKUP_RESTORE.md`. O próximo bloco é backup NOVO coordenado e implantação.

1. Classificar as 49 entradas de backup sem exclusão; verificar checksums e capacidade.
2. Preparar snapshot coerente de banco/artefatos, restauração isolada e rollback da candidata.
   O backup atual não pausa API/worker; sua coerência durante gravações precisa ser comprovada.
3. Requalificar a candidata integrada e implantar em janela controlada; validar quotas atuais,
   captura de alertas, agendamento, logs Docker e retenção dos logs internos do OpenClaw.
4. Apenas depois considerar limpeza: checksum e restore comprovados, cópia recuperável fora
   do host e alvos exatos revisados. Mover dentro do mesmo disco NÃO recupera espaço.
5. Prosseguir para V-12.3 (janela prolongada/saturação/perfis combinados), demais gates e
   homologação final pelo especialista. Não antecipar aprovação de produção.

`v12_2_complete=false`, `production_capacity_qualified=false`, `release_ready=false`.
