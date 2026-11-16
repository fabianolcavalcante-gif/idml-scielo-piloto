# Compatibilidade residual JATS/Style Checker — 28/10/2026

O VH-02/07 agora possui duas regras determinísticas integradas ao compositor de
compatibilidade. Elas classificam limitações exatas do XPM 4.0.096; não corrigem
o XML, não alteram relatórios originais e não aprovam publicação.

## Regras e pré-condições

- `xpm-jats13-legacy-dtd-1.0`: um fatal somente quando o bloco nativo completo
  contém exclusivamente o PUBLIC ID MathML3 1.3 desconhecido, a exigência legada
  de `dtd-version=1.1` e as rejeições de `coi-statement` correspondentes às notas
  existentes no XML. Nenhuma mensagem adicional é aceita.
- `xpm-sps110-style-unavailable-1.0`: um erro somente para a mensagem exata de
  SPS 1.10 não suportado pelo Style Checker 2.4.2, no bloco estrutural esperado.

As duas regras são atômicas e específicas ao perfil ESA 1.1. Exigem o mesmo
pacote/XML/relatório/empresa/recurso, atestado e imagem já qualificados, consulta
Crossref consistente e dois recibos modernos distintos, atuais e sem erros.
O XML é novamente validado localmente pela DTD JATS 1.3 MathML3 e pelas regras
obrigatórias, com os nomes de arquivos do ZIP. Esta checagem é necessária:
os modernos isolados não detectaram o título de periódico ausente no controle
nativo. XML inválido nunca recebe a exceção, mesmo com recibos modernos limpos.

O parser verifica o identificador do bloco e o nome do XML nas duas mensagens.
Texto do artigo reproduzido no relatório não é usado como diagnóstico. Blocos
duplicados, marcação inesperada, mensagens desconhecidas, versão diferente ou
hash/escopo divergente recusam a regra. Coordenadas são inteiros positivos:
o XPM formata sua cópia privada antes da validação; suas linhas não correspondem
às linhas do arquivo submetido, que permanece intacto.

Esta é uma decisão técnica interna autorizada pela ADR-019, não uma dispensa
oficial SciELO. O aceite editorial do DOCTYPE de entrega continua separado.

## Evidência e resultado

Reprodução na VPS dos relatórios nativos selados da composição de 28/10,
usando explicitamente o instante original. Não foram renovadas consultas,
credenciais, autorizações ou datas dos recibos, nem alegadas novas execuções
dos validadores. O código corrente refez a validação local dos dois controles
nativos negativos. Erros adicionais inseridos apenas em cópias de laboratório
dos dois relatórios impediram a nova classificação.

| Artigo | XPM bruto B/F/E/A | Derivado antes | Derivado com as duas regras |
|---|---|---|---|
| e20240086 | 3/1/4/2 | 0/1/1/2 | 0/0/0/2 |
| e20240135 | 3/1/4/3 | 0/1/1/3 | 0/0/0/3 |

B/F/E/A: bloqueios, fatais, erros e avisos. O resultado bruto permanece falho.
Cada artigo passa a ter oito ocorrências classificadas pelas regras combinadas.
O compositor retorna `technical_errors_resolved=true` e
`homologation_disposition=review-pending` para esses dois casos. Isso significa
que os erros técnicos XPM foram explicados pelas regras qualificadas; não é
aprovação do artigo, dos avisos, das identidades ou do sistema inteiro.

`homologation_ready` e `release_approved` permanecem falsos. O serviço de
validação formal e a política de publicação não foram relaxados. Na ausência
das pré-condições, as regras anteriores são preservadas e a parte estrutural
retorna indisponível; erros remanescentes mantêm `technical-validation-pending`.

Evidência pública sem conteúdo dos artigos:
`benchmarks/qualification/reports/vh1-structural-native-replay-v1.json`,
SHA-256 `b597f1f154ffb94fb8ab483344bb502c1451a81ee93589ebd5b5430edbdef503`.
O vínculo de sucessão dos fontes aceita apenas esse código exato e recusa
alterações nas dependências ou na prova. As qualificações históricas permanecem
preservadas, sem substituir seus resultados por uma execução supostamente atual.

## Pendências e próximo passo

Validação do incremento: 405 testes locais e os mesmos 405 em Linux na VPS,
sem falhas/erros/skip; incluem 32 novos testes da regra e 17 da sucessão dos
fontes. V-10/V-11 requalificados, Ruff global e mypy em 135 módulos aprovados.
Não houve nova medição de cobertura global, suíte completa ou E2E em navegador.
Candidata `vh1-structural-20261028-v1` armazenada na VPS, com 1.206 arquivos
conferidos; os 25 serviços permaneceram iguais e ready/app retornaram HTTP 200.
A versão ativa continua `vh09-heads-20261021-v1`; nenhuma IA foi invocada.


Permanecem cinco avisos por ferramenta moderna/artigo, dois/três avisos XPM,
quatro pendências de nome público ORCID no segundo artigo e a verificação
obrigatória das afiliações. Timeout Wayta não comprova identidade institucional.
Nenhuma dessas pendências foi aceita automaticamente.

Próximo na fila existente: ativação qualificada da candidata acumulada e ligação
do resultado de compatibilidade à promoção formal/revalidação restaurada do
VH-09, preservando a separação entre revisão para homologação e publicação.
Depois executar ciclo/worker, fluxo web, operação e entrega previstos em
VH-10–20. Não abrir nova fase nem repetir a pesquisa de DOCTYPE encerrada.

Atualização de 29/10: a candidata foi ativada na API/worker, com backup,
restauração e rollback testados. Ver `VH1_STRUCTURAL_DEPLOYMENT.md`. A prova
acima continua sendo a qualificação histórica da regra; ativação não concede
aprovação editorial, conecta executores automaticamente ou encerra o VH-09.
