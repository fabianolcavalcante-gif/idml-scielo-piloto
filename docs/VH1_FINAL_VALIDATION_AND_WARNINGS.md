# VH-07 — pacote exato, correção de afiliação e triagem dos avisos

Atualizado em 2026-10-14. Desenvolvimento candidato; **VH-07 parcial por VH-02/XPM**.

Nota de continuidade 2026-10-16: XPM online controlado na VPS revelou divergências
de título do periódico/editora no cadastro real; VH-05 reaberta apenas para esses
campos e VH-07 aguardará novos pacotes. `VH1_XPM_ONLINE_AND_COMPATIBILITY.md`
registra consultas parciais, compatibilidade legada e a proposta ainda não autorizada
de exceções pontuais. A prova abaixo não é substituída nem transformada em aceite XPM.

Nota de continuidade 2026-10-15: a decisão Windows descrita neste checkpoint foi
substituída, com autorização do proprietário, pela execução Linux na própria VPS.
Cinco relatórios reais foram obtidos sem alterar o XPM; restam compatibilidade
SPS 1.10/JATS 1.3, consultas e integração. Ver `VH1_XPM_LINUX_QUALIFICATION.md`.
Resultados Packtools/SPS abaixo permanecem válidos para seus pacotes exatos;
não significam aprovação integral XPM.
Não é liberação para homologação, aprovação científica ou indexação SciELO.

## Entrega deste incremento

A triagem encontrou um defeito real em um aviso de `orgdiv2`: dois níveis
institucionais explícitos estavam reunidos em `orgdiv1`. O builder agora separa
somente a sintaxe qualificada `Graduate School of …, Department of …`, quando os
três campos de origem estão presentes, sem alternativas, com evidência comum e
transformações de extração determinística. O prefixo completo precisa coincidir
literalmente com a afiliação original. Outros padrões permanecem inalterados.

O campo canônico conserva a expressão original; a correção é representacional na
saída JATS. Não há inferência de unidade ausente, consulta IA, enriquecimento de
autoria ou uso do XML gold. O contrato de delta comprova uma afiliação modificada
no e20240086 e nenhuma no e20240135. Todo o restante do XML é idêntico em C14N;
os dois canônicos, catálogos de referências/fórmulas e anexos permanecem iguais.

## Resultado nativo atual

| Caso | Packtools | SPS Validator | Consultas comprovadas em cada execução |
|---|---|---|---|
| e20240086 | 0 críticos, 0 erros, 5 avisos | 0 críticos, 0 erros, 5 avisos | DOI, fascículo, seção e 3 ORCIDs |
| e20240135 | 0 críticos, 0 erros, 5 avisos | 0 críticos, 0 erros, 5 avisos | DOI, fascículo, seção e 4 ORCIDs |

Os validadores compartilham regras: não são vinte defeitos distintos. O primeiro
artigo tinha seis avisos por ferramenta; apenas o aviso da afiliação corrigida
desapareceu. Os demais achados são preservados integralmente, inclusive severidade.

Execução na VPS em imagens imutáveis do registro
`config/validator-registry-vh1-history.json`, via executor isolado já qualificado,
com novas consultas e grants restritos de laboratório. Não é E2E da aplicação.
Fontes/grants estavam válidos na execução; este relatório não renova autorizações
nem transforma snapshots históricos em consultas atuais no runtime.

## Classificação dos avisos restantes

| Grupo | e20240086 | e20240135 | Decisão de triagem, sem aceite de release |
|---|---:|---:|---|
| Ausência de segunda subdivisão institucional | 2 | 4 | Texto original preserva uma subdivisão; não inventar outra |
| Ausência de apêndice | 1 | 1 | Elemento opcional ausente; ausência não comprova completude da fonte, manter revisão |
| Seção sem parágrafo direto | 2 | 0 | Seções contêm subseções tituladas e parágrafos; não inserir parágrafos vazios |

O SPS 1.10 capturado em 07/10 define até três níveis institucionais, apêndices
opcionais e inclui exemplo de seção composta por subseções. Referência:
[especificação oficial vinculada pelo validador](https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit),
SHA `09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef`.
Usadas as seções `aff`, `app-group` e `sec`, não a documentação antiga SPS 1.7
como substituta normativa. A classificação não modifica regras de terceiros.

O relatório nativo sanitizado reutiliza um localizador em várias ocorrências.
Por isso a triagem vincula cada grupo à lista completa de subárvores e suas
contagens, sem inventar correspondência um-a-um entre linha nativa e nó.
Regra desconhecida, erro, contagem divergente, seção vazia ou afiliação ambígua
impedem a classificação. Os avisos continuam visíveis para revisão humana.

As 30 diferenças brutas já triadas em VH-06, a abstenção científica de um glifo e
os dois localizadores bibliográficos continuam preservados. O novo delta prova
que corpo, fórmulas e referências não mudaram; não representa um novo aceite
científico nem altera o comparador bruto.

## Evidências atuais e integridade

- `vh1-final-validation-linux-v2.json`: SHA
  `8e86df94a1eb14544a781c2ce3876140bb81771107c20252e3c7810e6e0b601a`.
- `vh1-final-warnings-v2.json`: SHA
  `40ace7e7f026be8964a8ac84cd5477dec5328cae078e1decc549302ccb0310d0`.
- Contrato: `benchmarks/qualification/contracts/vh1-final-validation-delta-v1.json`.
- Gate nativo: `python -m ops.gate_vh1_final_validation`.
- Gate de triagem: `python -m ops.gate_vh1_final_warnings`.
- Plano privado: `benchmarks/private/output/vh1-final-validation-20261014T155218Z/plan.json`,
  SHA `7f4042490ef244603fd8910c5daf653979b2a9c1e7a2fc75de6216bb91847d4c`.
- Mesmo diretório de ensaio em `/opt/idml-platform/private/qualification/`, acesso
  restrito; conteúdo científico não é publicado nos relatórios públicos.

| Caso | SHA-256 XML | SHA-256 ZIP |
|---|---|---|
| e20240086 | `9a1386e47778597683f9ceb0c4d078b37a68e521d3b2e2eb7b3b51ad31e93916` | `ba685142396801ed3901d8c63e3ad5da0c81af3b753c6a16b27bb63457a66c6c` |
| e20240135 | `b29d362fea52e648a3adc3930e406784732b04cdbf6efce7a0b6deea9a332c92` | `2c4aad2df2b1b61316d6bf2f44795c0b4c1acbb7088fb6fd822020a974f9583f` |

As versões v1 deste incremento são históricas: depois delas mudou o verificador
de sucessão de fontes. A v2 reexecuta o mesmo candidato, com novo plano/fontes e
grants, e é a evidência corrente. Nenhum relatório anterior foi sobrescrito.

## XPM: pendência concreta, não download

`vh1-xpm-preflight-windows-v1.json`, SHA
`a76500fb60e7975ec18862a3169fa2ebc36527e88734d95ff5eb614366d95177`, confirma:

- cópia local do ZIP oficial já armazenado na VPS, mesmo SHA-256;
- intérprete local Windows 3.11.3 com módulo Tkinter presente, mas sem as duas
  dependências declaradas no ZIP (`packtools==2.4.2`, `pillow==6.2.2`);
- nenhuma extração, instalação ou execução de XPM neste incremento;
- nenhum executor Windows dedicado configurado; SPS 1.10 ainda não qualificado.

Isso é pré-verificação, **não** falha observada de XPM em Python 3.11, nem prova de
compatibilidade de qualquer versão Python. Não atualizar dependências antigas
arbitrariamente para fazer a ferramenta executar. A
[CLI oficial](https://documentacao.scielo.org/books/scielo-pc-programs/page/xml-package-maker-xpm)
existe; a lacuna é um ambiente oficial isolado e ensaios positivos/negativos reais,
incluindo relatório vinculado ao pacote exato e tratamento específico SPS 1.10.

Próxima decisão necessária em VH-02: identificar o host Windows dedicado, ou
autorizar preparar neste computador uma conta/ambiente isolados para homologação.
Não foi criada conta, instalado serviço, contratado host nem alterada a ADR-002.
Confirmação de uso em serviço/licenciamento permanece conforme `XPM_FEASIBILITY.md`.
Ausência de XPM continua `validation-unavailable`, nunca aprovação tácita.

## Testes e operação

103 testes novos cobrem divisão literal, abstenção em sintaxe/evidência ambígua,
preservação do canônico, DTD, delta completo, achado desconhecido/duplicado, seção
vazia, apêndice referenciado ausente, adulteração de evidência e proibição de
converter triagem em aprovação. Evidência de execução registrada ao fim do lote.

- Regressão direcionada: **936 aprovados**, zero falha/erro/skip,
  `tmp/vh1-final-validation-focused.xml` (446,45 s).
- Reexecução após endurecer o gate: **103 aprovados**, zero falha/erro/skip,
  `tmp/vh1-final-validation-current-unit.xml`. Esses testes se sobrepõem à regressão;
  não somar as contagens como testes distintos. Inclui uma nova contraprova de
  adulteração coordenada dos relatórios anterior e atual.
- V10/V11 requalificados com ensaios API/jobs/pacote/interface, 121 entradas
  arbitrárias, 128 mutações ZIP e 128 round-trips Unicode. Relatórios
  `v10-operational-workflow-vh1-final-validation-v1.json` (135 fontes) e
  `v11-robustness-mutation-vh1-final-validation-v1.json` (103 fontes).
- Ruff global e mypy (112 arquivos) aprovados; formatação dos arquivos deste
  incremento e `git diff --check` aprovados. Os dois scripts históricos de DOI
  continuam fora do formato, registrados em VH-17; não declarar CI global verde.
- Diagnóstico agregado `tmp/vh1-final-validation-7c08.json`: 17 de 18 gates
  aprovados; somente V09 permanece desatualizado, como no checkpoint anterior.
  Essa requalificação histórica continua explícita em VH-17; não foi dispensada.
- Suíte integral/cobertura **não** reexecutadas neste incremento representacional.
  1.892/89,20% é resultado histórico anterior, não medição da fonte atual.

Pós-checagem VPS: API/worker continuam na imagem `4fcf4766…`, ambos em execução,
readiness com banco/Redis `ok`, 1.182 MiB de RAM disponível e 15 GiB livres no disco.
Área temporária do executor vazia. Sem mudança de hardware, publicação, serviço
ativo, fonte autorizada em produção ou ativação OpenClaw.

## Sequência finita

VH-07 permanece parcial apenas quanto à validação obrigatória XPM; não reabrir
VH-06 nem perseguir indefinidamente a eliminação de avisos opcionais. Resolver a
decisão de ambiente em VH-02; enquanto houver dependência externa, VH-08 (política
IA restrita) pode avançar conforme a seção 6 do plano único. Implantação continua
em VH-14/16, regressão final/V09/formatação histórica em VH-17 e E2E em VH-18.
