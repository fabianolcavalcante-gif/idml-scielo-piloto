# Plano mestre de validação XML e homologação final

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

Controle da primeira entrega ao especialista em 2026-10-01: vinte itens e critérios
de término em `HOMOLOGATION_VH1_DELIVERY.md` (ADR-017). Este plano mantém os requisitos
de validação/produção, mas não reabre a sequência histórica como pré-requisito novo.

Revisão de escopo 2026-10-01: ADR-016 torna obrigatório o ciclo de correções
automáticas restritas H1-A1–A5 antes de G-HOMOLOG, com avaliação humana ao final,
sem dispensa de validação formal. Ver `AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`.
Implementação/qualificação pendentes; relatórios assistivos históricos não autorizam
aplicação automática retroativa nem publicação.

Estado consolidado em 2026-10-30: worker com validadores modernos/XPM e brokers
supervisionados implantados; dois artigos exercitados em job real e banco isolado,
sem erros técnicos derivados, mantendo avisos/consultas e publicação bloqueada.
Ciclo IA, fontes por artigo e fluxo web/E2E ainda pendentes. A sequência vigente
é a seção 52 de `HOMOLOGATION_VH1_DELIVERY.md`; os incrementos abaixo preservam
o histórico e não devem ser lidos como estado atual dos executores.

Data inicial: 2026-09-01. Revisão de sequência: 2026-09-25.
Estado: **PREPARAÇÃO PRIORITÁRIA DA HOMOLOGAÇÃO FUNCIONAL; V-12 INCOMPLETA**.

Em 2026-09-28, H1-01 integrou catálogos qualificados por empresa/artigo/origem ao worker.
Dois artigos reproduziram localmente os hashes qualificados via `process_job`; não houve deploy
nem execução externa. Próximos H1-02/H1-04 e XPM. Ver `docs/H1_JOB_ENRICHMENT.md`.

Primeiro incremento H1-02/H1-04: o job de pacote registra estado formal e ausência dos
executores; aprovação editorial não o altera. Ainda não executa validadores externos.
Próximo conectar executores isolados; ver `docs/H1_FORMAL_VALIDATION_STATES.md`.

## 1. Objetivo

Entregar primeiro uma versão funcional de homologação (VH), validada formalmente e segura para
testes restritos do especialista; concluir depois/em paralelo a prontidão completa de produção,
com revalidação humana final. Seguir `docs/EXPERT_TEST_READINESS_PLAN.md` e ADR-015. Codex, agentes
OpenClaw e validadores determinísticos devem encontrar, classificar e corrigir o máximo possível de
defeitos, para que o especialista concentre seu trabalho em decisões editoriais e exceções reais.

"Perfeito" significa, neste plano, zero defeito conhecido bloqueador ou crítico, nenhuma alteração
sem evidência, validações reproduzíveis e todos os riscos residuais declarados. Não significa assumir
que agentes de IA substituem a homologação humana ou que um corpus limitado prova generalização.

## 2. Governança e limites

- O desenvolvimento pode avançar até a prontidão de produção sem baseline humano intermediário.
- Gates técnicos podem ser aprovados por evidência automatizada e multiagente.
- A ativação para tráfego editorial real exige homologação e aceite do especialista em XML.
- Nenhum agente edita diretamente o XML final ou possui autoridade de release.
- Toda proposta permanece vinculada a evidência, schema, versão de prompt/modelo e custo.
- Discordância entre agentes, evidência insuficiente ou baixa confiança resulta em abstenção.
- Regras determinísticas, validadores formais e políticas de release prevalecem sobre agentes.
- Resultados de IA são evidência técnica provisória; não são baseline humano.
- A versão entregue ao especialista deve estar congelada e ser reproduzível.
- G-HOMOLOG permite avaliação inicial antes de G7-T/G8-RC; não dispensa validação formal,
  segurança, backup/restore atual, rollback e limites mínimos. Não autoriza produção.

## 3. Ambientes e conjuntos de dados

### 3.1 Ambientes

1. **Local/CI:** testes unitários, contratos, propriedades, fuzz e golden tests sem segredos.
2. **VPS de desenvolvimento:** integração, OpenClaw controlado, desempenho e recuperação, com os
   serviços atuais isolados e protegidos.
3. **Versão funcional de homologação:** ambiente controlado, acesso restrito e limitações
   declaradas; sem tráfego editorial real. A RC final terá configuração equivalente à produção.
4. **Produção:** somente após o Gate Humano Final e rollout gradual aprovado.

### 3.2 Particionamento do corpus

- `development`: exemplos usados para desenvolver regras e corrigir defeitos.
- `regression`: casos congelados que impedem o retorno de defeitos corrigidos.
- `adversarial`: entradas malformadas, ambíguas, extremas e com prompt injection.
- `holdout-ai`: casos ocultos dos agentes proponentes, usados pelo avaliador automático.
- `holdout-human`: artigos nunca usados em desenvolvimento, reservados ao especialista.

Cada item deve registrar hash, origem, autorização, versão do profile e regras de acesso. O corpus
ESA atual pode iniciar `development`, `regression` e perturbações adversariais, mas não deve ser o
único fundamento da homologação final.

## 4. Arquitetura da validação multiagente

Cada caso será avaliado em sessões separadas, sem compartilhar raciocínio privado:

1. **Proponente:** produz somente proposta tipada com evidência e confiança.
2. **Crítico XML:** procura perda textual, estrutura inválida, invenção e violação SPS/JATS.
3. **Crítico editorial:** procura inconsistências semânticas em metadados, autoria, referências e
   relações entre elementos.
4. **Adjudicador:** recebe entradas e saídas estruturadas, registra concordância ou abstenção e não
   pode aplicar mudanças.
5. **Juiz determinístico:** executa schemas, invariantes, hashes, métricas, validadores e política de
   release. Sua reprovação não pode ser anulada pelos agentes.

Sempre que possível, crítico e adjudicador devem usar versões/prompts independentes. Concordância de
agentes com a mesma origem não será considerada independência estatística; falsos consensos serão
medidos explicitamente.

## 5. Catálogo obrigatório de testes

### 5.1 Responsabilidade de execução

| Família | Executor primário antes da RC | OpenClaw ao vivo | Evidência principal |
|---|---|---:|---|
| V-01 | Codex + verificadores determinísticos | Não | manifestos e hashes |
| V-02 | Codex + suíte de segurança | Não | casos negativos e isolamento |
| V-03 | Codex + críticos OpenClaw | Quando houver ambiguidade | métricas de fidelidade |
| V-04 | Codex + property tests | Não | invariantes e regressões |
| V-05 | Codex + builder/validators | Não | XML e diffs estruturais |
| V-06 | Codex + validadores formais | Não | relatórios JATS/SPS/Packtools/XPM |
| V-07 | Codex + críticos/adjudicador OpenClaw | Sim, nos casos semânticos | métricas e diffs semânticos |
| V-08 | Agentes OpenClaw sob controle do Codex | Sim | propostas, críticas e abstenções |
| V-09 | Codex + testes automatizados de segurança | Não, salvo prompt injection | relatório de segurança |
| V-10 | Codex + automação de interface/API | Opcional e controlado | trilha ponta a ponta |
| V-11 | Codex + fuzz/property/mutation tools | Não | seeds, mutantes e regressões |
| V-12 | Codex + telemetria da VPS | Sim, em janelas orçadas | capacidade, custo e latência |
| V-13 | Codex + automação de recuperação | Não, salvo falha do provider | RPO/RTO e restore |
| V-14 | Codex + auditoria automatizada | Não | métricas, logs e reconstrução |
| V-15 | Codex + pipeline de deploy | Não | smoke, rollback e runbooks |

O especialista humano executará a homologação posterior sobre o `holdout-human`. Antes disso,
Codex responde por planejar, executar, interpretar e documentar os testes; os agentes OpenClaw são
avaliadores restritos, não autoridades do gate.

### V-01 — Proveniência e integridade do corpus

- conferir hashes de IDML, XML, PDF, planilhas, HTML e assets;
- validar autorização, classificação e segregação dos conjuntos;
- detectar arquivo trocado, truncado ou contaminado;
- impedir que o holdout apareça em prompts, fixtures ou logs;
- provar reprodução do mesmo manifesto em local, CI e VPS.

Aceite: 100% dos artefatos rastreáveis e nenhum conteúdo restrito versionado ou exposto.

Evidência: seis manifestos e 21/21 artefatos privados verificados; catálogo sem duplicação ou
contaminação entre splits; holdout ausente de prompts, testes e benchmarks executáveis; fingerprint
canônico reproduzido localmente e na VPS sem rede. Relatório:
`benchmarks/qualification/reports/v01-corpus-integrity-v1.json`.

### V-02 — Segurança da ingestão IDML

- ZIP Slip, symlink, arquivo duplicado e nomes Unicode conflitantes;
- limite de entradas, tamanho expandido, taxa de compressão e profundidade;
- XML externo, DTD externa, entity expansion e conteúdo binário inesperado;
- IDML incompleto, corrompido, com stories órfãos ou referências quebradas;
- cancelamento, timeout e limpeza de temporários.

Aceite: entrada perigosa falha fechada, sem escrita fora do job e sem perda de disponibilidade.

Evidência: 26/26 casos sintéticos e 6/6 pacotes reais aprovados; ZIP/XML validados antes do parser;
referências incompletas classificadas sem falha silenciosa; cancelamento, limites, limpeza de
temporários e indisponibilidade do scanner testados. Gate reproduzido na VPS sem rede e sem corpus
privado. Relatório: `benchmarks/qualification/reports/v02-ingestion-security-v1.json`.

### V-03 — Leitura e fidelidade do IDML

- ordem de leitura por stories, threads, páginas e coordenadas;
- sobrescrito, subscrito, itálico, negrito, links, caracteres especiais e espaços Unicode;
- parágrafos vazios, quebras de linha, tabs, soft hyphen e nonbreaking spaces;
- tabelas com spans, células vazias, notas, listas e conteúdo ancorado;
- imagens, legendas, créditos, equações, notas e material suplementar;
- estilos conhecidos, desconhecidos, ausentes e combinados.

Aceite: nenhuma perda textual não autorizada e toda normalização explicada por regra versionada.

Evidência: o gate independente reconstituiu exatamente 209/209 stories dos seis IDMLs autorizados,
sem emitir conteúdo restrito. O parser segue a ordem de spreads do `designmap.xml`, combina página,
coluna, coordenadas e thread, preserva propriedades diretas de caractere e parágrafo, notas,
hiperlinks, tabelas e vazios. A normalização canônica permite apenas hyperlinks `http`, `https` e
`mailto`; esquemas inseguros permanecem no Raw, são convertidos em texto sem link e geram revisão.
Negrito, itálico, combinações, sobrescrito, subscrito, listas e footnotes possuem regressão JATS.
Relatório: `benchmarks/qualification/reports/v03-idml-fidelity-v1.json`.

### V-04 — Canonical Article Model

- schemas, invariantes, IDs únicos e referências internas resolvidas;
- `RichText.plain` coerente com `inlines` após qualquer patch;
- autores, ORCID, afiliações e correspondência sem associação cruzada indevida;
- seções, listas, citações, notas, figuras, tabelas e referências com cardinalidade correta;
- migrations de versões anteriores e round-trip de serialização;
- property tests para operações idempotentes e ordem estável.

Aceite: 100% dos modelos candidatos válidos e nenhuma referência interna pendente silenciosa.

Evidência: Raw Article 1.3.0 e Canonical Article 1.2.0 publicados com schemas preservando as versões
anteriores e migrations explícitas. O gate rejeitou 13 classes de grafo inválido, aprovou 128 casos
de propriedade Unicode, migrou as duas versões imediatamente anteriores e confirmou round-trip
determinístico nos seis IDMLs autorizados. Estilos desconhecidos viram placeholders auditáveis,
sem definição inventada; células possuem identidade estável. Relatório:
`benchmarks/qualification/reports/v04-domain-model-integrity-v1.json`.

### V-05 — Construção XML JATS/SPS

- XML well-formed e encoding UTF-8;
- namespaces, declaração, ordem, cardinalidade e atributos permitidos;
- front, body, back e subartigos quando aplicável;
- metadados do periódico e artigo, idiomas, datas, licenças e identificadores;
- contribuintes, afiliações, notas de autor e correspondência;
- referências, DOI, links, citações no texto e `xref`/`rid`;
- figuras, tabelas, equações, notas, listas e assets;
- escaping, entidades, caracteres invisíveis e conteúdo misto;
- saída determinística para a mesma entrada e configuração.

Aceite: zero erro de formação, zero referência quebrada e XML determinístico.

Evidência: o builder produz declaração UTF-8 e DOCTYPE JATS Publishing 1.3 fixos, namespaces
XLink/MathML, metadados editoriais, autoria/ORCID/correspondência, afiliações/ROR, datas, licença,
financiamento, back matter, referências mistas e estruturadas e `xref` com tipo derivado do alvo.
O Canonical Article 1.3.0 passou a levar spans de tabela até `rowspan`/`colspan`, com migration
explícita desde 1.2.0. Caracteres invisíveis perigosos são preservados no modelo auditável e
removidos somente na serialização XML. O gate rejeitou 13 mutações negativas e confirmou saída
byte a byte determinística; o ESA real passou JATS/SPS, com 13 spans e zero referência quebrada.
Os cinco RBEdu permaneceram contraste explícito de profile, sem adaptação de regras. Relatório:
`benchmarks/qualification/reports/v05-jats-construction-v1.json`.

### V-06 — Validadores formais e regras editoriais

- validar contra a versão JATS/DTD e o profile SPS fixados;
- executar Packtools e XPM quando aplicável;
- testar regras internas equivalentes para execução offline;
- registrar versão, comando, ambiente, saída sanitizada e hashes;
- transformar cada defeito confirmado em fixture de regressão;
- testar atualização e rollback de versões dos validadores.

Aceite: zero erro bloqueador ou crítico; warnings somente com justificativa e aceite explícitos.

Evidência de qualificação: Packtools 4.17.2 e 4.16.10 e SPSValidator 0.3.0 em duas revisões foram
fixados em quatro imagens imutáveis e executados sem rede, como usuário sem privilégio e em
filesystem read-only. O gate V-06 aprovou contratos positivo/negativos, hash/perfil/versão,
sanitização, limites, atualização/rollback e quatro execuções externas sem exceções. O Canonical
Article 1.4.0 passou a representar os metadados formais confirmados durante o teste. Um falso
positivo crítico de afiliação do extrator de contribuintes externo foi reproduzido e permanece
visível, sem waiver de release. O XPM histórico 4.0.096 é SPS 1.9 e não atesta o candidato SPS 1.10;
a execução definitiva continua pendente do worker Windows dedicado. Assim, os validadores estão
qualificados, mas nenhum candidato XML foi aprovado por esta evidência.
Relatório: `benchmarks/qualification/reports/v06-formal-validators-v1.json`.

### V-07 — Fidelidade e comparação com referências

- Text Fidelity por região e por tipo de conteúdo;
- acurácia de metadados, autores, afiliações, referências e cross-references;
- comparação estrutural consciente de ordem e sem exigir igualdade byte a byte indevida;
- diff semântico entre XML candidato, XML aprovado e conteúdo fonte;
- detecção de omissão, duplicação, deslocamento, invenção e normalização indevida;
- renderização/inspeção visual quando PDF ou HTML forem evidência relevante.

Aceite: 100% dos campos críticos corretos; nenhuma omissão/invenção; divergências não críticas
classificadas e rastreáveis.

Estado em 2026-09-10: comparador e gate de mutações qualificados. Após quatro lotes corretivos,
estrutura, corpo, referências, figuras, tabelas, 17 fórmulas, quatro notas e mídia atingiram os
critérios. Fórmulas visuais, enriquecimentos ausentes no IDML e diferenças em que fonte/perfil têm
precedência sobre o XML histórico são aceitos somente por catálogos content-addressed, hashes exatos
e revisão humana final obrigatória. O candidato real terminou com zero bloqueios; qualquer mudança
de hash, posição, contagem ou alvo falha fechado. Relatório content-safe:
`benchmarks/qualification/reports/v07-semantic-fidelity-v2.json`.

Reabertura em 2026-09-11: um artigo até então não usado no desenvolvimento confirmou que o
comparador bloqueia corretamente candidatos com perda, mas também revelou falta de generalização
do pipeline. O candidato e20240135 teve 108 bloqueios semânticos, 38/39 cross-references, figuras
sem os sete assets finais, 40 fórmulas gráficas contra 43 MathML, 18 contra 26 seções e zero das sete
notas em `fn`. O Packtools 4.17.2 registrou 108 críticos e 79 erros, e o pacote falhou por ativo
inexistente. Portanto, o mecanismo V-07 continua qualificado, mas seu estado de corpus volta a
**REQUALIFICAÇÃO**. O plano obrigatório antes de V-12 é
`docs/PHASE_7_CORRECTIVE_E20240135.md`.

Progresso em 2026-09-14: G7C-02 aprovou os domínios `figures` e `media` com precisão, recall, F1 e
fidelidade 1,0. As sete figuras possuem `graphic` e vínculo exclusivo, a ordem global é 1–7, a seção
artificial foi removida e os sete JPGs finais foram resolvidos deterministicamente pelo
`PackageBuilder`.

Progresso em 2026-09-15: G7C-03 aprovou exatamente 43 fórmulas, sendo 32 inline e 11 display, com
zero fórmula gráfica no XML. O catálogo privado foi produzido a partir de 43 recortes autenticados
do PDF e 43 decisões multiagente aceitas para revisão humana; os dois críticos somaram 86 passes e
o gold permaneceu oculto. Os domínios `formulas` e `formula_content` passaram, o candidato é
determinístico e válido e os bloqueios remanescentes caíram para 33. Esse resultado abriu a etapa
7C-04 de hierarquia e notas; o candidato geral e produção permaneceram bloqueados.

Progresso em 2026-09-16: G7C-04 reproduziu exatamente 26 seções nos níveis 6/11/9, aprovou sete
notas estruturais e dez unidades semânticas de notas e preservou tabelas, referências e 43 fórmulas.
O corpo não apresentou omissão, invenção, alteração, deslocamento nem token não autenticado, com
precisão 0,998969 e recall 1,0. O gate determinístico foi aprovado sem mismatch e os bloqueios
remanescentes caíram de 30 para 6.

Progresso em 2026-09-16: G7C-05 preservou quatro autores e quatro ORCIDs autenticados pelo IDML,
usou autoridade Crossref content-addressed e independente para os componentes dos nomes, título do
periódico e `other=00224`, e completou a referência ordinal 18. O resultado foi 39/39
cross-references e zero bloqueio nos 12 domínios após reconciliação das 24 fórmulas qualificadas.
O candidato semântico geral está aprovado. Em 2026-09-17, G7C-06 provou conformidade offline,
integridade e reprodutibilidade byte a byte do pacote com XML, PDF e sete JPEGs. Os erros reais de
paginação e divergência entre referências estruturadas/mistas foram zerados; os achados restantes
dos validadores externos possuem reprodução, código, quantidade e evidência fechados no contrato.
O XPM SPS 1.10 continua pendente no worker Windows e mantém `release_ready=false`. A próxima etapa
foi 7C-07, que reavaliou os seis domínios alterados em 24 chamadas OpenClaw. Os seis casos passaram
checks determinísticos e críticos e ficaram somente `accepted_for_human_review`; os cinco controles
negativos falharam fechado e a matriz adversarial passou 30/30 casos. O custo foi 140.447 micro-USD,
sem ferramentas expostas, reparo ou persistência. Flags, credencial, sessões e redes transitórias
foram removidas ao final. Como os papéis compartilham o mesmo modelo, essa concordância não autoriza
release. Em 2026-09-21, G7C-08 encerrou a trilha: dois artigos requalificados com zero bloqueio,
380 testes/87,31%, 18 gates isolados e implantação com backup/restore/rollback comprovados.
V-07 volta a **PASSOU NO CORPUS ATUAL**; próxima etapa V-12. Ver
`docs/PHASE_7C08_REQUALIFICATION.md`. XPM e Gate Humano Final permanecem bloqueadores de release.

### V-08 — Validação assistiva OpenClaw

- executar todos os domínios em casos positivos, negativos, ambíguos e de abstenção;
- medir precisão, recall, exatidão, ganho sobre baseline automático e taxa de abstenção;
- comparar proponente, críticos e adjudicador sem revelar o alvo ao proponente;
- rejeitar evidence hash incorreto, path proibido, schema extra e patch parcial de `RichText`;
- testar alucinação, DOI inexistente, autor inventado e expansão não apoiada;
- testar custo, tokens, latência, timeout e repetição limitada;
- manter tools/Skills vazios nos avaliadores e `needs_human=true` até o aceite final.

Aceite: zero alteração sem evidência, zero violação de contrato, orçamento respeitado e todos os
erros ou desacordos encaminhados como bloqueio/abstenção.

Evidência incremental: a matriz `idml-multi-agent-adversarial-matrix-1.0` cobre seis domínios e cinco
cenários por domínio sem provider. Em 2026-09-01, os 30 casos e 84 papéis simulados passaram 100% dos
oráculos, incluindo invenção com metadados de evidência válidos, ambiguidade, falso consenso e prompt injection. Estrutura e
matemática são sintéticas e continuam exigindo evidência real autorizada antes da RC.

Estado em 2026-09-11: V-08 aprovada. A matriz adversarial foi reexecutada com 30/30 casos, 84 papéis,
zero provider e custo zero; sete mutações adicionais de contrato falharam fechado. A janela real
materializou por backend autenticado 10/10 propostas textuais exatas e melhores que o baseline;
nove ficaram aceitas somente para revisão humana e uma foi corretamente rejeitada por defeito
semântico no proxy XML histórico. Uma inconsistência de agreement foi corrigida no prompt e
requalificada isoladamente. As duas janelas finais custaram 297.872 micro-USD, não expuseram
tools/Skills e terminaram com provider/flags desligados e zero persistência. Estrutura e as 17
fórmulas completam os seis domínios por evidências content-addressed anteriores. Os papéis continuam
correlacionados pelo mesmo modelo e não autorizam release. Relatório:
`benchmarks/agents/reports/v08-assistive-validation-v1.json`.

### V-09 — Segurança, identidade e multiempresa

- login, logout, expiração, recuperação, MFA e reautenticação;
- RBAC por empresa, usuário, papel, recurso e ação;
- tentativas de leitura/escrita cruzada entre empresas;
- IDOR, CSRF, XSS, injection, upload malicioso e rate limiting;
- escopo de jobs, artefatos, revisões, auditoria e agentes;
- segredo ausente/rotacionado, logs sanitizados e permissões de arquivos;
- prompt injection em IDML, PDF, XML, metadados e evidências.

Aceite: zero achado crítico/alto aberto e nenhuma possibilidade conhecida de vazamento entre
empresas.

Estado em 2026-09-11: V-09 aprovada. Foram 35 testes dedicados de segurança e 305 testes completos
com 87,02% de cobertura; 40 operações autenticadas e 30 operações multiempresa foram inventariadas
pelo gate. Não houve vazamento conhecido entre empresas nem achado crítico/alto aberto. Limitação
Redis de login/recuperação, equalização temporal de senha, auditoria persistente de falhas,
sanitização de mensagens de log, contratos contra mass assignment e cabeçalhos defensivos foram
implementados. Backup/restore e gate read-only/sem rede passaram na VPS, e a imagem
`phase7-v09-security-v1` ficou saudável. Relatório:
`benchmarks/security/v09-security-validation-v1.json`.

### V-10 — Fluxo ponta a ponta e experiência operacional

- criar empresa/usuário e executar upload, processamento, revisão, aprovação e download;
- reprocessar sem duplicar jobs, propostas, artefatos ou auditoria;
- cancelar, retomar e repetir após falha;
- conferir estados, mensagens, permissões e trilha de auditoria na interface;
- comparar pacote baixado com manifestos e hashes persistidos;
- comprovar operação degradada com OpenClaw desligado.

Aceite: todos os cenários críticos concluídos de forma reproduzível e auditável.

Estado em 2026-09-11: **PASSOU**. Os jobs operacionais `idml.process` e `scielo.package`, artefatos
gerados íntegros, idempotência estrita, cancelamento/retry, revisão, dupla aprovação, manifesto e
interface foram exercitados de ponta a ponta. Foram 308 testes, cobertura de 87,44% e gate local/VPS
sem rede. OpenClaw permaneceu desligado e sem persistência. Relatório:
`benchmarks/qualification/reports/v10-operational-workflow-v1.json`.

### V-11 — Robustez, propriedades e mutações

- fuzz de XML, ZIP, Unicode, estilos, tabelas e conteúdo misto;
- property tests de idempotência, estabilidade de ordem e preservação de texto;
- metamorphic tests: renomear IDs, reordenar ZIP e variar espaços sem alterar semântica;
- mutation testing nos módulos críticos para verificar a força da suíte;
- regressão automática de cada defeito encontrado por agentes ou especialista.

Aceite: nenhuma falha não controlada e metas de mutação definidas por módulo antes da RC.

Estado em 2026-09-11: **PASSOU**. Foram rejeitadas de modo controlado 121 entradas binárias
arbitrárias, 128 mutações de ZIP e cinco formas hostis de XML. Propriedades de Unicode, conteúdo
misto, ordem, renomeação de IDs, espaços XML, manifesto e hashes passaram. A campanha matou 13/13
mutações comportamentais (100%) e revelou uma propagação não normalizada de `zlib.error`, agora
corrigida e coberta por regressão. A suíte integral terminou com 317 testes e 87,50% de cobertura;
o gate passou localmente e na imagem implantada, read-only e sem rede. Relatório:
`benchmarks/qualification/reports/v11-robustness-mutation-v1.json`.

### V-12 — Desempenho, capacidade e custo

Pré-condição adicional: G7C-08 aprovado. Testes de desempenho não devem congelar baselines de um
pipeline que ainda substituirá fórmulas gráficas por MathML e corrigirá assets e empacotamento.

- artigos pequenos, típicos, grandes e patológicos;
- concorrência inicial e filas sob carga controlada;
- CPU, RAM, swap, disco, I/O, tempo de fila e duração por etapa;
- limites de upload, artefatos, logs, backups e volumes Docker;
- custo de IA por artigo, domínio, reparo e falha;
- teste prolongado para detectar vazamento de memória ou crescimento de estado.

Aceite: nenhuma degradação dos serviços existentes; orçamento respeitado; capacidade documentada e
upgrade da VPS indicado somente por métricas.

V-12.1 aprovada em 2026-09-22: cobre somente baseline e janela inicial limitada;
V-12.2 cobre fila durável e limites de armazenamento/ingestão; V-12.3 cobre duração prolongada e
capacidade integrada com IA. O gate inicial mantém `v12_complete=false` e não qualifica throughput
de produção. A matriz pequena/típica/grande é sintética, com 16/128/512 parágrafos, não uma
amostragem estatística do corpus editorial. Ver `docs/PHASE_7_V12_CAPACITY.md`.

V-12.2 iniciada em 2026-09-22: correções locais do horário de retry, prioridade da fila
durável sobre avisos Redis e timeouts de notificação; 415 testes/87,53%. Ainda faltam
limites de ingestão/armazenamento e implantação qualificada. O laboratório real PostgreSQL/Redis
foi aprovado no mesmo dia: 24 conversões na janela reforçada, quatro modos, 25 serviços
preservados e 428 testes locais/87,53%. Não é qualificação de throughput de produção.

Ingestão limitada avançou em 2026-09-22: um OOM sintético foi reproduzido em container de
256 MiB e corrigido com orçamento agregado de XML e contagem de complexidade antes da árvore.
Oito casos VPS, 453 testes/87,57% e 18 gates de requalificação passaram; os dois XMLs de referência
mantêm seus hashes. Restam corpo HTTP/multipart, volume no pipeline completo e quotas/logs/backups.
As correções não foram implantadas nos serviços existentes. Ver `docs/PHASE_7_V12_INGESTION.md`.

Recepção HTTP/multipart limitada conferida em 2026-09-24: envios reais de 100 MiB com/sem
Content-Length, rejeição antecipada e limpeza de temporários passaram em laboratório;
489 testes/87,65%. Próximos: quotas, reserva de disco, admissão concorrente/cliente lento,
pipeline completo, logs/backups e implantação controlada. Ver `docs/PHASE_7_V12_HTTP_UPLOAD.md`.

Admissão de uploads avançou em 2026-09-24: limite entre processos, espaço temporário e prazos
de inatividade/recepção implementados na candidata; HTTP real confirmou recusa 503, timeout 408
e recuperação 200. Próximos: quotas por empresa e reserva do armazenamento definitivo,
pipeline completo e demais controles V-12.2. Ver `docs/PHASE_7_V12_UPLOAD_ADMISSION.md`.

Quotas/armazenamento aprovados na candidata em 2026-09-24: bytes/arquivos por empresa,
trava até fim da transação, órfãos contabilizados e deduplicação verificada. 530 testes/87,72%,
18 gates e repetição dos ensaios VPS, incluindo PostgreSQL real. XMLs de referência inalterados.
Próximos: volume no pipeline completo, alertas/logs/backups e implantação controlada.
Detalhes e tentativas do laboratório: `docs/PHASE_7_V12_STORAGE_BUDGET.md`.

Perfis volumétricos aprovados em 2026-09-24: seis cenários de persistência/conversão e proteção
de armazenamento, sem OOM, respeitando a reserva da VPS. O perfil binário de 500 MiB não
representa 500 MiB de conteúdo editorial. Próximos: alertas/reconciliação, logs/backups e
implantação controlada. Escopo restrito em `docs/PHASE_7_V12_VOLUME_PROFILES.md`.

Em 2026-09-25, auditoria somente leitura e plano de retenção implementados: 566 testes,
87,72% de cobertura do pacote, 18 gates e dois artigos requalificados sem alteração dos XMLs.
VPS sem divergência de armazenamento; 90 backups protegidos e 49 entradas para classificação,
nenhuma exclusão. Agendamento/rotação apenas preparados. Próximos: classificar backups,
restore isolado e implantação controlada. Ver `docs/PHASE_7_V12_OPERATIONS.md`.

### V-13 — Falhas, recuperação e continuidade

Pré-requisito operacional de V-12.2: restore isolado do backup existente aprovado em
2026-09-25 (21 tabelas, integridade SQLite e hash do artefato). Nenhum serviço existente
alterado; snapshot coordenado novo e rollout ainda pendentes. Ver
`docs/PHASE_7_V12_BACKUP_RESTORE.md`. Não equivale à conclusão da família V-13.

- queda de worker, API, PostgreSQL, Redis, OpenClaw, proxy e provider;
- timeout, rate limit, resposta inválida, falta de espaço e processo terminado;
- reinício no meio de ingestão, geração, validação, revisão e pacote;
- backup consistente, checksum, restore isolado e recuperação completa;
- rollback de aplicação, migration, prompt, modelo, profile e configuração;
- exercícios de incident response com tempos medidos.

Aceite: sem corrupção ou perda silenciosa; retomada idempotente; RPO/RTO medidos e aprovados antes
da ativação.

### V-14 — Observabilidade, auditoria e conformidade

- correlação por empresa, usuário, job, versão e artefato;
- métricas e alertas de erro, fila, custo, latência, disco e validação;
- auditoria imutável de decisões humanas e assistivas;
- ausência de segredo, conteúdo restrito e raciocínio privado em logs;
- retenção, exclusão e exportação conforme a política LGPD definida;
- reconstrução completa de quem fez o quê, quando e com qual versão.

Aceite: incidentes e decisões reconstruíveis sem acessar conteúdo indevido.

### V-15 — Deploy e prontidão de produção

- build reproduzível, SBOM/inventário, dependências fixadas e scan de vulnerabilidades;
- migration compatível, smoke test, health/readiness e rollback automático/manual;
- TLS, firewall, headers, secret management e networks privadas;
- rollout gradual, kill switch de IA e modo somente determinístico;
- runbooks executados por outra pessoa ou agente sem conhecimento tácito;
- comparação antes/depois do deploy sem alterar artigos existentes.

Aceite: candidato implantável e reversível, sem ativar tráfego editorial real.

## 6. Metas da versão candidata

As metas completas abaixo continuam obrigatórias para a RC de produção. A primeira avaliação
usa o recorte H0–H4/G-HOMOLOG, sem declarar as famílias V-12 a V-15 concluídas. Não há dispensa
de segurança, fidelidade conhecida ou validadores obrigatórios aplicáveis à VH.

- 100% dos testes bloqueadores e críticos aprovados.
- 100% dos XMLs candidatos well-formed e aprovados no schema/profile fixado.
- Zero erro crítico nos validadores externos aplicáveis.
- Zero perda, duplicação ou invenção conhecida de conteúdo.
- Zero `xref`, `rid`, asset ou identificador obrigatório quebrado.
- Zero vazamento entre empresas e zero segredo em código/logs.
- 100% das mudanças assistivas com evidência válida e revisão requerida.
- Suíte global com cobertura mínima de 85%; módulos críticos com meta mínima de 90% e mutation score
  definido antes da RC.
- Pipeline determinístico reproduzível e idempotente.
- Backup, restore, rollback e modo degradado comprovados.
- Nenhum blocker/critical aberto; major somente com correção antes da homologação humana.

As metas de qualidade semântica por domínio serão calculadas no corpus congelado. Uma métrica alta
não compensa uma invenção, perda textual ou violação estrutural crítica.

## 7. Evidências obrigatórias por execução

- manifesto de corpus e configuração;
- commit, imagem, modelo, prompt, schema, profile e versões de validadores;
- casos executados, aprovados, reprovados e abstidos;
- métricas por domínio e tipo de falha;
- custos, tokens, latências e uso de recursos;
- diffs sanitizados e vínculos de evidência;
- logs de backup/restore, rollback e fault injection;
- lista de riscos e defeitos residuais;
- relatório assinado do Gate Técnico correspondente.

## 8. Protocolo de homologação do especialista XML

O especialista receberá a VH após G-HOMOLOG; para o aceite final receberá a RC completa:

1. ambiente isolado e instruções de uso;
2. corpus autorizado e critérios de amostragem, distinguindo referências já usadas de
   `holdout-human` independente; preservar as regras de acesso e não contaminar o holdout;
3. XMLs, fontes, relatórios de validação e diffs semânticos;
4. matriz de cobertura por domínio e lista de riscos conhecidos;
5. formulário para classificar `blocker`, `critical`, `major`, `minor` e melhoria;
6. mecanismo para reproduzir cada resultado e registrar evidência.

Cada apontamento deve gerar issue rastreável, teste de regressão, correção, reexecução completa e
nova RC. O Gate Humano Final exige zero `blocker`/`critical`, todos os `major` corrigidos e riscos
residuais aceitos explicitamente. Só então a ativação de produção poderá ser autorizada.

## 9. Ordem de execução planejada

1. completar o laboratório multiagente e os casos restantes da Fase 6;
2. automatizar V-01 a V-11 e congelar os corpus de regressão/holdout;
3. priorizar H0–H4: validação formal/XPM, implantação segura mínima, fluxo integrado e material;
4. congelar a VH e aprovar G-HOMOLOG para avaliação restrita do especialista;
5. incorporar apontamentos com regressão enquanto V-12 a V-15/prontidão 8.1 avançam;
6. atingir metas completas, aprovar G7-T/G8-RC e apresentar a RC final para revalidação;
7. aprovar Gate Humano Final, sem tratar feedback inicial como aceite de produção;
8. realizar rollout gradual acompanhado e manter revisão por artigo no período inicial.
