# Mapeamento do novo site para os métodos do bot

Registro iniciado em 03/09/2026. Este documento serve para reaproveitar as
opções do novo site na criação dos filtros HT, FT, próximo gol e escanteios.
Ele não altera as regras nem o funcionamento do bot PackBall atual.

## Opções já identificadas

| Novo site | Significado no bot atual | Uso |
|---|---|---|
| Gols | Gols no placar | Obrigatório para selecionar o placar |
| Escanteios | Escanteios acumulados | Métodos de cantos |
| Finalizações Totais | Chutes totais | Atividade ofensiva |
| Finalizações no Gol | Chutes no gol | Qualidade da atividade ofensiva |
| Finalizações para Fora | Chutes para fora | Apoio; não aprova sozinho |
| Posse de Bola | Posse percentual | Apenas contexto; não aprova sozinho |
| Ataques | Ataques acumulados | Apoio de volume ofensivo |
| Ataques Perigosos | Ataques perigosos acumulados | Apoio mais relevante que ataques comuns |
| Pressão | Índice de pressão | Confirma intensidade; validar primeiro a escala do site |
| ATPM (Ataques Perigosos por Minuto) | Ritmo de ataques perigosos | Útil para comparar intensidade entre jogos e minutos diferentes |
| CG (Chance de Gol) | Indicador proprietário de chance de gol | Útil como confirmação, mas exige validar escala e significado |
| Cartões Amarelos | Amarelos acumulados | Contexto de intensidade e base para mercados de cartões |
| Cartões Vermelhos | Vermelhos acumulados | Obriga reanálise do comportamento; não indica gol sozinho |
| Faltas | Faltas acumuladas | Apoio para cartões e bolas paradas; não aprova gol sozinho |
| Impedimentos | Impedimentos acumulados | Apoio de profundidade ofensiva; não aprova sozinho |
| Soma das equipes (Total) | Soma mandante + visitante | Total da partida |

## Seletor Equipe

Esse menu define a quem a estatística escolhida pertence:

- Soma das equipes (Total): soma os dois lados. Usar para gols totais, chutes
  totais, chutes no gol e escanteios da partida.
- Casa: somente o mandante.
- Fora: somente o visitante.
- Favorito: time definido como favorito pelas odds pré-jogo.
- Azarão: time definido como azarão pelas odds pré-jogo.
- Qualquer equipe: a condição é satisfeita se pelo menos uma das equipes atingir
  o valor. Usar para confirmar que existe um lado pressionando.
- Diferença entre equipes: compara a distância entre os valores dos dois times;
  confirmar depois se o site usa diferença absoluta ou orientada.
- Favorito jogando em Casa: favorito identificado que também é o mandante.
- Favorito jogando Fora: favorito identificado que também é o visitante.
- Azarão jogando em Casa: azarão identificado que também é o mandante.
- Azarão jogando Fora: azarão identificado que também é o visitante.
- Time vencendo: aplica a estatística ao lado que estiver à frente no placar.
- Time perdendo: aplica a estatística ao lado que estiver atrás no placar; útil
  para medir reação ofensiva em métodos FT.

Não somar percentuais ou índices de cada equipe. Para Pressão, ATPM e CG, usar
"Qualquer equipe", "Favorito", "Casa" ou "Fora", conforme o método.

## Operações matemáticas

- Não: comparação direta; é a opção correta quando o site já fornece o total.
- Soma: somente para somar grandezas iguais quando o total não estiver pronto.
- Subtração: pode medir diferença entre equipes na mesma estatística.
- Divisão: pode formar uma taxa entre grandezas compatíveis.
- Multiplicação: não é necessária nos métodos atuais.

Não somar métricas de escalas diferentes, como pressão com chutes.

## Comparadores

- Maior ou igual (>=): usar nos valores mínimos, como chutes >= 1, pressão >=
  65 e odd >= 1.44.
- Menor ou igual (<=): usar nos limites máximos, como minuto <= 28.
- Maior que (>): somente quando o limite não deve ser incluído.
- Menor que (<): usar em limites exclusivos, como odd < 1.90 no FT reforçado.
- Igual a (=): usar no placar, como total de gols = 0.
- Diferente de (!=): apenas para excluir um valor específico; não é necessário
  no filtro HT 0-0.

## Filtro HT 0-0 v5

Condição de placar no construtor:

1. Primeiro valor: Estatística ao vivo > Gols > Soma das equipes (Total).
2. Operação matemática: Não.
3. Comparador: Igual a.
4. Segundo valor: Número 0.

A aba "Número" do segundo valor precisa estar selecionada. Se permanecer em
"Estatística Ao Vivo", a regra vira Gols Total = Gols Total e será sempre
verdadeira, portanto não filtra o placar 0-0.

Condições ofensivas no mesmo método:

- Finalizações Totais: Soma das equipes (Total).
- Finalizações no Gol: Soma das equipes (Total).
- Pressão, ATPM ou CG: Qualquer equipe, quando usados como confirmação de que
  pelo menos um lado está atacando.

Demais critérios:

- primeiro tempo;
- minuto entre 20 e 28;
- mercado Over 0.5 HT;
- odd entre 1.44 e 2.50;
- qualidade de dados mínima 80;
- evidência pré-jogo de Over 2.5;
- evidência histórica de ambas marcam mínima de 60%;
- janela recente válida entre 5 e 8 minutos;
- pelo menos um chute total nessa janela.

Nova confirmação na condição simples: Estatística Ao Vivo oferece o seletor
Intervalo de tempo com Jogo todo, Últimos 5 minutos e Últimos 10 minutos.
Portanto, a atividade HT deve usar diretamente Finalizações Totais da Soma das
equipes nos Últimos 5 minutos >= 1; não é mais necessário aproximar por quatro
finalizações acumuladas no jogo.

## Campos ainda pendentes de identificação

- validar quais estatísticas, além de Finalizações Totais, aceitam Últimos 5 e
  Últimos 10 minutos;
- índice de pressão;
- ataques perigosos;
- xG e xG recente;
- expectativa de gol e expectativa de escanteio;
- escala e período usados por Pressão, ATPM e CG;
- minuto/período;
- mercados e odds;
- cartões e eventos recentes;
- estatísticas pré-jogo e amostra histórica.

## Estrutura de Estatística Pré-Jogo

Disponível tanto no Passo 1 quanto no Passo 3.

Confirmado pelo usuário: o menu de estatísticas pré-jogo e suas opções são
iguais nos Passos 1 e 3. Assim, qualquer média ou probabilidade pode ser usada
como primeiro ou segundo valor da comparação.

Confirmado também: o seletor Equipe do pré-jogo repete o mesmo conjunto de
opções do seletor Equipe das estatísticas ao vivo, tanto no Passo 1 quanto no
Passo 3.

Grupos identificados:

- Médias.
- Probabilidades.

Ao escolher Probabilidades, o construtor permite definir:

- Estatística percentual.
- Jogos/amostra.
- Local.
- Operação matemática opcional no Passo 1.

Não há seletor Equipe nessa tela de Probabilidades.

Confirmado: em Probabilidades, Jogos repete Últimos 5/Últimos 10 e Local repete
Geral/Casa-Fora, nos mesmos moldes das Médias.

Confirmado pelo usuário: no Passo 3 (Segundo valor), Probabilidades repete as mesmas
estatísticas, Jogos e Local disponíveis no Passo 1.

Primeira probabilidade identificada:

- % Vitória da Casa.

Opções visíveis no grupo Probabilidades > Resultado:

- % Vitória da Casa.
- % Empate.
- % Vitória de Fora.
- % Casa ou Empate (1X).
- % Casa ou Fora (12).
- % Empate ou Fora (X2).
- % Vitória (da equipe).

Opções visíveis no grupo Probabilidades > Gols:

- % Over 0.5 Gols.
- % Over 1.5 Gols.
- % Over 2.5 Gols.
- % Over 3.5 Gols.
- % Over 4.5 Gols.
- % Under 0.5 Gols.
- % Under 1.5 Gols.
- % Under 2.5 Gols.
- % Under 3.5 Gols.
- % Under 4.5 Gols.
- % Ambas Marcam (Sim).
- % Ambas Marcam (Não).

Próximo grupo identificado:

- Probabilidades > Gols (1º tempo).

Opções confirmadas até agora:

- % Over 0.5 Gols (1º tempo).
- % Over 1.5 Gols (1º tempo).
- % Over 2.5 Gols (1º tempo).
- % Under 0.5 Gols (1º tempo).
- % Under 1.5 Gols (1º tempo).
- % Under 2.5 Gols (1º tempo).

#### Probabilidades > Escanteios

Opções confirmadas até agora:

- % Over 7.5 Escanteios.
- % Over 8.5 Escanteios.
- % Over 9.5 Escanteios.
- % Over 10.5 Escanteios.
- % Under 7.5 Escanteios.
- % Under 8.5 Escanteios.
- % Under 9.5 Escanteios.
- % Under 10.5 Escanteios.

Observação: podem existir outras opções abaixo que ainda não foram exibidas nas capturas.

#### Probabilidades > Cartões

Opções confirmadas até agora:

- % Over 2.5 Cartões.
- % Over 3.5 Cartões.
- % Over 4.5 Cartões.
- % Over 5.5 Cartões.
- % Under 2.5 Cartões.
- % Under 3.5 Cartões.
- % Under 4.5 Cartões.
- % Under 5.5 Cartões.

Observação: podem existir outras opções abaixo que ainda não foram exibidas nas capturas.

#### Probabilidades > Defesa

Opções confirmadas até agora:

- % Clean Sheets (não sofrer gol).

Observação: podem existir outras opções abaixo que ainda não foram exibidas nas capturas.

Ao escolher Médias, o construtor permite definir:

- Estatística.
- Equipe.
- Jogos/amostra, por exemplo Últimos 5 jogos.
- Local, por exemplo Geral.
- Operação matemática opcional no Passo 1.

Opções confirmadas no seletor Jogos:

- Últimos 5 jogos.
- Últimos 10 jogos.

Limitação identificada: não existe opção de últimos 15 jogos nesse construtor.
Para aproximar o método atual, usar Últimos 10 jogos como base principal e, se
necessário, combinar com o recorte de 5 jogos para medir a forma mais recente.

Opções confirmadas no seletor Local:

- Geral.
- Casa/Fora.

Casa/Fora é o recorte equivalente ao mando: histórico do mandante em casa e do
visitante fora. Geral inclui partidas independentemente do local.

Confirmado: o seletor Local, com Geral e Casa/Fora, é idêntico nos Passos 1 e 3.

Primeira estatística de média identificada:

- Média de Gols a Favor.

Opções visíveis no grupo Médias > Gols:

- Média de Gols a Favor.
- Média de Gols Contra.
- Média de Gols no Jogo (total).
- Média de Gols no 1º Tempo.
- Média de Gols a Favor (1º tempo).

Opções visíveis no grupo Médias > Escanteios:

- Média de Escanteios a Favor.
- Média de Escanteios Contra.
- Média de Escanteios no Jogo (total).
- Média de Escanteios a Favor (1º tempo).
- Média de Escanteios Contra (1º tempo).

Opções visíveis no grupo Médias > Cartões:

- Média de Cartões a Favor.
- Média de Cartões Contra.
- Média de Cartões no Jogo (total).
- Média de Cartões a Favor (1º tempo).
- Média de Cartões Contra (1º tempo).
- Média de Cartões no Jogo (1º tempo).

Opções visíveis no grupo Médias > Finalizações:

- Média de Finalizações a Favor.
- Média de Finalizações Contra.
- Média de Finalizações no Jogo (total).
- Média de Finalizações no Gol a Favor.
- Média de Finalizações no Gol Contra.
- Média de Finalizações no Gol no Jogo (total).
- Média de Finalizações para Fora a Favor.
- Média de Finalizações para Fora Contra.
- Média de Finalizações a Favor (1º tempo).
- Média de Finalizações Contra (1º tempo).
- Média de Finalizações no Jogo (1º tempo).
- Média de Finalizações no Gol a Favor (1º tempo).
- Média de Finalizações no Gol Contra (1º tempo).
- Média de Finalizações no Gol no Jogo (1º tempo).

Próximo grupo identificado:

- Médias > Posse de Bola:
  - Média de Posse de Bola.

Opções visíveis no grupo Médias > Ataques:

- Média de Ataques a Favor.
- Média de Ataques Contra.
- Média de Ataques Perigosos a Favor.
- Média de Ataques Perigosos Contra.
- Média de Ataques Perigosos no Jogo (total).

Opções visíveis no grupo Médias > Faltas e Impedimentos:

- Média de Faltas Cometidas.
- Média de Faltas Sofridas.
- Média de Faltas no Jogo (total).
- Média de Impedimentos a Favor.
- Média de Impedimentos Contra.

Opções visíveis no grupo Médias > Defesas e Passes:

- Média de Defesas do Goleiro.
- Média de Passes por Jogo.
- Média de Precisão de Passes.

## Odd

Ao selecionar Odd, existem dois grupos:

- Pré-Live.
- Ao Vivo.

### Odd > Pré-Live

Estrutura confirmada no Passo 1 (Primeiro valor):

- Seleção de uma estatística/mercado de odd pré-live.
- Primeira opção identificada: Odd Casa.
- Operação matemática opcional: Não / + / - / × / ÷.

Estrutura confirmada no Passo 3 (Segundo valor):

- Pode selecionar Odd.
- Pode escolher Pré-Live.
- Repete o seletor de estatística/mercado de odd pré-live.
- Primeira opção identificada: Odd Casa.

Observação: o catálogo completo das odds pré-live ainda será registrado pelas próximas capturas.

Status informado pelo usuário: fim do catálogo de Odd Pré-Live.

#### Odds Pré-Live > Resultado

Opções confirmadas:

- Odd Casa.
- Odd Empate.
- Odd Visitante.
- Odd do Favorito.
- Odd do Azarão.

#### Odds Pré-Live > Dupla Chance

Opções confirmadas:

- Odd Casa ou Empate (1X).
- Odd Casa ou Fora (12).
- Odd Empate ou Fora (X2).

#### Odds Pré-Live > Draw no Bet

Opções confirmadas:

- Odd Casa (Draw no Bet).
- Odd Visitante (Draw no Bet).

#### Odds Pré-Live > Gols

Opções confirmadas até agora:

- Odd Over 0.5.
- Odd Under 0.5.
- Odd Over 1.5.
- Odd Over 2.5.
- Odd Over 3.5.
- Odd Over 4.5.
- Odd Under 1.5.
- Odd Under 2.5.
- Odd Under 3.5.
- Odd Under 4.5.

#### Odds Pré-Live > Gols (1º Tempo)

Opções confirmadas até agora:

- Odd Over 0.5 (1º tempo).
- Odd Under 0.5 (1º tempo).
- Odd Over 1.5 (1º tempo).
- Odd Under 1.5 (1º tempo).
- Odd Over 2.5 (1º tempo).
- Odd Under 2.5 (1º tempo).

#### Odds Pré-Live > Ambas Marcam

Opções confirmadas:

- Odd Ambas Marcam (Sim).
- Odd Ambas Marcam (Não).

#### Odds Pré-Live > Escanteios

Opções confirmadas até agora:

- Odd Over 7.5 Escanteios.
- Odd Over 8.5 Escanteios.
- Odd Over 9.5 Escanteios.
- Odd Over 10.5 Escanteios.
- Odd Under 7.5 Escanteios.
- Odd Under 8.5 Escanteios.
- Odd Under 9.5 Escanteios.
- Odd Under 10.5 Escanteios.
- Odd Over 11.5 Escanteios.
- Odd Under 11.5 Escanteios.
- Odd Over 5.5 Escanteios.
- Odd Under 5.5 Escanteios.
- Odd Over 6.5 Escanteios.
- Odd Under 6.5 Escanteios.

#### Odds Pré-Live > Escanteios (1º Tempo)

Opções confirmadas até agora:

- Odd Over 1.5 Escanteios (1º tempo).
- Odd Under 1.5 Escanteios (1º tempo).
- Odd Over 2.5 Escanteios (1º tempo).
- Odd Under 2.5 Escanteios (1º tempo).
- Odd Over 3.5 Escanteios (1º tempo).
- Odd Under 3.5 Escanteios (1º tempo).
- Odd Over 4.5 Escanteios (1º tempo).
- Odd Under 4.5 Escanteios (1º tempo).

#### Odds Pré-Live > Cartões

Opções confirmadas até agora:

- Odd Under 2.5 Cartões.
- Odd Over 3.5 Cartões.
- Odd Under 3.5 Cartões.
- Odd Over 4.5 Cartões.
- Odd Under 4.5 Cartões.
- Odd Over 5.5 Cartões.
- Odd Under 5.5 Cartões.

Observação: Odd Over 2.5 Cartões não apareceu nesta captura e permanece pendente de confirmação.

### Odd > Ao Vivo

O catálogo será registrado nas próximas capturas seguindo o mesmo processo usado para
Odd Pré-Live. A interface está disponível nos Passos 1 e 3.

Confirmado pelo usuário: no Passo 3 (Segundo valor), todo o catálogo de Odd repete as
mesmas opções do Passo 1, tanto em Pré-Live quanto em Ao Vivo.

## Próximas configurações

Após identificar todos os campos, registrar separadamente:

1. Gol FT reforçado.
2. Gol FT por tendência e placar.
3. Próximo gol por lado dominante.
4. Próximo escanteio.
5. Escanteios de primeiro e segundo tempo.
6. Seleções pré-live.

## Robô configurado — Gol HT 0x0

Status informado pelo usuário: ativo.

Configuração final:

- Período: primeiro tempo.
- Janela: minutos 20 a 28.
- Gols da soma das equipes no jogo = 0.
- Finalizações totais da soma das equipes nos últimos 5 minutos >= 1.
- Probabilidade pré-jogo de Over 2.5 gols nos últimos 10 jogos, Casa/Fora >= 60%.
- Probabilidade pré-jogo de Ambas Marcam (Sim) nos últimos 10 jogos, Casa/Fora >= 60%.
- Odd ao vivo Over 0.5 gol no primeiro tempo entre 1.44 e 2.50.
- Resultado do alerta: Gols > 1º tempo > Over 0.5.
- CG, finalizações no gol e ataques perigosos não foram adicionados como bloqueios obrigatórios.
- Ligas: todas as profissionais e oficiais; recomendação de excluir futebol simulado,
  amistosos, base, reservas e competições amadoras com dados incompletos quando o
  seletor permitir.

## Robô configurado — HT Antecipado v2 (adaptação StatsHub)

Status: concluído e ativado pelo usuário.

Configuração final:

- Período: primeiro tempo.
- Janela: minutos 5 a 19, para não usar a mesma janela do HT reforçado 20–28.
- Gols da soma das equipes no jogo = 0.
- Finalizações totais da soma das equipes nos últimos 5 minutos >= 2.
- Finalizações no gol da soma das equipes no jogo todo >= 1.
- Média de Gols no Jogo (total) da Soma das equipes, últimos 10 jogos,
  Casa/Fora >= 4.4; por somar as médias dos dois lados, equivale a média conjunta >= 2.2.
- Probabilidade pré-jogo de Over 0.5 gols no primeiro tempo, últimos 10 jogos,
  Casa/Fora >= 60%.
- Odd ao vivo Over 0.5 gol no primeiro tempo entre 1.40 e 2.50.
- Resultado do alerta a selecionar: Gols > 1º tempo > Over 0.5.

Justificativa do par live escolhido: no recorte entregue e finalizado do HT antecipado
entre 5 e 19 minutos, a presença de chutes nos últimos 5 minutos ocorreu em 14 casos,
com 10 greens e 4 reds (71.4%); todos esses casos também tinham ao menos um chute no
gol acumulado. Esse recorte é retrospectivo e não garante desempenho futuro.

## Robô configurado — FT Contextual 0x0 (adaptação StatsHub)

Status: concluído e ativado pelo usuário.

Configuração final:

- Período: segundo tempo.
- Janela: minutos absolutos 46 a 70; se a interface reiniciar o relógio no 2º tempo,
  a faixa equivalente é 1 a 25.
- Gols da soma das equipes no jogo = 0.
- Finalizações totais da soma das equipes nos últimos 5 minutos >= 2.
- Pressão de qualquer equipe nos últimos 5 minutos >= 65.
- Cartões vermelhos da soma das equipes = 0.
- Média de Gols no Jogo (total) da Soma das equipes, últimos 10 jogos,
  Casa/Fora >= 3.6.
- Probabilidade pré-jogo de Over 1.5 gols, últimos 10 jogos,
  Casa/Fora >= 60%.
- Odd ao vivo Over 0.5 FT entre 1.40 e 2.50.
- Resultado do alerta a selecionar: Gols > Jogo todo > Over 0.5.

O recorte histórico entregue e finalizado do contextual v2b com placar 0x0 teve
3 greens e 0 reds, nos minutos 57, 66 e 69. A amostra é pequena e não garante
desempenho futuro.

## Robô configurado — FT Antecipado com 1 gol (adaptação StatsHub)

Status: concluído e ativado pelo usuário.

Configuração final:

- Período: segundo tempo.
- Janela: minutos absolutos 46 a 75; se a interface reiniciar o relógio no 2º tempo,
  a faixa equivalente é 1 a 30.
- Gols da soma das equipes no jogo = 1, cobrindo 1x0 e 0x1.
- Finalizações totais da soma das equipes nos últimos 5 minutos >= 2.
- Finalizações no gol da soma das equipes no jogo todo >= 1.
- Cartões vermelhos da soma das equipes = 0.
- Média de Gols no Jogo (total) da Soma das equipes, últimos 10 jogos,
  Casa/Fora >= 4.4.
- Probabilidade pré-jogo de Over 1.5 gols, últimos 10 jogos,
  Casa/Fora >= 60%.
- Odd ao vivo Over 1.5 FT entre 1.40 e 2.50.
- Resultado do alerta a selecionar: Gols > Jogo todo > Over 0.5 contado depois
  do alerta, pois o objetivo é exatamente mais um gol; não escolher Over 1.5
  como incremento pós-alerta.

Histórico de referência: a linha Over 1.5 teve 23 greens e 10 reds (69.7%).
Na janela 46–75, foram 22 greens e 9 reds (71.0%). Nos casos dessa janela com
chutes nos últimos 5 minutos, foram 16 greens e 6 reds (72.7%). Esses recortes
são retrospectivos e não garantem desempenho futuro.

## Robô configurado — Canto FT Asiático +0.5 (adaptação StatsHub)

Status: configuração concluída até a seleção do resultado; ativação final pendente
de confirmação do usuário.

Configuração final:

- Nome: CANTO FT ASIÁTICO +0.5 — 75-86.
- Tipo: ao vivo.
- Janela: minutos 75 a 86.
- Escanteios da soma das equipes nos últimos 5 minutos >= 1.
- Finalizações totais da soma das equipes nos últimos 5 minutos >= 1.
- Pressão atual de qualquer equipe >= 65. O StatsHub não ofereceu intervalo de
  tempo para essa estatística, portanto ela aproxima, mas não replica, a pressão
  média dos últimos 5 minutos usada na origem.
- Cartões vermelhos da soma das equipes no jogo todo = 0.
- Situação da partida desligada.
- Sem odd fixa no robô, porque a linha muda com a quantidade atual de escanteios.
- Entrada operacional: Over asiático na linha exatamente 0.5 acima do total atual;
  exemplos: 7 escanteios -> Over 7.5, 9 -> Over 9.5, 11 -> Over 11.5.
- Resultado do alerta: Escanteios > Do alerta em diante > Próximo Escanteio
  (Over 0.5 limite), que marca green se sair pelo menos um escanteio após o alerta.
- Ligas: mesmas ligas profissionais e oficiais dos demais robôs; excluir simulados,
  amistosos, base, reservas e competições amadoras com dados incompletos quando
  possível.

Referência retrospectiva dinâmica: no recorte da regra asiática com linha 0.5 acima
dos escanteios atuais e minutos 75–86 havia 14 greens e 2 reds entre os resultados
entregues e liquidados disponíveis na verificação. Os filtros adicionais reduzem a
amostra comparável, e a pressão atual do StatsHub não é idêntica à pressão média da
origem. Não há garantia de desempenho futuro.
