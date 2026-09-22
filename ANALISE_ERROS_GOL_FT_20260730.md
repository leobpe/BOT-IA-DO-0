# Análise de erros — Gol FT sinais-v6

Data do corte: 30/07/2026

## População auditada

- Janela oficial congelada: 100 partidas independentes.
- Desenvolvimento: primeiras 70 partidas.
- Validação cronológica: 30 partidas seguintes.
- Todas as decisões tinham linha válida e precisavam de exatamente mais um gol.
- Não foram encontrados resultados sem linha ou liquidação incompatível.

| Grupo | Amostra | Acerto | ROI hipotético |
|---|---:|---:|---:|
| Desenvolvimento | 70 | 62,9% | +5,5% |
| Validação | 30 | 46,7% | -18,9% |

O resultado piorou fora do período de desenvolvimento. Isso confirma mudança
temporal e falta de generalização, não um simples erro de contagem.

## Falha principal encontrada

A pontuação técnica ficou invertida em relação ao desempenho futuro:

| Faixa da nota | Desenvolvimento | ROI desenvolvimento | Validação | ROI validação |
|---|---:|---:|---:|---:|
| 70–79,9 | 17/25 green (68,0%) | +18,9% | 7/12 green (58,3%) | +5,6% |
| 80–89,9 | 23/36 green (63,9%) | +5,6% | 6/14 green (42,9%) | -28,5% |
| 90–100 | 4/9 green (44,4%) | -31,7% | 1/4 green (25,0%) | -58,5% |

A regra v6 soma pontos de forma monotônica para chutes recentes, chutes no gol
acumulados e pressão. A amostra mostra que valores maiores desses componentes
não produziram maior chance de gol depois da entrada. Em partidas tardias,
atividade acumulada pode refletir o passado do jogo ou já estar incorporada à
odd, em vez de representar vantagem futura.

## Verificações complementares

- Minutos 70–75: ROI de validação de -36,2%.
- Minutos 76–82: ROI de validação de -34,3%.
- Nota igual ou superior a 90: ROI combinado fortemente negativo.
- Odds com idade de até 180 segundos reduziram a perda, mas a validação ainda
  ficou em -9,1%; frescor sozinho não resolve.
- Odd igual ou superior a 2,00 teve ROI positivo nos dois recortes, porém apenas
  21 observações no total. É evidência exploratória pequena e não autoriza
  filtro.
- Não houve corte simples de chutes ou pressão com vantagem consistente e
  amostra suficiente nos dois recortes.

## Ação profissional

1. A regra `sinais-v6` permanece congelada e reprovada para Gol FT.
2. A hipótese `pontuacao_tecnica <= 79,9` será observada somente em partidas
   posteriores a este diagnóstico.
3. A hipótese precisa de pelo menos 30 resultados selecionados e 10 no controle.
4. Além de ROI positivo, o intervalo de 95% do ganho contra o controle precisa
   ficar totalmente acima de zero.
5. Não existe promoção automática. Uma confirmação permitirá desenhar uma nova
   regra pré-registrada, com pesos recalculados e nova validação prospectiva.
6. Se a hipótese falhar, ela será mantida como refutada e não será incorporada.

Esta análise não transforma nota técnica em probabilidade e não representa
garantia de lucro.

## Segunda rodada — 117 resultados independentes

A hipótese inicial de nota até 79,9 foi confrontada com os 17 resultados
posteriores que ainda não haviam participado da descoberta. Ela selecionou 5
casos, com 2 greens, 3 reds e ROI de -38,8%. Portanto, a aparente vantagem da
faixa de nota não se generalizou; a hipótese permanece sombra e tende à
refutação se esse comportamento continuar.

Foi executada uma busca exploratória com cortes simples e combinações de dois
critérios. Para reduzir falsos padrões, um candidato precisava manter ROI
positivo separadamente nos três blocos cronológicos 70/30/17, com cobertura
mínima em cada bloco. Apenas três combinações passaram por esse filtro inicial.

O candidato com maior cobertura foi:

- gols já marcados menor ou igual a 3; e
- chutes totais nos últimos 5 minutos menor ou igual a 3.

| Bloco cronológico | Amostra | Acerto | ROI hipotético |
|---|---:|---:|---:|
| Primeiras 70 | 49 | 63,3% | +2,7% |
| Próximas 30 | 20 | 60,0% | +1,2% |
| Últimas 17 | 8 | 62,5% | +10,8% |
| Total selecionado | 77 | 62,3% | +3,1% |
| Total excluído | 40 | 40,0% | -26,8% |

O delta observado de ROI foi +30,0 pontos percentuais, mas seu intervalo normal
de 95% ficou entre -4,4 e +64,4 pontos. Como o intervalo ainda cruza zero e o
candidato foi escolhido após comparar vários cortes, ele não está confirmado.

O challenger composto
`gol_ft_baixa_saturacao_v1_20260730` foi registrado às 23:41:50 para começar
do zero. Ele exige 30 resultados selecionados, 10 de controle, ROI selecionado
positivo e limite inferior do IC95 do delta acima de zero. Não há promoção
automática.

## Terceira rodada — 191 resultados independentes

Revisão executada em 02/08/2026, após a amostra de Gol FT ultrapassar 180
resultados independentes:

- amostra total: 191;
- acerto: 50,3%;
- ROI hipotético: -14,5%;
- janela cronológica final de 30 casos: 46,7% de acerto e ROI de -17,1%;
- challenger de baixa saturação: refutado após 49 novos casos, ROI de -29,5%;
- score candidato com contexto: ainda inconclusivo; o limite inferior do AUC95
  permanece abaixo do mínimo exigido.

Uma nova busca de cortes simples foi feita somente no bloco de desenvolvimento
e depois conferida nos 30 casos finais. Nenhum corte apresentou evidência
robusta: os melhores resultados aparentes no desenvolvimento perderam a
vantagem ou ficaram com amostra muito pequena na validação. Por isso, nenhum
corte foi promovido como nova regra.

Decisão operacional versionada:

1. avisos de teste de `gol_ft` com `sinais-v6` ficam suspensos;
2. candidatos e resultados continuam registrados internamente para pesquisa;
3. a suspensão não afeta Gol HT, próximo gol, próximo escanteio ou escanteios
   asiáticos FT;
4. uma futura regra de Gol FT usará uma nova versão e validação prospectiva,
   sem reutilizar o resultado antigo como prova;
5. o script somente-leitura `analisar_erros_gol_ft.py` reproduz a auditoria.

## Detector de regime Gol FT/HT

Em 02/08/2026 foi congelada uma nova geração prospectiva do challenger com
contexto API. Gol FT e Gol HT possuem âncoras e contadores independentes. Gol
FT iniciou validação futura em 0/30; Gol HT permanece aguardando treino porque
a amostra contextual ainda é inferior a 60. O challenger não altera alertas,
não promove regras automaticamente e preserva a geração anterior para
comparação e rollback.

## Auditoria ampliada de 03/08/2026

A amostra independente chegou a 208 resultados. A auditoria passou a cruzar
as features temporais com o contexto avançado da API e a identificar
competições por país + liga. Identificadores arbitrários de fixture, time e
liga foram explicitamente excluídos da pesquisa para impedir falso poder
preditivo.

Foram pesquisados cortes simples e combinações, sempre com desenvolvimento
cronológico, estabilidade em três fatias temporais e uma conferência
posterior de 30 resultados. As combinações de maior ROI no desenvolvimento
falharam na conferência posterior e foram descartadas. Nenhuma competição
possui amostra cronológica suficiente para justificar bloqueio por liga.

O único corte simples positivo no desenvolvimento e na conferência posterior
foi **movimento_gols.odd_atual >= 1.66**:

- desenvolvimento: 53 selecionados, 54,7% de acerto e ROI +5,0%;
- estabilidade: duas de três fatias temporais positivas;
- conferência posterior: 7 selecionados, 57,1% de acerto e ROI +6,4%.

Esses números continuam exploratórios. Em 03/08/2026 às 18:40:54 foi
registrado o challenger imutável
**gol_ft_odd_atual_min_166_v1_20260803**. Ele começa do zero, requer 30
resultados futuros independentes, mantém aplicação automática desligada e
só pode ser considerado para promoção se apresentar ROI positivo e intervalo
de 95% favorável contra o grupo excluído.

Por preferência operacional de evitar entradas excessivamente tardias, foi
registrado também o challenger conservador
**gol_ft_odd_166_minuto_max_82_v1_20260803**. O corte no minuto 80 foi
descartado porque teria ROI histórico de -6,3%. Com limite no minuto 82, a
amostra histórica foi de 57 casos, 54,4% de acerto e ROI +2,4%; no
desenvolvimento foram 50 casos e ROI +1,9%, e na conferência posterior foram
7 casos e ROI +6,4%. As duas versões começam prospectivamente e serão
comparadas sem aplicação automática.

## Acompanhamento V3 — hipótese reservada até o fechamento da coorte

Registro em 12/08/2026, com 19 resultados futuros independentes da V3 Gol FT:

- resultado parcial: 8 greens, 11 reds e ROI de -26,74%;
- todos os 19 casos tinham exatamente 1 chute nos últimos 5 minutos;
- com 3 ou mais gols já marcados: 2 greens e 7 reds;
- com menos de 3 gols já marcados: 6 greens e 4 reds;
- entradas no minuto 75 ou depois: 1 green e 4 reds;
- entradas antes do minuto 75: 7 greens e 7 reds;
- pressão, chutes no gol acumulados, nota técnica e odd média não separaram
  greens de reds nessa amostra.

Interpretação provisória: um único chute recente parece confirmação fraca, e
atividade acumulada alta pode refletir o passado de partidas já saturadas, não
necessariamente a chance de outro gol. Placares com 3 ou mais gols e entradas
a partir do minuto 75 concentram erros, mas os cortes foram observados depois
dos resultados e ainda podem ser acaso.

Decisão metodológica:

1. a V3 atual não será modificada nem reaberta;
2. nenhuma dessas observações será usada para bloquear ou liberar sinais;
3. a análise será refeita somente após o fechamento da coorte pré-registrada;
4. se a evidência permanecer, será criada uma nova versão prospectiva, sem
   reutilizar estes 19 resultados como validação;
5. hipóteses reservadas para essa futura versão: evitar minuto 75 ou posterior,
   evitar placar com 3 ou mais gols e exigir atividade recente mais forte que
   um chute isolado;
6. qualquer nova versão continuará somente em sombra, sem Telegram oficial e
   sem promoção automática, até cumprir sua própria política estatística.

Este registro preserva a análise para revisão futura e não representa mudança
na regra em execução nem garantia de desempenho.
