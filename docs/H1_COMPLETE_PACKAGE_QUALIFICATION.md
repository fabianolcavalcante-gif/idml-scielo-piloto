# H1 — Pacote sintético completo no executor Linux

Incremento de 2026-09-29. H1 permanece em andamento, sem liberação para especialista.

## Implementação

`ops/build_h1_synthetic_package.py` reutiliza o artigo canônico sintético V-05 e
o empacotador da aplicação. Gera XML, PDF em branco estruturalmente legível, SVG
referenciado e manifesto; nomes, referências e hashes são determinísticos.
É um pacote completo em composição de arquivos, não um artigo editorial aprovado.
Nenhum conteúdo do corpus privado é lido ou enviado.

O cliente de smoke agora aceita o caso `complete`; o observador exige, nesse caso,
execução `completed` de ambos os validadores, além de transporte íntegro e limpeza.
Receber relatório de falha não basta para aprovar esse novo cenário.

## Resultado observado na VPS

Executados sequencialmente Packtools e SPSValidator com imagens fixadas, sem rede,
com limites de recursos e o broker corrigido no incremento anterior. Diretório:
`/opt/idml-platform/qualification/h1-validator-complete-v1`.

| Validador | Execução | Críticos | Erros | Avisos | XML aprovado |
|---|---|---:|---:|---:|---|
| Packtools | completed | 1 | 3 | 7 | não |
| SPSValidator | completed | 1 | 4 | 7 | não |

SPSValidator não reproduziu `validator-exception-or-invalid-output` com o pacote
completo. Isso comprova que o caminho integrado consegue concluir uma execução;
não identifica isoladamente qual elemento ausente causou a exceção anterior,
nem justifica suprimir exceções futuras. Os achados permanecem bloqueadores.

Identidades, horários de início e contadores de reinício dos serviços existentes
permaneceram iguais. Socket e temporários do broker foram removidos. Os arquivos
sintéticos e scripts permanecem no diretório de qualificação para reprodução.
Não houve implantação do worker, daemon instalado, envio de corpus privado ou
ativação de produção. Checagem de saúde anterior à execução: banco/Redis OK.

## Próximo passo

Evidência pública com hashes: `benchmarks/qualification/reports/h1-complete-package-v1.json`.
Regressão completa: **645 testes aprovados, três avisos, cobertura 87,83%** da
aplicação. Artefatos locais: `tmp/h1-complete-tests.xml` e
`tmp/h1-complete-coverage.json`. Ruff/formatação aprovados nos arquivos alterados;
Mypy aprovado nos 97 arquivos da aplicação. Não renovados os gates de implantação.

1. Qualificar os pacotes reais autorizados no fluxo integrado, preservando a
   governança do corpus; analisar e corrigir achados reais sem alterar o gold.
2. Resolver a integração XPM compatível com SPS 1.10 e sua execução atestada.
3. Fechar autorização formal do candidato e renovar evidências afetadas antes
   da implantação H2 e do fluxo/interface H3. H4/G-HOMOLOG permanecem pendentes.

O ensaio não cobre carga prolongada, falhas reais de daemon/OOM nem aceitação
editorial. A matriz simulada de falhas continua documentada separadamente em
`H1_BROKER_FAILURE_QUALIFICATION.md`.
