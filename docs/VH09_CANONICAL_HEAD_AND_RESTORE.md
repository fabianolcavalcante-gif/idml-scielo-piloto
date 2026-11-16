# VH-09 — Versão de trabalho explícita e restauração conservadora

Incremento de 2026-10-21, implantado em 2026-10-22. Mesmo item VH-09, sem fase nova. Não implementa ainda
promoção automática validada, aprovação editorial ou G-HOMOLOG.

## Mudança funcional

- `canonical_head_events` registra uma sequência append-only de versões de
  trabalho, com hashes, vínculo anterior e chave idempotente. Migração aditiva
  `c0e1f2031425`, depois de `b9d0e1f20314`, sem reescrever artigos antigos.
- A versão de trabalho não é mais necessariamente o maior número de snapshot.
  Artigos legados sem evento mantêm a regra antiga até a primeira transição.
  Um snapshot reutilizado por deduplicação não restaura nada implicitamente.
- Novos snapshots canônicos geram evento no mesmo savepoint. Transições posteriores
  incrementam a versão do recurso, inclusive A → B → A: tarefas/grants antigos não
  recuperam validade só porque o hash do artigo voltou a ser igual.
- Revisão humana, concessão de grants, staging e revalidação consultam o mesmo
  seletor de versão atual. Snapshot candidato da automação continua fora dessa
  linhagem até implementação e aprovação da promoção formal.
- Criação de revisão, claim e decisão humana compartilham o lock do recurso usado
  pela automação. A decisão humana inteira fica em savepoint; falha no validador
  não deixa versão, decisão ou mudança parcial do item.

## Restauração interna, com limites explícitos

`restore_working_head` aceita somente um snapshot já integrante da linhagem,
da mesma empresa, artigo e fonte, com bytes canônicos conferidos. Exige versão
atual esperada e chave de requisição. Repetição devolve evidência histórica, sem
reaplicar a restauração sobre uma edição posterior. Não duplica nem apaga snapshots.

Restauração recusa qualquer artigo com decisão humana ou item atualmente assumido
por um revisor. Não decide automaticamente quais alterações humanas desfazer.
Itens abertos são vinculados à versão restaurada e têm versão incrementada;
requisições feitas sobre a versão anterior são invalidadas.

O resultado exige nova validação (`requires_revalidation=true`), não herda
aprovação (`release_approved=false`) e não publica arquivos. Não há novo endpoint,
ferramenta de IA ou botão de restauração. A interface/worker serão ligados somente
com a política, autenticação e ciclo completo previstos na lista VH1.

Essa entrega é a base transacional para restauração de rascunhos não revisados,
**não** restauração completa de pacote promovido/revalidado. Permanecem pendentes
a promoção condicionada às validações obrigatórias e a reconstrução/revalidação
do pacote da versão restaurada. XPM ainda não está conectado nesse caminho.

## Verificação local

23 testes novos de versão/restauração, compondo 180 testes direcionados aprovados.
Cobrem idempotência após edição posterior, duas sessões com a mesma chave e com
chaves concorrentes, adulteração, rollback, legado, empresa errada, snapshot não
ativado, proteção humana, atualização dos itens e edição sobre a versão restaurada.
Mypy: 126 módulos; Ruff global aprovado.

A suíte integral encontrou o gate VH-08 vinculado ao hash anterior de `reviews.py`.
Foi reexecutada a matriz da política: 102 testes e 100% de linhas/ramificações nos
dois módulos medidos. Prova nova `vh08-autocorrection-policy-v2.json`, mantendo v1
como histórica; os 11 testes de contrato/verificação passaram novamente. Não foi
retirada checagem de hash nem ampliada a política. CI global não declarado aprovado.

## Operação deste incremento

Release própria `vh09-heads-20261021-v1`, construída por
`ops/build_vh09_heads_source.py`. `ops/deploy_vh09_heads.py` reutiliza o processo
de backup/restore, imagens limitadas, qualificação Linux/PostgreSQL e verificação
de hashes/permissões, sem sobrescrever os registros da release de 20/10.

`ops/qualify_vh09_heads_postgres.py` usou banco isolado e comprovou duas sessões
de restauração, conflito de versão, bloqueio nativo durante claim humano, recusa
após o commit humano, triggers e rollback externo. Não usou dados ativos como fixture.

O ensaio de rollback para a imagem de 20/10 só é permitido enquanto não há eventos
de versão de trabalho no banco ativo. Depois de uma restauração, uma imagem antiga
que só conhece a maior revisão pode selecionar o artigo errado: usar imagem que
entenda a linhagem ou recuperação explicitamente qualificada. Nunca executar
downgrade da tabela para viabilizar rollback.

## Qualificação na VPS

223 testes Linux aprovados (um warning de depreciação da biblioteca de testes).
PostgreSQL nativo aprovou os dois cenários de concorrência, timeout de lock durante
claim humano, recusa após commit humano, rollback externo e recusa de UPDATE/DELETE
pelo trigger append-only. Banco isolado criado e removido pelo ensaio; nenhuma
fixture foi inserida no banco ativo.

A primeira tentativa Linux parou antes dos testes por falta de acesso do UID 10001
à pasta de fontes. Antes de abrir a travessia/leitura das fontes, o arquivo de
recuperação foi protegido com modo 0600, como o ambiente privado de rollback.
O build foi repetido e a qualificação passou. Arquivo de fonte final (1.123 arquivos,
sem corpus/segredos): SHA-256
`0bde59491871395b70431f2eb9b12d6b40a0f6da0ce02b03d703a1f65bcd8898`.
Os registros de preparação/backup foram preservados, sem repetir backup nem apagar
evidências da release anterior. A correção de permissão do arquivo de recuperação
também foi aplicada à release de 20/10; seu conteúdo não mudou.

## Implantação confirmada em 2026-10-22

API/worker em `idml-foundation:vh09-heads-20261021-v1`, imagem
`sha256:e62c59509fdf366c7d95b0d9b49c53ecd0320f576b1822b887cbe2296d5aeec5`.
Migração `c0e1f2031425` aplicada. 324 arquivos de runtime foram conferidos na
imagem em execução, por hash e ausência de escrita pelo UID da aplicação;
o mesmo conjunto local e todos os testes conferem com o manifesto congelado.

Como a ativação aconteceu no dia seguinte à preparação, foi gerado um backup
adicional, `/opt/idml-platform/backups/20261022T120540Z`, e sua restauração foi
testada em banco/diretório isolados antes da troca. O ensaio recuperou 26 tabelas,
um arquivo de artefato e 14 arquivos de estado OpenClaw. O backup de preparação
de 21/10 continua preservado e referenciado no recibo original de deployment;
o adicional tem recibo separado `preactivation-20261022.json`.

Retorno real à imagem de 20/10 e reaplicação concluídos com tabela de eventos
de versão ainda vazia. Cinco serviços IDML saudáveis, contagens dos dados
existentes preservadas e demais serviços com os mesmos containers/inícios/restarts.
O `.env` aponta à imagem efetivamente ativa; credenciais não foram exibidas.
Nenhum artigo real teve versão restaurada e nenhum job IA foi iniciado.

Readiness e `/app` retornaram 200; `/v1/resources` sem autenticação retornou 401;
CSP e nosniff presentes. Sem nova porta/URL. É smoke operacional, não E2E de
homologação. Flags continuam falsas; a implantação não conclui VH-09 nem G-HOMOLOG.
Registros sanitizados na pasta da release: `deployment.json`,
`preactivation-20261022.json` e `postcheck-20261022.json`.

A suíte integral anterior foi interrompida sem JUnit/cobertura final utilizáveis.
A repetição de 22/10 terminou: **2.654 testes aprovados**, zero falhas/erros/skip,
seis warnings; **90,04% de cobertura de linhas**, 13.087/14.534, sem medição global
de ramificações. Duração JUnit: 1.185,251 s (19min45s). Log, JUnit e cobertura
em `tmp/vh09-head-final-*-20261022.*`; a execução incompleta não foi somada.
Os conjuntos de 180 locais, 223 Linux e política/contratos se sobrepõem à suíte.
Os 2.631 testes/89,99% da release de 20/10 permanecem históricos.

Registro consolidado: `benchmarks/qualification/reports/vh09-head-vps-v1.json`.
Vincula arquivo de fonte, imagem, testes, cobertura, PostgreSQL, backup/restore,
rollback e smoke por hashes. Ruff global, mypy 126 módulos, formatação dos 18
arquivos do incremento e prova VH-08 passaram novamente. Não declara CI global
aprovado: as pendências existentes de prova V09, formatação histórica e orçamento
do runner continuam em VH-17. Cobertura não é taxa de precisão do XML.

Próximo passo na lista existente: concluir compatibilidade/conexão XPM e demais
validações obrigatórias (VH-02/07); em seguida, promoção formal e reconstrução/
revalidação do pacote restaurado (VH-09). Só depois conectar worker/ciclo IA,
interface e E2E, sem aumentar campos elegíveis nem dispensar validadores.
