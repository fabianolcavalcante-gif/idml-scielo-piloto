# Fase 4 — Validação, fidelidade e pacote

- Data: 2026-08-24
- Implementação: concluída
- Gate G4: bloqueado por conteúdo/editorial e XPM externo
- Produção: não autorizada

## Componentes entregues

- `ValidationEngine` unifica severidade, categoria, versão, hash do candidato e
  estado `completed/unavailable/failed`;
- validação offline JATS 1.3 + SPS baseline e adaptadores isolados para
  Packtools/SPSValidator;
- `FidelityEngine` compara Canonical, XML e PDF por título, autores, corpo,
  referências, figuras e tabelas, acionando OCR somente sem camada textual;
- `SafeRepairEngine` limita reparos a whitespace de `id/rid`, registra apenas
  hashes antes/depois e revalida após patch;
- `PackageBuilder` renomeia arquivos segundo o profile ESA, reescreve os hrefs,
  exige XML/PDF/assets íntegros e gera ZIP byte-determinístico;
- `ConversionManifest 1.0.0` registra origem, arquivos, tamanhos, hashes,
  versões de validadores e digest do conjunto candidato;
- parser XPM `1.0.0` extrai versão e totais do relatório sem confiar no HTML;
- Release Policy `1.0.0` falha fechada, vincula XPM ao SHA do pacote e permite
  override humano somente para revisão editorial após gates técnicos válidos.

## Decisão sobre validadores SciELO

O tag Packtools `4.16.11` aponta para o commit
`fe1ada8cd7cc638c8eab7ab1651f3b4f891d08e7`, mas seu metadata interno informa
`4.16.10` e o StyleChecker clássico rejeita SPS 1.10/JATS 1.3. Essa
incompatibilidade é reportada como `unavailable`, nunca mascarada.

Para SPS 1.10, o gate executa o SPSValidator `0.3.0` no commit
`d1aa774d4e335d6559c24c2c728471b8fd2e6e42`, que usa o pipeline novo de regras
do Packtools. Ambos os adaptadores são isolados do runtime principal. O commit e
o hash da ferramenta ficam registrados no resultado.

## Segurança e privacidade

- nenhum binário do corpus entra em Git, imagem, CI ou VPS;
- o gate local verifica cada fonte restrita pelo manifesto antes de ler;
- ZIP e XML reais de avaliação ficam somente em `artifacts/`, ignorado pelo Git;
- relatórios processáveis registram hashes e métricas; conteúdo não vai para
  logs operacionais;
- XPM histórico prova o parser, mas não vale para um candidato de hash diferente.

## Operação local restrita

```text
python ops/gate_phase4.py --source-root <CORPUS_PRIVADO> \
  --manifest corpus/manifests/esa-e20240086.json \
  --spsvalidator-json <RESULTADO_DO_MESMO_ZIP>
```

O código de saída é zero somente para `READY_FOR_SCIELO`. `2` significa gate
negado ou indisponível e é comportamento esperado enquanto houver pendências.

