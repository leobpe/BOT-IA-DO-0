# Mapeamento validado da Bet365

## Regra operacional

- A Bet365 somente deve ser acessada mediante ação manual explícita do usuário.
- O bot não deve abrir sessões, clicar em partidas ou consultar a Bet365 em
  segundo plano.
- A fonte permanece desligada no monitor até existir integração autorizada,
  limitada, auditável e validada.
- Capturas manuais não representam sinais de aposta. Elas servem somente para
  comprovar a estrutura e as odds exibidas.

## Evidência de 26/07/2026

Partida observada:

- Bet365: Weston Bears x Melbourne City
- PackBall: Weston Workers FC x Melbourne City
- API-Football: confirmou `Weston Bears` como o mesmo mandante da partida
  PackBall, fixture `1560871`.

Arquivo preservado:

- `evidencias_bet365/20260726/995fcdf9d66fd7ce54bc570fee1ea1a29f8da75eb1af2cae0ea493461471acbe.png`
- SHA-256:
  `995fcdf9d66fd7ce54bc570fee1ea1a29f8da75eb1af2cae0ea493461471acbe`

Mercados comprovados na imagem:

- Escanteios Asiáticos FT: linha `8`, Mais de `2.000`, Menos de `1.800`.
- 1º Tempo - Escanteios Asiáticos: linha `3`, Mais de `1.850`,
  Menos de `1.950`.

## Regra temporal obrigatória

- Durante o primeiro tempo, a ausência do mercado de escanteios asiáticos do
  segundo tempo significa `ainda_nao_aplicavel`.
- Essa ausência não pode ser registrada como mercado indisponível, rejeitado
  ou não coberto.
- O mercado de segundo tempo somente pode ser avaliado depois do início do
  segundo tempo.
- Uma oferta 2T somente é comprovada quando a tela mostrar o título do período,
  a linha e os dois lados completos: Mais de e Menos de.

## Dados ainda necessários

- URL pública do evento Bet365 contendo `#/IP/EV...`.
- Captura realizada durante o segundo tempo para comprovar o mercado 2T.
- Mais de uma partida real para confirmar que a estrutura não é específica
  desta competição ou deste evento.

