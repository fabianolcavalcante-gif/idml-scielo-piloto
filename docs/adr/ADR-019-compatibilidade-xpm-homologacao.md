# ADR-019 — Compatibilidade pontual do XPM para homologação

- Data: 2026-10-16.
- Status: desenvolvimento autorizado pelo proprietário; implementação/qualificação
  parcial até 19/10 (duas regras DOI, três SPS/data e aplicabilidade Wayta);
  integração/ativação pendentes.
- Origem: autorização explícita nesta conversa para a proposta de tratar somente
  falsos positivos comprovados, preservar relatórios e bloquear erros reais.
- Escopo: VH-02/07 e sua integração na VH1; não cria fase ou permissão de publicação.

## Decisão e limites

Implementar avaliação de compatibilidade para homologação, separada da aprovação
editorial/publicação. A autorização resolve a decisão de implementar; não comprova
exceções individuais nem encerra VH-02/07. Manter SPS/JATS do candidato e XPM
oficial intacto. Preservar relatório e contagens originais; registrar o tratamento
de falsos positivos em resultado derivado próprio, não como correção oficial SciELO.

Cada regra exige identificador, versão/hash da ferramenta e perfil, evidência
normativa/técnica, condições verificáveis, validação independente e contraprova.
Vincular decisão, XML/ZIP, relatório e fontes aos mesmos hashes, empresa e execução.
Regra desconhecida, versão diferente ou evidência insuficiente falha de forma fechada.
Não aceitar exceção por semelhança de mensagem ou por consenso dos agentes.

Erro real, imagem ausente, XML malformado, perda de conteúdo, consulta indisponível,
catálogo ausente/ambíguo, timeout e hash divergente nunca viram sucesso. Corrigir
título do periódico/editora por fonte; não registrá-los como falsos positivos.
Não alterar dados corretos ou perfil apenas para reduzir contagens. A ressalva
de DOCTYPE documentada em `VH1_XPM_ONLINE_AND_COMPATIBILITY.md` ainda exige
conclusão específica com fonte; esta autorização não a resolve automaticamente.

A Release Policy da ADR-012 e a produção editorial não são liberadas por esta
decisão. Aptidão à avaliação com compatibilidade não concede `READY_FOR_SCIELO`
nem altera `XpmResult.passed` pela adulteração de contagens. Exibir resultado bruto,
exceções aplicadas e pendências separadamente. Aceite humano e controles de acesso,
segurança, backup e G-HOMOLOG permanecem obrigatórios.

## Aceite de implementação

1. Contrato versionado e lista fechada de regras, com negação por padrão.
2. Testes positivos e de erro real semelhante, regra desconhecida, relatório
   adulterado, hash/versão/empresa divergente e consulta incompleta.
3. Provas nativas nos dois pacotes corrigidos e controles negativos; somente
   achados qualificados recebem tratamento de compatibilidade.
4. Resultado derivado reproduzível, relatório bruto preservado e publicação bloqueada.
5. Integração no worker/UI e teste ponta a ponta na mesma VPS antes de G-HOMOLOG.

Referências: ADR-012, ADR-015, ADR-017 e `VH1_XPM_ONLINE_AND_COMPATIBILITY.md`.

## Primeiro incremento qualificado — 2026-10-16

`xpm-doi-journal-exact-1.0` e `xpm-doi-article-exact-1.0` comprovadas por oito
contraprovas do código original e pelos dois pacotes reais corrigidos. Relatório
bruto preservado; avaliação derivada não concede prontidão ou publicação. Correções
de cadastro implementadas no pipeline, sem tratá-las como falso positivo.
SPS/pub-date, DOCTYPE/JATS e Wayta permanecem pendentes. Detalhes e hashes:
`VH1_JOURNAL_METADATA_AND_XPM_COMPATIBILITY.md`. Não encerra o aceite 1–5 integral.

## Segundo incremento qualificado — 2026-10-17

Regras `xpm-sps110-version-table-1.0`, `xpm-sps110-date-type-1.0` e
`xpm-sps110-date-combination-1.0` implementadas e comprovadas por dez controles
nativos e avaliação dos dois pacotes exatos. Quatro ocorrências adicionais por
artigo classificadas, sem mudar contagens brutas, XML ou aprovação. Validação
independente, escopo, calendário e correspondência exata obrigatórios.
DOCTYPE/JATS, erro residual, Wayta e integração continuam pendentes.
Detalhes: `VH1_SPS_DATE_COMPATIBILITY.md`. Não altera os limites desta decisão.

## Terceiro incremento qualificado — 2026-10-19

`xpm-wayta-requirement-1.0` classifica Wayta como auxiliar somente no perfil de
afiliações qualificado de ESA 1.1, por inferência normativa/técnica delimitada.
Especificação SPS atual arquivada não inclui `normalized` entre tipos institucionais;
contraprova no XPM original confirma validador de normalização desativado. Não é
waiver oficial geral, dispensa de país/vínculo ou comprovação de identidade.

Indisponibilidade permanece indisponibilidade. Sondagem de serviço não é consulta
do artigo; HTTP 200 tampouco comprova resposta semântica. Escopo, hashes, evidências
independentes e observação com até 24 horas exigidos. Formato fora do qualificado
retorna indeterminado. Sem alterar flags globais de consultas concluídas, contagens
originais/derivadas, ReleasePolicy, XML ou relatórios anteriores. O país ausente,
não detectado pelo método legado, é recusado pelo controle novo.

Prova nos dois candidatos e 23 casos nativos sintéticos; detalhes/fontes/limites em
`VH1_WAYTA_QUERY_REQUIREMENTS.md`. DOCTYPE/JATS, erro residual, demais consultas e
integração continuam pendentes. Próximo desenvolvimento VH-08, conforme plano único.

## Integração parcial no executor — 2026-10-23

As duas regras DOI passam a compor o diagnóstico da execução atual na candidata
`vh1-xpm-runtime-20261023-v1`, com consulta Crossref recente e vínculo integral ao
pacote/relatório/empresa. Dois artigos e dois negativos requalificados na VPS;
contagens brutas e bloqueios de publicação preservados. Diagnóstico complementar
ORCID não é exceção de compatibilidade nem dispensa de identidade. SPS/data/Wayta
no fluxo composto, decisão DOCTYPE/JATS e ativação continuam pendentes. Isso não
encerra os itens 1–5 do aceite. Ver `VH1_XPM_RUNTIME_COMPATIBILITY.md`.

## Composição SPS/data e Wayta — 2026-10-26

As regras já qualificadas agora são compostas no serviço de pacote, com dois
resultados independentes atuais, hashes individuais preservados, vínculo adicional
ao relatório XPM e observação Wayta recente selada. Prova nova nos dois artigos e
negativos, sem mudança de XML/contagens brutas. Aplicação ativa e critérios de
publicação não mudam; DOCTYPE/JATS e erro residual não foram dispensados. Detalhes
em `VH1_XPM_COMPOSED_VALIDATION.md`; aceite integral/UI ainda pendente.

## Decisão técnica DOCTYPE e erro residual — 2026-10-26

Corrigido erro real do gerador: PUBLIC ID da variante padrão combinado com arquivo
MathML3. Identificação agora corresponde ao catálogo NLM; a validação offline
recusa a combinação anterior. O XPM continua com DTD 1.1 e seu Style Checker
interrompe por SPS 1.10 não suportado, comprovados em seis testes nativos.
Não é uma nova exceção: zero contagens dispensadas, nenhum downgrade ou alteração
de conflito de interesses. A ressalva editorial de DOCTYPE continua independente
da validade estrutural moderna. Diagnóstico técnico encerrado; não pesquisar
indefinidamente sem fonte nova. Integrar essas causas ao diagnóstico web e
qualificar eventual regra residual antes de aplicá-la. Provas/limites em
`VH1_DOCTYPE_JATS_DECISION.md`; não encerra o aceite integral/UI.

## Compatibilidade residual qualificada e integrada — 2026-10-28

Regras `xpm-jats13-legacy-dtd-1.0` e `xpm-sps110-style-unavailable-1.0`
integradas ao compositor da candidata. A qualificação técnica de 26/10 e a
reprodução dos relatórios nativos selados de 28/10 sustentam a atribuição exata
das duas ocorrências residuais. Exigem XML local válido, dois validadores
modernos sem erros, atestado/escopo/hash correspondentes e mensagens completas
sem ocorrências adicionais. O conteúdo XML reproduzido no HTML não é evidência
de diagnóstico. Linhas são da cópia formatada pelo XPM, não do arquivo submetido.

Nos dois artigos, contagens derivadas chegam a zero bloqueios/fatais/erros,
mantendo dois/três avisos XPM e os demais avisos/consultas pendentes. Os
resultados brutos, `XpmResult.passed`, política de publicação e os gates globais
não mudam. A decisão é interna, não waiver oficial do DOCTYPE. Erro desconhecido
ou pré-condição incompleta mantém bloqueio. Releitura histórica não renova
validade de recibos nem autorizações. Detalhes, prova e próximos passos:
`docs/VH1_STRUCTURAL_COMPATIBILITY.md`. Aplicação ativa ainda depende da promoção
da candidata; não encerra G-HOMOLOG nem a autorização editorial de publicação.

## Uso na promoção de rascunho — 2026-10-29

As regras foram implantadas na imagem `vh1-structural-20261028-v1`. O novo
serviço interno de promoção, qualificado mas ainda não conectado ao worker,
usa a composição somente após validação nova e mantém os resultados brutos.
Avisos pendentes podem acompanhar uma versão de trabalho; isso não aceita
avisos nem concede aprovação formal/publicação. Consultas selecionadas ausentes
ou divergentes continuam impeditivas. Reprodução de relatório histórico serve
apenas como teste da política, nunca como autorização atual de promoção.
Detalhes: `docs/VH09_WORKING_DRAFT_PROMOTION.md`.
