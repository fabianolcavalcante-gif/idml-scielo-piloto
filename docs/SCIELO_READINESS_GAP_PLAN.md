# Plano de fechamento — XML e entrega SciELO

> Controle atual em 2026-10-01: `HOMOLOGATION_VH1_DELIVERY.md`, itens VH-01–20.
> Este arquivo preserva detalhes/histórico técnico. Todos os “próximos passos” e
> estados abaixo devem ser lidos pela data e não criam trabalho fora da fila VH1.

Decisão de escopo 2026-10-01: desenvolver correção automática restrita antes da
avaliação humana, mantendo as pendências H1 de validação e fontes. H1-A1–A5 são
requisitos da entrega, não trabalho opcional posterior. Ver
`AI_AUTOCORRECTION_HOMOLOGATION_PLAN.md` e ADR-016. Não implementado/ativado ainda.

2026-10-01: quatro comparações DOI reais positivas localmente, com snapshots
novos vinculados. Contexto editorial/ORCID e achados de conteúdo permanecem;
alinhar versões antes de comparar contagens Linux. Ver `H1_REAL_DOI_LOCAL.md`.

Atualização mais recente: SPS aceita autoridade DOI vinculada ao ZIP e XML
interno, com contraprovas sintéticas pelo socket concluídas. Sem aprovação
do XML real ou implantação ativa; ver `H1_SPS_DOI_AUTHORITY.md`.

Último avanço H1: prova completa broker/socket/Packtools e correção do gerador
de autores na validação DOI. Contraprovas de divergência/vencimento/desconexão
aprovadas na VPS isolada. Próximo é SPS; ver `H1_DOI_SOCKET.md`.

Atualização mais recente: transporte candidato DOI para Packtools implementado,
com montagem somente leitura qualificada em prova nativa sintética na VPS.
Sem aprovação de XML ou implantação; próximos gates em `H1_DOI_TRANSPORT.md`.

Atualização 2026-09-30, DOI: esgotamento de consultas identificado no runtime
fixado; diagnóstico repetido na VPS com três/quatro bloqueios nos dois artigos.
Ponte Crossref segura implementada e comparação DOI local positiva com
contraprova negativa; integração isolada ainda pendente. 736 testes aprovados,
88,02% de cobertura. Ver `H1_DOI_AUTHORITY_BRIDGE.md`. Sem aprovação XML/deploy.

Estado em 2026-09-29. Objetivo: reduzir ajustes humanos por validação automática
rastreável, sem prometer aprovação editorial universal ou indexação automática.
Este detalhamento integra H1–H4, não substitui o plano de homologação.

Estado atual, após afiliações (2026-09-30): consultas indisponíveis explicitadas
em bloqueios de sistema, sem rebaixar severidade original. e20240086: dois bloqueios
adicionais de cadastro; e20240135: três, incluindo ORCID. Críticos/erros continuam
22/4 e 6/4. DOI real ainda não classificado por evidência específica. 725 testes
aprovados e prova em duas imagens Linux; ver `H1_EXTERNAL_VERIFICATION.md`.
Próximo: retorno DOI e autoridades verificadas/vinculadas para essas consultas,
mantendo os defeitos XML e XPM no plano. Os registros abaixo são históricos.

Último incremento (2026-09-30): resolução de afiliações corrigida no modelo do
adaptador candidato, sem editar XML ou dispensar regras. Matrizes negativas nas
duas imagens Linux preservam falhas. Mesmos candidatos: e20240086 agora 22 críticos/
4 erros/12 avisos; e20240135 agora 6/4/8. Ambos ainda reprovados. Ver
`H1_AFFILIATION_COMPATIBILITY.md`. Próximo: consultas externas e achados de conteúdo,
com XPM ainda pendente. Os parágrafos abaixo preservam a sequência histórica.

Estado mais recente (2026-09-30): perfil candidato 1.1 corrigiu os três códigos
de país do primeiro artigo, agora com 25 críticos/4 erros/12 avisos em cada
validador. Segundo artigo permanece 10/4/8. Falha de resolução de afiliações
reproduzida em XML sintético no runtime fixado, sem waiver. Próximo incremento:
compatibilidade dessa regra com contraprovas de referências inválidas, antes da
promoção H2/H3. Ver `H1_COUNTRY_CODES_AND_FRONT_TRIAGE.md`; XPM ainda pendente.

Atualização 2026-09-30: a reserva de RAM permitiu a qualificação completa na VPS.
Nova imagem candidata corrige a resolução PDF e preserva erro quando o PDF está
ausente. e20240086 corrigido: ambos os validadores completed, 28 críticos/4 erros/
12 avisos; e20240135: ambos completed, 10 críticos/4 erros/8 avisos. Ambos reprovados.
As execuções e a contraprova não alteraram serviços existentes; cópias privadas
remotas removidas. Ver `H1_RENDITION_COMPATIBILITY.md` e relatório
`h1-rendition-linux-v1.json`. Resultados abaixo são históricos, não o estado novo.
Próximo: classificar/corrigir achados remanescentes e qualificar XPM; não repetir
o bloqueio de RAM histórico como se ainda impedisse esta rodada já concluída.

## Prova nova: candidatos reais na VPS

Autorização do responsável registrada nesta conversa e em `CORPUS_POLICY.md`.
Dois candidatos foram reconstruídos com os catálogos existentes e hashes de
conversão iguais aos já qualificados. PDF/figuras conferidos por manifesto.
Não se usou XML gold como entrada. O primeiro manifesto aponta figuras na raiz,
mas as cópias estão junto ao PDF: o resolvedor aceita apenas arquivo único com
tamanho/hash exatos, sem alterar silenciosamente o manifesto.

| Artigo | Offline | Packtools: estado / críticos / erros / avisos | SPSValidator: estado / críticos / erros / avisos |
|---|---|---|---|
| e20240086 | válido | failed / 28 / 4 / 9 | failed / 29 / 5 / 9 |
| e20240135 | válido | completed / 10 / 4 / 8 | completed / 10 / 5 / 8 |

Os números são achados emitidos, não contagem de defeitos confirmados ou únicos.
O primeiro artigo apresentou `validator-exception-or-invalid-output`. O segundo
concluiu sem exceção, porém reprovou por achados. A execução sem rede não comprova
consultas DOI/ORCID/registro editorial; é necessário separar indisponibilidade,
falha da ferramenta, divergência do perfil e erro real. Nenhum waiver novo aplicado.

Escopo comprovado: pipeline/empacotador atuais → arquivos exatos → broker/validadores
Linux fixados. NÃO é ainda prova do job completo via API/Redis/UI implantada.
Os dois casos são development, não holdout nem prova de generalização.

Os ensaios não reiniciaram serviços; banco/Redis responderam OK depois. As quatro
cópias candidatas remotas foram removidas; scratch/socket vazios. Originais e
candidatos locais privados preservados. A área restrita de qualificação ficou
em disco, fora dos volumes coletados pelo script de backup IDML inspecionado;
não foi usado tmpfs porque o broker exige reserva de 5 GiB e o tmpfs tinha 1,9 GiB.
Não se afirma ausência de snapshots/backups externos do provedor. Scripts sem
conteúdo privado permanecem. Não houve ativação do worker nem publicação.

## Requisitos oficiais e limites das ferramentas

Evidência: `benchmarks/qualification/reports/h1-real-candidates-v1.json`.
Regressão local: 649 testes aprovados, três avisos, cobertura 87,83%; artefatos
`tmp/h1-real-tests.xml` e `tmp/h1-real-coverage.json`. Passar nos testes locais
não equivale à aprovação dos candidatos nos validadores externos.

O [guia de entrega SciELO Brasil](https://www.scielo.org/documents/57/guia_entrega_pacotes.pdf)
exige composição e nomes adequados, XML/PDF por idioma aplicável, ativos e relatório
XPM. Publicação contínua exige `other` e coerência de seção com o controle editorial.
O guia distingue entrega técnica de publicação e não aceita AOP como modalidade
atual. O nome legado `esa-aop` do nosso perfil não prova, sozinho, saída incompatível.

Em [resposta da Publicação SciELO de março de 2026](https://groups.google.com/g/scielo-xml/c/KiC-TDlazJE),
a equipe reconhece descompasso das ferramentas com SPS 1.10 e possíveis falsos
erros. Não há base para exigir simplesmente zero mensagens de um XPM antigo,
nem para ignorá-las em bloco: compatibilidade e exceções precisam de evidência.
Essa resposta não comprova que nenhuma versão posterior exista hoje.

## Sequência de fechamento com critérios de aceite

| Ordem / plano | Lacuna verificada ou prova faltante | Desenvolvimento e aceite |
|---|---|---|
| 1 / H1-02 | Erros reais retornados; exceção no e20240086; códigos genéricos `rule-N` no SPSValidator | Preservar identidade de regra e classificar cada achado: defeito, dado ausente, consulta indisponível ou falso positivo demonstrado. Reproduzir exceções; nenhum erro silenciosamente aceito. |
| 2 / H1-01/02 | Datas, identificadores, afiliações, referências e vínculos de fórmulas aparecem nos achados | Correção baseada em fonte/autoridade, com teste positivo e negativo por regra; não inventar datas, ORCID, financiamento ou `other`. Comparar fidelidade, não só XML bem formado. |
| 3 / H1-03 | XPM registrado 4.0.096/SPS 1.9, worker não integrado | Identificar distribuição oficial, qualificar runtime isolado e gerar relatório do candidato exato. Tratar incompatibilidades normativas documentadas sem alterar XML correto para satisfazer regra antiga. |
| 4 / H1-04 | Avaliação formal sempre incompleta; aprovação editorial separada | Vincular validação, relatórios, versão e decisão ao mesmo candidato; invalidar evidência se houver mudança. Nunca aprovar por hash arbitrário, execução ausente ou exceção. |
| 5 / H1/H2 | Empacotador permite exatamente um PDF e acrescenta manifesto interno; perfil fixa volume 30 | Separar pacote interno de pacote de entrega; incluir relatório XPM, PDFs por idioma, ativos e suplementos aplicáveis; validar nomes, volume/periódico e controle `other` sem valores fixos genéricos. Caso sem suporte deve bloquear explicitamente. |
| 6 / H2/H3 | Código candidato e testes externos não são versão web implantada | Backup/restore/rollback, deploy limitado, fluxo upload → conversão → diagnóstico → revisão → revalidação → download, com isolamento de empresa. Testar assistência IA e modo sem IA. |
| 7 / H4/G-HOMOLOG | Falta prova independente e especialista identificado | Corpus novo autorizado, roteiro por tipo de conteúdo, acesso individual e feedback reproduzível. Liberar como homologação restrita; aceite humano continua distinto de publicação. |

Matriz normativa a completar por perfil: estrutura JATS/SPS, metadados, autores e
afiliações, idiomas, datas/licença, referências e citações, tabelas, fórmulas,
figuras/legendas, notas/anexos, ciência aberta/financiamento/contribuições, arquivos
e integridade. Cada requisito deve ter fonte/versionamento, implementação, teste
positivo/negativo, evidência no candidato e estado explícito. Não há percentual
global de conformidade defensável enquanto esse inventário não estiver fechado.

Prioridade imediata é a ordem 1, seguida das correções da ordem 2; XPM deve ser
investigado sem bloquear essas correções. Novas funções fora do template ESA
devem ter escopo explícito e não atrasar a avaliação restrita sem necessidade.

Atualização: identidade de regras recuperada em imagem de laboratório e comprovada
no e20240086, preservando todas as severidades. Data/ano de publicação ausentes
nesse candidato; ValueError em referências identificada, causa final pendente.
Repetição e20240135 com nova imagem bloqueada por reserva de memória. Ver
`H1_RULE_IDENTITY_QUALIFICATION.md`; nenhuma aprovação ou promoção de imagem ativa.

Correção seguinte: ano/volume/licença do e20240086 enriquecidos por snapshot DOI
conferido, sem gold. Regra local de ano das 52 referências deixou de lançar
ValueError; validação externa da nova candidata pendente. PDF identificado como
divergência de nome esperado, não ausência física. Ver
`H1_PUBLICATION_METADATA_CORRECTION.md`.

Pacote dessa candidata preparado, determinístico e offline válido. Triagem de
nomes PDF cobre presença/ausência/ambiguidade/traduções sem alterar a política de
aprovação. VPS abaixo da reserva de memória; nenhum envio da nova candidata.
Ver `H1_CORRECTED_PACKAGE_TRIAGE.md` para evidências e sequência.

Compatibilidade candidata implementada para PDF: basename real do XML, sem
renomear arquivos e sem silenciar ausências. Prova local nos dois pacotes e
15 cenários sintéticos; execução externa repetidamente impedida por reserva RAM.
Ver `H1_RENDITION_COMPATIBILITY.md`. Necessária margem estável antes de promover.
