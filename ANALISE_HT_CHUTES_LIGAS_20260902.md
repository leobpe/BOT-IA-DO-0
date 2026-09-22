# HT 0x0 — filtro de chutes e prejuízo por liga

Corte dos dados: 02/09/2026, 17:28:43, horário local do computador.
Escopo: `gol-ht-00-min20-over25-ou-btts-odd144-red-ok-v3`.

## Mudança autorizada

Veto adicional antes de enviar este método: zero chutes TOTAL das duas equipes,
confirmado na janela de 5 minutos. Aceita a tolerância temporal que o coletor já
usa (janela real entre 5 e 8 minutos). Um chute não aprova sozinho: continuam
valendo histórico, tendência, odd, minuto, qualidade e todas as outras proteções.

- PackBall tem prioridade, incluindo as colunas temporais do Scanner.
- API-Football só complementa janela ausente/inválida com fixture pareado,
  período correto, leitura de até 120 segundos e sem conflito de chutes atual.
- Zero confirmado no PackBall não é sobrescrito por valor maior na API.
- Ausência, contador reiniciado, duração inválida, dados incoerentes ou antigos
  não são considerados zero. Nesses casos, este veto não acrescenta bloqueio;
  as proteções anteriores continuam valendo.
- Rechecagem de odd não renova a idade da estatística de chutes.
- Não altera outros HT, FT, próximo gol, escanteios, pré-live ou Scanner.
- Não reativa métodos. Não muda a geração/coorte original do HT.

Versão independente: `ht00-veto-zero-chutes-recentes-v1`.
Auditoria por sinal: `entregas_alertas`, canal interno
`gateway:ht_chutes_recentes`, sem mensagem no Telegram e sem contar como envio.
O registro original das características do sinal permanece imutável.

Para desfazer apenas esta mudança: configurar
`FILTRO_HT_CHUTES_RECENTES_ATIVO=0` no ambiente e reiniciar pelo iniciador
validado. Padrão do filtro: ativo. Não é necessário restaurar arquivos antigos
nem mexer nos filtros/login do navegador.

## Efeito retrospectivo — não é validação futura

Apenas entregas reais confirmadas no Telegram; deduplicação por partida/método.
Resultado e retorno registrados pelo bot, com 1 unidade por entrada. Sombra sem
entrega e avisos de monitoramento não entram. Não houve duplicatas na amostra.

| Recorte | Método antes do veto | Casos que o veto retiraria | Casos mantidos |
|---|---|---|---|
| Mesma versão, histórico completo | 47 G / 31 R; +7,4103 u | 3 G / 7 R; −4,6094 u | 44 G / 24 R; +12,0197 u |
| 27/08 a 02/09 | 43 G / 27 R; +7,2603 u | 2 G / 5 R; −3,4394 u | 41 G / 22 R; +10,6997 u |
| Hoje, 02/09 | 13 G / 13 R; −1,9716 u | 1 G / 3 R; −2,1667 u | 12 G / 10 R; +0,1951 u |

Os 7 vetados do recorte semanal: sinais 310185, 313079, 315677, 323204,
325916, 325976 e 326308. Os 3 anteriores adicionais no histórico: 279005,
279250 e 279388. Todos usam chutes PackBall/Scanner, não API fallback.

Casos de hoje retirados pelo veto:

- Yunnan Yukun x Chongqing Tonglianglong FC: red (323204).
- Sorrento x Cosenza: red (325916).
- Inter Milano W x Wolfsburg W: green (325976).
- Slavia Sofia x Levski Sofia: red (326308).

Dados ausentes foram 33 dos 70 casos semanais, com 22 G / 11 R e +7,5604 u.
Por isso, exigir janela disponível de todos seria uma mudança bem mais restritiva
e diferente da hipótese autorizada. Não foi aplicada.

A hipótese foi escolhida após observar perdas. Há viés de seleção e amostra
pequena (7 casos semanais). Os ganhos acima são contrafactuais, não lucro real
recuperado nem promessa de melhora. Uma avaliação posterior deve usar apenas
novas partidas, medir greens perdidos/reds evitados/ROI, separar casos com dado
ausente, manter o mesmo corte e não ajustar o limiar a cada sequência negativa.

## Ligas com maior prejuízo — somente este HT, últimos 7 dias

| País / liga | Green | Red | Lucro em unidades | Dias distintos |
|---|---:|---:|---:|---:|
| Japão — J1 League | 1 | 4 | −2,90 | 1 |
| Argentina — Liga Profesional de Fútbol | 0 | 2 | −2,00 | 2 |
| China — FA Cup | 0 | 2 | −2,00 | 2 |
| Croácia — 2. HNL | 0 | 2 | −2,00 | 1 |
| Itália — Coppa Italia Serie C | 1 | 2 | −1,0909 | 1 |

Competições de nomes iguais foram separadas por país: FA Cup da China não foi
misturada com a FA Cup da Malásia. Não há justificativa para excluir toda uma
liga de gols FT ou escanteios com base nestes resultados HT. Nenhum bloqueio
por liga foi adicionado. O filtro de chutes também não teria eliminado os quatro
reds da J1; é incorreto apresentá-lo como solução comprovada para aquela rodada.

Outros métodos HT na semana, preservados sem alterações:

- Antecipado v2: 10 G / 5 R; +2,0417 u.
- Contextual v2b: 2 G / 3 R; −1,7630 u.
- Top critério casa/fora 10: 3 G / 0 R; +1,8300 u.

Reprodução somente leitura: `auditar_ht_chutes_ligas.py`. O script consulta
resultados atuais, portanto uma nova execução gera um novo corte; este documento
preserva o recorte que orientou a mudança.
