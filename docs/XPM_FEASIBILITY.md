# Viabilidade do XML Package Maker (XPM)

Atualização vigente — **2026-10-16: consultas restritas e catálogo real na VPS**.
`vh1-xpm-online-v1.json` vincula três execuções à fonte/imagem, relatórios e catálogo
HTTPS. Crossref/ORCID acessíveis não significam todas as consultas concluídas;
Wayta foi recusado. Encontradas divergências reais no título/editora, regra DOI
com falso positivo e incompatibilidades SPS/JATS. 111 testes direcionados aprovados,
serviços preservados. VH-05 reaberta para dois campos; VH-02/07 continuam parciais.
`VH1_XPM_ONLINE_AND_COMPATIBILITY.md` registra a política pontual autorizada
posteriormente em 16/10 (ADR-019), ainda não implementada/ativada; nenhum erro foi
dispensado. Não falta autorização geral, Windows ou instalação.

Atualização histórica — **2026-10-15: execução headless comprovada na mesma VPS**.
O proprietário autorizou instalações e determinou manter todos os componentes
na VPS atual. `vh1-xpm-linux-v1.json` registra cinco execuções: dois artigos reais
e três contraprovas, todas com relatório original. Não foi necessário Windows,
Wine, desktop virtual ou modificar fonte do XPM. A conclusão anterior sobre
Windows era excessiva: os erros de log/Tk mostravam ambiente incompleto.
Detalhes: `VH1_XPM_LINUX_QUALIFICATION.md`; ADR-002 revisada.
**Ainda não há aprovação SPS 1.10, consultas externas concluídas ou integração
ao serviço web ativo.** As atualizações abaixo são históricas.

Atualização 2026-10-14: `vh1-xpm-preflight-windows-v1.json` verifica uma cópia do ZIP
oficial já obtido, com mesmo hash, e o intérprete local Windows Python 3.11.3.
Tkinter foi localizado; Pillow/Packtools não estão instalados nesse intérprete.
Nenhum XPM foi extraído/executado nem software instalado. Não é demonstração de
incompatibilidade com Python 3.11: é pré-verificação de ambiente não preparado.
O executor dedicado/sem privilégios ainda não foi definido. Antes de criar
conta/serviço, o proprietário deve indicar host Windows ou autorizar preparo
isolado neste computador. A VPS Linux e a aplicação ativa não foram alteradas.
VH-07 agora tem Packtools/SPS, consultas e triagem completos na candidata, mas
continua parcial por VH-02. Não substituir XPM pelos demais validadores.
Detalhes: `VH1_FINAL_VALIDATION_AND_WARNINGS.md`.

Atualização 2026-10-01, VH-02: **distribuição oficial baixada na VPS; execução e
compatibilidade SPS 1.10 ainda pendentes**. Evidência: `vh1-xpm-download-v1.json`.
O FTP funciona. A falha anterior ocorreu em nosso leitor da página UTF-8: o
espaço inseparável foi decodificado incorretamente e usado como senha. Corrigido
e coberto por regressão; não era prova de indisponibilidade do acesso oficial.
Nas pastas oficiais `xpm/multiplatform` e `xpm/Windows`, a revisão mais recente
listada foi 15/12/2023. ZIP de 4.567.599 bytes e SHA abaixo conferidos; 455 entradas
inspecionadas sem extração/execução. Não instalado nem conectado ao sistema ativo.
Detalhes em `VH1_LOT1_BASE_AND_SOURCES.md`; exigência XPM não dispensada.

## Classificação

```text
CLASSIFICATION: GO_WITH_CONSTRAINTS
UNTOUCHED_LINUX_HEADLESS: PROVEN_OFFLINE_AND_RESTRICTED_ONLINE
INTEGRATION_PATH: ISOLATED_LINUX_WORKER_ON_EXISTING_VPS
SPS_1_10_COMPATIBILITY: NOT_PROVEN_LEGACY_RULES_REJECT_CURRENT_PROFILE
RELEASE_ROLE: REQUIRED_EXTERNAL_GATE_WHEN_APPLICABLE
```

## Função e exigência

O [guia de entrega SciELO](https://www.scielo.org/documents/57/guia_entrega_pacotes.pdf) inclui `xpm.html` no pacote. A [documentação oficial do XPM](https://documentacao.scielo.org/books/scielo-pc-programs/page/xml-package-maker-xpm) descreve a geração dos pacotes SciELO/PMC e dos relatórios de erros. O projeto deve tratá-lo como gate externo de empacotamento, não como parser do IDML nem como único validador.

## Artefato público avaliado

- Pacote: `SciELO_XPM_4.0.096-R20231215.zip`.
- SHA-256: `1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec`.
- 455 entradas; aproximadamente 18,97 MB descompactados.
- Verificação prévia: nenhuma entrada absoluta, traversal, symlink ou tamanho anômalo.
- Dependências internas: `packtools==2.4.2` e `pillow==6.2.2`.
- Release notes do pacote cobrem SPS 1.9, não SPS 1.10.

O pacote público é antigo em relação ao perfil atual. Downloads futuros deverão ser allowlisted por URL, nome, hash e revisão humana. Nenhum arquivo estranho localizado em áreas não relacionadas do FTP foi baixado ou executado.

## Primeiro spike isolado — histórico, conclusão revista em 2026-10-15

O teste usou container Python 3.8, usuário não-root, fonte read-only e execução sem rede.

- A primeira importação tentou gravar diretamente em `/xpm/xml/app.log`, contrariando execução read-only.
- Com cópia em filesystem temporário gravável, a CLI falhou por importar Tkinter incondicionalmente e não encontrar `libtk8.6.so`.
- A distribuição pressupõe ambiente gráfico/Windows, caminhos locais, Python e Java conforme a [documentação de instalação](https://documentacao.scielo.org/books/scielo-pc-programs/page/como-instalar).

Essas falhas não demonstravam necessidade de portar/modificar a ferramenta.
Em 2026-10-15, instalar Tk/Java/dependências e usar área gravável por job foi
suficiente para executar a CLI `-auto` mantendo todos os arquivos originais.

## Arquitetura aprovada

1. A aplicação constrói um pacote candidato imutável.
2. Um job solicita execução a um worker Linux isolado na mesma VPS, por canal interno autenticado; integração supervisionada ainda pendente.
3. O worker possui versão allowlisted de XPM, Python/Tk/Java exigidos e área temporária por job. O runtime legado do ensaio ainda não é runtime aprovado de produção.
4. O worker executa com conta sem privilégios, sem acesso ao banco da aplicação e sem compartilhar diretórios entre empresas.
5. Retorna `xpm.html`, stdout/stderr, versão, hash do executável/pacote, timestamps e status normalizado.
6. A aplicação anexa as evidências ao job, aplica a Release Policy e nunca interpreta ausência do relatório como sucesso.
7. Timeouts, indisponibilidade ou versão divergente deixam o job em `VALIDATION_UNAVAILABLE`, nunca `READY_FOR_SCIELO`.
8. Modo offline não comprova consultas externas. XML reempacotado pelo XPM tem
   hash diferente e nunca herda aprovação do XML de entrada; revalidar a saída
   antes de eventual promoção. Não rebaixar SPS/JATS para acomodar ferramenta antiga.

## Falsos positivos e licenciamento

Discussões oficiais de [janeiro de 2026](https://groups.google.com/g/scielo-xml/c/g4WQoK_cGss) e [março de 2026](https://groups.google.com/g/scielo-xml/c/KiC-TDlazJE) reconhecem falsos erros enquanto ferramentas alcançam o SPS 1.10. Toda exceção será específica e auditável.

Não foi localizado, dentro do pacote avaliado, um termo claro que autorize redistribuição modificada. Portanto:

- não redistribuir nem modificar XPM no produto sem confirmação;
- instalar o artefato oficial no worker conforme orientação SciELO;
- confirmar com SciELO a automação em ambiente de serviço antes da homologação externa;
- manter XPM desacoplado para substituição por versão oficial atualizada.

Essa pendência é uma condição de homologação, não um bloqueio para iniciar a fundação técnica e o pipeline determinístico.
