# VH-02 — consultas XPM na VPS e limites de compatibilidade

Checkpoint: 2026-10-16. **Desenvolvimento parcial; XML/release/G-HOMOLOG não aprovados.**
Decisão posterior no mesmo dia: proprietário autorizou desenvolver a política
pontual descrita abaixo. ADR-019 e seção 29 do plano único controlam a execução;
autorização resolvida. Primeiro incremento posterior implementou as correções
cadastrais e duas regras DOI exatas; veja `VH1_JOURNAL_METADATA_AND_XPM_COMPATIBILITY.md`.
O diagnóstico e as contagens abaixo são históricos, anteriores a essas correções.
Mesmo item VH-02, sem fase nova. A execução Linux já estava comprovada; este
incremento acrescenta acesso externo controlado, auditoria e diagnóstico concreto.
Não altera a aplicação ativa, a política formal ou o código oficial do XPM.

## Implementado e executado

- Proxy temporário de laboratório, com rede Docker interna e sem porta publicada.
  Só o proxy possui saída externa; XPM não acessa as redes da aplicação.
- GET restrito ao catálogo oficial, com transporte elevado de HTTP a HTTPS e
  resposta integral preservada. CONNECT somente para Crossref e ORCID, porta 443,
  TLS ponta a ponta, DNS público verificado e conexão ao IP verificado.
- Recusa de endereços internos/metadata, outros destinos e métodos; limites de
  tempo, bytes, concorrência e requisições. Nenhuma chave/credencial foi necessária.
- Runner usa configuração documentada `ENABLED_WEB_ACCESS=on`; originais montados
  somente para leitura; fonte oficial conferida antes/depois. XPM: 384 MiB,
  0,5 CPU, usuário sem privilégios; proxy: 96 MiB, 0,25 CPU. Uma execução por vez.
- Auditoria confere fonte executada, imagem, hashes de entradas/relatórios/logs,
  catálogo efetivamente carregado, contagens nativas, controle negativo e saúde.
  Troca de evidência interrompe a auditoria; não existe aprovação por exit code.
- Comparação exata de título/editora com o cadastro, selecionado por coleção,
  dois ISSNs e sigla. Ausência/ambiguidade é recusada; não corrige automaticamente.

Arquivos: `ops/xpm_egress_proxy.py`, `ops/run_xpm_online_qualification.py`,
`ops/qualify_vh1_xpm_online.py`, `ops/audit_vh1_xpm_online.py` e
`deploy/Dockerfile.xpm-online-qualification`.

## Evidência final

Prova pública: `benchmarks/qualification/reports/vh1-xpm-online-v1.json`.
SHA-256: `8f0f8dc26171aa9dbf417153d6001a953df51f7c16b234e8a1405f3f1e51d8e2`.
Execução: `20261016T102428Z`; imagem imutável:
`sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63`.
Base offline previamente qualificada: `sha256:dfcc38f04950f075f03a6f1d48ab654ec4fc3be32c600c62b25ee76f9da98116`.
ZIP oficial intacto: `1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec`.

Evidências privadas (HTML/XML/logs/CSV) em
`benchmarks/private/output/vh1-xpm-online-20261016T102428Z` e
`/opt/idml-platform/private/qualification/vh1-xpm-online-20261016T102428Z`.
Ensaio exploratório `20261016T101825Z` preservado; não é a prova da fonte final.

| Caso | Bloqueios | Fatais | Erros | Avisos |
|---|---:|---:|---:|---:|
| e20240086 original | 3 | 2 | 5 | 2 |
| e20240135 original | 3 | 1 | 5 | 3 |
| e20240086 sem imagem gf01 | 4 | 2 | 5 | 2 |

Imagem removida detectada por mensagem específica nova. Nenhum caso é exemplo
de aprovação integral. Totais preservados, sem supressão/reclassificação. O HTML
legado requer recuperação do parser (100 registros em cada caso); isso continua
explícito. XMLs reempacotados diferem dos originais e não foram promovidos.
O DOCTYPE das saídas destes três casos permaneceu igual ao de entrada; o uso
interno de DTD antiga para validação não significa que a saída tenha sido rebaixada.

Catálogo: três respostas HTTPS 200, **516.455 bytes**, SHA-256
`003921e3d6597dd57406ef86885d140990a0174fe2b326be1e501be70dbfc00a`.
`Last-Modified: Wed, 03 Sep 2025 04:21:19 GMT`; não apresentar como catálogo
atualizado em outubro de 2026 apenas porque foi baixado nesta data.
Fonte: [catálogo oficial SciELO](https://static.scielo.org/sps/titles-tab-v2-utf-8.csv).

Houve 12 túneis Crossref e 13 ORCID: 24 encerramentos normais e um reset.
**Não equivalem a 25 respostas HTTP 200 nem provam autoria ORCID.** O XPM testa
URLs ORCID, não autenticação/titularidade; os controles próprios do projeto continuam.
Dez GETs para Wayta foram recusados, identificados por enumeração segura, sem
registrar nomes de instituições/URLs. Origem confirmada em `ws_institutions.py`.
Portanto `all_external_queries_completed=false`: não chamar Wayta de concluído
ou dispensado. Verificar sua disponibilidade/necessidade no executor antes de
ampliar a lista de destinos; falha deve continuar distinguível de XML incorreto.

Os 25 serviços mantiveram imagem/início/estado/saúde. Readiness, banco e Redis ok.
Tempo CLI por caso: 8,49–8,69 s; maior RSS de subprocesso: 62.532 KiB, não pico
total do container nem ensaio de carga. Pós-checagem: 1.201 MiB disponíveis e
13 GiB livres. Containers/rede temporários removidos; evidências e imagens
retidas para auditoria. Sem restart de app, ativação OpenClaw ou upgrade.

## Achados e encaminhamento — não são todos falsos positivos

| Grupo | Evidência | Ação delimitada |
|---|---|---|
| Cadastro do periódico | e86 usa `Engenharia Sanitária e Ambiental`; catálogo usa `Engenharia Sanitaria e Ambiental`. e135 já coincide | Corrigir representação de `journal-title` por fonte no pipeline, sem mudar título do artigo |
| Cadastro da editora | Ambos omitem ` - ABES` do valor oficial | Corrigir `publisher-name` por cadastro versionado, auditável e vinculado ao periódico |
| DOI legado | `generics/doi_validations.py` sempre acrescenta ERROR nas comparações de título do periódico/artigo quando há dados, mesmo com correspondência exata; só eleva para FATAL com baixa similaridade | Não alterar DOI correto. Preparar contraprova específica e proposta de compatibilidade; nenhuma dispensa aplicada |
| SPS/data | Regras nativas esperam 1.8/1.9 e rejeitam `pub`/`collection` de SPS 1.10 | Preservar marcação vigente; não adicionar `pub-type` legado para eliminar mensagem |
| JATS/DTD | Catálogo/Packtools incorporados não cobrem o perfil 1.3 do projeto | Decisão explícita de compatibilidade/entrega antes de encerrar VH-02/07 |
| Consultas | Wayta recusado; túneis TLS não provam resposta semântica | Não marcar conjunto de consultas completo; qualificar tratamento específico |

Os valores acima são metadados públicos de periódico; corpus e relatórios integrais
permanecem privados. Neste checkpoint, o comparador só diagnosticava: **essas três
ocorrências ainda não estavam corrigidas**. A correção posterior está documentada
em `VH1_JOURNAL_METADATA_AND_XPM_COMPATIBILITY.md`. VH-05 foi reaberta apenas
para esses dois campos; evidências anteriores continuam históricas e válidas
para seus hashes. Demais conteúdo/fórmulas/referências não são reabertos.

## Fontes normativas e decisão de compatibilidade

Reconsulta oficial `vh1-xpm-multiplatform-v2.json`, de 15/10, encontrou dez entradas;
a revisão mais recente listada continua R20231215. Não é prova da inexistência
de toda outra distribuição; não se encontrou substituta compatível nesse canal.

O [comunicado SciELO de 06/10/2025](https://groups.google.com/g/scielo-xml/c/MJHQuqRwsgs)
recomenda consultar SPS 1.10 e reconhece erros dos validadores antigos para certas
marcações novas; ressalva DOCTYPE. Não autoriza ignorar qualquer erro do XPM.
A [resposta oficial de 17/03/2026](https://groups.google.com/g/scielo-xml/c/KiC-TDlazJE)
também desaconselha o atributo legado `pub-type` naquele caso de `pub-date`.
A [issue técnica Packtools 814](https://github.com/scieloorg/packtools/issues/814)
relaciona SPS 1.10 a JATS 1.3, mas é tarefa de engenharia aberta, não autorização
de entrega que elimine a ressalva do comunicado. Não resolver a diferença por suposição.

**Política autorizada em 16/10 (ADR-019), parcialmente implementada no checkpoint posterior:** manter SPS/JATS do candidato,
relatório XPM original visível e exceções exclusivamente para regras legadas
individualmente comprovadas, com fonte, escopo/versionamento, contraprova e
validação independente. Nunca aceitar falha de consulta, cadastro divergente,
imagem ausente ou XML malformado como exceção. Não transformar homologação em
aceite SciELO; a publicação continua dependendo do aceite final/política formal.
A autorização cobre desenvolvimento/qualificação para homologação, não publicação
nem aprovação genérica de regras desconhecidas. A decisão derivada fica separada
da Release Policy, preservando bloqueios reais e a ressalva de DOCTYPE ainda não
resolvida. Nenhuma mensagem enviada à SciELO ou ativação da política realizada.

## Testes e próximo trabalho

**111 testes direcionados aprovados**, incluindo 62 testes novos de proxy/auditoria
e 49 anteriores; não somar reexecuções. JUnit: `tmp/vh1-xpm-online-tests.xml`.
Ruff e formatação dos seis arquivos novos aprovados. Gates existentes de validação
final e avisos continuam passando para seus checkpoints; o status histórico XPM
`unavailable` nesses relatórios não foi reescrito. Sem nova cobertura/suíte integral.

Reproduzir a auditoria local, sem nova consulta ou gravação de aprovação:

```powershell
.venv/Scripts/python -c "from pathlib import Path; from ops.audit_vh1_xpm_online import audit; r=audit(Path('benchmarks/private/output/vh1-xpm-online-20261016T102428Z')); print(r['release_approved'])"
```

**Próximo incremento deste checkpoint, posteriormente executado:** correção dos dois campos por cadastro em VH-05, com
proveniência/conflitos e testes; revalidar os novos pacotes exatos em VH-07.
Compatibilidade e Wayta permanecem em VH-02; sem repetir o ensaio idêntico ou
buscar Windows. A autorização geral está resolvida; VH-08 pode avançar conforme
o plano único. Integração web supervisionada/hardening continuam VH-14/16;
G-HOMOLOG continua fechado. Os vinte IDs não aumentaram.
