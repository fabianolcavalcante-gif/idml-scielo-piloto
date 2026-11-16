# ADR-017 — Escopo fechado e execução por entregas até VH1

- Data: 2026-10-01.
- Status: consolidação do pedido do usuário de definir término e executar até entrega.
- Complementa ADR-015/016, sem dispensar validações ou autorizar produção.

## Decisão

Adotar `HOMOLOGATION_VH1_DELIVERY.md` como fila única, com vinte itens em seis
lotes e critérios de pronto explícitos. Planos e relatórios anteriores são
especificações/evidências históricas; seus próximos passos não abrem filas novas.

Congelar VH1 no piloto ESA e automação restrita definidos; separar prontidão
de homologação de prontidão geral de produção. Após G-HOMOLOG, entregar e
aguardar avaliação; melhorias fora do escopo vão para H5/backlog posterior.

Antecipar XPM e permissões/fontes ao lote 1. Dependência externa insolúvel deve
gerar pergunta concreta ao responsável, nunca ensaios repetidos sem avanço.
Não há dispensa implícita de XPM, privacidade, segurança ou aceite humano.

## Consequências

Checkpoint reporta IDs concluídos e evidências, não quantidade de relatórios.
Testes focados por mudança e completos por integração/RC; repetir provas só
quando há mudança relevante ou contraprova ainda faltante. Nenhuma evidência
antiga passa automaticamente a aprovar uma nova versão.

Operações IA ficam nas famílias/campos enumerados de VH-08; a ampliação para
decisões editoriais ou científicas é outro escopo. Sem ativação por simples flag.
Identidade do especialista é necessária para entregar acesso, não para continuar
o desenvolvimento técnico. Estimativas dependem da resolução dos bloqueios iniciais.
