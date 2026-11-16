# V-12.2 — classificação e restauração isolada

Data: 2026-09-25. Ensaio de recuperação de um backup existente concluído; não é implantação.

## Desenvolvimento

- Inventário agora classifica entradas não canônicas, caminhos inseguros, arquivos ausentes/
  vazios e datas futuras, sem emitir nomes privados nem permitir exclusão.
- `ops/verify_backup.py` valida os três SHA-256 do manifesto. Os caminhos absolutos históricos
  nunca são seguidos: somente os nomes permitidos são lidos na pasta selecionada.
- Extração própria limitada a 128 MiB e 10 mil entradas por arquivo compactado; rejeita links,
  dispositivos, travessia de diretórios, duplicatas e sobrescrita de destino existente.
  Extração não preserva permissões inseguras do tar; arquivos ficam privados.
- `ops/qualify_backup_restore.py` restaura em PostgreSQL separado, sem rede/portas, sem volumes
  ativos e sem credenciais reais. Verifica tabelas, tamanho/hash dos artefatos registrados e
  integridade SQLite do OpenClaw. Os agentes restaurados nunca são iniciados.
- O helper legado `ops/restore-test.sh` não foi executado: ele usa o PostgreSQL em serviço e
  remove um banco de nome fixo. O ensaio novo recusa container preexistente e remove somente
  o container criado e a pasta temporária exata validada.

## Resultado na VPS

Backup selecionado: `20260921T121706Z`, o mais recente no inventário consultado.
Imagem PostgreSQL 16 já instalada, fixada pelo ID no relatório. Nenhum download de imagem.

| Verificação | Resultado |
|---|---|
| Manifesto SHA-256 | 3/3 arquivos íntegros; 165.053 bytes compactados |
| PostgreSQL isolado | 21 tabelas públicas restauradas sem erro |
| Artefatos | 1 arquivo, 272 bytes; tamanho e hash conferidos contra o banco restaurado |
| OpenClaw | 14 arquivos, 3.406.839 bytes; configuração presente e SQLite íntegro |
| Recursos | limite 192 MiB, 0,25 CPU, sem swap adicional; dados PostgreSQL em tmpfs de 128 MiB |
| Observação | 8 amostras, mínimo disponível 906.768.384 bytes, readiness máximo 10,86 ms |
| Preservação | serviços existentes inalterados, sem OOM, banco ativo não modificado |
| Limpeza | container isolado e cópias temporárias removidos; originais preservados |

Evidência: `benchmarks/qualification/reports/v12-backup-restore-v1.json`. As cópias temporárias
removidas podem ser recriadas a partir do backup original, que não foi alterado.

Inventário: 90 conjuntos protegidos pela regra de sete mais recentes OU até 30 dias.
As 49 entradas restantes são 34 nomes fora do padrão e 15 conjuntos sem
`openclaw-state.tar.gz`; estes 15 possuem os outros arquivos esperados não vazios. Nenhuma
data futura/caminho inseguro detectado. Não inferimos corrupção nem autorizamos remoção.
Os 34 nomes legados permanecem preservados e fora de qualquer expurgo automático.

## Escopo comprovado e limitações

Regressão local: **581 testes aprovados, três avisos, cobertura 87,72%** do pacote
`idml_foundation` (scripts `ops` fora dessa métrica). Quinze novos testes de manifesto e
extração; 35 testes focados de backup/auditoria aprovados após o detalhamento do inventário.
Ruff e formatação aprovados. Evidências em `tmp/phase7-v12-backup-tests.xml` e
`tmp/phase7-v12-backup-coverage.json`. O pipeline XML não foi alterado nesta etapa.

O sucesso comprova recuperabilidade do backup selecionado, não de todos os históricos.
Hashes confirmam integridade em relação ao manifesto, não autenticidade contra adulteração
conjunta. O inventário geral continua indicando checksums/restore não verificados para a
coleção inteira. Não foi gerado backup novo nem pausado o sistema ativo.

O watchdog verifica reservas e saúde entre as operações; cada comando tem timeout de 45 s.
Não é monitoramento contínuo durante cada comando. O volume pequeno deste backup não
qualifica automaticamente restaurações grandes. Conteúdo sensível ficou somente na VPS,
em pasta privada temporária; nenhum conteúdo de backup foi copiado ao computador local.

## Próximo bloco: snapshot coerente e implantação

Repriorização de 2026-09-25: esta sequência passa a apoiar H2 do plano
`EXPERT_TEST_READINESS_PLAN.md`. A próxima ação geral é H0 (escopo/bloqueadores formais e
funcionais); somente a proteção mínima necessária à VH precede a avaliação do especialista.

1. Implementar backup coordenado com trava exclusiva e recuperação garantida em falha.
   Impedir novas gravações, drenar jobs em andamento (com prazo e aborto seguro), só então
   parar API/worker dedicados; não afetar outro projeto nem pausar PostgreSQL/Redis.
2. Registrar estado prévio dos serviços e restaurar somente os que estavam ativos. Pausar
   apenas o OpenClaw dedicado durante sua cópia, com tratamento de sinais/falhas.
3. Capturar banco e artefatos na mesma janela sem escritores, gerar manifesto e marcador de
   conclusão somente ao final. Retomar serviços e comprovar readiness antes de continuar.
4. Repetir este ensaio isolado sobre o backup NOVO; reprovação bloqueia rollout.
5. Requalificar candidata, implantar com rollback de imagem/configuração, verificar quotas,
   logs e auditoria. Não alterar esquema sem plano específico de compatibilidade/rollback.
6. Ativar agendamento/rotação somente após comprovar alertas e preservação dos serviços.

Continuam pendentes cópia recuperável fora da VPS, tratamento dos nomes legados, política
dos logs internos OpenClaw, V-12.3, demais gates e homologação humana final.
`v12_2_complete=false`, `release_ready=false`.
