# VH1 — Escopo fechado e lista única para entrega à homologação

Revisão de 16/11/2026. Piloto web aberto para o especialista enviar novos artigos ESA, acompanhar o processamento e avaliar os dois exemplos de referência. Convite individual enviado. O aceite formal da versão e o parecer do especialista seguem em aberto. A seção 67 registra a ampliação do acesso.
Este é o controle principal de execução até G-HOMOLOG. Substitui a ordem de
trabalho e os “próximos passos” históricos espalhados nos documentos H0/H1/V-12.
Os documentos técnicos continuam referências/evidências, não novas filas paralelas.
ADR-017 registra a consolidação; ADR-015/016 e os controles de release permanecem.

## 1. O ponto de chegada

VH1 é um piloto funcional para um especialista avaliar ESA no template e perfil
qualificados. Não é indexação SciELO nem produção editorial. Estará tecnicamente
pronta quando os 20 itens abaixo estiverem encerrados com suas evidências, a versão
estiver implantada e o roteiro final passar. Não há obrigação de chegar a 100% de
cobertura, suportar todo IDML, eliminar todo aviso ou automatizar todo juízo editorial.

Experiência obrigatória: entrar na empresa → criar/selecionar artigo → enviar IDML,
PDF e imagens → processar → obter diagnóstico → executar correções automáticas
permitidas → revalidar → revisar diferenças/pendências → baixar artefatos de
avaliação identificados. Não exigir IDs copiados manualmente, terminal, SQL ou
preparação oculta de catálogos por artigo para apresentar o fluxo como funcional.
Preparação administrativa de fontes/perfil permitida, explícita e documentada.

Sucesso de job, XML gerado, DOI aprovado, validação formal e aceite humano são
estados distintos. Candidato inválido pode ser inspecionado pelo especialista,
com acesso controlado e rótulo de avaliação; não pode ser tratado como release
aprovado. Não relaxar a política formal vigente para permitir sua publicação.

## 2. Escopo de produto congelado

- ESA, JATS 1.3/SPS 1.10, perfil candidato de países 1.1 a fixar no item VH-01;
  apenas layouts/estruturas qualificados. Outros periódicos/templates ficam fora.
- Dois artigos reais existentes como regressão. Não chamá-los de corpus independente.
  Casos sintéticos de aceitação novos são congelados antes de ajustar a automação;
  artigos inéditos autorizados servem à avaliação e ampliação posterior, não promessa
  de conversão universal. Preservar holdout e não usar gold como entrada de conversão.
- Uma empresa piloto com usuários individuais; isolamento multiempresa obrigatório.
  Uma execução por vez na VPS atual, sem upgrade obrigatório e sem prejudicar o outro sistema.
- IA atuando antes do humano, com aplicação restrita a três famílias: normalização
  representacional exata; reparo de vínculo com destino único comprovado; recuperação
  literal de trecho não científico já existente em evidência autorizada no mesmo campo.
  VH-08 enumera caminhos/operações/testes concretos; qualquer caminho não enumerado é negado.
  Não inserir permissões genéricas para metadados sensíveis ou edição científica.
- Texto científico, fórmulas/OCR, novos valores, datas, ORCID, autoria, CRediT,
  financiamento e licença não têm alteração autônoma inicial. Enriquecimento
  administrativo verificado e revisão humana permanecem possíveis com rastreabilidade.
- No máximo dois ciclos IA; abstenção, reversão e modo sem IA. Modelo/prompts fixados
  por versão depois da qualificação, sem pesquisa indefinida de modelos “melhores”.
- Packtools/SPS em runtime fixado e XPM aplicável conforme política atual. Hashes,
  relatórios e proveniência devem corresponder ao pacote final, inclusive após correção.
- Interface funcional: seleção de arquivos, progresso, diagnóstico, diferenças,
  histórico, decisão/reversão e downloads. Não há redesign visual amplo nesta entrega.

## 3. Auditoria do estado real

Auditoria inicial histórica: leitura de código, planos e relatórios; consulta read-only da VPS em 2026-10-01. O estado operacional atual está na seção 65; a tabela abaixo preserva o diagnóstico inicial.
Não foi repetido teste de navegador, recuperação ou segurança nesta auditoria.

| Área | Evidência atual | Lacuna para entrega |
|---|---|---|
| Login/empresa/usuários, upload, fila, revisão, pacote | Implementados, com testes anteriores | Regressão e experiência integrada na imagem VH1 |
| Enriquecimento por fonte autorizada | Worker candidato e paridade local existentes | Provisionamento governado; fluxo na versão implantada |
| Validação externa | Broker/socket e wrappers candidatos qualificados em laboratório | Serviço supervisionado, registro/autoridades e conexão ao worker ativo |
| DOI real | Quatro comparações locais positivas | Runtime local difere do Linux fixado; repetir na base única |
| XML real restante | e20240086: 2 bloqueios/22 críticos/4 erros/11 avisos; e20240135: 3/10/4/7 localmente | Triagem contra regra/fonte e correção; contagens não equivalem a defeitos únicos |
| XPM | Atualização 2026-10-15: CLI original executada na VPS Linux; dois artigos e três negativos com relatórios reais | Regras legadas rejeitam SPS 1.10/JATS 1.3; consultas offline não concluídas; falta integração supervisionada |
| OpenClaw | Serviço existe e houve ensaios de laboratório | Flags API/worker falsas; ciclo automático da VH ainda não existe |
| UI | Formulários de pacote/revisão exigem IDs técnicos | Resolver associações e pendências sem comandos ocultos |
| VPS | API/worker na imagem `4fcf4766…`; banco/Redis ready | Melhorias recentes ainda não implantadas; campos opcionais de socket/enriquecimento ausentes ou não configurados na imagem ativa |
| Operação | Backup/restore/rollback históricos e limites em código | Provas atuais, na RC; não exigir operação de produção completa |

Atualização operacional de 2026-10-22 (substitui o estado antigo da linha VPS):
API/worker em `vh09-heads-20261021-v1`, banco `c0e1f2031425`, 324 arquivos de runtime
conferidos, backup/restore e rollback de imagem testados. Melhorias locais
allowlisted implantadas, sem habilitar agentes ou integração externa incompleta.
A linha Operação passa a ter prova atual **intermediária**, ainda não da RC final.
Detalhes e lacunas na seção 37; checkpoint anterior preservado na seção 36.

O XPM oficial documenta geração de pacote e relatórios por execução. A página não
comprova compatibilidade da distribuição registrada com SPS 1.10; essa dependência
não pode continuar apenas mencionada como “próximo passo”. Fonte conferida em
2026-10-01: [documentação XPM](https://documentacao.scielo.org/books/scielo-pc-programs/page/xml-package-maker-xpm).

## 4. Lista única — 20 itens, seis lotes

Legenda: `[~]` parcialmente existente, ainda sem aceite final; `[ ]` não entregue;
`[x]` somente após anexar evidência. Parcial não conta como concluído.
Responsável pelo desenvolvimento/testes: agente de desenvolvimento; responsável
pelas decisões/fontes/acesso externo: proprietário do projeto quando indicado.

| ID / lote | Estado | Entrega restante | Evidência que encerra o item | Dependências |
|---|---|---|---|---|
| VH-01 / 1 — Base | [x] | Base de desenvolvimento fixada: perfil 1.1, fonte/configuração, dois executores imutáveis e dependências reais | `vh1-lot1-baseline-v2.json` após scripts de download/armazenamento; v1 preservada. XMLs/ZIPs idênticos; imagem integrada final em VH-14/16 | Nenhuma |
| VH-02 / 1 — XPM | [~] | Compatibilidade DOI/SPS/DOCTYPE/JATS e erro residual resolvidos na política qualificada; broker supervisionado e worker implantados. Restam consultas/fontes de artigo e aceite integrado | Seções 48/52 e `vh10-worker-native-v1.json`: XPM real nos dois jobs, zero erros técnicos derivados, bruto preservado, avisos/consultas pendentes | 03/04/10/14; mesma VPS |
| VH-03 / 1 — Fontes | [x] | Contrato de autorização, instalador, destino/validade/revogação e fontes definidos; armazenamento privado autorizado e preparado | `source-authorization-1.0`, bundle 1.1, testes e `vh1-vps-source-staging-v1.json`: seis catálogos e dois snapshots privados; nenhum bundle ativo | Integração ao runtime por empresa/artigo em VH-04/14; consentimento de armazenamento recebido |
| VH-04 / 2 — Consultas | [x] | Adapters, broker e worker candidatos vinculam DOI/ORCID/fascículo/seção à empresa/artigo/XML/ZIP; desenvolvimento qualificado | `vh1-scoped-socket-v1.json`, `vh1-scoped-images-v1.json`, V10 e 938 testes: contrato real Linux, contraprovas, imagens e fontes verificadas. IDs de laboratório sintéticos; não é E2E implantado | 01,03; grants reais/serviço/ativação em 14/16, E2E em 18 |
| VH-05 / 2 — Metadados | [x] | Correções de título do periódico/editora concluídas no pipeline candidato por cadastro autorizado; restante do XML e ativos preservados | `vh1-journal-metadata-linux-v1.json` e `vh1-journal-xpm-compatibility-v1.json`: novos pacotes determinísticos, quatro validações modernas, igualdade cadastral no XPM e grants testados | 01,03; histórico preservado; implantação em 14/16 e aprovação integral ainda dependem de 02/07 |
| VH-06 / 2 — Conteúdo | [x] | Correções por fonte e auditoria das 87 referências concluídas na candidata; três tipos restantes classificados e 30 diferenças brutas triadas. Uma abstenção científica e dois localizadores bibliográficos seguem explícitos para o especialista; não é aceite científico | `vh1-reference-types-linux-v1.json`: 0 críticos/erros, 6/5 avisos por ferramenta. `vh1-reference-types-audit-v1.json` e `vh1-content-triage-v1.json` preservam achados brutos e adjudicações. 1.892 testes/89,20%; detalhes `VH1_REFERENCE_TYPES_AND_CONTENT_TRIAGE.md` | 01; implantação em 14/16 e aceite humano futuro preservados |
| VH-07 / 2 — XML final | [~] | Dois XMLs preservados; quatro execuções modernas sem erros/críticos e XPM sem erros técnicos derivados. Restam decisões de avisos/consultas e pacote final após ciclo | `vh10-worker-native-v1.json`: cinco avisos por ferramenta/artigo; XPM dois/três avisos. Nenhuma aprovação de publicação | 02,04,05,06,10/18 |
| VH-08 / 3 — Política IA | [x] | Contratos separados, três operações restritas a campos ausentes, evidência/grant/escopo, proteção humana e limites implementados; elegibilidade sem aplicação | `vh08-autocorrection-policy-v2.json`: política requalificada em 21/10 após alteração da revisão humana, 102 testes/100% dos dois módulos medidos e 11 de contrato; v1 preservada como histórica. Caminhos e fronteira de confiança em `VH08_AUTOCORRECTION_POLICY.md` | 01,03; executor/resolução de autoridades em 09, chamadas reais em 10/18 |
| VH-09 / 3 — Aplicação | [x] | Aplicação restrita, reversão e recuperação comprovadas com preservação do original e revalidação dos bytes resultantes | Seção 64 e `vh18-web-access-v1.json`: correção paga com quatro chamadas, retorno ao erro esperado e recuperação exata; os dois últimos comandos executados pelo portal ativo. Disponibilidade contínua do provedor permanece em VH-10/14 | 08,07,10/14 |
| VH-10 / 3 — Ciclo IA | [x] | Operador autoriza a recuperação de afiliação comprovada na revisão atual pelo portal. OpenClaw disponível no piloto | Seção 65 e `vh19-web-provider-v1.json`. Quatro chamadas reais, rascunho corrigido e revalidado, abstenção posterior com zero chamadas | 09,14 |
| VH-11 / 4 — Entrada | [x] | UI associa artigo, IDML, PDF, figuras e snapshot automaticamente/por seleção clara. Fila do scanner na seção 60 e seleção por nome, artigo e revisão comprovada na seção 62 | Fluxo de upload/processamento/pacote sem copiar IDs; erro de arquivo errado é identificável | 01 |
| VH-12 / 4 — Diagnóstico | [~] | Exibir estados formais, problemas agrupados e alterações automáticas | Usuário distingue falha de consulta, erro XML, pendência humana e aprovação; evidências/diffs legíveis | 04,10 |
| VH-13 / 4 — Revisão/saída | [x] | Downloads por revisão, histórico, diferenças e reversão/recuperação conferidos com operador e revisor | Seção 64: duas revalidações nativas concluídas, ZIPs idênticos às referências, comandos por nome e recusa HTTP 403 ao revisor para criar job; pacote inválido identificado como bloqueado | 09,12 |
| VH-14 / 5 — Operação candidata | [~] | Gateway dedicado e worker disponíveis para correções autorizadas pelo portal. Catálogos e fontes públicas por artigo em operação. Conferir retenção no fechamento da versão | Seções 64–65. Papel do emissor, IDML, PDF, revisão, escopo e vigência verificados. Backup privado e reversão de imagem exercitados | 02,03,10 |
| VH-15 / 5 — Recuperação | [x] | Backup, restauração, reversão de imagem e reaplicação comprovados na versão vh18-web-access-20261111-v1 | Seção 64: banco/artefatos e 179 arquivos privados restaurados, incluindo novas permissões, decisão do proprietário, catálogos e autoridades; hashes, proprietários e modos conferidos | 14 |
| VH-16 / 5 — Implantação | [~] | vh19-web-provider-20261114-v1 ativa, banco e2f314253647. Reversão/recuperação e permissões web comprovadas. Falta congelar a RC final | Seção 62. Ready/app 200, rota privada 401, 351 arquivos por runtime e rollback verificado | 07,10,11,12,13,14,15 |
| VH-17 / 6 — Regressão | [x] | Suíte integral Windows e Linux, segurança, robustez, capacidade e verificações do workflow aprovadas na candidata | Seção 63. Relatórios V-09 a V-12, ensaios nativos e contraprovas ligados ao código qualificado | 16 |
| VH-18 / 6 — Ponta a ponta | [~] | Dois originais percorreram navegador, API, fila, worker, avaliação, validadores e download na seção 61. Consolidar as contraprovas da RC final | Dois artigos de referência + contraprovas; sem atalhos de laboratório; auditoria/custos/reversão corretos | 17 |
| VH-19 / 6 — Entrega ao especialista | [~] | [Roteiro e modelo de apontamento](ROTEIRO_REVISOR_XML.md) conferidos com conta individual de ensaio. Falta identificar e convidar o destinatário após G-HOMOLOG | Pacote preparado e acesso testado; conta destinada ao especialista somente quando sua identidade for informada | 18; identidade é dependência externa |
| VH-20 / 6 — Fechamento | [ ] | Congelar VH1, decidir G-HOMOLOG e entregar | Checklist final assinado em registro, versão/URL/roteiro e defeitos não impeditivos; parar desenvolvimento pré-homologação | 01–19 |

Cada defeito descoberto dentro do escopo entra no item existente correspondente,
com responsável, causa, correção e teste. Não criar “fase seguinte” só para registrar
mais um ensaio da mesma integração. Os vinte itens não representam vinte dias,
nem porcentagem de conformidade ou estimativa de esforço equivalente.

## 5. Critérios de pronto — todos obrigatórios

- [x] Dois artigos de referência processados pelo fluxo implantado; texto e ativos
  preservados, sem informação inventada e com validações obrigatórias concluídas.
- [ ] Erros reais impeditivos resolvidos. Falso positivo/não aplicabilidade exige
  justificativa específica e teste; proibido rebaixar severidade genericamente.
- [ ] Os três tipos de correção IA qualificados nos caminhos explícitos de VH-08;
  ciclo positivo e negativo real. Casos fora da lista permanecem visíveis para humano.
- [ ] Sem perda/corrupção/exposição de dados, falha de isolamento, credencial em log
  ou contorno de release. Testar alterações maliciosas, evidence tampering e acesso
  cruzado; não depender somente da confiança do modelo.
- [ ] UI funciona sem intervenção técnica durante uso normal; falhas e retomadas
  são claras. Mesmo resultado com IA desligada não é anunciado como revisão IA.
- [ ] Restore/rollback, limites, uma execução por vez e saúde dos serviços comprovados.
- [ ] Regressão final e E2E passam; versão congelada, limitações/avisos registrados.
- [ ] Acesso individual e roteiro prontos; identidade do destinatário confirmada
  para o convite. Prontidão técnica pode ser declarada separadamente enquanto
  aguarda o nome, mas G-HOMOLOG/acesso entregue não são marcados indevidamente.

Cobertura não precisa subir indefinidamente: manter o piso exigido no projeto e
testar todos os caminhos críticos novos. Casos fora do escopo devem ser recusados
ou diagnosticados, não suportados à força para declarar a aplicação pronta.

## 6. Dependências que precisam aparecer cedo

1. **XPM**: VH-02 precisa terminar a investigação técnica já no lote 1. Se faltar
   distribuição compatível, ambiente/licença ou acesso externo, registrar exatamente
   o que falta e pedir decisão. Não portar/rebaixar perfil nem dispensar XPM
   silenciosamente. H1-A/UI podem avançar; o bloqueio de liberação continua visível.
   Em 2026-10-16, Linux e consultas restritas estão demonstrados; não solicitar
   Windows novamente. Restam compatibilidade SPS/JATS, Wayta e integração.
   Desenvolvimento das exceções pontuais autorizado em 16/10 (ADR-019/seção 29).
   Duas regras DOI, três SPS/data e aplicabilidade Wayta qualificadas até 19/10;
   restam DOCTYPE/JATS, erro residual, demais consultas e integração. Ver seção 32.
   VH-08 concluída no checkpoint 33, requalificada no 37; VH-09 parcial nos 34–37.
   Próximo: concluir compatibilidade/conexão VH-02/07, depois a promoção formal e
   revalidação da restauração VH-09. Não promover candidata enquanto a validação
   obrigatória estiver bloqueada, nem criar outra fase para essa dependência.
   Não aguardar nova autorização geral
   nem tratar a autorização como aprovação do XML ou implantação já realizada.
2. **Fontes e privacidade**: a autorização atual de corpus na VPS cobre derivados,
   não todos os catálogos. VH-03 deve resolver coleta local/remota ou pedir ampliação
   específica; não descobrir a dependência apenas na implantação.
3. **Dados editoriais ausentes**: quando a fonte não traz valor necessário, pedir
   o dado/decisão específica ao responsável. Repetir IA ou validadores não cria informação.
4. **Identidade do especialista**: usuário informa destinatário. Não impede desenvolvimento
   nem preparo da conta/roteiro; impede envio a uma pessoa não identificada.

Não há prazo honesto de conclusão antes de VH-01–03 quantificarem esses bloqueios.
Ao fechá-los, registrar estimativa por lote com premissas; atualizar só com causa concreta.

## 7. Fora da VH1 — não bloqueia por padrão

- Outros periódicos/templates, pacotes com múltiplos artigos/XMLs, traduções com
  múltiplos DOIs não qualificadas e conversão universal de qualquer IDML.
- Correção autônoma de texto científico, OCR/matemática, autoria, datas, ORCID,
  financiamento/licença ou decisões editoriais ambíguas; continuam em revisão.
- V-12–V-15 completos: carga prolongada, alta disponibilidade, escalabilidade,
  observabilidade avançada e automação completa de produção. Controles mínimos
  de segurança/recuperação/capacidade do piloto continuam obrigatórios.
- Remodelagem visual ampla, dashboards adicionais e otimizações sem impacto
  demonstrado no roteiro ou no envelope do piloto.
- Indexação/publicação automática, aprovação universal SciELO e aceite humano final.

Uma descoberta só bloqueia a VH1 se causar falha de segurança, perda/invenção de
conteúdo, validação obrigatória ausente/enganosa ou impedir uma função prometida.
Melhorias restantes vão para backlog pós-homologação, com ID, sem mudar a meta.

## 8. Disciplina de execução e teste

Executar lotes 1 → 2 → 3 → 4 → 5 → 6; VH-08/11 podem ser trabalhados enquanto
dependência externa de lote 2 aguarda resposta, mas sem promover versão incompleta.
Um checkpoint por item ou lote: entregue, evidência, pendência e próximo ID.

Testes durante desenvolvimento: focados no componente alterado. Suíte integral
ao integrar lote, alterar contrato compartilhado ou preparar RC. Reexecução real
somente se mudou candidato/ferramenta/configuração/evidência ou se fecha uma
contraprova antes ausente. Não repetir a mesma prova para gerar novo relatório.

Gates source-bound permanecem obrigatórios: quando invalidados por mudança,
reexecutar o escopo correspondente; não remover checagem nem atualizar hashes
sem teste. Histórico preservado, mas apenas o quadro desta entrega define o próximo ID.

Depois de VH-20: **encerrar o desenvolvimento pré-homologação e entregar ao especialista**.
Feedback passa a uma fila H5 separada; melhorias novas não reabrem indefinidamente VH1.

## 9. Evidências de partida

- `H1_REAL_DOI_LOCAL.md` e `h1-real-doi-summary-v1.json`: DOI real, limites de runtime.
- `H1_SPS_DOI_AUTHORITY.md`, `H1_DOI_SOCKET.md`: integrações candidatas e contraprovas.
- `H1_JOB_ENRICHMENT.md`: worker candidato e provisionamento ainda necessário.
- `H0_HOMOLOGATION_BASELINE.md`: lacunas UI/XPM/implantação identificadas.
- `AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`: desenho H1-A; VH-08–10/12/17–18 o executam.
- Código inspecionado: `routers/ui.py`, `routers/assistants.py`, `worker.py`,
  `services/package_validation.py`, `services/validator_transport.py`, `settings.py`,
  `release/policy.py`, registro de validadores e Compose de desenvolvimento.

Esta auditoria/planejamento não concluiu os vinte itens, não executou chamadas
IA nem alterou dados, flags ou serviços da VPS.

## 10. Execução — lote 1, 2026-10-01

**Dois itens entregues (VH-01/03); VH-02 bloqueado externamente. Lote 1 não encerrado
integralmente; G-HOMOLOG continua NÃO LIBERADO.** Não há nova fase ou extensão de escopo.

- Base única: `config/validator-registry-vh1.json` e
  `benchmarks/qualification/reports/vh1-lot1-baseline-v1.json`. Inventário real das
  duas imagens Linux, Python/dependências/regras/wrappers; fonte e perfil fixados.
  O pipeline local reproduziu duas vezes os mesmos XMLs/ZIPs reais, com as regras
  offline estáveis. Não foi reexecutada validação externa dos artigos neste lote.
- O aceite VH-01 fixa a base **do desenvolvimento**. Não antecipa o congelamento da
  imagem da aplicação integrada, que só existe após as alterações dos lotes 2–4
  e será inventariada em VH-14/16. A configuração ativa não foi promovida.
- VH-03 entrega controle e procedimento: grants privados vinculados à decisão do
  proprietário, destinos separados, expiração/revogação, escopo e instalação sem
  sobrescrita. Nenhum grant real criado nem catálogo enviado à VPS. Catálogos 1.0
  devem ser reprovisionados com autorização explícita; não há migração silenciosa.
- Verificação: **803 testes aprovados**, 3 avisos, cobertura **88,07%**; 75 testes
  direcionados incluídos nesse total, não adicionais. Ruff e tipagem dos módulos
  de autorização/enriquecimento aprovados. V10 reexecutado e novo relatório
  source-bound `v10-operational-workflow-vh1-lot1-v1.json`, preservando o anterior.
- Artefatos locais de teste: `tmp/vh1-lot1-final-tests.xml`,
  `tmp/vh1-lot1-coverage.json`, `tmp/vh1-lot1-workflow.xml`.

Decisões pendentes, sem autorização presumida:

1. **XPM:** solicitar ao proprietário distribuição/acesso oficial compatível ou
   orientação SciELO vigente, e definição do ambiente Windows. Não contatar terceiros
   em seu nome nem dispensar o gate sem decisão explícita registrada.
2. **Dados na VPS:** confirmar o armazenamento privado dos catálogos e autoridades
   somente dos dois ESA, fora de Git/imagens/logs, sem gold/holdout. Até confirmação,
   operação desses dados permanece local. Isso bloqueia sua instalação real, não
   invalida os controles de autorização entregues em VH-03.

Próximo ID de desenvolvimento independente: **VH-04**, contexto editorial/ORCID e
DOI no runtime fixado. A liberação final permanece dependente de VH-02. Não há
estimativa final de prazo enquanto a distribuição/automação XPM estiver indefinida.

### Atualização após autorização do proprietário — 2026-10-01

Substitui os dois pedidos de decisão acima; não solicitar novamente acesso XPM
ao proprietário nem consentimento de armazenamento já recebido.

- **Download resolvido:** XPM oficial baixado diretamente na VPS e checksum
  confirmado. A tentativa anterior falhou por erro nosso de decodificação da página
  (UTF-8/NBSP), não por comprovação de acesso externo indisponível. Parser corrigido
  e testes adicionados. Revisão mais recente listada nas pastas oficiais consultadas:
  15/12/2023. Compatibilidade 1.10 e execução isolada não estão aprovadas.
- **Autorização recebida:** decisão em `authorizations/VH1_VPS_DATA_20261001.md`.
  Seis catálogos, dois registros Crossref com manifestos, candidatos dos dois ESA e
  decisão armazenados privadamente na VPS (15 arquivos + manifesto; 2,86 MB de dados).
  Hashes/escopo/validade conferidos; root:root, diretórios 0700, arquivos 0600.
  Gold, holdout e IDML não enviados. Snapshot não ganha nova data de coleta ao copiar.
- **Sem ativação indevida:** arquivos em cofre administrativo, não montados no worker
  ativo; ainda falta provisionamento vinculado à empresa/artigo em VH-04/14.
- **Verificação:** 60 testes direcionados aprovados, Ruff e V10 aprovados. A suíte
  completa 803/88,07% do checkpoint anterior não foi reexecutada neste incremento.
  Novo manifesto base v2 reprocessou os dois artigos e preservou XMLs/ZIPs, perfil
  e imagens. API/worker sem troca de imagem; readiness de banco/Redis `ok`.

Lote 1 permanece com VH-02 parcial por execução/compatibilidade, **não por falta
de download ou de autorização dos dados**. Próximo passo técnico: avançar VH-04
com as fontes agora disponíveis; qualificação XPM continua visível em VH-02,
sem dispensá-lo silenciosamente ou anunciar o XML formalmente aprovado.

## 11. Execução — lote 2 / VH-04, 2026-10-01

Integração de evidências editoriais implementada e qualificada **nos validadores
nativos**, sem aprovação integral do XML ou implantação. Documento técnico:
`VH1_LOT2_EDITORIAL_AUTHORITIES.md`. Não foi criada nova fase.

- Dois artigos, duas ferramentas: DOI/fascículo/seção explicitamente aprovados.
  Quatro ORCIDs do e20240135 confirmados em cada ferramenta por registro público
  mais associação nome–ORCID do mesmo DOI no Crossref. Nomes públicos diferentes
  continuam registrados; isso não é autenticação da conta do autor.
- Contraprovas rejeitam volume/seção/nome alterados. Indisponibilidade volta a
  bloquear; nada foi dispensado para aprovar. XML/ZIP originais preservados.
- Restantes por ferramenta: e20240086, 22 críticos/4 erros/9 avisos;
  e20240135, 6 críticos/0 erros/5 avisos/4 informativos. Não são contagens de
  defeitos únicos entre ferramentas, nem comprovação de aprovação SciELO.
- 867 testes passaram na suíte completa, cobertura 88,07%; 12 testes adicionais
  do novo gate passaram depois, sem nova execução integral. Ruff, gate nativo
  source-bound VH-04 e V10 aprovados. API/worker/imagens/flags ativos preservados.
- Base atualizada em `vh1-lot2-baseline-v1.json`: mesmas imagens/perfil/XMLs/ZIPs,
  código novo inventariado; os manifestos anteriores não foram sobrescritos.
- Fontes autorizadas em diretório privado da VPS, fora de imagens/Git/logs.
  Cofre não é bundle operacional; a nova lógica foi montada apenas no ensaio.

Próximo passo permanece **VH-04**: adapters candidatos e transporte pelo broker,
com vínculo empresa/artigo/candidato, autorização e prova pelo contrato real.
Depois: VH-05 (metadados), VH-06 (conteúdo), VH-07 (validação integral).
VH-02/XPM permanece obrigatório e pendente de execução/compatibilidade.
**G-HOMOLOG continua NÃO LIBERADO.**

## 12. Encerramento do desenvolvimento VH-04 — 2026-10-03

Substitui o próximo passo do checkpoint anterior. **VH-04 concluído no escopo de
desenvolvimento/qualificação da integração candidata; próximo ID: VH-05.**
Ativação na empresa piloto e serviço supervisionado continuam explicitamente
em VH-14/16; não antecipam VH-18 nem encerram o lote 2.

- Autoridades por empresa/artigo/fonte/perfil/XML/ZIP; grant revogável e expirável,
  conferido antes/depois da validação; instalador atômico sem sobrescrita.
- Quatro execuções reais pelo socket Linux, fontes e imagens verificadas; negativos
  de escopo cruzado, XML alterado, revogação e expiração. As bibliotecas nativas
  permanecem idênticas à base anterior. Novas imagens contêm somente wrappers.
- **938 testes aprovados, 88,09% de cobertura**; 108 testes focados incluídos no
  total, V10 e gates VH-04 aprovados. Formatação global ainda aponta dois scripts
  históricos, registrados para VH-17; lint global e formatação do incremento passam.
- Nenhuma aprovação integral de XML: permanecem 22 críticos/4 erros no e20240086
  e seis críticos no e20240135 por ferramenta. XPM obrigatório ainda não executado.
- API/worker ativos preservados, readiness `ok`; sem ativação IA, sem grant real
  para empresa piloto. Dois IDs sintéticos usados somente no laboratório.

Detalhes, hashes, testes e limites: `VH1_SCOPED_VALIDATOR_INTEGRATION.md`.
Próxima implementação: **VH-05**, corrigir/classificar metadados com fontes e
aplicabilidade demonstradas, começando por afiliações e histórico editorial.
Depois VH-06/07; VH-02 permanece pendente e visível. Nenhuma nova fase aberta.

## 13. Execução VH-05 — 2026-10-05

**Avanço parcial, não encerramento de VH-05.** Correções determinísticas no mapper
e builder recuperam duas UFs explícitas no IDML e normalizam três papéis CRediT
já atribuídos. Guarda do XML completo permite somente essas mudanças; o segundo
artigo e os demais campos/arquivos permanecem intactos. Sem nova leitura de gold/holdout.

- Quatro execuções Linux, nas mesmas imagens fixadas: primeiro artigo passou de
  **22 críticos/4 erros para 14 críticos/3 erros**, nove avisos por ferramenta.
  Segundo artigo mantém seis críticos, zero erros, cinco avisos. Nenhum achado novo.
- Experimento de publicação somente com ano no histórico criou novos achados;
  foi retirado do código e da candidata. Relatório v1 preserva o experimento
  rejeitado; **v2 registra esse checkpoint**, sucedido pelo v3 da seção 14.
  Não inventar dia/mês para forçar aprovação.
- **981 testes aprovados, três avisos, cobertura 88,13%**. Os 73 focados e 12 testes
  do gate novo estão incluídos. Ruff/formatação do incremento, tipagem, V10, V11
  requalificado e gates de integração aprovados.
- API/worker ativos preservados; readiness banco/Redis `ok`. Sem ativação IA,
  troca de imagem da aplicação ou liberação de XML.

Detalhes e matriz finita de pendências: `VH1_METADATA_CORRECTIONS.md`.
**Próximo passo continua VH-05:** fonte e precisão de datas/histórico, decomposição
verificável do financiamento; estados/ORCID ausentes dependem de fontes vinculadas.
Os três erros restantes de vínculo de fórmulas pertencem a VH-06. XPM continua
em VH-02. Sem nova fase, waiver genérico ou aprovação integral/G-HOMOLOG.

## 14. Continuação VH-05 — precisão de datas e financiamento, 2026-10-05

Substitui o checkpoint anterior; detalhes em `VH1_METADATA_CORRECTIONS.md`.

- Preserva precisão ano/mês/dia na importação, rejeita conflitos/calendário inválido
  e impede redução de precisão. Data da referência formal tem evidência própria.
- Financiamento não é mais truncado na primeira vírgula. Pares explícitos de
  agência/auxílio são extraídos com evidência; prosa ambígua é preservada e
  marcada `needs_review`. Crossref desse artigo também contém segmentação
  inconsistente de instituição, portanto não é copiado cegamente.
- Quatro validações Linux: e20240086 **13 críticos/3 erros/9 avisos**; e20240135
  **6 críticos/0 erros/5 avisos**, sem achados novos. A retirada do grupo incompleto
  reduz uma ocorrência, mas **não resolve o financiamento**. Datas reais inalteradas.
- **1.042 testes/88,32%**; Ruff global/mypy passam. V10/V11 e gate do incremento
  passam, com novos relatórios v3. V09 está com evidência de `settings.py` antiga:
  requalificar em **VH-17**, sem alterar hashes para simular execução. Dois scripts
  históricos continuam fora do padrão de formatação; CI global não está verde.
- API/worker ativos preservados e readiness saudável. Sem ativação IA, implantação,
  aprovação integral ou liberação. Fontes ausentes/conflitantes permanecem na VH-05,
  três vínculos de fórmulas na VH-06; depois VH-07. XPM continua em VH-02.

## 15. Continuação VH-05 — datas ArticleMeta, 2026-10-06

Checkpoint histórico, sucedido pelo item 16 abaixo. Sem abertura de nova fase.

- Fonte oficial ArticleMeta, vinculada por PID/DOI e hash do IDML, confirma publicação
  em 2025-07-07, recebimento em 2024-09-06 e aceite em 2025-03-09. As duas últimas
  resolvem a convenção ambígua dia/mês deste IDML; não houve inversão global do parser.
- Catálogo de datas integrado ao conversor/worker candidato, com origem rastreável,
  autorização por empresa/artigo/destino, expiração e revisão humana ainda requerida.
  Não é uma nova permissão para IA alterar datas ou conteúdo científico.
- Quatro execuções nas imagens nativas fixadas: e20240086 de **13 para 8 críticos**,
  mantendo três erros/nove avisos; e20240135 permanece seis críticos/zero erros/cinco
  avisos e XML/ZIP idênticos. Sem achados novos, regras rebaixadas ou leitura do gold.
- **1.088 testes aprovados/88,41%**; gates de metadados/editoriais/scoped e V10/V11
  aprovados com evidências atuais. Ruff e mypy passam. V09 histórico desatualizado e
  dois scripts fora da formatação continuam em VH-17; CI global não está todo aprovado.
- Aplicação ativa preservada, readiness banco/Redis `ok`, sem ativação IA/implantação.
  Fontes e catálogo novos somente na área privada de qualificação.

**Próximo: ORCIDs ausentes do e20240086**, usando associação verificável do registro
editorial e consulta dos registros públicos. Qualificar catálogo e aceitação das
autoridades nos validadores; não apenas adicionar strings ao XML. Permanecem VH-05:
estados, vínculos de financiamento e datas de revisão/aplicabilidade. Depois VH-06
(três vínculos de fórmulas) e VH-07. VH-02/XPM e demais itens da lista seguem visíveis.
Provas, hashes, testes e limites: `VH1_METADATA_CORRECTIONS.md`. VH-05 continua parcial;
nenhuma aprovação integral do XML ou liberação para homologação.

## 16. Continuação VH-05 — ORCIDs verificados, 2026-10-06

Checkpoint histórico, sucedido pelo item 17; execução no mesmo lote, sem ampliação do escopo.

- Três ORCIDs ausentes do e20240086 recuperados da associação autor/obra no
  ArticleMeta e conferidos nos registros públicos ORCID. Nomes completos exatos,
  checksum válido, sem busca aproximada ou alteração de autoria. `authenticated=false`
  preservado: consistência de registro não é autenticação OAuth pelo autor.
- Catálogo novo integrado ao worker candidato, limitado a identificadores ausentes,
  com duas fontes por campo, hashes, escopo, validade/revogação e revisão humana.
  Identificadores já decididos, nomes ambíguos ou aplicação parcial são recusados.
- Quatro execuções nativas nas mesmas imagens: e20240086 de **8 para 5 críticos**,
  mantendo três erros/nove avisos. Os três ORCIDs explicitamente positivos nos dois
  validadores. Segundo artigo mantém seis críticos/zero erros/cinco avisos e hashes
  idênticos; nenhum achado novo. XML inteiro comparado, sem uso do gold como entrada.
- **1.139 testes aprovados/88,52%**, incluindo 250 focados e 39 do gate. Gates
  editorial/scoped/metadados e V10/V11 aprovados com provas atuais. Ruff global,
  formatação do incremento e mypy aprovados. V09/formatação históricos seguem VH-17.
- VPS preservada, API/worker na imagem anterior e readiness saudável. Fontes/catálogo
  somente no laboratório privado; sem implantação, ativação IA ou liberação formal.

**Próximo: estados/províncias das afiliações em VH-05**, com fonte institucional
autoritativa e correspondência ao artigo. Permanecem financiamento e datas de
revisão/aplicabilidade; depois VH-06 (três vínculos de fórmulas) e VH-07. XPM,
IA/UI/operação/E2E seguem os IDs existentes. Detalhes e hashes:
`VH1_METADATA_CORRECTIONS.md`. VH-05 parcial; G-HOMOLOG não liberado.

## 17. Continuação VH-05 — estados/províncias verificados, 2026-10-06

Checkpoint histórico, sucedido pelo item 18; mesma lista de vinte itens, sem abertura de fase.

- Cinco afiliações com estado ausente receberam somente esse campo: Tokyo no
  primeiro artigo e Tamil Nadu nas quatro instituições indianas do segundo.
  Seis fontes institucionais/governamentais verificadas, com endereço/unidade
  compatíveis. Região Kanto não foi usada como prefeitura; nenhum endereço,
  departamento, cidade, distrito, CEP ou texto científico foi reescrito.
- Catálogo administrativo novo integrado ao conversor/worker candidato, com
  regra de correspondência exata, hash do fragmento/página, DOI/IDML/perfil,
  autorização por empresa/artigo/destino e validade/revogação. Preenche apenas
  ausência sem decisão prévia, é idempotente e mantém revisão humana requerida.
  Não é geocodificação geral nem nova permissão autônoma de IA.
- Quatro execuções nativas nas imagens fixadas, comparação completa do XML e
  conversão/ZIP determinísticos. e20240086: **4 críticos/3 erros/9 avisos**;
  e20240135: **2 críticos/0 erros/5 avisos**. Redução de cinco ocorrências críticas
  de estado por ferramenta, sem achados novos e mantendo autoridades positivas.
- **1.190 testes/88,62%**, incluindo 165 focados e 50 testes do gate. Gates
  metadados/editorial/scoped e V10/V11 aprovados; novas provas imutáveis v3 destes
  últimos. Ruff global, formatação do incremento e mypy aprovados. V09/formatação
  históricos continuam em VH-17; não há aprovação global de CI.
- Fontes/catálogos/pacotes na área privada da VPS; aplicação ativa preservada,
  readiness saudável e temporários removidos. Sem implantação, ativação IA,
  aprovação integral de XML ou liberação para especialista.

**Próximo: financiamento e datas de revisão/aplicabilidade, ainda em VH-05.**
Restam duas ocorrências críticas de agência/auxílio no e20240086 e duas datas de
revisão em cada artigo. Não inventar datas, atribuir auxílios por proximidade nem
considerar ausência de informação prova de não aplicabilidade. Depois VH-06
(três vínculos de fórmulas) e VH-07. VH-02/XPM e IA/UI/operação/E2E mantêm seus
IDs existentes. Provas, fontes, hashes e limitações: `VH1_METADATA_CORRECTIONS.md`.

## 18. Continuação VH-05 — vínculo de financiamento, 2026-10-06

Checkpoint histórico, sucedido pela seção 19; dentro do mesmo lote 2 e da lista única VH-01–20.

- Auxílio já declarado no IDML e20240086 vinculado à Embrapa por publicação
  institucional, extraída e conferida visualmente. Somente o par comprovado foi
  estruturado; declaração, demais apoiadores e conteúdo científico preservados.
  Não se importou a segmentação incorreta do ministério no registro ArticleMeta
  nem contratos adicionais encontrados em outros trabalhos.
- Catálogo administrativo integrado ao conversor/worker candidato, com hash do
  PDF/IDML/registro, escopo, autorização, prazo/revogação e revisão humana futura.
  Preserva decisões anteriores, é idempotente e rejeita aplicação parcial ou alvo
  alterado. Não amplia a permissão de autocorreção IA para financiamento.
- Quatro execuções nativas nas mesmas imagens e comparação integral do XML:
  e20240086 **2 críticos/3 erros/9 avisos**; e20240135 **2 críticos/0 erros/5 avisos**,
  este último com arquivos idênticos ao v6. Duas ocorrências críticas de financiamento
  eliminadas, sem novos achados. Conversão/ZIP determinísticos, DTD válida, sem gold.
- **1.235 testes aprovados/88,69%**, incluindo 198 focados e 62 do gate. Gates
  editorial/scoped/metadados e V10/V11 passam; novas provas imutáveis v4 destes
  últimos. Ruff, formatação do incremento e mypy passam. V09/formatação históricos
  continuam VH-17; CI global não declarado aprovado.
- Fonte/pacotes somente na área privada da VPS; API/worker ativos preservados e
  readiness saudável. Sem implantação, ativação IA, aprovação integral/G-HOMOLOG.

**Próximo: datas de revisão/aplicabilidade, ainda na VH-05.** Os dois críticos em
cada artigo são `rev-request`/`rev-recd`, obrigatórios na configuração nativa fixada
inspecionada. Confrontar com fonte editorial e especificação 1.10; implementar
tratamento auditável com contraprovas. Ausência na fonte não equivale a evento não
aplicável, e a documentação antiga não autoriza alterar política 1.10. Não inventar
datas nem rebaixar regras para obter zero. Depois VH-06 (três vínculos de fórmulas)
e VH-07. XPM e IA/UI/operação/E2E mantêm os IDs existentes. Detalhes:
`VH1_METADATA_CORRECTIONS.md`. VH-05 parcial, G-HOMOLOG não liberado.

## 19. Encerramento técnico VH-05 — histórico SPS 1.10, 2026-10-07

Checkpoint histórico, sucedido pela seção 20. **VH-05 concluída no desenvolvimento candidato**, não implantada.

- A especificação 1.10 indicada pelo módulo nativo foi obtida e preservada por hash.
  A obrigatoriedade universal de datas de revisão na configuração diverge da lista
  normativa de datas obrigatórias. ADR-018 registra a correção específica, não uma
  dispensa editorial baseada em ausência de dados. Nenhuma data foi inventada.
- Camada própria de compatibilidade executa checks originais/efetivos, mantém
  auditoria e exige identidade de todas as demais regras. Recebimento, aceite,
  publicação, revisão informada inválida e severidades continuam verificados.
  Bibliotecas nativas intactas, imagens/registro candidatos separados e rollback.
- Quatro execuções completas nos XMLs/ZIPs exatos do v7, com grants/fontes ainda
  válidos: e20240086 **0 críticos/3 erros/9 avisos**; e20240135 **0 críticos/0 erros/5
  avisos**, por ferramenta. Nenhum outro achado mudou. Autoridades permanecem positivas.
- Treze contraprovas nativas por imagem, 62 testes locais novos e gate integrado
  ao CI. Fontes, imagens, pacotes, resultados originais e adulterações verificados.
  Regressão final: **1.297 testes aprovados/88,69%**, sem falhas/erros/skip;
  `tmp/vh1-history-final-tests.xml` e `tmp/vh1-history-final-coverage.json`.
  Gates metadados/editorial/scoped/histórico/V10/V11, Ruff global, formatação do
  incremento e mypy passam; V09/formatação históricos continuam em VH-17.
- VPS preservada: API/worker na imagem anterior, readiness/banco/Redis `ok`,
  1.051 MiB disponíveis/15 GiB em disco após ensaio, temporários removidos.
  Sem implantação, ativação IA, aprovação integral de XML ou G-HOMOLOG.

**Próximo: VH-06 — três vínculos de fórmulas do e20240086**, com destino único
comprovado, conteúdo preservado e testes negativos. Depois VH-07, revalidação
integral/classificação de avisos. XPM e IA/UI/operação/E2E continuam nos IDs
existentes. Requerimentos de revisão humana dos enriquecimentos não foram removidos.
Detalhes: `VH1_METADATA_CORRECTIONS.md`; registro candidato de validadores para
continuidade: `config/validator-registry-vh1-history.json` (não é registro implantado).

## 20. Continuação VH-06 — vínculos corrigidos, 2026-10-07

Checkpoint histórico, sucedido pela seção 21; mesmo lote 2, sem novos itens ou mudança do ponto de chegada.

- Resolvedor corrige o segundo número de pares literais de equações e a expressão
  introdutória de fórmula imediatamente seguinte, com destino único e contraprovas.
  Cinco vínculos acrescentados no e20240086; três eliminam os erros nativos.
- Reconversão dupla dos dois IDMLs; XML/ZIP determinísticos, DTD válida, PDF/imagens
  intactos. Fora dos cinco vínculos, XML integralmente preservado; e20240135 idêntico.
- Quatro execuções nativas na VPS: **e20240086 0 críticos/0 erros/9 avisos;
  e20240135 0 críticos/0 erros/5 avisos**, por ferramenta. Nenhum novo achado,
  autoridades positivas, política de histórico e imagens qualificadas preservadas.
- 90 testes novos e 136 focados aprovados; gate de evidência integrado ao CI e V10/V11
  reexecutados com relatórios novos. Regressão final: **1.387 testes/88,76%**,
  sem falhas/erros/skip; Ruff, mypy, formatação do incremento e gates passam.
  V09/formatação históricos continuam em VH-17, sem aprovação global do CI.
- **VH-06 permanece parcial**: a inspeção visual detectou divergência preexistente
  `g`/`a` na fórmula 15 do primeiro artigo. MathML não alterado nem aprovado nesta
  entrega. Concordância IA histórica e zero erros formais não provam fidelidade.
- Aplicação ativa preservada, sem implantação/ativação IA/liberação G-HOMOLOG.
  Evidências: `VH1_FORMULA_LINKS_AND_FIDELITY.md` e `vh1-formula-links-linux-v1.json`.

**Próximo: correção versionada da transcrição e auditoria de fidelidade, ainda em
VH-06**, preservando fonte, catálogo histórico, decisões e revisão humana futura;
fechar referências/seções/objetos, depois VH-07. Não inserir edição científica na
allowlist de autocorreção IA. XPM/IA/UI/operação/E2E continuam nos IDs existentes.

## 21. Continuação VH-06 — transcrições revisadas por fonte, 2026-10-08

Checkpoint histórico, sucedido pela seção 22; mesmo lote 2 e lista única VH-01–20.

- Conferência visual dos 60 registros de fórmulas contra PDFs autorizados: 14
  transcrições corrigidas (3 no e20240086, 11 no e20240135), 41 sem defeito
  confirmado nesta inspeção e 5 revisões de glifo/estilo pendentes. Inclui a
  divergência `g`/`a` da fórmula 15. Não equivale a aprovação científica integral.
- Contrato de catálogo 1.1 preserva 1.0, proposta/qualificação IA histórica,
  fonte, recorte e motivo da revisão. Mantém revisão humana, autorização e escopo;
  não amplia edição autônoma IA nem inventa uma nova qualificação por consenso.
- Reconversão dupla: DTD válida, XML/ZIP determinísticos, PDF/imagens intactos.
  Comparação integral aceita somente os 14 fragmentos MathML comprovados;
  texto, metadados, IDs e vínculos anteriores preservados. Sem gold na entrada.
- Fontes externas efetivamente recoletadas em 2026-10-08. Quatro execuções
  nativas na VPS: **e20240086 0 críticos/0 erros/9 avisos; e20240135 0/0/5**,
  por ferramenta. Todos os achados iguais aos anteriores, autoridades positivas,
  imagens/política de histórico fixadas. XPM e fidelidade integral não aprovados.
- 82 testes novos, 131 focados e V10/V11 reexecutados com provas imutáveis.
  Regressão completa: **1.469 testes/88,81%**, sem falhas/erros/skip. Ruff,
  formatação do incremento, mypy e gates passam. V09/formatação históricos
  continuam em VH-17; não há aprovação global de CI.
- Aplicação ativa preservada e readiness saudável; sem implantação, ativação IA,
  publicação ou G-HOMOLOG. Provas e limites: `VH1_FORMULA_SOURCE_REVISIONS.md`.

**Próximo na VH-06:** resolver cinco revisões de glifo/estilo do segundo artigo,
conferir símbolos dos dois algoritmos fora do MathML e fechar referências/seções/
objetos. Corrigir somente divergência demonstrável da fonte e registrar abstenções;
as cinco revisões não são cinco erros comprovados. Depois VH-07 consolida validação
integral e classificação de avisos. XPM/IA/UI/operação/E2E mantêm os IDs existentes.

## 22. Continuação VH-06 — glifos e auditoria de conteúdo, 2026-10-09

Checkpoint histórico, sucedido pela seção 23, consolidando ensaios de 2026-10-08; mesmo lote 2 e lista
VH-01–20. **VH-06 ainda parcial**, sem abertura de nova fase.

- Quatro fórmulas tiveram letras caligráficas corrigidas por evidência visual e
  fontes do PDF. Total acumulado: 18 transcrições corrigidas, preservando as
  versões, revisões anteriores e exigência de revisão humana.
- Corrigida a prioridade de `Position="Normal"` sobre nomes de estilo que indicam
  subscrito. Quatorze posições indevidas em algoritmos/texto foram normalizadas;
  índices legítimos, propriedades originais e caracteres científicos preservados.
- Uma dúvida de glifo permanece com abstenção explícita para o especialista: a
  extração do PDF é ambígua e falta o PDF de equação externo vinculado no IDML.
  Não inferir correção científica nem prolongar indefinidamente sua pesquisa.
- Prova integral permite somente quatro fragmentos MathML e 14 remoções de `sub`;
  demais nós XML/assets intactos. Primeiro artigo permanece byte a byte igual.
  Reconversão dupla, DTD válida e pacotes determinísticos.
- Quatro execuções nativas na VPS: **e20240086 0 críticos/0 erros/9 avisos;
  e20240135 0/0/5**, por ferramenta, sem alteração dos achados anteriores.
  Relatório imutável `vh1-glyphs-linux-v1.json` e gate integrado ao CI.
- Comparação posterior ao congelamento dos XMLs confirma contagens/estrutura de
  seções, referências, figuras, tabelas, notas e mídias. Não usa gold na conversão.
  Encontrado defeito real de segmentação bibliográfica sem volume; diferenças de
  chamadas do primeiro artigo incluem vínculos incoerentes no próprio gold.
  Exigem correção/adjudicação por fonte, não cópia automática da referência.
  Sete/23 achados brutos do comparador integral continuam visíveis para triagem;
  não equivalem a 30 novos defeitos nem foram aprovados automaticamente.
- **1.540 testes aprovados/88,81%**, sem falhas/erros/skip; 71 novos e 126 focados.
  V03 preserva 106/106 stories reais; V10/V11 reexecutados com novas evidências.
  Ruff global, mypy, formatação do incremento e gates atuais passam.
  V09/formatação históricos continuam em VH-17; CI global não aprovado.
- Aplicação ativa preservada, banco/Redis/readiness saudáveis; sem implantação,
  ativação IA, publicação ou G-HOMOLOG. Documentação técnica e limitações em
  `VH1_GLYPHS_AND_CONTENT_AUDIT.md`.

**Próximo na VH-06:** corrigir/testar os subcampos de referências sem volume,
adjudicar as diferenças bibliográficas e concluir a triagem de conteúdo usando as
provas já existentes. A abstenção científica segue explícita para o especialista.
Depois VH-07 consolida validadores aplicáveis e avisos. XPM/IA/UI/operação/E2E
permanecem nos mesmos IDs e critérios; zero formal não é liberação integral.

## 23. Continuação VH-06 — referências, 2026-10-09

Checkpoint histórico, sucedido pela seção 24; mesmo lote 2 e lista VH-01–20.

- Separação literal de autoria/título/fonte corrigida para referências sem volume:
  23 campos em 13 referências. Iniciais preservadas, páginas/datas de acesso fora
  do título/fonte; o texto integral das 87 referências é idêntico ao anterior.
- Reconversão dupla, DTD válida, XML/ZIP determinísticos; diferença integral permite
  apenas esses campos. Demais nós XML, xrefs, fórmulas, PDF/imagens e catálogos intactos.
- Quatro execuções nativas na VPS: **e20240086 0 críticos/0 erros/9 avisos;
  e20240135 0/0/6**. O aviso adicional identifica acesso ainda sem marcação própria,
  antes escondido na segmentação incorreta. Diagnóstico nativo antes/depois preservado;
  nada foi suprimido ou rebaixado para manter a contagem anterior.
- Seis diferenças bibliográficas conferidas com IDML: três destinos incoerentes
  com o ano no gold e três vínculos ausentes nele. Candidata preservada, adjudicação
  separada do comparador bruto; segundo artigo mantém 39/39 chamadas coincidentes.
- 95 testes novos, 150 focados aprovados; V03 mantém 106/106 stories e V10/V11 foram
  reexecutados. Provas históricas preservadas; evolução do mapper exige novo ensaio
  nativo fixado e diferença XML qualificada, não substituição de hashes antigos.
- Regressão final: **1.635 testes aprovados/88,99%**, sem falhas/erros/skip;
  resultado inicial com um gate histórico desatualizado preservado, ligação à
  requalificação corrigida e suíte integral repetida com sucesso. Ruff, mypy e
  formatação do incremento passam; isso não encerra o V09 histórico ou aprova CI global.
- Aplicação ativa preservada, sem implantação/IA/G-HOMOLOG. Detalhes, testes finais
  e limitações: `VH1_REFERENCE_FIELDS_AND_AUDIT.md`. V09/formatação históricos em VH-17.

**Próximo na VH-06:** marcar datas de acesso explícitas, corrigir tipos/campos de
livros/capítulos/tese/recurso online e conferir as 87 referências estruturadas.
Depois encerrar triagem dos sete/23 achados brutos com as provas existentes e
consolidar VH-07. Não é parser universal ou nova fase; dúvida científica de glifo
mantida para o especialista. XPM/IA/UI/operação/E2E conservam os IDs anteriores.

## 24. Continuação VH-06 — tipos e datas bibliográficas, 2026-10-13

Checkpoint histórico, sucedido pela seção 25; qualificação nativa em 09/10, consolidação em 13/10.
**VH-06 parcial**, sem nova fase ou ampliação do escopo.

- Quatro datas de acesso explícitas estruturadas; livros, dois capítulos e uma
  tese deixam de ser marcados como periódicos. Quinze referências ajustadas,
  com quatro edições e dois intervalos de páginas adicionais. Modelo canônico
  1.5.0 com migração que não inventa valores para snapshots antigos.
- SPS 1.10: capítulos em `part-title`, títulos de livro/tese em `source` e datas
  em `date-in-citation content-type="access-date"`. Fonte literal e evidência mantidas.
- Conferidas as 87 referências no IDML: texto integral, autores, ano, DOI e URLs
  preservados. Diferença XML permite somente as 15 citações estruturadas; todos
  os demais nós XML, assets, fórmulas e catálogos anteriores permanecem intactos.
- Três tipos ainda não resolvidos geram revisão explícita: e20240086 referências
  44/49 e e20240135 referência 31. URL não foi tomada como prova de tipo webpage.
  Presença literal dos campos não substitui validação de seu papel bibliográfico.
- Reconversão dupla, DTD válida e pacotes determinísticos; qualificação nativa
  final **e20240086 0 críticos/0 erros/6 avisos; e20240135 0/0/5**, por ferramenta.
  Quatro avisos de marcação resolvidos; nenhum novo, suprimido ou rebaixado.
- Gold usado só depois de congelar a candidata. Sete/23 achados integrais brutos
  e seis adjudicações de citações anteriores permanecem visíveis, sem aceite
  científico automático. Única abstenção de glifo continua para o especialista.
- 109 testes novos, 259 direcionados aprovados; regressão integral **1.744
  aprovados/89,10%**, sem falhas/erros/skip. V03 real 106/106 stories. V10/V11
  reexecutados com provas sucessoras imutáveis; somente V09 histórico falha na
  matriz 7C-08. Registros detalhados e regressão integral final em
  `VH1_REFERENCE_METADATA.md`. Gate nativo novo integrado ao CI, sem dispensas
  para fontes ou alteração dos relatórios antigos.
- Aplicação ativa/banco/Redis saudáveis e imagens inalteradas em 13/10. Sem
  deploy, ativação OpenClaw, mudança de hardware ou liberação G-HOMOLOG.

**Próximo delimitado na VH-06:** qualificar os três tipos restantes com fonte,
consolidar a triagem dos sete/23 achados usando as provas existentes e encaminhar
a única dúvida científica ao especialista no momento previsto. Depois VH-07.
V09/formatação históricos seguem VH-17; XPM/IA/UI/implantação/E2E mantêm seus IDs.

## 25. Conclusão de desenvolvimento VH-06 — 2026-10-14

**VH-06 concluída na candidata**, sem liberação G-HOMOLOG. Mesmo lote 2;
próximo item é VH-07, não uma fase adicional.

- Três tipos restantes qualificados com fontes institucionais e conferência visual
  do PDF técnico: uma página web e dois relatórios. Catálogo vinculado à citação,
  IDML, perfil, DOI e respostas; integrado ao worker com autorização, validade,
  revogação e isolamento. Não habilita classificação autônoma pela IA.
- Somente essas três citações estruturadas mudaram. Textos/autores/anos/DOI/URLs,
  demais nós XML, fórmulas, PDFs e imagens preservados. Schema 1.6.0 com migração
  sem inferência. Nos dois artigos, nenhum tipo `other` permanece; dois links
  continuam sinalizados e todas as decisões conservam revisão humana.
- Dois pacotes determinísticos, DTD válida e quatro execuções nativas na VPS:
  **e20240086 0 críticos/0 erros/6 avisos; e20240135 0/0/5**, por ferramenta.
  Achados idênticos aos anteriores, sem supressão ou rebaixamento.
- Triagem cobre as 30 diferenças brutas: duas de grafia/fronteira textual,
  27 ocorrências de fórmulas ligadas às revisões históricas por fonte e uma
  abstenção científica de glifo. Não são 30 defeitos novos nem 28 fórmulas
  automaticamente equivalentes. Comparador bruto continua `passed=false`,
  com sete/23 achados visíveis; aprovação científica permanece falsa.
- **148 testes novos, 407 direcionados e 1.892 na regressão integral aprovados;
  cobertura 89,20%**, sem falhas/erros/skip. V03 real 106/106 stories, V10/V11
  requalificados, Ruff/mypy/formatação do incremento e gates VH passam.
  V09/formatação históricos continuam em VH-17; CI global ainda não aprovado.
- Aplicação ativa, imagens e hardware preservados; readiness/banco/Redis saudáveis.
  Sem deploy, ativação de bundles/OpenClaw, chamadas IA ou publicação.

Evidências, fontes, hashes, limitações e testes:
`VH1_REFERENCE_TYPES_AND_CONTENT_TRIAGE.md`.

**Próximo: VH-07**, consolidar regras/consultas e classificar os avisos dos dois
pacotes exatos. **VH-02/XPM** segue dependência não resolvida: qualificar execução
e compatibilidade, sem tomar Packtools/SPS como substitutos. IA/UI/operação/E2E
prosseguem nos IDs já aprovados. Abstenção e limites editoriais serão apresentados
ao especialista na entrega; não reabrir pesquisa indefinida do glifo.

## 26. Continuação VH-07 — validação final e avisos, 2026-10-14

Consolidação e triagem implementadas, **VH-07 ainda parcial por XPM**. A análise
dos avisos encontrou uma afiliação com duas subdivisões juntas. O builder foi
corrigido por divisão literal com evidência comum; canônicos, fórmulas, referências,
demais nós XML e anexos preservados. O segundo artigo não mudou.

`vh1-final-validation-linux-v2.json` prova **0 críticos/0 erros/5 avisos nos dois
artigos por ferramenta**, com consultas DOI/fascículo/seção/ORCID completas na
execução, DTD e pacotes exatos. `vh1-final-warnings-v2.json` classifica todas as
ocorrências: seis afiliações de uma subdivisão, dois apêndices opcionais ausentes
e duas seções compostas por subseções. Sem criar conteúdo, suprimir severidade
ou dar aceite automático. A abstenção científica e dois localizadores continuam
para revisão final. Detalhes e hashes: `VH1_FINAL_VALIDATION_AND_WARNINGS.md`.

103 testes novos; 936 aprovações na regressão direcionada e reexecução dos 103
após endurecer o gate (contagens sobrepostas); V10/V11 atuais no relatório
técnico. Sem alegar nova suíte integral/cobertura a partir de teste
focado. VPS preservada, sem implantação ou OpenClaw ativado; G-HOMOLOG fechado.

**VH-02:** o ZIP oficial está na VPS e foi conferido localmente. Pré-verificação
Windows registra Tkinter presente, dependências XPM ausentes no intérprete
consultado e nenhum executor dedicado. Não foi executado XPM; compatibilidade
SPS 1.10 não comprovada. Antes de provisionar conta/serviço, definir host Windows
dedicado ou autorizar ambiente isolado neste computador. Não contratar servidor,
portar ferramenta, modificar perfil ou dispensar requisito silenciosamente.

**Próximo passo:** decisão de ambiente em VH-02 e qualificação real XPM; enquanto
depender dessa decisão externa, avançar **VH-08** conforme a exceção já aprovada
nas seções 6/8. Não iniciar nova fase nem repetir validação dos mesmos avisos.

## 27. VH-02 — execução XPM na mesma VPS comprovada, 2026-10-15

Este checkpoint substitui a necessidade de decisão Windows do anterior.
Proprietário autorizou instalações e determinou manter tudo na VPS atual.
ADR-002 revisada: executor Linux isolado; usuário continua exclusivamente web.
Sem código XPM modificado, desktop virtual, Wine ou hardware novo.

`vh1-xpm-linux-v1.json` registra cinco relatórios reais: dois artigos processados
e três negativos detectados (periódico sem título, imagem ausente, XML truncado).
49 testes locais direcionados aprovados; 25 serviços preservados e readiness ok.
Nenhum deploy/ativação IA. Pacotes de entrada e código oficial mantiveram hashes.
Detalhes: `VH1_XPM_LINUX_QUALIFICATION.md`.

**Não é aprovação XML:** ambos os artigos têm 3 bloqueios/4 fatais/4 erros no XPM
legado offline; seis/oito avisos. Regras SPS 1.10 e DTD JATS 1.3 não são suportadas
corretamente pela distribuição; consultas externas foram desativadas apenas no
ensaio e não contam como concluídas. XML reempacotado tem hash diferente e não foi
promovido. Não há um caso positivo de aprovação integral nesta prova de execução.

**Próximo trabalho: VH-02**, compatibilidade específica e autoridades/consultas,
sem rebaixar o XML ou dispensar ferramenta. Se exigir mudança da política formal,
apresentar evidências e solicitar decisão. VH-08 continua independente; serviço
supervisionado em VH-14/16. Os vinte IDs e G-HOMOLOG permanecem inalterados.

## 28. VH-02 — consultas restritas e diagnóstico cadastral, 2026-10-16

Implementados proxy isolado, runner online e auditoria de evidências; três novas
execuções finais na mesma VPS, sem modificar o XPM. Catálogo oficial carregado
por HTTPS, conexões Crossref/ORCID e contraprovas de rede verificadas. Dez consultas
Wayta foram recusadas; conjunto externo não é declarado completo. XML continua
bloqueado, independentemente de exit code zero ou conectividade.

`vh1-xpm-online-v1.json` preserva totais: e86 **3 bloqueios/2 fatais/5 erros/2 avisos**;
e135 **3/1/5/3**. Controle de imagem ausente detectado. **111 testes direcionados
aprovados**, Ruff/formatação do incremento e gates históricos de validação/avisos
passam; sem nova suíte integral/cobertura. 25 serviços preservados, sem deploy,
ativação IA, upgrade ou mudança de política formal.

**VH-05 reaberta de forma delimitada:** catálogo revela título do periódico
divergente em e86 e nome da editora divergente nos dois. Ainda não corrigidos nos
candidatos. Próximo desenvolvimento: representar esses dois campos por cadastro
versionado/proveniência, sem tocar DOI/título do artigo ou reabrir conteúdo científico;
revalidar os novos pacotes em VH-07. Evidências anteriores não são apagadas.

VH-02 também identificou regra DOI que produz erro mesmo com correspondência
exata e incompatibilidades SPS/JATS. Proposta pendente: exceções pontuais, com
fonte/versão/contraprova e validação independente, preservando relatório original;
sem dispensar consulta falha, erro real ou aprovação SciELO. **Precisa de decisão
explícita antes de alterar efeito sobre aprovação.** Alternativa: aguardar
distribuição/orientação compatível. VH-08 pode avançar independentemente.
Detalhes, fontes e procedimento: `VH1_XPM_ONLINE_AND_COMPATIBILITY.md`.

## 29. Autorização de compatibilidade e sequência até testes — 2026-10-16

Proprietário autorizou explicitamente implementar a política proposta. ADR-019
registra limites e aceite. **Autorizada; primeiro incremento executado na seção 30,
ainda sem ativação.** Esta
decisão substitui a pendência da seção 28, preservando seu histórico. Não autoriza
publicação nem dispensa erros reais ou consultas obrigatórias.

As cinco entregas abaixo agrupam itens existentes; não são cinco fases novas:

| Ordem | Itens existentes | Entrega necessária | Critério de término |
|---|---|---|---|
| 1 — XML e compatibilidade | VH-02/05/07 | Corrigir título do periódico/editora por cadastro; implementar regras pontuais XPM; concluir consultas necessárias; revalidar pacotes exatos | Erros reais impeditivos corrigidos, validações obrigatórias concluídas, exceções justificadas e contraprovas aprovadas; homologação separada de publicação |
| 2 — Correção automática segura | VH-08–10 | Lista fechada de operações, executor reversível e ciclo OpenClaw integrado | Elegíveis corrigidos/revalidados; inseguros recusados; até dois ciclos, limites de custo/tempo, auditoria e modo sem IA |
| 3 — Uso inteiramente web | VH-11–13 | Associação arquivos/artigo, progresso, diagnóstico, diferenças, revisão/reversão e downloads | Fluxo sem IDs copiados ou terminal; usuário distingue aprovado, pendente, erro e exceção de compatibilidade |
| 4 — Candidata na VPS atual | VH-14–16 | Validadores/worker supervisionados, configuração por empresa, backup/restore/rollback e implantação | Versão identificada, serviços saudáveis, limites e rollback comprovados; outro sistema preservado |
| 5 — Aceite técnico e entrega | VH-17–20 | Regressão/segurança, testes ponta a ponta, roteiro e acesso individual | Dois artigos e contraprovas pelo fluxo real, modos com/sem IA verificados, checklist G-HOMOLOG fechado e versão congelada |

Próximo incremento: **entrega 1**, começando pelas correções cadastrais e pelo
contrato de compatibilidade; depois prova dos pacotes resultantes. Não acrescentar
repetição de pesquisas/spikes sem mudança ou contraprova faltante. Se uma regra
específica depender de orientação externa, registrar sem dispensar e avançar nos
itens independentes VH-08/11 conforme seção 8.

Ponto de parada: após a entrega 5, liberar o piloto ao especialista, sem iniciar
melhorias opcionais antes da avaliação. Novos periódicos/templates, redesign,
escala/alta disponibilidade e expansões continuam pós-homologação. Pendências
editoriais declaradas, como a abstenção científica já registrada, continuam
visíveis; não exigir que IA invente uma resolução. Identidade do especialista
necessária para entregar acesso, não para continuar o desenvolvimento.
O registro de planejamento desta seção não executou código/testes nem alterou a VPS.

## 30. Entrega 1 — cadastro corrigido e primeiras regras XPM, 2026-10-16

**VH-05 concluída na candidata; VH-02/07 continuam parciais.** Título do periódico
e editora corrigidos por catálogo oficial, com grants, proveniência, isolamento,
conflito e idempotência. Novo contrato de compatibilidade reconhece somente dois
falsos positivos DOI de correspondência exata; não altera o relatório bruto ou
a Release Policy. Ainda não integrado à UI/serviço supervisionado.

Dois artigos reconstruídos, sem mudar os demais nós XML, PDFs ou figuras.
Packtools/SPSValidator na VPS: quatro execuções, zero críticos/erros e cinco
avisos por ferramenta/artigo. XPM: três execuções, incluindo imagem ausente
corretamente bloqueada. Contraprova adicional: oito casos nos métodos DOI originais.
25 serviços preservados; nenhuma implantação da aplicação ou ativação IA.

Provas: `vh1-journal-metadata-linux-v1.json`,
`vh1-journal-xpm-compatibility-v1.json` e `vh1-xpm-doi-comparisons-v1.json`.
170 testes direcionados aprovados; V10/V11 reexecutados (`*-journal-metadata-v2`),
novos gates no CI. Cache limitado e vinculado aos bytes evita avaliações repetidas
da cadeia histórica; troca de fonte/relatório invalida o resultado em testes.
Detalhes, hashes, limites e comandos em `VH1_JOURNAL_METADATA_AND_XPM_COMPATIBILITY.md`.

**Fechamento da regressão, conferido em 2026-10-17:** suíte integral concluída em
2026-10-16, com **2.166 testes aprovados, zero falhas/erros/skip, cinco avisos e
89,33% de cobertura de linhas**. Duração local: 17min02s. Evidências:
`tmp/vh1-journal-final-tests.xml` e `tmp/vh1-journal-final-coverage.json`.
Ruff global, tipagem de 114 módulos e formatação dos 20 arquivos do incremento
aprovados. Não equivale a CI global aprovado: V09 e dois scripts históricos ainda
pendem; verificar também o limite de 15 minutos do job no runner real em VH-17,
sem presumir que Windows local e Linux CI têm o mesmo desempenho.

**Próximo incremento:** regras legadas SPS/pub-date e análise específica
DOCTYPE/JATS, seguidas da consulta Wayta e revalidação. Não reabrir cadastro ou
conteúdo científico; não dispensar fatal/consulta falha. Se houver dependência
externa demonstrada, continuar VH-08/11 independentes conforme sequência aprovada.
As entregas 2–5 e o ponto de parada da seção 29 permanecem inalterados.

## 31. Entrega 1 — SPS/data qualificados, 2026-10-17

Implementadas três regras adicionais da ADR-019, sobre a avaliação DOI intacta.
Contraprova na VPS confirmou interpretação de 1.10 como decimal 1.1 no XPM legado
e tabela que termina em 1.9. Dez casos nativos; vendor intacto, sem rede ou mudança
de aplicação. Calendário/ISO/precisão/tipos, escopo e duas validações independentes
são exigidos pela aplicação; não há modificação de datas ou XML.

Nos mesmos dois pacotes atestados da seção 30, quatro ocorrências adicionais por
artigo foram classificadas (um erro de versão e três bloqueios de datas). Contagens
XPM originais mantidas em **3 bloqueios/1 fatal/4 erros**; derivado após DOI+SPS/data:
**0 bloqueios/1 fatal/1 erro**, com 2/3 avisos e consultas pendentes. Sem aprovação
integral. Não houve reexecução integral dos validadores para bytes inalterados.

Prova ativa `vh1-sps-compatibility-v2.json`, probe `vh1-xpm-sps-dates-probe-v1.json`.
**136 testes direcionados aprovados**, Ruff global, tipagem dos 115 módulos,
formatação do incremento e gates V10/V11/nativo/SPS aprovados. Sem nova suíte
integral/cobertura ou CI global aprovado; VH-17 preservado. Detalhes, hashes e
comandos: `VH1_SPS_DATE_COMPATIBILITY.md`.

Análise específica de DOCTYPE: a ressalva oficial consultada não foi resolvida
pela tarefa técnica SPS/JATS; fatal não dispensado, candidato não rebaixado.
Wayta resolveu DNS, mas uma tentativa HTTPS da VPS expirou sem resposta HTTP;
registrada como indisponibilidade, não sucesso nem prova de encerramento do serviço.

**Próximo incremento:** tratamento verificável da consulta Wayta indisponível e
sua necessidade normativa. Dependência externa de DOCTYPE/JATS/validador permanece
explícita; se persistir, avançar VH-08/11 independentes, conforme seção 8, em vez de
repetir pesquisas sem contraprova nova. Integração do avaliador supervisionado/web
ainda pendente. Mantidas as cinco entregas e o ponto de parada da seção 29.

## 32. Entrega 1 — aplicabilidade Wayta qualificada, 2026-10-19

Implementado contrato de avaliação que distingue consulta auxiliar de validação
obrigatória de afiliação. Base: especificação SPS arquivada, comportamento original
do XPM e validações independentes dos pacotes exatos. **Inferência delimitada ao
perfil ESA 1.1 qualificado**, não dispensa oficial geral nem nova exceção sobre erros.
Não aceita `normalized` legado, país ausente/divergente, instituição incompleta,
IDs ambíguos ou vínculo de autor sem destino. Outros perfis ficam indeterminados.

Na VPS, cinco respostas sintéticas de consulta e dezoito combinações de afiliação
foram executadas no código original, sem rede, alteração do vendor ou aplicação.
A normalização Wayta está desativada no verificador original; vazio, JSON inválido
e timeout retornam a mesma lista vazia. Descoberta adicional: esse verificador não
detecta país ausente. O novo controle recusa essa lacuna, sem copiar o comportamento
inseguro. Uma tentativa HTTPS sem dados de artigo expirou em 8,017 s; não prova
encerramento do serviço, consulta concluída ou identidade institucional verificada.

Prova ativa: `vh1-wayta-requirements-v1.json`, com probe nativo final
`vh1-wayta-native-v3.json` e observação `vh1-wayta-service-v1.json`.
As versões nativas v1/v2 são intermediárias, preservadas, não execuções de artigos.
Dois candidatos reavaliados; **nenhum XML/ZIP alterado, nenhum erro adicional
dispensado**: continuam 0 bloqueios/1 fatal/1 erro no derivado, 2/3 avisos, demais
consultas e integração pendentes. Contagens brutas 3/1/4 intactas; sem prontidão.

**229 testes direcionados aprovados**, incluindo 93 novos; Ruff global, tipagem
dos 116 módulos e formatação dos oito arquivos do incremento aprovados. Gate
Wayta verifica a cadeia nativa e foi adicionado ao CI. JUnit:
`tmp/vh1-wayta-focused.xml`. Sem nova suíte integral/cobertura ou CI global aprovado.
Gates V10/V11 também passaram. Pós-checagem: 25 containers em execução, serviços
IDML saudáveis, sem restart/deploy ou alteração dos serviços do outro projeto.
Detalhes e reprodução: `VH1_WAYTA_QUERY_REQUIREMENTS.md`.

**Próximo item de desenvolvimento: VH-08**, contrato versionado e lista fechada
das operações automáticas, com testes positivos/negativos e negação por padrão.
Depois VH-09/10, seguindo a entrega 2 já aprovada. DOCTYPE/JATS, erro residual e
demais consultas permanecem em VH-02/07; não repetir pesquisa de Wayta nem bloquear
desenvolvimento independente por essa dependência externa. Integração de resultados
e diagnóstico web em VH-12/14; ainda sem deploy, IA ativa ou G-HOMOLOG. Mantidas
as cinco entregas e o ponto de parada da seção 29.

## 33. Entrega 2 — VH-08 concluída, política automática fechada, 2026-10-19

Implementados contratos `autocorrection-intent/decision/event-1.0` e política
`vh1-autocorrection-1.0`, separados dos contratos assistivos. Três operações:
preencher código de país pelo mapa exato ESA 1.1; recuperar asset de figura com
destino único e hash; recuperar literalmente texto original de afiliação do IDML.
Somente campos ausentes; valor existente/divergente, ambiguidade, origem humana,
decisão histórica, fórmula/texto científico e qualquer operação não enumerada
continuam proibidos. Caminhos e valores resolvidos pelo servidor, não pela IA.

Empresa/artigo/snapshot/revisão/perfil, achado, origem e conteúdo da evidência,
grant vigente e before hash são obrigatórios. Lote de operações é todo elegível
ou todo recusado/abstido. Há contrato de evento sem texto privado, proteção de
caminhos humanos e limites finitos de ciclos/tempo/tokens/custo/concorrência.
São verificações de elegibilidade; persistência/reservas/locks e extração de
evidência confiável pertencem ao executor, não são simuladas como implantadas.

**102 testes da política aprovados**, cobertura de linhas/ramificações dos dois
módulos novos em 100% (não do sistema inteiro), e **223 testes na regressão
direcionada**, incluindo 113 novos e preservação dos contratos/revisões históricos.
Ruff global, tipagem de 118 módulos, exports e cadeia Wayta/DOI/SPS aprovados.
Prova `vh08-autocorrection-policy-v1.json`; detalhes em `VH08_AUTOCORRECTION_POLICY.md`.
Sem suíte integral nova, avaliação real por IA, alteração de XML, deploy ou G-HOMOLOG.

**Próximo item: VH-09**, executor transacional, idempotente e reversível. Resolver
grants/bytes/extratos no servidor, conferir novamente estado humano e política
dentro da transação, gerar candidata sem sobrescrever origem, persistir trilha
append-only e revalidar os novos hashes antes de promoção. Testar repetição,
concorrência, interrupção, revogação e regressão de conteúdo. Depois VH-10 conecta
os agentes e prova os ciclos reais; nenhuma flag atual deve ser ativada como atalho.
VH-02/07 e entregas web/VPS/E2E permanecem no quadro, sem nova fase ou expansão.

## 34. Entrega 2 — VH-09 parcial, candidatas isoladas, 2026-10-19

Implementada a primeira parte do executor: resolve IDML/assets nos registros da
empresa, confere bytes/hash e scanner, extrai literalmente texto/link por locator
e consulta grants persistidos/revogações. Não aceita prova ou valor substituto da
IA. Evidência legada sem hash/locator suficientemente preciso é recusada, não
completada por suposição. Grants de extração têm escopo/validade e provisão interna;
integração do produtor de evidências/autorizações da ingestão ainda precisa terminar.

A transação reavalia VH-08 e estado humano atual/histórico, confere versão/snapshot,
cria cópia canônica privada, aplica somente os campos preparados, reconstrói XML e
executa validação offline sobre o novo hash. Recibos sem texto privado, deduplicação
por intenção e histórico preservado. Descarte acrescenta registro, não apaga bytes.
Nenhuma candidata entra em `DomainSnapshot`: as telas existentes selecionam a maior
revisão, portanto guardar ali uma versão não validada mudaria indevidamente a revisão.

Migração `a8c9d0e1f203` preparada para quatro tabelas com proteção append-only no
ORM e no banco. SQLite: upgrade/downgrade/reupgrade, rollback externo, interrupção
e duas sessões concorrentes testados. Corrigido BEGIN ausente no modo legado do
SQLite antes de savepoint. PostgreSQL: DDL compilada, **execução nativa ainda não
qualificada**. Não houve alteração do banco/VPS, endpoint novo ou chamada de IA.

**85 testes novos e 312 na regressão direcionada aprovados**, zero falhas/erros/skip.
Cobertura apenas dos três módulos novos: **95,16% de linhas, 83,33% de ramificações**
(92,49% combinada); não é cobertura do sistema. Ruff global, mypy de 121 módulos,
formatação do incremento e prova VH-08 aprovados. Registro local:
`benchmarks/qualification/reports/vh09-staging-local-v1.json`; JUnit/coverage em
`tmp/vh09-staging-*` e `tmp/vh09-focused-regression.xml`. Sem nova suíte integral
ou declaração de CI global aprovado. Detalhes: `VH09_AUTOCORRECTION_STAGING.md`.

**Próximo passo, ainda VH-09:** integrar evidências de campo e grants ao fluxo
autorizado; reconstruir pacote e revalidar os hashes nos verificadores aplicáveis;
implementar promoção/restauração com nova checagem de estado humano, grants,
concorrência e invariantes XML, qualificando a migração/transação no PostgreSQL
isolado. Descarte de staging não é rollback de versão promovida. Runtime/achados
continuam dependências internas confiáveis, não dados aceitos da IA. Reservas
distribuídas, ciclos e chamadas reais continuam em VH-10. VH-09 não foi encerrada;
flags inativas e pendências XPM/G-HOMOLOG mantidas, sem ampliar a lista de entregas.

## 35. Entrega 2 — VH-09, evidências e pacote privado, 2026-10-20

Implementados os dois trechos seguintes do item existente, sem criar nova fase:

1. Produtor opt-in de evidências exatas sobre o resultado da ingestão, mantendo
   todos os valores e o XML; suporte aos seletores virtuais do parser. Catálogo
   determinístico por fonte/canônico/perfil, com abstenção por ambiguidade.
2. Autorização administrativa de lote, provisionada no servidor, derivando grants
   limitados aos campos do catálogo. Releitura da autorização-mãe antes/depois
   do staging e da revalidação; remoção, revogação ou alteração bloqueia o uso.
3. Reconstrução privada do ZIP com PDF/imagens verificados, vínculos exatos e
   invariantes XML. Validação offline nova e despacho dos novos hashes aos
   executores externos confiáveis; rechecagem de estado humano, fonte, grants,
   descarte e relógio depois da validação. Nenhum valor final vem da IA.

O worker não foi ativado nem alterado; não foram reescritos snapshots históricos.
O serviço de pacote devolve dados privados e recibo vinculado, **ainda sem
persistência do resultado ou promoção**. PDF selecionado por ID/hash confiável:
integridade de bytes não é prova de correspondência científica com o artigo.
XPM permanece indisponível nesse caminho de orquestração e não há aprovação
formal, mesmo quando os dois executores sintéticos externos respondem positivamente.

Verificação: **82 testes novos, 167 VH-09 e 421 direcionados aprovados** (conjuntos
sobrepostos), zero falhas/erros/skip. Seis módulos VH-09: 94,30% de linhas e 83,58%
de ramificações, não cobertura global. Ruff global, mypy 124 módulos, formatação
do incremento e prova VH-08 aprovados. Registro:
`benchmarks/qualification/reports/vh09-integration-local-v1.json`; detalhes e
limites em `VH09_AUTOCORRECTION_STAGING.md`. Não houve deploy, chamada paga,
execução externa real, nova suíte completa ou declaração de CI global aprovado.

**Próximo passo delimitado, ainda VH-09:** persistir revalidação/histórico e ligar
promoção/restauração à cabeça canônica sem expor versões não validadas à revisão
humana existente; comprovar transação/concorrência e migração em PostgreSQL isolado.
Integrar as validações aplicáveis (XPM em VH-02/07) antes de autorizar promoção.
Depois conectar worker/ciclos reais em VH-10. Permanecem as mesmas entregas web,
VPS e E2E do quadro, sem nova fase ou expansão da allowlist.

## 36. VH-09 — Persistência, PostgreSQL e atualização da VPS, 2026-10-20

Entrega concreta: a reconstrução/revalidação passa a gerar um registro privado
persistente, ligado à tentativa, XML/ZIP, manifesto e relatórios por hashes.
Repetir a mesma requisição recupera o histórico sem duplicar artefatos; mudar
seus parâmetros é conflito. Nova requisição revalida novamente. Falha durante
a gravação não deixa registro parcial. As mesmas regras de quotas/empresa e
armazenamento endereçado por conteúdo da aplicação continuam valendo.

Migração aditiva `b9d0e1f20314` acrescenta a quinta tabela append-only.
PostgreSQL nativo comprovou migração, triggers, duas sessões concorrentes com
um único registro e rollback externo, em banco descartável, separado do ativo.
Os 16 testes novos integram 73 direcionados locais; 199 testes passaram em Linux
na VPS. Suíte completa encerrada em 20/10, resultado recuperado em 21/10:
2.631 aprovados, zero falhas/erros/skip e 89,99% de cobertura de linhas
(12.960/14.401). Registro `vh09-history-vps-v1.json`, vinculado ao arquivo de fonte
da release, não à árvore de trabalho posterior. Esses conjuntos se sobrepõem.
Ruff global, mypy de 125 módulos,
formatação dos seis arquivos do incremento sujeitos ao Ruff e prova VH-08
passaram; migrations seguem a exclusão preexistente do formatador no projeto.

VPS atualizada para `idml-foundation:vh09-20261020-v1`, schema
`b9d0e1f20314`. Backup `/opt/idml-platform/backups/20261020T183258Z` com restauração
isolada aprovada; retorno real à imagem anterior e reaplicação da nova passaram.
322 arquivos de runtime conferidos por hash e sem escrita pelo usuário da
aplicação; API/worker saudáveis; dados existentes e outros serviços preservados.
Aplicação web respondeu 200; recurso privado sem autenticação respondeu 401.
Não houve publicação de nova porta/URL. Isso é smoke, não E2E de homologação.

**Limite mantido:** histórico não é autorização vigente nem promoção de artigo.
O serviço continua interno, sem ciclo automático ativo. XPM não está conectado
nesse caminho; os executores externos dos testes são sintéticos. Não houve
nova validação dos artigos reais, chamadas pagas ou aprovação formal do XML.
Rollback da imagem não prova restauração de uma versão de artigo. A VH-09
permanece parcial e G-HOMOLOG continua não liberado.

Próximo desenvolvimento, sem mudar a lista de vinte itens:

1. VH-09: promoção/restauração com cabeça e linhagem explícitas, checagem atômica
   dos estados/autoridades/validações e integração com leitores/escritores humanos.
   Ensaiar concorrência com revisão humana e restauração efetiva, não só descarte.
2. VH-02/07: concluir pendências e conexão das validações obrigatórias antes de
   autorizar promoção. Nunca remover o bloqueio apenas para fazer o ciclo passar.
3. VH-10–13: ligar o ciclo limitado ao worker e à interface, com diferenças,
   histórico e arquivos selecionáveis sem IDs manuais.
4. Concluir operação/RC e E2E dos dois artigos; entregar roteiro e acesso ao
   especialista somente após os critérios da lista única.

Detalhes e evidências operacionais:
`VH09_REVALIDATION_HISTORY_AND_DEPLOY.md`.

## 37. VH-09 — Versão atual e restauração de rascunhos, 21–22/10/2026

Implementada a linhagem explícita da versão de trabalho, com migração
`c0e1f2031425`. A seleção da versão atual agora é compartilhada por revisão humana,
grants, staging e revalidação. A transação de uma decisão humana inclui snapshot,
evento de versão, decisão, validação e estado dos itens; uma exceção não deixa
partes confirmadas. Claim/criação/decisão de revisão usam o lock do recurso.

Restauração interna de rascunho comprovada: move o seletor para um snapshot
histórico sem apagá-lo/duplicá-lo; preserva a linhagem e incrementa a versão do
recurso. Repetição não reaplica sobre trabalho posterior. Empresa/fonte errada,
snapshot fora da linhagem, requisição antiga e adulteração são recusados.
Decisões humanas ou item assumido pelo revisor bloqueiam essa restauração
automática conservadora. Não foi criada permissão para desfazer trabalho humano.

23 testes novos, 180 na regressão local direcionada e 223 Linux aprovados.
PostgreSQL isolado: duas sessões idempotentes, conflito entre requisições distintas,
timeout real de lock durante claim humano, recusa após commit, rollback externo
e triggers comprovados. Mypy 126 módulos e Ruff global aprovados.

A alteração de `reviews.py` invalidou corretamente a prova vinculada à fonte VH-08.
Matriz reexecutada: 102 testes, 100% de linhas/ramificações dos dois módulos da
política; nova prova v2, sem sobrescrever v1, com 11 testes de contrato retestados.
Não reduzir gates nem anunciar CI global aprovado.

Implantação concluída em 22/10: imagem `vh09-heads-20261021-v1`, migração
`c0e1f2031425` e 324 arquivos de runtime verificados por hash/permissão. O backup
da preparação, `/opt/idml-platform/backups/20261021T133104Z`, foi preservado;
antes da ativação foi feito e restaurado em teste isolado um backup atualizado,
`/opt/idml-platform/backups/20261022T120540Z`. Retorno real à imagem de 20/10 e
reaplicação aprovados, sem eventos de restauração no banco ativo. API/worker
saudáveis, contagens dos dados e demais serviços preservados. Readiness e `/app`
responderam 200; recurso privado sem autenticação, 401; CSP/nosniff presentes.
Nenhuma nova porta/URL, credencial ou flag de IA. Não é teste E2E de homologação.
Repetição integral concluída em 22/10: **2.654 aprovados, zero falhas/erros/skip**,
seis warnings e **90,04% de cobertura de linhas** (13.087/14.534), em 19min45s.
A execução anterior foi interrompida, sem JUnit/cobertura final utilizáveis, e
não foi contada como aprovada. Prova `vh09-head-vps-v1.json` vinculada ao arquivo
de fonte, imagem e evidências desta release; conjuntos direcionados se sobrepõem.
Ruff global, mypy 126 módulos, formatação de 18 arquivos do incremento e prova
VH-08 aprovados novamente. Não é CI global aprovado; pendências VH-17 permanecem.
Detalhes: `VH09_CANONICAL_HEAD_AND_RESTORE.md`.

**VH-09 ainda parcial:** falta ligar a promoção às validações obrigatórias e
reconstruir/revalidar o pacote após restauração. O movimento da versão de trabalho
é distinto de release aprovada e não habilita IA, endpoint de restauração ou
aceite editorial. Próximo desenvolvimento: concluir DOCTYPE/JATS, erro residual
e consultas aplicáveis do XPM e conectar os validadores aos hashes finais
(VH-02/07); completar promoção/revalidação da restauração (VH-09); depois conectar
ciclo/worker/interface e executar E2E da lista única. Não ampliar a allowlist.

## 38. VH-02/07 — Ponte interna da execução XPM, 2026-10-22

Implementada a recepção interna de resultado XPM vinculado à empresa, artigo,
fonte, perfil e bytes XML/ZIP. A revalidação privada deriva o escopo no servidor
e persiste o diagnóstico verificado; erros/avisos/consultas incompletas permanecem
visíveis. Relatório de outro pacote, empresa, ferramenta ou versão é recusado.
Falha offline ou registro de validadores inválido não dispara XPM. Repetição da
requisição recupera histórico, sem nova execução ou promoção.

28 testes novos, 176 direcionados locais aprovados, zero falhas/erros/skip; Ruff,
mypy 127 módulos, seis arquivos formatados e prova VH-08 aprovados. Sem nova suíte
integral ou CI global aprovado. Os testes são sintéticos, não validação dos artigos
reais. Detalhes: `VH1_XPM_EXECUTION_BRIDGE.md`.

Repetição Linux isolada: 176 aprovados, mesmo conjunto da matriz local. A candidata
v2 corrige também emissão de aviso com valor privado inválido durante serialização;
contraprova exige ausência de warning. Fontes conferidas por manifesto, serviços
ativos idênticos ao estado anterior. Prova: `vh1-xpm-execution-bridge-v1.json`.

**Candidata, não ativada:** a VPS continua na imagem da seção 37. A ponte não é
o serviço XPM supervisionado, não aplica regras novas de compatibilidade e não
remove a barreira de aprovação. Próximo: ligar executor/retenção privada do HTML,
concluir DOCTYPE/JATS/erro residual/consultas e qualificar pacotes reais antes da
implantação integrada. Mantidos os mesmos IDs VH-02/07/09, sem nova fase.

## 39. VH-02/07 — Executor XPM real por socket, 2026-10-22

Entregue o transporte Linux entre a ponte da seção 38 e o XPM original já
instalado. O processo supervisor root aceita somente UID autorizado, configuração
fixa e escopo vinculado ao pacote/XML; o cliente verifica que o supervisor é root.
Sem socket Docker no container da aplicação, sem comandos/imagens/caminhos
escolhidos pelo solicitante. Há limites de entrada, saída, tempo, CPU, memória,
reserva de disco e retenção, além de exclusão mútua no diretório de trabalho.

O executor usa a imagem imutável qualificada, sem rede, valida integridade do
original e retém HTML/evidência em diretório privado. Não promove o XML reescrito
pelo XPM. A resposta pública continua sendo o diagnóstico sanitizado da ponte;
o relatório bruto trafega apenas no canal interno autorizado.

**Execução real comprovada:** dois artigos do pacote corrigido de 16/10 e dois
negativos (título da revista removido e XML truncado). Os quatro diagnósticos
foram atestados; todos conservaram bloqueios e consultas incompletas. Remover o
título aumentou os bloqueios de 3 para 4. Os relatórios root/0600 foram conferidos
por hash; 25 serviços ativos permaneceram idênticos à release ativa. É teste do
executor offline, não uma nova aprovação editorial nem comparação equivalente
com o XPM online.

28 novos testes incluídos em **211 locais e 211 Linux aprovados**, conjuntos
sobrepostos; Ruff global, mypy 128 módulos e formatação aprovados. O primeiro
ensaio detectou caminho AF_UNIX longo; o segundo, permissão de travessia do
mount de teste. Corrigidos na candidata v3. A primeira regressão Linux teve
210 aprovações e uma recusa correta por reserva temporária: o tmpfs de 256 MiB
era menor que reserva + upload. Repetida com tmpfs de 512 MiB, sem reduzir o
limite de admissão da aplicação. Tentativas anteriores não contam como aprovação.

Fontes candidatas verificadas na VPS, sem mudar API, worker, banco, flags, portas
ou credenciais. Sem nova execução integral/cobertura global. Detalhes e provas:
`VH1_XPM_EXECUTION_BRIDGE.md`, `vh1-xpm-socket-real-v1.json` e
`vh1-xpm-socket-v1.json` em `benchmarks/qualification/reports`.

**Próximo passo fechado:** conectar consultas externas supervisionadas e concluir
DOCTYPE/JATS/erro residual sob ADR-019, reaproveitando o transporte entregue;
qualificar as evidências finais com os dois artigos e negativos antes de ativar
API/worker. Depois completar promoção/restauração revalidada (VH-09), ciclo e web
(VH-10–13), operação/RC/E2E (VH-14–20). Sem acrescentar fase, ampliar allowlist,
dispensar validação ou declarar G-HOMOLOG.

## 40. VH-02/07 — Transporte online supervisionado do XPM, 2026-10-22

Conectado ao executor da seção 39 o modo online original, escolhido somente pela
configuração administrativa. Cada execução cria rede interna e proxy restrito,
sem porta pública, usando a mesma imagem imutável qualificada. O cliente continua
sem Docker socket e não pode escolher rede, proxy, comando ou endpoint.
Modo offline preservado. Antes do artigo, são exigidas recusas reais de localhost,
endereço de metadados e domínio não autorizado. Falha no teste impede execução.

Containers do proxy e da sonda e a rede são removidos pelos IDs exatos, inclusive
em falhas/timeout. A evidência online só é selada após a limpeza bem-sucedida.
Eventos privados do proxy são vinculados por hash; HTML bruto, ferramenta e XML
permanecem intactos. O XPM reescrito não é promovido, e conexão TLS não vira
declaração de consulta concluída.

Qualificação na VPS pela ponte real: dois artigos corrigidos e negativos de
título removido/XML truncado. Nos artigos válidos de referência, as contagens
brutas foram **3/1/4/2** e **3/1/4/3** (bloqueios/fatais/erros/avisos), contra
3/4/4/6 e 3/4/4/8 no offline. A redução decorre do modo online, não de alteração
dos candidatos ou aplicação de compatibilidade. Negativos continuam bloqueados.
O catálogo completo obtido por HTTPS teve hash conferido com o consumido pelo
XPM; título/editora coincidem exatamente com um único registro em ambos os artigos.

**267 testes locais e 267 Linux aprovados**, conjuntos sobrepostos, incluindo
24 novos de modo administrativo, falhas e limpeza. Ruff global, mypy 128 módulos
e formatação aprovados. Quatro relatórios atestados, 12 recusas de destinos,
16 arquivos de evidência root/0600 verificados, 25 serviços ativos preservados;
sem rede temporária remanescente. Provas: `vh1-xpm-online-socket-v1.json` e
`vh1-xpm-online-socket-real-v1.json`, em `benchmarks/qualification/reports`.

Candidata `vh1-xpm-online-socket-20261022-v1` na VPS, não ativada na API/worker.
Nenhuma migração, credencial, flag de IA ou publicação; sem nova suíte integral
ou cobertura global. **VH-02/07 ainda não concluída:** falta comprovar respostas
semânticas obrigatórias (túneis Crossref/ORCID não bastam), integrar as regras
ADR-019 qualificadas e resolver DOCTYPE/JATS/erro residual. Só então qualificar
o conjunto/ativação e avançar promoção/restauração, ciclo/web e RC/E2E conforme
a mesma lista única. Indisponibilidade Wayta não foi transformada em sucesso.

## 41. VH-02/07 — Respostas semânticas Crossref/ORCID, 2026-10-23

Implementadas coleta independente e avaliação de respostas públicas, selecionadas
pelo XML exato e não por URLs enviadas pelo usuário. Conferem DOI/ISSN/títulos e
lista ordenada de autores Crossref; ORCID exige identificador/checksum/registro
correto e correspondência exata com nome público, com normalização NFC, caixa e
espaços, sem aproximação, remoção de acentos ou mudança de autoria.

Recibos privados com bytes, origem, hash e horário ficam ligados à empresa,
recurso, fonte IDML, perfil, XML/ZIP e relatório XPM. Validade de 24 horas; destinos
HTTPS fixos e IP público, sem redirecionamento/proxy herdado, com timeout real de
subprocesso, limites de resposta e orçamento total. Diagnóstico não publica nomes
ou JSON bruto. Não são respostas interceptadas do XPM: são verificações
independentes posteriores; a conclusão global das consultas continua falsa.

Conflito agora gera `xpm-authority-response-conflict` e bloqueia o pacote mesmo
quando as contagens XPM são zero. Falha/ausência gera pendência explícita; evidência
semântica inválida não transforma o relatório bruto válido em aprovação. O fluxo
de histórico recebe esse diagnóstico; não houve ativação de worker/UI/promoção.

Matriz real final: quatro relatórios atestados, dois artigos e dois negativos;
13 recibos verificados e 19 arquivos selados root/0600. Crossref corresponde nos
dois baselines. No e86, três ORCIDs correspondem; no e135, quatro nomes públicos
não são confirmados por igualdade exata. Dois registros não oferecem sobrenome
separado; não se concluiu que os identificadores sejam errados nem se alterou o
XML. O título removido foi recusado na comparação Crossref; XML truncado não
dispara coleta semântica e conserva os erros XPM.

**373 testes locais e 373 Linux aprovados**, sobrepostos, 55 novos; Ruff global,
mypy 130 módulos e formatação aprovados. A primeira matriz real foi parcial:
regressão Linux concorrente consumiu a reserva de memória e a proteção interrompeu
o último caso. Esse container temporário também apareceu como adicional no
inventário. Os 25 serviços ativos continuaram idênticos. A matriz real foi repetida
sem concorrência, concluindo os quatro casos, e a regressão Linux executada depois.
Nenhum limite da VPS foi reduzido, nem hardware aumentado.

Candidata `vh1-xpm-semantic-20261023-v3`, 1.142 arquivos verificados; a aplicação
ativa continua `vh09-heads-20261021-v1`. Sem nova suíte integral/cobertura global,
aprovação SciELO, mensagem externa ou IA. Detalhes e provas:
`VH1_XPM_SEMANTIC_QUERIES.md`, `vh1-xpm-semantic-v1.json` e
`vh1-xpm-semantic-real-v1.json` em `benchmarks/qualification/reports`.

Próximo incremento delimitado, nos mesmos VH-02/07: distinguir os quatro casos
ORCID de registro incompleto/divergência usando as fontes autorizadas, sem troca
automática de identificador/nome; integrar a avaliação derivada ADR-019 com provas
atuais e concluir DOCTYPE/JATS/erro residual e demais consultas. Requalificar a
combinação antes de ativar API/worker. Depois VH-09, ciclo/web e RC/E2E da lista
única. Não acrescentar fase ou dispensar pendências para obter aprovação.

## 42. VH-02/07 — Compatibilidade DOI integrada e triagem ORCID, 2026-10-23

Conectadas as duas regras DOI qualificadas à execução atual, com Crossref fresco,
relatório/escopo/imagem conferidos. Nos dois artigos, duas ocorrências classificadas
por artigo: bruto e86 3/1/4/2 e e135 3/1/4/3; derivado **somente DOI** 3/1/2/2 e
3/1/2/3. Sem apagar erros, alterar XML/ZIP ou conceder aprovação. SPS/data não foi
descontado nesse resultado: sua composição com prova independente atual é o próximo
incremento, não uma implementação presumida a partir dos testes isolados anteriores.

Investigação e implementação demonstraram sete vínculos exatos autor–ORCID no
Crossref. No e135, as quatro pendências de nome público dividem-se em duas
incompletas e duas não exatas. Não há base nesta prova para trocar identificadores
ou nomes. O diagnóstico mostra ambas as fontes sem confundir vínculo depositado
com titularidade autenticada. Vínculo divergente bloqueia mesmo com XPM limpo;
ausência de depósito, nomes repetidos e editor têm tratamentos próprios.

Matriz real repetida nos dois artigos e negativos (título removido/XML truncado);
negativos sem aplicação indevida de compatibilidade. **498 testes locais e 498
Linux aprovados**, sobrepostos, 41 novos; Ruff global e mypy 132 módulos aprovados.
Quatro relatórios, 13 recibos e 19 selos root/0600 verificados; 25 serviços preservados,
nenhuma rede temporária restante. Não houve nova cobertura global ou suíte integral.

Candidata `vh1-xpm-runtime-20261023-v1` na VPS, não ativada. Provas e sequência
delimitada: `VH1_XPM_RUNTIME_COMPATIBILITY.md`, `vh1-xpm-runtime-v1.json` e
`vh1-xpm-runtime-real-v1.json` em `benchmarks/qualification/reports`.
Próximo: integrar SPS/data/Wayta com provas atuais; concluir decisão DOCTYPE/JATS,
erro residual e demais consultas. Depois requalificação/ativação e os mesmos
VH-09–20. Sem mudança da allowlist de IA, etapa adicional ou liberação G-HOMOLOG.

## 43. VH-02/07 — Validação composta SPS/data e Wayta, 2026-10-26

Entregue composição do resultado DOI com SPS/data e aplicabilidade Wayta no serviço
de validação de pacote. Contrato runtime 2.0 preserva os hashes individuais dos
validadores modernos e acrescenta vínculo reproduzível com escopo/relatório XPM.
Falha independente mantém DOI, mas impede SPS/data; observação Wayta inválida ou
ausente mantém requisito indeterminado. Nenhuma falha vira aprovação.

Novo cadastro candidato conserva imagens qualificadas, com versões de rollback
distintas. Sem relaxar validação do cadastro ou mudar configuração ativa. Sonda
Wayta limitada e selada pelo broker, com norma/prova histórica verificadas por hash.
Consulta auxiliar para o perfil qualificado não significa consulta concluída.

Em 26/10 foram coletadas fontes novas, executados seis testes modernos nativos e
quatro XPM. Nos baselines, seis ocorrências por artigo classificadas; bruto e86
3/1/4/2 e e135 3/1/4/3, derivado **0/1/1/2 e 0/1/1/3**. Fatal, erro residual,
avisos e pendências ORCID permanecem. Título removido e XML truncado continuam
bloqueados sem aplicação indevida de compatibilidade. XML truncado não é
provisionado nos modernos: indisponibilidade explícita, não sucesso inventado.

Candidata `vh1-xpm-composed-20261023-v4`, não ativada na API/worker. Prova atual e
limites em `VH1_XPM_COMPOSED_VALIDATION.md`. Próximo trabalho: decisão DOCTYPE/JATS,
erro residual e fechamento das pendências de consultas/avisos; depois ativação
qualificada e os mesmos VH-09–20. Sem nova fase, liberação editorial ou G-HOMOLOG.

Fechamento da seção 43: **609 testes locais e 609 Linux aprovados**, sobrepostos,
35 novos; Ruff global, mypy 132 módulos e formatação aprovados. Auditoria reproduziu
os dois hashes compostos e conferiu seis relatórios modernos, quatro XPM, 13 recibos
de consulta e 22 arquivos selados root/0600. Três sondas Wayta com timeout explícito.
25 serviços ativos preservados; ready/app HTTP 200. Sem suíte integral/cobertura
nova ou CI global. Provas `vh1-xpm-composed-v1.json` e `vh1-xpm-composed-real-v1.json`
em `benchmarks/qualification/reports`; fontes/evidências renovadas em 26/10.

## 44. VH-02/07 — Correção MathML3 e decisão técnica XPM, 2026-10-26/27

Corrigida a combinação PUBLIC/SYSTEM da DTD MathML3 no gerador. Os dois artigos
reconstruídos preservam conteúdo e ativos; os manifestos refletem os novos hashes.
Ambos passaram nos validadores modernos com cinco avisos cada. Nota inventada
gera erro nos dois; versão incompatível falha sem aprovação. Seis recibos modernos
e duas falhas registradas, além de seis testes estruturais nativos do XPM.

Diagnóstico encerrado: fatal decorre do catálogo/DTD 1.1 legado; erro residual
decorre do Style Checker sem suporte SPS 1.10. Não existe nova exceção de
compatibilidade, downgrade ou autorização SciELO. A ressalva editorial permanece.
Ver `VH1_DOCTYPE_JATS_DECISION.md` e `vh1-doctype-native-v2.json`.

Provas históricas preservadas; transições exatas de código auditadas e V-10/V-11
reexecutados. Candidata final `vh1-doctype-20261027-v1` armazenada, não ativa. Próximo:
diagnóstico de homologação para as causas identificadas, tratamento de avisos e
consultas/ORCID, composição completa nos novos hashes; ativação qualificada e os
mesmos VH-09–20. Sem nova fase ou pesquisa DOCTYPE indefinida.

Fechamento inclui o vínculo das regras SPS/data e Wayta com a composição nativa
já auditada em 26/10. Essa correção de rastreabilidade não muda regras nem aprova
contagens. Os relatórios e candidatos anteriores permanecem preservados.

Fechamento em 27/10: **2.906 testes locais e 966 Linux aprovados**, sobrepostos,
41 novos; zero falhas/erros/skip finais. Ruff global, mypy 132 módulos e whitespace
aprovados. Sem nova cobertura global ou integração PostgreSQL. Auditoria reproduzida,
1.176 arquivos conferidos, 25 serviços preservados, ready/app HTTP 200. Prova:
`benchmarks/qualification/reports/vh1-doctype-closure-v1.json`. Sem ativação,
exceção DTD ou aprovação XML; composição completa dos novos hashes ainda pendente.

## 45. Painel de diagnóstico por job — 27/10/2026

Concluído o primeiro próximo passo da seção 44: API de diagnóstico autenticada
e botão no dashboard. A leitura separa achados XML/pacote, limitações conhecidas
do XPM e pendências editoriais. Preserva totais, evidências e bloqueios; não
transforma erro desconhecido em exceção, nem considera indisponibilidade aprovação.
Resultados salvos não são novas execuções ou renovações de fontes.

**139 testes locais e 139 Linux aprovados**, mesmo conjunto; 34 novos casos
incluídos. Seis verificações JavaScript em DOM controlado, V-10/V-11 reexecutados
localmente e na VPS, Ruff e mypy (133 módulos) aprovados. Sem novo teste E2E
visual, cobertura global ou execução online XPM neste incremento.

Candidata `vh1-diagnosis-20261027-v1` armazenada na VPS, não ativa; 1.184 arquivos
verificados e 25 serviços preservados, ready/app HTTP 200. Detalhes e evidências
em `VH1_VALIDATION_DIAGNOSIS.md` e `vh1-diagnosis-closure-v1.json`.

Próximo: avisos e consultas/ORCID, composição completa nos novos hashes,
ativação qualificada e conclusão dos mesmos VH-09–20. Sem nova fase, novo
aceite de compatibilidade, publicação ou liberação G-HOMOLOG.

## 46. Ações para avisos, consultas e ORCID — fechamento em 28/10/2026

Diagnóstico estendido com ações por fonte/estado, vínculo entre consulta e
depósito ORCID e separação entre disponibilidade Wayta e identidade institucional.
Não aceita avisos nem infere titularidade. Os totais modernos não permitem
classificação individual; essa limitação permanece explícita.

297 testes locais e 297 Linux aprovados (sobrepostos), 41 casos novos; seis
verificações JavaScript e releitura da prova nativa histórica dos dois artigos.
Sete vínculos depositados e quatro pendências de nome público preservados.
V-10/V-11, Ruff e mypy (134 módulos) aprovados. Candidata
`vh1-followups-20261027-v1` armazenada na VPS, não ativa; 1.191 arquivos
conferidos, 25 serviços preservados, ready/app HTTP 200.

Detalhes: `VH1_QUERY_WARNING_FOLLOWUPS.md`. Próximo passo autorizado em 28/10:
composição online completa nos pacotes MathML3 corrigidos, com consultas novas
e recibos vinculados aos hashes atuais; depois ativação qualificada e VH-09–20.

## 47. Composição online MathML3 concluída — 28/10/2026

Quatro execuções XPM novas (dois artigos corrigidos e dois controles negativos),
seis recibos modernos e treze recibos de consultas auditados. Os pacotes corrigidos
mantiveram os hashes já qualificados. Modernos: zero erros e cinco avisos por
artigo/ferramenta. XPM conserva os bloqueios legados; após as regras existentes,
restam um fatal, um erro e dois/três avisos. Todos os casos continuam `blocked`.

Avisos classificados por grupos estruturais sem aceite; quatro pendências de
nome público ORCID preservadas apesar dos sete vínculos Crossref coincidentes.
Wayta retornou timeout. Os controles negativos foram bloqueados pelo conjunto;
os modernos isolados não detectaram ausência do título do periódico.

25 serviços e 1.191 arquivos preservados; ready/app HTTP 200. Diagnóstico atual
reproduzido sobre os quatro resultados novos. Ver `VH1_MATHML3_COMPOSED_VALIDATION.md`
e provas `vh1-mathml3-composed-*-v1.json`. Não houve ativação ou aprovação XML.

Próximo: integrar a decisão de compatibilidade residual JATS/Style Checker e a
saída formal para avisos/consultas no VH-02/07; depois ativação qualificada e os
mesmos VH-09–20/G-HOMOLOG. Não criar outra fase nem repetir a pesquisa já encerrada.

## 48. Compatibilidade residual integrada — 28/10/2026

As duas regras restritas para DTD legada e Style Checker sem suporte SPS 1.10
estão integradas ao compositor. Exigem XML local válido, dois validadores modernos
sem erros, vínculo completo da evidência e mensagens exatas. A reprodução dos
relatórios nativos selados dos dois artigos, no instante original, resulta em
zero bloqueios/fatais/erros derivados, com dois/três avisos XPM preservados.
Resultado bruto e bloqueio de publicação permanecem intactos. Não houve novas
consultas/execuções dos validadores neste replay nem renovação de evidências.

405 testes locais e 405 Linux aprovados, conjuntos sobrepostos; 32 testes novos
das regras e 17 testes de integridade da sucessão dos fontes. Dois controles
nativos negativos rechecados localmente e dois relatórios com erro adicional
recusados. V-10/V-11 requalificados; Ruff, mypy (135 módulos) e diff-check aprovados.

Candidata `vh1-structural-20261028-v1` preservada na VPS, não ativa; 1.206 arquivos
conferidos, 25 serviços preservados, ready/app HTTP 200. Evidências em
`vh1-structural-native-replay-v1.json` e `vh1-structural-closure-v1.json`.
Detalhes e limites em `VH1_STRUCTURAL_COMPATIBILITY.md` e ADR-019.

Próximo item concreto: ativação qualificada da candidata acumulada e ligação à
promoção formal/revalidação restaurada do VH-09; depois a fila já definida
VH-10–20. Avisos, identidades, afiliações e aceite editorial permanecem pendentes.
Isso conclui a regra residual técnica, não a liberação G-HOMOLOG ou publicação.

## 49. Candidata acumulada ativada na VPS — 29/10/2026

API/worker em `vh1-structural-20261028-v1`, imagem `c174d22a596c…`, com 334
arquivos de runtime verificados em cada container. Banco permanece em
`c0e1f2031425`. Backup novo e restauração isolada aprovados; retorno à imagem
anterior e reaplicação exercitados. Dados preservados, cinco serviços IDML
saudáveis e os outros 23 containers inalterados.

625 testes na imagem Linux final e concorrência/proteção humana no PostgreSQL
isolado aprovados. O teste de upload inicialmente recusado por tmpfs insuficiente
passou após aumentar apenas o limite do laboratório; log inicial preservado.
Reprodução nativa histórica na imagem confirmou as regras dos dois artigos e
controles negativos, sem renovar recibos. HTTP ready/app/JS 200, rotas privadas
sem autenticação 401; diagnóstico web e cabeçalhos de segurança conferidos.

O código acumulado está implantado, mas isso não conecta o XPM ao worker comum
nem habilita aplicação automática. Nenhuma IA executada, nenhuma migração nova,
aprovação de XML ou G-HOMOLOG. Próximo desenvolvimento: promoção formal da
candidata e reconstrução/revalidação da versão restaurada, dentro do VH-09.
Depois, fila existente VH-10–20. Evidências, limites e critérios em
`VH1_STRUCTURAL_DEPLOYMENT.md` e `vh1-structural-deployment-v1.json`.

## 50. VH-09 — Promoção para versão de trabalho qualificada — 29/10/2026

Serviço interno agora promove candidata elegível mediante revalidação nova,
checagem de fontes/grants/escopo, política técnica explícita e proteção humana.
Snapshot, linhagem e recibo são gravados atomicamente. Repetição retorna histórico
sem mover novamente a versão atual, inclusive depois de restauração. Avisos
ficam pendentes; publicação e aprovação editorial não são concedidas.

60 testes novos; 387 locais e os mesmos 387 Linux aprovados. PostgreSQL isolado
comprovou concorrência, idempotência, conflito, lock humano, rollback e
imutabilidade. Reprodução de política sobre relatórios nativos: e86 elegível
como rascunho, e135 bloqueado por consultas ORCID divergentes; dois negativos
recusados. Isso não executou promoção real, renovou evidências ou chamou IA.
Ruff, mypy (137 módulos) e diff-check aprovados; sem nova cobertura/suíte integral.

Código qualificado armazenado na VPS; aplicação ativa continua na imagem da
seção 49. 25 serviços e banco ativo preservados, ready HTTP 200. As duas falhas
iniciais de laboratório e os limites estão documentados em
`VH09_WORKING_DRAFT_PROMOTION.md`. Provas `vh09-promotion-v1.json` e
`vh09-promotion-native-policy-v1.json`.

Próximo desenvolvimento concreto: reconstrução/revalidação do pacote da versão
restaurada, ainda no VH-09. Depois ligar promoção/restauração ao ciclo/worker e
executores supervisionados (VH-10/14), fluxo web e ensaios finais existentes.
Sem fase adicional, ativação automática ou liberação G-HOMOLOG.

## 51. VH-09 — Pacote restaurado revalidado — 29/10/2026

Reconstrução exata do snapshot restaurado com XML/ZIP e recibo novos. Conferência
de IDML/PDF/imagens, empresa, versão e estado humano antes/depois dos validadores.
Restauração e persistência podem ocorrer na mesma transação; erro de integridade
desfaz ambas. Validação impeditiva fica registrada como bloqueada, sem herdar
aprovação anterior. Pedido repetido retorna histórico; novo pedido revalida.

34 testes novos, 421 locais e os mesmos 421 Linux aprovados. PostgreSQL isolado
comprovou migração aditiva, concorrência/idempotência/conflito, proteção humana,
rollback, imutabilidade e downgrade/upgrade sem modificar versões existentes.
Ruff, mypy (140 módulos) e diff-check aprovados. Validadores externos sintéticos;
sem nova execução online, aprovação de artigo real, IA ou cobertura global.

Código qualificado armazenado na VPS; migração `d1f203142536` testada somente
em banco descartável. Aplicação/banco ativos preservados em
`vh1-structural-20261028-v1`/`c0e1f2031425`; 25 serviços inalterados e ready 200.
Prova `vh09-restored-package-v1.json`; detalhes e limites em
`VH09_RESTORED_PACKAGE_VALIDATION.md`.

Os serviços internos previstos do VH-09 estão implementados. Seu aceite integrado
ainda depende da ligação ao worker/ciclo e aos executores supervisionados
(VH-10/14), implantação e E2E. Esse é o próximo desenvolvimento, sem nova fase
ou repetição da implementação de promoção/restauração. G-HOMOLOG não liberado.

## 52. VH-10/14 — Worker e validadores supervisionados implantados — 30/10/2026

O job `scielo.package` agora envia XML/ZIP ao Packtools, SPS Validator e XPM com
escopo derivado dos registros da empresa/artigo. Revisão e worker usam o perfil
1.1. Relatórios inválidos, de outro pacote ou indisponíveis não concedem aprovação.

Dois artigos reais passaram pelo worker em banco isolado com execução nativa dos
três validadores. Os XMLs e ativos ficaram idênticos à referência qualificada;
somente a versão do validador offline foi adicionada ao manifesto ZIP. Fontes
públicas foram obtidas novamente e vinculadas aos novos hashes. Não foi repetida
ingestão IDML nem acionada IA. Quatro execuções modernas: zero erros/críticos,
cinco avisos cada. XPM: oito ocorrências técnicas reconhecidas pela política,
zero erros derivados, dois/três avisos e consultas pendentes. Publicação bloqueada.

**Implantação concluída:** `vh10-worker-20261030-v1`, imagem `e4f9649a…`, banco
`d1f203142536`. 1.235 fontes congeladas; 340 arquivos conferidos por hash e sem
escrita em cada runtime. Backup `/opt/idml-platform/backups/20261030T115545Z`,
restore isolado, rollback real para a imagem anterior e reaplicação aprovados.
25 containers e contagens preservados; cinco serviços IDML saudáveis. Ready/app
200, rota privada 401. Dois serviços systemd novos, sem Docker socket na aplicação;
reinício após SIGKILL, bind preservado, reconexão do worker e recusa de UID indevido
comprovados. Não houve autorização laboratorial copiada para usuários reais.

**Validação:** 242 testes locais, incluindo 25 novos; 465 Linux, conjuntos
sobrepostos, zero falhas. Migração/concorrência/rollback/imutabilidade no PostgreSQL
descartável aprovados. Ruff, mypy (140 módulos) e diff-check aprovados. Dois avisos
Linux: depreciação do cliente de teste e serialização de fixture negativa; não
houve nova medição de cobertura nem aprovação global de CI.

Provas: `vh10-worker-native-v1.json` e `vh10-worker-deployment-v1.json` em
`benchmarks/qualification/reports/`. Procedimento/limites: `VH10_WORKER_VALIDATION.md`.

**Sequência restante, sem novas fases:** (1) fontes/autorização por empresa/artigo
e ciclo IA limitado com promoção, restauração e revalidação — VH-09/10/14;
(2) fluxo web completo de entrada, diagnóstico, diferenças e saída — VH-11–13;
(3) RC, regressão/E2E com os dois artigos e contraprovas, recuperação e entrega ao
especialista — VH-14–20. O gate final continua exigindo essas funções integradas.
Agentes IA desativados; sem G-HOMOLOG, aceite humano ou publicação SciELO.

## 53. VH-10/14 — Fontes públicas por artigo e coleta automática implantadas — 30/10/2026

A aba **Fontes públicas** permite ao administrador selecionar o artigo e autorizar,
renovar ou revogar consultas por 7/30 dias, sem copiar IDs. Decisões são vinculadas
à empresa/artigo/IDML/perfil, imutáveis e auditadas; leitura por operadores, escrita
somente por administrador. Conflito de versão não sobrescreve outra decisão;
repetição retorna histórico e não reativa autorização revogada. Expiração, troca
da origem e perda de permissão administrativa são verificadas pelo supervisor.

O broker lê a decisão confirmada no banco através do container gerenciado da API.
Não recebe grants/URLs/comandos do job. Coleta Crossref/ORCID/cadastro SciELO novos,
vincula ao XML/ZIP e limita o bundle a 24 horas e à validade do consentimento.
Novo pacote gera novas fontes; renovação preserva o histórico. Dados adulterados
não são substituídos silenciosamente. Consentimento é conferido após a coleta e
após cada execução moderna/XPM; consultas ausentes nunca contam como sucesso.

**Ensaio real:** os dois artigos partiram de diretórios de fontes vazios, receberam
autorização pela rota HTTP e concluíram worker + coleta + Packtools/SPS/XPM.
O supervisor leu decisões reais no banco isolado, sem simular o resultado da
autorização. Depois da revogação, todos os executores recusaram novas chamadas,
sem novo bundle/execução XPM. Quatro execuções modernas: zero críticos/erros e
cinco avisos cada; XPM derivado: zero erros técnicos, dois/três avisos. Os XMLs e
ZIPs permaneceram iguais aos qualificados na seção 52. Não foi repetida ingestão
IDML nem acionada IA; nenhum usuário/artigo ativo recebeu autorização implícita.

**Implantação concluída:** `vh10-sources-20261030-v1`, imagem `c0ed6eef…`, banco
`e2f314253647`. 1.250 fontes congeladas; 345 arquivos verificados em cada runtime.
Backup `/opt/idml-platform/backups/20261030T175647Z`, restore isolado,
rollback real à imagem anterior e reaplicação aprovados. Reinício após SIGKILL,
reconexão, recusa de UID indevido e ausência de consentimento comprovados na VPS.
25 containers/dados preservados; cinco serviços IDML saudáveis. Ready/app/script
200 e rota privada 401. IA continua desativada e homologação não liberada.

**Validação:** 532 testes locais e os mesmos 532 Linux (38 novos), sem falhas/erros/
skip; PostgreSQL descartável com concorrência, conflito, rollback, revogação e
dois controles SQL de imutabilidade. UI em Node: seleção, texto seguro e respostas
atrasadas de outra empresa/artigo. Não é E2E de navegador. Ruff, mypy (144 módulos)
e diff-check aprovados. Sem nova cobertura ou aprovação global de CI; dois avisos
Linux históricos (cliente de teste e fixture negativa).

Provas: `vh10-article-sources-native-v1.json` e `vh10-article-sources-deployment-v1.json`.
Detalhes: `VH10_ARTICLE_PUBLIC_SOURCES.md`. Fontes públicas não autorizam alterações
automáticas no XML nem substituem os catálogos editoriais e evidências de correção.
Próximo, no mesmo VH-09/10/14: ligar esses insumos e os serviços existentes ao ciclo
IA limitado; depois concluir o fluxo web geral e RC/E2E/entrega já previstos.

## 54. Evidências do IDML no worker e revalidação de pacotes reconstruídos (31/10)

O job `idml.process` prepara a proveniência dos campos no perfil ESA 1.1 qualificado antes de persistir a primeira revisão. O catálogo relaciona evidência, origem e versão canônica. O diagnóstico do job mostra quantos vínculos exatos as regras identificaram e quantas verificações recusaram. Uma repetição que encontra a versão histórica anterior reutiliza o snapshot. A preparação compara os bytes de XML antes e depois e recusa divergência.

Candidatos de correção e versões restauradas selecionam os sockets configurados pelo servidor depois de reconstruir o pacote e validar o XML localmente. O escopo inclui empresa, artigo, origem, perfil e hashes do XML e do ZIP recém-gerados. Falha local impede o envio. Permissões de fonte pública e de edição continuam independentes.

**Ensaio com os IDMLs originais.** A conversão sem catálogos editoriais privados produziu XML localmente válido para os dois artigos. Em cada caso o XML foi idêntico ao produzido pelo mesmo pipeline sem a preparação de evidência.

| Artigo | Vínculos nas três regras | Verificações recusadas | SHA-256 do XML desta conversão |
|---|---:|---:|---|
| e20240086 | 0 | 0 | `f0753f472b391058341a8979cfad4cc7c86fe4e8f15c9da5d94a1f250ab58f5f` |
| e20240135 | 0 | 0 | `22c63e1b7b9008385ef3c54999b6279e8d11faaade0a897d1fdac72b5e887f3c` |

Esses hashes identificam o XML de ingestão. A seção 53 identifica os pacotes enriquecidos, com outros hashes e validações formais próprias. O caso sintético com afiliação ausente exercita um vínculo positivo no job. As integrações de candidato e restauração verificam os bytes que seriam enviados aos três validadores com transportes controlados.

**Critério para avançar no mesmo VH-09/10/14.** O worker da VPS está com a varredura ClamAV e o armazenamento de enriquecimento privado desabilitados. O executor exige arquivos verificados. As versões canônicas dos dois artigos usadas no ensaio da seção 53 registram 27 e 54 itens de layout, respectivamente, todos sem hash de conteúdo. Um ZIP que já contém as figuras permite testar o transporte dos validadores, mas não prova o vínculo das figuras fornecidas com a versão canônica restaurada.

1. Qualificar na VPS a varredura com limite de memória, a releitura dos bytes históricos e o vínculo exato por hash entre as figuras do XML e os arquivos fornecidos. Hoje reenviar bytes idênticos reutiliza o mesmo registro e seu estado anterior de varredura. O aceite deve demonstrar uma nova verificação auditável para esses bytes, inclusive a recusa quando o serviço estiver indisponível. Itens de diagramação e figuras com correspondência ambígua devem ficar identificados.
2. Usar o catálogo recalculado a partir do IDML e uma autorização específica de edição, vinculada à empresa, ao artigo e à versão. Qualificar o caso com um campo ausente comprovado e o caso sem operação elegível. O segundo deve encerrar antes de chamar o provedor.
3. Exercitar os papéis de proposta, crítica e adjudicação, com recusa, interrupção, orçamento, limite de duas rodadas, aplicação ao rascunho e restauração revalidada. Só então habilitar a execução no escopo autorizado e percorrer o fluxo web da RC até a entrega ao especialista.

**Resultado na VPS.** A imagem ativa da API e do worker é `vh10-evidence-20261031-v1`, banco `e2f314253647`. O pacote enriquecido do e20240086 passou pelo transporte de revalidação com autorização restrita ao banco de ensaio. Packtools e SPS registraram cinco avisos cada, sem erro. O XPM bruto registrou três bloqueantes, um fatal, quatro erros e dois avisos. A composição de compatibilidade do job no mesmo pacote registrou zero erros técnicos e dois avisos. A revogação impediu os três executores de iniciar outra execução nativa. O ensaio utilizou bytes previamente qualificados do pacote, sem promover nem restaurar esse artigo real por IA.

536 testes locais e os mesmos 536 no Linux, com zero falhas. Quatro testes novos cobrem a ingestão e repetição com versão nova ou histórica e os dois caminhos de pacote reconstruído. PostgreSQL isolado aprovado. Ruff e mypy (144 módulos) aprovados no escopo verificado. Backup restaurado em isolamento, reversão da imagem e reaplicação verificadas. Os cinco serviços IDML estão saudáveis. A homologação humana continua pendente.

Prova consolidada em `benchmarks/qualification/reports/vh10-worker-evidence-v1.json`.

## 55. Varredura dos arquivos e vínculo das figuras (31/10)

O mesmo artigo tem duas perguntas diferentes sobre figuras. Para saber se o ZIP preservou a imagem enviada, o worker registra a referência do XML, o nome no pacote, o identificador do arquivo na empresa e o SHA-256 dos bytes. Para confirmar também a origem no documento canônico, exige uma única entrada correspondente em estado presente, com hash igual, além da varredura do arquivo. O diagnóstico informa quantas origens continuam pendentes. O registro identifica os itens de layout sem referência gráfica no XML. Havendo conflito com um hash canônico conhecido, o job recusa o pacote. Candidatos por número de figura permanecem identificados como tal. O empacotamento recusa uma imagem solicitada pelo XML quando o arquivo falta ou o número admite duas correspondências. Também recusa nomes de arquivo duplicados. Uma origem canônica desconhecida deixa a figura pendente no diagnóstico.

O operador pode usar **Ingestão e processamento → Verificar arquivo** para reler e verificar um arquivo histórico da própria empresa. O registro de auditoria associa usuário, empresa, arquivo, hash, estado anterior e resultado à transação. Reenviar os mesmos bytes após uma varredura limpa atualiza o registro existente. Uma nova varredura inconclusiva retira a confirmação anterior. Um resultado de detecção coloca o arquivo existente em quarentena e bloqueia a leitura pelo sistema. O conteúdo e a revisão do XML não são alterados pela varredura.

A VPS executa ClamAV sob demanda em um container de uso único, com uma entrada por vez. O motor recebe os bytes pela entrada padrão e só monta as assinaturas para leitura. A API acessa o socket privado de varredura. A atualização de assinaturas usa um processo separado com trava mútua. As bases vencidas há mais de sete dias causam recusa. O limite por varredura é de 850 MiB de RAM, 1.400 MiB somando RAM e swap, 0,7 CPU e 110 segundos para o motor. Comando de atualização e parâmetros de operação no runbook.

**Resultado com os arquivos fornecidos**

| Artigo | Referências gráficas na conversão direta | Figuras no XML de referência | Figuras idênticas no ZIP enriquecido | Origens confirmadas por hash no canônico |
|---|---:|---:|---:|---:|
| e20240086 | 20 | 5 | 5 | 0 |
| e20240135 | 43 | 7 | 7 | 0 |

A montagem direta falhou nos dois casos por falta de arquivo para uma referência gráfica. O ensaio repetiu a montagem com a versão canônica enriquecida já qualificada de cada artigo, ligada ao mesmo IDML. Os ZIPs reproduziram os hashes históricos e passaram na validação XML offline. A comparação com o XML fornecido conferiu os nomes de todas as figuras. As 12 imagens dentro dos ZIPs foram comparadas byte a byte com os originais. O processo releu os dois IDMLs históricos com registro de auditoria, verificou os dois PDFs e as 12 imagens e rejeitou o controle EICAR. Em outro ensaio isolado, a releitura com um socket indisponível devolveu HTTP 503 e gravou a auditoria. Os validadores externos e os agentes não foram executados neste ensaio.

Na versão sintética, a origem canônica única com hash correto, estado presente e arquivo limpo foi confirmada. Duas origens possíveis, ausência de verificação de conteúdo e estado canônico pendente ficaram sem confirmação. Um hash canônico divergente impediu o pacote.

**Implantação.** Release `vh10-scan-20261031-v1`, banco `e2f314253647`. 575 testes locais e 575 no Linux aprovados, com dois avisos em cada plataforma. PostgreSQL isolado, restauração do backup, reversão, reaplicação e varredura pela API ativa verificados. Cinco serviços IDML saudáveis. A homologação segue pendente. Prova consolidada em `benchmarks/qualification/reports/vh10-scan-figure-bindings-v1.json`.

**Próximo aceite de VH-09/10/14.** Usar o catálogo recalculado do IDML e a autorização de edição específica da empresa, artigo e versão. Demonstrar um campo ausente com evidência suficiente e a abstenção antes da chamada ao provedor quando não houver operação elegível. Na presença de figuras, somente uma origem comprovada pode sustentar a correção que depende dela. Em seguida, executar o ciclo limitado de proposta, crítica, adjudicação e restauração antes do ensaio web da RC.

## 56. Decisão de edição por revisão e abstenção antes do provedor (01/11)

O job `autocorrection.preflight` relê o IDML verificado e recalcula o catálogo de campos para a revisão vigente. Se há um campo elegível, a autorização administrativa precisa corresponder à empresa, ao artigo, ao ID e ao hash do snapshot, à revisão editorial e aos hashes do IDML e do catálogo. A API só recebe os identificadores. O worker verifica a decisão novamente ao terminar. Uma mudança de revisão exige nova decisão mesmo com XML idêntico. O job registra o resultado, e o diagnóstico distingue candidato validado, abstenção e recusa.

| Entrada na VPS | Operações elegíveis | Resultado |
|---|---:|---|
| IDML original e20240086 | 0 | Abstenção antes do provedor. Nenhuma permissão de campo nem candidato criado. |
| IDML original e20240135 | 0 | Abstenção antes do provedor. Nenhuma permissão de campo nem candidato criado. |
| IDML sintético com afiliação ausente | 1 | A afiliação recuperada apareceu em `aff/institution[@content-type='original']`. O XML candidato passou na validação offline. |

O ensaio na VPS usou ClamAV real, ZIPs IDML fornecidos e banco isolado. Conferiu repetição idempotente, empresa e artigo incorretos, revisão e versão canônica incorretas, expiração, integridade dos hashes, revogação e renovação de decisão. Os rascunhos permaneceram na mesma versão. O candidato sintético permaneceu separado. Foram feitas zero chamadas a provedores e zero edições de artigos ativos. A validação formal do pacote após a aplicação e a restauração continua no ciclo integrado.

A versão `vh10-edit-20261101-v2` está ativa na VPS, com banco `e2f314253647`. Passaram 578 testes locais e os mesmos 578 no Linux, com dois avisos em cada plataforma. PostgreSQL isolado, backup e restauração, reversão e reaplicação da imagem passaram. O diretório de decisões reais está vazio e montado somente para leitura no worker. Prova em `benchmarks/qualification/reports/vh10-edit-preflight-v1.json`. Procedimento em `RUNBOOK_DEVELOPMENT_VPS.md`.

**Próximo aceite de VH-10.** Ligar as funções de proposta, crítica e adjudicação do OpenClaw ao lote autorizado no laboratório. Testar recusa, interrupção, custo e limite de duas rodadas, com revalidação do pacote ao aplicar e restaurar. A abstenção sem campo elegível deve continuar encerrando a execução antes do provedor. A conferência de origem das 12 figuras e as referências extras da conversão direta registradas na seção 55 seguem abertas para o fluxo com figuras. A homologação humana depende de concluir os itens já previstos de fluxo web e ensaio ponta a ponta.

## 57. Ciclo de edição com OpenClaw em laboratório (02/11)

O ensaio na VPS partiu da afiliação ausente de um IDML sintético sem ilustrações. O worker releu o trecho autorizado e vinculou o literal ao elemento do candidato e ao hash do XML. O gateway dedicado executou proponente, crítico XML, crítico editorial e adjudicador em sessões separadas. Os quatro apoiaram o mesmo candidato na primeira rodada. O catálogo do projeto estimou US$ 0,013452 para as quatro chamadas. O executor separa essa decisão da permissão de alterar o rascunho. Os testes cobriram recusa, revogação após chamada, interrupção, voto sobre outro hash, orçamento insuficiente e limite de duas rodadas. Os dois IDMLs originais voltaram a passar pela conversão e pela verificação da revisão em um container sem rede. Ambos encerraram o ciclo antes de chamar um agente.

| Ensaio | Resultado |
|---|---|
| XML candidato sintético | A validação offline passou e a afiliação original foi recuperada literalmente. |
| Aplicação e restauração com respostas formais controladas | O rascunho do laboratório avançou, reconstruiu o ZIP e voltou à revisão original. O SHA-256 do XML restaurado coincidiu com o do XML de entrada. A transação de teste foi desfeita. |
| Validação nativa do mesmo candidato | Na primeira tentativa os serviços recusaram iniciar por reserva de memória. A repetição usou os mesmos votos e bytes. O XPM concluiu com 4 bloqueios, 8 falhas fatais, 6 erros e 7 avisos. O preparo de consultas para Packtools e SPSvalidator recusou o XML por ausência do DOI do artigo. O sistema manteve a revisão original. |
| Controle com o pacote enriquecido do e20240086 | Packtools, SPSvalidator e XPM foram exercitados separadamente no pacote histórico com DOI. As contagens e hashes constam no relatório. Este controle não contém uma edição por IA. |

A liberação do provedor ficou restrita à janela de laboratório e foi encerrada. A API e o worker seguem na versão `vh10-edit-20261101-v2`, com os agentes desativados para usuários e cinco serviços IDML saudáveis. O Mapalead permaneceu ligado. Passaram 586 testes locais e os mesmos 586 no Linux. Prova em `benchmarks/qualification/reports/vh10-openclaw-edit-cycle-lab-v1.json`. O procedimento de repetição está no `RUNBOOK_DEVELOPMENT_VPS.md`.

**Próximo aceite no mesmo VH-09/10/14.** Produzir um ensaio positivo com metadados completos e DOI autêntico. Usar um artigo autorizado e uma cópia isolada em que se omita um campo recuperável do IDML, preservando o original como referência. Se houver figuras, exigir vínculos comprovados com os arquivos fornecidos. Conferir a aplicação, o ZIP e a restauração com os três validadores nativos. Depois, levar o ciclo autorizado ao fluxo web e percorrer a RC até o especialista. G-HOMOLOG segue pendente.

## 58. Correção e restauração nativas do e20240086 (03/11)

O laboratório partiu da versão canônica enriquecida do artigo com DOI autêntico. Omitiu de uma cópia somente o texto original de uma afiliação. O IDML, o XML publicado e o artigo no banco ativo foram preservados. No perfil ESA, o leitor reconhece uma sequência de números sobrescritos em trechos próprios e conserva os limites do texto de cada instituição. A hierarquia de escola e departamento continua separada quando o literal recuperado comprova o mesmo parágrafo de origem.

As cinco figuras da cópia utilizam as versões publicadas fornecidas pelo usuário. A conferência inclui manifesto, referência no XML, bytes dentro do ZIP histórico e SHA-256 do arquivo enviado. O inventário canônico conserva os 27 itens de diagramação. Os cinco gráficos destinados ao XML exigem referência exata e arquivo correspondente. Esses hashes identificam as versões publicadas. O tamanho registrado pelo InDesign diverge para os cinco JPGs de origem. O ensaio não certifica esses arquivos de vínculo.

A revisão do OpenClaw consumiu 4 chamadas e teve custo estimado de US$ 0.013303. A decisão era específica da empresa, artigo e revisão de laboratório. A edição recuperou o literal do próprio IDML. O XML corrigido e o pacote ficaram idênticos, byte a byte, aos da referência enriquecida. A restauração gerou novamente o XML e o ZIP da cópia em que a afiliação estava omitida.

| Validação nativa | Aplicação da correção | Retorno ao rascunho incompleto | Recuperação da revisão íntegra |
|---|---|---|---|
| Packtools | 5 avisos, zero erros | 1 ocorrência crítica e 6 avisos | 5 avisos, zero erros |
| SPSvalidator | 5 avisos, zero erros | 1 ocorrência crítica e 6 avisos | 5 avisos, zero erros |
| XPM bruto | 3 bloqueios, 1 fatais, 4 erros e 2 avisos | 3 bloqueios, 1 fatais, 5 erros e 2 avisos | 3 bloqueios, 1 fatais, 4 erros e 2 avisos |
| XPM após política de compatibilidade | zero erros técnicos, 2 avisos | 3 bloqueios, 1 fatais, 3 erros e 2 avisos | zero erros técnicos, 2 avisos |

A primeira tentativa de implantação parou quando a restauração da versão incompleta revelou o defeito intencional. Os votos e os hashes dessa execução foram preservados. A recuperação seguinte selecionou a última revisão íntegra previamente admitida, conferiu a linhagem e executou os três validadores de novo. O XML e o ZIP recuperados são idênticos aos do candidato aplicado. A versão íntegra recuperada ficou no banco de ensaio; o banco da aplicação permaneceu preservado. O ensaio distinguiu a capacidade de voltar a uma revisão da sua aptidão para uso.

Avisos e pendências editoriais continuam disponíveis para revisão. As decisões de avanço e de restauração dizem respeito ao rascunho do laboratório. Homologação e publicação dependem de seus próprios aceites.

A versão `vh10-reference-20261103-v2` está ativa. A qualificação passou nos 622 testes locais e Linux, no PostgreSQL isolado e nos ensaios de backup, restauração, reversão e reaplicação. O provedor foi desconectado depois do laboratório. Os cinco serviços IDML estão saudáveis e o Mapalead permaneceu ligado. Evidências em `benchmarks/qualification/reports/vh10-reference-edit-native-v1.json`.

**Próximo aceite no mesmo plano.** Integrar o ciclo qualificado ao fluxo web restrito ao artigo autorizado. O operador deve poder selecionar a revisão, iniciar a avaliação, ver as diferenças e os avisos e consultar a restauração. Percorrer então o fluxo autenticado com o perfil do especialista na RC antes de abrir G-HOMOLOG.

## 59. Avaliação e histórico pelo portal na RC (04/11)

A tela **Avaliação do XML** permite selecionar artigo e revisão, iniciar a avaliação e consultar candidatos, trechos antes/depois, custo, diagnósticos formais e histórico de restaurações. O revisor tem acesso de consulta; a execução exige permissão de operador. O teste de outra empresa recebeu 404, o perfil de revisor recebeu 403 ao tentar iniciar um job e a entrada rejeitou a tentativa de enviar uma autorização administrativa pelo formulário.

O Chrome acessou a RC isolada da VPS por túnel SSH. O operador selecionou a revisão do e20240086 e criou o job pelo portal. O worker executou quatro chamadas reais do OpenClaw, com custo estimado de US$ 0.012040, aplicou a correção literal da afiliação e revalidou o pacote. A restauração da cópia incompleta ficou bloqueada; a revisão íntegra foi recuperada e revalidada. O perfil automatizado de revisor consultou os dois resultados e comparou o XML antes/depois. Este teste não representa avaliação de um especialista humano.

O XML e o ZIP corrigidos e recuperados coincidiram com os hashes da referência enriquecida. Packtools e SPSvalidator concluíram com zero erros e cinco avisos cada. O XPM bruto manteve três bloqueios, uma falha fatal, quatro erros e dois avisos; a política de compatibilidade qualificada resultou em zero erros técnicos e dois avisos. A restauração incompleta produziu novamente o bloqueio esperado. Os relatórios brutos e as pendências editoriais permanecem preservados.

A cópia usada no preparo anterior expirou durante a pausa e foi preservada. Um novo preparo foi recusado pelo socket do antivírus durante o encerramento da varredura anterior; nenhum arquivo foi admitido sem análise. O ensaio repetido espaçou em dois segundos as sete verificações nativas. A solução permanente para envios consecutivos/concorrentes pertence a VH-11/17 e precisa de teste antes do E2E geral. Esse intervalo foi aplicado somente ao preparo do laboratório, não ao código da aplicação.

A versão vh11-web-20261103-v1 foi implantada com backup, restauração, reversão e reaplicação de imagem. Passaram 624 testes locais e 624 no Linux, com dois avisos em cada plataforma, mais PostgreSQL isolado. Cinco serviços IDML saudáveis; Mapalead e registros ativos preservados. O portal descartável foi removido antes do backup de implantação. Evidência: benchmarks/qualification/reports/vh11-web-edit-native-v1.json.

**Limite operacional.** O menu está disponível na aplicação. A execução paga ainda exige uma seleção administrativa específica por empresa/artigo/revisão e uma janela de provedor; a flag permanece falsa na instalação normal. Sem autorização ou campo elegível, o job recusa ou se abstém. Com candidato autorizado e janela fechada, informa essa condição. Uma decisão já utilizada não inicia nova cobrança. A integração qualificada cobre uma afiliação, com figuras publicadas já comprovadas. Não certifica o fluxo de qualquer IDML nem os JPGs originais de vínculo ausentes.

**Próximo aceite, dentro de VH-11/14/15/17/18.** Corrigir e testar a concorrência na varredura; concluir a ligação das fontes e catálogos ao fluxo normal; percorrer upload, conversão, avaliação/abstenção, pacote, diagnóstico e download dos dois artigos pelo portal. Conferir retenção/backup privado e fechar a lista existente de G-HOMOLOG. A documentação e o acesso destinado ao especialista entram em VH-19/20; não criar outra fase para essas pendências.

## 60. Fila limitada do antivírus e repetição dos dois pacotes (04/11)

A recusa entre arquivos consecutivos vinha de dois pontos: o socket admitia apenas uma conexão, e a trava externa permanecia ocupada até o processo encerrar, mesmo após enviar o resultado. O socket agora admite até quatro conexões. Cada entrada conserva o limite de 100 MiB e 25 segundos para transmitir o conteúdo. A espera pela trava é limitada a 130 segundos. A trava cobre somente o motor de varredura e é liberada antes da resposta, mantendo exclusão mútua com a atualização de assinaturas. Há um único motor de antivírus por vez, com os mesmos limites de memória e CPU. O cliente Unix e o serviço têm limite de 300 segundos. Falta de capacidade, timeout ou resultado indeterminado continuam sem admissão do arquivo.

O teste nativo usou um socket systemd isolado com a configuração candidata. Dois IDMLs reais foram verificados consecutivamente; três chamadas simultâneas retornaram dois arquivos limpos e o controle EICAR recusado. Não houve pausa artificial entre envios nem repetição automática de transporte. O monitor observou no máximo um motor em execução. Os testes de regressão também cobriram expiração da espera sem iniciar motor, liberação da trava após falha e recusa de saídas ambíguas.

O laboratório HTTP autenticado repetiu a releitura auditada dos dois IDMLs, os uploads dos PDFs e das 12 figuras, a conversão e o download dos ZIPs. Os arquivos dos ZIPs coincidiram byte a byte com as imagens fornecidas. Os dois pacotes enriquecidos reproduziram os hashes históricos e passaram na validação offline. O empacotamento da conversão direta continuou recusado com invalid_job_input: o ensaio usou separadamente os snapshots enriquecidos já qualificados para a comparação. Isso não encerra VH-18 nem comprova a ligação dos catálogos ao fluxo normal.

A versão vh11-scan-queue-20261104-v1 está ativa, com os novos arquivos de unidade do scanner conferidos e um arquivo limpo verificado pela API ativa. Passaram 630 testes locais (429 + 201), 630 testes Linux, PostgreSQL isolado e análise de tipos de 149 módulos. Backup, restauração, reversão e reaplicação de imagem passaram. Cinco serviços IDML saudáveis; Mapalead e registros ativos preservados. Os agentes permaneceram desligados e não houve chamada paga. Evidência: benchmarks/qualification/reports/vh11-scanner-queue-v1.json.

**Próximo aceite existente — VH-14/18.** Provisionar e ligar os catálogos autorizados ao worker por empresa/artigo/fonte, com sua proveniência e validade. Repetir a conversão a partir do upload no portal sem importar uma versão canônica pronta. Conferir os dois artigos até avaliação/abstenção, validação formal e download. O backup privado e o fechamento da RC permanecem em VH-15/17/19/20. A correção da fila de varredura desta seção está concluída; não repetir os testes já aprovados sem mudança ou falha nova.

## 61. Conversão dos IDMLs com os catálogos no portal ativo (05/11)

O operador de qualificação criou artigos na empresa **Qualificação ESA — catálogos**, enviou dois IDMLs, dois PDFs e doze figuras pelo navegador e enfileirou as conversões. O worker leu os IDMLs enviados e aplicou os catálogos selecionados para a empresa, o artigo, o hash do arquivo e o perfil ESA. A revisão canônica de cada job nasceu dessa conversão. Os ensaios finais reutilizaram os mesmos uploads verificados pelo ClamAV em novos registros de artigo para preservar os primeiros resultados.

Na primeira execução, a conferência do XML isolou três diferenças em relação aos pacotes qualificados. Duas páginas bibliográficas tinham mudado e uma consulta institucional devolveu HTTP 403. O e20240135 teve uma ocorrência crítica em cada validador moderno. A repetição diagnóstica do Packtools reproduziu o hash do relatório e identificou a regra de estado ausente na afiliação. A declaração oficial da Easwari Engineering College na página 2 confirmou instituição, cidade e estado. A regra aceita a cópia conferida do PDF, vinculada ao hash do arquivo e ao trecho do endereço. As páginas SAAE e OMS foram conferidas com as versões anteriores pelos respectivos títulos e origens. A página da OMS também preservou a data e o link do mesmo relatório. Os hashes renovados foram acrescentados apenas às duas regras correspondentes. As referências mantêm o texto do IDML e a trilha registra os bytes efetivamente usados. [Declaração da instituição](https://srmeaswari.ac.in/wp-content/uploads/2025/03/AICTE-MD-Submitted-in-2024-2025.pdf)

| Artigo | Catálogos | Figuras / fórmulas / referências | Packtools | SPSvalidator | XPM pela política |
|---|---:|---|---|---|---|
| esa-e20240086 | 9 | 5 / 17 / 52 | 5 avisos | 5 avisos | 2 avisos |
| esa-e20240135 | 6 | 7 / 43 / 35 | 5 avisos | 5 avisos | 3 avisos |

Os três validadores concluíram nos dois artigos. Packtools e SPSvalidator tiveram zero bloqueios, ocorrências críticas e erros. O XPM teve zero erros técnicos após a aplicação da política documentada. As contagens brutas estão no relatório. XML e ZIP baixados pelo navegador coincidiram byte a byte com os arquivos históricos qualificados. A comparação com os XMLs publicados conferiu as quantidades de figuras, fórmulas, afiliações e referências. Os dois PDFs e as doze imagens coincidiram com as entradas verificadas.

Os jobs de avaliação se abstiveram e registraram zero chamadas de IA. A tela Jobs oferece os downloads do XML da conversão e do ZIP de avaliação com o nome do arquivo. A lista de uploads é atualizada ao abrir a tela. O primeiro ensaio precisou recarregar essa lista para localizar um ZIP recém-gerado. O ensaio da versão final baixou ambos pelo resultado do job. O diagnóstico da conversão apresenta o número de catálogos aplicados e o resultado técnico contém a validade e os hashes. O worker verifica a autorização novamente antes de persistir a conversão.

O primeiro diagnóstico de falha de login do ensaio exibiu uma senha temporária. A credencial foi invalidada e substituída. O teste passou a registrar somente o status HTTP em falhas de login. A conta do proprietário recebeu acesso de revisor à empresa de qualificação e a conta temporária do ensaio foi desativada. Os registros com título **Fontes conferidas** identificam as versões finais. O operador técnico provisionou decisões específicas durante o ensaio. A interface de entrada ainda exige relacionar alguns identificadores de artigo, revisão e anexos. Esse ponto de usabilidade pertence a VH-11/13.

Release vh14-catalog-portal-20261105-v1. Passaram 764 testes locais e 764 no Linux, com quatro avisos em cada plataforma, além do PostgreSQL isolado e da análise de tipos. Reversão e reaplicação de imagem passaram. O backup final foi restaurado em destinos isolados com conferência de banco, artefatos e dados privados de catálogos e autoridades, incluindo permissões de arquivo. Cinco serviços IDML saudáveis. Evidências em benchmarks/qualification/reports/vh14-catalog-web-qualified-v1.json.

**Próximo aceite.** Concluir o percurso operacional de VH-11/13 com escolhas por nome e associação dos arquivos ao artigo, conferir o roteiro com perfil de revisor e fechar os critérios restantes de VH-17/19/20 antes do convite ao especialista.

## 62. Entrada por nome e conferência do percurso do revisor (06/11)

O operador escolheu pelo título os artigos **ESA · Fontes conferidas · e20240086** e **ESA · Fontes conferidas · e20240135** na empresa de qualificação. Cada revisão informa o IDML de origem. O operador escolhe o PDF e as imagens entre os uploads da empresa verificados pelo antivírus. Ao repetir um pacote, a tela recupera os anexos e a ordem do último pacote concluído daquele artigo, revisão e IDML. A persistência do vínculo ocorre ao enfileirar o job. A primeira montagem exige a seleção dos anexos pelo operador.

Na VPS, a conta com papel de operador enfileirou duas conversões e duas montagens pelo navegador usando os uploads já verificados na seção 61. Em sessão independente, a conta com papel de revisor escolheu os artigos pelo título, consultou o IDML, o PDF e as listas de cinco e sete imagens, abriu os diagnósticos e as avaliações existentes e baixou os dois ZIPs. Os XMLs e ZIPs coincidiram byte a byte com as referências qualificadas. Packtools e SPSvalidator completaram cada validação com cinco avisos e zero ocorrências críticas ou erros. O XPM teve dois e três avisos após a política de compatibilidade. A API recusou com HTTP 403 o POST autenticado do revisor para criar um job. O ensaio consultou as abstenções já registradas. As três contas temporárias foram desativadas após o teste.

A seleção por nome também foi exercitada em navegador com respostas simuladas para um artigo novo, troca de empresa e perda da resposta ao envio. A repetição reutilizou a chave do primeiro pedido. Testes de integração conferiram a origem por revisão, arquivos homônimos, quarentena e recusa de acesso cruzado. Passaram 766 testes direcionados em cada plataforma, quatro avisos por plataforma, PostgreSQL isolado e tipagem de 150 módulos. A implantação verificou 351 arquivos por contêiner de aplicação, reversão e reaplicação. A verificação operacional V-10 foi atualizada para a tela vigente. Os treze cenários foram requalificados e a adulteração do relatório foi rejeitada.

**Antes de convidar o especialista.** Em VH-17, executar a regressão integral sobre a candidata e reconstruir as evidências de segurança V-09 e robustez V-11. Os testes internos desses dois verificadores passaram na execução de 06/11, mas ambos recusaram seus relatórios publicados. Em VH-09/13/18, consolidar as contraprovas e o aceite de correção, restauração e revalidação da versão final. Para novas consultas públicas do piloto, a empresa precisa de uma decisão válida emitida por um administrador ativo. O ensaio reativou temporariamente o emissor da autorização anterior. A consulta e o download dos pacotes já concluídos continuam disponíveis. Fechar VH-19/20 com a identidade do especialista, o roteiro, a versão congelada e a decisão G-HOMOLOG. O teste técnico usou contas de ensaio.

[Roteiro do revisor](ROTEIRO_REVISOR_XML.md) · [Evidência da execução](../benchmarks/qualification/reports/vh11-named-inputs-v1.json)

## 63. Regressão integral da candidata e conferência na VPS (09/11)

A versão **vh17-regression-20261109-v1** passou nos mesmos 3.244 testes no Windows e no Linux da VPS, com zero falhas, erros e testes pulados. A cobertura atingiu 90,16% e 90,15%, respectivamente. No Windows, a execução foi dividida em três grupos e a cobertura foi combinada. Os identificadores de todos os casos coincidiram com a execução integral do Linux. O código passou no Ruff e na análise de tipos dos 150 módulos. Os 42 comandos de qualificação da configuração de CI foram executados localmente. O repositório estava sem remoto configurado para disparo no GitHub Actions. O limite do workflow passou de 15 para 60 minutos. A suíte integral do Windows havia levado 30 minutos em execução sequencial. A etapa de implantação também passou em 865 testes Linux e no ensaio isolado de PostgreSQL.

**XML e validadores.** Os IDMLs e os catálogos históricos reproduziram os dois XMLs de referência com a alteração de DOCTYPE já qualificada. O PDF e as imagens de cada pacote coincidiram com as entradas. O ensaio de DOCTYPE reconstruiu seis variantes e verificou os relatórios nativos preservados. O XPM executou novamente os dois artigos e duas entradas com defeitos. Pela política de compatibilidade, os originais ficaram com zero erros técnicos e dois ou três avisos. A falta do título do periódico e o XML malformado mantiveram os bloqueios. Em outro ensaio, Packtools e SPSvalidator processaram pacotes históricos com defeitos conhecidos e repetiram seus achados. Foram consultadas fontes públicas vigentes com autorização restrita ao laboratório. Cinco contraprovas cobriram empresa e artigo incorretos, XML modificado, revogação e vencimento.

**Segurança, dados e fila.** V-09, V-10 e V-11 passaram com evidências vinculadas ao código. Foram verificados os 13 controles comportamentais de mutação e a recusa de comprovantes adulterados. Os testes de cancelamento, tamanho e integridade de uploads agora exercitam a interface HTTP e a chave real do armazenamento. O ZIP sintético do teste XPM ganhou uma data de entrada fixa. No Windows, a hora de criação podia mudar entre duas leituras e alterar o hash de um pacote de conteúdo idêntico. O teste cobre essa troca de hora e a alteração intencional do conteúdo.

O laboratório de fila reúne API, worker e executor de testes em um contêiner. Na primeira medição, o limite de 224 MiB causou encerramento por falta de memória. Com 320 MiB para esses processos e 432 MiB para o laboratório completo, os 24 jobs passaram nos quatro cenários de fila. Os serviços ativos de API e worker têm limites individuais de 256 MiB. Os ensaios de upload HTTP, ingestão, quotas e volume passaram, incluindo arquivos de 100 MiB, expansão de 500 MiB e 10 mil entradas. As medições dizem respeito à VPS e aos limites do laboratório.

**Implantação e uso.** Nos seis arquivos ajustados pelo formatador, as árvores sintáticas coincidiram com as da versão anterior. O portal entregou os mesmos bytes de HTML, CSS e JavaScript. A implantação na VPS incluiu backup, restauração isolada, reversão da imagem e reaplicação. Uma conta temporária de revisor conferiu os diagnósticos e as abstenções, baixou os dois ZIPs e verificou o XML interno. A API recusou a criação de jobs por essa conta com HTTP 403. A conta foi desativada e os cinco serviços IDML passaram na conferência final. O backup de fechamento foi restaurado com conferência de conteúdo e permissões dos catálogos e autoridades.

**Próximo aceite.** Na candidata implantada, percorrer o ciclo autorizado de correção antes da avaliação humana e conferir o XML alterado, o diagnóstico, a restauração e a revalidação do pacote restaurado. Para o piloto com novas consultas, vincular as decisões de fontes a um administrador ativo e conferir a validade por artigo. Registrar o fechamento de VH-09/13/18 e a decisão de G-HOMOLOG antes do convite individual em VH-19/20.

[Relatório da regressão](../benchmarks/qualification/reports/vh17-regression-v1.json) · [Roteiro para o especialista](ROTEIRO_REVISOR_XML.md)


## 64. Permissões operacionais e restauração pela web (11/11)

Entrega operacional de VH-09/13/18 na versão `vh18-web-access-20261111-v1`. O proprietário autorizou os acessos necessários aos usuários web e decidiu definir o administrador do piloto depois. A conta existente permanece administradora de sua empresa e revisora da empresa de qualificação. A política permite delegar a operadores ativos a autorização de consultas públicas apenas nas empresas selecionadas. Revisores consultam os resultados e baixam arquivos; sua função permanece sem criação de jobs.

As permissões provisionadas pelo proprietário são específicas para empresa, artigo, IDML e perfil ESA, duram até trinta dias e registram a decisão anterior. Uma revogação posterior pelo portal prevalece sobre a permissão provisionada. A montagem do arquivo de política na API é somente leitura. Consultas públicas não autorizam publicação nem substituem a autorização específica de uma correção por IA.

O ensaio real de 10/11 aplicou uma correção de afiliação em cópia separada do e20240086. Foram quatro chamadas OpenClaw, com custo de US$ 0,013666. O XML e o ZIP corrigidos coincidiram com a referência qualificada. A primeira reversão encontrou os validadores indisponíveis por reserva de memória. A recuperação posterior concluiu os validadores modernos com zero erros/ocorrências críticas e cinco avisos; XPM pela política com zero erros e dois avisos. O artigo original foi preservado.

A implementação acrescenta comandos de reverter e recuperar na avaliação web. A solicitação usa a revisão e versão vigentes, a promoção comprovada e o PDF registrado. A indisponibilidade de um validador impede a troca da revisão e permite nova tentativa. Um XML efetivamente inválido, com validações concluídas, permanece identificado como bloqueado. Downloads de XML e ZIP de cada validação ficam disponíveis no histórico.

A implantação concluiu backup/restauração, reversão e reaplicação da imagem, 885 testes Linux e PostgreSQL isolado. Em 11/11, o operador executou os dois comandos na interface ativa. A reversão gerou novamente um crítico e seis avisos por validador moderno. A recuperação concluiu com zero críticos/erros e cinco avisos por ferramenta; XPM pela política com zero erros e dois avisos. Todos os validadores nativos concluíram nas duas operações. XML e ZIP coincidiram byte a byte com as respectivas referências. O artigo original permaneceu intacto.

O revisor consultou o histórico, o trecho alterado e os diagnósticos e baixou o ZIP tanto pela avaliação quanto pela seleção por nome. Sua tentativa de criar um job recebeu HTTP 403. As três contas temporárias estão desativadas. Os três artigos de exemplo mantêm consultas autorizadas até 10/12/2026; a empresa do proprietário também tem delegação a operadores, sem permissões artificiais para artigos ainda inexistentes. A escolha do administrador do piloto permanece adiada. O backup final restaurou banco, artefatos e 179 arquivos privados, incluindo política de acesso, decisão do proprietário e catálogos, com conteúdo, proprietário e permissões conferidos. Cinco serviços IDML saudáveis; os demais contêineres foram preservados.

Os ensaios de fila e volume foram repetidos porque a versão do worker mudou. Ambos passaram. A suíte integral no Windows passou nos 3.246 testes, com cobertura de 90,16%. Os 42 comandos de verificação do workflow passaram. Fechamento registrado em 14/11/2026. Evidências em `benchmarks/qualification/reports/vh18-web-access-v1.json`, `vh18-queue-observation-v1.json` e `vh18-volume-observation-v1.json`.

**Próximo trabalho delimitado, dentro dos itens existentes.** Fechar VH-10/14 para a disponibilidade operacional da IA no piloto: atualmente uma correção paga exige decisão específica por revisão e uma janela do provedor, que permanece fechada fora do ensaio. As consultas públicas e os comandos de recuperação estão disponíveis na aplicação. A autorização de consultas não libera edição científica ou publicação. Após resolver esse limite de operação e conferir o roteiro final, congelar a versão e registrar G-HOMOLOG em VH-19/20. A identidade do especialista permanece necessária para criar seu acesso individual. Os avisos editoriais e o aceite SciELO permanecem distintos da aprovação técnica desta entrega.

## 65. Autorização de correção por IA no portal

A release `vh19-web-provider-20261114-v1` passou a atender o piloto na VPS em 14/11/2026. O operador ou administrador da empresa seleciona a revisão em **Avaliação do XML** e confirma **Autorizar correção por IA**. O worker usa o último pacote concluído para aquele artigo, IDML e revisão. A autorização de duas horas identifica o emissor, o campo, o trecho do IDML e o PDF do pacote. O worker confere o papel ativo do emissor durante as chamadas e antes da promoção. A chave existente permanece no gateway dedicado. O provedor continuava ativo na conferência de 16/11.

O ensaio usou uma cópia controlada do e20240086 com uma afiliação ausente. A preparação da cópia foi técnica. A seleção do pacote, a autorização de edição, a revalidação, a comparação e o download percorreram o portal ativo. O operador autorizou a edição no navegador sem instalar arquivos de permissão por artigo no servidor. As quatro chamadas custaram US$ 0,012069 segundo a telemetria do sistema. Os agentes sustentaram a recuperação do texto da afiliação da University of Tokyo. Packtools e SPSvalidator terminaram com cinco avisos cada e zero bloqueios, erros ou ocorrências críticas. O XPM bruto registrou três bloqueios, uma falha fatal, quatro erros e dois avisos. A política de compatibilidade qualificada resultou em zero erros técnicos e dois avisos.

O revisor baixou o XML e o ZIP. Os dois arquivos coincidiram byte a byte com as referências qualificadas. A segunda avaliação da revisão corrigida se absteve antes de qualquer chamada paga. A revisão do artigo original foi preservada e as contas temporárias estão desativadas. A operação qualificada cobre a recuperação literal de uma única afiliação elegível por revisão no perfil ESA. As cinco imagens são as versões publicadas autorizadas.

Passaram 134 testes direcionados no Windows, 886 no Linux, os testes isolados de PostgreSQL e os verificadores V-09/10/11. Os 42 comandos de verificação do workflow passaram, incluindo fila e volume no código desta release. O backup final restaurou o banco, os artefatos e 197 arquivos privados. A implantação exercitou reversão e reaplicação da imagem. A regressão integral da versão congelada pertence ao aceite final. O próximo aceite existente é o congelamento da versão com a conferência do roteiro final e a decisão G-HOMOLOG. O convite individual depende da identificação do especialista. O resultado técnico do ensaio e as verificações finais estão em `benchmarks/qualification/reports/vh19-web-provider-v1.json`.


## 66. Abertura do piloto para o especialista em 16/11/2026

O titular indicou o destinatário e autorizou o convite. O portal de homologação atende em
[HTTPS na VPS](https://143.95.214.8:8443/app). A conta individual tem papel de revisor
em **Qualificação ESA — catálogos**. O e-mail enviado contém um link de primeiro acesso
de uso único, válido por 24 horas, e o roteiro para os dois artigos. O primeiro login e
o parecer editorial do especialista aguardam sua participação.

A versão de referência da sessão usa a API `vh19-web-recovery-20261116-v2` e o worker
`vh19-web-provider-20261114-v1`. Em um navegador externo, uma conta revisora de ensaio
entrou pela URL pública, consultou o diagnóstico e a abstenção da IA e baixou os dois ZIPs.
O XML e o ZIP de cada artigo coincidiram por SHA-256 com as referências qualificadas.
A tentativa de iniciar conversão com o papel de revisor retornou HTTP 403 nos dois casos.
Uma conta descartável também concluiu a troca de senha e o login pela URL pública.
As contas de ensaio foram desativadas.

**Decisão de escopo.** O especialista pode iniciar agora a avaliação do conteúdo,
das figuras e da apresentação dos diagnósticos. Registrar divergências conforme o
[roteiro](ROTEIRO_REVISOR_XML.md). Corrigir de imediato problemas de acesso, isolamento,
download ou integridade que impeçam esse percurso. A expansão para outros periódicos,
artigos inéditos e novas ações de IA pode aguardar os apontamentos.
A regressão integral da composição final, a consolidação dos itens abertos do checklist
e o aceite G-HOMOLOG permanecem no fechamento formal. O resultado bruto do XPM e as
exceções da política seguem disponíveis para o parecer humano. A publicação depende
da decisão editorial própria.


## 67. Envio e acompanhamento de novos IDML pelo especialista

A mesma conta do convite recebeu o papel operacional na empresa **Homologação ESA — novos artigos**.
A empresa dos dois exemplos mantém o papel de revisão. Na nova empresa o operador pode decidir,
por artigo e pelo prazo escolhido, sobre as consultas externas do perfil ESA.

O ensaio no portal público usou uma conta temporária com o mesmo papel. No novo envio de
e20240135, o IDML, o PDF e sete figuras foram recebidos. A conversão terminou e a autorização
de fontes pelo portal funcionou. O empacotamento ficou bloqueado: o XML da nova conversão
ainda referenciava arquivos de equações, entre eles `ESA_2024135_Eq03.pdf`, ausente no conjunto
enviado. Esse novo artigo não recebeu os catálogos privados dos exemplos já qualificados.
O job apresentou `invalid_job_input`; o nome do primeiro arquivo faltante foi confirmado
na conferência técnica. O XML da conversão fica disponível no job concluído.

Em um segundo envio, com IDML, PDF e figura sintéticos compatíveis entre si, a conta
criou o artigo, enviou os arquivos, acompanhou os jobs de conversão e pacote, abriu o
diagnóstico e baixou um ZIP com XML e figura. O ensaio confirma o percurso do usuário.
A decisão editorial depende dos achados dos validadores e do especialista.
A conta temporária foi desativada. O roteiro do revisor contém as etapas no navegador.
