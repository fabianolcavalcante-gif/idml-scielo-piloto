# ADR-013 — Egress controlado do provider OpenClaw

- Status: aceito com restrições
- Data: 2026-08-28

## Contexto

O gateway OpenClaw dedicado precisa alcançar o provider em uma futura avaliação, mas não deve obter
egress irrestrito nem tornar a credencial acessível à API ou ao worker. O usuário autorizou reutilizar
a chave OpenAI já configurada no OpenClaw existente; essa decisão cria acoplamento de rotação entre os
dois ambientes.

## Decisão

O Compose base continua inerte. Um overlay opt-in injeta `IDML_OPENAI_API_KEY` somente no
`openclaw-idml` e o conecta a uma rede interna de provider. O gateway só sai por um Squid dedicado,
sem porta publicada, cuja ACL permite exclusivamente `CONNECT api.openai.com:443`. Apenas o proxy
participa de uma rede com egress. API e worker não recebem a chave.

O staging não altera `IDML_FEATURE_OPENCLAW=false` nem `IDML_FEATURE_AI_SWARM=false` e não chama
`/v1/responses`. O kill switch recria o gateway pelo Compose base e remove proxy e redes de provider.

## Consequências

A rota de provider pode ser validada sem executar agentes, enquanto o caminho padrão permanece sem
credencial e sem egress. A chave compartilhada não aparece no repositório, no JSON ou nos logs, mas
sua rotação exige coordenação com o OpenClaw existente. Uma chave exclusiva continua sendo uma
melhoria futura possível, não um requisito para o staging autorizado.
