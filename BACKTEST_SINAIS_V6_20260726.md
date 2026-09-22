# Backtest cronológico da regra sinais-v6

Data da execução: 26/07/2026.

## Método

- Origem: banco operacional aberto somente para leitura.
- Snapshots reproduzidos em ordem cronológica: 13.216.
- Cada decisão foi gerada apenas com informações disponíveis naquele snapshot.
- A liquidação utilizou exclusivamente snapshots posteriores.
- O banco temporário do replay não foi incorporado à calibração oficial.
- A análise de cortes usou 70% inicial para desenvolvimento e 30% final para
  validação, sem escolher o corte consultando o resultado futuro.

## Resultado geral

| Mercado | Amostra | Acerto | ROI |
|---|---:|---:|---:|
| Over de gols FT | 151 | 53,64% | -12,83% |
| Gol no primeiro tempo | 52 | 59,62% | +2,02% |
| Próximo gol | 88 | 48,86% | -10,92% |
| Escanteio normal | 0 | — | — |
| Escanteios asiáticos FT | 0 | — | — |
| Escanteios asiáticos 1T | 0 | — | — |
| Escanteios asiáticos 2T | 0 | — | — |

Os mercados de escanteio ficaram sem amostra porque o histórico anterior não
possuía odds tipadas de forma compatível com a separação introduzida na v6.
Esses dados não foram reinterpretados retroativamente.

## Cortes sombra

### Over de gols FT

O corte escolhido apenas no desenvolvimento foi odd maior ou igual a 1,53.
Ele teve ROI de +4,89% em 47 observações de desenvolvimento, mas falhou na
validação: 35 observações e ROI de -13,00%. Portanto, não está apto.

### Gol no primeiro tempo

A amostra de desenvolvimento não permitiu selecionar um corte simples com o
mínimo exigido. Nenhuma mudança deve ser feita.

### Próximo gol

O corte escolhido apenas no desenvolvimento foi minuto maior ou igual a 56:

- desenvolvimento: 32 observações, 59,38% de acerto e ROI de +8,69%;
- validação: 19 observações, 52,63% de acerto e ROI de +6,58%;
- baseline da validação: 27 observações e ROI de -1,52%.

O corte melhorou fora da amostra, mas a validação contém somente 19 resultados.
Ele deve permanecer como hipótese sombra e não ser promovido automaticamente.
Uma confirmação independente com resultados posteriores da v6 é necessária.

## Comparação com a sinais-v4

O histórico FT da v4 permanece no banco:

- 127 resultados brutos independentes;
- 83 resultados na amostra oficial vinculada;
- amostra oficial: 55,4% de acerto, ROI de -8,0% e AUC de 0,516;
- faltavam 17 resultados para o mínimo de 100 da amostra oficial.

Chegar a 100 não teria garantido liberação, porque ROI, discriminação e
validação cronológica também precisam passar. A v4 permanece como baseline
histórico e não é somada à v6 como se as regras fossem iguais.

## Atualização incremental às 03:11

Um novo replay integral foi executado depois da entrada dos snapshots mais
recentes, novamente com a origem aberta somente para leitura e um banco
temporário descartado ao final:

- snapshots processados: 13.415;
- partidas com liquidação independente: 183;
- Over de gols FT: 152 resultados, 81 greens, 71 reds, 53,29% de acerto e
  ROI de -13,40%;
- Gol no primeiro tempo: 54 resultados, 31 greens, 23 reds, 57,41% de
  acerto e ROI de -1,76%;
- Próximo gol: 90 resultados, 43 greens, 47 reds, 47,78% de acerto e
  ROI de -12,90%.

O replay prova que há dados históricos compatíveis suficientes para avaliar o
FT sob a lógica v6, mas não autoriza sua ativação: o ROI permaneceu negativo e
a pontuação técnica não discriminou greens de reds (AUC 0,4716; intervalo de
95% entre 0,3794 e 0,5638). Esses resultados permanecem como backtest de
pesquisa e não são incorporados ao contador oficial futuro.

## Análise temporal reproduzível com linhagem

O replay agora cria no SQLite temporário a âncora criptográfica da v6 antes da
primeira decisão e anexa o fingerprint vigente a todos os candidatos. Assim, o
dataset temporal é reconstruído pelo mesmo validador usado na operação:

- 152 partidas FT elegíveis e 152 vetores válidos, cobertura de 100%;
- desenvolvimento cronológico: 106 partidas;
- validação cronológica posterior: 46 partidas;
- fingerprint do dataset:
  `fb1ae6d35f380d077ed1509143223535e8d63749db3842f5fe3d19407794cb66`.

Nenhuma feature pré-registrada apresentou intervalo de 95% da AUC totalmente
acima de 0,5. O melhor limite escolhido exclusivamente no desenvolvimento foi
`j5_chutes_por_minuto <= 0,3914`: teve ROI de +7,22% em 58 partidas de
desenvolvimento, mas ROI de -0,56% nas 27 partidas futuras que atenderam ao
corte. Apesar de reduzir a perda da validação-base de -14,80%, permaneceu
negativo e está formalmente marcado como inapto para alterar a regra.

Esse resultado substitui qualquer interpretação manual do corte baseada apenas
na amostra completa. O motor FT permanece inalterado.

## Atualização de gol no primeiro tempo em 28/07

O replay integral foi repetido sobre 16.791 snapshots, em banco temporário
descartado ao final. O mercado `gol_ht` produziu 66 partidas independentes:

- 36 greens e 30 reds, acerto de 54,55%;
- retorno de -4,61 unidades e ROI de -6,98%;
- drawdown máximo de 11,10 unidades e sequência máxima de sete reds;
- AUC da nota técnica de 0,4611, com intervalo de 95% entre 0,3204 e 0,6018.

Na divisão cronológica, as 46 partidas de desenvolvimento tiveram ROI de
+7,74%, enquanto as 20 partidas futuras caíram para 35% de acerto e ROI de
-40,85%. O corte escolhido somente no desenvolvimento (`minuto >= 20`) também
falhou na validação: 14 partidas, 35,71% de acerto e ROI de -38,86%.

Uma busca exploratória adicional avaliou cortes simples de minuto, odd, linha,
nota, qualidade, idade da odd, chutes, pressão e escanteios nas janelas de
5/10/15 minutos. Exigindo amostra mínima de 20 no desenvolvimento, oito na
validação e ROI positivo nos dois blocos, nenhum padrão sobreviveu.

Conclusão: não existe evidência reproduzível para ajustar `gol_ht` agora.
Nenhuma hipótese sombra nova foi registrada e o motor ativo permaneceu
inalterado. A coleta prospectiva deve continuar; eventual nova hipótese precisa
ser criada com dados posteriores e validada em amostra independente.
