# H1 — Decisão necessária para executar pacotes reais

DECISÃO RESOLVIDA: em 2026-09-29 o responsável autorizou os envios/testes na VPS.
Exceção aplicada aos dois candidatos de desenvolvimento, com limpeza confirmada.
Resultados e sequência: `SCIELO_READINESS_GAP_PLAN.md`. O texto abaixo preserva o
contexto anterior à autorização, não representa bloqueio atual.

Verificado em 2026-09-29, antes de transferir qualquer conteúdo privado.

`CORPUS_POLICY.md` proíbe copiar o corpus para a VPS, imagens, Git ou CI.
Os validadores Linux isolados foram qualificados na VPS somente com dados
sintéticos. A execução integrada dos pacotes reais requer conciliar essa regra
com o ambiente de execução; a autorização genérica de continuidade não foi
interpretada como alteração silenciosa da política.

No computador atual, `docker` não foi encontrado no PATH e `wsl --list --quiet`
retornou ajuda/erro, sem listar uma distribuição utilizável. Isso não prova ausência
de outros runtimes fora do PATH, mas não há executor Linux local qualificado.

## Opção proposta ao responsável

Autorizar exceção limitada aos pacotes candidatos dos dois artigos ESA de
desenvolvimento já autorizados: enviar à própria VPS apenas XML, PDF e imagens
necessários, nunca IDML, catálogos, gold ou holdout. Usar diretório privado,
contêineres sem rede, execução sequencial, sem acesso público e relatórios
minimizados; remover as cópias temporárias ao final e registrar a limpeza.
Avaliar a exposição a backups/snapshots antes da transferência; não prometer
eliminação de cópias preexistentes ou geridas pelo provedor.

Alternativa: provisionar executor Linux local isolado, preservando a regra atual.
Isso pode requerer instalação de Docker/WSL e reinício do computador.

Nenhuma opção foi aplicada. Nenhum pacote privado foi transferido. A política
vigente permanece inalterada. Após a decisão, registrar escopo e executar H1;
XPM compatível e demais critérios continuam obrigatórios, sem aprovação presumida.
