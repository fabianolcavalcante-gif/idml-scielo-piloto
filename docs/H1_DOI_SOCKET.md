# H1 — DOI no fluxo completo do Packtools

2026-09-30. Candidato isolado, sem implantação ativa ou aprovação de XML.

## Defeito encontrado e corrigido

A prova de regra DOI isolada não detectava um defeito do modelo nativo:
`DoiWithLang.authors` era um gerador. A regra de existência percorria os autores;
na regra de registro seguinte a lista já estava consumida, produzindo falso
resultado divergente mesmo com título/autores correspondentes no Crossref.

`ops/doi_model_compat.py` materializa os autores na construção do modelo usado
pelo validador DOI. A instalação é idempotente. Não altera XML, metadados,
limiar de similaridade, severidades ou resultado da comparação.

Contraprova Linux nativa, no mesmo XML sintético fixado por hash: regra isolada
passa; sequência original falha; sequência com compatibilidade passa; substituição
por metadados divergentes continua sendo rejeitada. Saída pública só de booleanos.

## Fluxo real pelo socket

Imagem candidata: `sha256:113366e7788c111faada2ef2cb6bc218c1c1b5061dca447fd462ce0216bc23ae`.
Cliente Linux UID/GID 10001, protocolo completo, broker e adaptador Packtools
com todas as regras. Contêiner sem rede e com limites anteriores preservados.

| Cenário sintético | Resultado |
|---|---|
| Metadados correspondentes | Adaptador concluído; sem achado de divergência DOI |
| Título/autores divergentes | Adaptador concluído; erro DOI mantido |
| Manifesto vencido | Rejeitado antes de executar o validador |
| Cliente desconectado | Broker encerra e limpa seus temporários |

Em todos os casos, socket removido e scratch vazio. Serviços existentes não
reiniciados nem substituídos; readiness de banco e Redis OK. Nenhum artigo real
ou snapshot privado transferido. Scripts/imagens e fixture sintética de laboratório
permanecem; temporários de cada execução foram removidos.

O socket é criado em `/run`, mas o trabalho fica em diretório privado no disco:
o tmpfs de `/run` não atende à reserva de 5 GiB do executor. Nenhum limite foi
reduzido. Broker agora registra apenas códigos de erro de uma lista fixa, sem
expor mensagens arbitrárias de exceção.

No cenário correspondente permanecem três bloqueios, três erros e seis avisos
da fixture sintética, alheios à comparação DOI. Concluir transporte não aprova XML.
Evidência: `benchmarks/qualification/reports/h1-doi-socket-v1.json`.

## Próxima sequência

Atualização posterior: integração SPS com vínculo ZIP/XML e seis contraprovas
qualificada na VPS; ver `H1_SPS_DOI_AUTHORITY.md`. O item 1 abaixo foi concluído
para pacote sintético plano com um XML; artigos reais continuam pendentes.

Regressão: 751 testes aprovados, três avisos; 88,02% de cobertura em
`src/idml_foundation` (scripts ops não incluídos nesse percentual). Cinquenta
testes focados, Ruff e gate operacional V10 aprovados.

1. Integrar SPSValidator: conferir hash do ZIP e do XML interno, rejeitar seleção
   ambígua e arquivos inseguros; aplicar a mesma compatibilidade de autores e
   repetir as contraprovas pelo adaptador de pacote.
2. Qualificar candidatos reais conforme a política de corpus e autoridades;
   suportar explicitamente múltiplos DOIs/traduções, sem reutilização indevida.
3. Continuar autoridades de seção/fascículo, ORCID, achados de conteúdo e XPM.
4. Somente após os gates, preparar implantação reversível e provas API/worker/UI.

SPS ainda não integrado nesta entrega: a divergência nativa descoberta foi
corrigida antes de propagar a integração. G-HOMOLOG permanece pendente.
