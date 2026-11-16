# VH-09 — Histórico persistente e atualização intermediária da VPS

Checkpoint de desenvolvimento: 2026-10-20. Não é encerramento da VH-09,
ativação de correções autônomas, aceite editorial ou aprovação SciELO.
Estado posterior, com linhagem/restauração de rascunhos e implantação de 22/10:
`VH09_CANONICAL_HEAD_AND_RESTORE.md`. Os números deste checkpoint permanecem históricos.

## Desenvolvimento entregue

`services/autocorrection_history.py` conecta a execução real do serviço interno
de revalidação à persistência transacional:

- `revalidate_and_store` executa a reconstrução/revalidação; não recebe XML,
  ZIP ou relatórios fornecidos pelo cliente como se fossem provas do servidor.
- XML e pacote são armazenados como artefatos privados da empresa, com nomes
  `evaluation-*`, hashes, quotas e verificação de integridade existentes.
- Relatórios offline/formal, manifesto e recibo ficam ligados à tentativa
  original. O recibo tem hashes e referências; os relatórios são dados privados.
- Chave de requisição por empresa garante idempotência. Repetir a chave devolve
  **evidência histórica**, não nova autorização. Trocar os parâmetros sob a mesma
  chave é recusado. Nova chave executa nova validação; bytes idênticos são deduplicados.
- Savepoint protege contra gravação parcial; o chamador continua responsável pelo
  commit. Um rollback pode deixar arquivo CAS imutável órfão, sem registro aprovado;
  ele permanece contabilizado na quota e só pode ser reutilizado após conferência.
- `read_revalidation` confere empresa, recurso, tentativa, recibo, relatórios e
  bytes dos artefatos. Revogação/descarte posterior não apaga o histórico.
  Ler esse histórico não autoriza sua promoção.

Tabela nova `automation_revalidations`, migração `b9d0e1f20314`, após
`a8c9d0e1f203`. Proteção append-only no ORM e por triggers SQLite/PostgreSQL.
São cinco tabelas de automação no total. As migrações são aditivas, sem alteração
dos snapshots, decisões humanas, usuários, permissões ou releases existentes.

`promotion_authorized=false`, `historical_evidence_only=true` e
`release_approved=false` permanecem obrigatórios. Não há novo endpoint público
nem ligação automática ao worker. A lógica de promoção/restauração da cabeça
canônica ainda precisa ser implementada; isso não foi substituído pelo histórico
nem pelo teste de rollback da **imagem**.

## Qualificação

- 16 testes novos de persistência: idempotência, conflitos, empresa errada,
  adulteração, interrupção entre escritas, rollback externo, reutilização CAS,
  duas sessões e triggers do banco migrado.
- 73 testes direcionados de persistência/pacote/transações passaram localmente.
- Suíte integral da fonte implantada: **2.631 aprovados**, zero falhas/erros/skip,
  1.196,671 segundos; cobertura de linhas **89,99%** (12.960/14.401).
  Resultado encerrado em 20/10 e recuperado em 21/10 após a interrupção.
- 199 testes passaram em Linux na VPS, sem rede no container de testes.
- PostgreSQL nativo: banco isolado criado para o ensaio e removido ao final;
  upgrade completo, cinco triggers, duas sessões concorrentes gerando um único
  registro, bloqueio de UPDATE/DELETE e rollback externo comprovados.
  Nenhuma tabela do banco ativo foi usada para as fixtures.

Executores externos de validação continuam sintéticos nesses testes. Validação
offline/JATS é exercitada; isso não é nova execução de artigos reais no XPM,
Packtools ou SPSValidator. A ausência de XPM continua explícita.

## Implantação controlada

Scripts: `ops/build_vh09_source.py`, `ops/deploy_vh09.py` e
`ops/qualify_vh09_postgres.py`. Release intermediária `vh09-20261020-v1`.
O arquivo allowlisted contém 1.113 arquivos de fonte, testes, configuração e
documentação, sem `.env`, credenciais ou corpus privado. Manifesto por arquivo
permite comparar o runtime efetivo com a fonte enviada.

Foi corrigida, antes da ativação, a herança de permissões Windows `0666`: arquivos
de fonte passam a `0644`, scripts shell a `0755`. O pós-check também exige que o
usuário da aplicação não possa escrever nos arquivos de runtime verificados.

O procedimento preserva imagem anterior, `.env` de rollback e backup; testa
restauração isolada, aplica migrações aditivas e substitui somente API/worker.
Banco e Redis não são recriados; nenhum serviço do outro projeto é reiniciado.
O rollback de imagem mantém as tabelas aditivas: **não executar downgrade no banco
ativo** para desfazer uma atualização da aplicação.

## Resultado da atualização da VPS

Implantação concluída em 2026-10-20, sem ativar automação:

- API/worker em `idml-foundation:vh09-20261020-v1`, imagem
  `sha256:903a1027c94116a884f118dbbb0e31d1ea4af6b2a2a8d944b79c8ffc6831e32f`.
- Banco ativo na revisão `b9d0e1f20314`; 322 arquivos do runtime conferidos por
  SHA-256, sem permissão de escrita pelo usuário da aplicação.
- Backup `/opt/idml-platform/backups/20261020T183258Z` restaurado em teste isolado.
  Retorno real à imagem `phase7-7c08-v1` e reaplicação da nova imagem passaram.
  Esse teste é de recuperação da aplicação, não de restauração de um artigo.
- API/worker saudáveis; contagens dos dados existentes preservadas. IDs, início,
  reinícios e saúde dos demais containers não mudaram.
- `/app` respondeu 200; `/v1/resources` sem autenticação respondeu 401.
  CSP e `nosniff` presentes. Mantido o acesso existente, sem nova porta pública.
- Flags IA desligadas; nenhuma chamada paga, autorização real de autocorreção
  provisionada ou nova validação dos artigos reais foi realizada neste incremento.

Provas operacionais sanitizadas em
`/opt/idml-platform/releases/vh09-20261020-v1/`: `deployment.json`,
`qualification.json`, `postgres-tests.log` e `linux-tests.log`.
Arquivo de fonte SHA-256
`3e1248fc090b5e21a498db1f28e1ea48a07db095dc5e91b40104429087fa7555`.
Os checkpoints locais anteriores permanecem históricos, não provas da fonte atual.
Registro consolidado: `benchmarks/qualification/reports/vh09-history-vps-v1.json`.
Atualizações documentais posteriores são sincronizadas separadamente, sem alterar
o arquivo de fonte congelado nem a imagem qualificada.

## Próximo trabalho, sem nova fase

1. Concluir promoção/restauração com cabeça/linhagem explícita e rechecagem atômica,
   integrada aos escritores/leitores de revisão humana. Não usar a maior revisão
   como sinônimo de versão aprovada nem duplicar snapshots antigos.
2. Finalizar a conexão das validações obrigatórias, incluindo as pendências
   XPM VH-02/07. Não reduzir a política de aprovação para desbloquear automação.
3. Conectar o ciclo controlado ao worker e à interface (VH-10–13), provisionar as
   autoridades reais e executar os dois artigos pelo fluxo implantado.
4. Encerrar os controles operacionais/CI/E2E restantes e entregar o roteiro do
   especialista. O escopo continua sendo a lista única de 20 itens, não novas fases.
