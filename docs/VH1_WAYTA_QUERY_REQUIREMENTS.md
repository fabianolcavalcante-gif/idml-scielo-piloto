# VH1 — Wayta: aplicabilidade e indisponibilidade

Checkpoint: 2026-10-19. VH-02/07 parciais. Contrato implementado e qualificado,
**não implantado no worker/UI**, sem aprovação de XML ou ativação de IA.

## Decisão delimitada e fontes

Wayta é auxiliar no perfil de afiliações ESA 1.1 qualificado, não uma fonte
obrigatória para aprovar por si só nomes de instituições. Trata-se de **inferência
delimitada**, combinando a especificação e o comportamento executado do XPM, não
de uma comunicação oficial que dispense toda consulta ou toda afiliação.

- [Especificação SPS](https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit):
  seção de afiliações, texto coletado em 17/10. Lista `orgname`, `orgdiv1`, `orgdiv2`
  e `original`; não lista `normalized`. Afiliação e país continuam exigidos.
- [Issue oficial SPS 558](https://github.com/scieloorg/scielo_publishing_schema/issues/558):
  discussão histórica sobre retirada da obrigatoriedade de normalização. Apoio
  histórico, não usada sozinha como autorização para dispensar consultas.
- [Projeto Wayta](https://github.com/scieloorg/wayta): serviço de sugestões de nomes;
  uma sugestão não autentica identidade nem vínculo real de autor.
- XPM original 4.0.096: `AffValidator.normalized` retorna lista vazia imediatamente.
  O código morto abaixo não foi reativado nem editado. `Wayta.search` devolve lista
  vazia para resposta vazia, ausente, malformada e timeout; não distingue esses casos.

Norma integral privada: `benchmarks/private/output/vh1-history-spec-20261017T133639Z/`.
SHA-256: `09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef`.
Mudança de norma/vendor/perfil exige requalificação, não atualização cega de hash.
Não se concluiu que Wayta foi encerrado; um timeout da VPS não demonstra isso.

## Implementação e segurança

`src/idml_foundation/release/xpm_query_requirements.py` compõe o avaliador DOI/SPS
inalterado. A evidência é interna, produzida pelo executor supervisionado, nunca
recebida como decisão do usuário/IA. Não foi criado endpoint que aceite essa evidência.

A classificação auxiliar exige os mesmos bytes de XML/ZIP, empresa/artigo/perfil,
relatório XPM atestado, Crossref vigente e as duas validações independentes modernas.
Exige ainda norma/contraprova/vendor fixados e observação de serviço coerente,
datada e com até 24 horas. Observação futura, sem fuso ou forjada é recusada.

Guarda conservadora: afiliações diretas do artigo, IDs únicos, instituições original
e principal preenchidas, tipos suportados, cidade/estado, país e vínculo de cada
autor com destino existente. Códigos/nomes BR (Brazil/Brasil), IN (India) e JP (Japan)
são os qualificados no perfil ESA 1.1. Outros países, subartigos, pesquisador sem
instituição, markup não qualificado ou vínculo ambíguo ficam **indeterminados**;
não são declarados universalmente inválidos. A guarda não substitui a norma completa.

`normalized` legado não recebe essa classificação. País ausente/incoerente e vínculo
inválido tampouco. O método nativo de afiliação deixa passar país ausente porque
itera apenas países existentes; o controle novo não reproduz essa lacuna.

Nenhum achado é subtraído neste incremento. Resultado contém a avaliação anterior
intacta, classificação auxiliar/indeterminada, observação do serviço e razões
separadas. `article_query_completed`, `institution_identity_verified`,
`homologation_ready` e `release_approved` continuam falsos; exigência de validação
de afiliação permanece verdadeira. A flag global de consultas obrigatórias não é
alterada. O XML que o XPM eventualmente reescreve não é promovido a candidato.

## Evidências executadas

Na mesma VPS, imagem original fixada
`sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63`.
Contraprova sem rede, usuário 65534, rootfs somente leitura, sem capabilities,
256 MiB, 0,5 CPU, 48 PIDs e sem portas. Todos os arquivos vendor copiados foram
comparados antes/depois e permaneceram intactos.

- Cinco respostas sintéticas: correspondência, vazio, JSON inválido, ausente, timeout.
- Seis afiliações × três estados de consulta: válida, sem orgname, sem país,
  código inválido, sem original e xref quebrado. Dezoito casos, incluindo a lacuna
  nativa de ausência de país. Todos retornaram zero achados de normalização.
- Sondagem HTTPS separada, sem nome de instituição/artigo: DNS público; conexão
  expirou após 8,017 s, sem status HTTP. Sem retry, redirect ou fallback HTTP;
  DNS privado/misto bloqueado, TLS com verificação e corpo limitado a 64 KiB.
  Corpo e IP não registrados no relatório, somente hash/quantidade/status.

Arquivo final da contraprova: `vh1-wayta-native-v3.json`, SHA-256
`144d937523f966751d2ce73300131c1fbde1e6e380cbd1ad5de022e411459802`.
v1/v2 são intermediárias anteriores à formatação final do script; não são novas
provas de artigos. Tentativas diagnósticas iniciais foram preservadas na pasta
privada da VPS; a expectativa sobre país ausente foi corrigida para registrar o
comportamento real, não se modificou o XPM para fazê-lo passar.

Sondagem: `vh1-wayta-service-v1.json`, SHA-256
`b5a9250a259584059fdd18273a40ec4b40492479844dad4d215fde40fdd4e53a`.
Diretório remoto privado: `/opt/idml-platform/private/qualification/vh1-wayta-20261019`.
Fontes/documentação/provas do incremento arquivadas ali em
`wayta-requirements-source-v1.tar.gz`, sem extração no diretório da aplicação ativa.

Auditoria `ops/audit_vh1_wayta_requirements.py` revalida entradas nativas privadas
e a cadeia histórica, não apenas um JSON com status aprovado. Nos mesmos candidatos
cadastrais e20240086/e20240135: 3/4 afiliações e 3/4 autores no perfil qualificado.
Avaliação anterior preservada exatamente. Não houve rerun integral dos validadores
porque os bytes dos artigos/ferramentas não mudaram.

Prova ativa `vh1-wayta-requirements-v1.json`, SHA-256
`da5aadf7da82ca4e993fdabe181bb4448bd09ee840a46130318050c6b9bb073f`.
XPM bruto segue 3 bloqueios/1 fatal/4 erros por artigo. Derivado DOI/SPS continua
0/1/1, avisos 2/3 e consultas pendentes. Packtools/SPS preservados na prova anterior:
zero críticos/erros, cinco avisos por ferramenta/artigo. Não é aprovação integral.

## Testes e reprodução

229 testes direcionados aprovados (93 novos), JUnit `tmp/vh1-wayta-focused.xml`.
Incluem erros reais, hashes/escopo, evidência vencida/futura, HTTP 200 sem consulta,
país ausente, segurança de conexão, preservação de fatal e adulteração de prova.
Ruff global, mypy dos 116 módulos e formatação dos oito arquivos novos aprovados.
Sem nova suíte integral/cobertura e sem declaração de CI global aprovado. O resultado
2.166/89,33% de 16/10 precede os módulos SPS e Wayta.
Gates V10/V11 passaram novamente; verificação final da VPS mostrou 25 containers
em execução e serviços IDML saudáveis. Nenhum restart/deploy ou mudança dos serviços
do outro projeto. Não houve chamada de IA nesta etapa.

```powershell
.venv/Scripts/python -m ops.gate_vh1_wayta_requirements
.venv/Scripts/python -m pytest tests/test_xpm_query_requirements.py tests/test_wayta_service_probe.py tests/test_vh1_wayta_requirements_gate.py --no-cov
```

Gate incluído no CI, sem corpus privado/rede. Verifica prova histórica e fontes;
não declara que o serviço está disponível hoje nem reutiliza observação expirada
em nova execução. Reexecutar auditoria exige entradas privadas e observação atual;
novo resultado usa outro arquivo, sem sobrescrever histórico.

## Próximo trabalho fechado

VH-08: contrato e lista fechada de correções automáticas por campo/operação, com
negação por padrão e matriz positivo/negativo. Depois VH-09/10 conforme plano.
DOCTYPE/JATS, erro residual XPM, demais consultas e integração supervisionada
permanecem em VH-02/07; não reabrir pesquisa Wayta sem evidência nova. A integração
dos diagnósticos na web é VH-12/14. Sem IA ativa, deploy ou liberação ao especialista.
