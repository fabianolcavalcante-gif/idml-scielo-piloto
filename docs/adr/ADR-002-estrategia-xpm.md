# ADR-002 — Estratégia de integração XPM

- Status: revisado com autorização do proprietário; aceito com restrições
- Data original: 2026-08-24; revisão: 2026-10-15

## Contexto

O XPM integra o pacote SciELO e fixa dependências antigas. O ensaio inicial
Linux parou por falta de Tk e área de logs gravável. Isso foi interpretado como
necessidade de Windows, mas não demonstrava incompatibilidade. Em 2026-10-15,
a distribuição oficial 4.0.096-R20231215 executou sem alterações de fonte na
VPS Linux, gerando relatórios para dois artigos e três controles negativos.
O proprietário determinou manter tudo na mesma VPS e autorizou os pacotes necessários.

## Decisão

Substituir a exigência de Windows por executor Linux isolado, sem privilégios,
desacoplado e na mesma VPS. A interface permanece exclusivamente web para o usuário.
A aplicação enviará pacote imutável e receberá relatório/evidências. Falha,
consulta omitida ou ausência de relatório nunca será sucesso. A IA pode acionar
e interpretar a ferramenta, não substituir o resultado real nem dispensar bloqueios.

Essa decisão aprova a direção arquitetural, **não** a compatibilidade SPS 1.10
nem a ativação do executor no serviço em produção. O ensaio offline identificou
rejeição de SPS 1.10/JATS 1.3 nas regras legadas; não mudar o artigo para SPS antigo.

## Consequências

Não há contratação de host, instalação no computador do usuário ou upgrade
obrigatório de hardware. Bibliotecas foram instaladas somente na imagem privada
de teste. VH-02 conserva compatibilidade/consultas pendentes; VH-14/16 integra
o executor supervisionado. Confirmar uso em serviço/licenciamento e avaliar
o risco do runtime legado antes da ativação. O pipeline Linux mantém DTD,
Packtools/SPS e regras próprias. A saída transformada do XPM exige nova
validação e vínculo de hash antes de promoção; não reutilizar atestado da entrada.

Evidência: `../VH1_XPM_LINUX_QUALIFICATION.md` e
`benchmarks/qualification/reports/vh1-xpm-linux-v1.json`.
