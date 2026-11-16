# Protocolo de baseline humano — Gate G6

Este protocolo usa um corpus editorial separado do desenvolvimento. O piloto sintético v1 serve
somente para provar segurança, schema e execução; não aprova o gate.

## Amostra mínima

- 30 itens por domínio ativo, distribuídos entre tipos de artigo e dificuldades;
- `math_notes` somente se incluído no piloto;
- dois revisores independentes, cegos à resposta da IA;
- terceiro revisor resolve discordâncias;
- nenhum caso usado para ajustar prompt/modelo entra no holdout final.

## Procedimento

1. Congelar IDs/hashes do corpus, prompt, schema, agente, modelo e configuração.
2. Registrar estado inicial, evidências autorizadas e patch editorial gold.
3. Medir tempo e número de ações do revisor sem sugestão de IA.
4. Em sessão separada e ordem randomizada, medir a mesma tarefa com sugestão assistiva.
5. Validar ambos os patches pelo mesmo pipeline determinístico.
6. Registrar aceitação, correções, falso positivo, falso negativo e incidente de segurança.
7. Manter avaliadores sem acesso à partição de holdout durante ajustes.

## Métricas e limiares propostos

- exact patch accuracy e evidence compliance por domínio;
- redução mediana de pelo menos 15% no tempo humano, com intervalo reportado;
- aumento de erro crítico permitido: zero;
- injection resistance, schema pass e isolamento: 100%;
- nenhum patch automático e nenhuma autoridade de release;
- custo observado por artigo menor ou igual ao orçamento configurado;
- latência e indisponibilidade não podem interromper o fluxo sem IA.

O responsável editorial deve aprovar os limiares antes da coleta. Resultados sintéticos ou de um
único revisor não substituem esse aceite.
