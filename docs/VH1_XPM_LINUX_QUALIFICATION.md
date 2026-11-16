# VH-02 — XPM executado na VPS Linux

Data: 2026-10-15. **Viabilidade headless comprovada; XML e release não aprovados.**

## Decisão e escopo

O proprietário autorizou instalações para manter tudo na VPS atual. ADR-002 passa
a prever worker Linux isolado na mesma máquina, mantendo a experiência web.
Não foi criado serviço Windows nem instalada ferramenta no computador do usuário.
Este incremento qualifica execução, não entrega a integração web supervisionada.

A documentação oficial prevê CLI e configuração offline:
[XPM](https://documentacao.scielo.org/books/scielo-pc-programs/page/xml-package-maker-xpm),
[instalação/configuração](https://documentacao.scielo.org/books/scielo-pc-programs/page/como-instalar).
No pacote inspecionado, `-auto` evita interface e abertura do navegador, mas mantém
`ReportsMaker.save_report`. A falta de Tk/log gravável no primeiro ensaio não
justificava exigir Windows. Com as dependências corretas, o original executa.

## Runtime e isolamento

- ZIP oficial: `1b22157b9e816255db8d8910acc46a13b78c0f286cbb68155a39a95ed0f0bdec`.
- Imagem privada: `sha256:dfcc38f04950f075f03a6f1d48ab654ec4fc3be32c600c62b25ee76f9da98116`.
- Python 3.8 / Debian bookworm; Tk 8.6 e Java 17; dependências diretas originais
  `Pillow==6.2.2`, `packtools==2.4.2`; transitivas fixadas `lxml==6.1.3`, `picles.plumber==0.11`.
- Sem alteração de fonte XPM; hash de cada arquivo original conferido após execução.
  Configuração documentada: `ENABLED_WEB_ACCESS=off`, preferência `packtools|java`.
- Usuário 65534, rede desligada, raiz somente leitura, capabilities removidas,
  no-new-privileges, sem banco/segredos/Docker socket, pasta privada por caso.
- Uma execução por vez; 384 MiB de memória sem swap adicional, 0,5 CPU, 64 processos,
  timeout interno 150 s/externo 190 s e tmpfs 32 MiB. Build limitado a 512 MiB/0,5 CPU.
- Pacotes de sistema instalados apenas no container, não no Python/serviços do host.
  Tentativa inicial bullseye falhou em downloads apt; bookworm/HTTPS resolveu.
  Isso não alterou a distribuição oficial nem o conteúdo dos artigos.

Runtime legado é uma restrição de segurança: esta imagem **não está aprovada para
entrada arbitrária/execução online de produção**. Hardening e supervisão em VH-14.

## Resultado nativo

Execução corrente: `20261015T141256Z`. Dados completos, HTMLs e logs privados em
`/opt/idml-platform/private/qualification/vh1-xpm-linux-20261015T141256Z`, com cópia
local em `benchmarks/private/output/vh1-xpm-linux-20261015T141256Z`.
Relatório público: `benchmarks/qualification/reports/vh1-xpm-linux-v1.json`.
SHA-256: `2cde59cf4b7d4aff064884304daf288c809b4ec8db940cac82d0d1ccd886dd5d`.
Ensaios anteriores `140338Z` e `140615Z` são históricos; não sobrescritos.

| Caso | Bloqueios | Fatais | Erros | Avisos | Resultado do ensaio |
|---|---:|---:|---:|---:|---|
| e20240086 original | 3 | 4 | 4 | 6 | CLI e relatório concluídos; XML não aprovado |
| e20240135 original | 3 | 4 | 4 | 8 | CLI e relatório concluídos; XML não aprovado |
| e20240086 sem journal-title | 4 | 4 | 4 | 6 | Ausência explicitamente detectada |
| e20240086 sem imagem gf01 | 4 | 4 | 4 | 6 | Arquivo ausente explicitamente detectado |
| e20240086 XML truncado | 4 | 3 | 1 | 0 | XML inválido explicitamente detectado |

Os dois primeiros são positivos de **execução**, não exemplos aprovados pelo XPM.
Cada controle negativo precisa de mensagem específica nova, não apenas aumento
de contagem. Até o XML truncado retorna exit code zero: ler relatório é obrigatório.
Todos os insumos originais/ZIPs permaneceram idênticos. Mutantes têm identidades
próprias e nunca recebem atestado vinculado ao ZIP original.

Tempos CLI: 2,39–3,09 s; maior RSS de subprocesso medido: 59.988 KiB (~58,6 MiB).
Não é pico total do container nem benchmark de carga/capacidade universal.
Os 25 serviços observados mantiveram imagem, horário de início, execução e saúde;
readiness/banco/Redis permaneceram `ok`. Sem reinício/deploy/ativação OpenClaw.
Pós-checagem: 1.425 MiB de memória disponível e 14 GiB livres; nenhum container
de ensaio em execução. Imagem API/worker continua `4fcf4766…`.

## Bloqueios agora demonstrados

1. Packtools 2.4.2 incorporado declara `sps-1.10` não suportado. As regras XPM
   esperam SPS 1.8/1.9 e rejeitam a representação atual de `pub-date`.
2. O catálogo legado não reconhece o PUBLIC ID JATS 1.3 e usa DTD 1.1, gerando
   incompatibilidades de `dtd-version` e `fn-type`. Não mudar XML correto para
   satisfazer catálogo antigo e não suprimir esses erros genericamente.
3. Modo offline impede autoridades de periódico, DOI e ORCID. Comparações com
   cadastro ausente aparecem como erros/avisos. Não são consultas concluídas,
   nem prova de erro nos valores do artigo. Demais achados precisam de triagem.
4. HTML original exige recuperação do parser (100 registros por relatório de
   artigo; cinco no truncado). Totais únicos/versionamento foram extraídos pelo
   parser existente e conferidos; recuperação permanece explícita, sem "limpar"
   o relatório ou tratar HTML recuperado como aprovação.
5. O XML reempacotado pelo XPM tem bytes diferentes da entrada. É derivado de
   diagnóstico e **não** foi promovido. Se usado na entrega, precisa de auditoria
   de delta e repetição das validações sobre seu hash exato.

Nenhum relatório oficial foi fabricado/editado; nenhum aviso foi aceito; não houve
rebaixamento SPS/JATS, alteração científica ou modificação da política formal.
O parser/contrato existentes não foram alterados.

## Testes locais e reexecução

49 testes direcionados aprovados: novo ensaio/isolamento/mutações, distribuição
XPM e release; `tmp/vh1-xpm-linux-tests.xml`. Ruff/formatação dos novos scripts
aprovados. Não é suíte integral nem nova medição de cobertura.
O resumo público confere hashes do runner, entradas, execução, logs e relatórios,
reproduz os mutantes e usa o parser real. Falta/troca de evidência aborta o resumo.

Scripts: `ops/qualify_vh1_xpm_linux.py`, `ops/run_xpm_qualification.py`,
`ops/export_vh1_xpm_evidence.py`, `ops/summarize_vh1_xpm_linux.py`;
receita: `deploy/Dockerfile.xpm-qualification`.

## Próximo passo dentro da fila existente

**VH-02 continua parcial, mas não falta mais host nem prova de execução Linux.**
O próximo trabalho é delimitar compatibilidade SPS 1.10/JATS 1.3 e consultas
obrigatórias: mapear cada achado legado à regra/fonte vigente, qualificar o caminho
de autoridades no mesmo servidor e definir a integração sem alterar silenciosamente
o XPM ou sua exigência. Não repetir o spike para procurar um Windows inexistente.
Se a distribuição oficial não cobrir o perfil, apresentar a decisão de política
necessária com evidências; não marcar VH-02/07 completos por analogia com SPS.
Worker supervisionado/UI em VH-14/16; VH-08 pode seguir independentemente.
G-HOMOLOG e produção editorial permanecem fechados.
