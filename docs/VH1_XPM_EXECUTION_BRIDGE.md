# VH-02/07 — Conexão interna da evidência XPM, 2026-10-22

Incremento dentro da lista VH1, não uma fase nova. Ponte interna implementada;
executor supervisionado real e compatibilidade completa ainda pendentes.

## Entregue

`services/xpm_execution.py` recebe uma dependência de execução **do servidor**,
nunca relatório, comando, URL ou atestação enviados pelo usuário/agente. Confere
empresa, artigo, fonte IDML, perfil e hashes XML/ZIP; o XML validado deve ser o
único XML contido no ZIP. Recusa caminho inseguro, duplicidade e entrada divergente
antes de chamar o executor. Não extrai arquivos para disco.

O retorno deve corresponder à imagem/ferramenta/versionamento XPM já qualificados,
ao pacote enviado e aos bytes do relatório. O parser calcula contagens a partir
do HTML; um indicador `passed` fornecido pelo executor não é aceito. Erros,
avisos e consultas incompletas são separados. Exceções, HTML, comandos e ambiente
não aparecem no diagnóstico sanitizado. Hash não é assinatura: essa dependência
continua restrita ao servidor, não constitui API para aceitar provas externas.

`assess_package` agora pode consumir esse resultado em vez de informar sempre
“XPM não configurado”. Sem executor, conserva o comportamento anterior. Registro
de validadores inválido impede despacho. Mesmo uma resposta sintética sem erros
mantém `complete=false`, `ready_for_scielo=false` e a pendência explícita de
integração da aprovação. Nenhuma exceção de compatibilidade foi acrescentada.

A revalidação automática deriva o escopo dos bytes reconstruídos e dos registros
da empresa. Falha offline impede envio; as verificações posteriores de grants,
fonte e estado humano continuam valendo. O histórico persiste diagnóstico,
contagens e hashes XPM; repetição retorna histórico sem nova execução, enquanto
uma requisição nova revalida. Isso não promove snapshot nem concede aprovação.

## Qualificação e limites

28 testes novos, incluídos em 176 direcionados locais aprovados, zero falhas,
erros ou skips. Ruff global, mypy 127 módulos, formatação dos seis
arquivos e prova VH-08 aprovados. JUnit: `tmp/vh1-xpm-bridge-final-tests.xml`.
Os testes usam executores sintéticos; não são uma execução real XPM nem medição
de precisão editorial. Não foi repetida a suíte integral de 2.654 testes, cujo
resultado anterior pertence à release `vh09-heads-20261021-v1`.

A candidata está separada em `/opt/idml-platform/releases/vh1-xpm-bridge-20261022-v2`.
O ensaio Linux usa fontes candidatas somente leitura, imagem de qualificação
existente, sem rede, sem volumes/banco ativos, 512 MiB e 0,5 CPU. Não é implantação.
A imagem ativa continua `vh09-heads-20261021-v1`; nenhuma migração ou flag mudou.
A primeira matriz Linux também passou, mas evidenciou um warning de serialização
no controle de resposta inválida. A v2 suprime essa serialização diagnóstica e
revalida o contrato normalmente; uma contraprova verifica ausência de warnings
com valor privado inválido. O primeiro diretório de qualificação foi preservado.

Fechamento v2: **176 testes locais e 176 Linux aprovados**, conjuntos sobrepostos,
zero falhas/erros/skips e um warning de depreciação Starlette por execução. A
contraprova de valor privado inválido não emite warning. Manifesto de 1.127 arquivos
verificado na VPS e todos os containers ativos conferidos contra o estado anterior,
sem mudança. Registro consolidado por hashes:
`benchmarks/qualification/reports/vh1-xpm-execution-bridge-v1.json`.

## Próximo trabalho delimitado

1. Conectar o executor XPM Linux supervisionado ao contrato, com armazenamento
   privado do HTML bruto e prova de execução/consultas. O resumo persistido aqui
   não substitui a retenção do relatório bruto pelo executor.
2. Concluir DOCTYPE/JATS, erro residual e demais consultas sob ADR-019; integrar
   avaliação derivada preservando erros e relatórios originais. Sem waiver genérico.
3. Requalificar com os dois pacotes reais e negativos, implantar a integração e
   então completar promoção/restauração de pacote (VH-09) e ciclo/web/E2E.

Não há nova validação de artigos reais, chamada de IA, G-HOMOLOG ou produção.

## Continuação: executor offline real, 22/10/2026

O limite acima descreve a entrega inicial. Nesta continuação, o executor real foi
conectado e exercitado, ainda isoladamente, sem ativar API/worker.

Arquivos: `services/xpm_socket.py`, `ops/xpm_validator_broker.py`,
`ops/qualify_vh1_xpm_socket.py` e `tests/test_xpm_socket.py`.
O cliente recebe escopo já derivado pelo servidor; não é uma autorização para
clientes HTTP declararem empresa/fonte ou para ignorar grants. As verificações
existentes antes/depois da revalidação continuam necessárias na integração ativa.

### Contrato operacional

- Socket Unix: root autentica UID 10001; cliente autentica UID 0. Sem porta TCP.
- Imagem fixa `sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63`,
  executando `/opt/run_xpm_qualification.py`, sem rede/pull/credenciais.
- Container não root, somente leitura, sem capabilities, 384 MiB, 0,5 CPU,
  64 processos; timeout supervisor de 190 s e transporte com prazo absoluto.
- Pacote limitado a 100 MiB, XML a 8 MiB; ZIP plano seguro, até 100 membros e
  64 MiB expandidos. HTML até 8 MiB, envelope até 12 MiB.
- Reserva inicial de RAM de 768 MiB e de disco acima de 5 GiB; limite monitorado
  de 512 MiB por execução. Diretório privado, até 32 execuções retidas por workdir,
  sem expurgo automático; lock não bloqueante impede dois executores no mesmo
  workdir. Operação persistente deverá usar um único workdir configurado.
- O supervisor remove apenas seu container. Mantém entrada, execução e logs
  privados; cópia selada `report.html` e `evidence.json`, root/0600, fora do mount
  gravável. Pacote transformado pelo fornecedor nunca é promovido.
- Consultas obrigatórias permanecem explicitamente incompletas no modo offline;
  hashes/atestação não equivalem a aprovação nem assinatura de autoridade externa.

### Resultado real

Fonte: pacotes corrigidos em `vh1-journal-metadata-20261016T165250Z`;
hashes originais conferidos com `plan.json`. Escopos laboratoriais preexistentes,
sem alterar grants ou registros de empresas ativas.

| Caso | Bloqueios | Fatais | Erros | Avisos |
| --- | ---: | ---: | ---: | ---: |
| ESA e20240086 | 3 | 4 | 4 | 6 |
| ESA e20240135 | 3 | 4 | 4 | 8 |
| e20240086 sem título da revista | 4 | 4 | 4 | 6 |
| e20240086 XML truncado | 4 | 3 | 1 | 0 |

Todos `completed/attested=true`, `raw_passed=false` e
`required_queries_complete=false`. Esses números são o resultado bruto do XPM
offline, incluindo limitações do ambiente/compatibilidade; não medem precisão
editorial e não são comparáveis diretamente à execução online anterior. O parser
recuperou o HTML legado, registrando 16/13/16/5 ocorrências de recuperação, sem
suprimir severidades. O XML truncado foi enviado diretamente ao executor para
testar defesa em profundidade; o fluxo normal o barra antes do XPM.

Relatórios privados em:
`/opt/idml-platform/private/qualification/vh1-xpm-socket-20261022T180433Z`.
Resumo sanitizado: `benchmarks/qualification/reports/vh1-xpm-socket-real-v1.json`.
Verificados quatro relatórios root/0600 e 25 serviços ativos inalterados.

28 novos testes; matriz de 211 locais e 211 Linux aprovada, um warning Starlette
por execução; Ruff global e mypy 128 módulos aprovados. Sem nova cobertura global.
O caminho de socket foi encurtado para `/run/idml-xpm-<uuid>` e a permissão de
travessia do mount de teste foi corrigida, mantendo seu pai privado. A regressão
Linux foi repetida com tmpfs de 512 MiB para comportar a reserva de upload de
256 MiB; não houve redução desse gate da aplicação. As duas tentativas iniciais
do ensaio e a primeira regressão Linux foram preservadas como falhas de montagem
do teste, não contadas como sucesso.

Candidata final: `/opt/idml-platform/releases/vh1-xpm-socket-20261022-v3`,
1.132 arquivos verificados; arquivo de fontes SHA-256
`359a4d61415ca668995fb29dc0a9eea4b25353740ce02051d14c26e506acb9ae`.
Documentação de fechamento é posterior ao arquivo imutável de fontes testado.
A aplicação ativa continua `vh09-heads-20261021-v1`; nenhuma IA foi acionada.

Próximo: implementar consultas supervisionadas e compatibilidade restante no
executor, qualificar o conjunto e ativar a ligação na API/worker. Esta entrega
conclui a conexão offline e retenção privada, não toda a VH-02/07 nem G-HOMOLOG.

## Continuação: modo online supervisionado, 22/10/2026

`ops/xpm_online_transport.py` fornece o ciclo de vida da rede/proxy; o broker
seleciona modo exclusivamente por registro administrativo `xpm-online-1.0`.
Não há campo de modo/rede/URL aceito do cliente. Offline continua compatível.
O XPM original usa `/opt/run_xpm_online_qualification.py` na mesma imagem fixa.
O proxy, também nessa imagem, admite o catálogo HTTPS e túneis Crossref/ORCID já
qualificados; não há ampliação de destinos nem autorização genérica de navegação.

Antes de executar o artigo, uma sonda isolada deve comprovar três recusas:
localhost, metadados de nuvem e domínio não autorizado. Proxy: UID 65534,
96 MiB, 0,25 CPU, sem capabilities/rootfs gravável/porta publicada. Sonda: 64 MiB,
0,25 CPU, igualmente restrita. Somente o proxy conecta-se à saída bridge; o XPM
fica na rede interna. Não se altera a rede dos serviços existentes.

O supervisor remove IDs exatos da sonda/proxy/rede em `finally`; teste de falha
de limpeza não produz prova de sucesso. Depois do encerramento dos escritores,
sela `proxy-events.jsonl` e `network-evidence.json` root/0600, vinculados por hash.
O broker verifica essa prova antes de emitir o envelope online. A flag
`required_queries_complete` continua falsa: provar transporte não é provar a
validade semântica de todas as respostas. Esta infraestrutura continua candidata,
não serviço multitenant persistente ativado.

### Nova matriz real e evidências

Execução: `/opt/idml-platform/private/qualification/vh1-xpm-socket-online-20261022T183211Z`.
Os hashes dos dois candidatos de referência são idênticos aos do ensaio offline.

| Caso | Bloqueios | Fatais | Erros | Avisos |
| --- | ---: | ---: | ---: | ---: |
| ESA e20240086 | 3 | 1 | 4 | 2 |
| ESA e20240135 | 3 | 1 | 4 | 3 |
| e20240086 sem título da revista | 4 | 4 | 3 | 2 |
| e20240086 XML truncado | 4 | 3 | 1 | 0 |

Quatro diagnósticos atestados, nenhum aprovado, nenhum relatório bruto alterado.
Quatro catálogos HTTPS retornados; nos dois artigos de referência, hash igual ao
consumido pelo XPM e registro único por coleção/ISSNs/acrônimo, com título/editora
exatamente correspondentes. Catálogo SHA-256:
`003921e3d6597dd57406ef86885d140990a0174fe2b326be1e501be70dbfc00a`.
Isso comprova essa comparação do cadastro, não todas as consultas externas.
Nos baselines, 4 túneis Crossref por artigo, 4/5 túneis ORCID e 3/4 recusas Wayta.
Eventos TLS não contêm/decriptam respostas nem comprovam titularidade ORCID.

12 controles de destinos proibidos aprovados; 16 arquivos selados root/0600
conferidos, 25 serviços ativos inalterados. Nenhuma rede temporária com label
`idml.purpose=xpm-supervised` remanescente. Disco continuou com aproximadamente
14 GiB livres. HTML e demais artefatos privados mantidos para auditoria.

24 testes novos; matriz final de **267 locais e 267 Linux**, sobreposta, com um
warning Starlette por execução. Inclui timeout/falha de criação, conexão, sonda,
corpo da execução e limpeza, prova adulterada, integridade e proibição de modo
escolhido pelo cliente. Ajustada a simulação de `chown` nos testes Windows;
falhas dessa primeira execução não contam como aprovação. Ruff global, mypy
128 módulos e formatação aprovados; sem medição global nova de cobertura.

Fontes testadas: `vh1-xpm-online-socket-20261022-v1`, 1.136 arquivos verificados,
arquivo SHA-256 `954f2fd9512c5a7eac7f22be4a9330d4f49926bb2f8136286dee07f90da76456`.
Documentação de fechamento posterior ao arquivo imutável. Prova consolidada:
`benchmarks/qualification/reports/vh1-xpm-online-socket-v1.json`.

Concluída a ligação do **transporte online** ao executor. Ainda não concluídas
as **respostas semânticas obrigatórias/compatibilidade final**. Próximo incremento
deve produzir/validar essas evidências e aplicar ADR-019 em resultado separado,
resolver DOCTYPE/JATS/erro residual, requalificar e então ativar API/worker.
A imagem ativa permanece `vh09-heads-20261021-v1`; sem aprovação XML ou IA ativa.

### Continuação de 23/10

Coleta/avaliação semântica Crossref e ORCID implementada na candidata
`vh1-xpm-semantic-20261023-v3`, com bloqueio explícito de conflitos no pacote.
373 testes locais/373 Linux aprovados; dois artigos e dois negativos reais.
Não conclui todas as consultas, compatibilidade ou aprovação. Os quatro nomes
ORCID não confirmados no e135 permanecem pendências, sem alteração automática.
Evidências, condições de coleta e próximo incremento em
`VH1_XPM_SEMANTIC_QUERIES.md` e seção 41 do plano único.
