# VH-02/07 — Compatibilidade DOI no executor e diagnóstico ORCID

Entrega delimitada de 2026-10-23; continuidade da seção 41, não uma nova fase.
Implementação candidata `vh1-xpm-runtime-20261023-v1` qualificada na mesma VPS,
sem ativação na API/worker. Mantidos XML, ZIP, XPM original e Release Policy.

## Implementado

- As duas regras DOI da ADR-019 agora recebem os bytes do relatório da execução
  atual e a resposta Crossref vinculada ao mesmo XML/ZIP, empresa e recurso.
  Exigem imagem/ferramenta qualificadas, perfil ESA 1.1, consulta de até 24 horas,
  DOI/ISSN/títulos/lista ordenada de autores correspondentes e ocorrência exata.
  Hash do código de comparação deriva da imagem imutável já qualificada; não é
  alegação enviada pelo cliente. Não há novo endpoint ou parâmetro HTTP.
- O resultado apresenta contagens brutas e avaliação derivada separadas. Nenhuma
  exceção muda `raw_passed`, aprovação, prontidão ou completude das consultas.
  Erros da avaliação complementar não apagam o relatório bruto válido.
- ORCID ganha classificação de nome público exato, incompleto, não exato,
  indisponível ou registro inválido, sem aproximação de nomes.
- Depois de conferir a lista ordenada de autores Crossref, o diagnóstico compara
  o ORCID depositado para cada autor com o XML. Identificador ausente é
  `not-deposited`, não contradição; identificador divergente/malformado é conflito;
  nomes repetidos são ambíguos. Editores não herdam vínculos de autores.
- Conflito de vínculo também bloqueia o pacote com contagens XPM zero. Vínculo
  correspondente não sobrepõe divergência de nome público nem autentica titularidade,
  inclusive se o depósito trouxer `authenticated-orcid=true`.
- Diagnóstico público contém códigos e hashes, não nomes, IDs, HTML ou respostas
  JSON de autoridade. Evidências completas ficam no armazenamento privado.

## Resultado nos artigos reais

Nova matriz nativa, não somente replay, em
`/opt/idml-platform/private/qualification/vh1-xpm-semantic-20261023T154139Z`.
Coleta nova Crossref/ORCID, relatórios atestados, sem consulta ao XML gold.

| Caso | XPM bruto (bloqueios/fatais/erros/avisos) | Derivado somente DOI | Autor–ORCID no Crossref |
|---|---|---|---|
| e20240086 | 3/1/4/2 | 3/1/2/2 | 3 vínculos exatos |
| e20240135 | 3/1/4/3 | 3/1/2/3 | 4 vínculos exatos |
| Título de periódico removido | 4/4/3/2 | Não aplicado | Não avaliado: Crossref não corresponde |
| XML truncado | 4/3/1/0 | Não aplicado | Sem coleta semântica |

No e135, dois nomes públicos estão incompletos e dois não correspondem exatamente.
Os quatro identificadores estão ligados aos respectivos autores no depósito do
artigo. Isso esclarece a origem da pendência, mas **não comprova titularidade nem
autoriza corrigir nome/identificador**. As quatro pendências permanecem explícitas.
No e86, os três nomes públicos também correspondem.

As contagens derivadas acima são apenas DOI. As antigas provas isoladas SPS/data
continuam válidas como histórico, mas não foram simuladas como execução integrada.
Portanto os resultados desta entrega não são comparáveis a um total já descontado
de todas as regras da ADR-019.

## Verificação

498 testes locais e os mesmos 498 Linux aprovados; 41 casos novos. Conjuntos
sobrepostos, zero falhas/erros/skip finais e um aviso de depreciação por execução.
Incluem troca de ORCIDs entre autores, homônimos, editor, dados ausentes,
identificador inválido, evidência adulterada/vencida/futura, escopo, perfil,
imagem/ferramenta, preservação de erros e impedimento de promoção.

Ruff global e mypy (132 módulos) aprovados. Não é nova suíte integral nem medição
global de cobertura. Regressão Linux executada após a matriz XPM, sem concorrência
entre as duas cargas na VPS. Quatro relatórios, 13 recibos e 19 arquivos selados
root/0600 verificados; entradas e arquivos do fornecedor intactos. Os 25 serviços
ativos ficaram idênticos; nenhuma rede de qualificação remanescente.

Provas: `benchmarks/qualification/reports/vh1-xpm-runtime-v1.json` e
`vh1-xpm-runtime-real-v1.json`. Código candidato e documentação enviados à VPS;
API/worker continuam em `vh09-heads-20261021-v1`. Sem migração, nova credencial,
porta, execução de IA ou ativação de correções automáticas.

## Próximo passo e critério de fechamento

1. Compor SPS/data com resultados **atuais** dos validadores independentes,
   preservando os hashes individuais originais dos relatórios. Não criar prova
   positiva a partir de flags, resultados históricos ou reescrita de hashes.
   Integrar também aplicabilidade Wayta qualificada; indisponibilidade não é sucesso.
2. Concluir decisão específica DOCTYPE/JATS e erro residual com fonte e
   contraprova; esta entrega não adiciona regra para dispensá-los. Manter tratamento
   explícito das pendências ORCID e das demais consultas obrigatórias.
3. Requalificar a composição e depois ativar a candidata com backup/rollback;
   seguir VH-09 (promoção/restauração), VH-10–13 (ciclo/web), VH-14–20 (operação/RC/E2E).

Sem ampliar a lista única VH1 ou declarar G-HOMOLOG/publicação antes desses gates.
