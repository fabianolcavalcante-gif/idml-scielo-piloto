# H1-02/H1-04 — resultado formal vinculado ao pacote

Data: 2026-09-28. Primeiro incremento implementado localmente; executores externos ainda
não conectados. H1-02/H1-04 permanecem EM ANDAMENTO, XPM pendente, G-HOMOLOG não liberado.

## Mudança implementada

O job `scielo.package` agora persiste `formal_validation` junto ao resultado. Esse registro
vincula SHA-256 do ZIP e do XML final (após resolução dos nomes dos ativos), os validadores
obrigatórios, versões/ferramentas selecionadas do registro e estado individual dos resultados.
O relatório fica fora do ZIP para não criar dependência circular entre hash e relatório.
Os bytes do pacote e seu manifesto não foram modificados por esta instrumentação.

A interface informa que pacote gerado/aprovação editorial não equivalem a validação formal
ou autorização de publicação. O resultado estruturado aparece na visualização já existente
do job; uma apresentação editorial mais amigável continua em H3.

| Estado | Significado nesta implementação |
|---|---|
| Job `succeeded` | Operação de geração/armazenamento terminou; não é aprovação formal |
| `validation-unavailable` | Registro/executor/evidência obrigatória ausente, inválida ou indisponível |
| `blocked` | Execução externa concluída com achados não aceitos; XPM pode continuar indisponível |
| `editorially_approved` | Dupla aprovação editorial, em fluxo separado; não modifica `formal_validation` |

Não existe caminho novo para `ready-for-scielo`. `complete`, `ready_for_scielo` e
`production_activation_authorized` ficam falsos enquanto XPM não estiver integrado.
Pacotes continuam sendo candidatos para avaliação; downloads existentes não são publicação.

## Limite de confiança

`services/package_validation.py` define a orquestração e a interface de execução confiável.
O executor recebe XML para Packtools e ZIP para SPSValidator, conforme o registro fixado.
Confere nome, versão, profile, contrato, ferramenta, hash dos bytes de entrada e presença
do hash de relatório em saídas concluídas. Exceções/timeout ou divergências não geram sucesso.
Só contagens, hashes e códigos genéricos entram no resumo; texto de artigos/diagnósticos
arbitrários não é copiado para o resultado ou logs.

A interface de executor é dependência interna do servidor, NÃO campo da API. Na aplicação
atual ela está desconectada: não chama subprocessos, Docker, provider ou serviço externo.
Os testes injetam executores sintéticos para provar contratos/estados, não execução oficial.
Essa implementação não autentica transporte remoto nem qualifica novo runtime de validador.

## Testes executados

Quinze testes focados aprovados: os três testes do fluxo V-10, ampliados para confirmar
vínculo pacote/resultado e preservação do estado formal após dupla aprovação, e 12 novos
casos de contrato, ausência de executor/registro, falhas, hashes, versões, profile e privacidade.
Mypy aprovado em 96 arquivos de fonte; Ruff e formatação aprovados.

Regressão completa concluída: **609 testes aprovados, três avisos, cobertura 87,80%** do
pacote da aplicação. O novo módulo de orquestração atingiu 100% das linhas nos testes;
isso não significa cobertura de um executor externo real. Evidências:
`tmp/h1-formal-tests.xml` e `tmp/h1-formal-coverage.json`.

Evidência operacional atualizada após repetição dos testes:
`benchmarks/qualification/reports/v10-operational-workflow-h1-formal-v1.json`.
Relatórios anteriores preservados, sem remoção dos controles de integridade de fonte.

## Próximo incremento obrigatório

Atualização de 2026-09-28: cliente/broker isolados implementados e smoke sintético
Linux executado; detalhes em `H1_VALIDATOR_TRANSPORT.md`. A lista abaixo permanece
como critérios de conclusão: transporte não implica qualificação dos artigos nem XPM.

1. Conectar executor isolado/autenticado de Packtools/SPSValidator, sem expor socket Docker
   ao worker web nem aceitar comandos/relatórios do usuário como autoridade. Limitar memória,
   CPU, tempo, saída e rede; registrar execução e relatório íntegro pelo hash exato do candidato.
2. Executar os dois artigos e seus pacotes reais nesse fluxo; avaliar erros/avisos e exceções
   estritamente vinculadas a evidências. Não substituir execução nova por replay histórico.
3. Completar vínculo entre solicitação editorial, snapshot, artefato e avaliação formal
   persistida; impedir promoção por hash arbitrário ou evidência antiga. A separação de estados
   comprovada aqui NÃO encerra essa autorização formal de release.
4. Integrar executor XPM qualificado e atestação conforme H1-03, antes de aprovar H1/G-HOMOLOG.
5. Renovar os demais gates vinculados ao fonte e prosseguir para implantação H2 e fluxo H3.

Não houve implantação na VPS, chamada de IA nem liberação para especialista/produção.
