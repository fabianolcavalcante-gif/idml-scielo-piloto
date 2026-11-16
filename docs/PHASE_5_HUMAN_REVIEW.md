# Revisão humana e interface mínima — Fase 5

## Escopo entregue

A Fase 5 adiciona uma camada editorial auditável sobre o modelo canônico. O
revisor nunca edita XML: ele assume um `ReviewItem`, aplica um patch JSON
restrito ao campo em revisão e informa uma justificativa. O backend cria um
novo `DomainSnapshot`, reconstrói JATS, executa a validação offline e persiste
`ReviewDecision` e `ReviewBuild` como histórico append-only.

## Concorrência e integridade

- claim e decisão exigem `expected_version`;
- updates condicionais impedem dupla resolução e sinalizam conflito HTTP 409;
- somente `replace` é permitido, em conteúdo canônico editável e no escopo do item;
- IDs, schema, evidências e hashes de origem não podem ser alterados pelo patch;
- snapshot anterior permanece imutável; o novo aponta para `parent_snapshot_id`;
- outras pendências ativas são rebaseadas para a nova revisão e voltam à fila;
- diff, histórico, XML e relatório de validação são consultáveis por tenant.

## Identidade e empresa

A API oferece login/logout, recuperação de senha, MFA TOTP, códigos de
recuperação, sessões e revogação. Organizações possuem membros, convites e
papéis. Convite, mudança de papel, solicitação/aprovação editorial e exportação
de auditoria exigem autenticação recente e MFA. Todas as queries de domínio
validam `X-Organization-ID`; recursos de outra empresa retornam 404.

## Interface

`/app` entrega uma interface sem dependências externas, protegida por CSP. Ela
inclui seleção de empresa, jobs/timeline, upload IDML/PDF/imagens, fila e detalhe
de revisão, evidências, alternativas, modelo, histórico, diff, XML/validação,
usuários/convites, MFA/sessões, aprovações e auditoria/download controlado.

O bearer token permanece somente em `sessionStorage`. Artefatos e XML são
baixados por requisição autenticada, com verificação de hash e evento de
auditoria.

## Aprovação editorial

Revisão e aprovação possuem permissões distintas. Uma solicitação exige MFA e
duas aprovações de pessoas diferentes; o solicitante não pode aprovar a própria
solicitação. O estado final é `editorially_approved`, deliberadamente separado
da Release Policy técnica. Esse fluxo não concede `READY_FOR_SCIELO`.

## Operação

A migration `c4e5f6a7b8c9` adiciona MFA, histórico de revisão e aprovação. O
segredo `IDML_MFA_ENCRYPTION_KEY` deve ser independente do session pepper e não
pode ser trocado sem um procedimento de rotação dos segredos TOTP cifrados.
Nenhum arquivo do corpus restrito deve ser enviado à VPS.
