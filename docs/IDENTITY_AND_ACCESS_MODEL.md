# Modelo de identidade e acesso

## Decisão

A primeira versão usa autenticação local com senha Argon2 e sessões opacas armazenadas por hash. Autorização é RBAC multiempresa no backend, com negação por padrão. OIDC poderá substituir a autenticação por adapter; `Organization`, memberships, roles e permissões permanecem internos.

## Entidades

- `Organization`: empresa/tenant e raiz de isolamento.
- `User`: identidade global, desativável sem apagar histórico.
- `Membership`: vínculo único entre usuário e empresa, com um papel ativo.
- `ServiceAccount`: identidade não humana limitada a empresa, scopes, expiração e revogação.
- `SessionToken`: sessão opaca revogável; somente HMAC-SHA256 do token é persistido.
- `OneTimeToken`: convite ou recuperação, de uso único, com finalidade e expiração.

Um usuário pode pertencer a várias empresas. Toda requisição de domínio informa `X-Organization-ID`; o backend valida organização, membership e permissão. Identificadores de outra empresa retornam 404 para reduzir enumeração.

## Matriz RBAC

| Permissão | Org admin | Operador | Revisor | Release manager |
|---|:---:|:---:|:---:|:---:|
| administrar empresa/membros | ✓ | — | — | — |
| ler recursos/jobs | ✓ | ✓ | ✓ | ✓ |
| criar/alterar recursos | ✓ | ✓ | — | — |
| enviar artefato/criar job | ✓ | ✓ | — | — |
| aplicar revisão | ✓ | — | ✓ | — |
| solicitar aprovação editorial | ✓ | ✓ | ✓ | ✓ |
| aprovar release | ✓ | — | — | ✓ |
| ler auditoria | ✓ | — | — | ✓ |

Papéis desconhecidos e permissões não listadas são negados. Administrador de plataforma é excepcional, auditado e não será usado no fluxo diário.

## Login, logout, convite e recuperação

- login normaliza email, verifica Argon2, emite token aleatório de alta entropia e grava evento de auditoria;
- mensagem de falha é genérica; rate limiting e lockout progressivo usarão Redis na interface pública;
- logout revoga a sessão atual;
- desativação ou incremento de `token_version` revoga todas as sessões do usuário;
- convites e recuperação usam token opaco armazenado por hash, finalidade única, TTL e consumo atômico;
- mudança de email, senha, MFA, papel e release exigirá reautenticação recente;
- senha mínima inicial: 14 caracteres; senhas nunca entram em logs.

## MFA e reautenticação

O Gate G5 implementa MFA TOTP com segredo cifrado, proteção contra replay e dez
códigos de recuperação de uso único persistidos somente como HMAC. Habilitar MFA
revoga as sessões anteriores. WebAuthn permanece uma evolução futura; TOTP é o
segundo fator suportado nesta fase.

Ações sensíveis exigirão autenticação ocorrida nos últimos 10 minutos e, quando configurado, segundo fator:

- alterar memberships/roles;
- criar ou rotacionar service accounts;
- alterar política de release;
- aprovar release;
- exportar auditoria ou restaurar backup.

Convites, alteração de papéis, solicitação/aprovação editorial e exportação de
auditoria exigem autenticação dos últimos 10 minutos e MFA verificada na sessão.
A organização nunca pode ficar sem ao menos um administrador ativo.

## Sessões

- TTL padrão: 8 horas, máximo configurável de 7 dias;
- tokens são opacos, nunca JWT sem revogação;
- rotação no login e após elevação/reautenticação;
- revogação individual e global por `token_version`;
- IP e user-agent são armazenados apenas como hash;
- cookies futuros serão `Secure`, `HttpOnly`, `SameSite=Strict` e protegidos contra CSRF; a API inicial usa Bearer.

## Service accounts

Service accounts não fazem login interativo, não herdam papel humano e têm scopes explícitos, tenant fixo, expiração, rotação e revogação. Seus secrets serão mostrados somente uma vez e persistidos por hash. Não poderão aprovar release.

## Isolamento multiempresa

- banco: toda tabela de domínio possui `organization_id`; queries incluem tenant;
- cache/fila: chaves carregam tenant ou apontam para job cujo tenant é validado no banco;
- storage: chave `organization_id/prefixo-hash/hash` e volume sem acesso público;
- logs/auditoria: `organization_id` e correlation ID, sem conteúdo do artigo;
- workers: carregam job e tenant do banco; payload não escolhe tenant;
- OpenClaw: sem acesso direto e sem autoridade de autorização.

O teste `test_user_cannot_access_other_organization` é regressão obrigatória do CI.
