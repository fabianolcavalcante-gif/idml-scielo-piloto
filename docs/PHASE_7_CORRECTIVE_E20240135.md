# Fase 7C — Plano corretivo de generalização do artigo e20240135

Data de abertura: 2026-09-11. Estado: **7C-08 CONCLUÍDA EM 2026-09-21; PRÓXIMA ETAPA V-12**.

## 1. Finalidade e enquadramento

Esta trilha corrige as falhas de generalização reveladas pelo primeiro processamento do artigo
`ESA_2024135_AOP.idml`, comparado localmente com seu PDF, sete imagens e XML editorial aprovado.
Ela faz parte da Fase 7 e precede V-12. Não cria uma exceção para o artigo, não transforma o XML
aprovado em entrada do conversor e não autoriza produção.

V-01 a V-11 qualificaram os mecanismos de teste, segurança, validação e operação. O novo caso
demonstrou que a aprovação anterior de V-07 não pode ser interpretada como generalização para todo
IDML do periódico. O comparador funcionou como projetado e bloqueou o candidato; o pipeline do
artigo é que precisou ser corrigido. Com G7C-08 concluído, V-07 está **PASSOU NO CORPUS ATUAL**.

Princípios obrigatórios:

- corrigir regras gerais de parser, mapper, builder, validação e empacotamento;
- impedir condicionais baseadas no nome, hash ou conteúdo exclusivo deste artigo;
- usar o XML aprovado somente como oráculo oculto de avaliação e nunca como entrada de runtime;
- preservar proveniência até IDML, PDF, asset, catálogo autorizado ou perfil editorial;
- manter IA assistiva atrás de feature flag, sem edição direta do XML e sem poder de release;
- manter corpus e relatórios com conteúdo do artigo fora do Git e fora da VPS;
- transformar cada defeito confirmado em regressão content-safe ou fixture sintética mínima;
- executar cada etapa isoladamente e só iniciar a seguinte após seu gate passar.

## 2. Baseline congelado — 7C-00

Entrada e referência:

| Artefato | SHA-256 |
|---|---|
| IDML `ESA_2024135_AOP.idml` | `48c5c693d0e1a3f5fa597811fc861fccf21b987956340966552bbefec0175574` |
| XML editorial aprovado | `356936b42a1c30f0b3317a8520b04f730fa72c65edca41f3a15bb89c581b9d2c` |
| PDF editorial | `d997b54fdac501397b80e7a4526d6fff705509a99b52e90bd70310d8cdba6157` |
| XML candidato inicial | `0080b2986805788bfe8023a105ea81e57f0a9dfee39dc486f1559a4e3891e09b` |

O candidato inicial é determinístico, passa no validador offline interno com um warning, mas falha
na fidelidade semântica, no Packtools SPS 1.10 e no empacotamento. O baseline registrado é:

- 108 achados semânticos bloqueadores;
- cross-references com 38 de 39 ocorrências, faltando a referência ordinal 18;
- Packtools 4.17.2: 108 críticos, 79 erros, uma exceção e 68 warnings;
- 26 seções esperadas contra 18 atuais;
- sete figuras e sete imagens esperadas, mas nenhum vínculo de imagem no candidato;
- 43 fórmulas MathML esperadas contra 40 fórmulas gráficas atuais;
- sete notas estruturadas esperadas contra zero elementos `fn` atuais;
- 35 referências, cinco tabelas e quatro afiliações preservadas;
- corpo com recall 1,0 e fidelidade textual 0,995482 no comparador por fluxo;
- pacote recusado no primeiro ativo ausente, `ESA_2024135_Eq03.pdf`;
- suíte geral com 317 testes aprovados e cobertura de 87,50%.

Evidências privadas ficam em
`tmp/ARQUIVOS TESTE/e20240135-test-output/`; o resumo principal é
`comparison-summary.json`. Nenhum binário ou conteúdo integral será versionado.

Checklist 7C-00:

- [x] Confirmar que o IDML corresponde ao XML, PDF e planilha de referência.
- [x] Verificar que o caso não havia sido usado nas qualificações anteriores.
- [x] Executar conversão determinística duas vezes e congelar hashes.
- [x] Executar validação offline, Packtools, comparação semântica e tentativa de pacote.
- [x] Inspecionar visualmente todas as 14 páginas do PDF.
- [x] Classificar os defeitos por domínio e definir a ordem corretiva.
- [x] Atualizar o roadmap, plano mestre, relatório da Fase 7 e README.

Gate G7C-00: **APROVADO**. O baseline é reproduzível e suficiente para iniciar correções.

## 3. Ordem de desenvolvimento

```text
7C-00 baseline congelado
  -> 7C-01 regressão e inventário de origem
  -> 7C-02 figuras, ativos e ordem
  -> 7C-03 fórmulas e MathML
  -> 7C-04 estrutura e notas
  -> 7C-05 autores, metadados e cross-references
  -> 7C-06 conformidade SPS e pacote
  -> 7C-07 avaliação assistiva OpenClaw
  -> 7C-08 requalificação integral e implantação
  -> retomar V-12
```

As etapas 7C-02 a 7C-05 podem revelar causas compartilhadas, mas seus commits, fixtures,
relatórios e gates permanecem separados. V-12 não começa antes do G7C-08, pois a correção de
MathML, assets e pacote altera custo, memória, I/O e duração do fluxo.

## 4. Etapa 7C-01 — Regressão e inventário de origem

Objetivo: converter o baseline privado em um gate reproduzível e localizar, no IDML, a evidência
de cada figura, fórmula, seção, nota, autor e referência cruzada antes de alterar o mapper.

Desenvolvimento:

- [x] Criar manifesto privado content-addressed para IDML, PDF, XML e sete imagens.
- [x] Criar gate local que reconverta o IDML, compare os 12 domínios e falhe nos 108 bloqueios.
- [x] Persistir somente hashes, contagens, decisões e códigos de achado no relatório versionável.
- [x] Inventariar `Stories`, `Spreads`, objetos ancorados, hyperlinks e estilos envolvidos.
- [x] Mapear cada ativo externo do IDML para tipo, posição, rótulo e evidência.
- [x] Separar objetos de figura de objetos de equação e glifos auxiliares.
- [x] Criar fixtures sintéticas mínimas para cada nova classe de falha.
- [x] Proibir lookup por nome/hash específico no código de produção.

Aceite G7C-01:

- o gate reproduz o baseline e detecta cada família de defeito;
- todos os objetos relevantes possuem locator e hash de evidência;
- o relatório público não contém texto privado;
- a suíte anterior permanece verde.

Resultado em 2026-09-14: **APROVADO**. O manifesto verificou 12/12 artefatos. O gate converteu o
IDML duas vezes, reproduziu o mesmo SHA-256 do candidato, os 108 bloqueios e todas as métricas do
contrato sem mismatch. O inventário privado registrou 60 Stories, 68 frames, 54 objetos ancorados,
54 assets externos, 89 links, 292 estilos e 697 evidências; seu hash é
`9c24c356bf8e5ae992805cb2be87d7e69b673b209a1c9b8635d2942566aad086`. O relatório público não
contém paths de assets nem texto do artigo. A CI executa somente a validação de metadados e contrato,
sem acesso ao corpus. A suíte completa passou com 321 testes e cobertura de 87,58%; Ruff, formatação
e mypy strict também passaram. Relatório:
`benchmarks/qualification/reports/phase7-7c01-e20240135-baseline-v1.json`.

Gate G7C-01: **APROVADO**. O candidato continua intencionalmente bloqueado; a próxima etapa é 7C-02.

## 5. Etapa 7C-02 — Figuras, ativos e ordem editorial

Objetivo: ligar as sete figuras às sete imagens corretas, na ordem editorial, sem confundir
equações ou glifos com figuras.

Desenvolvimento:

- [x] Resolver links externos e nomes percent-encoded do IDML de modo seguro e determinístico.
- [x] Associar objeto, caption, label, primeira menção disponível e arquivo de origem.
- [x] Aplicar nomes finais pelo `PackageBuilder`, sem codificar o nome deste artigo no mapper.
- [x] Preservar a ordem global `Figure 1` a `Figure 7` relativa ao fluxo de blocos conhecido.
- [x] Eliminar a seção sintética `Elementos gráficos` quando ela não existir na hierarquia fonte.
- [x] Emitir `graphic` em cada `fig`, com ID e `xlink:href` válidos.
- [x] Bloquear figuras sem ativo, associação ambígua e ativos numerados extras.
- [x] Adicionar regressões para ordem fora de sequência, legenda sem mídia e alias `gfNN`.

Aceite G7C-02:

- sete figuras, sete `graphic` e sete assets, todos com vínculo um-para-um;
- precisão, recall, F1 e fidelidade de figuras/mídia iguais a 1,0;
- zero deslocamento de figuras e zero seção artificial;
- tentativa de pacote não falha por imagem de figura.

Resultado em 2026-09-14: **APROVADO**. A classificação passou a reconhecer por ordinal os nomes
seguros `FigNN`, `FigureNN` e `gfNN`, inclusive quando a origem vinculada é PDF, sem confundir
equações, glifos e branding. As sete legendas foram associadas um-a-um aos sete assets de figura;
o JATS contém sete `fig`, sete `graphic`, sete `xlink:href` únicos e ordem global 1–7. Os domínios
`figures` e `media` atingiram precisão, recall, F1 e fidelidade 1,0, com zero omissão, invenção,
duplicação ou deslocamento. A seção artificial foi removida e os bloqueios semânticos totais caíram
de 108 para 94.

O `PackageBuilder` resolveu os sete JPGs reais pelos ordinais e aplicou os nomes finais `gf01` a
`gf07`, preservando a extensão do payload. O worker agora valida o XML já reescrito e os nomes
efetivamente empacotados. A tentativa integral avança por todas as imagens de figura e para somente
em ativo gráfico de fórmula, como esperado antes da 7C-03. Figuras sem primeira menção explícita
continuam marcadas com fallback ordinal auditável; o refinamento de sua seção local pertence ao
gate estrutural 7C-04 e não altera a aprovação de ordem global deste gate.

Gate real executado duas vezes, sem rede e com 12/12 artefatos verificados: determinístico, XML
offline válido e contrato sem mismatch. A suíte completa passou com 325 testes e cobertura de
87,50%; Ruff, formatação e mypy strict também passaram. Relatório:
`benchmarks/qualification/reports/phase7-7c02-e20240135-figures-v1.json`.

Gate G7C-02: **APROVADO**. O candidato geral continua bloqueado pelos 94 achados remanescentes; a
próxima etapa é 7C-03.

## 6. Etapa 7C-03 — Fórmulas, classificação inline/display e MathML

Objetivo: detectar as 43 fórmulas, classificar corretamente 32 inline e 11 display e produzir
MathML seguro e semanticamente equivalente.

Desenvolvimento:

- [x] Identificar por que 13 inline viraram display e por que três fórmulas foram omitidas.
- [x] Distinguir equações reais de letras/glifos auxiliares (`A.pdf`, `C.pdf`, `X.pdf` etc.).
- [x] Preservar posição, rótulo, sequência e contexto de cada fórmula no modelo canônico.
- [x] Gerar recortes visuais content-addressed a partir do PDF quando a fonte for apenas gráfica.
- [x] Reutilizar o contrato MathML seguro, validação de aridade e equivalência semântica existentes.
- [x] Transcrever com OpenClaw somente após a detecção determinística estar completa.
- [x] Manter o gold oculto aos agentes e usá-lo apenas no comparador final.
- [x] Rejeitar MathML inseguro, incompleto, fora de posição ou sem evidência autenticada.
- [x] Adicionar regressões sintéticas e do catálogo privado para todas as classes encontradas.

Aceite G7C-03:

- exatamente 43 fórmulas: 32 inline e 11 display;
- zero fórmula gráfica no XML candidato final;
- zero omissão, invenção ou alteração sem autoridade registrada;
- domínio `formulas` e `formula_content` aprovado;
- MathML passa parser seguro, DTD, regras internas e equivalência semântica.

Resultado em 2026-09-15: **APROVADO**. O parser passou a reconhecer fórmulas inline embutidas em
`TextFrame`, atribuir corretamente os ativos `Eq-txt-NN`, ignorar duplicatas não monotônicas e
preservar as expressões nativas e agrupadas do pseudocódigo. A detecção determinística passou a
produzir exatamente 43 fórmulas nas posições da referência: 32 inline e 11 display.

Os 43 recortes do PDF foram revistos visualmente, renderizados a 300 dpi, autenticados por hash e
avaliados em lotes OpenClaw com proponente, dois críticos e adjudicador. O gold permaneceu oculto.
O catálogo final contém 43 decisões `accepted_for_human_review`, 86 aprovações de críticos, 43
aceites do adjudicador, zero abstensão incorporada e custo auditado de 1.793.642 micro-USD. Uma
rejeição correta do crítico encontrou expoente ligado ao nó errado; a regra geral de `msup` foi
corrigida antes do novo aceite. Recortes ambíguos também foram corrigidos antes da reavaliação.

Com o catálogo content-addressed aplicado, o XML é determinístico e válido, contém 43 elementos
MathML, zero fórmula gráfica e nenhum bloqueio de transcrição. `formulas` atingiu precisão, recall,
F1 e fidelidade 1,0; `formula_content` ficou aprovado após qualificar 24 alterações visuais com
autoridade registrada. Os bloqueios gerais caíram de 94 para 33; os restantes são de estrutura,
notas, metadados e referências, escopo de 7C-04 e 7C-05. O XML candidato e o catálogo permanecem
privados, e a revisão humana final continua obrigatória. Relatório content-safe:
`benchmarks/qualification/reports/phase7-7c03-e20240135-formulas-v1.json`.

A suíte completa passou com 335 testes e cobertura de 87,59%; Ruff, formatação e mypy strict
também passaram. O gate público de CI executa somente metadados e hashes, sem o catálogo nem o
corpus privados.

Gate G7C-03: **APROVADO**. O candidato geral permanece bloqueado; a próxima etapa é 7C-04.

## 7. Etapa 7C-04 — Hierarquia, fluxo e notas editoriais

Objetivo: recuperar a estrutura editorial completa sem quebrar o texto já preservado.

Desenvolvimento:

- [x] Reconstruir as 26 seções com níveis e ordem corretos a partir de estilos e frames.
- [x] Corrigir os títulos intermediários atualmente omitidos.
- [x] Preservar a relação entre parágrafos, fórmulas, figuras e tabelas durante o aninhamento.
- [x] Extrair e tipar as sete notas de autor/editor e suas referências.
- [x] Manter contribuições, financiamento, disponibilidade e conflitos no local SPS adequado.
- [x] Evitar duplicação semântica entre `fn`, `funding-group` e seções de `back`.
- [x] Adicionar regressões de hierarquia profunda, notas rotuladas e seções especiais.

Aceite G7C-04:

- 26 seções esperadas, na mesma hierarquia semântica;
- domínio `structure` aprovado e corpo sem perda ou duplicação;
- sete notas estruturais e dez unidades semânticas de notas aprovadas;
- tabelas e referências permanecem com precisão/recall 1,0.

Resultado em 2026-09-16: a hierarquia candidata reproduziu exatamente as 26 seções da referência,
com seis seções de nível 1, onze de nível 2 e nove de nível 3, inclusive os `sec-type` editoriais.
As sete notas estruturais foram materializadas como duas notas de autor/editor, quatro notas de
tabela com seis parágrafos e uma declaração financeira; as dez unidades semânticas de notas
atingiram precisão, recall, F1 e fidelidade 1,0. Tabelas e referências permaneceram com precisão e
recall 1,0.

O fluxo do corpo preservou os 5.814 tokens esperados, sem omissão, invenção, alteração,
deslocamento ou token não autenticado. Permanecem seis tokens duplicados autenticados de rótulos
de controle, com precisão 0,998969, recall 1,0 e fidelidade 0,998366; eles não representam conteúdo
editorial inventado. Os marcadores numerados passaram a listas JATS sem duplicação textual e as 43
fórmulas continuaram presentes e qualificadas. O XML é determinístico e válido. Os achados
semânticos bloqueadores caíram de 30 para 6, todos fora do escopo estrutural desta etapa.

O gate `ops/gate_phase7_7c04.py` foi aprovado sem mismatch contra o contrato content-addressed.
O candidato geral continua bloqueado pelos seis achados restantes e não está autorizado para
produção. A suíte integral aprovou 343 testes com cobertura de 87,72%; Ruff, formatação e mypy
também passaram.

Gate G7C-04: **APROVADO**. A próxima etapa é 7C-05.

## 8. Etapa 7C-05 — Autores, metadados e cross-references

Objetivo: remover as divergências restantes do front e atingir cobertura total dos vínculos.

Desenvolvimento:

- [x] Substituir o split ingênuo pelo reconhecimento baseado em marcação, ordem e evidência.
- [x] Preservar nomes compostos e iniciais sem inferir convenção cultural não declarada.
- [x] Comparar nomes por componentes JATS, não apenas pelo texto concatenado.
- [x] Recuperar o identificador editorial `other=00224` apenas de fonte autorizada.
- [x] Manter `publisher-id=e20240135` somente quando o perfil exigir e sem substituir `other`.
- [x] Completar a chamada bibliográfica da referência ordinal 18.
- [x] Corrigir vínculos de figura, tabela, fórmula, afiliação e nota afetados pelas etapas anteriores.
- [x] Adicionar regressões para nomes compostos e RIDs múltiplos.

Aceite G7C-05:

- quatro autores com componentes semanticamente equivalentes ao aprovado;
- metadados críticos com precisão e recall 1,0 ou autoridade independente explícita;
- 39 de 39 cross-references, sem RID órfão;
- nenhum enriquecimento sem proveniência ou pendência de revisão humana.

Resultado em 2026-09-16: **APROVADO**. Os quatro autores foram estruturados na ordem original do
IDML e seus quatro ORCIDs vieram dos hyperlinks autenticados da própria fonte. Para evitar qualquer
inferência cultural dos nomes compostos, os componentes `given-names`/`surname`, o título do
periódico e o identificador editorial `other=00224` foram confirmados por um registro Crossref
content-addressed e independente do XML aprovado. O catálogo falha fechado quando DOI, hash da
fonte, ordem, nome corrente ou ORCID divergem, e mantém a revisão humana final explicitamente
pendente.

A resolução de citações passou a aceitar `et al.` para referências de três autores sem remover o
padrão completo; a ocorrência de Laghdaf et al. passou a apontar para a referência ordinal 18. O
resultado atingiu 39/39 cross-references, 35/35 destinos únicos e zero RID deficitário ou excedente.
Os metadados e quatro autores atingiram precisão, recall e F1 1,0. Duas normalizações gerais
adicionais eliminaram representações duplicadas já contidas em MathML qualificado e separaram
linhas numeradas múltiplas de um mesmo parágrafo IDML. Assim, o corpo passou a 5.814/5.814 tokens,
sem omissão, invenção, duplicação, alteração ou deslocamento.

O gate `ops/gate_phase7_7c05.py` verificou 12/12 artefatos, determinismo, XML offline válido sem
issues, os catálogos privados por hash e o contrato público sem conteúdo restrito. Após reconciliar
as 24 transcrições visuais qualificadas, o comparador ficou com **zero bloqueio nos 12 domínios** e
aprovou o candidato semântico geral. Isso ainda não autoriza produção: SPS, Packtools, pacote e XPM
pertencem a 7C-06, e a homologação humana continua obrigatória. A suíte integral aprovou 350 testes
com cobertura de 87,70%; Ruff, formatação, mypy e `git diff --check` passaram.

Gate G7C-05: **APROVADO**. A próxima etapa é 7C-06.

## 9. Etapa 7C-06 — Conformidade SPS 1.10 e pacote íntegro

Objetivo: eliminar achados reais do perfil vigente e construir um pacote completo e reproduzível.

Desenvolvimento:

- [x] Reexecutar validador offline, Packtools fixado e SPSValidator fixado.
- [x] Tratar afiliações, datas, idiomas, papéis CRediT, ORCID, IDs e acessibilidade.
- [x] Separar falsos positivos por reprodução mínima e regra/versionamento, sem waiver genérico.
- [x] Incluir PDF, sete imagens e demais assets realmente referenciados no pacote.
- [x] Confirmar que nenhuma equação depende de PDF externo após MathML.
- [x] Conferir manifest, hashes, nomes, MIME types, reprodutibilidade e ausência de extras.
- [ ] Executar XPM SPS 1.10 no worker Windows quando disponível; manter bloqueio explícito até lá.

Aceite G7C-06:

- zero crítico e zero erro real no Packtools/SPSValidator;
- pacote construído duas vezes com o mesmo hash;
- todos os `xlink:href` resolvidos e nenhuma sobra de asset;
- XPM aprovado ou pendência operacional mantida como bloqueador de release, nunca simulada.

Resultado em 2026-09-17: o gate `ops/gate_phase7_7c06.py` aprovou os 12 artefatos privados,
o contrato público e a construção repetida byte a byte. O XML empacotado passou no validador
offline com zero issue. O ZIP determinístico contém exatamente um XML, um PDF e sete JPEGs,
todos os vínculos de imagem resolvem, não há ativo de equação em PDF e não existe sobra de ativo.
O pacote tem hash
`e86f51a83a1f5d7cc869e51f4e13d18bb68fcf6c758016dd99bead032b0559ee`.

As referências passaram a emitir 35 `element-citation` estruturados, volume, fascículo,
paginação/elocation, DOI e links externos marcados. Os oito erros reais de `lpage` e as nove
divergências `element-citation`/`mixed-citation` foram eliminados. Packtools 4.17.2 registrou
14 críticos, cinco erros e sete warnings; SPSValidator 0.3.0 registrou 14 críticos, seis erros e
sete warnings. O gate classifica como **zero erro real** somente porque exige, por código e
quantidade, as reproduções comprovadas: agregação incorreta de afiliação e CRediT; estado e datas
de revisão ausentes também na referência autorizada; consultas externas de DOI/ORCID
indisponíveis; e o nome de PDF calculado incorretamente pelo SPSValidator. Qualquer achado novo ou
alteração nessas quantidades reprova o gate.

Há 69 referências de objetos, todas resolvidas; todas as sete figuras, cinco tabelas e 11 fórmulas
display possuem referência de entrada. As 32 fórmulas inline e 11 display usam IDs formais, as sete
figuras possuem texto alternativo, e os quatro autores têm afiliações e 14 papéis CRediT com URI.
O relatório content-safe é
`benchmarks/qualification/reports/phase7-7c06-e20240135-formal-v1.json`.

Gate G7C-06: **APROVADO COM BLOQUEIO DE RELEASE PRESERVADO**. `release_ready=false` e o XPM SPS
1.10 permanece `pending_windows_execution`. Naquele marco, a próxima etapa era 7C-07; a homologação humana segue
obrigatória após o desenvolvimento integral. A suíte integral aprovou 360 testes com cobertura de
87,33%; Ruff, formatação, mypy e `git diff --check` passaram.

## 10. Etapa 7C-07 — Avaliação assistiva OpenClaw

Objetivo: usar agentes para reduzir risco sem permitir que consenso substitua validação.

Desenvolvimento:

- [x] Executar proponente, críticos XML/editorial e adjudicador nos domínios alterados.
- [x] Usar evidência autenticada, saída estruturada e no máximo dois ciclos de reparo.
- [x] Testar omissão, invenção, troca de autor, fórmula visual ambígua e associação errada de ativo.
- [x] Medir precisão, recall, abstenção, falso consenso, latência, tokens e custo por domínio.
- [x] Manter todas as propostas somente `accepted_for_human_review`.
- [x] Desativar flags/provider e limpar sessões após a janela.

Aceite G7C-07:

- zero proposta sem evidência e zero violação de contrato;
- nenhum falso consenso aceito;
- todos os casos negativos falham fechado;
- custo e evidências registrados, sem aplicação ou release automático.

Resultado em 2026-09-17: **APROVADO**. O dataset privado content-addressed selecionou um caso de
cada domínio alterado — metadados, autores/afiliações, estrutura, referências, figuras/tabelas e
matemática/notas — sem expor o XML aprovado aos agentes. A janela
`phase7-7c07-domains-v34-001` executou proponente, crítico XML, crítico editorial e adjudicador com
`openai/gpt-5.4-mini` e `thinking=medium`. Os seis casos concluíram, passaram todos os checks
determinísticos, melhoraram o baseline e receberam decisão `accepted_for_human_review`; os cinco
casos textuais foram exatos e a fórmula visual foi semanticamente equivalente ao gold oculto.
Houve 12 passes de críticos, seis adjudicações `unanimous_accept`, zero abstenção, zero rejeição,
zero candidato de falso consenso e zero ciclo de reparo. As 24 chamadas custaram 140.447
micro-USD, consumiram 121.676 tokens de entrada e 10.929 de saída e somaram 136.145 ms de
latência observada, com máximo de 11.609 ms por chamada. No conjunto controlado de mudanças
esperadas, precisão e recall foram 1,0. Nenhuma chamada recebeu tools ou Skills.

Os controles específicos de omissão, invenção, troca de autor, fórmula visual ambígua e associação
incorreta de ativo falharam fechado: quatro foram rejeitados e a ambiguidade levou à abstenção. A
matriz adversarial complementar reexecutou 30 casos/84 papéis em seis domínios, com 100% dos
oráculos, zero provider e custo zero. O gate `ops/gate_phase7_7c07.py` vincula por hash o dataset,
plano, manifesto e relatório privado, publica somente contagens/códigos e também roda na CI em modo
sem corpus.

O pós-teste somente leitura confirmou API, worker e OpenClaw saudáveis, duas flags falsas, zero
credencial do provider, zero proxy/rede transitória, zero sessão e zero `agent_runs`/propostas. Os
quatro papéis compartilham o mesmo modelo (`role_models_independent=false`), portanto essa
concordância não é consenso independente, não aplica alterações e não autoriza release. O relatório
content-safe é
`benchmarks/qualification/reports/phase7-7c07-e20240135-assistive-v1.json`.

Gate G7C-07: **APROVADO COM REVISÃO HUMANA E BLOQUEIO DE RELEASE PRESERVADOS**. A próxima etapa é
7C-08; `release_ready=false` continua vigente pelo XPM SPS 1.10 pendente e pela homologação humana
final. A suíte integral aprovou 367 testes com cobertura de 87,29%; Ruff, formatação, mypy e
`git diff --check` passaram.

## 11. Etapa 7C-08 — Requalificação integral e implantação

Objetivo: provar a correção sem regressão no artigo anterior e atualizar a imagem candidata.

Desenvolvimento:

- [x] Reexecutar os dois artigos reais e todas as fixtures sintéticas/adversariais.
- [x] Exigir zero bloqueio semântico no artigo e20240135.
- [x] Reexecutar V-01 a V-11 afetadas, Ruff, formatação, mypy e cobertura.
- [x] Produzir relatório content-safe requisito → defeito → correção → teste → evidência.
- [x] Fazer backup/restore antes da implantação na VPS.
- [x] Implantar código e gates sem copiar corpus privado.
- [x] Reproduzir gates sintéticos em container read-only e sem rede.
- [x] Confirmar API, worker, banco, Redis e OpenClaw saudáveis, com agentes desativados.

Aceite G7C-08:

- 12 domínios sem bloqueios no comparador semântico;
- validação formal e pacote atendem G7C-06;
- nenhuma regressão nos artigos e gates anteriores;
- suíte completa, tipos e lint aprovados;
- rollback comprovado e serviços existentes sem impacto;
- V-07 volta a `PASSOU NO CORPUS ATUAL`, permitindo iniciar V-12.

## 12. Critérios globais de encerramento

Resultado G7C-08: **APROVADO EM 2026-09-21**, com restrições de release preservadas.
Foram aprovados 380 testes, cobertura de 87,31%, 18 gates locais/isolados e ambos os artigos.
A reconstrução textual verificou 106/106 stories; o candidato formal final manteve zero bloqueio
nos 12 domínios e o mesmo hash autenticado em 7C-06. A regressão de ORCID editorial ambíguo no
artigo anterior foi corrigida sem inserir regra exclusiva de artigo. Backup/restore e retorno
real à imagem anterior passaram; API/worker foram atualizados e os outros 23 serviços mantiveram
IDs, início e contadores de reinício. Evidências: `docs/PHASE_7C08_REQUALIFICATION.md`.

A trilha somente termina quando:

- [x] todos os gates G7C-01 a G7C-08 estiverem aprovados;
- [x] não existir perda, invenção, duplicação ou deslocamento conhecido no corpus qualificado;
- [x] o candidato não depender de arquivos inexistentes;
- [x] warnings remanescentes tiverem classificação, evidência e responsável (G7C-06; Codex na trilha técnica, especialista no G8-H);
- [x] os relatórios privados estiverem íntegros e os públicos estiverem sanitizados;
- [x] a documentação principal refletir o estado real;
- [x] a próxima ação oficial voltar a ser V-12.

Mesmo após esta trilha, `READY_FOR_SCIELO` continuará bloqueado pelo XPM aplicável e pelo Gate
Humano Final G8-H.
