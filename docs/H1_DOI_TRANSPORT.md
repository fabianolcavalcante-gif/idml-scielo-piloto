# H1 — Transporte isolado de autoridade DOI

Incremento de 2026-09-30; candidato de laboratório, sem implantação ativa.

## Implementado

- Broker aceita configuração opcional `doi_authority` somente no registro do
  servidor. O protocolo de clientes continua rejeitando campos adicionais.
- Manifesto fixado por SHA-256 identifica XML, snapshot, data e origem Crossref.
  A origem declarada não autentica uma resposta: a coleta administrativa confiável
  continua sendo requisito. Usuários não podem cadastrar esse manifesto.
- Leitura no host exige caminhos absolutos sem links, arquivos regulares, dono root
  e nenhum componente gravável por grupo/outros. Limites: manifesto 8 KiB e
  resposta 10 MiB. Vínculo ao XML e validade de sete dias conferidos antes do Docker.
- Cópias por execução são montadas somente leitura; rede desabilitada, usuário
  10001, limites de memória/CPU e reserva do host preservados.
- Wrapper candidato Packtools confere novamente DOI, ISSN, hashes e prazo, usa
  a comparação nativa e restaura a função de consulta mesmo após falha.
- Configuração ausente mantém modo anterior; configuração parcial ou inválida
  falha fechada. SPSValidator com essa opção é recusado até ter integração própria.

O diretório atual `/opt/idml-platform` pertence a idmladmin; não serve como raiz
de confiança para essas autoridades. A prova usou staging sintético privado em
`/root/idml-doi-qualification`, sem mudar permissões da aplicação.

## Evidência Linux

Imagem candidata Packtools:
`sha256:6812b87e87f0d92a898747f6f6183ee0b9702e6faf0180e64a9eebd566e12f18`.
Base verificada:
`sha256:4a35ec1dba3c62a8fa52cfdda87b3908c873c02034371fb7809a0fed1ca5ad61`.

Prova com os mesmos staging e argumentos de montagem do broker, mas entrypoint
de diagnóstico restrito à regra DOI nativa: dados sintéticos correspondentes
aceitos; título/autores divergentes rejeitados. Nenhum corpus real transferido.
Contêineres e arquivos temporários da prova removidos; diretório de laboratório,
código e imagem mantidos. Readiness de banco e Redis: OK.

Não é evidência do socket completo com autoridade, do pacote SPS, do XML completo
ou do fluxo API/worker/UI implantado. Não modifica o registro ativo de validadores.
Evidência pública: `benchmarks/qualification/reports/h1-doi-transport-v1.json`.

## Sequência restante

Atualização: fluxo completo Packtools pelo socket qualificado, com correção
do gerador de autores nativo identificado durante as contraprovas. Ver
`H1_DOI_SOCKET.md`; o item 1 abaixo foi concluído para a fixture sintética.

Regressão local final: 750 testes aprovados, três avisos, 88,02% de cobertura
do código `src/idml_foundation` (não inclui scripts ops nesse percentual).
49 testes focados aprovados; Ruff e gate operacional V10 aprovados.

1. Qualificar a execução completa broker/socket/Packtools com essa configuração,
   incluindo erros de staging, desconexão e limpeza; não substituir prova nativa
   por aprovação presumida do fluxo completo.
2. Integrar ao SPSValidator vinculando o XML extraído ao hash do pacote autorizado,
   sem selecionar XML ambíguo e sem extrapolar o corpus permitido.
3. Qualificar com candidatos reais dentro da política de corpus, mantendo dados
   externos de autoridades em escopo explícito. Não marcar DOI aprovado apenas por
   hash correto ou ausência de erro de transporte.
4. Continuar autoridades editoriais de seção/fascículo, ORCID, achados de conteúdo,
   XPM e depois implantação reversível/H2-H3. G-HOMOLOG permanece pendente.
