# VH1 — Entrega técnica do lote 1

2026-10-01. Executa **VH-01/02/03**, sem criar outra fila de desenvolvimento.
Controle: `HOMOLOGATION_VH1_DELIVERY.md`. Não autoriza publicação nem homologação.

## VH-01 — Uma referência reproduzível

`config/validator-registry-vh1.json` seleciona as imagens candidatas já qualificadas
em laboratório, sem trocar o registro ativo `validator-registry-v1.json`:

| Componente | Base fixada |
|---|---|
| Perfil candidato | `profiles/esa-aop-1.1.json`, ESA 1.1.0, JATS 1.3/SPS 1.10 |
| Packtools | imagem `113366e7788c…`; distribuição observada `4.17.2rc20260909` |
| SPS Validator | imagem `9549ba39d357…`; distribuição `0.3.0`; Packtools interno `4.16.9rc20260909` |
| Python das imagens | 3.12.14 / Linux x86_64 |
| Aplicação ativa | preservada; não é a candidata deste lote |

O rótulo de versão do adapter não substitui a versão observada da distribuição.
As ferramentas são dois executores distintos; não se afirma que compartilham o
mesmo Packtools. O manifesto fixa **o par**, suas dependências, árvores nativas e
wrappers. Daqui em diante o comparativo de cada ferramenta usa a sua própria
imagem fixa. O ensaio Windows anterior não é equivalente ao Linux por ter um
número de versão parecido. Atualizar uma imagem implica novo manifesto e teste.

`ops/vh1_baseline.py` produz um manifesto único contendo fonte, DTDs vendorizadas,
perfil, lockfiles, registro, scripts de execução, imagens e inventário real de
dependências. Reprocessa localmente os dois IDMLs autorizados, duas vezes, com os
catálogos já qualificados; exige XML idêntico e o mesmo diagnóstico offline,
inclusive igualdade com os candidatos anteriores. Não lê gold nem envia corpus.

O modo `--check` recusa qualquer divergência de fonte/runtime/configuração/entrada.
O modo de criação não sobrescreve evidência anterior. Saída pública: hashes,
versões e contagens, nunca textos ou catálogos. Fonte da candidata ainda em
desenvolvimento não é imagem de release; a imagem integrada será construída e
inventariada em VH-14/16. Esta base não substitui a revalidação real VH-04/07.

Execução administrativa (com chave/host fornecidos pelo operador):

```powershell
.venv\Scripts\python.exe -m ops.vh1_baseline --ssh-key CAMINHO_DA_CHAVE --host USUARIO@HOST --output benchmarks/qualification/reports/vh1-lot1-baseline-v1.json
# Repetir os mesmos argumentos com --check para verificar a base.
```

## VH-02 — Distribuição obtida; execução/compatibilidade pendentes

Investigação primária em 2026-10-01:

- O [repositório PC-Programs](https://github.com/scieloorg/PC-Programs/releases)
  informa arquivamento em 16/03/2026 e não oferece releases nessa página.
- A página [Package Maker](https://documentacao.scielo.org/books/scielo-pc-programs/page/como-validar-o-pacote-xml-sps)
  descreve o XPM já conhecido, não um sucessor comprovadamente compatível.
- O [canal de download publicado](https://documentacao.scielo.org/books/scielo-pc-programs/page/download)
  aponta para FTP. A primeira consulta falhou (`vh1-xpm-discovery-v2.json`), mas
  a conclusão de impedimento externo foi corrigida: nosso script decodificava
  UTF-8 como Latin-1 e interpretava o separador NBSP como parte da senha pública.
  Leitura corrigida e testada; listagens autenticadas das duas pastas oficiais
  realizadas (`vh1-xpm-multiplatform-v1.json`, `vh1-xpm-windows-v1.json`).
- O [comunicado SciELO de outubro de 2025](https://groups.google.com/g/scielo-xml/c/MJHQuqRwsgs)
  menciona limitações dos validadores diante da marcação 1.10. É evidência histórica,
  **não** comprovação de que nenhuma distribuição nova exista em outubro de 2026.

Após autorização do proprietário, o ZIP oficial `SciELO_XPM_4.0.096-R20231215.zip`
foi baixado diretamente pela VPS: **4.567.599 bytes**, SHA-256
`1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec`, igual ao registro
anterior. É a revisão mais recente listada nas duas pastas consultadas, não uma
versão SPS 1.10 comprovada. Arquivado sob
`/opt/idml-platform/private/vendor/xpm/<sha256>/`, root:root, 0600.
455 entradas inspecionadas, sem extração/execução, traversal ou symlinks; dependências
declaradas ainda são Packtools 2.4.2 e Pillow 6.2.2. Evidência: `vh1-xpm-download-v1.json`.
O transporte FTP não oferece TLS; integridade foi conferida contra o hash já fixado.

Não falta mais acesso/instalador fornecido pelo usuário. Falta qualificar executor
isolado e compatibilidade aplicável ao SPS 1.10, incluindo positivo/negativo e
relatório vinculado ao pacote. A ADR-002 ainda prevê Windows; download do ZIP
multiplataforma em Linux não demonstra execução headless e não altera essa decisão.
Não instalar dependências antigas globalmente nem modificar XML para simular suporte.
Qualquer alteração de política deve ser explícita e fundamentada. VH-02 não está
concluído e G-HOMOLOG permanece indisponível; os demais itens podem prosseguir.

O contrato existente continua exigindo versão/hash da ferramenta, hash do pacote
exato, hash do relatório, comando, ambiente e totais explícitos. HTML de referência
não atesta a execução de um candidato novo. O aceite requer positivo e negativo
no executor compatível; não foi realizado nesta etapa.

## VH-03 — Provisionamento com autorização verificável no servidor

Implementados:

- Bundle `enrichment-bundle-1.1`, com referência a autorização separada.
- `source-authorization-1.0`: empresa, artigo, IDML, perfil, destino `local` ou
  `vps`, hashes de catálogos/evidências, referência à decisão registrada, validade
  e revogação. Uma autorização local não serve à VPS.
- Prazo máximo do grant: 30 dias; fonte Crossref: no máximo 7 dias desde coleta;
  evidência de artigo/editorial: no máximo 30 dias nesta política inicial. Relógios
  sem fuso, futuros, grant expirado/revogado e escopos diferentes são recusados.
- Releitura da autorização a cada seleção, sem cache de aprovação. Histórico de
  jobs conserva o hash usado, mas não autoriza novas execuções após revogação.
- Manifestos 1.0 não passam como autorizados. Falta de root/destino/grant não
  habilita fallback silencioso para um bundle presente e inválido.
- Instalador administrativo `ops/provision_enrichment.py`: valida em área temporária,
  promove o diretório completo, não sobrescreve bundle existente e nunca cria consentimento.

### Onde ficam os dados

Root privado definido pelo operador; na VPS, proposta para VH-14:
`/opt/idml-platform/private/enrichment`. Não provisionado neste lote.

```text
root privado (administrador escreve; worker somente lê)
  authorizations/<authorization_id>.json
  <sha256(empresa:artigo:IDML)>/
    manifest.json
    formula_catalog.json                 # somente se autorizado
    crossref_metadata_catalog.json       # somente se autorizado
    formal_metadata_catalog.json         # somente se autorizado
    editorial_enrichment_catalog.json    # somente se autorizado
```

`IDML_ENRICHMENT_LOCATION` é obrigatório quando há root configurado. O upload/job
não escolhe diretórios nem escreve autorizações. A fronteira de confiança é o
administrador e as permissões do volume, **não uma assinatura criptográfica**;
um hash de decisão documenta sua identidade, não prova sozinho consentimento.
VH-14 deve montar o root read-only no worker, negar escrita ao app/IA e testar
permissões. Não expor o diretório por HTTP, CI, imagem, Git ou logs.

### Fluxo de operador (não trabalho oculto por artigo na interface)

1. Registrar a decisão do proprietário fora do diretório de uploads; guardar ID
   e hash da decisão. Não emitir grant porque uma IA sugeriu ou um arquivo declarou.
2. Coletar somente as fontes permitidas; preservar original privado, horário e hash.
   Catálogo transformado mantém seu próprio hash e contrato de evidência existente.
3. Emitir autorização privada com escopo/destino exatos em `authorizations/`.
4. Preparar manifest 1.1 e catálogos em diretório administrativo de entrada.
5. Executar `python -m ops.provision_enrichment --root ROOT --incoming ENTRADA
   --location local` (ou `vps`, **no host autorizado**). Não há transferência remota
   embutida no comando. Rejeição deixa o bundle final ausente.
6. Consumidor registra hashes e validade no job. Para revogar, administrador muda
   o status da autorização para `revoked`; novas seleções falham. Não apagar histórico.
7. Renovação exige rever a autorização e recoletar fontes expiradas. Nunca prolongar
   automaticamente o prazo nem sobrescrever evidência para fazer a validação passar.

A automação de coleta/associação em uso normal continua em VH-04/11/14; este lote
entrega o contrato e o instalador administrativo seguro, não a tela final.

### Fontes identificadas e limites

| Uso | Fonte admissível | Limite |
|---|---|---|
| Texto, representação, fórmulas | IDML/PDF/imagens do próprio artigo autorizados | Sem gold como entrada; transcrição científica não ganha aplicação IA autônoma |
| DOI | Resposta pública Crossref `/works/{doi}`, coletor já existente | Consulta pelo DOI, não upload do artigo; metadados ainda comparados nativamente; validade 7 dias |
| ORCID | Registro público oficial ORCID do identificador existente | Coleta/adapter em VH-04; ausência/inacessibilidade não é sucesso nem permite inventar ID |
| Periódico/volume/fascículo | [Grade oficial ESA/SciELO](https://www.scielo.br/j/esa/grid), ou exportação autenticada da coleção | ISSN e volume/ano vinculados; não usar o próprio XML como autoridade |
| Seção/sumário | Registro editorial de seções da coleção/periódico; sumário oficial do fascículo como evidência específica | Lista esperada não pode ser copiada dos valores a validar; exportação ou confirmação editorial quando necessário |
| Datas, CRediT, financiamento | Evidência do artigo e/ou registro editorial autorizado | Divergência exige triagem em VH-05; consulta externa não autoriza substituir conteúdo automaticamente |

A grade pública identifica 2025/volume 30; isso **não resolve sozinho** a seção ou
o contexto completo exigido pelo validador. A injeção desse contexto será VH-04.
Snapshots de validação ficam separados dos catálogos de conversão, privados no
host do broker, somente leitura durante a execução. O transporte DOI já confere
hash do XML/ZIP e expiração; estender fontes não libera rede no validador.

### Autorização recebida e armazenamento preparado

O proprietário autorizou explicitamente nesta conversa o armazenamento dos
catálogos/registros e dados necessários na VPS. Registro:
`authorizations/VH1_VPS_DATA_20261001.md`, SHA-256
`dd8ce44956daabfcf738bb7116dbb221c9c85eaf8db5100d5469ace70fba5086`.

Foram enviados seis catálogos, dois snapshots Crossref e seus manifestos de coleta,
dois XMLs/ZIPs candidatos e a decisão: 15 arquivos (2.860.458 bytes), além do manifesto.
Todos os hashes conferidos após SCP, em
`/opt/idml-platform/private/source-vault/25ca4293d4e180ad32b7751b50fd30cd0f66ace056ff7226cddf01640b69b1e8`.
Diretórios root:root 0700, arquivos 0600; nada conectado ao worker ativo.
Não houve envio de IDML, gold ou holdout. Datas de coleta mantidas; snapshot foi
verificado quanto a validade e vínculo com o XML/ZIP antes do envio.

Isso prepara o armazenamento, **não** um bundle ativo vinculado à empresa/artigo.
O consumo e as autorizações específicas do runtime continuam em VH-04/14.
Evidência minimizada: `vh1-vps-source-staging-v1.json`. Scripts administrativos
`stage_vh1_authorized_sources.py` e `verify_vh1_private_vault.py` recusam escopo,
hash, caminho, inventário ou arquivos adicionais divergentes.

## Verificação e encerramento

Regressão: **803 aprovados**, três avisos, cobertura **88,07%**. Os 75 testes
direcionados são um subconjunto desse total. Os novos testes cobrem vínculo de escopo/hash, origem incompatível,
prazo, revogação, destino, instalação sem sobrescrita e drift de runtime.
V10 é requalificado com execução nova dos workflows; o relatório antigo é preservado.

Manifesto executado: `benchmarks/qualification/reports/vh1-lot1-baseline-v1.json`.
XMLs finais reproduzidos (após a normalização de nomes dos assets pelo empacotador):
e20240086 `7081d302358f8c022114a0ebf568372af43e115bda38a748cc7c2ebbc1494ad0`;
e20240135 `1757cdb3a15b7fd44beb009e794ff812995eb59cd6e2c1eee2cabee15f9a9706`.
ZIPs também idênticos aos candidatos anteriores. Isso prova reprodutibilidade,
não ausência dos achados editoriais já conhecidos nem aprovação formal.

O próximo desenvolvimento, depois de fixada a base, é **VH-04**: contexto editorial,
ORCID e DOI dos dois artigos nos executores fixos. Não repetir ensaios sem mudança
nem anunciar XML aprovado antes de VH-07 e XPM compatível.

### Verificação após download e transferência autorizados

60 testes direcionados aprovados (XPM/download, inventário privado e autorizações),
Ruff e gate V10 aprovados. O total 803/88,07% acima refere-se à regressão anterior,
não foi somado aos testes deste incremento. `tmp/vh1-vps-sources-tests.xml`.
Base requalificada em `vh1-lot1-baseline-v2.json` após mudança dos scripts ops,
preservando v1; imagens, perfil e XMLs/ZIPs não foram alterados. Readiness da VPS:
banco e Redis `ok`; API/worker seguem na imagem `4fcf4766…`, sem implantação.
