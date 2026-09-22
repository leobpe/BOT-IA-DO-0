# Retorno da seleção pré-live do dia 30 com odd mínima 1,50

Pedido confirmado em 02/09/2026: retomar a forma de seleção do dia 30/08,
mas conservar odd mínima 1,50. Alteração exclusiva da pré-live.

## Referência recuperada

- Versão de origem: `seletor-pre-live-variedade-bet365-v7`.
- Linhagem original do modelo:
  `72acfa171c6c371b24dec54578cb8b38dbf6d023544d3ae4c11285758631e748`.
- Nas listas publicadas em 30/08: 21 bilhetes únicos, 16 greens e 5 reds,
  76,19%, retorno hipotético de +2,8358 unidades usando as odds registradas.
- Não houve entregas individuais confirmadas naquele dia. Esses números
  pertencem às listas, inclusive preliminares; não devem virar ROI de
  entradas oficiais confirmadas. Uma amostra de um dia não comprova
  superioridade futura.

## Perfil de retorno

Ativação: `PRELIVE_PERFIL_SELECAO=dia30_v7`, seguida de reinício validado.
Nova versão: `seletor-pre-live-retorno-dia30-odd150-v12`.

- Mesma fórmula contextual de histórico, casa/fora, temporada, confronto,
  classificação, previsão e jogadores da V7.
- Retoma elegibilidade por probabilidade/edge do modelo e qualidade.
- Consenso entre casas continua registrado para diagnóstico, sem os vetos
  e a prioridade de ranking acrescentados pela V8.
- Bilhetes ordenados por probabilidade do modelo, faixa preferencial,
  edge e qualidade. Retirado o corte relativo de score introduzido na V9.
- Simples, duplas e triplas continuam exigindo os critérios mínimos de cada
  tipo; múltiplas só entre partidas diferentes e ofertas da mesma casa.
- Qualidade de confirmação volta a 82 e exige escalação confirmada de todas
  as equipes. Não chama dados ausentes de confirmação. As restrições extras
  oficiais da V11 não se aplicam a esse perfil.
- Odd mínima final permanece 1,50 (não 1,45 da V7 original). Faixa
  preferencial até 1,60 e estendida até 1,70 com as exigências existentes.

## Correções preservadas

Pareamento e catálogo de odds atuais; somente mercados com cálculo e
liquidação implementados; não multiplicar pernas correlacionadas do mesmo
jogo; remover multigols dominado por time +0,5 na mesma casa quando este paga
igual ou mais; calendário de listas, não repetir jogos, revalidar sem
republicar listas e editar os resultados green/red. As regras de gols ao
vivo, cantos, Scanner e login PackBall não foram editadas.

## Verificação histórica

Recuperada a V7 em memória a partir dos registros de alterações desta
mesma tarefa, revertendo 11 alterações posteriores. Versão e hash original
acima conferiram. Sem escrever no banco ou em fontes históricas:

- A fórmula contextual do perfil de retorno coincidiu com a V7.
- 27 bilhetes históricos forneceram 44 ofertas para a comparação.
- Aplicando a mesma odd mínima 1,50 a ambos os seletores, os 10 bilhetes
  resultantes foram idênticos em ordem, seleções, odds e estados.

Esse teste usa apenas ofertas históricas disponíveis, não reconstitui todas
as oportunidades daquele dia e não estima lucro futuro.

## Reversão

Definir `PRELIVE_PERFIL_SELECAO=v11` e fazer reinício validado restaura o
seletor anterior. As chaves existentes `PRELIVE_POLITICA_V11_ATIVA` e
`PRELIVE_V11_MULTIPLAS_OFICIAIS_ATIVAS` não são alteradas por este retorno.
Uma configuração de perfil desconhecida é recusada. Não sobrescrever
bilhetes, resultados, agendas ou linhagens históricas ao mudar de perfil.

O perfil V11 mantém sua linhagem original; o retorno recebe linhagem nova,
pois a odd mínima e as correções preservadas diferem da V7 de agosto.

## Testes

- Suíte completa: 2.052 testes aprovados.
- Rechecagem do agendador, retorno e execução pré-live após acrescentar
  identificação do perfil ao estado do processo: 28 testes aprovados.
- Cobertura dos dois perfis, rollback/linhagem, mínimo 1,50, ordenação,
  consenso apenas diagnóstico no retorno, qualidade/histórico, confirmação
  real de escalações, múltiplas e revalidação sem reescrever identidade.
- Nenhum envio manual de sinais ou mensagens de teste ao Telegram.

## Aplicação

Perfil ativado no `.env` com odd mínima 1,50. Reinício validado, monitor e
supervisor estáveis. Conferência por hash confirmou que os arquivos de
HT, FT, motor ao vivo, filtro de chutes, política de cantos e normalizador
de odds ficaram idênticos aos anteriores a esta alteração.
