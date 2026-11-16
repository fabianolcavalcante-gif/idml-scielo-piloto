# H1 — Correção candidata da resolução de PDF

Atualizado em 2026-09-30. Implementada e qualificada em imagem isolada na VPS;
não ativada na aplicação nem no registro de validadores atual.

## Alteração

`ops/sps_rendition_compat.py` fornece uma visão do artigo que resolve renditions
pelo basename real do XML, como no código mais recente já inspecionado localmente,
em vez do nome de pacote/PID recalculado pelo runtime antigo. O PDF principal usa
o mesmo basename; traduções usam sufixo de idioma. Não modifica XML, ZIP nem objeto
original e delega outros campos ao objeto do validador.

O helper `validate_package` pode alimentar o mesmo `validate_sps_xml_with_pre`,
preservando linhas, exceções e artigos. Ainda não é chamado pelo adaptador ativo;
deve entrar somente em nova imagem de qualificação, nunca via troca silenciosa
da imagem/registro atual. A execução completa desse helper foi comprovada na
imagem de qualificação abaixo; promoção para aplicação permanece pendente.

Nomes ambíguos, membros duplicados ignorando caixa, basename inseguro e idioma de
tradução indefinido são recusados. PDF de tradução ausente continua ausente mesmo
havendo PDF principal. Nenhuma severidade é diminuída nem exceção ignorada.
Presença por nome não comprova conteúdo visual correto ou conformidade universal
de nomes: regras de entrega continuam sendo verificadas separadamente.

## Prova local

No runtime local instalado, `probe_h1_rendition_compat.py` confirmou:

| Pacote | Ausentes pela lógica antiga | Ausentes pela visão candidata |
|---|---:|---:|
| e20240086 corrigido | 1 | 0 |
| e20240135 | 1 | 0 |

Hashes dos ZIPs inalterados. Evidência: `h1-rendition-compat-v1.json` em
`benchmarks/qualification/reports`. Escopo: apenas busca de renditions, sem executar
demais regras/consultas nem declarar aprovação formal. Quinze testes sintéticos
cobrem o comportamento positivo e a preservação das falhas.

## Histórico de capacidade (2026-09-29)

Novo preflight VPS: MemAvailable 776.568 KiB, aproximadamente 758 MiB, abaixo
da reserva inicial de 768 MiB, sem contar cliente/validador. Banco e Redis OK.
Não houve transferência privada, execução pesada, redução de limites ou parada
de serviços neste incremento. A indisponibilidade repetiu a observação anterior.

Para qualificar a candidata corrigida e esta compatibilidade, é necessário ter
margem estável: janela acordada para reduzir carga concorrente ou capacidade
adicional. Não encerrar outros projetos por inferência. Sem isso, seguir apenas
testes locais não substitui a prova Linux do fluxo e não libera G-HOMOLOG.

## Qualificação Linux (2026-09-30)

Reserva disponível nesta rodada: 1.078.392 KiB, sem redução dos limites.
Imagem candidata `idml-spsvalidator:h1-rendition-compat-v1`:
`sha256:3d3f136c650f4b83f9836b77a378b4fd3304fe30c9c2effa0aa1a06dd1f4de07`.
Base conferida: imagem de sanitizer `48b91db1bc1a…`; build sem download de
dependências. Dockerfile dedicado mantém o caminho fixo aceito pelo broker e
preserva o adaptador original em módulo separado. Registro apenas de laboratório:
`benchmarks/qualification/contracts/h1-rendition-compat-registry.json`.

| Artigo | Packtools | SPSValidator | Críticos / erros / avisos (cada ferramenta) |
|---|---|---|---|
| e20240086 corrigido | completed, reprovado | completed, reprovado | 28 / 4 / 12 |
| e20240135 | completed, reprovado | completed, reprovado | 10 / 4 / 8 |

O e20240086 agora conclui sem `validator-exception-or-invalid-output`. Seu XML
inclui também a correção anterior de ano/volume/licença: não atribuir toda mudança
de contagens ao adaptador PDF. No e20240135 o ZIP não mudou; o SPSValidator passou
de 5 para 4 erros, sem a regra Renditions. Não houve supressão de severidade.

Contraprova no runtime nativo com o inventário de PDFs ocultado (sem modificar ZIP):
1 artigo, 1 erro Renditions, 0 exceções. É teste negativo da resolução/inventário,
não uma prova de integridade de um ZIP adulterado nem de traduções reais.
Provas: `benchmarks/qualification/reports/h1-rendition-linux-v1.json`.

Quatro execuções pelo broker concluídas; dois artigos ainda reprovados.
Serviços existentes não reiniciados; scratch e sockets limpos. Quatro cópias
privadas remotas removidas, originais locais preservados. Banco e Redis OK;
MemAvailable final 1.041.436 KiB. Nenhuma imagem/registro da aplicação promovido.

## Próximo incremento

1. Classificar achados remanescentes por regra e evidência: metadados/afiliações,
   histórico, identificadores, referências, fórmulas e seção editorial.
2. Separar consultas indisponíveis sem rede de defeitos XML e incompatibilidades
   demonstradas. Nenhuma dispensa automática nem dado inventado.
3. Corrigir defeitos comprovados com regressão positiva/negativa; repetir os
   mesmos candidatos versionados. Integrar XPM e depois promover em H2/H3 com
   rollback e prova do fluxo real API/worker/UI.

PDF resolvido não significa XML aprovado nem G-HOMOLOG liberado.

## Regressão deste incremento

680 testes aprovados, 3 avisos, cobertura 87,86% do pacote da aplicação.
Artefatos: `tmp/h1-rendition-linux-tests.xml` e
`tmp/h1-rendition-linux-coverage.json`. A cobertura não mede conformidade SciELO
nem inclui os scripts `ops` nesse percentual. Testes de compatibilidade cobrem
agregação nativa, preservação de exceções e rejeição de pacote sem artigos.
Recorte de compatibilidade/triagem: 28 testes aprovados sem aferição global de
cobertura; Ruff aprovado nos cinco arquivos Python deste incremento.
