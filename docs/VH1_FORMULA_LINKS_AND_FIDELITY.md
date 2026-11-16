# VH-06 — vínculos de fórmulas e fidelidade científica

Checkpoint: 2026-10-07. **Vínculos corrigidos e qualificados no desenvolvimento
candidato; VH-06 ainda parcial. Sem implantação ou liberação G-HOMOLOG.**
Continua o lote 2 e a lista única VH-01–20; não é uma fase adicional.

Atualização em 2026-10-08: este checkpoint é histórico. A divergência `g`/`a`
abaixo e outras 13 transcrições foram corrigidas e revalidadas, com catálogos
anteriores preservados. Estado vigente, evidências e pendências da VH-06:
[`VH1_FORMULA_SOURCE_REVISIONS.md`](VH1_FORMULA_SOURCE_REVISIONS.md).

## Correção implementada

O conversor reconhecia somente o primeiro número em chamadas como `Equations N
and M`. O resolvedor agora associa também o segundo número quando ambos possuem
destinos únicos e o primeiro vínculo corresponde exatamente à chamada. Não
interpreta faixas, listas maiores, números decimais/sufixados ou tipos diferentes.
Não sobrescreve vínculos existentes nem formatação do trecho final.

A fórmula 15 é introduzida pela expressão literal `we have:`. A inspeção visual
da página 7 do PDF autorizado confirmou a fórmula imediatamente seguinte à frase.
O resolvedor associa as palavras já existentes, sem acrescentar uma chamada
numérica ao artigo. Requer a mesma seção, uma fórmula display rotulada e nenhum
conteúdo interveniente; somente parágrafos vazios de layout podem ser ignorados.
Abstém-se diante de duas fórmulas consecutivas, formatação ou vínculo conflitante.
Mantém evidências do parágrafo e da fórmula no modelo canônico.

O elemento [xref da JATS 1.3](https://jats.nlm.nih.gov/publishing/tag-library/1.3/element/xref.html)
admite conteúdo textual de chamada. A decisão de destino aqui é específica ao
contexto estrutural qualificado; não é autorização para inventar chamadas ou
vincular toda fórmula à ocorrência de um número próximo.

Foram acrescentados cinco vínculos no e20240086: números 4, 8, 12, 14 e a expressão
introdutória da fórmula 15. Os dois primeiros destinos já tinham outras chamadas,
por isso os validadores só apontavam três erros. A comparação inicial recusou os
dois vínculos adicionais até a conferência dos pares literais e dos rótulos únicos.
Não se desativou a verificação de diferenças.

## Preservação e testes nativos

- Reconversão dupla dos dois IDMLs originais com os catálogos previamente
  qualificados. DTD válida e XML/ZIP determinísticos; nenhum gold lido como entrada.
- Comparação integral C14N: retirados apenas os cinco novos elementos `xref`,
  reconstituindo texto/tail, o XML é idêntico ao anterior. MathML, metadados,
  referências e conteúdo preservados. O e20240135 é idêntico inclusive em bytes/ZIP.
- Nomes dos membros do pacote idênticos, PDF/imagens intactos byte a byte.
  Apenas XML e manifesto da conversão podem mudar no pacote.
- Quatro execuções completas na VPS, pelo executor isolado do broker, uma por vez,
  com imagens e política de histórico já qualificadas; não é E2E da aplicação ativa.
  Fontes/grants válidos no ensaio; horários de coleta de fontes não foram renovados
  artificialmente. Reexecutar coletas quando expirarem, antes de novos ensaios.

| Artigo | Antes, por ferramenta | Depois, por ferramenta |
|---|---|---|
| e20240086 | 0 críticos / 3 erros / 9 avisos | **0 críticos / 0 erros / 9 avisos** |
| e20240135 | 0 críticos / 0 erros / 5 avisos | **0 críticos / 0 erros / 5 avisos** |

Packtools e SPSValidator removeram exatamente os três achados esperados, sem
novos achados e preservando integralmente os avisos. Autoridades DOI, ORCID,
fascículo e seção permanecem positivas; auditoria original/efetiva de histórico
preservada. Isso **não equivale a aprovação integral, XPM concluído ou aceite SciELO**.

## Evidências e reprodução

- Relatório público sem texto científico:
  `benchmarks/qualification/reports/vh1-formula-links-linux-v1.json`.
- Gate `python -m ops.gate_vh1_formula_links`: vincula plano, código, imagens,
  arquivos, fontes, chamadas e deltas dos achados. Integrado ao CI, sem depender
  do corpus privado. Retorna aprovação científica e liberação sempre falsas.
- Plano privado: `benchmarks/private/output/vh1-formula-links-20261007T202358Z`;
  mesmo nome em `/opt/idml-platform/private/qualification/`, permissão 0700.
  SHA-256 do plano: `49b9e1154cd87f3ae26dd6c59d48f6ec9f0639d028f9b9077b965d40ec2129e5`.
- e20240086 XML: `297d660afa87e34ca530bdf0c22d8f9c1f5623461c8cd425eaa3b3177a119b3d`;
  ZIP: `6b2ba60422107ad023893995b6149a1fe5d3926daf9cc679532bb27dc0f5d3be`.
- e20240135 XML: `9ff50bc3ae960c16fea624c71482e8aedd7c616f9e36e2fb1a82fdf5f79b0590`;
  ZIP: `793956107ec688fb529fc83340d1dc3b3da5fe517e13558db7aa781b4e03b1a3`.
- Registro de imagens: `config/validator-registry-vh1-history.json`, sem mudança.
- 35 testes novos do resolvedor, 18 de integridade XML/pacote e 37 do gate.
  Contraprovas rejeitam texto/MathML/rótulo/destino alterados, vínculo extra,
  duplicação, evidência incompleta, troca de imagem ou remoção indevida de avisos.
  **136 testes focados aprovados**, incluindo os fluxos V10/V11 e enriquecimentos;
  `tmp/vh1-formula-links-focused.xml`.
- V10/V11 executados novamente, com provas imutáveis
  `v10-operational-workflow-vh1-formula-links-v1.json` e
  `v11-robustness-mutation-vh1-formula-links-v1.json`. Não são mera atualização de hashes.

Regressão final: **1.387 testes aprovados, zero falhas/erros/skip e 88,76% de
cobertura de linhas**; `tmp/vh1-formula-links-final-tests.xml` e
`tmp/vh1-formula-links-final-coverage.json`. Os 90 testes novos estão incluídos
nesse total. Cobertura mede código executado de `src`, não conformidade SciELO
ou acerto de transcrição científica. Ruff global, formatação dos dez arquivos do
incremento, mypy (108 arquivos), gates metadados/histórico/editorial/scoped/vínculos
e V10/V11 passam. V09 foi repetido e continua reprovando a evidência histórica;
formatação global ainda aponta apenas os dois scripts históricos já em VH-17.
Não há aprovação global do CI.

## Defeito científico detectado — bloqueio de fidelidade na VH-06

A inspeção visual utilizada para confirmar o vínculo da fórmula 15 também mostrou
uma divergência preexistente: o PDF traz `g` no denominador `Hgk`, mas o catálogo
e o MathML candidato trazem `a`. Esta entrega preserva esse MathML e **não o aprova**.

- Fonte autorizada: `tmp/sample/1809-4457-esa-30-0825/1809-4457-esa-30-e20240086.pdf`,
  página 7; SHA-256 `232fb2428bbdf344af192d24865a4e39848fd4e4fae20f2325aa9ecef6ff2496`.
- Caso de catálogo: `esa-math-notes-observed-015`, versão histórica preservada em
  `benchmarks/private/output/h1-country-codes-v1/esa-e20240086/formula_catalog.json`.
  MathML histórico SHA-256 `f2e22e7d6f8b6e8d34a41c587afa8086e6bd8866fd3b083de3ec6c8374c90c87`.
- A proposta histórica foi aceita **para revisão humana**, não como transcrição
  cientificamente homologada. Consenso de agentes e XML estruturalmente válido
  não garantem que cada símbolo corresponda à fonte. Não houve chamada IA neste incremento.

Próximo trabalho, dentro de VH-06:

1. Corrigir a transcrição por nova versão rastreável do catálogo, baseada na fonte
   visual e com teste que detecte a troca `g`/`a`. Preservar proposta/evidência antiga,
   exigência de revisão humana e separação entre edição científica e allowlist IA.
2. Conferir a fidelidade das fórmulas dos dois artigos contra fontes autorizadas,
   registrando divergências concretas e abstenções. Não usar XML gold na conversão.
3. Fechar conferência de referências/seções/objetos e arquivos ainda abrangidos
   pela VH-06; registrar os avisos aplicáveis, sem inventar dados para eliminá-los.
4. Reconverter/revalidar a nova candidata; depois VH-07 classifica os avisos e
   consolida validações obrigatórias. XPM continua em VH-02, IA em VH-08–10,
   UI/operação/E2E nos itens já existentes. Não abrir nova fila paralela.

## Ambiente e limites

Readiness, banco e Redis `ok` antes/depois. API/worker preservados na imagem
`sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`.
Pós-teste: 914 MiB de memória disponível, 15 GiB livres em disco, temporários do
executor removidos automaticamente. Fontes/pacotes ficam somente na área privada.
Não houve implantação, ativação IA, edição de decisões humanas ou publicação.
V09 e formatação dos dois scripts históricos continuam em VH-17; não declarar CI
global aprovado por este incremento.
