# H1 — Pacote corrigido e triagem conservadora de PDF

Data: 2026-09-29. Sem implantação e sem aprovação SciELO.

## Candidata preparada

`ops/package_h1_corrected_candidate.py` verifica o hash da candidata de metadados,
confere IDML/PDF/figuras contra manifesto e empacota sem ler o XML gold.
Histórico preservado; saídas locais privadas em
`benchmarks/private/output/h1-publication-metadata-v1/packaged.xml` e `candidate.zip`.

- XML empacotado: `32e71ba24570b2c43f7f8d190cc8055b521768941a7519970d91dfeb8f7a747c`.
- ZIP: `44f30381779f0f520780b272b95dfcfd54312a70a7c17012f08ace7aaaabe825`.
- Tamanho: 1.094.843 bytes; sete arquivos de conteúdo mais manifesto interno.
- Empacotamento repetido: bytes iguais; validação offline do XML empacotado: válida.

Evidência: `benchmarks/qualification/reports/h1-corrected-package-v1.json`.
Não confundir pacote interno com entrega final, que ainda exige controles/relatórios.

## Diagnóstico de nome de PDF

`ops/rendition_name_diagnostic.py` compara nomes reais no ZIP com o nome esperado
pelo validador e com o PDF associado ao basename XML. Sua saída é diagnóstica,
não modifica XML/ZIP nem concede waiver. Rejeita caminho não suportado, membro
duplicado, ambiguidade e idioma de tradução não resolvido. O PDF principal não
substitui PDF de tradução ausente. Não comprova correspondência visual do PDF.

No runtime local instalado, ambos os artigos produzem
`validator-derived-name-conflict`. A lista real vem do ZIP, não da propriedade
`filenames` do runtime, que não representa necessariamente todos os membros.
Evidência: `benchmarks/qualification/reports/h1-rendition-name-triage-v1.json`.

Dez testes sintéticos cobrem presença, ausência, PDF de outro nome, conflito,
duplicidade, caminhos e tradução. Nenhum erro externo foi removido do resultado
formal. Ainda falta fechar compatibilidade normativa e implementação do validador;
não renomear arquivos com underscore apenas para satisfazer a ferramenta antiga.

Regressão: **662 testes aprovados, três avisos, cobertura 87,86%** da aplicação.
Artefatos `tmp/h1-package-triage-tests.xml` e `tmp/h1-package-triage-coverage.json`.
Ruff/formatação aprovados nos arquivos alterados; Mypy aprovado em 97 arquivos.

## Execução externa impedida por recurso disponível

Preflight VPS: MemAvailable 759.988 KiB (aproximadamente 742 MiB), abaixo dos
768 MiB mínimos do executor, antes mesmo do cliente de teste. Disco disponível
14.939 MiB; banco/Redis OK. Não foram enviados novos arquivos privados nem
executados validadores nessa candidata. Não se reduziu limite nem se parou serviço.

Próximo: com reserva suficiente, enviar só candidata/ZIP, validar sequencialmente,
comparar achados por regra e limpar cópias. Se a baixa disponibilidade persistir,
avaliar uma janela de operação acordada ou capacidade adicional; não declarar
qualificação externa com base em teste local.

A integração do novo catálogo no bundle/worker e a promoção da imagem candidata
permanecem condicionadas à requalificação. XPM, H2–H4 e G-HOMOLOG continuam abertos.
