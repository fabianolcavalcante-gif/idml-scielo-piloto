# Avisos e consultas — fechamento em 28/10/2026

Implementado o próximo passo de `VH1_VALIDATION_DIAGNOSIS.md`, na candidata
`vh1-followups-20261027-v1`, armazenada e testada na VPS, ainda não ativa.

O diagnóstico por job agora informa a próxima ação para avisos locais, dos
validadores modernos e do XPM. As contagens originais são preservadas. Os
resumos persistidos dos validadores modernos contêm totais; não contêm decisões
individuais de aceite. A interface explicita essa limitação e orienta análise
do relatório da mesma versão, correção sustentada nas fontes e revalidação.
Não inventa classificação por ocorrência nem aceita avisos automaticamente.

Nas consultas, apresenta fonte, estado registrado, hash da evidência, hash do
alvo e ação. Diferencia nome público ORCID incompleto, indisponível ou divergente;
vínculo Crossref coincidente, não depositado, inválido ou conflitante; e nome
ambíguo. Vínculo no depósito não oculta problema no registro público. Nenhum
resultado autentica titularidade. Ausência no depósito não autoriza excluir
ORCID do XML. Falha de rede não é motivo para alterar metadados.

Wayta tem observação de disponibilidade separada da identificação institucional.
Resposta HTTP não verifica uma afiliação. O caráter consultivo aplica-se somente
ao perfil já qualificado; validar afiliações nas fontes continua obrigatório.

O endpoint continua somente leitura, autenticado e isolado por empresa. A
projeção recusa versões desconhecidas, recibos incoerentes, alvos duplicados,
conjuntos incompletos e tentativas de afirmar identidade/aprovação. Textos das
ações são fixos; conteúdo livre de fontes não é exibido. Ler um job não renova
consultas antigas.

## Evidências

- **297 testes selecionados locais e 297 Linux aprovados**, mesmo conjunto,
  zero falhas/erros/skip; 41 casos novos incluídos.
- Seis verificações JavaScript com DOM controlado, incluindo escape dos campos
  novos e descarte de respostas tardias após mudança de contexto.
- Releitura da prova nativa de 26/10 fixada por hash: dois artigos, sete vínculos
  depositados coincidentes, quatro pendências de nome público preservadas e
  dois timeouts Wayta sem alegação de identidade institucional.
- V-10/V-11 reexecutados localmente e na VPS; Ruff global, mypy de 134 módulos
  e whitespace aprovados. Não houve alteração do gerador ou validadores.
- 1.191 arquivos da candidata conferidos; 25 serviços preservados;
  `/health/ready` e `/app` responderam HTTP 200.

Provas: `v10-operational-workflow-vh1-followups-v1.json`,
`v11-robustness-mutation-vh1-followups-v1.json` e
`vh1-followups-closure-v1.json`, em `benchmarks/qualification/reports/`.
Sem nova cobertura global, E2E visual em navegador ou integração PostgreSQL.
A releitura nativa é histórica, não nova execução online.

## Próximo passo

Atualização de 28/10: composição online executada e auditada nos hashes corrigidos.
Resultados e continuidade em `VH1_MATHML3_COMPOSED_VALIDATION.md`. O texto abaixo
registra o passo autorizado e agora concluído.

Executar a composição online completa com os dois pacotes MathML3 corrigidos
e controles negativos. Atualizar consultas e recibos sobre os hashes exatos,
auditar os resultados originais e confrontar o diagnóstico com esses resultados.
Depois, ativação qualificada e continuidade dos mesmos VH-09–20/G-HOMOLOG.
Sem nova fase ou liberação de publicação.
