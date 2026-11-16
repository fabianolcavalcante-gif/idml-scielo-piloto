> Histórico até 2026-10-01. Não usar seus próximos passos como fila atual.
> Controle vigente: HOMOLOGATION_VH1_DELIVERY.md.

# Plano prioritário — versão funcional para testes do especialista

Decisão 2026-10-01 (ADR-016): a VH deverá incluir correção automática restrita
antes da avaliação humana. H1-A1–A5 são obrigatórios para esta entrega;
escopo e aceites em `AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`. Ainda não implementado.

2026-10-01: comparação DOI positiva nos dois artigos reais/duas ferramentas
localmente; XMLs intactos. Runtime fixado e demais achados ainda pendentes.
Ver `H1_REAL_DOI_LOCAL.md`; não libera G-HOMOLOG.

Atualização H1: integração DOI SPS qualificada pelo socket na VPS, com hashes
de ZIP/XML e rejeição de dados inválidos. Seis cenários SPS e quatro Packtools
passaram. Próximo: artigos reais e autoridades editoriais; ver `H1_SPS_DOI_AUTHORITY.md`.

Último incremento H1: socket completo Packtools qualificado com quatro cenários;
defeito de consumo dos autores corrigido na compatibilidade candidata, sem alterar
XML/regras de comparação. SPS continua próximo; ver `H1_DOI_SOCKET.md`.

Atualização H1, transporte DOI: integração candidata Packtools implementada;
prova nativa Linux sintética positiva e negativa com rede desabilitada concluída.
Fluxo completo/socket e SPS permanecem pendentes. Ver `H1_DOI_TRANSPORT.md`.

Incremento H1 em 2026-09-30: diagnóstico DOI qualificado na VPS e ponte de
autoridade Crossref qualificada localmente, com hashes, prazo e vínculo ao artigo.
736 testes aprovados (88,02% de cobertura). Próximo: integrar consulta vinculada
ao transporte isolado e repetir contraprovas; depois autoridades editoriais,
achados restantes e XPM. Ver `H1_DOI_AUTHORITY_BRIDGE.md`.
H1 continua em implementação; G-HOMOLOG e implantação não liberados.

Decisão autorizada pelo usuário em 2026-09-25. Estado em 2026-09-28: H0 CONCLUÍDO;
H1 EM IMPLEMENTAÇÃO, NÃO LIBERADO. Baseline: `H0_HOMOLOGATION_BASELINE.md`.
Referência: ADR-015. Esta sequência substitui a exigência de concluir toda a prontidão
operacional antes da primeira avaliação humana; não elimina nenhum requisito de produção.

## Objetivo e limites

Entregar uma versão funcional de homologação (VH), congelada e reproduzível, para avaliar
qualidade editorial do XML e usabilidade do fluxo IDML → XML/pacote. Não é produção, nem
aprovação SciELO, nem o aceite humano final G8-H. A abertura depende do novo gate G-HOMOLOG.
V-12.2 continua incompleta; G7-T e G8-RC não são declarados aprovados por essa mudança.

Base comprovada: 581 testes locais aprovados, cobertura de 87,72% do pacote da aplicação,
dois artigos requalificados no corpus atual e um backup existente restaurado isoladamente.
Isso não comprova a candidata implantada, o XPM pendente ou qualidade universal em novos artigos.

## Ordem de execução

### H0 — Fixar escopo e inventariar bloqueadores (concluído em 2026-09-28)

- [x] Comparar fonte candidata e imagem implantada; listar correções necessárias ao fluxo.
- [x] Fixar baseline de periódico/template, schema/profile, imagem atual, prompts e modelos;
  imagem final da VH permanece condicionada a H1–H3, sem alegar congelamento final.
- [x] Inventariar XPM/worker Windows, requisitos de execução e eventual dependência externa.
- [x] Definir corpus autorizado, critérios editoriais e envelope conservador a verificar em H2.
- [x] Registrar responsáveis, evidências esperadas e limitações; separar funcionalidade
  existente, pendente e não incluída. Não anunciar suporte a qualquer IDML/periódico.

Aceite: lista rastreável de bloqueadores H1–H4 e escopo fechado. Não iniciar uma sequência
ilimitada de melhorias operacionais sem demonstrar que bloqueiam essa entrega.

### H1 — Fechar validação formal do candidato

H1-01 integrado e testado localmente: dois jobs reproduziram os hashes qualificados,
com isolamento/proveniência. Ver `H1_JOB_ENRICHMENT.md`; provisionamento e prova da UI em H2/H3.
Próximo: H1-02/H1-04 (validação/estado integrado) e H1-03 (XPM).
Primeiro incremento H1-02/H1-04 implementado: resultado formal vinculado ao pacote, falha
fechada e separação da aprovação editorial. Transporte isolado implementado e exercitado
na VPS com entradas sintéticas incompletas, sem aprovação XML nem implantação no worker.
Matriz local de falhas do broker concluída em 2026-09-29, com correção de prazo
vencido; ver `H1_BROKER_FAILURE_QUALIFICATION.md`. Próximo: pacotes completos,
falhas reais Linux e XPM. Ver `H1_VALIDATOR_TRANSPORT.md`.
Pacote sintético completo executado na VPS em 2026-09-29: Packtools e SPSValidator
concluíram sem exceção de execução, mas com achados; não houve aprovação XML.
Ver `H1_COMPLETE_PACKAGE_QUALIFICATION.md`. Pacotes reais e XPM continuam pendentes.
Envio privado autorizado em 2026-09-29 e candidatos reais testados na VPS; ambos
reprovaram externamente, um com exceção. Cópias remotas removidas. Próximo:
classificar/corrigir achados e fechar compatibilidade XPM. A sequência detalhada
e os critérios estão em `SCIELO_READINESS_GAP_PLAN.md`; G-HOMOLOG continua pendente.
Pacote corrigido do e20240086 preparado e validado offline; triagem distingue
divergência de nome de PDF de ausência real. Reexecução externa dessa candidata
aguarda reserva mínima de RAM. Ver `H1_CORRECTED_PACKAGE_TRIAGE.md`.
Não confundir parser de relatório ou validação offline com execução formal completa.

Atualização 2026-09-30: com reserva RAM suficiente, os dois candidatos completaram
Packtools e SPSValidator na VPS, usando imagem candidata de compatibilidade PDF.
Erro de PDF resolvido e contraprova de ausência preservada. Os XMLs continuam
reprovados por outros achados; XPM, promoção e prova API/worker/UI continuam
pendentes. Ver `H1_RENDITION_COMPATIBILITY.md`. H1 e G-HOMOLOG não concluídos.

Incremento seguinte concluído em laboratório: perfil 1.1, três erros críticos de
país corrigidos e comprovados na VPS; segundo artigo sem regressão. 696 testes
locais aprovados. Falha de afiliação da ferramenta reproduzida, próxima correção
estreita planejada. Ver `H1_COUNTRY_CODES_AND_FRONT_TRIAGE.md`. Perfil padrão,
bundles do worker e aplicação não promovidos; XMLs e G-HOMOLOG ainda não aprovados.

Compatibilidade de afiliações qualificada em seguida: 20 casos nativos Linux
(dez por imagem), 708 testes locais aprovados e quatro execuções reais completas.
Críticos reduzidos de 25 para 22 e de 10 para 6, sem edição de XML. Ver
`H1_AFFILIATION_COMPATIBILITY.md`. Ainda faltam achados remanescentes, XPM e prova
do fluxo implantado H2/H3; esta evidência não libera G-HOMOLOG.

Incremento de diagnóstico externo concluído em laboratório: bloqueios explícitos
para cadastros indisponíveis, 725 testes aprovados, V10 local requalificado em novo
relatório sem alterar o histórico. Prova nas duas imagens/candidatos; não houve
consulta nova nem aprovação XML. Próximo: evidência DOI e ligação às autoridades
de periódico/identificadores. Ver `H1_EXTERNAL_VERIFICATION.md`.

- [ ] Executar validadores obrigatórios sobre XML/pacote exatos da VH, inclusive XPM SPS 1.10
  no executor compatível. Replay histórico por hash não substitui esta prova de integração.
- [ ] Corrigir erros reais; exceções somente com evidência rastreável, nunca waiver genérico.
- [ ] Revalidar dois artigos de referência: texto, autores/afiliações, referências, figuras,
  tabelas, fórmulas, notas, cross-references, arquivos vinculados e pacote.
- [ ] Demonstrar que saída inválida ou incompleta é bloqueada e que o motivo aparece na UI.

Aceite: candidatos de referência aprovados nos validadores aplicáveis, zero erro crítico
real ou perda/invenção conhecida. Se XPM estiver indisponível, registrar impedimento concreto;
não simular aprovação nem liberar G-HOMOLOG silenciosamente. Artigos novos podem reprovar:
isso deve gerar diagnóstico reproduzível, não falso sucesso.

### H1-A — Correção automática restrita antes do especialista

- [ ] Concluir contratos/política, executor reversível, agentes e interface H1-A1–A4.
- [ ] Preparar matriz de elegibilidade/abstenção/reversão e evidências de H1-A5.
- [ ] Não exigir aprovação humana intermediária nas operações elegíveis; manter
  exceções pendentes e impedir aplicação fora da política ou com perda de conteúdo.

Aceite e sequência detalhados em `AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md`.
Esta etapa não substitui o fechamento da validação H1 nem o aceite final humano.

### H2 — Implantação segura mínima da VH

- [ ] Gerar backup novo coerente de banco/artefatos/estado antes do deploy; comprovar sua
  restauração isolada. O ensaio do backup histórico não substitui essa proteção atual.
- [ ] Fixar imagem/configuração anterior, compatibilidade de banco e procedimento de rollback.
- [ ] Implantar somente componentes da VH, preservando o outro sistema e OpenClaw existentes.
- [ ] Verificar autenticação, HTTPS, RBAC, isolamento multiempresa, proteção dos downloads,
  segredos, limites de recursos, saúde básica e capacidade para o envelope de testes.
- [ ] Confirmar mecanismo de interrupção, modo sem IA e recuperação básica de job com erro.

Aceite: smoke test aprovado na versão implantada, backup recuperável, retorno seguro disponível,
nenhum bloqueador de segurança ou exposição de dados. Logs e acompanhamento básicos são
obrigatórios; observabilidade completa não é pré-requisito desta entrega.

### H3 — Teste integrado pelo fluxo que o especialista usará

- [ ] Percorrer login/empresa → upload IDML e ativos → fila → conversão → validação → revisão
  → download autorizado de XML/pacote, sem depender de comandos manuais ocultos.
- [ ] Demonstrar erros de upload, validação, ativo ausente e falha de processamento; apresentar
  mensagens úteis, estado correto e tentativa de recuperação sem duplicação.
- [ ] Demonstrar OpenClaw e ciclo automático H1-A5 na candidata implantada: aplicação
  elegível sem decisão humana intermediária, rejeição/abstenção, rollback e modo
  sem IA, com custos/evidências. Automação restrita obrigatória nesta VH; publicação
  automática proibida. Não declarar IA ativa apenas por flags ou serviço em execução.
- [ ] Reexecutar regressão e checks de isolamento na candidata implantada; vincular relatórios
  aos hashes dos XMLs, imagens e versões utilizadas.

Aceite: fluxo utilizável ponta a ponta; zero blocker/critical e nenhum major que impeça a
avaliação, comprometa dados ou altere conteúdo conhecido. Demais limitações declaradas.

### H4 — Acesso e material de avaliação

- [ ] Confirmar identidade do especialista e criar acesso individual, mínimo e revogável;
  não compartilhar o administrador ou inventar destinatário. Não enviar convite sem solicitação.
- [ ] Preparar guia curto, roteiro de casos, resultados esperados, fontes autorizadas, XMLs,
  relatórios, diferenças semânticas e lista explícita de limitações.
- [ ] Preparar casos novos autorizados para testes livres. Os artigos já utilizados servem
  para demonstração/regressão, nunca como holdout humano independente.
- [ ] Preservar `holdout-human` para avaliação humana, sem usar seu gold para corrigir antes
  do teste; registrar autorização e governança de novos artigos.
- [ ] Disponibilizar registro de achados com artigo/job, versão, esperado/observado, reprodução,
  evidência e severidade (blocker, critical, major, minor, melhoria).

Aceite: acesso testado, pacote reproduzível e canal de feedback funcionando. A falta do nome
do especialista não impede H0–H3, mas impede entregar uma conta pessoal a destinatário incerto.

### G-HOMOLOG — Autorizar somente testes restritos

- [ ] H0–H4 concluídos com evidências vinculadas à VH.
- [ ] H1-A1–A5 concluídos; ciclo automático qualificado, auditável e reversível,
  com operações fora da allowlist rejeitadas e avaliação humana final preservada.
- [ ] Validação formal obrigatória e fluxo integrado aprovados no escopo declarado.
- [ ] Backup atual/restore, rollback, acesso seguro e limites mínimos comprovados.
- [ ] Riscos/limitações informados e versão congelada; identificar o ambiente como homologação.
- [ ] Sem tráfego editorial de produção, publicação ou release automático; permitir apenas
  obtenção controlada de artefatos de avaliação sem contornar a política formal de release.

Registrar decisão e responsável; não marcar concluído com base apenas neste planejamento.

### H5 — Avaliação, correções e regressão

- [ ] Especialista executa roteiro e testes livres, registra resultados e novos casos.
- [ ] Cada defeito confirmado gera correção e teste de regressão; preservar caso/evidência.
- [ ] Entregar novas versões identificadas, repetir validadores/checks afetados e regressão
  completa nos ciclos relevantes, sem mudar silenciosamente corpus, modelos ou profiles.
- [ ] Reconfirmar resultados na RC final antes do G8-H; feedback inicial não equivale a aceite final.

## Trabalho que pode continuar depois/em paralelo

| Item | Para iniciar avaliação | Antes da produção |
|---|---|---|
| V-12: capacidade | limites e teste no envelope restrito | carga prolongada, saturação e custos integrados |
| V-13: recuperação | backup atual, restore e rollback mínimos | matriz abrangente de falhas e RPO/RTO |
| V-14: operação | logs seguros, rastreabilidade e saúde básica | alertas completos, retenção e conformidade |
| V-15: implantação | versão fixa, smoke e reversibilidade | automação, hardening e prontidão completa |
| Corpus | fontes autorizadas e limites declarados | diversidade e evidências finais exigidas pelo plano |

Não haverá expurgo de backups para viabilizar testes. Retenção histórica, cópia fora da VPS,
logs internos OpenClaw e demais pendências permanecem no backlog operacional. Se um risco
operacional inviabilizar a segurança do piloto, ele volta a ser bloqueador com justificativa.

Produção continua exigindo G7-T, G8-RC, conclusão dos controles aplicáveis e G8-H. Nenhuma
conclusão de agente substitui aceite humano ou autoriza go-live.
