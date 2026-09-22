# Probabilidade individual — diagnóstico de 02/09/2026

## Pedido corrigido

O usuário quer a chance específica de cada entrada baseada na análise do
confronto, incluindo notícias, escalações e jogadores relevantes. Não quer
a taxa média de acerto de um método apresentada como chance da partida.

O cálculo histórico entregue anteriormente não atende a esse pedido. O novo
protótipo permanece **somente para avaliação offline**, sem importação no
monitor/gateway e sem alteração de métodos, odds, filtros ou Telegram.

## O que está disponível de verdade

O coletor da API-Football consulta `/fixtures/lineups` e `/injuries`. A ausência
de escalação não significa titulares confirmados. O seletor da pré-live já
tem um bloco de jogadores-chave, mas isso não implica que todos os snapshots
ao vivo contenham o mesmo enriquecimento.

Nos 20 últimos sinais HT/FT entregues no corte da consulta:

- 5 tinham as duas escalações confirmadas; 15 não tinham ambas confirmadas.
- 20 indicavam cobertura do endpoint de desfalques. Isso não prova que o
  relatório seja completo nem quantifica o impacto de cada ausência.
- Nenhum tinha bloco `jogadores_chave` nos snapshots ao vivo.
- Nenhum tinha notícias registradas. A busca nos módulos Python operacionais
  também não encontrou um coletor de notícias.

IDs auditados: 326883, 326602, 326508, 326308, 326297, 326285, 326000, 325982,
325976, 325931, 325916, 325659, 325636, 325619, 325608, 325470, 325012, 324997,
324329, 323826.

## Primeiro teste numérico — não aprovado

Antes do esclarecimento sobre notícias foi testado um protótipo logístico
com os dados observados no momento de cada entrada: minuto, placar, linha,
odd, ataque contra defesa, H2H e atividade recente quando disponível.
Modelos separados para HT/FT, treinados com entregas reais; primeira entrada
por partida, sem sombra não entregue e sem dados posteriores à decisão.

| Mercado | Base utilizável | Validação posterior | Brier modelo | Brier média do treino | Brier 1/odd bruta | Erro agregado de calibração |
|---|---:|---:|---:|---:|---:|---:|
| HT | 160 | 32 (13 greens) | 0,2806 | 0,2730 | 0,2397 | 0,2061 |
| FT | 227 | 46 (34 greens) | 0,2353 | 0,2364 | 0,2022 | 0,2007 |

Brier menor é melhor; a odd bruta contém margem e serve somente como
referência, não como verdade. O limiar de erro agregado fixado antes do teste
era 0,15: ambos falharam. Não afrouxar esse limiar para conseguir publicar um
número. As métricas são retrospectivas, sujeitas a revisões dos resultados
registrados; não constituem validação prospectiva imutável.

Cobertura: xG realmente recente em apenas 6/160 registros HT e 16/227 FT.
Pressão recente em 66/160 HT e 187/227 FT. Ausência permanece ausente; não
substituir pelo acumulado ou por zero. Features com cobertura insuficiente
não são utilizadas pelo ajuste. Nenhuma destas probabilidades experimentais
foi enviada ao usuário ou ao canal como chance validada.

## O que falta para a análise completa

1. Incorporar notícias verificadas com URL, publicação, horário de leitura,
   identificação inequívoca do jogo/time e fatos confirmados. Rumor e notícia
   antiga devem permanecer separados; não converter sentimento de uma
   manchete em pontos percentuais arbitrários.
2. Confirmar ambas as escalações e relacionar desfalques/titulares à
   participação efetiva dos jogadores: posição, minutos, gols/assistências
   ou outras métricas pertinentes. Somente contar nomes não mede impacto.
3. Registrar essa informação antes da entrada e avaliar a influência em
   resultados posteriores. Não preencher notícias/escalacões antigas com
   informações descobertas depois do resultado para “melhorar” o backtest.
4. Validar novamente em uma amostra futura reservada. Este primeiro holdout
   já foi observado e não poderá ser chamado de teste independente após
   ajustes orientados por seus resultados.

Escopo adicional de pré-live/cantos foi perguntado ao usuário; não foram
ativados novos mercados. Os sinais ao vivo atuais seguem com os critérios
anteriores. O percentual atualmente ativo continua sendo histórico, não a
probabilidade individual completa solicitada.

## Verificação de código

49 testes direcionados aprovados, incluindo diferenciação por tempo/linha,
dados ausentes, separação de mercados, corte temporal, deduplicação e recusa
de modelo mal validado. Estes testes verificam a implementação; não provam
a qualidade preditiva do modelo. Sem reinício necessário, porque nenhum
arquivo operacional importado foi alterado neste protótipo.
