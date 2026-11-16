# Pipeline determinístico da Fase 3

## Contrato de execução

```text
IDML não confiável
  -> inspeção ZIP e XML sem rede/entidades
  -> Raw Article 1.1.0
  -> Journal Profile ESA 1.0.0
  -> Canonical Article 1.0.0
  -> builder JATS 1.3
  -> DTD offline + regras SPS baseline
  -> ValidationReport 1.0.0
```

O pipeline não recebe PDF nem XML gold. Esses artefatos são admitidos somente
por avaliadores do corpus, fora do caminho de geração. OpenClaw, Swarm e IA não
participam desta fase.

## Parser e ordem de leitura

O parser valida o pacote integralmente em memória antes de ler XML. DesignMap,
Stories, Styles e Spreads são convertidos para IDs UUIDv5 estáveis e evidência
com SHA-256/localizador. Parágrafos preservam os runs e estilos; tabelas
preservam células e spans.

TextFrames são associados a páginas e Stories. O algoritmo valida início único,
links recíprocos, ciclos e componentes desconectados. A posição do primeiro
frame ordena Stories com frame; `StoryList` é fallback explícito para Stories
sem frame. Toda exceção vira `ReadingOrderIssue`.

URIs externas do InDesign nunca são persistidas. Somente o basename decodificado
e saneado, media type e evidência do elemento IDML entram no Raw.

## Perfil ESA

`profiles/esa-aop-1.0.json` congela identidade do periódico, idiomas, categoria
e prefixos dos estilos. O texto corrompido por encoding no nome de estilo não é
usado para decidir a função; prevalece o prefixo numérico do template. O nome
original continua preservado para auditoria.

Ausências permanecem `missing`. Estilos, assets e relações não solucionados
permanecem no Raw e geram `review_reasons`. O XML válido produzido na Fase 3 não
é, por isso, um pacote liberável.

## Builder e validação

O builder cria a árvore XML com lxml e serialização determinística. `IdRegistry`
recusa IDs duplicados, colisões após normalização e RIDs órfãos.

A DTD oficial JATS Publishing 1.3 MathML3 está fixada em `vendor/jats/1.3`.
`SOURCE.json` registra URL, hash do ZIP e hash de cada arquivo. A validação usa
somente esse diretório allowlisted e desativa rede. O relatório normaliza:

- XML não well-formed;
- erros da DTD JATS;
- versão, publisher-id e título obrigatórios;
- IDs duplicados e RIDs órfãos;
- referências de asset externas, com diretório ou ausentes do modelo.

## Limites deliberados

- correspondência, datas editoriais, equações, notas e relações completas entre
  captions/assets ainda exigem regras e métricas da Fase 4;
- os 20 assets do IDML ESA são links externos e precisam ser resolvidos no
  Package Builder;
- as quatro tabelas IDML versus três tabelas gold continuam como divergência
  classificada, não como correção implícita;
- Packtools, XPM e política de release pertencem à Fase 4;
- o resultado atual permanece `NEEDS_REVIEW` e nunca `READY_FOR_SCIELO`.

