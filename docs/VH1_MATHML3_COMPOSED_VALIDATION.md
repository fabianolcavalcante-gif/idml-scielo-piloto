# Composição online dos pacotes MathML3 — 28/10/2026

Executado o próximo passo autorizado: validação completa dos dois pacotes com
PUBLIC ID MathML3 corrigido, usando os mesmos bytes nos validadores modernos e
no XPM online. Nenhum relatório antigo foi reapresentado como execução nova.

Fonte congelada: `vh1-followups-20261027-v1`, 1.191 arquivos. Laboratório:
`/var/lib/idml-vh1-qualification/composed-mathml3-20261028-v1`.
Execução XPM: `vh1-xpm-composed-20261028T112542Z` dentro desse laboratório.
API/worker ativos permanecem em `vh09-heads-20261021-v1`.

## Resultados efetivos

| Caso | Validador local | packtools / spsvalidator | XPM original: bloqueantes/fatais/erros/avisos |
|---|---|---|---|
| e20240086 corrigido | Sem erros | Cada um: 0 erros, 5 avisos | 3 / 1 / 4 / 2 |
| e20240135 corrigido | Sem erros | Cada um: 0 erros, 5 avisos | 3 / 1 / 4 / 3 |
| Sem título do periódico | `missing-journal-title` | Cada um: 0 erros, 5 avisos | 4 / 4 / 3 / 2 |
| XML malformado | `xml-not-well-formed` | Indisponíveis; entrada não provisionada | 4 / 3 / 1 / 0 |

Os quatro casos terminam `blocked`, com `ready_for_scielo=false`. No controle
sem título, os validadores modernos não apontaram erro: o controle foi detectado
pelo validador local, pela consulta Crossref e pelo XPM. A validação em camadas
continua necessária; “zero erros modernos” isoladamente não autoriza entrega.
Os controles negativos são pacotes deliberadamente alterados; não constituem
novas versões publicáveis e não receberam regeneração de manifesto de entrega.

Nos dois artigos corrigidos, seis ocorrências por artigo são reconhecidas pelas
regras já qualificadas de DOI/SPS. Permanecem, nas contagens derivadas, um fatal,
um erro e dois/três avisos. As contagens originais estão preservadas. Não foi
adicionada exceção para DOCTYPE/Style Checker, nem dispensada a ressalva editorial.

## Avisos e consultas

Avisos modernos confrontados com a estrutura, preservando severidade e sem aceite:

- e20240086: dois de afiliação, um de apêndice e dois de seção, em cada ferramenta.
- e20240135: quatro de afiliação e um de apêndice, em cada ferramenta.

Os códigos conhecidos foram vinculados ao grupo estrutural completo, sem inventar
correspondência de uma ocorrência a um nó quando o sanitizador compartilha o
localizador. Nenhum conteúdo, metadado ou identificador foi modificado.

As consultas novas mantiveram sete vínculos autor/ORCID coincidentes no depósito
Crossref. Os três nomes públicos de e20240086 coincidem; em e20240135 permanecem
dois nomes públicos incompletos e dois sem coincidência exata. As quatro pendências
continuam visíveis e não são apagadas pelos vínculos do depósito. Isso não autentica
titularidade. As três observações Wayta realizadas retornaram timeout; não são
consultas institucionais do artigo nem comprovação de identidade.

## Auditoria e limites

- Quatro execuções XPM online e seis recibos nativos modernos novos.
- Treze recibos de consultas conferidos, 22 arquivos privados com proprietário
  root e modo 0600; hashes de relatório, pacote, XML, escopo, grants e bundles
  conferidos. Autorizações novas apenas no laboratório, sem concessões na aplicação.
- Dois hashes compostos reproduzidos; limites de rede testados e recursos
  temporários removidos pelo executor.
- Manifestos dos dois pacotes corrigidos íntegros; hashes iguais aos qualificados
  após a correção de cabeçalho. Validação local e diagnóstico da candidata
  reproduzidos para os quatro casos sem alterar resultados ou conceder aprovação.
- 25 serviços preservados; 1.191 arquivos de código conferidos; ready/app HTTP 200.

Pacotes corrigidos:

- e20240086: `07a4789dfcb70aed8436b3f69a67be9b3112954f054857b249f693b20f00f7d4`.
- e20240135: `de753e0aad72debdf6fee7c770b1c82f2ed6d59824bf9548c0cc45ba4b3d8a1b`.

Provas públicas sem conteúdo dos artigos:
`vh1-mathml3-composed-real-v1.json`, `vh1-mathml3-composed-audit-v1.json` e
`vh1-mathml3-composed-closure-v1.json`, em `benchmarks/qualification/reports/`.
Os scripts de laboratório e logs ficam preservados. As primeiras tentativas de
auditoria identificaram falta de permissão de leitura de diretórios de outro UID
e comparação indevida de grupo estrutural vazio. A execução final usou leitura
privilegiada em montagens somente leitura e a mesma exclusão de grupos vazios do
classificador existente. As evidências dos validadores não foram alteradas.

Não houve nova mudança de runtime, execução de IA, aceite de aviso, aprovação
SciELO ou ativação. Os 297 testes locais/Linux e seis verificações JavaScript
da candidata são os do fechamento de avisos/consultas; não representam uma nova
suíte executada durante esta composição.

## Próximo passo no plano existente

A composição nos novos hashes está concluída. Prosseguir no VH-02/07 com a
integração da decisão de compatibilidade residual JATS/Style Checker, estritamente
vinculada às evidências, e com a saída formal para avisos/consultas pendentes.
Separar liberação técnica para homologação de aceite editorial para publicação;
não reabrir pesquisa DOCTYPE sem fonte nova ou alterar XML para satisfazer ferramenta
legada. Em seguida, ativação com backup/rollback e conclusão dos mesmos VH-09–20.

Atualização de 28/10: a regra residual foi implementada e qualificada usando
esta evidência selada, com reprodução no instante original. Ver
`VH1_STRUCTURAL_COMPATIBILITY.md` e seção 48 da entrega VH1. Nenhum resultado
desta composição foi reescrito ou considerado uma execução nova.
