# VH-04 — integração candidata por empresa, artigo e versão do pacote

Checkpoint: 2026-10-03. Ensaios Linux: 2026-10-02.
**Desenvolvimento e qualificação da integração concluídos; não implantada na
aplicação ativa. XML integral e G-HOMOLOG continuam não aprovados.**

Este checkpoint encerra o trabalho de adapters/broker/worker previsto em VH-04.
Complementa `VH1_LOT2_EDITORIAL_AUTHORITIES.md`, preservando aquele ensaio nativo.
Não cria nova fase. Ativação supervisionada e provisionamento para os IDs reais
da empresa piloto pertencem a VH-14/16; fluxo implantado completo, a VH-18.

## Entrega implementada

- Adapters candidatos de Packtools e SPS consomem somente fontes selecionadas
  pelo servidor, montadas individualmente e somente para leitura. DOI, ORCID,
  fascículo e seção conservam evidência explícita no resultado. Não alteram XML,
  não reduzem severidades e não substituem biblioteca/regra nativa.
- Contrato de socket `local-validator-1.1`, separado do legado 1.0. A seleção
  inclui empresa, artigo, hash do IDML, perfil, XML e ZIP. O worker obtém esses
  campos dos registros da própria empresa e dos bytes finais, não do JSON enviado
  pelo usuário. Snapshot de outra fonte ou perfil é recusado.
- Bundle `validation-authority-bundle-1.0` vinculado a grant administrativo
  `validation-authority-grant-1.0`, decisão, destino VPS, validade e hashes.
  Revogação, expiração, fonte alterada ou ausência não produzem aprovação.
  O grant e os arquivos são conferidos novamente após a execução nativa.
- `ops/provision_scoped_authorities.py` instala atomicamente sem sobrescrever
  bundle anterior. Exige grant já instalado; não emite consentimento nem renova
  datas de coleta. Snapshot editorial/Crossref tem TTL de sete dias; grant tem
  duração máxima de trinta dias. Um não substitui a validade do outro.
- Seleção confiável exige diretórios ancestrais root-owned, sem escrita por
  grupo/outros, sem symlinks. O cliente não escolhe caminhos nem recebe o cofre
  inteiro, arquivo de autorização ou socket Docker. O broker permanece serial.
- Configuração opcional: `IDML_VALIDATOR_SCOPED_AUTHORITIES`,
  `IDML_VALIDATOR_REGISTRY_PATH` e `IDML_JOURNAL_PROFILE_PATH`, além do socket.
  O modo novo exige configuração explícita; o padrão continua desativado.

O contrato de autorização de enriquecimento entregue em VH-03 continua separado.
Não reutilizar implicitamente um grant de enriquecimento como grant de validação.

## Imagens e evidências verificáveis

Registro candidato: `config/validator-registry-vh1-scoped.json`.
O registro ativo da aplicação e o registro-base anterior não foram substituídos.

| Ferramenta | Nova imagem candidata imutável | Versão nativa mantida |
|---|---|---|
| Packtools | `sha256:8b10e0d37580ed5c018e86049281010968eac05ee07e4cbc640cc9f2358aa266` | `4.17.2+ef0e6f874ea7`; distribuição `4.17.2rc20260909` |
| SPS | `sha256:3832b370222634f1eb9ddbd8aa9aa74e31acf2ee4e2cfba398eb72ff3d918ff7` | `0.3.0+d1aa774d4e33`; Packtools interno `4.16.9rc20260909` |

`vh1-scoped-images-v1.json` compara as árvores das bibliotecas e dependências com
`vh1-lot2-baseline-v1.json`; são idênticas. Verifica também os hashes dos wrappers
copiados nas imagens. As duas versões internas de Packtools não foram confundidas.
O build só acrescenta código, nunca conteúdo de artigo, credenciais ou catálogos.

`vh1-scoped-socket-v1.json` registra duas ferramentas para cada artigo, usando
o cliente real e `assess_package`, socket Linux e containers isolados. O cliente
rodou sem privilégios numa instância temporária da imagem da aplicação, com o
código candidato montado para leitura, sem alterar o worker em execução.

| Artigo | DOI / fascículo / seção por ferramenta | ORCID presente por ferramenta | Achados restantes por ferramenta |
|---|---|---|---|
| e20240086 | 1 / 1 / 1 positivos | nenhum ORCID presente | 22 críticos, 4 erros, 9 avisos |
| e20240135 | 1 / 1 / 1 positivos | 4 positivos | 6 críticos, 0 erros, 5 avisos |

ORCID confirmado significa registro público mais associação nome–ORCID no
Crossref do mesmo DOI; não significa autenticação da conta do autor. Zero ORCID
no primeiro artigo não aprova a ausência desse metadado. As contagens das duas
ferramentas não devem ser somadas como defeitos únicos.

Contraprovas pelo socket: outra empresa, outro artigo, XML modificado,
autorização revogada e expirada. Todos os cenários permanecem não aprovados.
Na alteração somente do XML, Packtools recusa esse XML; SPS ainda conclui o ZIP
original, que não foi alterado. Isso não valida o par XML/ZIP divergente.

O laboratório usou IDs **sintéticos** de empresa/artigo, identificados como tal,
e grants temporários sob o consentimento já registrado para testes/armazenamento.
Não criou grant operacional para uma empresa real. O ensaio local de API/DB/worker
confere a derivação do escopo com executor simulado; o ensaio Linux separado
confere o transporte real. Não apresentar a combinação como E2E implantado.

Plano privado da execução bem-sucedida:
`/opt/idml-platform/private/qualification/vh1-scoped-socket-20261002T113237Z`;
SHA-256 do plano `2ccbe233c7b7b931a96f8b15d76eb333887a0f1ae3d1d4d0822e56372320c49a`.
Os ensaios anteriores que falharam por Python 3.10/versão de contrato de registro
foram corrigidos e não são evidência de aprovação. O relatório público é da
execução bem-sucedida. Os grants/scratch e o broker temporário foram removidos
ao encerrar o laboratório; fontes e relatórios privados foram preservados.

## Verificação final

- **938 testes aprovados**, três avisos, cobertura de linhas **88,09%** de
  `src/idml_foundation`. Não é porcentagem de aprovação XML; scripts `ops` não
  entram nessa medição. Os 108 testes focados e os 18 testes do novo gate estão
  incluídos no total, não são testes adicionais a somar.
- Artefatos locais: `tmp/vh1-scoped-all-tests.xml`,
  `tmp/vh1-scoped-coverage.json`, `tmp/vh1-scoped-workflow.xml`.
- V10 reexecutado, com relatório novo `v10-operational-workflow-vh1-scoped-v1.json`;
  gate nativo e novo gate `python -m ops.gate_vh1_scoped` aprovados. O novo gate
  recusa código/imagem divergentes, evidência ausente, escopo cruzado, bibliotecas
  alteradas e ausência de contraprovas. Ambos adicionados ao CI.
- Ruff lint global aprovado; tipagem dos seis módulos de aplicação envolvidos e
  formatação dos 22 arquivos verificados deste incremento aprovadas.
  `ruff format --check .` ainda aponta dois scripts históricos fora deste escopo:
  `qualify_doi_socket_linux.py` e `qualify_doi_transport_linux.py`. Não foram
  reformatados para não invalidar evidências antigas sem requalificação. É uma
  pendência de higiene de CI a resolver em VH-17, não um teste de XML aprovado.
- Readiness da VPS: banco/Redis `ok`; API/worker saudáveis e na mesma imagem
  `sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`.
  Nenhum serviço existente reiniciado ou flag IA alterada. Sem chamada IA nesta etapa.

## Continuidade, sem ampliação do escopo

1. **VH-05:** tratar os metadados restantes com regra e fonte: afiliações/estado,
   histórico/datas, CRediT e financiamento. Os seis críticos do e20240135 incluem
   quatro afiliações sem estado e duas exigências de histórico; verificar
   aplicabilidade antes de corrigir. Não inventar datas nem substituir por IA.
2. **VH-06/07:** conteúdo e revalidação integral dos candidatos corrigidos.
   Qualquer mudança de XML/ZIP exige novas evidências vinculadas aos novos hashes.
3. **VH-14/16:** identidade real da empresa/artigo, provisionamento/renovação
   governados, serviço supervisionado e ativação. O uso normal não poderá exigir
   preparação oculta manual por artigo; cumprir o fluxo da lista única.
4. **VH-02:** XPM segue obrigatório, pendente de execução e compatibilidade SPS 1.10.

Não há aceite SciELO, liberação ao especialista ou aprovação formal integral neste
checkpoint. A lista principal continua `HOMOLOGATION_VH1_DELIVERY.md`.
