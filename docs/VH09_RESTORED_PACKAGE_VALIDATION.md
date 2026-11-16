# VH-09 — Pacote restaurado reconstruído e revalidado

Estado em 29/10/2026: serviço interno qualificado, ainda não conectado ao worker
ou à interface web. Fecha a função restante de reconstrução/revalidação do
VH-09; o aceite integrado depende dos VH-10/14/18 já planejados.

## Entrega

`restore_and_revalidate_package` combina restauração conservadora e validação
na mesma transação. `revalidate_restored_package` executa nova validação da
versão já restaurada. Exigem empresa, evento de restauração e versão esperada.

O XML é reconstruído do snapshot restaurado, sem enriquecimento ou correção
adicional. IDML, PDF e imagens são conferidos por hash e estado de verificação.
Imagens precisam corresponder exatamente aos vínculos, sem associação por
semelhança/numeração. A montagem permite somente a renomeação prevista dos
arquivos, preservando conteúdo, estrutura e bytes dos ativos. Insumos, versão
e estado humano são conferidos novamente depois dos validadores.

Validação offline antecede os executores externos; falha offline não dispara
Packtools/SPS/XPM. Relatórios novos são vinculados ao XML/ZIP reconstruído,
snapshot, evento e perfil. Avisos ficam pendentes e erros/consultas impeditivas
bloqueiam a decisão técnica. Nenhuma aprovação anterior é herdada.

O mesmo pedido devolve histórico mesmo após a versão atual mudar, sem nova
restauração ou execução. Um novo pedido exige que o evento ainda seja atual e
executa validação nova. XML inválido reconstruível fica registrado como bloqueado.
Falha de integridade/montagem ou mudança de estado desfaz a operação combinada.
Rollback externo também desfaz evento e registro; possíveis arquivos órfãos por
hash seguem o tratamento existente, sem referência aprovada.

Tabela privada `restored_package_validations`: unicidade do pedido por empresa,
vínculos e proteção contra alteração/exclusão via ORM/SQL. Migração aditiva
`d1f203142536`, sem alteração de snapshots ou resultados retroativos. O leitor
confere recibo, relatórios e artefatos; histórico não é autorização vigente.

## Verificação e VPS

- 34 testes novos; 421 testes direcionados locais e os mesmos 421 Linux aprovados.
- PostgreSQL descartável: migração sobre dados existentes, ausência de resultados
  retroativos, concorrência, conflito, proteção humana, rollback e dois controles
  SQL de imutabilidade. Downgrade/upgrade preservou as versões de trabalho;
  isso não autoriza excluir histórico na aplicação.
- Alterações de IDML/PDF/imagem, versão e revisão durante execução recusadas;
  empresa incorreta, adulteração, limite e relógio inválidos também recusados.
- Ruff, mypy (140 módulos) e diff-check aprovados. Sem nova cobertura, suíte
  integral, chamadas IA ou novas execuções externas sobre artigos reais.

Os validadores externos dos testes transacionais são sintéticos. A DTD real foi
exercitada no controle negativo. Isso não aprova artigos reais nem indexação.
Uma fixture local inicialmente sem `field_path` foi corrigida antes da execução
final. Reserva de 1 MiB usada só no laboratório com tmpfs de 512 MiB; configuração
ativa preservada.

Código/migração qualificados armazenados na VPS. Aplicação continua em
`vh1-structural-20261028-v1`, banco `c0e1f2031425`; a migração nova foi aplicada
somente no banco descartável. 25 serviços e contagens ativas preservados; ready
HTTP 200. Prova: `benchmarks/qualification/reports/vh09-restored-package-v1.json`.
Ensaio repetível: `ops/qualify_vh09_restored_postgres.py`. Laboratório:
`/var/lib/idml-vh1-qualification/restored-20261029-v1`.

## Próximo passo

Integrar promoção/restauração/revalidação ao worker e aos executores supervisionados
(VH-10/14), com implantação da migração/código e teste de ciclo completo. Depois
concluir fluxo web e ensaios finais existentes. Não criar nova fase nem reabrir
esses serviços internos; G-HOMOLOG e publicação dependem do fluxo integrado.
