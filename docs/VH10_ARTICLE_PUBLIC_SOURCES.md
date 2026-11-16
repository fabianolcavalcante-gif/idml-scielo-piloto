# VH-10/14 — Autorização e coleta de fontes públicas por artigo

Incremento de 2026-10-30 qualificado e implantado. Provas finais na seção 53 de
`HOMOLOGATION_VH1_DELIVERY.md`. Release `vh10-sources-20261030-v1`; banco
`e2f314253647`. Não é liberação de homologação.

O administrador da empresa seleciona o artigo na tela **Fontes públicas** e pode
autorizar, renovar ou revogar consultas por 7/30 dias. A decisão vincula empresa,
artigo, IDML e perfil corrente. A aplicação mantém um histórico imutável, com
controle de concorrência e idempotência. Troca da origem, validade encerrada,
revogação e perda da permissão administrativa tornam a autorização inativa.

O supervisor consulta a decisão confirmada no banco pelo entry point fixo do
container gerenciado da API. Não aceita autorização, URL, comando, caminho de arquivo ou
valor esperado fornecido pelo job ou pelo agente. Não concede acesso Docker à
aplicação nem expõe um endpoint HTTP que dispense autenticação. Somente o
administrador autenticado pode registrar a decisão; operadores podem ler o estado.

Com autorização vigente, o broker obtém registros novos de Crossref, ORCID e do
fascículo SciELO já qualificado para ESA/perfil 1.1. Os identificadores extraídos do
XML servem para consulta, nunca como valor de referência aprovado. O contrato
existente e os validadores comparam o retorno independente com o candidato.
Não há suporte novo a outro periódico/ano/template por esta alteração.

Os destinos são fixos, com TLS, DNS público verificado, sem proxy/redirect e com
limites de tempo/tamanho. Ausência de Crossref/cadastro impede construir o bundle;
ORCID indisponível fica registrado como indisponível, não como identidade validada.
Cada bundle é vinculado ao XML/ZIP, expira em no máximo 24 horas e nunca ultrapassa
a autorização. Reutilização exige o mesmo escopo e decisão vigente. Mudança de
pacote exige novas fontes. Renovação guarda o bundle anterior em histórico; corrupção
não é resolvida silenciosamente com uma nova coleta. A publicação utiliza a mesma
trava administrativa do instalador de bundles.

A autorização é conferida antes/depois da coleta e após cada validador moderno e
XPM. Revogação durante execução suprime o resultado corrente; relatórios históricos
permanecem preservados. O XPM também exige consentimento, mesmo quando a validação
moderna não conseguiu concluir. Falta de consentimento nunca concede aprovação.

Limites: 128 registros de fontes por instalação e limites existentes do XPM.
Ao atingir o orçamento, o sistema recusa novas coletas; não apaga provas. O backup
e a gestão da área privada dos brokers continuam no fechamento operacional VH-14/15.
Esta autorização permite consultas/armazenamento de fontes públicas, **não**
modificações automáticas no XML, uso de novos catálogos editoriais ou publicação.

Ainda falta conectar os serviços de aplicação/promoção/restauração ao ciclo IA e
concluir o fluxo web geral e E2E. Agentes continuam desativados. Não houve novo
escopo/fase nem liberação de homologação.

## Fechamento

532 testes locais e 532 Linux aprovados, incluindo 38 novos; conjuntos sobrepostos.
PostgreSQL: concorrência/conflito, rollback, revogação e imutabilidade SQL aprovados.
UI/Node, Ruff/mypy e diff-check aprovados. Dois artigos reais em ambiente isolado:
autorização HTTP, decisão no banco, fontes novas, três validadores e negativa após
revogação, sem arquivos de autorização preparados manualmente. Nenhum grant criado
para artigo/usuário ativo. Avisos/consultas e bloqueio de publicação preservados.

O ensaio usou canônicos e ativos antes qualificados, sem nova ingestão IDML ou IA.
O driver nativo está preservado em
`/var/lib/idml-vh1-qualification/run_article_sources_native.py`, com hash na prova.
Resultados privados em `/var/lib/idml-vh1-qualification/sources-20261030-v1/`.
O teste usa containers/SQLite isolados e o mesmo resolver real de decisão; somente
o destino gerenciado do resolver é redirecionado para o container de qualificação.
Não é um bypass existente na requisição do usuário ou nos jobs.

Backup/restore/rollback/reaplicação aprovados; 345 arquivos por runtime, 25 containers
e dados preservados. Reinício/reconexão e recusa sem consentimento verificados.
Provas em `benchmarks/qualification/reports/vh10-article-sources-*.json`.
Manifesto/arquivo fonte congelados; textos finais no checkout ativo.
