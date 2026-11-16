# VH-02/07 — compatibilidade SPS 1.10 e datas

Checkpoint: 2026-10-17. Incremento da entrega 1, sem fase nova.
**Três regras adicionais implementadas e qualificadas; XML/homologação/publicação
continuam não aprovados.** Não houve implantação na aplicação ativa.

## Resultado e limite

O XPM oficial converte `sps-1.10` em `float(1.10)`, ou seja, `1.1`, e entra no ramo
anterior a 1.8 para validar datas. Sua tabela de versões também termina em 1.9.
O ensaio executou os métodos originais na VPS, sem rede e sem alterar vendor:
SPS 1.10 com datas corretas gera três bloqueios de datas e um erro de versão;
a mesma estrutura sintética em SPS 1.9 é aceita por esses métodos. A segunda
entrada é contraprova de laboratório, não alteração dos XMLs dos artigos.

Regras implementadas em `release/xpm_sps_compatibility.py`, sobre a avaliação DOI
anterior preservada:

- `xpm-sps110-version-table-1.0`: mensagem exata de tabela legada e data correspondente.
- `xpm-sps110-date-type-1.0`: duas ocorrências exatas, vinculadas aos dois nós XML.
- `xpm-sps110-date-combination-1.0`: combinação exata `pub`/`collection`.

As três ocorrências de datas são tratadas em conjunto: ausência, duplicidade,
snippet divergente, mensagem/severidade desconhecida ou evidência insuficiente
impedem a exceção. Marcadores visuais de espaço do HTML nativo são reconhecidos
somente na forma exata do formatter; nenhum caractere arbitrário é removido.

Contrato `xpm-sps-compatibility-evidence-1.0`: escopo empresa/artigo/IDML/perfil/XML/ZIP,
XPM/imagem e três módulos oficiais fixados; duas validações independentes concluídas
dos mesmos XML/ZIP, imagens/versões qualificadas, perfil e hash da prova. Evidência
é criada pelo executor confiável; não pode vir de payload HTTP ou saída de IA.
Erros/críticos/bloqueios, timeout e ausência de um dos validadores recusam o contrato.
Avisos não são dispensados nem convertidos em aprovação.

O perfil qualificado é restrito: ESA 1.1, SPS 1.10/JATS 1.3, publicação eletrônica,
data completa com ISO correspondente e coleção anual do mesmo ano. Recusa datas
impossíveis/futuras, atributos legados, precisão incompleta, duplicações e conteúdo
extra. Não inventa data, não modifica XML e não generaliza para AOP ou outros perfis.

## Fontes e DOCTYPE

Fontes primárias reconsultadas em 17/10:

- [Comunicado SciELO de 06/10/2025](https://groups.google.com/g/scielo-xml/c/MJHQuqRwsgs):
  marcações 1.10 e falsos erros legados, com ressalva explícita de DOCTYPE.
- [Resposta da Publicação SciELO de 17/03/2026](https://groups.google.com/g/scielo-xml/c/KiC-TDlazJE):
  não acrescentar `pub-type` indevido para contornar o XPM.
- [Packtools, tarefa 814](https://github.com/scieloorg/packtools/issues/814):
  relaciona SPS 1.10 a JATS 1.3; continua aberta na consulta. Não é autorização
  editorial que revogue a ressalva do comunicado.

Conclusão delimitada de DOCTYPE: o relatório original identifica PUBLIC ID 1.3
desconhecido e valida internamente contra DTD 1.1. Isso explica incompatibilidade,
mas não autoriza dispensar o fatal. Nenhuma fonte consultada nesta etapa resolveu
a ressalva de entrega. **Não alterar DOCTYPE, `dtd-version` ou `coi-statement` apenas
para satisfazer o legado; não conceder exceção de DTD.** A Release Policy permanece
intacta. A pendência externa não impede os itens independentes VH-08/11 do plano.

## Evidências reproduzíveis

Prova nativa: `benchmarks/qualification/reports/vh1-xpm-sps-dates-probe-v1.json`.
SHA-256: `e5f3bfeb57e8c06b60b25cca94d7c86611ebea1bf27bb14d20337c4d980a44de`.
Dez casos sintéticos: versões 1.10/1.9/2.0, dia ausente, calendário inválido,
atributo legado, formato errado, tipo desconhecido, dia na coleção e duplicidade.
Os negativos evidenciam também limites do próprio legado: calendário inválido
não recebe erro específico nele; a aplicação verifica o calendário por conta própria.

Diretório VPS: `/opt/idml-platform/private/qualification/vh1-xpm-sps-dates-20261017`.
Imagem original `sha256:43ca49864959e4106d7cbb571f6f64a1222f9865068fee1ce61953aa19886d63`;
container temporário sem rede/porta, rootfs somente leitura, UID 65534, 256 MiB,
0,5 CPU e remoção automática após terminar. Nenhum pacote novo instalado.

Prova final: `benchmarks/qualification/reports/vh1-sps-compatibility-v2.json`.
SHA-256 dos bytes: `500b9cad7dd1293ef1650f34b870d640c8c5beb5a4b40559d8930264815c9760`.
v1 é intermediária, anterior ao ajuste final de tipagem; preservada, não é o gate ativo.

Os dois XMLs/ZIPs e relatórios XPM são os mesmos do checkpoint cadastral. A auditoria
verificou novamente entradas privadas, hashes, fontes atuais e provas independentes.
**Não houve nova execução integral do XPM ou dos validadores modernos:** reutilizam-se
execuções atestadas para os mesmos bytes; a avaliação de compatibilidade é nova.

| Artigo | XPM bruto: bloqueios/fatais/erros/avisos | Exceções DOI | Novas ocorrências SPS/data | Ainda não resolvidos: bloqueios/fatais/erros/avisos |
|---|---|---:|---:|---|
| e20240086 | 3 / 1 / 4 / 2 | 2 | 4 | 0 / 1 / 1 / 2 |
| e20240135 | 3 / 1 / 4 / 3 | 2 | 4 | 0 / 1 / 1 / 3 |

Contagens brutas e `XpmResult.passed` permanecem intactos. Fatal, erro residual,
avisos e consultas não foram dispensados. `homologation_ready` e `release_approved`
continuam obrigatoriamente falsos. O controle anterior de imagem ausente continua
vinculado à prova predecessora; escopo/pacote diferente não pode reutilizar sucesso.

## Testes e próximo trabalho

**136 testes direcionados aprovados**, incluindo 76 novos testes de contrato/gate,
isolamento, versões, datas inválidas, evidência adulterada e preservação de bloqueios.
JUnit: `tmp/vh1-sps-final-focused.xml`. Ruff global, tipagem dos 115 módulos e
formatação dos seis arquivos novos aprovados. Gates V10/V11 e cadeia nativa
predecessora continuam aprovados; novo gate incluído no CI:

```powershell
.venv/Scripts/python -m ops.gate_vh1_sps_compatibility
```

Não foi repetida a suíte integral/cobertura nesta etapa. O resultado 2.166/89,33%
da seção 30 é anterior ao novo módulo, não a cobertura atual dele. V09, formatação
histórica e orçamento do CI continuam em VH-17; sem declaração de CI global aprovado.

Wayta: DNS resolveu na VPS, mas uma tentativa HTTPS ao endpoint de instituições
terminou em timeout de conexão após 12 segundos, sem resposta HTTP. Isso não prova
que o serviço foi encerrado, nem valida instituições. Sem fallback HTTP, mudança
de proxy ou marcação de consulta concluída. Pós-checagem mostrou 25 containers em
execução, com API/worker/banco/Redis IDML saudáveis; não houve restart/deploy.

Próximo incremento: qualificar tratamento de consultas Wayta indisponíveis e sua
necessidade normativa, mantendo a pendência distinguível de erro XML. DOCTYPE/JATS
permanece dependência específica de compatibilidade/entrega, não pesquisa aberta
sem limite. Se a dependência externa persistir, avançar VH-08 (operações automáticas
permitidas) e VH-11 (diagnóstico web) conforme seção 8, sem simular aprovação.
Integração do novo avaliador ao serviço supervisionado/UI ainda pendente; sem IA ativa.

Atualização 2026-10-19: o incremento Wayta foi implementado/qualificado em
`VH1_WAYTA_QUERY_REQUIREMENTS.md`; preserva integralmente esta avaliação. Próximo
desenvolvimento é VH-08, conforme seção 32 do plano único; as pendências XPM não
foram dispensadas.
