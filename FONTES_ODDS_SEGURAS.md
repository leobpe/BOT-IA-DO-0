# Fontes externas de odds — critérios de aceitação

## Objetivo

Complementar o PackBall sem remover partidas que não existam no provedor e sem
confundir mercados parecidos. Uma nova fonte permanece desligada até comprovar,
com respostas reais de partidas ao vivo, cada mercado que pretende fornecer.

## Situação atual

- Auditoria integral em 09/09/2026: 251.685 registros de odds ao vivo foram
  reprocessados. FT possui 20.917 estruturas asiáticas válidas; 1T possui zero
  asiáticas e 9.163 `Exactly`; 2T possui zero asiáticas e 9.464 `Exactly`.
- API-Football: asiático FT comprovado pelo bet 32, com 7.249 consultas e
  12.498 ofertas anexadas; asiático 1T catalogado no bet 51, mas sem oferta
  real após 222 consultas; asiático 2T não catalogado.
- PackBall: oferece dados e mercados auxiliares, mas o histórico integral não
  comprovou Over/Under asiático de duas opções para 1T ou 2T.
- Bet365: evidência visual manual válida, porém a navegação automática não é
  considerada uma fonte operacional estável.

## Candidatos

### TotalCorner

Documentação: https://www.totalcorner.com/page/api
Preços: https://www.totalcorner.com/page/membership

- HTTPS, JSON e limite documentado de 30 requisições por minuto.
- O endpoint de partidas expõe `cornerLine` e `cornerLineHalf`.
- O histórico de odds expõe `cornerList` e `cornerHalfList`, com linha, duas
  cotações e horário.
- A documentação não comprova uma lista asiática exclusiva do segundo tempo.
- A associação anuncia um dia VIP gratuito após verificação do telefone,
  €5 por um dia ou €28 por 30 dias. A API é descrita como disponível para
  membros VIP, mas o acesso precisa ser confirmado no trial antes de pagar.

Conclusão: primeiro candidato a trial gratuito para FT/1T; 2T continua não
comprovado.

### The Odds API

Documentação: https://the-odds-api.com/sports-odds-data/betting-markets.html

- O plano inicial anuncia 500 créditos mensais gratuitos.
- Documenta `alternate_totals_corners` para totais de escanteios Over/Under e
  `alternate_spreads_corners` para handicap de escanteios.
- A documentação pública não comprova variantes de total de escanteios
  específicas do primeiro ou segundo tempo.
- Mercados adicionais são consultados por partida e podem consumir créditos
  conforme o número de mercados e regiões.

Conclusão: candidato gratuito para comprovar cobertura real de FT; não liberar
1T ou 2T por analogia com mercados genéricos de períodos.

### BetsAPI

Documentação: https://betsapi.com/docs/events/odds.html

- Documenta `1st Half Asian Corners`.
- A documentação pública consultada não comprova o equivalente de 2T.

Conclusão: solicitar amostra real de 1T e 2T antes de contratar.

### AnySport

Documentação: https://docs.anysport.io/football/live-odds/

- Documenta vários mercados de escanteios ao vivo.
- O total específico de 2T mostrado publicamente possui três opções
  (`Over`, `Exactly`, `Under`) e não equivale ao asiático de duas opções.

Conclusão: não usar o mercado de três opções como substituto.

### Betfair Exchange

Documentação: https://developer.betfair.com/exchange-api/

- API oficial com identificação de mercado e atualizações estruturadas.
- A disponibilidade exata de escanteios por tempo precisa ser comprovada em
  partidas e competições reais.
- A chave atrasada é gratuita para desenvolvimento, mas pode entregar snapshots
  com atraso variável de 1 a 180 segundos. A chave ao vivo possui taxa única
  elevada e não é prioridade para este projeto.

Conclusão: possível fonte complementar de pesquisa, inadequada para validação
ao vivo enquanto estiver usando dados atrasados.

### LSports OddsService

Cobertura: https://www.lsports.eu/wp-content/uploads/Market-Coverage-table.pdf
In-play: https://docs.lsports.eu/lsports/products/oddsservice/general/in-play
Liquidações: https://docs.lsports.eu/lsports/integration/message-structure/settlements

- A tabela oficial de cobertura lista `2nd Half Corners Over/Under` para
  prematch, in-play e settlement. Isso faz da LSports o primeiro candidato
  documental encontrado para a lacuna específica de 2T.
- O snapshot oficial identifica `FixtureId`, mercado, provedor e apostas com
  `Id`, `Name`, `Line`, `BaseLine`, `Status`, `Price` e `LastUpdate`.
- A documentação de liquidação confirma status de aposta `3` e o campo
  `Settlement`, mas a página pública não fornece todo o significado dos enums
  de aposta ativa e de resultado necessário para uma integração fail-safe.
- Não há resposta real do pacote contratado nem preço público fixo comprovado
  para a cobertura exata de que o projeto precisa.

Conclusão: candidato prioritário para solicitar amostra/trial, sem compra e sem
ativação. `diagnostico_lsports_escanteios_2t.py` valida o JSON recebido de forma
offline e exige o mapeamento escrito dos enums do pacote. Mesmo após oferta e
liquidação válidas, libera no máximo uma futura integração em sombra.

### Conferência manual Bet365

- Não possui custo adicional nem depende de automação frágil do navegador.
- O bot mantém a fila restrita às oportunidades candidatas; o operador confere
  jogo, período, mercado, linha e odd na página visível.
- A evidência manual não vira fonte automática nem comprova cobertura geral.

Conclusão: fallback atual para oportunidades raras de 1T/2T até uma API
estruturada passar pelo gate.

## Gate obrigatório para um trial

O provedor deve entregar uma resposta JSON real contendo:

1. Identificador estável da partida, nomes dos times e competição.
2. Estado ao vivo, minuto e horário da atualização.
3. Nome ou chave inequívoca do mercado.
4. Período explícito: `FT`, `1T` ou `2T`.
5. Formato de duas opções: `Over` e `Under`.
6. Linha e odd de ambos os lados.
7. Linhas inteiras, meias e, quando oferecidas, quartos asiáticos.
8. Identificação da casa de apostas ou origem agregada.
9. Regras de liquidação para linha inteira e linhas `.25`/`.75`.
10. Limite de requisições, paginação, latência e cobertura de ligas.

## Regras de integração

- Token somente no `.env`; nunca em logs, Telegram ou arquivos de evidência.
- Fonte nova desativada por padrão.
- Resposta incompleta, suspensa ou antiga falha de forma fechada.
- O horário do cabeçalho precisa ser válido; odds e liquidações não podem ser
  antigas, futuras nem aparecer fora da ordem oferta -> settlement.
- `Exactly` e mercados de três opções nunca viram asiático.
- 1T nunca vira 2T por diferença ou inferência.
- A ausência na fonte externa nunca remove um jogo do PackBall.
- Antes da ativação: parser isolado, testes com fixtures, cota diária, cache,
  circuit breaker, proveniência no SQLite e execução em sombra.
