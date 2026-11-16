# VH-04 — fontes editoriais e ORCID no runtime fixado

Nota de continuidade — 2026-10-03: este documento preserva o checkpoint nativo.
A integração adapters/broker/worker que constava como próxima ação foi concluída
e qualificada em `VH1_SCOPED_VALIDATOR_INTEGRATION.md`. Ativação permanece em
VH-14/16; o próximo desenvolvimento é VH-05. As limitações históricas abaixo
não substituem o estado atual da lista única `HOMOLOGATION_VH1_DELIVERY.md`.

Checkpoint: 2026-10-01. **Qualificação nativa aprovada; integração operacional
ainda pendente. VH-04 permanece parcial e G-HOMOLOG não liberado.**

## Entrega deste incremento

- Coletor com origens HTTPS permitidas, sem seguir redirecionamentos, orçamento
  de resposta, timeout e nenhuma credencial nova. Fontes privadas fora de Git.
- Contexto de fascículo/seções obtido do ArticleMeta, independente dos valores
  candidatos. Escopo qualificado: ESA, coleção `scl`, fascículo contínuo de 2025,
  perfil `esa-aop-1.1.0`. Não é um cadastro universal de periódicos/fascículos.
- Manifestos vinculam XML, perfil, origem, hash dos registros e data da coleta.
  Validade máxima de sete dias; cópia não renova a coleta. A verificação rejeita
  outro candidato/periódico/ano, adulteração, fonte incompleta e tempo inválido.
- Parâmetros são fornecidos apenas aos grupos nativos de fascículo, seção e
  colaboradores. Nenhum nível de severidade ou resultado nativo é substituído.
  As funções são restauradas ao sair do contexto, inclusive em falha. Uso é
  síncrono, em processo isolado para um candidato; não usar em threads concorrentes.
- Evidências explícitas são observadas antes de o SPS descartar linhas `OK`.
  Ausência de erro não é utilizada como evidência de execução/aprovação.

Código principal: `ops/editorial_authority.py`, `editorial_authority_runtime.py`,
`collect_vh1_editorial_sources.py`, `probe_vh1_editorial.py`,
`prepare_vh1_editorial_qualification.py`, `run_vh1_editorial_linux.py`.

## ORCID: registro público, associação editorial e identidade são diferentes

Os quatro ORCIDs do e20240135 responderam pela API pública oficial. Seus nomes
públicos não são iguais aos nomes completos do XML. Não houve alteração de autoria,
expansão de iniciais, remoção de acentos, reordenação de nomes ou troca de ORCID.

Política implementada para a consulta:

1. ORCID precisa ter formato/checksum válido, pertencer ao XML e responder com o
   registro correspondente. Falha de rede, registro ausente e redirecionamento
   não confirmam o identificador.
2. Nome público completo igual ao XML, após apenas NFC/caixa/espaços, confirma
   consistência. `family-name` pode ser ausente quando `given-names` contém o
   nome completo; comparação continua literal, sem aproximação.
3. Havendo diferença, só se aceita confirmação cruzada se o snapshot Crossref
   confiável do **mesmo DOI/ISSN/XML**, íntegro e vigente, contiver exatamente um
   autor com o mesmo ORCID e o mesmo nome completo. Os quatro casos reais
   satisfazem essa condição. A proveniência fica explícita como
   `public_registry_and_crossref_author_match`, não `public_record_and_name_match`.
4. Sem confirmação, resultado `unconfirmed`/`name_not_confirmed`: pendência de
   consistência, não falha de rede. Dados indisponíveis continuam `unknown`, e
   o normalizador mantém o bloqueio de consulta não concluída.

Isso verifica existência do registro e associação depositada à publicação;
**não prova controle da conta, autenticação OAuth do autor ou identidade civil**.
A diferença de nomes permanece registrada para o roteiro do especialista.
Crossref é também fonte de enriquecimento já utilizada: esta prova não constitui
um corpus independente nem validação científica/autoral independente.

## Prova real na VPS

Relatório: `benchmarks/qualification/reports/vh1-editorial-linux-v1.json`.
Gate source-bound: `python -m ops.gate_vh1_editorial`.

Imagens nativas originais de VH-01 preservadas:

- Packtools `sha256:113366e7788c111faada2ef2cb6bc218c1c1b5061dca447fd462ce0216bc23ae`.
- SPS `sha256:9549ba39d357854d51c3a1af3d11adc8a0583b83e12092928e808e76f706ad6d`.

Os testes usam essas imagens **mais um executor de qualificação montado somente
para leitura e identificado por hashes**. Não se afirma que as imagens originais
já contêm a nova integração. Bibliotecas nativas não foram atualizadas e as duas
versões internas de Packtools continuam diferentes conforme o inventário de VH-01.

| Candidato | DOI / fascículo / seção, por ferramenta | ORCID, por ferramenta | Achados restantes, por ferramenta |
|---|---|---|---|
| ESA e20240086 | 1 / 1 / 1, todos aprovados | 0: não há identificadores a consultar | 22 críticos, 4 erros, 9 avisos |
| ESA e20240135 | 1 / 1 / 1, todos aprovados | 4 confirmados com ORCID + Crossref | 6 críticos, 0 erros, 5 avisos e 4 informativos |

As contagens coincidem entre as ferramentas neste ensaio; não somá-las como
defeitos únicos. Ausência de ORCID no e20240086 não foi aprovada: os achados de
metadados de colaboradores continuam no relatório e em VH-05.

Contraprovas executadas nos dois runtimes:

- Volume e seção incorretos são rejeitados pela regra nativa.
- Nome de autor adulterado não ganha aprovação pelo registro Crossref original.
- Sem autoridades, voltam dois bloqueios de consulta no primeiro artigo e três
  no segundo; nenhuma consulta faltante se transforma em sucesso.
- XMLs e ZIPs de referência permanecem com os mesmos hashes. As mutações de
  contraprova existem somente em memória, não como artefato de release.

Não houve leitura de gold/holdout, chamadas IA, envio a revisores, publicação,
troca de imagem da aplicação, reinício de API/worker ou alteração de flags.
Readiness final: banco e Redis `ok`; imagens API/worker mantidas.

## Armazenamento e segurança

Autorização aplicável: `authorizations/VH1_VPS_DATA_20261001.md`.
Coleta original: `benchmarks/private/output/vh1-editorial/20261001T214623Z`.
Pacote qualificado na VPS:
`/opt/idml-platform/private/qualification/vh1-editorial-upload-e74af5ed56fc7960`.
Hash do manifesto de qualificação:
`e74af5ed56fc7960584b51225759e9a5ddec0c749a2831b7d88bf876ee89b89a`.
Diretórios privados root:root 0700; registros 0600. O pacote ocupa 208 KiB em disco.

Uma execução por vez, sem rede no container, usuário não root, filesystem somente
leitura, sem capabilities, 192 MiB e 0,25 CPU; reservas originais mantidas.
Scratch root-owned fica em `/var/lib/idml-vh1-qualification`, não em `/run` (tmpfs
pequeno que corretamente reprovou a reserva de disco na primeira tentativa).
Os diretórios temporários específicos são removidos ao concluir; fontes/evidências
privadas são preservadas. Nenhum diretório amplo ou dados anteriores são apagados.

## Testes e limites de conclusão

- Suíte integral: **867 aprovados**, 3 avisos, cobertura **88,07%** de
  `src/idml_foundation`; scripts `ops` não entram nessa porcentagem.
- 121 testes direcionados estão incluídos nesses 867, não são adicionais.
- Depois da suíte, 12 testes novos do gate source-bound passaram separadamente.
  Não afirmar uma execução integral de 879 testes neste checkpoint.
- Ruff dos arquivos novos, gate nativo VH-04 e V10 aprovados.
- Base atual: `benchmarks/qualification/reports/vh1-lot2-baseline-v1.json`;
  fingerprint de fonte `c403c3644921305e37e059cb97bd454c0ece287576255b52ab444a42a4ba0a79`.
  Inventário real das imagens e reprocessamento local dos dois artigos em duas
  execuções preservam XML/ZIP. Bases anteriores permanecem históricas, sem
  sobrescrita; a base nova não representa implantação do executor de qualificação.
- Arquivos locais: `tmp/vh1-editorial-tests.xml`, `tmp/vh1-editorial-coverage.json`.

VH-04 **não está concluído operacionalmente**. Próxima ação, ainda no mesmo ID:
empacotar a integração nos adapters candidatos e transportar as autoridades pelo
broker com seleção administrativa, vínculo de empresa/artigo/candidato, revogação,
expiração e montagens mínimas; qualificar pelo contrato real do worker/socket.
Não apontar o worker diretamente para o cofre, não aceitar caminhos enviados
pelo cliente e não enfraquecer a exigência root-owned dos diretórios confiáveis.
Implantação/ativação permanecem em VH-14/16.

Em seguida, VH-05 trata os achados de datas/histórico, afiliações, CRediT,
financiamento e ORCID ausente; VH-06 trata conteúdo/vínculos; VH-07 fecha o XML.
Os seis críticos do segundo artigo concentram-se em quatro afiliações sem estado
e duas datas de histórico exigidas pelo runtime. São itens de triagem/correção
com fonte e aplicabilidade, **não autorização para inventar dados ausentes**.
XPM (VH-02) continua pendente de execução/compatibilidade, apesar do download feito.

## Fontes oficiais consultadas

- [Cliente oficial ArticleMeta](https://github.com/scieloorg/articlemetaapi/blob/master/articlemeta/client.py): endpoints públicos de fascículos.
- [Xylose / modelo Issue](https://github.com/scieloorg/xylose/blob/master/xylose/scielodocument.py): mapeamento `v31`, `v32`, `v49`.
- [Fascículo ESA 2025, volume 30](https://www.scielo.br/j/esa/i/2025.v30/?ilang=pt_BR): conferência do fascículo público.
- [ORCID — leitura de registros](https://info.orcid.org/documentation/api-tutorials/api-tutorial-read-data-on-a-record/): consulta pública, conteúdo e limites de autenticação.

A qualificação utiliza consultas públicas anônimas pontuais. Não provisiona
credenciais ORCID, não autentica autores e não promete disponibilidade ilimitada
da API para produção; limites/termos e operação de coleta entram no provisionamento.
