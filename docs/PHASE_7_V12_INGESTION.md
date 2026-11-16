# V-12.2 — Ingestão limitada e amplificação de memória

Data: 2026-09-22. Estado: **correções locais e ensaio isolado aprovados; V-12.2 incompleta**.
Nenhuma mudança foi implantada nos serviços existentes. Sem upgrade ou novas inferências de IA.

## Problema comprovado e correções

Um IDML sintético de 8.000.399 bytes, contendo XML com dois milhões de elementos, excedeu
o limite de 256 MiB do container: `OOMKilled=true`, saída 137. O arquivo estava abaixo dos
limites antigos em bytes. O teste usava um container descartável sem rede; os 25 serviços
existentes foram preservados. Não foi falha de uma conversão editorial em produção.

Foram implementadas quatro proteções:

- Tamanho de XML individual e de `mimetype` verificado no diretório ZIP antes de CRC/leitura.
- Orçamento agregado de **16 MiB de XML por IDML**, conferido antes da descompactação.
  Os limites externos de 100 MiB/upload e 500 MiB/ZIP expandido não foram aumentados.
- Pré-análise XML sem construir a árvore, em blocos de 64 KiB, com orçamento compartilhado de
  **200 mil unidades de complexidade**: elementos, atributos, comentários e instruções de
  processamento. Dividir o conteúdo entre vários XMLs não reinicia o orçamento. DOCTYPE,
  entidades e XML malformado continuam proibidos. Somente após essa análise a árvore é criada.
- Leitura de artefatos confere tamanho declarado, limite configurado e tamanho do arquivo aberto;
  a leitura tem limite explícito de tamanho declarado + 1, detecta crescimento/truncamento e
  preserva a verificação SHA-256. Nenhum arquivo preexistente é apagado por essas recusas.

Esses limites são políticas conservadoras da candidata, não uma garantia universal de memória.
Nos artigos de referência, os XMLs somam 1.848.962 e 2.172.275 bytes e consomem 44.253 e
51.877 unidades de complexidade, respectivamente. Ambos cabem com folga, mas outros artigos
legítimos mais complexos podem exigir revisão desses limites, sempre com novas medições.

## Ensaio na VPS

Cada caso roda em processo/container novo: 256 MiB, sem swap adicional, 0,25 CPU, rede
desabilitada e filesystem somente leitura. Somente os quatro módulos candidatos são montados
read-only sobre a imagem anterior. O observador externo preserva reserva de 512 MiB no host,
disco abaixo de 90%/mínimo 5 GiB livres, readiness até 500 ms e CPU até 85% entre amostras.

A primeira tentativa foi interrompida por pressão de CPU após o caso de 100 mil elementos.
A segunda terminou e registrou o OOM do caso de dois milhões. Os relatórios foram preservados.
O cálculo de CPU passou a exigir intervalo mínimo de um segundo inclusive entre casos curtos;
o limiar de 85% não mudou. Não é possível atribuir o pico inicial exclusivamente ao laboratório.

Após a correção, os oito casos da matriz ampliada passaram:

| Caso | Resultado | Pico RSS aproximado |
|---|---|---:|
| 100 mil elementos | Parsing aceito | 56 MiB |
| 500 mil elementos | Recusado por complexidade | 49 MiB |
| Dois milhões de elementos | Recusado, sem OOM | 67 MiB |
| XML individual maior que 32 MiB | Recusado antes de descompactar | 75 MiB |
| `mimetype` excessivo | Recusado | 44 MiB |
| ZIP acima do limite expandido configurado | Recusado | 43 MiB |
| XML agregado 5 bytes abaixo de 16 MiB | Parsing aceito | 78 MiB |
| XML agregado 11 bytes acima de 16 MiB | Recusado | 62 MiB |

O RSS inclui a geração do fixture e o parser, não somente o processamento XML. O teste do
limite expandido usa configuração reduzida de 1 KiB; **não descompactou 500 MiB**. Os casos
de volume não incluem o mapeamento canônico, construção de JATS, snapshots e pacote completo.

Na matriz final: 38 amostras, aproximadamente 899 MiB de RAM disponíveis no pior momento,
readiness máximo de 53,978 ms, nenhum OOM, serviços preservados e container removido.
O gate exige RSS até 192 MiB nos casos medidos, mas não autoriza produção ou fecha V-12.2.

## Evidências e regressão

- Interrupção inicial: `benchmarks/qualification/reports/v12-ingest-observation-attempt1.json`.
- Antes da correção de complexidade: `v12-ingest-observation-before-v1.json` na mesma pasta.
- Matriz corrigida inicial: `v12-ingest-observation-after-v1.json`.
- Matriz ampliada final: `v12-ingest-observation-after-v2.json`.
- Gate: `v12-ingest-gate-v1.json`; fontes candidatas vinculadas por SHA-256; execução na CI.
- Testes: `tmp/phase7-v12-ingest-tests.xml`, `tmp/phase7-v12-ingest-coverage.json`.

**453 testes aprovados, três avisos, cobertura 87,57%**. São 25 regressões novas de ingestão
e do gate; Ruff, formatação e mypy aprovados. Relatórios anteriores V-09/V-10/V-11 são
preservados; a requalificação dos fontes alterados usa relatórios próprios com sufixo
`v12-ingest-v1`. Evidência histórica não é reescrita para corresponder aos novos hashes.

Requalificação final: `benchmarks/qualification/reports/v12-ingest-requalification-v2.json`,
**18/18 gates aprovados**, 106/106 stories preservadas e ambos os artigos com os mesmos hashes
de XML e zero bloqueio semântico. Validadores externos conferidos por replay vinculado ao hash,
sem nova execução externa. A tentativa `v12-ingest-requalification-v1.json` permanece registrada:
ela recusou corretamente o hash antigo do relatório V-09; os artigos já passavam nessa tentativa.

## Próximos passos obrigatórios

1. Limitar o corpo HTTP antes do processamento multipart, incluindo uploads sem Content-Length,
   múltiplas partes e interrupção do cliente; medir arquivos grandes e o espaço temporário.
2. Medir o pipeline completo perto dos limites; ampliar entradas adversariais, inclusive
   atributos/textos grandes e arquivos não XML. Estes oito casos não esgotam entradas hostis.
3. Implementar quotas por empresa e reserva de disco com proteção contra concorrência;
   alertas, rotação do OpenClaw dedicado e política de retenção sem excluir backups históricos.
4. Requalificar o conjunto e executar backup/restore e implantação controlada antes de considerar
   os serviços existentes protegidos por estas novas alterações.

`release_ready=false`; o especialista humano continua previsto somente após a trilha automatizada.
