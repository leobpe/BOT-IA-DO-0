# Comparação descritiva dos métodos — 02/09/2026, 12:20 locais

Somente leitura. Fontes: monitor_packball.db e pre_live.db. Nenhuma regra foi alterada nesta comparação.

## Critério de contagem

- Ao vivo: sinal com confirmação de entrega e ID de mensagem; canal de entrada, incluindo métodos autorizados que internamente usam a rota `:teste`. Excluir avisos de espera, edições de resultado, entregas incertas e candidatos sem envio. Uma observação por sinal entregue, sem duplicar canais.
- Identificar o método em `features.exploracao_sombra.versao`, quando existir, e separar o mercado. A versão genérica `sinais-v6` não identifica sozinha o método contextual ou antecipado.
- Acerto = green/(green+red). Estes recortes não têm resultados parciais. ROI = soma do retorno registrado/entradas liquidadas com retorno conhecido, a uma unidade por entrada; void, sem dado e pendentes separados.
- Pré-live: entregas individuais confirmadas separadas de candidatas que apareceram somente nas listas. Não somar a lista preliminar ao ROI das entradas confirmadas.

## Recortes históricos principais

| Método | Greens | Reds | Acerto | ROI registrado | Período dos envios |
|---|---:|---:|---:|---:|---|
| Gol FT antecipado 2T | 70 | 33 | 67,96% | +6,33% | 15/08–02/09 |
| Gol FT contextual V2b | 9 | 2 | 81,82% | +39,20% | 27/08–02/09 |
| Gol HT antecipado | 22 | 11 | 66,67% | +14,79% | 15/08–30/08 |
| Gol HT 0x0/min20 | 40 | 26 | 60,61% | +9,73% | 26/08–02/09 |
| Cantos asiáticos FT base v9d | 17 | 2 | 89,47% | +67,50% | 05/08–01/09 |

HT 0x0 tem mais uma entrada pendente. Cantos base tem também um void e um sem dado, não incluídos na taxa/ROI da tabela. Não confundir cantos base com o experimento ampliado `exploracao-asiatico-ft-multiplos-v2`, que registrou 1 green e 5 reds (ROI −66,67%).

## Recência

- FT antecipado 2T de 27/08 até o corte: 12 greens/5 reds, 70,59%, ROI +8,99%.
- FT contextual V2b: os 11 resultados estão nesse mesmo intervalo.
- HT 0x0 desde 31/08 às 12:00: 8 greens/13 reds, 38,10%, ROI −31,89%, mais uma pendente.
- Todos os métodos ao vivo somados no histórico: 457 greens/332 reds, ROI −1,45%; versões antigas e novas misturadas, portanto não é uma medida específica da configuração atual.

## Pré-live

- Entradas individuais confirmadas: 3 greens/0 reds, ROI +51,67%; amostra insuficiente para atestar superioridade.
- Somente nas listas: 54 greens/32 reds e 2 pendentes, ROI descritivo −5,76%. As listas incluem candidatas pendentes e diferentes versões; não equivalem a entradas confirmadas.

## Interpretação e limites

O FT antecipado 2T é uma base favorável mais bem amostrada para estudar gols; o V2b é promissor, porém seus 11 casos não demonstram que seja superior. As classes de evidência adicionadas à mensagem são explicativas e não representam taxas de acerto validadas.

Estes resultados antecedem a nova proteção de atualidade histórica aplicada em 02/09. Incluem decisões que a checagem nova poderia impedir. Não excluí-los retroativamente nem tratar o desempenho antigo como prova da configuração nova. Intervalos aproximados de ROI para FT antecipado 2T (−8,11% a +20,76%) e V2b (−5,55% a +83,95%) incluem zero, mesmo antes de ajustar múltiplas comparações.

Comparação retrospectiva, com períodos, regras auxiliares e mercados diferentes; não é experimento controlado, não prova vantagem futura e não determina a probabilidade de uma próxima entrada. Nenhuma mistura nova de métodos foi validada ou ativada com base nesta tabela.

Reprodução: auditar_metodos_enviados.py, aberto em SQLite somente leitura. Como o banco continua recebendo resultados, novas execuções terão corte atualizado.
