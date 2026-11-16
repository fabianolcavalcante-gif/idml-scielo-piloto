# H1 — Autoridade DOI no pacote SPS

2026-09-30. Integração candidata qualificada com dados sintéticos na VPS;
sem implantação ativa, sem aprovação do XML completo.

## Implementação

O manifesto confiável do SPS passa a conter dois vínculos independentes:
`package_sha256` identifica o ZIP completo e `candidate_sha256` identifica o
XML interno. O broker verifica ambos antes de criar o contêiner; o runtime
confere novamente antes de instalar a consulta DOI. Hashes de resposta Crossref,
prazo, DOI e ISSN continuam obrigatórios. O manifesto não vem do cliente.

`ops/doi_package_binding.py` seleciona exatamente um XML, sem extrair arquivos
no host. O perfil candidato exige pacote plano: recusa diretórios, caminhos
absolutos/relativos, duplicatas normalizadas, links, entradas especiais,
criptografia e métodos de compressão não suportados. Limites: ZIP 100 MiB,
1000 entradas, total declarado 500 MiB, entrada/XML 100 MiB e expansão máxima
100:1. São limites de engenharia, não requisitos atribuídos à SciELO.

O wrapper SPS preserva as compatibilidades anteriores de PDF e afiliação e
inclui a correção do gerador de autores DOI. Comparação nativa mantida; nenhuma
regra dispensada e nenhuma edição do XML. Configuração ausente mantém o modo
anterior; configuração presente e inválida é rejeitada, sem fallback de aprovação.

## Prova pelo socket real

Imagem SPS candidata:
`sha256:9549ba39d357854d51c3a1af3d11adc8a0583b83e12092928e808e76f706ad6d`.
Base fixada:
`sha256:372a13a1ad2dcbf94391559c20db4f63c1fbf3ab13453bf38e9e43ec1d34db77`.

Cliente UID/GID 10001, broker, manifesto somente leitura e adaptador SPS real,
sem rede e preservando limites de recursos. Seis cenários passaram:

- Metadados correspondentes: execução concluída, sem divergência DOI.
- Título/autores diferentes: erro DOI mantido.
- Dados vencidos: rejeitados.
- Cliente desconectado: limpeza concluída.
- Hash de ZIP errado: rejeitado.
- Hash de XML interno errado: rejeitado.

Também repetidos os quatro cenários anteriores do Packtools, todos aprovados.
Sockets removidos, scratch vazio e serviços existentes inalterados; banco e Redis
saudáveis. Nenhum artigo/snapshot real transferido. Fixtures sintéticas, código
e imagens de laboratório mantidos; temporários das execuções removidos.

O cenário correspondente ainda contém três bloqueios, três erros e seis avisos
da fixture sintética. Portanto, esta evidência confirma integração e rejeições,
não aprovação editorial, formal do pacote inteiro ou liberação ao especialista.
Relatório: `benchmarks/qualification/reports/h1-sps-doi-authority-v1.json`.

## Próximos passos

Atualização 2026-10-01: ambos os artigos reais revalidados localmente, com
quatro comparações DOI explicitamente positivas. Runtime local diferente da
imagem fixada; limites e sequência em `H1_REAL_DOI_LOCAL.md`.

Testes: 762 aprovados na regressão, três avisos e cobertura de 88,02% em
`src/idml_foundation` (não inclui scripts ops nesse percentual). Os 61 testes
focados, Ruff e gate operacional V10 passaram. As contraprovas Linux cobrem
os adaptadores nativos, além desses testes locais.

1. Requalificar os dois artigos reais usando coleta de autoridade em escopo
   autorizado, sem transportar catálogos privados indiscriminadamente. Registrar
   hashes, data, origem e resultado nativo por artigo; não presumir aprovação
   real a partir da prova sintética.
2. Tratar autoridades de seção/fascículo e ORCID, e separar bloqueios de consulta
   de divergências reais de conteúdo. Suporte a vários DOIs/traduções requer
   vínculo explícito por documento e ainda não está qualificado.
3. Fechar achados restantes/XPM; depois promoção reversível e provas API/worker/UI
   conforme H2/H3. G-HOMOLOG continua pendente.
