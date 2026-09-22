# Análise preservada — HT e J1 League — 02/09/2026

## Finalidade e autorização

O usuário pediu para verificar as fragilidades do HT, sem mudar a regra, e depois guardar a análise para evolução futura. Este documento é um registro retrospectivo, não uma configuração do bot. Não autoriza alteração de filtros, limites, métodos, canais ou promoção automática de hipóteses.

Somente este registro, seu arquivo de evidências e a referência no roadmap foram acrescentados. Nenhuma regra, arquivo de configuração, rotina de envio ou dado do banco foi alterado para esta análise.

## Amostra congelada

- Método: `gol-ht-00-min20-over25-ou-btts-odd144-red-ok-v3`.
- Linhagem: `3f8556ce73cc56b1e62daf979c9614b697b267a41133c415df91a3e618be490a`.
- Período das entradas: 26/08/2026 às 14:25:33 até 02/09/2026 às 06:32:54, horário local.
- Corte de identificação: sinal `322020`, inclusive. Não incluir entradas posteriores neste retrato histórico.
- Fonte: consulta somente leitura ao `monitor_packball.db`, tabelas `sinais`, `partidas`, `snapshots`, `resultados_sinais` e `entregas_alertas`.
- 61 sinais, em 61 partidas distintas, com entrega Telegram registrada como `entregue`, provedor Telegram e identificador de mensagem presente. Foram excluídos candidatos sem envio confirmado e avisos de espera sem entrega.
- A versão é experimental internamente, porém estas 61 entradas foram efetivamente enviadas; não confundir ausência de calibração com ausência de publicação.
- Todas as entradas eram Over 0,5 HT, em placar 0–0, aos 20–28 minutos, com odds de 1,44 a 2,50.
- ROI calculado com uma unidade por entrada e a odd registrada no sinal, não com uma odd posterior. Os retornos conferiam com a odd de cada green e −1 unidade por red.
- Evidências preservadas em [ANALISE_HT_J1_20260902_EVIDENCIAS.json](ANALISE_HT_J1_20260902_EVIDENCIAS.json): IDs, jogos, horários, resultados, recortes de histórico e atividade, hashes das features/contexto originais e critérios hipotéticos.

## Resultado observado do método

| Recorte | Entradas | Greens | Reds | Acerto | Lucro em unidades | ROI |
|---|---:|---:|---:|---:|---:|---:|
| Total desde 26/08 | 61 | 38 | 23 | 62,30% | +7,9246 | +12,99% |
| Até 30/08 | 43 | 31 | 12 | 72,09% | +13,3940 | +31,15% |
| De 31/08 até o corte | 18 | 7 | 11 | 38,89% | −5,4694 | −30,39% |
| J1 League, apenas nesta amostra | 5 | 1 | 4 | 20,00% | −2,9000 | −58,00% |

O conjunto ainda estava positivo, mas houve piora recente. O corte temporal é descritivo, escolhido nesta revisão, e não constitui validação independente. Cinco entradas da mesma liga no mesmo dia não bastam para concluir que a liga é ruim ou para justificar bloqueio permanente.

## Contexto dos sinais da J1 League

O registro sazonal do PackBall coletado em 02/09 às 06:04:53 indicava Over 0,5 no primeiro tempo em 78% de 40 jogos com estatísticas, temporada 2026/2027. É uma frequência do primeiro tempo inteiro, não a probabilidade de um gol depois de uma entrada aos 27 minutos em 0–0.

| Sinal | Partida | Minuto | Odd | Resultado |
|---|---|---:|---:|---|
| 321930 | Machida Zelvia × Kawasaki Frontale | 23 | 1,9091 | Red |
| 321961 | JEF United × Fagiano Okayama | 26 | 2,10 | Green |
| 321984 | Shimizu S-Pulse × FC Tokyo | 27 | 2,10 | Red |
| 321991 | Yokohama F. Marinos × Kyoto Sanga | 27 | 2,20 | Red |
| 321998 | V-Varen Nagasaki × Gamba Osaka | 28 | 2,10 | Red |

Os três mais recentes usaram apoio histórico da API-Football: o recorte PackBall tinha quatro jogos por time, abaixo da amostra mínima de dez. Os históricos gerais de gol HT eram Shimizu 60% / Tokyo 78,57%; Yokohama 78,57% / Kyoto 71,43%; Nagasaki 73,33% / Gamba 80%, com 14–15 jogos válidos por time.

No mando correto, Shimizu tinha gol HT em 2/6 jogos em casa (33,33%), contra 4/5 do Tokyo fora (80%). A média dos dois, 56,66%, superou o mínimo atual de 45%. Portanto, o filtro aceitou compensação entre os times; isso não foi uma violação da regra vigente, mas é uma hipótese a investigar.

## Comparações hipotéticas — nenhuma aplicada

Os testes abaixo usam informações persistidas no momento da entrada e o desfecho posterior. Foram formulados após observar os resultados e são exploratórios. Não tratá-los como prova de melhoria futura nem escolher um novo limite apenas porque favorece esta amostra.

### A. Histórico HT mínimo de 50% de cada time no mando correto

- Exigir ao menos quatro jogos HT válidos de cada lado e taxa individual de pelo menos 50% para casa e fora, sem compensar um lado fraco pela média.
- 45 entradas tinham dados suficientes; 16 não permitiam essa comparação.
- Passariam 38: 24 greens e 14 reds; lucro +5,5003 unidades.
- Seriam retiradas 7: **5 greens e 2 reds**; essas entradas somaram +1,9743 unidades.
- Na amostra comparável, o bloqueio não mostrou benefício financeiro: retiraria um conjunto que foi positivo. Não aplicar só para eliminar o red do Shimizu.

### B. Evitar entradas com zero chutes na janela recente disponível

- Usar `janelas.5.disponivel` e `janelas.5.chutes_total`; exigir pelo menos um chute total quando existe essa leitura.
- A janela é a registrada como cinco minutos pelo bot; a duração real pode variar e está preservada nas evidências. Não é necessariamente um intervalo exato de cinco minutos.
- 30 entradas tinham dado comparável; **31 não tinham a janela disponível**. Ausência de dado não foi convertida em zero.
- Passariam 24: 16 greens e 8 reds; lucro +4,0860 unidades.
- Seriam retiradas 6: **2 greens e 4 reds**; esse conjunto somou −2,4427 unidades.
- É uma hipótese mais interessante para estudar, mas seis casos são insuficientes. Exigir a presença do dado em todos os jogos seria outro filtro, muito mais restritivo, e não está validado por esta comparação.

## Validações ainda incompletas

1. **Probabilidade condicional ao minuto/placar:** o histórico de placares de intervalo não reconstrói completamente quais jogos estavam 0–0 aos 20–28 minutos e tiveram gol depois. No histórico em cache dos dez times da J1, havia 150 registros correspondentes a 127 partidas distintas; apenas 25 dessas partidas tinham sido monitoradas localmente. Há eventos parciais, mas não uma série completa de todos os jogos para estimar essa chance sem viés.
2. **Comparabilidade do histórico:** os 15 jogos não são necessariamente da liga e temporada atuais. Por exemplo, Shimizu incluía 13 partidas da J1 e dois amistosos; Tokyo incluía 12 da J1, uma da Emperor Cup e dois amistosos. Não chamar essa taxa de estatística exclusiva da J1 atual.
3. **xG recente:** havia xG na janela API de cinco minutos em apenas 2 das 61 entradas. Não existe cobertura suficiente nesta amostra para comparar um filtro de xG recente de forma ampla.
4. **Preço e calibração:** nenhuma das 61 entradas tinha probabilidade calibrada persistida. Histórico HT do jogo inteiro não pode ser usado diretamente como probabilidade ao vivo para alegar vantagem sobre a odd.
5. **Resultados:** 46 das 61 entradas tinham uma confirmação API posterior ao primeiro tempo disponível na consulta e estavam coerentes com o resultado registrado; nas outras 15 não havia essa confirmação posterior nessa forma. Isso não prova erro nas 15, mas limita a segunda conferência. Os cinco resultados J1 estavam coerentes com o HT posterior consultado.

## Validação pré-registrada existente — população separada

O avaliador `validacao_gol_ht_00_min20.py` conserva uma coorte dos primeiros 100 candidatos independentes após a âncora de 26/08 às 13:00:29, não apenas os sinais enviados. Não somar seus números ao ROI do Telegram.

- Total: 100 resultados, 60 greens, 40 reds; ROI +8,27%.
- Primeiros 70, desenvolvimento: 45 greens, 25 reds; ROI +16,48%.
- Últimos 30 reservados: 15 greens, 15 reds; ROI −10,87%.
- Intervalo de ROI de 95% calculado pelo avaliador para os 100: −9,43% a +25,97%.
- Decisão registrada: **inconclusiva**. A amostra mínima foi completada, mas os critérios de vantagem não foram satisfeitos.

## Como usar este registro na evolução futura

- Preservar esta amostra e sua data de corte; criar nova revisão para resultados posteriores, sem sobrescrever este retrato.
- Separar sinais enviados, candidatos não enviados e observações silenciosas. Manter ROI de entrega real separado de resultados hipotéticos.
- Comparar por versão/linhagem e documentar mudanças de coleta ou proteções; uma linhagem de método igual não prova que todas as camadas operacionais permaneceram idênticas.
- Caso o usuário autorize estudar um novo filtro, definir antes os critérios e a amostra futura; não retunar limites sobre os mesmos resultados até parecer lucrativo.
- Medir simultaneamente reds evitados, greens perdidos, volume, ROI, cobertura dos dados e incerteza; considerar dependência entre jogos da mesma rodada/liga.
- Melhorar a evidência de minuto, placar e eventos históricos antes de afirmar probabilidade condicional de gol no restante do HT.
- Nenhuma regra deve ser alterada com base neste documento sem nova autorização do usuário.

Conclusão preservada: o método tinha fundamento histórico e saldo geral positivo, mas a queda recente e o teste separado inconclusivo impedem afirmar que os reds foram apenas azar. Também não há prova de que endurecer o histórico individual melhore o método. A hipótese de atividade recente merece estudo futuro, não ativação imediata.
