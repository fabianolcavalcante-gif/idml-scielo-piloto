# VH-09 — Promoção de correção para versão de trabalho

Estado em 29/10/2026: serviço interno implementado e qualificado; ainda não
conectado ao worker ou disponível como ação web. A aplicação ativa continua em
`vh1-structural-20261028-v1`. Esta entrega integra o VH-09 existente.

## Comportamento entregue

`promote_revalidated_candidate` exige uma revalidação nova do XML e do pacote,
com executores fornecidos pelo servidor. Reconfere empresa, fontes, grants,
perfil, validade, versão atual e estado humano antes de alterar a versão de
trabalho. Relatórios enviados por usuário/modelo não são uma entrada desse serviço.

A política `autocorrection-working-draft-admission-1.0` exige validação offline
válida, Packtools/SPS sem erros e XPM atestado. Erros brutos legados só são
tratados pelas oito ocorrências exatas já qualificadas em ADR-019, com contagens
recalculadas, escopo e prova nativa. Ocorrência adicional continua impeditiva.
Recuperação do HTML do relatório XPM não equivale a erro de sintaxe do XML.

Avisos podem permanecer na versão de trabalho, explicitamente pendentes e sem
aceite automático. Consultas selecionadas ausentes/divergentes impedem promoção.
Wayta auxiliar só admite observação de serviço com aplicabilidade comprovada;
isso preserva revisão de afiliação e não afirma identidade institucional. ORCID
público correspondente também não prova titularidade autenticada.

Uma transação grava snapshot, linhagem, evento de mudança e vínculo ao recibo
privado. A versão anterior continua recuperável. Itens de revisão abertos mudam
de base e versão; artigo com item assumido ou decisão humana anterior é recusado.
Repetir pedido bem-sucedido devolve histórico, inclusive após restauração, sem
mover novamente a versão atual. Pedido antes bloqueado executa validação nova.

Não há nova migração, autorização de publicação, ampliação das três operações
permitidas ou herança de aprovação formal. O chamador precisa confirmar a
transação; rollback desfaz promoção e registro de revalidação. Arquivos órfãos
no armazenamento por hash seguem o tratamento existente, sem referência ativa.

## Verificação

- 60 testes novos; conjunto direcionado de 387 testes aprovado localmente e
  387 na imagem Linux da VPS. São os mesmos casos, não 774 testes distintos.
- PostgreSQL em banco descartável: mesmo pedido promove uma vez; pedidos
  diferentes conflitam; revisão humana mantém lock e bloqueia a promoção;
  rollback externo e dois controles SQL de imutabilidade aprovados.
- Reprodução de política sobre dois relatórios reais e dois negativos fixados:
  e86 elegível como rascunho com pendências; e135 recusado pelas quatro consultas
  de nome público ORCID não confirmadas; negativos recusados. XML offline
  revalidado. Nenhuma nova execução externa, consulta, autorização ou promoção
  real foi feita a partir desses relatórios históricos.
- Ruff, mypy (137 módulos) e diff-check aprovados. Não houve suíte integral,
  nova medição de cobertura ou E2E autenticado neste incremento.
- 25 serviços e contagens do banco ativo preservados; readiness HTTP 200.

Os validadores do ensaio transacional PostgreSQL são sintéticos; o ensaio nativo
separado verifica a política sobre evidências reais históricas. Um não substitui
o teste ponta a ponta do worker com executores reais, ainda previsto em VH-18.

Duas falhas de laboratório foram corrigidas e seus logs preservados: IDs fixos
reutilizados pelas fixtures entre cenários PostgreSQL e reserva padrão de 5 GiB
incompatível com tmpfs de 512 MiB. A execução Linux final usou reserva de 1 MiB
somente no ambiente sintético isolado. A configuração da aplicação não mudou.

Provas: `benchmarks/qualification/reports/vh09-promotion-v1.json` e
`vh09-promotion-native-policy-v1.json`. Scripts repetíveis:
`ops/qualify_vh09_promotion_postgres.py` e `ops/qualify_vh09_promotion_native.py`.
Laboratório: `/var/lib/idml-vh1-qualification/promotion-20261029-v1`.

## Próximo passo delimitado

Reconstruir e revalidar o pacote da versão restaurada, com recibo novo vinculado
ao conteúdo restaurado, sem reutilizar a aprovação anterior. Integrar esse
serviço e a promoção ao ciclo/worker e executores supervisionados nos VH-10/14
já planejados; concluir fluxo web e regressão/E2E nos mesmos VH-11–20.
Não abrir uma fase adicional. VH-09 continua parcial e G-HOMOLOG não foi liberado.

Atualização posterior, 29/10: reconstrução/revalidação restaurada implementada e
qualificada em `VH09_RESTORED_PACKAGE_VALIDATION.md` (seção 51 da lista única).
Próximo trabalho passa a ser integração ao worker/ciclo e executores VH-10/14.
