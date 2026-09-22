# Revisão do bloqueio de histórico — 03/09/2026

Revisão somente leitura do funcionamento do bot e dos registros locais. Nenhuma regra, configuração, entrega, resultado ou processo do bot foi alterado. Corte estatístico: 03/09/2026 às 12h30, no relógio local do banco.

## Conclusão

Não há evidência suficiente para baixar indiscriminadamente a amostra mínima. O histórico insuficiente é real nos casos examinados, e alguns deles têm outras reprovações que só seriam verificadas depois desse primeiro bloqueio. Assim, quatro resultados posteriormente verdes não significam quatro entradas recuperáveis alterando apenas essa proteção.

A melhoria indicada é completar e validar o histórico antes da decisão, preservando os critérios atuais. Isso ainda não foi implementado nesta revisão.

## O que já está em vigor

- Para a linha HT, a proteção de conversão exige pelo menos 10 jogos com placar de intervalo conhecido por equipe e 4 no mando correspondente. Não basta haver 10 placares finais.
- A coleta solicita as últimas 15 partidas à API-Football. O recorte de mando é extraído dessas mesmas 15; não são 15 adicionais em casa/fora.
- A exceção HT para histórico insuficiente está ligada: exige método HT ativo, pelo menos 2 chutes no gol acumulados e qualidade de dados de pelo menos 80. Não dispensa as outras proteções.
- O veto de zero chutes recentes do HT 0–0 também está ligado. Chutes no gol acumulados e total de chutes recentes são métricas diferentes.
- A validação de histórico anterior ao envio rejeita jogos históricos com mais de 365 dias. Ela ocorre depois da primeira decisão de bloqueio por amostra.

## Os cinco casos do bloqueio de histórico de hoje

Somente HT 0–0 v4, sem entradas efetivamente entregues e sem repetir partida/mercado/linha. As amostras abaixo são as que estavam no snapshot da decisão, antes de qualquer saneamento por idade.

| Partida | Amostra HT geral casa/fora | Amostra HT no mando | Chutes no gol acumulados | Resultado posterior |
| --- | --- | --- | --- | --- |
| Korea DPR U20 x Iran U20 | 6 / 15 | 1 / 8 | 1 | Red |
| Bangladesh U20 x Syria U20 | 4 / 11 | 1 / 6 | 1 | Green |
| Palestine U20 x Vietnam U20 | 9 / 11 | 2 / 5 | 0 | Green |
| Sri Lanka U20 x Maldives U20 | 4 / 6 | 2 / 4 | 1 | Green |
| Shimshon Tel Aviv x Ironi Beit Shemesh | 15 / 2 | 9 / 1 | 1 | Green |

IDs: 332436, 333390, 333879, 334151 e 335482, respectivamente. Todos os resultados foram conferidos em `resultados_sinais` e nos snapshots de liquidação do intervalo.

Nenhum dos quatro greens satisfazia a exceção já ativa de 2 chutes no gol. Qualidade 100 nos snapshots não significa que o histórico de intervalo esteja completo: são verificações diferentes.

### Outras proteções que continuariam relevantes

Reexecutando a função pura de chutes no instante da tentativa registrada, com o snapshot original:

- Korea DPR e Bangladesh: zero chutes na janela recente; ambos também seriam vetados por essa proteção.
- Palestine: zero chutes recentes; também seria vetado.
- Sri Lanka: dois chutes recentes; passa nesse veto, mas não na amostra histórica.
- Shimshon: janela recente indisponível; isso não é tratado como zero e não acrescenta veto por chutes.

Nos caches de 15 jogos anteriores à decisão, que reproduzem exatamente os resumos gravados, há histórico com mais de 365 dias em Korea DPR, Bangladesh, Palestine e Sri Lanka. Nos três greens desse grupo, a validação histórica também reprovaria a entrada se a primeira barreira fosse removida.

Esclarecimento temporal conferido na comparação seguinte: em Shimshon, `criado_em` (10h53min43s) marca o registro inicial, não a decisão final. `features.decisao_em` é 10h54min03s e a tentativa ocorreu às 10h54min04s. Os caches foram gravados às 10h54min01s e 10h54min02s, portanto antes da decisão final, e reproduzem os resumos do snapshot. O visitante tem quatro jogos, todos com mais de 365 dias. Assim, esse quarto green também seria bloqueado pela validade histórica, ainda que a amostra mínima fosse dispensada.

## Comparação: reduzir a exceção de 2 para 1 chute no gol

Comparação somente leitura, com o mesmo corte de 12h30. Considera apenas candidatos com exatamente 1 chute no gol e qualidade de pelo menos 80; casos com 2 ou mais já pertencem à exceção atual e não são acréscimos.

- HT 0–0 v4: quatro candidatos adicionais passariam nessa primeira exceção; resultados posteriores de 3 greens (Bangladesh, Sri Lanka e Shimshon) e 1 red (Korea DPR).
- Mantendo a validade histórica, os quatro continuariam bloqueados por partidas antigas. Os caches pertinentes são anteriores à decisão final e reproduzem os resumos gravados. Portanto, nenhum envio adicional seria liberado entre esses quatro apenas por mudar 2 para 1.
- Bangladesh e Korea DPR também seriam vetados por zero chutes recentes. Isso é um veto separado, não uma exigência de chutes no gol.
- No recorte anterior v3 da mesma janela de sete dias, os casos com exatamente 1 chute no gol tiveram 1 green e 4 reds. Essa versão não deve ser combinada com a v4 como se fosse a mesma política.

Não houve alteração do limite de 2 chutes, das demais proteções ou dos envios. A comparação não constitui retorno oficial nem promessa de acerto futuro.

## Comparação ampliada, sem misturar versões

Janela: 27/08/2026 12h30 a 03/09/2026 12h30. Primeiro bloqueio por `historico_da_linha_insuficiente` de cada partida/mercado/linha, excluindo seleções com entrega efetiva registrada.

| Versão HT 0–0 | Greens hipotéticos | Reds hipotéticos |
| --- | ---: | ---: |
| v3 anterior | 4 | 7 |
| v4 atual | 4 | 1 |

Esses são resultados observados de candidatos barrados, não resultados de um replay completo de uma regra alternativa. As versões e proteções mudaram no período; não se deve juntar as linhas para apresentar uma probabilidade ou taxa esperada da versão atual. A amostra v4 é de apenas cinco seleções.

O total anteriormente informado de seis greens e quatro reds incluía outros motivos de bloqueio dos métodos ativos. Esta revisão é especificamente sobre a amostra histórica insuficiente.

## Limitação encontrada na coleta

O guardião `protecao_conversao_gols.py` utiliza `tendencia_linhas_gols_v1`, produzida pela coleta de histórico da API-Football. O histórico do PackBall não completa automaticamente esse campo.

A coleta separada de até 30 jogos para o método por períodos existe, mas tem resumo próprio. Nos casos de hoje, os resumos de mando também eram pequenos; não há evidência de que bastaria reutilizá-los para completar as amostras. Aumentar o número solicitado não cria partidas ausentes na fonte, e estender anos para trás é especialmente problemático em sub-20.

## Melhoria recomendada para uma próxima alteração autorizada

1. Distinguir falta de resposta, placar HT ausente, pouca amostra geral, pouca amostra no mando e histórico antigo. Hoje vários desses problemas aparecem sob o mesmo primeiro motivo.
2. Quando houver dados recuperáveis, complementar apenas os registros necessários em fontes disponíveis, validando equipe, competição, data, período e identidade da partida, sem duplicações.
3. Descartar partidas antigas antes de recompor os resumos; não simplesmente ignorar o veto final de idade.
4. Reanalisar o candidato com a amostra recomposta e manter odd fresca, minuto, tendência, chutes e ausência de duplicidade.
5. Medir prospectivamente quantas entradas esse resgate recupera. Não prometer recuperar os greens retrospectivos nem contabilizá-los no ROI oficial.

Fontes locais: `monitor_packball.db` em modo somente leitura; `protecao_conversao_gols.py`, `contexto_linhas_gols.py`, `contexto_periodos_10.py`, `validade_historico_gols.py`, `filtro_ht_chutes_recentes.py`, `telegram_alertas.py` e `servico_monitor.py`.
