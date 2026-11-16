# V-12.2 — Perfis volumétricos de armazenamento e conversão

Data: 2026-09-24. Ensaios aprovados para a candidata, **sem implantação nos serviços existentes**.
Esta etapa acrescentou testes e evidências; não alterou o código de produção nem seus limites.

## Matriz executada

| Perfil sintético | Resultado | Pico RSS do processo |
|---|---|---:|
| IDML armazenado com exatamente 16 MiB | Persistido, relido, convertido e XML salvo/verificado | 101,73 MiB |
| IDML armazenado com exatamente 100 MiB | Mesmo fluxo aprovado | 185,60 MiB |
| ZIP com exatamente 500 MiB descompactados | Mesmo fluxo aprovado; entrada de 12.218.500 bytes | 100,80 MiB |
| Dois trechos textuais de 7 MiB cada | XML de saída com 14.682.538 bytes, válido offline e persistido | 194,88 MiB |
| 10.000 arquivos existentes na empresa | Próxima gravação recusada com `artifact_quota_exceeded` | 78,18 MiB |
| Volume temporário de 64 MiB com 52 MiB ocupados e reserva de 16 MiB | Gravação recusada com `artifact_disk_reserve` | 77,94 MiB |

Nos perfis de conversão foram chamados os serviços reais de gravação de IDML, leitura com
verificação de hash, pipeline determinístico completo (parser, mapeamento, construção JATS e
validação offline), gravação do XML e leitura final para conferir os bytes. Metadados deste
ensaio usam SQLite isolado; PostgreSQL/API/worker/fila foram exercitados na etapa anterior.
Não houve HTTP, fila nem inferência de IA nesta matriz.

## Limites da conclusão

- Nos perfis 16/100/500 MiB, o volume adicional é um arquivo binário não referenciado pelo
  artigo; os XMLs resultantes têm 2.488 bytes. Isso mede transferência interna, CRC, hashing,
  persistência e conversão de um artigo pequeno acompanhado de payload grande — não um
  artigo de 500 MiB de conteúdo editorial. A descompressão é verificada em fluxo; não cria
  uma cópia de 500 MiB em memória/disco. O limite agregado de XML de 16 MiB continua vigente.
- O perfil textual cobre dois blocos extensos, não milhares de tabelas, fórmulas ou objetos.
  Não extrapolar seu resultado para toda combinação de texto, elementos e anexos.
- Os 10.000 arquivos são sintéticos, não cadastrados no banco: confirmam que órfãos contam na
  quota. Somam 138.890 bytes lógicos, mas ocupam cerca de 39 MiB em blocos do filesystem.
- A pressão de espaço ocorreu somente no tmpfs limitado do container, nunca preenchendo o
  disco da VPS. Não é um ensaio de esgotamento do filesystem de produção.
- RSS é memória do processo, não inclui toda a memória do container/volume temporário.
  O limite total de 256 MiB do container permaneceu ativo e não houve OOM em nenhum caso.
- Tempos do relatório incluem a geração dos dados sintéticos e a execução medida; não são
  SLA, latência de internet, desempenho sob concorrência nem limite homologado por artigo real.

## Isolamento e proteção da VPS

Laboratório: `/opt/idml-platform/qualification/v12-volume-v1`; um container por vez,
256 MiB, 0,25 CPU, sem swap adicional, rede desativada, imagem read-only, tmpfs de 64 MiB.
O código-fonte candidato completo, perfis e schemas foram montados em modo somente leitura.
A imagem fixa fornece o runtime e os validadores offline existentes.

Entrada e artefatos usam uma pasta temporária exclusiva no disco, não tmpfs, para que duas
cópias de um IDML de 100 MiB não consumam artificialmente toda a RAM do container. O maior
uso alocado observado nessa pasta foi 210.067.456 bytes, abaixo do orçamento de 256 MiB.
O watchdog exige espaço inicial para esse orçamento além da reserva de 5 GiB do host.

Foram 71 amostras: memória disponível mínima 710.103.040 bytes e readiness máximo 67,904 ms.
Reserva de 512 MiB de RAM preservada, 25 serviços existentes inalterados. Os seis containers
e todas as pastas temporárias sintéticas foram removidos após validação do caminho exato.
O sistema existente permaneceu pronto, com banco/Redis saudáveis. Sem chaves, corpus privado,
inferências pagas, upgrade de hardware ou reinício de serviços.

## Evidências e controles

- `benchmarks/qualification/reports/v12-volume-observation-v1.json`
- `benchmarks/qualification/reports/v12-volume-gate-v1.json`
- `ops/probe_phase7_v12_volume.py` e `ops/observe_phase7_v12_volume.py`
- `tests/test_phase7_v12_volume.py`: tamanho exato, ratio permitido e conteúdo textual realmente convertido.
- `tests/test_phase7_v12_volume_gate.py`: regressões de volume, OOM, quotas, pressão de disco,
  preservação de serviços, limpeza e recusa de evidência vinculada a código desatualizado.

O novo gate na CI exige as seis provas e os hashes de todo o fonte candidato, perfis, schemas
e scripts relevantes. A CI verifica a evidência; não executa carga remota automaticamente.

Regressão local: **546 testes aprovados, três avisos, cobertura 87,72%**. Foram adicionados
quatro testes de geração/fluxo e 12 testes do gate. Ruff e formatação aprovados.
Evidências: `tmp/phase7-v12-volume-tests.xml` e `tmp/phase7-v12-volume-coverage.json`.

Requalificação consolidada aprovada em `v12-volume-requalification-v1.json`: 18 gates e
controles dos dois artigos passaram; hashes XML preservados, zero bloqueios semânticos
detectados. Os validadores externos permanecem com replay vinculado por hash, sem nova
execução externa. Homologação humana e demais bloqueios de liberação continuam pelo plano.

## Sequência planejada

1. Auditoria de armazenamento e plano de retenção testados em modo somente leitura em
   2026-09-25; ver `PHASE_7_V12_OPERATIONS.md`. Classificação de backups e ativação pendentes.
2. Requalificação integrada, backup/restore e implantação controlada com rollback, conforme
   o plano. Conferir uso/quota existentes antes de ativar os novos limites.
3. V-12.3: janela prolongada, saturação e perfis reais/combinados, incluindo diversidade de
   objetos e orçamento integrado de IA. Os seis perfis sintéticos não substituem essa etapa.

`v12_2_complete=false`, `production_capacity_qualified=false`, `release_ready=false`.
