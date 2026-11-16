# Correções automáticas por IA antes da homologação humana

Atualização de 05/11 — ambos os IDMLs geraram XML e ZIP iguais às referências qualificadas na aplicação ativa. As avaliações se abstiveram. O aceite técnico e o roteiro de entrega estão na seção 61 de HOMOLOGATION_VH1_DELIVERY.md.

Atualização de 04/11 — fila do antivírus corrigida; envios consecutivos e simultâneos qualificados, uma varredura por vez. Release vh11-scan-queue-20261104-v1 ativa. O replay HTTP dos pacotes confirmou a comparação enriquecida, mas a ligação dos catálogos ao fluxo normal ainda falta. Ver seção 60 de `HOMOLOGATION_VH1_DELIVERY.md`.

Atualização de 04/11 — ciclo restrito iniciado pelo portal e consultado com perfil de revisor na RC isolada; quatro chamadas reais, aplicação e recuperação nativas válidas, restauração incompleta bloqueada. Release vh11-web-20261103-v1 implantada, provedor fechado. Restam fluxo geral dos dois artigos e fechamento da RC, conforme seção 59 de `HOMOLOGATION_VH1_DELIVERY.md`.

Atualização de 03/11 — a correção de uma afiliação e a restauração passaram pela validação nativa na cópia isolada do e20240086. O pacote corrigido reproduziu a referência histórica. As cinco figuras usam as versões publicadas. Avisos editoriais e a integração web do ciclo permanecem pendentes. Ver seção 58 de `HOMOLOGATION_VH1_DELIVERY.md`.

Atualização de 02/11 — ciclo com quatro papéis executado no OpenClaw da VPS. O candidato sintético foi bloqueado na validação nativa; os dois IDMLs reais se abstiveram. Segue pendente o positivo de aplicação e restauração com metadados completos, DOI autêntico e evidência da edição. Ver a seção 57 de `HOMOLOGATION_VH1_DELIVERY.md`.

Atualização de 01/11 — a verificação prévia de edição está implantada na VPS. Os dois IDMLs reais resultaram em abstenção. Com decisão específica para a revisão, um artigo sintético produziu um XML candidato válido offline. O próximo ensaio exercita o ciclo limitado do OpenClaw e a revalidação do pacote. Ver a seção 56 de `HOMOLOGATION_VH1_DELIVERY.md`.

Atualização de 31/10 — etapa de arquivos. Na VPS, a API verifica uploads e relê históricos com auditoria. Nos dois pacotes enriquecidos, as 12 figuras coincidiram com os bytes fornecidos. Faltam a confirmação da origem canônica dessas figuras e o ensaio de edição autorizada e de abstenção. Evidências e limites na seção 55 de `HOMOLOGATION_VH1_DELIVERY.md`.

Etapa anterior de 31/10. A conversão pelo worker prepara evidências exatas do IDML e
preserva o XML produzido antes dessa preparação. A reconstrução de candidatos e
restaurações já pode acionar os validadores configurados na VPS. Os dois IDMLs
originais não apresentaram operação nas três regras atuais. Um caso sintético
com afiliação ausente exercitou o caminho com evidência positiva. Os critérios
para arquivos verificados, autorização de edição e ciclo OpenClaw estão na seção
54 de `HOMOLOGATION_VH1_DELIVERY.md`. Agentes desativados para os usuários.

Controle de execução/limite de escopo em 2026-10-01: `HOMOLOGATION_VH1_DELIVERY.md`
(ADR-017). H1-A1–A5 são mapeados em VH-08–10/12/17–18, não uma fila adicional.
Para a primeira entrega, prevalece a allowlist restrita da VH1; famílias amplas
citadas abaixo não autorizam novos campos sem qualificação explícita.

Estado atual, 2026-10-30: serviços internos VH-09 implantados, incluindo promoção
e revalidação do pacote restaurado; migração d1f203142536 ativa. Worker conectado
a Packtools/SPS/XPM e brokers supervisionados. Dois artigos testados no job real,
com banco isolado e sem chamada IA. Falta integrar fontes por empresa/artigo e
propor/criticar/adjudicar/aplicar/revalidar/restaurar no ciclo limitado, seguido do
fluxo web e E2E. Flags IA continuam falsas. Detalhes e sequência única: seção 52
de `HOMOLOGATION_VH1_DELIVERY.md`. Os registros abaixo são históricos.

Data inicial: 2026-10-01. Atualização 2026-10-22: H1-A1/VH-08 implementado e
qualificado como contrato/política; H1-A2/VH-09 parcial com staging transacional,
extração exata, descarte e histórico da revalidação persistidos. PostgreSQL nativo
qualificado e versão intermediária implantada. Versão de trabalho explícita e
restauração conservadora de rascunho qualificadas em 21/10 e implantadas em 22/10;
promoção formal/pacote restaurado revalidado, XPM e ciclo real pendentes.
Detalhes: `VH09_CANONICAL_HEAD_AND_RESTORE.md`.
Incremento 23/10: executor candidato agora registra compatibilidade DOI derivada
e triagem ORCID com vínculo Crossref por autor; sete vínculos reais correspondem,
mas quatro nomes públicos e135 continuam não confirmados. Não são operações
elegíveis de correção de identidade nem autorização de promoção. 498 testes locais
e 498 Linux aprovados; candidata na VPS, ainda não ativa. SPS/data/Wayta no fluxo
composto e DOCTYPE/JATS continuam pendentes. Ver `VH1_XPM_RUNTIME_COMPATIBILITY.md`.
Atualização 26/10: SPS/data e aplicabilidade Wayta já compostos no serviço candidato,
com execuções novas e hashes individuais preservados. Nenhuma ampliação da política
de autocorreção, mudança de identidade ou promoção automática. DOCTYPE/JATS, erro
residual e integração ativa/ciclo continuam pendentes; ver `VH1_XPM_COMPOSED_VALIDATION.md`.
Complemento 26/10: corrigido PUBLIC ID MathML3 determinístico e concluído o
diagnóstico técnico do legado (DTD 1.1/Style Checker sem SPS 1.10). Nenhuma regra
nova de IA, alteração de autoria ou dispensa de fatal. Agentes não devem sugerir
downgrade de JATS nem trocar `coi-statement` apenas para satisfazer XPM. Ver
`VH1_DOCTYPE_JATS_DECISION.md`; ativação/ciclo ainda pendentes.
Decisão: ADR-016. Este requisito integra H1–H3 e passa a ser obrigatório para
G-HOMOLOG desta entrega. Não autoriza produção, publicação ou aceite editorial.

## Objetivo e limite

Entregar ao especialista um candidato já convertido, analisado por agentes,
corrigido automaticamente dentro de uma política restrita e revalidado. O humano
não precisa aprovar cada operação elegível antes desse ciclo. Examina o resultado,
o histórico e as exceções ao final. Casos ambíguos ficam pendentes, sem invenção.

IA propõe operações tipadas sobre o modelo canônico; um executor determinístico
decide a elegibilidade, aplica transação e reconstrói o XML. Agentes não editam
XML/arquivos livremente, não alteram regras/allowlists, não dispensam validadores
e não podem aprovar release. Confiança declarada e consenso não bastam.

## Política inicial por operação

Todos os exemplos abaixo dependem de implementação, testes e política versionada.
Não são permissões globais para alterar qualquer campo semelhante.

| Classe | Operação candidata à aplicação automática | Condição obrigatória |
|---|---|---|
| A — representação | Ajustar código de país ou representação de identificador já conhecido | Mapeamento exato aprovado no perfil, preservando identidade e valor de origem; sem inferência por nome/localidade |
| A — vínculos | Corrigir destino de citação/referência, figura/tabela/fórmula ou afiliação | Um único destino comprovado na fonte, no mesmo escopo; sem criar IDs arbitrários, excluir objetos ou inventar citações |
| A — estrutura | Corrigir marcação estrutural com conteúdo preservado | Regra específica qualificada, sem perda/reordenação de conteúdo, comparação semântica e validação de referências |
| B — recuperação de fonte | Preencher/corrigir campo a partir de evidência autorizada | Valor obtido exatamente de fonte verificada, atual e vinculada ao artigo/empresa/campo; executor resolve evidência, não aceita texto inventado pela IA |
| C — revisão humana | Resolver contradições, ambiguidade editorial ou interpretação científica | Não aplicar automaticamente; apresentar alternativas, evidências e motivo da abstenção |

Na primeira versão, classe B só poderá ser habilitada para campos enumerados e
qualificados individualmente. Datas, ORCID, autoria, CRediT, financiamento e licença
começam não elegíveis; uma fonte pública isolada não autoriza mudar esses campos.
Uma extensão futura exige política explícita, correspondência inequívoca e testes.

Também não elegíveis inicialmente: transcrição OCR de fórmulas, alteração de valores
numéricos, unidades, sinal/símbolo matemático, texto científico, tradução, associação
de autor por semelhança, criação/remoção de autores, referências ou conteúdo para
silenciar um erro. Uma fórmula pode ter seu vínculo reparado sem alterar sua expressão.
Se a operação exige editar campos imutáveis atuais, ela é recusada até existir
operação dedicada segura; não remover proteções genéricas para viabilizá-la.

## Fluxo e garantias

1. Congelar snapshot inicial, fontes autorizadas, perfil e versões de ferramentas.
2. Executar validação inicial e selecionar achados elegíveis por domínio/escopo.
3. Proponente apresenta operação/evidências; críticos XML e editorial verificam;
   adjudicador pode recomendar, rejeitar ou abster-se. Registrar se os papéis usam
   o mesmo modelo; não anunciar independência inexistente.
4. Política do servidor verifica operação/campo permitidos, integridade, versão
   esperada, empresa, evidência exata, limites e ausência de conflito. Proposta
   marcada para humano não pode ser reclassificada automaticamente apenas por voto.
5. Aplicar em cópia candidata transacional e idempotente; nunca sobrescrever origem
   ou decisão humana. Operações acopladas (texto/inlines, fórmula/representação)
   permanecem atômicas. Rejeitar proposta velha e concorrência conflitante.
6. Reexecutar checks determinísticos, integridade de assets e validadores aplicáveis
   na mesma versão/configuração. Exigir melhora comprovada no achado-alvo, nenhuma
   nova falha impeditiva e invariantes de conteúdo preservados. Menor contagem de
   erros, sozinha, não aprova uma alteração. Falha/indisponibilidade de validador
   impede promoção; manter a tentativa para diagnóstico sem marcá-la aceita.
7. Promover só a candidata aprovada por esses critérios, mantendo before/after.
   Limite inicial: dois ciclos corretivos por artigo, uma execução concorrente na
   VPS atual, e limites configurados de tempo/tokens/custo/recursos. Detectar ciclos,
   repetir sem progresso e retornar pendência; nunca execução ou gasto ilimitado.
8. Entregar ao especialista o resultado e a trilha. Distinguir: correção aplicada,
   correção desfeita/rejeitada, pendente de humano e validação formal concluída.
   Aprovação editorial/final e publicação continuam separadas.

Parar com segurança em evidência insuficiente, desacordo material, fonte divergente,
injeção de instruções no artigo, timeout, limite, resposta inválida ou falha de rede.
Modo sem IA deve continuar utilizável, sem fabricar conclusão dos agentes.

## Fases de implementação — H1-A

### H1-A1 — Contratos e política (antes de habilitar aplicação)

- [x] Inventariar operações/campos elegíveis e negados por perfil/domínio; política
  versionada e aprovada por configuração administrativa, não pelo agente.
- [x] Criar contratos de estados/eventos próprios para automação, autoria de serviço e vínculo
  de snapshot; distinguir proposta de aprovação editorial.
- [x] Preservar contratos históricos `needs_human=true` e relatórios assistivos:
  criar versão específica, sem converter decisões antigas em permissão automática.
- [x] Especificar custo/tempo/ciclos e comportamento de abstenção/interrupção.

Aceite de política em 2026-10-19: `VH08_AUTOCORRECTION_POLICY.md` e
`vh08-autocorrection-policy-v1.json`. Três operações, somente ausência: código de
país, vínculo figura/asset e original de afiliação. Nenhum outro exemplo amplo
deste documento está habilitado. No checkpoint seguinte, H1-A2/VH-09 passou a
persistir grants, tentativas e descarte em staging; não alterou o contrato de
elegibilidade nem habilitou aplicação na versão ativa.

Aceite: testes positivos/negativos de todas as permissões; nenhum campo fora da
allowlist, evidência obsoleta ou proposta humana aplicada automaticamente.

### H1-A2 — Executor reversível e revalidação

- [~] Transações, idempotência, isolamento multiempresa, bloqueio otimista e cópia
  candidata; histórico append-only e restauração sem apagar tentativas.
- [~] Reconstrução XML/pacote com evidência before/after; comparação de invariantes
  e revalidação em runtime fixado. Não reusar aprovação de hash anterior.
- [ ] Aplicação sem revisão humana intermediária somente para operações elegíveis;
  rollback da candidata em falha, sem adulterar estado humano ou release.

Aceite: repetição/queda/concorrência não duplicam nem perdem alterações; teste com
mudança aparentemente válida que perde conteúdo deve reprovar.

Checkpoint 2026-10-20: à cópia isolada e ao histórico do dia 19 foram acrescentados
produtor opt-in de evidência de campo, grants derivados de autorização de lote e
reconstrução/revalidação privada do pacote completo, com rechecagem antes/depois.
Alterações fora dos três campos permitidos e perda de conteúdo no empacotamento
continuam proibidas. O serviço interno agora persiste a revalidação com
idempotência; PostgreSQL nativo qualificado e migrações aplicadas na VPS.
Worker/ciclo automático, conexão XPM e promoção/restauração continuam pendentes.
Descarte **não equivale à restauração de versão ativa**. Não exigir aprovação
humana a cada operação: provisão administrativa sob autorização da fonte,
nunca da saída do modelo. Flags permanecem desligadas. Ver evidências e limites
em `VH09_REVALIDATION_HISTORY_AND_DEPLOY.md`; H1-A2 permanece parcial.

Incremento 2026-10-21: versão atual selecionada por linhagem append-only,
restauração interna de rascunhos sem decisões/claims humanos, controle de versão
contra A → B → A e integração com leitura/locks da revisão humana. Não há
restauração autônoma de artigo revisado, promoção formal ou herança de aprovação.
Política requalificada em `vh08-autocorrection-policy-v2.json`, sem ampliar campos.
180 testes direcionados e 223 Linux aprovados; concorrência e proteção contra
claim humano comprovadas no PostgreSQL isolado. Detalhes/estado de implantação
em `VH09_CANONICAL_HEAD_AND_RESTORE.md`.

Em 22/10, API/worker atualizados para `vh09-heads-20261021-v1` e migração
`c0e1f2031425` aplicada, com backup novo, restauração isolada, rollback de imagem
e verificação de runtime. Nenhuma restauração de artigo real ou ciclo IA foi
executado. Concluir VH-02/07 antes de habilitar promoção; o pacote da versão
restaurada também exige validação nova, não herda aprovação anterior.
Regressão integral concluída: 2.654 aprovados, zero falhas/erros/skip, 90,04% de
cobertura de linhas. Prova `vh09-head-vps-v1.json`, sem declarar CI global,
precisão editorial ou aprovação formal a partir de cobertura.

Continuação candidata em 22/10 (seção 38 do plano VH1): ponte XPM interna ligada
à revalidação e ao histórico privado, com escopo/bytes conferidos e diagnóstico
sanitizado. 176 testes locais e 176 Linux (sobrepostos) aprovados. Não está ativa
na API/worker; executor supervisionado, retenção de HTML bruto, compatibilidade
completa e promoção permanecem pendentes. Sem nova permissão ou chamada de IA.

Continuação da seção 39, ainda em 22/10: executor offline original conectado por
socket privado, com autenticação de UID nas duas pontas e retenção root/0600 dos
relatórios. Dois artigos reais e dois negativos executados pela nova ponte; todos
retornaram diagnóstico atestado sem aprovação. 211 testes locais e 211 Linux
aprovados. A candidata `vh1-xpm-socket-20261022-v3` não está ativa na API/worker.
Consultas externas, compatibilidade integral e promoção continuam pendentes;
esta execução não utilizou IA nem substituiu o aceite humano.

Continuação online (seção 40, 22/10): a mesma ponte agora executa o XPM com proxy
supervisionado e rede interna descartável por execução. Dois artigos e dois
negativos reais, 12 recusas de destinos proibidos e 267 testes locais/267 Linux
aprovados. Catálogo HTTPS comparado aos metadados dos dois artigos com igualdade
exata. Túneis Crossref/ORCID não são evidência de resposta semântica; Wayta segue
visível como indisponível/recusado, com aplicabilidade própria já qualificada.
Nenhum indicador global de consultas concluídas, promoção ou IA foi habilitado.
Candidata isolada, ainda sem ligação ativa na API/worker.

Atualização de 29/10/2026: os checkpoints candidatos acima foram incorporados à
imagem `vh1-structural-20261028-v1`, agora ativa na API/worker. 625 testes Linux,
PostgreSQL isolado, backup/restore e rollback aprovados. A ponte interna e as
regras estão implantadas; a ligação supervisionada ao worker comum, a promoção
formal e a reconstrução/revalidação restaurada ainda não estão implementadas.
Flags IA continuam falsas; não houve aplicação automática. Próximo: fechar essas
duas funções do VH-09 antes de ligar o ciclo. Ver `VH1_STRUCTURAL_DEPLOYMENT.md`.

Continuação de 29/10/2026: a promoção para versão de trabalho com validação nova
foi implementada e qualificada como serviço interno, sem ativação no worker.
387 testes locais e Linux, concorrência PostgreSQL e reprodução da política
sobre relatórios nativos aprovados. Avisos permanecem pendentes; consultas
selecionadas divergentes impedem promoção. Repetição não reaplica a mudança e
revisão humana fica protegida. Resta implementar o pacote restaurado revalidado
antes da integração ao ciclo. Ver `VH09_WORKING_DRAFT_PROMOTION.md` e seção 50
da lista única. Nenhuma chamada IA, operação adicional ou publicação autorizada.

Fechamento interno do VH-09 em 29/10 (seção 51): pacote restaurado agora é
reconstruído/revalidado, com histórico próprio e transação combinada opcional.
421 testes locais/Linux e ensaio PostgreSQL aprovados. Migração d1f203142536
qualificada apenas no banco descartável; ainda não ativada. Promoção e
restauração internas estão implementadas; próximo desenvolvimento é integrá-las
ao worker/ciclo e executores supervisionados (VH-10/14), não criar nova fase.
Detalhes: `VH09_RESTORED_PACKAGE_VALIDATION.md`. H1-A2 continua parcial até o
aceite integrado, e aplicação automática segue desligada.

23/10, seção 41: coleta independente e validação semântica Crossref/ORCID ligadas
ao executor, com escopo, relatório, hash e validade de 24 horas. Conflito na fonte
externa bloqueia o pacote mesmo sem erro bruto XPM; ausência mantém pendência.
373 testes locais/373 Linux aprovados. Nos dois candidatos, Crossref corresponde;
e86 tem três nomes públicos ORCID correspondentes, e135 tem quatro não confirmados
pela comparação exata. Não implica por si só identificadores errados; investigar
fontes autorizadas, sem trocar nomes/ORCIDs automaticamente ou expandir allowlist.
Sem prova de titularidade autenticada, aprovação global ou nova chamada de IA.
Detalhes: `VH1_XPM_SEMANTIC_QUERIES.md`. Candidata v3 na VPS, não ativada.

### H1-A3 — Agentes e orquestração

- [ ] Conectar OpenClaw ao job controlado, com as ferramentas restritas existentes,
  evidências mínimas autorizadas e decisão determinística final de elegibilidade.
- [ ] Rodar propor → criticar → adjudicar → aplicar → revalidar até o limite.
- [ ] Testar rede/provider indisponível, resposta inválida, falso consenso,
  confiança alta indevida, contradição e instruções maliciosas no conteúdo.
- [ ] Registrar modelos, prompts, parâmetros, chamadas, custos e versões sem
  expor segredos ou texto privado em logs públicos. Não mudar limites de corpus.

Aceite: nenhum consenso consegue contornar uma barreira; uma operação segura
deve completar sem decisão humana intermediária; uma insegura deve se abster.

### H1-A4 — Interface do especialista e controle administrativo

- [ ] Mostrar alterações automáticas com diff, motivo, evidências, ciclo e resultado
  formal; permitir decisão humana e reversão com histórico e nova revalidação.
- [ ] Mostrar pendências sem chamar candidata de aprovada. Proteger downloads
  pelos controles existentes de artefato e release.
- [ ] Flags separadas para assistência/aplicação, habilitadas por empresa/perfil
  no piloto; kill switch administrativo. Testar desligamento entre ciclos.

Aceite: especialista distingue claramente o que a IA propôs do que o sistema
aplicou e do que os validadores realmente aprovaram.

### H1-A5 — Qualificação para entrega, integrada a H2/H3

- [ ] Matriz sintética por operação: correto, incorreto, ambíguo, sem evidência,
  evidência adulterada/vencida/de outra empresa, conflito e regressão silenciosa.
- [ ] Fontes reais autorizadas e casos não usados para ajuste, sem acesso ao gold
  de holdout; comparar fidelidade sem declarar generalização a partir de dois artigos.
- [ ] Execuções reais de IA (não só replay/mock) na candidata implantada: caso
  automático positivo, caso recusado e modo degradado, com custos e hashes.
- [ ] Regressão, segurança/RBAC, resource budget, backup/restore e rollback;
  confirmar os dois artigos de referência nos validadores aplicáveis.
- [ ] Pacote de evidências assinado logicamente por hashes/versões e limitações;
  zero alteração indevida nos casos de contraprova. Não prometer erro zero universal.

## Ordem do projeto

Manter H1 de validação/autoridades/conteúdo em andamento. H1-A1 pode ser desenvolvido
em seguida, mas a promoção automática exige base de validação confiável. Concluir
H1-A1–A4 antes do deploy candidato H2; demonstrar H1-A5 no fluxo H3 e só então
H4/G-HOMOLOG. Evitar expandir a primeira allowlist para todos os tipos de correção.

## Estado de partida e rastreabilidade

Hoje existem contratos assistivos, operações tipadas, evidências, revisão e testes
de agentes em laboratório; as flags da aplicação estão desativadas. Não basta
ativá-las: worker, política, executor, auditoria e interface precisam do ciclo acima.
Principais áreas: `ai/outputs.py`, `ai/contracts.py`, `ai/multi_agent_lab.py`,
`services/reviews.py`, `worker.py`, rotas de revisão/IA/UI e configuração de flags.
Mapear migrations necessárias antes de alterar estados persistidos.

Este documento declara H1-A1 concluída e H1-A2 parcial, não o ciclo automático
completo ou implantado. H1-A3–A5 continuam pendentes; aprovação dos gates
anteriores não é aprovação retroativa do fluxo completo.
