# VH-02/07 — Cabeçalho MathML3 e diagnóstico estrutural XPM

Execuções nativas: 2026-10-26; fechamento da regressão: 2026-10-27.
Decisão técnica concluída; não concede aprovação SciELO,
ativação ou G-HOMOLOG. Continuação da seção 43 do plano único, sem nova fase.

## Correção real no gerador

O gerador combinava o PUBLIC ID da DTD JATS Publishing 1.3 padrão com o SYSTEM ID
`JATS-journalpublishing1-3-mathml3.dtd`. A variante MathML3 tem PUBLIC ID próprio,
contendo `with MathML3`. A correção segue o catálogo oficial já versionado no
projeto. A DTD local é idêntica ao arquivo consultado no NLM em 26/10, SHA-256
`af6f75cd07a575d4be12f4e44cc97c644c3b8a4d2ce68e6ff582c5b6170760fc`.

O validador offline agora exige a combinação correta; seu perfil passa a
`jats-1.3-mathml3+sps-baseline-1.2.0`. O código de erro `unexpected-doctype` permanece,
com mensagem que identifica PUBLIC/SYSTEM e MathML3. Documentos históricos não
foram reescritos. Uma nova reconstrução gera um novo XML e exige revalidação.

Nos dois artigos autorizados, o gerador e o empacotador foram executados sobre o
canônico preservado. O XML reconstruído corresponde à alteração exclusiva do
PUBLIC ID, desconsiderada somente a quebra de linha final da serialização. Os
candidatos de comparação preservam todos os demais bytes do XML original; a
árvore canônica permanece idêntica. PDFs/imagens são iguais byte a byte. Manifestos
de conversão foram regenerados e seus hashes conferidos no ZIP final.

## Decisão sobre o fatal e o erro residual

Seis execuções dos métodos estruturais originais do XPM 4.0.096, na imagem fixada,
sem rede e sem alteração do fornecedor, demonstraram:

1. O catálogo legado não reconhece os PUBLIC IDs JATS 1.3, inclusive o MathML3 correto.
2. O caminho Java usa internamente JATS 1.1. Rejeita `dtd-version="1.3"` e
   `fn-type="coi-statement"`, embora este tipo de nota exista na DTD 1.3.
3. O erro residual de Style Checker é a interrupção do packtools embutido por
   `sps-1.10` não suportado. Nesses casos o objeto de validação sequer é criado.
   Portanto, não é evidência de um novo defeito editorial no artigo.

São testes nativos dos métodos estruturais, **não seis novas execuções completas
do XPM online**. Os relatórios completos anteriores permanecem históricos; suas
contagens não são atribuídas aos novos hashes dos pacotes.

A causa técnica está identificada. Não reduzir JATS para 1.1, trocar a declaração
de conflito de interesses ou remover SPS 1.10 para satisfazer o legado. Também
não descontar fatal/erro residual: esta entrega adiciona **zero exceções**.

## Fontes e limite de interpretação

- [DTD Publishing 1.3 MathML3 do NLM](https://jats.nlm.nih.gov/publishing/1.3/JATS-journalpublishing1-3-mathml3.dtd)
  e catálogo local `vendor/jats/1.3/catalog-jats-v1-3-no-base.xml`: identificadores
  correspondentes. A variante padrão usa outro identificador.
- [NLM, fn-type em JATS 1.3](https://jats.nlm.nih.gov/publishing/tag-library/1.3/attribute/fn-type.html):
  admite `coi-statement`.
- [Comunicado SciELO de 06/10/2025](https://groups.google.com/g/scielo-xml/c/MJHQuqRwsgs):
  orienta SPS 1.10 e reconhece erros legados, mas ressalva o DOCTYPE. Consulta
  renovada em 26/10/2026; não foi encontrada nessa fonte dispensa da ressalva.
- [Tarefa oficial packtools #814](https://github.com/scieloorg/packtools/issues/814):
  relaciona SPS 1.10 com JATS 1.3 e continua aberta na consulta. Uma tarefa técnica
  não equivale a aceite editorial de entrega.

Conclusão: corrigir o erro de identificação MathML3 é justificado pelo padrão;
isso não resolve por inferência a aceitação de DOCTYPE no fluxo editorial SciELO.
A restrição de publicação permanece explícita. Não repetir pesquisa aberta de
DOCTYPE na próxima entrega sem nova fonte; avançar o diagnóstico e o fluxo web.

## Qualificação na mesma VPS

Código final candidato `vh1-doctype-20261027-v1`; API/worker ativos permanecem
`vh09-heads-20261021-v1`. Laboratório final:
`/var/lib/idml-vh1-qualification/doctype-20261026-v4`.

| Caso | Offline JATS/SPS baseline | packtools atual | spsvalidator atual |
|---|---|---|---|
| e20240086, cabeçalho corrigido | Válido | 0 erros, 5 avisos | 0 erros, 5 avisos |
| e20240135, cabeçalho corrigido | Válido | 0 erros, 5 avisos | 0 erros, 5 avisos |
| e86, tipo de nota inventado | Inválido | 1 erro, 5 avisos | 1 erro, 5 avisos |
| e86, versão raiz incompatível | Inválido | Execução falhou | Execução falhou |

Oito tentativas modernas: seis recibos nativos concluídos e duas falhas explícitas.
As falhas não são validações bem-sucedidas. Fontes de autoridade coletadas novamente
e concessões restritas aos hashes/escopos do laboratório. Auditoria confirmou
recibos root/0600, vínculo de fonte/escopo, hashes de relatórios, XMLs e manifestos.
Cinco avisos não são aceitos automaticamente. Sem agente de IA ou gasto de API.

O serviço formal atual foi reavaliado com esses recibos: três casos `blocked`,
versão incompatível `validation-unavailable`, todos sem prontidão. Nessa auditoria
o XPM não foi configurado para os pacotes novos; não se reutilizou atestado de
pacote antigo. A composição completa online precisará de execução nova.

Tentativas iniciais ficaram preservadas. V1 foi comparação exploratória sem
regeneração do manifesto; V3 detectou diferenças de serialização/nomes de ativos
na reconstrução de controle. Nenhuma dessas tentativas concede aprovação. A
prova final usa somente V4, com manifesto e reconstrução conferidos.

## Requalificação das provas de código

A suíte ampla inicial encontrou 20 recusas nas provas antigas: o cabeçalho mudou
e o serviço de pacote já havia evoluído na composição anterior. Não atualizar
hashes dentro de provas antigas para fazê-las parecer atuais.

O sucessor nativo `vh1-doctype-native-v2.json` liga somente duas transições exatas:
gerador do PUBLIC ID e serviço formal reavaliado. O gate verifica o hash da prova,
do auditor e de cada fonte atual; predecessor desconhecido, campo extra/ausente,
arquivo não relacionado ou qualquer mutação é recusado. A cadeia histórica mantém
os relatórios e resultados originais. V-10/V-11 têm novas execuções e relatórios
próprios. Isso qualifica a evolução de código, não aprova XML ou publicação.

Dois vínculos adicionais de SPS/data e Wayta estavam desatualizados desde a
integração anterior. Foram conectados à prova composta de 26/10 já auditada,
fixada por hash, com verificação dos arquivos de runtime atuais e negativos de
adulteração. Não se declarou nova execução XPM online ou renovação de consultas.
V-10/V-11 finais estão em `*-vh1-doctype-v3.json`; versões anteriores preservadas.

Conferência na VPS em 27/10: 966 testes Linux aprovados, zero falhas/erros/skip;
três avisos conhecidos de dependência/serialização em testes negativos. Auditoria
reproduziu exatamente o hash da prova nativa de 26/10, sem renovar artificialmente
fontes ou autorizações. Os 1.176 arquivos da candidata foram conferidos; os 25
serviços permaneceram iguais ao inventário inicial de 27/10. `/health/ready` e
`/app` responderam HTTP 200. Diretórios de código público receberam permissão de
travessia para o usuário de teste após uma primeira tentativa de teste sem acesso;
arquivos privados e bytes do código não foram alterados por essa correção.

Fechamento local de 27/10: **2.906 testes aprovados**, zero falhas/erros/skip,
em 1.113,01 segundos. Foram sete avisos de dependência/serialização, sem falha de
teste. Linux: **966 aprovados** em 189,58 segundos. Conjuntos sobrepostos; 41
casos novos neste incremento. Os 101 focados e 48 da cadeia de compatibilidade
também passaram, sem serem somados como testes únicos. Ruff global, mypy dos 132
módulos e conferência de whitespace aprovados. Não foi medida cobertura nova ou
reexecutada a integração externa PostgreSQL. Prova consolidada:
`benchmarks/qualification/reports/vh1-doctype-closure-v1.json`.

As tentativas intermediárias com recusas de provas antigas foram preservadas;
não entram nos totais aprovados finais. A documentação de fechamento foi
sincronizada separadamente do diretório de código congelado. Nada foi ativado
na API/worker; a composição online dos novos pacotes e G-HOMOLOG seguem pendentes.

## Próximo incremento fechado

Atualização de 27/10: o item 1 abaixo foi implementado como diagnóstico web
de leitura, sem nova exceção de compatibilidade. Qualificado localmente e na
VPS, ainda em candidata não ativa. Ver `VH1_VALIDATION_DIAGNOSIS.md`. O próximo
trabalho é o item 2; a atribuição de causa por ocorrência nos pacotes novos
depende da composição completa vinculada aos seus novos hashes.

Atualização posterior de 28/10: composição online nos hashes corrigidos concluída,
sem nova exceção residual. Ver `VH1_MATHML3_COMPOSED_VALIDATION.md`. Prosseguir
para integração da decisão formal, sem repetir a investigação técnica encerrada.

1. Integrar a distinção entre erro XML, indisponibilidade do Style Checker legado
   e ressalva de entrega DOCTYPE no diagnóstico de homologação, usando as causas
   comprovadas aqui. Qualificar eventual regra residual separadamente na ADR-019.
2. Concluir a apresentação/tratamento de avisos e consultas/ORCID pendentes, com
   reexecução completa da composição nos novos hashes; sem aceites automáticos.
3. Requalificar e ativar a combinação com backup/rollback, seguindo os mesmos
   VH-09 (promoção/restauração), VH-10–13 (ciclo/web) e VH-14–20 (operação/RC/E2E).

O bloqueio de publicação não deve virar uma fila de pesquisa indefinida nem impedir
os itens independentes da interface. Liberação ao especialista depende do
G-HOMOLOG; autorização de publicação continua separada.
