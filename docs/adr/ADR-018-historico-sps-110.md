# ADR-018 — Presença de datas de revisão na SPS 1.10

Data: 2026-10-07. Estado: implementação candidata qualificada; não implantada.
Escopo: encerramento técnico da VH-05, dentro da autorização e critérios da ADR-017.

## Evidência e decisão

A seção de histórico da [especificação indicada pelo próprio Packtools](https://docs.google.com/document/d/1GTv4Inc2LS_AXY-ToHT3HmO66UT0VAHWJNOIqzBNSgA/edit#heading=h.history)
identifica recebimento e aceite como obrigatórios, ressalvados os tipos documentais
enumerados. Revisão solicitada/recebida pertence à lista de eventos possíveis.
Quando uma dessas datas é informada, ao menos o ano continua obrigatório.
O documento identifica sua versão como SPS 1.10, junho de 2025.

O export público foi obtido por HTTPS e preservado em área privada, com hash integral
`09ade688acbf1aa6c48324b660bf4baeb9293c92ff315a2d68c371251909bbef` e hash da seção
`111b37673931946a14ae021c1c646afa8422fa582b31e17026c02a48cf0b675e`.
A consulta pelo navegador de pesquisa falhou; o endpoint público de exportação
respondeu HTTP 200, tanto localmente quanto pela VPS. Não houve acesso autenticado.

A configuração das imagens nativas fixadas exige universalmente `rev-request` e
`rev-recd`. A divergência é de obrigatoriedade configurada, não prova de erro nas
datas dos artigos. Corrigir somente esses dois flags no parâmetro de uma execução
isolada. Não inferir que o artigo não passou por revisão; não inserir datas ausentes.

## Limites obrigatórios

- É uma camada de compatibilidade própria, versionada e auditada, **não uma correção
  publicada pelo SciELO** nem aprovação oficial da indexação.
- Biblioteca/configuração instalada permanecem intactas; duas imagens candidatas
  novas e registro separado. As imagens anteriores continuam disponíveis para rollback.
- Configuração nativa deve coincidir byte a byte com a revisada; parâmetros devem
  coincidir em valores e tipos. Outra versão, perfil, override editorial ou regra
  desconhecida falha de forma fechada, sem aplicar a correção.
- Executar o verificador nativo com parâmetros originais e efetivos. Conservar
  auditoria do resultado original. Todos os resultados, fora das duas regras de
  presença, precisam permanecer idênticos. Não filtrar falhas do resultado efetivo.
- Recebimento, aceite e publicação continuam exigidos como antes; severidades,
  datas malformadas, outros tipos e escopo de tradução são preservados.
- Sem edição do XML/canônico, novas consultas editoriais, permissão IA ou dispensa
  de XPM/revisão humana. Informação de revisão disponível não pode ser apagada.
- Novas instruções editoriais mais restritivas exigem outro perfil/qualificação;
  este ajuste não é uma permissão universal para omitir dados conhecidos.

## Aceite

`vh1-history-images-v1.json`: bibliotecas idênticas e 13 contraprovas nativas por
imagem. `vh1-history-linux-v1.json`: quatro execuções completas sobre os XMLs/ZIPs
exatos do v7, sem reconversão, com autoridades e grants ainda válidos inalterados.
`ops/gate_vh1_history.py` verifica ausência de qualquer outra mudança de achados,
fontes, imagens, escopo e contraprovas; integrado ao CI.

VH-05 pode encerrar no desenvolvimento candidato. As três falhas de vínculos de
fórmulas pertencem à VH-06; avisos e revalidação integral, à VH-07. Implantação e
teste do fluxo integrado permanecem VH-14/16/18. Nenhuma aprovação formal ou
liberação G-HOMOLOG decorre deste ADR.
