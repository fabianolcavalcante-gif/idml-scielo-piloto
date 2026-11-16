# H0 — baseline e bloqueadores da homologação funcional

Data: 2026-09-28. H0 concluído como inventário; G-HOMOLOG NÃO aprovado.

Atualização H1-01: integração de catálogos no job e paridade local dos dois artigos aprovadas;
ver `H1_JOB_ENRICHMENT.md`. As lacunas abaixo são o baseline anterior à implementação.

## Versão e escopo fixados para a trilha

- Periódico: Engenharia Sanitária e Ambiental; profile `esa-aop-1.0.0`, versão 1.0.0;
  JATS 1.3/SPS 1.10; Canonical Article 1.4.0. Não oferecer suporte genérico a outros templates.
- Referências: `esa-e20240086` e `esa-e20240135`, fontes privadas já autorizadas; são casos
  de regressão, não holdout independente. Não copiar fontes privadas em relatórios públicos.
- Imagem implantada observada: `idml-foundation:phase7-7c08-v1`, ID
  `sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86`.
- Baseline candidata: fingerprint
  `2d05685fc2f4f53865665312319a486af951551157af8e9c17fc68d94a9c1806`.
  Este é um baseline de fonte para desenvolvimento, NÃO uma imagem final congelada/aprovada.
  Gerar novo inventário e imagem ao concluir H1–H3.
- Escopo do fingerprint: fonte da aplicação, profiles, schemas, prompts, migrations, lockfile,
  pyproject e registro de validadores. Não mede env/segredos, vendor, imagens externas ou todo
  o conteúdo da VPS. O inventário não certifica autenticidade de software ou prontidão.
- IA: sem troca de modelos/prompts nesta etapa; flags não ativadas. Registro existente
  `agent-config-1.5`, alias `openai/gpt-5.4-mini`, prompts por domínio 1.3 e matemática 1.7.
  Isso registra configuração, não comprova chamadas reais na VH. H3 deve qualificar a assistência
  antes de anunciá-la como ativa; nenhum downgrade silencioso do escopo assistivo.
- Envelope inicial planejado: um operador e um processamento por vez, começando nos dois
  artigos conhecidos, sem ensaios de carga; reserva de 512 MiB RAM/5 GiB disco e acompanhamento
  de readiness na VPS. H2 deve confirmar/aplicar os limites; não são capacidade já aprovada.

## Comparação realizada

`ops/inventory_homologation.py` foi executado somente para leitura na API da VPS e localmente.
Encontrou 153 arquivos iguais, nove alterados, três novos e nenhum removido no escopo.
Novos: recepção HTTP, admissão de uploads e orçamento de armazenamento. Alterados: proteção
ZIP/XML, parser IDML, API, rotas de artefatos/jobs, persistência de artefatos, settings e worker.
Migrations, profiles, schemas e prompts comparados não mudaram.

Evidências: `benchmarks/qualification/reports/h0-deployed-inventory-v1.json` e
`h0-candidate-inventory-v1.json`. Nenhum deploy, restart, mudança de credencial ou chamada IA.

## Bloqueadores rastreáveis e próximos desenvolvimentos

| ID | Evidência do problema | Entrega/aceite | Responsável |
|---|---|---|---|
| H1-01 | `_process_idml_job` cria `DeterministicPipeline(settings=...)` sem os quatro catálogos opcionais; qualificação usa enriquecimento explícito | Integrar proveniência e fornecimento autorizado por artigo/empresa; repetir os dois artigos pelo job real e comparar XMLs, sem copiar gold nem embutir corpus privado no código | Desenvolvimento |
| H1-02 | Job `scielo.package` chama somente `OfflineJatsValidator`; validadores externos não são executados nesse fluxo | Orquestrar validações externas com estado/relatórios vinculados ao hash, indisponibilidade explícita e evidência autenticada | Desenvolvimento |
| H1-03 | Registro XPM: 4.0.096, `sps-1.9-only`, `worker-pending`; parser não é executor | Qualificar distribuição compatível e worker Windows isolado, executar pacote exato, anexar relatório e aplicar política; nunca simular sucesso | Desenvolvimento; usuário se instalação/coordenação externa for necessária |
| H1-04 | Aprovação editorial na API e política formal são componentes distintos | Comprovar que dupla aprovação não representa aprovação formal; estados de homologação/produção e downloads não podem sugerir sucesso externo inexistente | Desenvolvimento |
| H2-01 | Melhorias de ingestão/quota estão na candidata, não na imagem ativa | Backup NOVO consistente/restore, rollback, implantação limitada e smoke; preservar outros serviços | Desenvolvimento |
| H3-01 | UI possui fluxo técnico com IDs manuais de artigo, snapshots e ativos | Tornar associação/seleção compreensível e testar upload → conversão → revisão → pacote/download sem comandos ocultos | Desenvolvimento |
| H3-02 | Evidência multiagente de laboratório não comprova assistência na VH | Validar modo assistivo, custos/abstenções e modo sem IA no fluxo real, sem alterar autoridade de release | Desenvolvimento |
| H4-01 | Especialista/destinatário ainda não confirmado | Conta individual, roteiro, fontes autorizadas, formulário de defeitos e versão identificada | Desenvolvimento + usuário para identidade |

Ordem imediata: H1-01 (paridade laboratório/job), H1-02/H1-04 (validação integrada), H1-03
(execução formal XPM), depois H2/H3/H4. Investigar compatibilidade XPM em paralelo às integrações
locais, sem bloquear trabalho seguro por dependência externa. Não iniciar nova trilha de carga
prolongada ou expurgo de backups como condição genérica de homologação.

## XPM: fatos e limite do inventário

Há contrato de atestação, parser e política em `release/xpm.py`/`policy.py`; não foi localizada
chamada do executor nas rotas/worker. As buscas em `C:\IDML`, pastas superiores de `C:\` e
Program Files não localizaram instalação XPM: isso não prova ausência em todo o computador.
Java está no PATH; Python launcher lista 3.11/3.13, além do venv 3.12 da aplicação. Isso não
qualifica o runtime requerido pelo XPM. Relatórios `xpm.html` fornecidos com as amostras são
referências, não atestações de execução dos nossos pacotes candidatos.

A [documentação oficial do XPM](https://documentacao.scielo.org/books/scielo-pc-programs/page/xml-package-maker-xpm)
descreve execução via `python xml_package_maker.py <xml_package_folder>` e relatórios de saída.
Essa descrição não comprova compatibilidade SPS 1.10 da distribuição registrada. Não instalar
versão desconhecida nem portar/modificar XPM para contornar essa pendência; seguir ADR-002.

## O que já existe e o que não está aprovado

Já existem login/multiempresa, uploads, jobs, revisão, downloads autorizados, pipeline offline,
contratos assistivos, construtor de pacote e testes de laboratório. Isso não equivale ao fluxo
editorial completo homologado com os catálogos/validadores externos. Os dois XMLs qualificados
continuam evidência de laboratório; não prometer equivalência da UI até H1-01/H3.

Após essas correções: executar suíte completa, renovar gates vinculados ao fonte e evidências
externas sobre os novos hashes antes de G-HOMOLOG. V-12–V-15 completos, retenção histórica e
endurecimento de produção continuam no backlog, sem aprovação automática.
