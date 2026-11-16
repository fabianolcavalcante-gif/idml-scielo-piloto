# Roteiro do revisor de XML

Abra o link de primeiro acesso do convite em até 24 horas e escolha sua senha. Depois use sua conta individual no [portal da VPS](https://143.95.214.8:8443/app).

## Enviar um IDML e acompanhar o processamento

1. No seletor de empresa, escolha **Homologação ESA — novos artigos**. Se já estava conectado quando recebeu o acesso, recarregue a página.
2. Abra **Uploads → Criar artigo**, informe um título e confirme. Em **Enviar arquivo**, escolha **IDML**, selecione o arquivo e clique em **Enviar**. Aguarde a confirmação. Repita para o PDF e cada figura, usando o tipo **PDF/JPG/PNG**.
3. Clique em **Atualizar revisões e pacote** para carregar os arquivos enviados. Em **Converter IDML**, selecione o IDML correto e clique em **Enfileirar conversão**. Em **Jobs**, clique em **Atualizar** para consultar o estado e em **Timeline** para acompanhar as etapas. Quando a conversão terminar, use **Baixar XML da conversão** para examinar o XML, inclusive se um empacotamento posterior ficar bloqueado.
4. Após a conversão, abra **Fontes públicas** e selecione o artigo. Para incluir as consultas externas previstas no perfil ESA, confira o prazo e clique em **Autorizar / renovar consultas**.
5. Volte a **Uploads**, selecione o artigo e clique em **Atualizar revisões e pacote**. Confira a revisão, selecione o PDF e as imagens correspondentes e clique em **Enfileirar pacote**. Acompanhe o novo processamento em **Jobs**.
6. Ao concluir, atualize a revisão em **Uploads**. Abra **Ver diagnóstico do pacote** e **Baixar ZIP de avaliação**. Confira o XML, os arquivos e os avisos. Para consultar a análise da automação ou solicitar a correção elegível, use **Avaliação do XML** para esse artigo e revisão.

O piloto foi qualificado para o perfil ESA. Um artigo novo pode apresentar pendências de metadados, vínculos, ativos ou validação. Inclua o título, a revisão e a mensagem do diagnóstico no apontamento.

## Comparar com os dois artigos de referência

Selecione a empresa **Qualificação ESA — catálogos** no topo da tela.

1. Abra **Uploads**. Em **Artigo**, selecione **ESA · Fontes conferidas · e20240086**. A tela abre a revisão atual e informa o nome do IDML usado na conversão.
2. Em **Revisão e pacote SciELO**, confira a revisão, o PDF e as cinco imagens associadas. Clique em **Baixar ZIP de avaliação**. Ao trocar de revisão, confira novamente os arquivos. O portal apresenta o último pacote concluído para a revisão escolhida.
3. Clique em **Ver diagnóstico do pacote**. Confira os resultados de Packtools, SPSvalidator e XPM. Leia os avisos e, quando houver aplicação da política de compatibilidade, examine também o resultado original em **Jobs → Resultado técnico salvo**.
4. Abra o XML do ZIP e compare-o com o PDF e as figuras fornecidas. Confira a identificação do artigo, autores e afiliações, datas, referências cruzadas, fórmulas, legendas e bibliografia. Verifique se cada chamada de figura leva à imagem correta.
5. Em **Avaliação do XML**, escolha o mesmo artigo e a revisão correspondente para consultar a decisão da automação. Uma abstenção indica que a automação encerrou a avaliação sem aplicar alterações.
6. Repita o percurso para **ESA · Fontes conferidas · e20240135**. Esse pacote contém sete imagens.

Para relatar uma divergência, informe o título do artigo, o número da revisão, o elemento ou trecho do XML, a página ou figura usada na conferência, o resultado obtido e o esperado. Se o achado for de um validador, inclua o nome da ferramenta e a mensagem que aparece no diagnóstico. Informe se a divergência impede a avaliação do restante do artigo. O responsável pela homologação reúne os apontamentos por artigo e revisão.

O ZIP é a cópia de avaliação. A decisão de aprovação editorial é registrada no fechamento da homologação.


## Correções e histórico

O artigo **ESA · Ensaio de correção e restauração · e20240086** conserva o ensaio controlado de uma afiliação. Em **Avaliação do XML**, a revisão inicial mostra o trecho anterior, a proposta aplicada e os relatórios correspondentes. A revisão corrigida mostra a recuperação e seus resultados. Cada validação oferece os downloads do XML e ZIP de avaliação.

Operadores autorizados podem usar **Reverter correção e revalidar** ou **Recuperar revisão corrigida e revalidar** na revisão atual. A operação exige confirmação e aparece em **Jobs**. Se algum validador ficar indisponível, a revisão vigente é preservada; consulte o diagnóstico e tente novamente após resolver a causa. Um pacote com erro XML efetivamente detectado fica bloqueado para aprovação, com histórico disponível para conferência.

Em **Fontes públicas**, revisores consultam a validade da autorização. Administradores e operadores habilitados podem autorizar ou renovar consultas por artigo. A permissão tem prazo, pertence à empresa e ao IDML selecionado e pode ser revogada. A autorização de consulta não substitui a decisão de edição por IA nem o aceite editorial.

A conta do proprietário administra **Fabiano Cavalcante** e é revisora em **Qualificação ESA — catálogos**. A definição de outro administrador do piloto permanece adiada. O ensaio não modifica esses papéis. As consultas dos exemplos receberam permissões delimitadas do proprietário, independentes das contas temporárias de teste.

## Avaliação com o OpenClaw

O operador gera primeiro o pacote da revisão em **Uploads**, vinculando o IDML, o PDF e as figuras. Em **Avaliação do XML**, escolhe o artigo e a revisão atual e clica em **Autorizar correção por IA**. A confirmação autoriza o envio ao OpenClaw do trecho de afiliação extraído do IDML para aquela revisão. A aplicação registra quem autorizou o pedido e qual pacote forneceu o PDF.

O resultado aparece no histórico da revisão de origem. **Correção aplicada ao rascunho** indica que os agentes sustentaram a proposta e que o pacote passou na revalidação. O operador pode abrir a revisão resultante e o especialista pode comparar o trecho e baixar os arquivos de avaliação. Uma abstenção indica que a revisão não tem uma afiliação elegível para a operação qualificada. Uma revisão já corrigida e posteriormente revertida oferece a recuperação da correção anterior.
