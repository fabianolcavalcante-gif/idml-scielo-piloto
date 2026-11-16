# VH-02/07 — Verificação semântica de consultas selecionadas

Checkpoint 23/10/2026. Candidata isolada na mesma VPS; não é ativação na API/worker
nem conclusão integral da homologação. Não amplia a allowlist de autocorreções.

## Entrega

O registro administrativo `xpm-online-semantic-1.0` seleciona coleta independente
após o XPM original. Modo offline e online anterior continuam disponíveis. Não há
URLs, comandos, rede ou modo controlados por uploads, cliente HTTP ou agente IA.

O XML exato fornece DOI e ORCIDs. Parser sem carregamento externo, recusa entidades
e subset interno, UTF-8, até 8 MiB, 100 mil elementos e profundidade 128; nomes
e identificadores ambíguos/duplicados/fora do formato qualificado são recusados.
Somente 17 alvos no máximo: um DOI e até 16 ORCIDs de contribuições presentes.

Coletor administrativo separado do proxy do XPM:

- `api.crossref.org/works/<DOI escapado>` e `pub.orcid.org/v3.0/<ORCID>/person`;
- DNS deve resolver somente IPs públicos; conexão fixa no IP resolvido, TLS com
  verificação do hostname e certificados, sem proxy do ambiente ou redirecionamento;
- status 200 e JSON exigidos; até 1 MiB por resposta e 2 MiB agregados;
- subprocesso por consulta, até 15 s, inclusive DNS/TLS/leitura; orçamento total
  de 70 s, sem retry infinito ou espera por aprovação;
- respostas/horários/hashes selados em `query-evidence.json`, root/0600. Erros
  externos geram recibo indisponível, sem publicar mensagem de exceção.

O prazo total do cliente Unix passa a 360 s; limites originais do XPM são mantidos.
O coletor consulta fontes públicas de forma independente: os recibos NÃO afirmam
que são os bytes internos recebidos pelo XPM nem que todas suas consultas passaram.
Não são assinatura externa. São evidências confiadas ao supervisor, não aceitas
de usuários/IA por endpoint público.

## Critério e efeitos

O avaliador confere versão, empresa/recurso/fonte/perfil/XML/ZIP, hash do relatório,
lista exata de alvos sem duplicações, origem, hash da resposta e idade de até
24 horas, recusando horário futuro. Crossref deve corresponder ao DOI e ISSN,
título do artigo/periódico e lista ordenada de autores. ORCID deve corresponder
ao identificador e nome público; NFC/caixa/espaços são normalizados, sem fuzzy,
remoção de acentos, abreviação inferida, reordenação ou renomeação automática.

Resultados: correspondência, conflito ou indisponibilidade. Diagnóstico público
contém hashes/tipos/códigos, não nomes ou respostas brutas. Correspondência de nome
é consistência de registro público, NÃO titularidade autenticada ou prova de autoria.
Nome público incompleto também pode resultar em não confirmação; isso não prova
que o ORCID seja errado. Esse limite deve permanecer visível na homologação.

A avaliação do pacote agora bloqueia conflito mesmo com XPM sem erros. Ausência
ou evidência semântica inválida conserva pendência. Relatório/contagens originais
não são reduzidos. `required_queries_complete`, `complete` e `ready_for_scielo`
continuam falsos; demais fontes, compatibilidade e aprovação são requisitos separados.

## Qualificação real

Diretório privado final:
`/opt/idml-platform/private/qualification/vh1-xpm-semantic-20261023T150553Z`.
Os dois XML/ZIP de referência permanecem os mesmos do checkpoint cadastral de
16/10 e do ensaio online anterior; não houve correção editorial neste incremento.

| Caso | Crossref | ORCID | XPM bruto: bloqueios/fatais/erros/avisos |
| --- | --- | --- | --- |
| e20240086 | DOI/ISSN/títulos/autores correspondem | 3 correspondem | 3/1/4/2 |
| e20240135 | DOI/ISSN/títulos/autores correspondem | 4 nomes não confirmados | 3/1/4/3 |
| e20240086 sem título da revista | Conflito detectado | 3 correspondem | 4/4/3/2 |
| e20240086 XML truncado | Não coletado: XML inválido | Não coletado | 4/3/1/0 |

Os quatro registros ORCID do e135 retornaram identificador correto e nome público.
Dois não trazem sobrenome separado, e os quatro não correspondem pela comparação
exata admitida. Verificação diagnóstica não encontrou alias público exato nem
diferença restrita a acentos. Não se usaram essas verificações para aceitar
similaridade, trocar nomes ou inferir identidade. Permanecem quatro pendências
delimitadas para análise por fontes autorizadas; não foram removidas para passar.

Quatro relatórios atestados, 13 recibos (incluindo repetição no controle negativo),
19 arquivos selados root/0600 e hashes conferidos. 25 serviços ativos preservados;
nenhuma rede temporária com label do executor restante. Aproximadamente 14 GiB
livres na VPS. Sem novo pacote de sistema, credencial, migração, hardware ou IA.

Tentativa intermediária `vh1-xpm-semantic-20261023T150220Z` preservada como parcial:
o container de regressão simultâneo consumiu a reserva de memória, e o supervisor
recusou o último caso. O inventário registrou apenas esse container adicional,
sem alteração nos 25 serviços. Matriz final repetida SEM regressão Linux paralela;
depois executados os testes Linux. Nenhuma proteção foi desativada.

## Regressão e continuidade

55 novos testes, incluídos em **373 locais e 373 Linux aprovados**, conjuntos
sobrepostos; um warning Starlette por execução. Cobrem origem, identificador,
entidades/complexidade XML, vencimento/futuro, pacote/relatório/empresa diferente,
duplicação/ausência de recibos, respostas inválidas, conflitos, indisponibilidade,
DNS privado, redirect, TLS, orçamento e bloqueio do pacote com XPM sem erros.
Ruff global, mypy 130 módulos e formatação dos nove arquivos aprovados.
Sem nova suíte integral/cobertura global ou afirmação de CI integral aprovado.

Arquivo de fontes final: `vh1-xpm-semantic-20261023-v3`, 1.142 arquivos;
SHA-256 `1871c0657b75568a7aa9920ca446a3fac781657ceb492ac47793405f5917f379`.
V1/v2 preservadas; v3 acrescenta bloqueio explícito no pacote e sua contraprova.
Documentação final é posterior ao arquivo imutável de fontes testado.

Relatórios: `benchmarks/qualification/reports/vh1-xpm-semantic-v1.json` e
`vh1-xpm-semantic-real-v1.json`. A aplicação ativa permanece
`vh09-heads-20261021-v1`; não houve ativação da candidata.

Próximo trabalho finito: esclarecer os quatro registros ORCID por fontes
autorizadas, integrar resultados derivados ADR-019 aos mesmos recibos/pacotes e
concluir DOCTYPE/JATS, erro residual e demais consultas. Requalificar antes da
ativação. Depois seguir VH-09/10–20 do plano único, sem adicionar fase.
