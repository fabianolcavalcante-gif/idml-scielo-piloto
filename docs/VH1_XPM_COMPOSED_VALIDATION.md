# VH-02/07 — Composição DOI, SPS/data e aplicabilidade Wayta

Implementação em 23/10/2026, retomada e requalificação em 26/10/2026.
Candidata `vh1-xpm-composed-20261023-v4`; não ativada na API/worker.
Continuidade da seção 42 da entrega VH1, sem nova fase ou ampliação da allowlist.

## Entrega

O serviço `assess_package` agora passa os dois resultados independentes da sua
invocação ao executor XPM. A composição usa os mesmos XML/ZIP, empresa, recurso,
perfil e relatório XPM. Exige ambos os validadores concluídos, imagens/versões
qualificadas, sem achados impeditivos e com hashes individuais dos relatórios.

`xpm-sps-runtime-evidence-2.0` acrescenta vínculo de composição reproduzível, sem
substituir os hashes individuais por um hash comum. O horário publicado é o da
composição, não uma renovação da data de coleta das fontes. Contrato histórico
1.0 preservado para as avaliações antigas; resultados históricos não são
apresentados como novas execuções. Evidência inválida impede SPS/data, conservando
o diagnóstico DOI e as contagens brutas. Warnings não são aceitos automaticamente.

Modo administrativo `xpm-online-composed-1.0`: o broker também verifica os hashes
da norma e da prova nativa Wayta já qualificadas, executa sonda HTTPS de serviço
em subprocesso com limite de 30 segundos e sela a observação privada. A aplicação
confere bytes/hash, escopo, relatório XPM e validade de 24 horas. O perfil restrito
de afiliações continua obrigatório. Timeout não é resposta válida, consulta de
artigo ou comprovação de identidade institucional. Falta de evidência mantém
Wayta indeterminado, sem apagar a composição SPS/data válida.

`config/validator-registry-vh1-composed.json` mantém as imagens modernas já
qualificadas e combina versões de rollback distintas aceitas pelo carregador.
O cadastro histórico de laboratório tinha a mesma revisão upstream nos canais
ativo e rollback; por isso não era carregável por esse serviço. Não se relaxou
a validação, nem se alteraram os cadastros históricos/ativos.

## Evidência real atual

As consultas de 23/10 foram preservadas como histórico e **não renovadas por
troca de timestamp**. Em 26/10 houve nova coleta Crossref, ORCID e cadastro editorial,
seis execuções nativas modernas e quatro execuções XPM. Resultados modernos passam
pelo executor scoped do broker; os recibos selados são ingeridos pelo cliente de
qualificação no mesmo lote. XPM usa o socket privado real. Isto não é E2E da UI
nem ativação da aplicação.

Diretórios privados:

- Modernos: `/var/lib/idml-vh1-qualification/composed-20261026-v1`.
- XPM: `/opt/idml-platform/private/qualification/vh1-xpm-composed-20261026T113457Z`.

| Caso | Bruto XPM: bloqueios/fatais/erros/avisos | Derivado DOI + SPS/data | Estado final |
|---|---|---|---|
| e20240086 | 3/1/4/2 | 0/1/1/2 | Bloqueado |
| e20240135 | 3/1/4/3 | 0/1/1/3 | Bloqueado |
| Título do periódico removido | 4/4/3/2 | Compatibilidade não aplicada | Bloqueado |
| XML truncado | 4/3/1/0 | Compatibilidade não aplicada | Bloqueado |

Seis ocorrências por artigo classificadas: duas DOI e quatro SPS/data. Wayta
auxiliar para ambos os perfis qualificados; a observação do serviço e a consulta
do artigo permanecem estados separados. Nos dois baselines, cada validador moderno
concluiu sem erros impeditivos e com cinco avisos. No XML truncado, o provisionamento
scoped é recusado antes dos modernos: dois resultados indisponíveis, não dois
sucessos nativos. O XPM ainda executa e registra os erros desse controle negativo.

Não houve alteração de XML, pacote, autoria, ORCID, fornecedor XPM ou DOCTYPE.
As quatro pendências de nome público do e135 permanecem explícitas, mesmo com os
vínculos depositados correspondentes. `raw_passed`, `required_queries_complete`,
`ready_for_scielo` e autorização de publicação continuam falsos.

## Testes e auditoria de fechamento

609 testes locais aprovados em 23/10 e os mesmos 609 Linux aprovados em 26/10,
incluindo 35 casos novos; conjuntos sobrepostos. Zero falhas/erros/skip finais.
Três avisos por execução: uma depreciação e dois avisos de serialização produzidos
por controles de evidência propositalmente inválida. Ruff global, mypy dos 132
módulos e formatação dos dez arquivos de código envolvidos aprovados. Não foi
repetida a suíte integral, medida nova cobertura global ou declarado CI global.

Auditoria de 26/10: quatro relatórios XPM, seis recibos modernos e 13 consultas
Crossref/ORCID conferidos; 22 arquivos XPM/consulta/sonda selados root/0600.
Os dois hashes de composição foram reproduzidos a partir dos recibos privados,
do escopo e do horário informado; hashes individuais não foram substituídos.
As três sondas Wayta terminaram em timeout, mantido como timeout. Nenhuma consulta
institucional de artigo foi declarada concluída. A auditoria usou mounts somente
leitura, sem rede, e permissão restrita de leitura para conferir os arquivos do
container XPM pertencentes ao UID 65534; não mudou permissões desses arquivos.

Os 25 serviços ativos permaneceram idênticos ao inventário de início de 26/10,
sem rede temporária remanescente; `/health/ready` e `/app` responderam HTTP 200.
Provas: `benchmarks/qualification/reports/vh1-xpm-composed-v1.json` e
`vh1-xpm-composed-real-v1.json`. JUnit, log Linux, auditoria e pós-checagem têm
hashes registrados. Código candidato tem 1.155 arquivos conferidos; documentação
de fechamento sincronizada separadamente, sem editar o diretório congelado.

## Segurança operacional e limites

O laboratório usa ancestralidade pertencente a root e diretório distinto por
validador. As primeiras tentativas incompletas foram preservadas: usuário do
container sem acesso, ancestralidade não confiável, colisão de staging e cadastro
de rollback incompatível. Não integram os resultados aprovados. As correções
respeitaram os controles existentes; nenhum limite da VPS foi reduzido.

As matrizes de 23/10 também foram concluídas; a repetição de 26/10 é a prova atual.
Nenhum pacote novo, credencial, porta, migração ou execução de IA. API/worker
permanecem `vh09-heads-20261021-v1`. Código candidato armazenado e testado na VPS;
ativação e G-HOMOLOG não concedidos.

## Próximo passo delimitado

Concluir a decisão específica sobre DOCTYPE/JATS e o erro residual XPM, com fonte
e contraprova, sem alterar dados corretos apenas para satisfazer a ferramenta legada.
Finalizar o tratamento das consultas/avisos/pendências ORCID para homologação.
Em seguida, requalificar e ativar o conjunto com backup/rollback; continuar os mesmos
VH-09 (promoção/restauração), VH-10–13 (ciclo/web) e VH-14–20 (operação/RC/E2E).
Não criar exceção de DTD por inferência desta entrega, nem declarar XML aprovado.

Atualização 27/10: diagnóstico técnico DOCTYPE/erro residual encerrado e PUBLIC ID
MathML3 corrigido; ver `VH1_DOCTYPE_JATS_DECISION.md`. A matriz desta página continua
vinculada aos hashes anteriores. A composição online ainda precisa ser executada
para os novos pacotes; este histórico não foi transferido como aprovação.

Atualização 28/10: a composição dos pacotes corrigidos foi executada e auditada
em laboratório separado, com consultas novas. Ver `VH1_MATHML3_COMPOSED_VALIDATION.md`.
Esta página e suas provas permanecem como registro da matriz anterior.
