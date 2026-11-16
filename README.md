# Plataforma IDML → XML SciELO

Monorepo da plataforma de conversão auditável de IDML para SciELO SPS/JATS.

Estado atual: **preparação prioritária da versão funcional para testes do especialista**;
V-12 permanece incompleta. Sequência e critérios em
[Plano de homologação funcional](docs/EXPERT_TEST_READINESS_PLAN.md): H0–H4/G-HOMOLOG antes
da prontidão completa de produção. Acesso do especialista ainda não liberado. O pipeline gera JATS
1.3/SPS 1.10 e pacote determinístico sem IA, com revisão humana auditável,
interface mínima, MFA, dupla aprovação editorial e contratos assistivos com patches
atômicos de `RichText` e MathML seguro. O Gate G6-T foi aprovado apenas para iniciar a Fase 7;
No novo artigo e20240135, figuras, mídia, ordem global, 43 fórmulas MathML, hierarquia e notas foram
corrigidas e aprovadas; os 12 domínios semânticos e 39/39 cross-references passaram em 7C-05.
Em 7C-06, o pacote formal reproduzível com XML, PDF e sete JPEGs passou no gate com zero erro real;
as exceções dos validadores são fechadas por código, quantidade e evidência.
Em 7C-07, os seis domínios alterados passaram por proponente, dois críticos e adjudicador; os seis
casos ficaram aceitos somente para revisão humana, e cinco controles negativos falharam fechado.
Em 7C-08, os dois artigos foram requalificados, 380 testes passaram (87,31% de cobertura) e a nova
imagem foi implantada na VPS com backup, restore, rollback e 18 gates isolados aprovados.
V-07 passou no corpus atual; isso não representa garantia de generalização para outros artigos.
XPM SPS 1.10, as etapas V-12 a V-15 e a homologação final continuam pendentes, portanto
`READY_FOR_SCIELO` segue corretamente negado.

## Estrutura

```text
src/idml_foundation/   API, domínio da fundação, segurança e worker
corpus/                manifestos e expectativas; binários privados fora do Git
schemas/               contratos JSON Schema versionados
tests/                 testes unitários, integração e segurança
migrations/            migrations Alembic
deploy/                 imagens, Compose e configuração operacional
ops/                    backup, restore e verificações
docs/                   arquitetura, ADRs e runbooks
profiles/               perfis de periódico e mapeamentos de estilo versionados
vendor/                 DTD JATS oficial fixada para validação offline
```

## Desenvolvimento

Pré-requisitos: Python 3.12 e Docker Compose.

```bash
python -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
pip install --no-deps -e .
pytest
ruff check .
ruff format --check .
mypy src
```

Conversão local determinística:

```bash
idml-admin pipeline-convert --input artigo.idml --output artigo.xml \
  --report validation.json --raw raw.json --canonical canonical.json
```

O XML gold não é parâmetro do conversor. Avaliações restritas usam somente gates
locais; binários reais não entram em Git, CI, imagem ou VPS.

Para o stack completo:

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.dev.yml up --build -d
```

Use apenas credenciais locais geradas para desenvolvimento. Nunca copie secrets de produção para `.env`.

## Segurança

- isolamento por organização é obrigatório no backend;
- autorização possui negação por padrão;
- sessões são opacas e revogáveis;
- MFA TOTP, códigos de recuperação e reautenticação protegem ações sensíveis;
- revisão e aprovação editorial usam papéis distintos e histórico append-only;
- artefatos são imutáveis e endereçados por SHA-256;
- arquivos IDML são inspecionados antes de persistência;
- XML externo é processado sem entidades e sem rede;
- logs não devem conter tokens, senhas ou conteúdo integral de artigos.

### Recuperar a senha pelo portal

Em um computador pessoal, marque **Confiar neste navegador** ao entrar. Durante 30 dias,
a opção **Recuperar senha** na tela de entrada permite informar o e-mail e escolher outra
senha nesse mesmo navegador. O recurso requer HTTPS ou o endereço local do piloto.

Para quem perdeu o acesso ou mudou de navegador, um administrador da plataforma pode
entrar com MFA, abrir **Usuários** e gerar um link após confirmar a identidade do titular.
O titular abre o link privado, escolhe uma senha de ao menos 14 caracteres e entra no portal.
O link vale por 30 minutos. A troca encerra as sessões anteriores e revoga a confiança
dos navegadores. O titular pode marcar a opção novamente no próximo login.

Consulte [docs/PHASE_5_HUMAN_REVIEW.md](docs/PHASE_5_HUMAN_REVIEW.md), a
[revisão do Gate G5](docs/PHASE_5_GATE_REVIEW.md) e o
[plano por fases](PLANO_DESENVOLVIMENTO_POR_FASES.md). A correção de generalização atualmente em
curso é controlada por
[docs/PHASE_7_CORRECTIVE_E20240135.md](docs/PHASE_7_CORRECTIVE_E20240135.md).
