# Análise de melhoria do HT 0–0 v4 — 03/09/2026

Análise retrospectiva, somente leitura, fechada às 17h28. Nenhuma regra, configuração, entrega ou processo foi alterado.

## População

Primeira entrega oficial por partida do método `gol-ht-00-min20-over25-ou-btts-odd144-red-ok`, preservando separadamente as versões v3 e v4. Resultados pendentes e entradas não entregues não foram tratados como green ou red.

| Recorte | Sinais | Green | Red | Acerto | Retorno |
| --- | ---: | ---: | ---: | ---: | ---: |
| v3 completa | 78 | 47 | 31 | 60,3% | +7,410 u |
| v4 completa | 15 | 5 | 10 | 33,3% | −5,594 u |

A v4 corrigiu a direção de previsões Over/Under. Os 15 sinais v4, porém, foram sustentados por consenso pré-jogo de Over 2,5 e/ou histórico de ambas marcam, que são apoios preservados da v3. Nenhum deles registra a previsão corrigida como apoio favorável. Portanto, a sequência v4 não pode ser atribuída diretamente à correção de direção.

## Alterações comparadas

“Atividade recente” abaixo significa uma janela válida de 5 minutos com pelo menos um chute total. Não significa chute no gol acumulado.

| Regra retrospectiva | v3 | Retorno v3 | v4 | Retorno v4 | Efeito observado |
| --- | --- | ---: | --- | ---: | --- |
| Regra atual | 47G/31R (60,3%) | +7,410 u | 5G/10R (33,3%) | −5,594 u | Referência |
| Exigir atividade recente | 20G/11R (64,5%) | +3,859 u | 4G/3R (57,1%) | +0,572 u | Opção intermediária |
| Exigir os dois apoios históricos | 30G/14R (68,2%) | +9,757 u | 3G/4R (42,9%) | −1,428 u | Insuficiente sozinha na v4 |
| Dois apoios + atividade recente | 12G/3R (80,0%) | +5,931 u | 3G/2R (60,0%) | +0,572 u | Melhor consistência entre versões |
| Anterior + excluir copas | 9G/3R (75,0%) | +3,650 u | 3G/1R (75,0%) | +1,572 u | Amostra pequena; piorou a v3 |

Os “dois apoios” são:

1. evidência pré-jogo de tendência de Over 2,5; e
2. evidência histórica de ambas marcam.

No conjunto combinado, a regra com dois apoios e atividade recente selecionou 20 entradas: 15 greens, 5 reds e +6,503 unidades. A combinação foi escolhida após observar os dados e, por isso, esses números não são uma garantia prospectiva.

## Alterações que não resolveram

- Exigir pelo menos dois chutes no gol acumulados: v3 57,6%; v4 33,3%.
- Limitar o minuto a 20–24: v3 62,0%; v4 33,3%.
- Limitar odd abaixo de 2,00: v3 77,1%; v4 36,4%. A odd, sozinha, não resolveu a v4.
- Excluir todas as copas: não é sustentado pela v3, na qual as copas tiveram 68,8% no recorte completo.
- Limitar somente o número de sinais a cada 10 minutos melhora a exposição, mas não seleciona tecnicamente a melhor partida. Aplicado junto ao filtro estrito, retirou um green da v4 e reduziu o resultado para 2G/2R.

## Origem da sequência ruim

Oito dos 15 sinais v4 não possuíam janela válida dos últimos 5 minutos. Esse grupo terminou com 1 green e 7 reds. Nos sete com janela válida, foram 4 greens e 3 reds, com +0,572 unidade.

Cinco sinais enviados entre 14h23 e 14h29 terminaram red. O filtro “dois apoios + atividade recente” teria bloqueado todos os cinco antes do envio. Isso mostra concentração de exposição, mas não prova independência estatística entre as partidas.

Na v3, a simples ausência da janela não foi negativa (24G/11R). Portanto, “janela indisponível” não deve ser declarada universalmente como uma característica ruim; ela é útil aqui quando combinada com os dois apoios e deve ganhar uma versão própria para validação futura.

## Mudança mais defensável

Criar uma versão nova e reversível apenas do HT 0–0, preservando a correção da v4 e todos os controles atuais, mas exigindo simultaneamente:

1. tendência pré-jogo de Over 2,5;
2. histórico de ambas marcam;
3. janela válida de 5 minutos;
4. pelo menos um chute total nessa janela.

Essa opção teria mantido 5 dos 15 sinais v4, removendo 8 dos 10 reds e 2 dos 5 greens. Na v3, teria mantido 15 dos 78 sinais, com 12 greens e 3 reds. A redução estimada de volume é grande: aproximadamente 67% na v4 e 81% na v3.

Uma alternativa intermediária é exigir somente a atividade recente. Ela preserva mais volume, mas tem evidência histórica menos forte.

Antes de promoção definitiva, a versão nova deve manter identidade própria e medição prospectiva. ROI oficial só deve incluir sinais realmente entregues.
