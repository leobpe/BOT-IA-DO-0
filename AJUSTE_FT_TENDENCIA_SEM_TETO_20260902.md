# FT: tendência sem teto de 2,5 — 02/09/2026

O usuário esclareceu que tendências superiores a 2,5 também devem ser
consideradas. O número descreve o total da partida, não exige que uma
equipe marque três gols sozinha.

## Mudança

Na rota `gol_ft_tendencia_mais_um`, quatro apoios deixaram de exigir a faixa
1,5–2,5 e passam a exigir pelo menos 1,5, sem teto superior:

- Linha de consenso pré-jogo, com consenso suficiente.
- Previsão explicitamente over do provedor.
- Soma de duas estimativas pontuais completas de gols esperados.
- Média de gols dos confrontos diretos, com a amostra mínima existente.

Cada apoio continua contando uma única vez. Um valor maior não aumenta por
si só a pontuação nem se transforma em probabilidade garantida. Previsões
under e faixas direcionais por equipe continuam sendo tratadas corretamente
pela correção anterior, sem virar evidência de over ou média esperada.

## Sem mudanças

- HT já aceitava tendências over iguais ou superiores a 2,5, ou apoio de
  ambas marcam; seu código e sua versão não foram alterados nesta aplicação.
- Odd mínima 1,44, faixa operacional de odds, janelas de minuto e placares.
- Linha da entrada: depende do placar, não da altura da tendência pré-jogo.
- Mínimo de dois apoios FT, qualidade, capacidade ofensiva, histórico por
  linha e mando, atividade recente e validações anteriores ao envio.
- Demais métodos ativos, métodos desativados, pré-live, escanteios e Scanner.
- Resultados e âncoras anteriores: não são reescritos nem transferidos para
  a estatística da nova versão.

## Registro e reversão

Nova versão: `gol-ft-tendencia-15-mais-um-odd144-v5`, com âncora FT v5.
Os nomes das quatro evidências agora dizem `15_ou_mais`; a faixa registrada
é `[1.5, null]`, onde `null` representa ausência de teto, não dado faltante.

Caso o usuário peça voltar ao teto, restaurar as quatro condições máximas
de 2,5, atualizar os testes, criar uma nova versão/âncora e fazer o reinício
validado. Não reutilizar nem sobrescrever uma âncora já registrada. Isso
preserva a correção direcional de over/under.

## Testes

Os testes específicos cobrem tendências 1,5/2,5/2,6/3,5/4,5/6,0, dados
inválidos, previsões under, mínimo de evidências, histórico por linha,
atividade, odd, minuto, qualidade, envio pela rota autorizada e preservação
das âncoras anteriores. Também verificam que a linha e a pontuação não sobem
automaticamente quando apenas o valor da tendência aumenta.

Resultados: 32 testes específicos passaram; suíte completa com 2.042 testes
passou em 95,585 segundos. Os testes não enviam mensagens reais ao Telegram.
