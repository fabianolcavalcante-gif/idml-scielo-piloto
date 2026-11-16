# Diagnóstico web de validação — VH-02/07

Incremento concluído em 27/10/2026 na candidata `vh1-diagnosis-20261027-v1`.
Implementa o primeiro próximo passo da decisão `VH1_DOCTYPE_JATS_DECISION.md`.
Não cria uma fase nova. A candidata foi armazenada e testada na VPS; a API/worker
ativos continuam em `vh09-heads-20261021-v1`.

## Comportamento entregue

No dashboard de Jobs, o botão **Diagnóstico de validação** mostra três grupos:

- **XML e pacote:** achados locais e dos validadores modernos. Erro no par
  PUBLIC/SYSTEM exige regeneração/revalidação. Avisos permanecem visíveis, sem
  serem confundidos com erro ou aceitos automaticamente.
- **Validadores e consultas:** resultado original do XPM, indisponibilidade de
  execução e consultas pendentes. A capacidade conhecida da distribuição
  4.0.096 é apresentada somente com atestado salvo consistente, distribuição
  fixada e perfil JATS 1.3 vinculado ao mesmo XML. A falta de suporte JATS 1.3/
  SPS 1.10 é contexto qualificado da ferramenta; não classifica automaticamente
  todas as ocorrências daquele artigo como defeitos do XPM.
- **Homologação e entrega:** ressalva de aceitação do DOCTYPE, G-HOMOLOG e
  aprovação editorial/publicação separadas da geração ou validação local.

O JSON original continua acessível em “Resultado técnico salvo”. A leitura não
altera o job, não zera contagens, não aceita avisos ou exceções, não executa
validação e não renova evidências/consultas antigas. Não concede aprovação.

## Contrato e segurança

`GET /v1/jobs/{job_id}/validation-diagnosis` requer `JOB_READ` e usa a mesma
consulta de job com filtro por empresa. Job inexistente ou de outra empresa
retorna 404; acesso sem autenticação retorna 401. Não recebe relatório ou
atestado fornecido pelo cliente.

A projeção usa apenas o resultado persistido pelo servidor. Confere versão do
contrato, hashes de XML/pacote, vínculo de cada entrada e tipos das contagens.
Ausência, duplicidade ou inconsistência gera evidência indisponível. Isso é uma
checagem de consistência da leitura, não nova certificação criptográfica dos
recibos. As garantias de execução continuam nos serviços originais.

Não publica HTML do XPM, texto do artigo, exceções privadas ou mensagens livres
dos validadores. Exibe rótulos fixos, hashes e contagens permitidas. A interface
escapa os valores e descarta respostas tardias após troca de job, empresa ou
sessão; atualizar a lista limpa o diagnóstico anterior.

## Validação executada

- 127 testes focados e 12 regressões web locais: **139 aprovados**, sem
  falhas/erros/skip. Os 34 casos novos estão incluídos nesses totais.
- O mesmo conjunto de **139 testes aprovado no Linux da VPS**, em container
  isolado, sem rede, filesystem de código somente leitura e limites de recursos.
- Seis verificações do JavaScript real da aplicação: renderização, escape e
  concorrência/troca de contexto. DOM mínimo controlado em Node; não equivalem
  a E2E visual em navegador real.
- V-10/V-11 reexecutados localmente e na VPS; Ruff global e mypy (133 módulos)
  aprovados. Nenhuma regra de validação, gerador XML ou política de release mudou.
- 1.184 arquivos da candidata conferidos por SHA-256; 25 serviços iguais ao
  inventário inicial; `/health/ready` e `/app` HTTP 200.

Relatórios atuais: `v10-operational-workflow-vh1-diagnosis-v2.json`,
`v11-robustness-mutation-vh1-diagnosis-v2.json` e
`vh1-diagnosis-closure-v1.json`, em `benchmarks/qualification/reports/`.
A tentativa parcial V-10 v1 foi preservada e não é a prova de fechamento.
As provas anteriores DOCTYPE/composição não foram reescritas.

Não se repetiu a suíte global de 2.906 testes do incremento anterior, nem se
mediu nova cobertura. Não houve nova execução online XPM, chamada de IA ou
integração externa PostgreSQL neste incremento. Os avisos de teste são a
depreciação conhecida do TestClient e serialização de um controle negativo.

## Próximo passo e critério de conclusão

Atualização de 28/10: item 1 implementado e qualificado na candidata de avisos/
consultas. Ver `VH1_QUERY_WARNING_FOLLOWUPS.md`. A próxima execução é o item 2.

Fechamento adicional de 28/10: item 2 também executado e auditado, com quatro
execuções XPM online e consultas novas. Ver `VH1_MATHML3_COMPOSED_VALIDATION.md`
para resultados e pendências formais antes da ativação do item 3.

1. Apresentar e tratar as pendências específicas de avisos/consultas/ORCID com
   fonte, estado e ação explícitos, sem inferir identidade ou aceitar avisos.
2. Reexecutar a composição completa para os pacotes MathML3 corrigidos, com
   recibos e consultas vinculados aos novos hashes. Somente essa execução pode
   fundamentar diagnóstico por ocorrência desses pacotes e eventual regra
   residual, qualificada separadamente pela ADR-019.
3. Requalificar e ativar com backup/rollback no fluxo já planejado; concluir
   VH-09–20 e G-HOMOLOG para disponibilizar o sistema ao especialista.

O painel de diagnóstico está implementado. A disponibilidade para o usuário
no ambiente ativo ainda depende dessa ativação. O XML não ganhou aprovação
SciELO e a publicação continua bloqueada.
