# Operação do Bot PackBall

## Estado esportivo sem mistura de odds V110 — 13/09/2026

A coorte prospectiva fixa revelou uma lacuna objetiva: entre as cinco primeiras
partidas instrumentadas, duas entradas tinham cotação de origem PackBall e eram
ignoradas pela fotografia rápida porque a coleta exigia Bet365 até para observar
placar, gol ou escanteios. Isso reduzia a cobertura futura sem tornar a entrada
inválida.

A V110 separa estado esportivo de preço executável. Para uma entrada PackBall,
a API-Football pode confirmar placar, minuto, status e escanteios entre dois e
dez minutos depois do alerta, no modo `somente_estado`. Nenhuma odd futura de
outra fonte é anexada. Para entradas BetsAPI/Bet365, continua sendo exigida a
mesma linha, fonte e bookmaker no modo `estado_e_preco`.

Com isso, gols e encerramentos HT/FT antes da fotografia seguinte podem ser
liquidados pelo evento real, inclusive quando não existe preço futuro comparável.
Contratos que continuam abertos sem a mesma odd futura permanecem excluídos da
análise de movimento de preço. A mudança reduz perda de resultados e viés de
sobrevivência, mas não infla a taxa nem mistura casas.

A evidência de estado passou para V3, a coleta para V4, a avaliação para V26
e a custódia para V15. O auditor também confronta fonte e bookmaker registrados
no estado com os dados imutáveis do sinal. O watchdog verifica que toda unidade
`somente_estado` pertence ao subconjunto sem oferta futura.

A camada segue estritamente observacional: não altera filtros, HT, FT, entrada,
probabilidade ou Telegram. Passaram 660 testes integrados e 2.766/2.766 na
regressão completa. A auditoria real V26/V15 verificou 11.714 observações,
permaneceu saudável e encontrou zero problema de integridade antes da retomada.

Na retomada, os PIDs reais ficaram em 29472, 45124 e 48792 para monitor,
watchdog e pré-live. As três travas ficaram ocupadas e os hashes do monitor e
do watchdog coincidiram com os arquivos testados. O trabalhador publicou a
coleta V4 ativa, íntegra, sem falhas e com efeitos em sinais/Telegram desligados.

O primeiro ciclo V110 terminou às 00:45:06 em 125,804 segundos: três partidas,
três tarefas agendadas e processadas, três jogos pareados/consultados na
BetsAPI e dez mercados anexados. A lista ficou consistente, sem adiamento,
falha de rede ou pausa. O ciclo seguinte terminou às 00:45:30 e foi reconhecido
pelo watchdog, que permaneceu saudável, sem falhas consecutivas e com V4 íntegra.

## Desfecho rápido por contagem de escanteios V109 — 13/09/2026

A fotografia feita entre dois e dez minutos após um alerta agora guarda também
a contagem de escanteios entregue no mesmo payload detalhado da API-Football.
Não há uma chamada de rede adicional. A orientação casa/fora é conferida, e os
dois contadores precisam ser inteiros e não negativos antes da persistência.

Nos escanteios asiáticos FT, isso elimina uma lacuna importante: se novos
cantos ultrapassarem a linha antes da próxima varredura PackBall, a avaliação
registra o contrato como liquidado pelo evento real. Se a linha continuar
aberta, a mesma cotação futura Bet365 ainda é usada para medir o movimento de
preço. Assim, mercados que somem logo depois de um canto deixam de desaparecer
da amostra e de produzir uma taxa enviesada pelos contratos sobreviventes.

A evidência de estado passou para V2 e a coleta para V3; registros V1 antigos
continuam legíveis. O SQLite mantém vínculo exato com sinal, partida, mercado,
linha e horário, hash SHA-256 e imutabilidade. O próximo escanteio permanece
declarado como `somente_snapshot`, pois não há cotação rápida independente para
esse contrato; a V109 não fabrica preço nem amplia a origem aceita.

Esta camada continua somente observacional. Não gera ou bloqueia sinais, não
envia Telegram e não muda HT, FT, filtros, probabilidades ou calibração.
Passaram 658 testes integrados e 2.763/2.763 na regressão completa. A auditoria
real V25/V14 verificou 11.711 observações, permaneceu saudável e encontrou zero
problema de integridade antes da retomada.

Na retomada, os PIDs reais foram 47008, 34620 e 42368, com as três travas
ocupadas e os hashes do monitor e watchdog idênticos aos arquivos testados. O
trabalhador publicou a V3 ativo, cobertura dos mercados íntegra, zero falha e
efeitos em sinais/Telegram desativados.

O primeiro ciclo V109 terminou às 00:22:54 em 185,418 segundos: cinco partidas,
cinco tarefas agendadas, quatro processadas, três pareamentos Bet365 e dez
mercados anexados. A lista ficou consistente, a API saudável, sem falha de rede
e sem pausa preventiva. Às 00:24:39, o watchdog já reconhecia um ciclo posterior
e permanecia saudável, com zero falha consecutiva e a coleta CLV V3 íntegra.

## Cobertura pós-alerta dos mercados de escanteios V108 — 12/09/2026

A coleta rápida de movimento de preço agora inclui também a linha asiática FT
de escanteios. Ela procura exatamente a mesma linha Bet365 enviada no alerta e
só aceita a fotografia quando Over e Under pertencem ao mesmo mercado, evento
e instante válidos. Não troca 8,5 por 9,5, não escolhe outra casa e não completa
um lado ausente por inferência.

O mercado de próximo escanteio continua sendo acompanhado pelos snapshots do
PackBall. A BetsAPI não oferece esse contrato e, por isso, ele aparece
explicitamente como `somente_snapshot`; apresentar essa limitação é mais seguro
do que declarar uma falsa cobertura rápida.

O trabalhador publica a versão V2 com quatro mercados rápidos — gol FT, gol
HT, próximo gol e escanteios FT asiático — e um mercado por snapshot — próximo
escanteio. O watchdog confere essa composição exata e rejeita telemetria que
omita, duplique ou misture os grupos. A coleta permanece observacional: não
gera sinais, não envia Telegram e não altera filtros ou calibração.

Passaram 681 testes focados e 2.763/2.763 na regressão integral. A auditoria
real V24/V13 confirmou os cinco mercados, custódia saudável e zero efeito
operacional. Monitor, watchdog e pré-live foram retomados com PIDs reais,
três travas e hashes correspondentes ao código testado. O trabalhador V2
iniciou saudável, com a cobertura declarada completa e sem falhas.

O primeiro ciclo V108 terminou às 23:55:11 com 12 partidas, 12 tarefas
agendadas, 6 processadas, 6 pareamentos Bet365 e 16 mercados anexados, sem
falha de rede.

Na supervisão persistida às 23:56:59, o watchdog já reconhecia um ciclo V108
posterior, permanecia saudável, com zero falha consecutiva e sem pausa. O
trabalhador rápido continuava ativo, com cobertura dos mercados íntegra, zero
falha CLV e nenhum efeito sobre sinais ou Telegram.

## Movimento da odd após o alerta V107 — 12/09/2026

O sistema agora revisita, de forma independente, cada sinal de gol realmente
entregue e procura a mesma cotação Bet365 entre dois e dez minutos depois do
envio. A comparação mostra se a entrada antecipou o mercado — odd posterior
menor — ou se o preço se moveu repetidamente contra o alerta. Essa evidência
serve para calibrar filtros futuros com dados reais; não é garantia de green
nem uma nova condição esportiva aplicada imediatamente.

A fotografia guarda o estado validado pela API-Football mesmo quando a linha
já não está disponível. Assim, uma partida encerrada sem o gol necessário
continua aparecendo como red, em vez de sumir por falta de cotação futura. Se
a consulta falhar tecnicamente, o item permanece pendente para nova tentativa
e não é registrado como mercado ausente.

Todo o registro é vinculado ao sinal, mercado, linha e partida exatos e fica
imutável no SQLite. A avaliação V23 audita essa cadeia e identifica a origem
da medição. A coleta não cria sinal, não envia Telegram e não muda HT, FT,
próximo gol, escanteios, pré-live, filtros, aprovação ou calibração. Uma falha
da medição fica isolada e visível no watchdog sem interromper os alertas.

Passaram 2.758/2.758 testes e a auditoria na base real não encontrou problema
de integridade. Monitor, watchdog e pré-live foram retomados com hashes atuais,
três PIDs e três travas corretas. A coleta rápida está ativa, sem falhas, e o
estado inicial `sem_candidatos_na_janela` é esperado até surgir um alerta de
gol elegível entre dois e dez minutos após a entrega.

O primeiro ciclo V107 terminou às 23:32:54 com 16 partidas, 16 tarefas
agendadas, 7 processadas, 6 pareamentos Bet365 e 14 mercados anexados, sem
falhas de rede. Às 23:34:07, o watchdog reconhecia esse ciclo como saudável,
sem falhas consecutivas ou pausa preventiva; o trabalhador rápido e sua coleta
CLV também estavam saudáveis e sem qualquer efeito sobre sinais ou Telegram.

## Proveniência reproduzível da vantagem histórica V106 — 12/09/2026

Uma fotografia histórica íntegra só é aceita se também puder ser reproduzida
a partir do SQLite. Na leitura, o sistema recarrega o sinal de origem, confirma
coorte, relógio causal, janela e cotação executável BetsAPI/Bet365 e recalcula
toda a população anterior ao alerta. O conteúdo canônico recalculado deve ser
idêntico ao congelado. Portanto, trocar os números e gerar outro hash válido
não consegue fabricar taxa, ROI ou vantagem robusta.

A verificação ocorre tanto antes de apresentar uma fotografia quanto na
auditoria contínua do watchdog. Uma divergência remove somente a análise
histórica da mensagem e torna a auditoria não saudável; não altera filtros,
geração, aprovação, calibração, HT, FT, escanteios, pré-live ou o Telegram.

Passaram 53 testes focados, 464 integrados e 2.750/2.750 na regressão integral.
Monitor, watchdog e pré-live foram retomados com hashes atuais e as três travas
corretas. O primeiro ciclo V106 terminou às 22:53:54 com 28 partidas, 28 tarefas
agendadas, 8 processadas, 6 pareamentos Bet365 e 17 mercados anexados, sem
falhas de rede. A supervisão seguinte reconheceu o ciclo, permaneceu saudável,
sem pausa, e confirmou os nove gatilhos. O auditor está em `sem_registros`,
estado esperado até o próximo alerta elegível criar a primeira fotografia V4.

## Robustez temporal e risco do histórico executável V105 — 12/09/2026

O histórico financeiro agora diferencia quantidade de entradas de quantidade
de dias realmente independentes. Além do intervalo t por entrada, a fotografia
V4 calcula um intervalo de ROI com variância robusta CR1 agrupada por dia.
Assim, muitos sinais correlacionados em uma mesma rodada não criam confiança
artificial.

Cada unidade congelada inclui partida, liga e horário de envio. O alerta pode
mostrar dias e ligas distintos, ROI da metade antiga e recente, maior sequência
de reds e drawdown máximo. O rótulo de vantagem histórica robusta exige, ao
mesmo tempo: pelo menos 30 entradas, 10 dias distintos, limite inferior acima
de zero nos dois intervalos de ROI e retorno positivo nas duas metades do
histórico. Falhar qualquer prova mantém a conclusão inconclusiva ou
desfavorável; nunca vira probabilidade individual nem autorização de entrada.

V2 e V3 foram preservadas e V4 recebeu três novos bloqueios SQLite, totalizando
nove gatilhos íntegros. Passaram 52 testes focados e 2.749/2.749 na regressão
integral. Nenhum filtro, geração, aprovação, calibração ou frequência de HT,
FT, próximo gol, escanteios e pré-live foi alterado.

Monitor, watchdog e pré-live foram retomados com hashes atuais e as três travas
corretas. O primeiro ciclo V105 terminou às 22:35:22 com 30 partidas, 28 tarefas
agendadas, 8 processadas, 7 pareamentos Bet365 e 21 mercados anexados, zero
falha de rede e circuitos fechados. A supervisão seguinte reconheceu esse ciclo,
permaneceu saudável, sem falhas consecutivas ou pausa preventiva, e confirmou
a custódia V2/V3/V4 em nove de nove gatilhos.

## Rentabilidade histórica executável V104 — 12/09/2026

A taxa de acertos deixou de ser tratada como prova financeira. Um método pode
ter muitos greens e ainda perder dinheiro se as odds dos greens forem baixas.
Para cada alerta novo, a fotografia V3 usa somente resultados de sinais
realmente enviados e a odd executável congelada da BetsAPI/Bet365. O retorno
de uma unidade é conferido como `odd - 1` no green e `-1` no red; liquidações
inconsistentes são excluídas e contabilizadas.

A apresentação agora informa unidades acumuladas, ROI histórico, odd média
realmente executada e intervalo de confiança de 95% de Student. Com menos de
30 liquidações, a conclusão é obrigatoriamente “amostra inicial/inconclusiva”.
Mesmo depois disso, só existe indicação histórica positiva quando o limite
inferior do intervalo de ROI está acima de zero. A odd atual continua visível
como referência de preço de equilíbrio, não como uma comparação capaz de
fabricar vantagem nem como chance individual calibrada.

A V2 permanece imutável e a V3 ganhou o mesmo conjunto de três proteções
SQLite, totalizando seis gatilhos íntegros. Passaram 589 testes direcionados e
2.746/2.746 na regressão completa. Nenhum filtro, aprovação, calibração ou
frequência de sinal HT, FT, próximo gol, escanteio ou pré-live foi alterado.

Monitor, watchdog e pré-live foram retomados com os hashes atuais e as três
travas corretas. O primeiro ciclo V104 terminou às 22:13:03 com 34 partidas,
28 tarefas agendadas, 8 processadas, 7 pareamentos Bet365 e 20 mercados
anexados. A supervisão reconheceu o ciclo, permaneceu saudável, com zero
falhas consecutivas, sem pausa preventiva e custódia íntegra em seis de seis
gatilhos.

## Custódia nativa da taxa histórica V103 — 12/09/2026

O hash V102 continua validando o conteúdo, mas agora a fotografia histórica
também recebe proteção nativa do SQLite. Cada chave
`probabilidade_acertos:v2:sinal:*` pode ser inserida uma única vez; três
gatilhos impedem atualização, exclusão e substituição posterior. Isso evita
que conteúdo e hash sejam trocados juntos por uma gravação normal no banco.

A leitura e a criação de uma fotografia falham fechadas se qualquer gatilho
estiver ausente ou tiver definição divergente. O watchdog confere presença e
semântica continuamente. A falha continua limitada à apresentação da taxa:
não altera filtros HT/FT, aprovação, calibração, Telegram nem resultados.

Passaram 632 testes direcionados e integrados e 2.743/2.743 na regressão
completa. A base real foi migrada com os três gatilhos íntegros, 33 tabelas
compatíveis, nenhum item obrigatório ausente e zero violação de chave
estrangeira. Monitor, watchdog e pré-live foram retomados com hashes e travas
atuais. O primeiro ciclo V103 terminou às 21:50:23 com 35 partidas, 7 tarefas
processadas, 4 pareamentos Bet365 e 10 mercados anexados, sem falhas de rede,
bloqueios de fonte ou pausa preventiva. A supervisão seguinte reconheceu o
novo sucesso e manteve a custódia saudável.

## Integridade imutável da taxa histórica V102 — 12/09/2026

Cada nova fotografia da taxa histórica executável é selada antes do primeiro
POST ao Telegram. A política V2 inteira possui SHA-256 próprio e o conteúdo
congelado recebe outro hash canônico. Antes de exibir ou reutilizar a taxa em
uma edição de green/red, o sistema confere versão, política, fonte/casa,
população, greens, reds, IDs independentes, taxa observada e a conta
Beta(1,1). Qualquer divergência faz a apresentação falhar fechada; o alerta e
os critérios esportivos continuam intactos, mas nenhum percentual suspeito é
mostrado.

O watchdog passou a auditar os registros persistidos e torna a supervisão não
saudável se encontrar hash adulterado, vínculo com outro sinal ou origem
ausente. A auditoria inicial encontrou zero V2, estado correto porque ainda
não houve um novo envio após a mudança; mensagens V1 permanecem históricas e
não são reinterpretadas. Passaram 348 testes integrados e 2.740/2.740 na
regressão integral.

Monitor, watchdog e pré-live foram retomados às 21:23 com os hashes atuais e
as três travas de instância corretas. O primeiro ciclo V102 terminou às
21:28:21 com 38 partidas, 8 tarefas processadas, 6 pareamentos Bet365 e 18
mercados anexados. A API permaneceu saudável, sem falhas de rede, bloqueios de
fonte ou pausa preventiva. Na supervisão seguinte, o watchdog reconheceu esse
novo sucesso e manteve a auditoria das estimativas saudável em `sem_registros`.

## Taxa histórica exibida alinhada à execução V101 — 12/09/2026

A taxa descritiva apresentada nos alertas agora usa o mesmo universo da
entrada executável. Cada green ou red precisa vir de uma entrega anterior do
mesmo método cuja fotografia congelada V2 comprove integralmente a oferta
BetsAPI/Bet365. Uma odd PackBall, API-Football, de outra casa, sem os dois
lados ou com prova adulterada é excluída antes da independência por partida.

Mensagens antigas e seus números V1 foram preservados. Novos alertas usam uma
chave V2 separada: se a cotação atual não for Bet365 executável, a mensagem
informa que não há histórico comparável; se for executável, mas houver menos
de cinco resultados anteriores da mesma coorte, informa a amostra
insuficiente. Só depois disso mostra a taxa Beta(1,1), a base Bet365 e o
intervalo de incerteza. O número continua rotulado como histórico e nunca
como chance individual calibrada.

Na auditoria real, o último próximo gol Bet365 tinha zero resultados exatos
comparáveis. Um método de Gol HT tinha somente 1 e excluiu corretamente 30
entregas antigas incompatíveis. Portanto, o antigo placar misto deixa de
sustentar uma porcentagem aparentemente precisa no novo alerta. A mudança é
somente de mensuração e apresentação; não afrouxa filtros, não altera HT/FT e
não promove estratégias. Passaram 146 testes direcionados e 2.737/2.737 na
regressão integral.

Monitor, watchdog e pré-live foram retomados com hashes carregados iguais aos
arquivos atuais e travas exclusivas ocupadas. O primeiro ciclo V101 terminou
às 21:09:33 com 38 partidas e 8 tarefas processadas; todas tinham odds
utilizáveis e todas receberam cobertura BetsAPI/Bet365. As 20 tarefas
restantes foram adiadas pela reserva normal de duração do ciclo. A API ficou
saudável, sem falha de rede, bloqueio de fonte ou pausa preventiva. O
watchdog reconheceu esse sucesso e acompanhou o início normal do ciclo
seguinte.

## Calibração alinhada à execução Bet365 V100 — 12/09/2026

A calibração oficial deixou de aprender com uma mistura de preços que o
usuário talvez não consiga executar. A política V11 admite somente sinais
aprovados cuja fotografia congelada V2 comprove a oferta BetsAPI/Bet365
exata. Fonte, casa, mercado, linha ou seleção, odd escolhida, par completo,
horário, cache e origem são revalidados antes de qualquer resultado entrar na
amostra.

Esse filtro acontece antes da escolha da primeira exposição por partida.
Assim, uma leitura PackBall ou API-Football anterior não elimina uma Bet365
válida observada depois. A prova da cotação participa do fingerprint da
amostra; adulteração, divergência ou falta de custódia falha fechado. O mesmo
contrato passou a orientar o progresso, a diversidade, o corte cronológico,
o frescor, o preflight, o watchdog e a aplicação da probabilidade ao próximo
candidato.

A auditoria da base mostrou por que isso importa: a regra atual de próximo
gol tinha 9 partidas resolvidas, mas somente 1 com prova executável completa;
próximo escanteio tinha 30 de fonte mista e nenhuma executável; escanteios FT
tinha 39 e nenhuma executável. Esses históricos continuam disponíveis para
pesquisa, mas não podem ativar um modelo oficial. A frequência inicial pode
cair; a melhoria é eliminar confiança aparente obtida em um universo de odds
diferente daquele em que a entrada seria feita. Passaram 427 testes
integrados e 2.734/2.734 na regressão completa.

Monitor, watchdog e pré-live foram retomados com hashes e travas atuais. O
primeiro ciclo real V100 terminou às 20:50:16, saudável: 54 partidas, 9
tarefas detalhadas e odds utilizáveis nas 9; 8 vieram da BetsAPI/Bet365 e 1
permaneceu apenas como observação PackBall. Não houve falha de rede, bloqueio
de fonte nem pausa preventiva. A calibração V11 segue corretamente
desativada: há 1 resultado executável de próximo gol e ainda são necessários
100 resultados por regra antes da avaliação para uma possível ativação.

## Coorte executável de escanteios FT V99 — 12/09/2026

A validação que pode autorizar escanteios FT agora mede exatamente o universo
que o usuário consegue executar. A nova V3 admite somente um candidato cuja
fotografia congelada comprove a oferta BetsAPI/Bet365, incluindo mercado,
linha, odd Over, odd Under, horário, idade, cache e identidade de origem. Uma
odd agregada ou de casa desconhecida continua útil para observação, mas não
ocupa a coorte nem prova vantagem oficial.

A V2 anterior foi preservada sem alteração para comparação diagnóstica. Ela
deixou de participar da decisão do portfólio e do circuit breaker. Toda
exclusão por custódia passa a ser registrada em tabela própria com motivo,
conteúdo canônico e hash; os membros aceitos também são revalidados a cada
leitura. Qualquer divergência falha fechado. A V3 mantém o protocolo forte de
100 partidas, desenvolvimento 70/holdout 30, checkpoint em 25, retorno
asiático completo e referência sem vig. Não há promoção automática.

O status e o watchdog mostram separadamente a V3 executável e a V2 legada.
Passaram 428 testes integrados e 2.732/2.732 na regressão integral. O preflight
aprovou a retomada, a âncora causal foi registrada às 20:15:53 e monitor,
watchdog e pré-live ficaram ativos com hashes atuais e travas ocupadas. O
primeiro ciclo V99 terminou às 20:21:27 com 48 partidas, 9 tarefas detalhadas
e 19 adiadas pela reserva segura, sem falha de rede, bloqueio de fonte ou
pausa preventiva. O snapshot das 20:22:19 confirmou a V3 saudável, vazia,
com zero violação e aguardando a primeira amostra executável futura.

## Custódia executável no gateway oficial V98 — 12/09/2026

Uma entrada oficial agora precisa provar não só que a odd é recente e que o
modelo tem valor esperado, mas também que o preço pertence à casa executável
adotada pelo sistema. A única combinação autorizada é BetsAPI/Bet365. A prova
é a fotografia V2 congelada no instante da decisão e precisa coincidir com o
candidato em mercado, linha ou seleção, odd escolhida, todos os lados,
bookmaker, fonte, horário, idade, cache e identidade do mercado.

PackBall, API-Football e outras casas continuam formando histórico e
simulações. Elas deixam de poder sustentar uma futura entrada oficial quando
não representam a mesma cotação disponível na Bet365. Essa separação evita
que um ROI aparente de preço agregado seja tratado como vantagem executável.
O gate é fail closed e registra `cotacao_oficial_nao_executavel`; nenhuma
cotação é inferida e nenhum fallback histórico é aceito.

O status mostra a política, os casos aptos, os bloqueados e os bloqueios reais
do gateway. Na primeira auditoria, não havia sinal simultaneamente aprovado,
calibrado e criado sob o marcador novo, logo nenhum alerta existente foi
retirado retroativamente. As simulações permanecem livres para acumular
evidência. Passaram 362 testes relacionados e a regressão integral final
aprovou 2.728/2.728 testes.

O preflight transacional aprovou a retomada. O primeiro snapshot do watchdog
após o início registrou corretamente o monitor ainda aguardando supervisão; o
snapshot seguinte se recuperou para saudável sem reinício. Monitor, watchdog
e pré-live ficaram ativos com hashes atuais e travas ocupadas. O primeiro
ciclo V98 encerrou às 19:56:03 com 45 partidas, 8 tarefas processadas e 21
adiadas pelo orçamento seguro, API saudável, zero falha de rede/cache, zero
bloqueio de fonte e nenhuma pausa preventiva.

## Funil causal do HT antecipado preciso V51 — 10/09/2026

A prontidão profissional agora distingue falta de geração de oportunidades,
rejeição pelo filtro e entrada efetiva na coorte do HT antecipado preciso. O
funil conta decisões e partidas independentes, registra todos os motivos de
rejeição e destaca o gargalo atual por partida. A leitura é estritamente
causal: não consulta resultados nem entregas, não altera sinais ou Telegram e
não promove qualquer rota automaticamente.

Na base real após a âncora, havia uma decisão do gerador em uma única partida,
nenhum candidato elegível e um único bloqueio:
`chutes_no_gol_insuficientes`. Assim, o zero da coorte não representa centenas
de partidas rejeitadas e não justifica afrouxar o filtro com base em uma
observação. O FT principal continua em `sinais-v6`, sem mudança de regra.

Passaram 593 testes relacionados, incluindo validação, prontidão, monitor e
watchdog. Após a retomada controlada, monitor, watchdog e pré-live ficaram
ativos. O acesso PackBall se recuperou da pausa e o ciclo das 23:16 processou
as três partidas agendadas, sem adiamentos, sem falha de API, sem bloqueio de
fontes e sem pausa preventiva.

## Separação explícita entre experimento e entrada V50 — 10/09/2026

Alertas sem probabilidade individual calibrada enviados ao grupo de teste
agora começam com `ANÁLISE EXPERIMENTAL — NÃO É ENTRADA`. A liquidação desses
itens também passou a usar `GREEN/RED DA SIMULAÇÃO` e `Retorno hipotético`,
impedindo que resultado de pesquisa seja confundido com desempenho ou ROI
oficial. A rota, os filtros, os limites e os canais não foram alterados.

Quando existe histórico congelado antes do envio, a mensagem identifica a
taxa como pertencente ao método, não ao jogo, e compara a odd com seu ponto de
equilíbrio bruto. Também informa a margem histórica em pontos percentuais e o
intervalo de Wilson de 95%; se o intervalo inclui o equilíbrio, o valor é
rotulado como inconclusivo. Isso evita transformar uma diferença mínima entre
taxa passada e odd em edge inexistente.

A reconstrução do alerta de `12 de Junio VH x Atlético Tembetary` mostrou
67,1% para o método, equilíbrio de 66,7% na odd 1,50, margem de apenas +0,46
p.p. e intervalo de 56,1% a 77,3%; portanto, valor inconclusivo. Passaram 317
testes relacionados. Após reinício controlado, monitor, watchdog e pré-live
voltaram com o novo código e o primeiro ciclo real concluiu às 19:50:49 com
14 partidas, nove tarefas processadas, zero falha de API e nenhuma pausa
preventiva.

## Custódia independente das fontes de odds V49 — 10/09/2026

O watchdog passou a validar explicitamente o contrato dos dois recortes
assíncronos de preço: observacional executável e convergência prospectiva.
Além da versão V12 e da integridade das comparações, cada recorte precisa
informar contagens coerentes por fonte e por origem, usar apenas os
armazenamentos autorizados, preservar a Bet365 como bookmaker executável e
exigir contraparte independente. Qualquer ausência, adulteração ou soma
inconsistente falha fechado como `contrato_fontes_invalido`.

O status operacional agora mostra essas fontes, origens e a decisão do
contrato. A alteração continua exclusivamente observacional: não promove
estratégia, não altera filtros, não envia Telegram e não usa uma única fonte
como prova de desajuste. Foram aprovados 22 testes direcionados, 656 testes
integrados e os 177 módulos isolados do preflight.

Na retomada autorizada, uma primeira abertura restrita do navegador recebeu
`WinError 5`; a tentativa parcial foi interrompida com monitor, watchdog e
pré-live encerrados, sem autorreinício. O reinício seguinte recebeu a
permissão correta, abriu o PackBall sem retry e concluiu às 18:14 o primeiro
ciclo: 12 partidas, cinco tarefas detalhadas, zero falhas e nenhuma pausa
preventiva. Às 18:14:43 o watchdog confirmou sistema saudável, avaliação V12
saudável e contrato de fontes íntegro.

## Retomada idempotente de resultados asiáticos V48 — 10/09/2026

A retomada transacional bloqueou corretamente o monitor ao encontrar uma
tentativa repetida de reabrir um resultado de escanteios FT asiáticos. O item
já havia sido recuperado como `void` mediante total estável desde uma leitura
tardia, apta e multifonte, três ou mais fechamentos PackBall ao longo de dez
minutos e duas confirmações finais independentes da API-Football. A rotina de
reabertura reconhecia como terminal apenas o caminho equivalente que acabava
em `green`, criando um ciclo `sem_dado -> void -> reabertura`.

A classificação agora preserva qualquer resultado produzido exatamente por
essa evidência terminal forte quando o snapshot de liquidação está em
`PEN/AET`. Uma observação genérica, uma fonte única ou um texto incompleto não
ganham essa exceção. Nenhum registro histórico foi apagado ou reescrito: as
revisões anteriores continuam append-only e o `void` confirmado foi mantido.

Foram aprovados 113 testes direcionados e a regra foi validada também numa
cópia do banco de produção, com zero reaberturas. O preflight integral aprovou
a retomada. Monitor, watchdog e pré-live iniciaram às 15:34, e o watchdog
confirmou o sistema saudável, sem alerta, enquanto o primeiro ciclo processa
normalmente a lista ao vivo.

## Referência assíncrona de odds nos snapshots V47 — 10/09/2026

A avaliação de desajuste de preço passou para
`avaliacao-desajuste-odds-prospectiva-v12`. A auditoria real encontrou 125
leituras rápidas válidas da Bet365 em seis partidas, mas nenhuma contraparte
de gols na mesma linha: as 125 exclusões `sem_referencia_mesma_linha` eram
ausência real de uma segunda fonte, não diferença de nome ou arredondamento.
Por isso o sistema continua proibido de inventar referência ou relaxar a
igualdade de linha.

Também foi corrigido um ponto de observabilidade: referências independentes
que já estavam preservadas na tabela de snapshots não eram lidas pelo recorte
assíncrono. A V12 agora une, somente em memória, a trajetória append-only da
bookmaker executável com contrapartes dos snapshots. O pareamento exige mesma
partida, mercado, período, linha, lado, placar e minuto compatível, além de
fonte independente; outra bookmaker entregue pelo mesmo provedor não vale
como confirmação. A origem e a contagem por fonte ficam explícitas no estado.

O recorte observacional iniciou a chave V5 e a convergência de preço iniciou
`convergencia-preco-bet365-prospectiva-v3`, ambas com âncoras novas e sem
backfill. Nenhum sinal, filtro oficial ou mensagem Telegram é alterado por
essas coortes. Foram aprovados 20 testes específicos e 523 testes integrados,
incluindo recuperação de referência do snapshot, separação entre over/under e
rejeição de uma contraparte oriunda da mesma fonte.

## Auditoria automática dos relógios de coorte V46 — 10/09/2026

O preflight agora executa `auditoria-relogios-coortes-v1` e bloqueia a retomada
se o formato temporal do armazenamento divergir do contrato de cada pipeline.
Para sinais ao vivo, as 200 linhas recentes precisam continuar em horário
local sem offset e as quatro coortes atuais precisam manter âncora UTC auditável
mais o relógio local de seleção. Para pré-live, os bilhetes V12 e sua âncora
precisam continuar em UTC com offset.

A auditoria é somente leitura e não altera sinais, bilhetes, filtros ou
Telegram. No banco real, as quatro coortes ao vivo passaram íntegras, assim
como os 200 sinais amostrados e os 152 bilhetes pré-live V12. Foram aprovados
cinco testes específicos de adulteração/formato e 42 testes combinados com o
preflight, incluindo a prova de que uma inconsistência impede o reinício. O
PackBall permaneceu ativo e saudável durante essa instalação.

## Relógio causal das coortes HT, FT e escanteios asiáticos V45 — 10/09/2026

As validações prospectivas do HT antecipado preciso, FT antecipado preciso e
escanteios FT asiáticos passaram para V2. A auditoria encontrou que as âncoras
V1 eram gravadas em UTC com offset, enquanto `sinais.criado_em` é gravado no
relógio local sem offset. A comparação direta no SQLite era conservadora, mas
começava a seleção aproximadamente quatro horas depois do instante declarado.

Cada V2 agora congela dois instantes coerentes: `registrado_em` em UTC com
offset para auditoria e `registrado_em_relogio_sinais` no mesmo relógio local
dos sinais para seleção causal. O corte do histórico gerador de HT e FT também
usa o relógio dos sinais. Definições sem qualquer um desses campos falham
fechado, e o contrato dos dois relógios faz parte do hash imutável da coorte.

As V1 foram preservadas no SQLite como trilha histórica e não são recalculadas
nem misturadas às V2. No momento da migração, a V1 de HT possuía um único
membro; FT e escanteios asiáticos possuíam zero. As três V2 começaram limpas às
18:49:27 UTC/14:49:27 no relógio dos sinais. Foram aprovados 21 testes
específicos, 547 testes integrados e os 176 módulos do preflight integral. O
sistema retomou com monitor, watchdog e pré-live ativos; o primeiro ciclo V2
concluiu 38 partidas e 7 tarefas detalhadas em 221,47 segundos. O watchdog
confirmou saúde, zero falhas consecutivas e nenhuma pausa preventiva.

## Coortes prospectivas dos quase-candidatos de Próximo Gol V44 — 10/09/2026

Dois relaxamentos possíveis do Próximo Gol passaram a ser avaliados em um
experimento futuro pré-registrado e totalmente silencioso. O braço
`odd_165_199` preserva qualidade, minuto, pressão, chute dominante, domínio
médio e pontuação do challenger balanceado e testa somente a ampliação da odd
de 1,65 até 1,99. O braço `atividade_com_chute` preserva a odd abaixo de 1,65
e testa somente o bloqueio genérico de atividade quando já existe chute recente
do lado dominante. Os braços são mutuamente exclusivos.

Cada braço congela os primeiros 60 jogos elegíveis após a âncora, com 42 para
desenvolvimento e 18 para holdout. A unidade é o primeiro quase-candidato da
partida entre os dois braços; o sincronizador não consulta resultado nem
entrega. Cartão vermelho, odd vencida, fonte inadequada e qualquer outro
bloqueio fora da lista fechada eliminam o candidato. A validação exige amostra
mínima, ROI positivo com intervalo de 95%, replicação no holdout e vantagem
conservadora sobre `1/odd` antes de permitir apenas revisão humana.

Uma verificação pós-registro detectou que `sinais.criado_em` usa o relógio
local sem offset enquanto a primeira âncora experimental havia sido serializada
em UTC. A definição foi substituída pela V2 antes de coletar qualquer membro:
ela preserva UTC com offset para auditoria e congela separadamente o relógio
local usado na comparação causal. A âncora V1 vazia permanece apenas como
trilha histórica e não participa da coorte.

O experimento não cria sinais novos, não envia Telegram, não altera os filtros
atuais e não possui promoção ou reativação automática. A definição e cada
membro ficam imutáveis no SQLite e o watchdog/status mostram o progresso dos
dois braços. Foram aprovados 554 testes direcionados do experimento, status,
monitor, watchdog e controle de processos antes do preflight integral. O
preflight aprovou todos os 176 módulos; a âncora V2 foi registrada às
18:32:43 UTC/14:32:43 no relógio dos sinais. O primeiro ciclo pós-V2 concluiu
41 partidas e 7 tarefas detalhadas sem falha, e o ciclo seguinte iniciou
normalmente.

## Auditoria contrafactual causal dos descartes V43 — 10/09/2026

O diagnóstico marginal do Próximo Gol agora acompanha também as liquidações
da auditoria silenciosa já existente. A população usa somente a primeira
auditoria de cada `partida+estado_de_gols`, escolhida por horário e ID antes de
consultar o resultado. Repetições posteriores não podem substituir uma
primeira entrada perdedora, pendente ou inválida.

A leitura é explicitamente exploratória e não pré-registrada para decisão:
exige 30 resultados apenas para deixar de ser uma amostra inicial, mas mesmo
depois disso não pode alterar filtro, Telegram ou promover mercado. A primeira
fotografia real contém quatro estados independentes, um red e três pendentes;
o ROI de -100% da única unidade resolvida não possui valor decisório.

O status operacional passou a mostrar `G/R/P` dessa auditoria ao lado do funil
marginal, mantendo a mensagem de que resultados não participam da seleção do
funil. Foram aprovados 53 testes direcionados e a consulta real terminou sem
gravação no SQLite.

## Proteção de risco visível no funil de Próximo Gol V42 — 10/09/2026

O diagnóstico marginal passou a excluir as cópias criadas pela auditoria
silenciosa de bloqueios. Essas cópias existem para receber liquidação
contrafactual, mas não representam uma nova decisão técnica e já não podem
aparecer como candidatos artificialmente sem bloqueios. Quatro linhas
derivadas foram identificadas e excluídas na validação real.

O primeiro estado que reuniu todos os critérios técnicos foi corretamente
barrado por `cartao_vermelho_reavaliar`: Al Quwa Al Jawiya x Al Zawra'a, aos
27 minutos, com odd 1,6154. O primeiro estado a uma condição técnica de
distância precisava de odd mais curta, mas ainda carregava o bloqueio separado
de atividade recente. Assim, nenhum dos dois justifica afrouxamento seguro.

O relatório normal `status_bot.py` agora mostra estados independentes, menor
distância, cobertura marginal de odd e pressão, gargalo e bloqueios de risco
dos estados tecnicamente completos. A execução real exibiu 56 estados,
`odd_curta` como gargalo e o cartão vermelho como proteção atuante. Foram
aprovados 51 testes direcionados, e o relatório operacional completo terminou
com código zero enquanto o PackBall permaneceu ativo.

## Diagnóstico marginal do Próximo Gol V41 — 10/09/2026

Foi acrescentado `diagnostico_funil_proximo_gol.py`, uma auditoria somente de
leitura para o challenger balanceado. O funil cumulativo continua sendo a
verdade sobre aprovação, mas, quando a primeira trava zera, o novo relatório
mede cada critério separadamente e calcula a menor quantidade de falhas no
mesmo snapshot de cada estado `partida+gols`. Ele não lê resultados, não grava
no SQLite, não altera filtros, não envia Telegram e não promove regras.

Na primeira execução real foram avaliadas 103 linhas e 52 estados
independentes, sem registros inválidos. A odd curta apareceu em 6 estados, a
pressão balanceada em 9, o chute dominante recente em 19 e a qualidade completa
em 32. Nenhum estado reuniu todos os critérios no mesmo instante; a distância
mínima foi de dois critérios em cinco estados. O principal gargalo marginal é
a odd, seguido pela pressão, mas essa observação ainda não autoriza relaxamento:
não existe quase-candidato barrado por um único limite. Os 19 testes do novo
diagnóstico e dos componentes diretamente relacionados foram aprovados, com o
PackBall permanecendo ativo.

## Liquidação conservadora de escanteios e retomada resiliente V40 — 10/09/2026

Resultados de escanteios FT asiáticos que terminam como `sem_dado` ganharam
uma recuperação adicional, estritamente conservadora. Ela só liquida quando
há uma leitura PackBall apta e multifonte entre os minutos 80 e 99, o total
permanece exatamente invariável em pelo menos três confirmações terminais por
dez minutos e a API-Football confirma o encerramento pelo menos duas vezes.
Qualquer mudança posterior no total mantém o resultado indeterminado, evitando
misturar escanteios do tempo regulamentar com prorrogação.

Na produção, o sinal 338536 foi revisado de `sem_dado` para `void`: a linha
asiática 12.0 terminou com total 12, sustentado por 126 confirmações PackBall e
348 confirmações da API-Football. O sinal 204367 permaneceu `sem_dado`, pois o
total mudou depois da última leitura regulamentar confiável. A revisão ficou
gravada no histórico, sem alterar resultados incertos.

O preflight isolado passou a ter limite global de 300 segundos. Uma falha
comum isolada só pode ser classificada como transitória após três aprovações
consecutivas do mesmo módulo em interpretadores novos; qualquer reincidência,
timeout ou falha nativa continua bloqueando a partida. Foram aprovados os 36
testes do preflight, os 38 do finalizador e os 174 módulos da suíte completa.
Depois da validação, a manutenção foi liberada, monitor e watchdog foram
retomados e o primeiro ciclo concluiu 45 partidas sem falhas.

## Preflight isolado por módulo V39 — 10/09/2026

A retomada no Windows deixou de executar os 2.501 testes dentro de um único
interpretador. Foi reproduzida uma falha nativa intermitente do Python 3.14
quando greenlet/Playwright e os módulos numéricos permaneciam carregados ao
longo de toda a suíte; também foi provado que algumas alterações temporárias
de configuração podiam contaminar módulos posteriores e produzir falsos
negativos.

O preflight agora executa cada um dos 174 módulos de teste em um processo
local descartável, sequencial e sem janela. O ambiente operacional continua
sendo removido antes da validação, o limite global de 180 segundos permanece
e qualquer falha aponta o módulo, o código e se houve encerramento nativo. Não
há retry que esconda defeito: um único módulo reprovado ainda bloqueia o
reinício.

Na validação real fora do sandbox, os 174 módulos e 2.501 testes foram
aprovados em 84,122 segundos. A falha nativa não reapareceu, e os casos que
antes recebiam estado vazado passaram em seus ambientes limpos. Nenhuma
mensagem Telegram real foi enviada.

## Retomada resiliente e tendência robusta de armazenamento V38 — 10/09/2026

O watchdog deixou de interpretar um salto isolado de backups como crescimento
recorrente do banco. A tendência operacional usa agora a mediana robusta das
inclinações entre pares de amostras (Theil–Sen), mantendo separada a variação
bruta entre o primeiro e o último ponto para auditoria. No histórico real, o
salto bruto de 4.818,4 MB/dia caiu para uma tendência recorrente de 197,7
MB/dia, com aproximadamente 325,2 dias até a reserva configurada. O alerta
crítico falso foi removido sem afrouxar a detecção de crescimento linear
sustentado.

A retenção oficial removeu dois backups pré-reinício antigos e não protegidos,
preservando cinco cópias pré-reinício mais novas e os backups diários e
periódicos. A rotina de início agora também reconcilia o backup diário mesmo
quando o banco já está no esquema atual; isso elimina o impasse causado por
uma migração interrompida. Avisos do Telegram que estão contidos e aprovados
para reinício deixam de aparecer como falhas efetivas no preflight.

O estado da coleta também atravessa a rotação do log: se o arquivo atual foi
aberto no meio de um ciclo, o último sucesso e as falhas subsequentes são
recuperados dos arquivos rotacionados. Assim, a rotação não se confunde com
uma instalação que nunca concluiu um ciclo.

Uma falha de compressão também deixou de ser fatal quando o SQLite original
passa novamente pela verificação completa. Nesse caso, a cópia sem compressão
é preservada como ponto de recuperação utilizável, o evento fica registrado
como aviso e a coleta continua. Se o original também falhar, o comportamento
permanece fail-closed.

Foram aprovados 254 testes dos componentes de backup, observabilidade e
serviço, além de 2.499 testes integrais. Nenhuma
mensagem Telegram real foi enviada pelos testes.

## Ritmo operacional auditável por coorte V37 — 10/09/2026

O prazo central agora mede o ritmo de cada coorte exata somente depois de 5
unidades independentes e 24 horas de exposição operacional confirmada. O
relógio não usa mais uma simples diferença entre a data da âncora e o presente:
ele reconstrói faixas sustentadas por ciclos próximos do monitor, exclui
manutenções e recusa extrapolação quando o histórico não cobre a âncora. Com
menos de 15 unidades ou 72 horas, qualquer estimativa permanece marcada como
`preliminar`; acima desses dois limites, passa a `observada`.

Âncoras gravadas em UTC são convertidas para a hora local usada pelos eventos
históricos antes da comparação. Isso evita descartar ciclos válidos por causa
do deslocamento de fuso. O diagnóstico mostra, por método, unidades observadas,
tamanho da coorte, horas confirmadas, ritmo por 24 horas operacionais e dias
operacionais restantes. Esses dias não são somados e nunca viram uma data
global, porque as coortes se sobrepõem e ainda existem gates não
quantificáveis.

Na auditoria real, a manutenção manual continuou ativa, sem falha técnica e
com zero ritmos extrapoláveis. As coortes novas têm 0 hora operacional; o braço
FT 1T possui 11,914 horas confirmadas, mas a telemetria disponível não cobre
sua âncora antiga e ele tem 0 unidade na coorte atual. Portanto não existe
prazo responsável enquanto o bot permanecer pausado. Foram aprovados 159
testes direcionados e 2.491 testes integrais, sem iniciar processos nem enviar
Telegram real.

## Prazo de prontidão baseado em coortes V36 — 10/09/2026

O resumo central agora recusa datas de liberação sem ritmo prospectivo da
versão exata. Em manutenção, o estado é `suspenso_manutencao`, a coleta e o
calendário aparecem parados e o tempo de parede não conta como amostra. As
metas não são somadas, pois uma partida pode alimentar coortes distintas e
cada método possui sua própria unidade causal.

O painel expõe separadamente o restante do seletor pré-live, de cada braço de
mercado e da coorte CLV. Também normaliza os validadores aninhados do portfólio
FT, evitando que um método ativo apareça sem candidatos, resultados e
faltantes. No estado real de 10/09/2026, ficaram visíveis: FT 1T 100, FT 2T
preciso 60, HT preciso 60, Próximo Gol principal 92, challenger 40, Próximo
Escanteio 70, Escanteios FT asiáticos 100, pré-live 60 e CLV 120 unidades.

A maior meta quantificada é 120, mas isso não representa 120 apostas somáveis
nem autoriza uma data. Foram aprovados 120 testes direcionados e 2.486 testes
integrais. O bot permaneceu em manutenção manual, sem processos ativos ou
Telegram real.

## Gate central do worker de treinamento V35 — 10/09/2026

O autoteste do worker isolado agora também faz parte da prontidão profissional
central. O diagnóstico só aceita o componente quando a resposta é saudável, o
estado é `pronto` ou `recuperado` e o protocolo corresponde exatamente a
`treino-modelo-isolado-v1`. Falha, protocolo divergente ou resposta incompleta
degradam `operacao_continua` e aparecem como pendência técnica, inclusive
durante uma pausa planejada.

O resumo operacional expõe estado, tentativas, recuperação transitória,
motivo e duração do autoteste. Na validação real de 10/09/2026, o worker ficou
`pronto`, respondeu em 57,948 ms na primeira tentativa e não recuperou falha.
O diagnóstico geral permaneceu corretamente em `pausa_planejada`, sem falha
técnica ativa. Foram aprovados 181 testes direcionados e 2.484 testes
integrais, sem iniciar o bot nem enviar mensagens reais.

## Autoteste do worker no preflight V34 — 10/09/2026

Antes de qualquer retomada, o preflight agora lança um desafio local e efêmero
ao worker de treinamento. A prova exige processo filho funcional, protocolo
JSON exato, PID pai vivo, resposta correspondente ao desafio e auditoria da
tentativa. O teste não abre PackBall, não consulta API, não escreve no banco e
não envia Telegram.

Falha de criação, timeout, protocolo inválido ou resposta incompatível fazem
`worker_treino_isolado.saudavel=false` e bloqueiam o reinício. Uma falha
transitória recuperada continua visível com tentativas e motivos. Na prova real
de 10/09/2026, o worker respondeu em 54,424 ms, na primeira tentativa e sem
falha transitória. Foram aprovados 86 testes direcionados e 2.482 testes
integrais, mantendo a manutenção manual e zero processos do bot.

## Treinamento numérico isolado V33 — 10/09/2026

Os challengers de pontuação contextual e de janelas longas não executam mais
o ajuste logístico dentro do monitor. Cada treinamento raro roda em um processo
local descartável, oculto no Windows, com protocolo JSON restrito, limite de
cinco segundos e até três tentativas. Timeout, exceção numérica, saída inválida
ou modelo incompatível são contidos fora do processo principal.

O worker recebe o PID do chamador e mantém uma custódia independente a cada
250 ms. Se o monitor desaparecer durante um ajuste travado, o worker se encerra
sozinho, em vez de permanecer órfão ou deixar uma janela residual no Windows.

Antes de aceitar a saída, o chamador revalida mercado, versão, configuração,
features e tamanho da amostra. Uma recuperação bem-sucedida fica registrada no
próprio modelo em `execucao_treino_isolado`, com quantidade de tentativas e
tipos das falhas transitórias; se as três tentativas falharem, nenhum modelo é
persistido. Erros determinísticos de dados continuam sendo recusados sem
repetição inútil.

`treino_processo_isolado.py` e `treinar_modelo_worker.py` fazem parte das
assinaturas de runtime do monitor e do watchdog. Foram aprovados 50 treinos
contextuais consecutivos no Python 3.14, 50 no Python 3.13, mais 20 de cada
challenger depois da integração e a regressão integral de 2.480 testes. O bot
permaneceu em manutenção, sem fontes externas nem mensagens reais.

## Retomada manual transacional V32 — 10/09/2026

Uma pausa manual agora só pode ser removida por uma intenção explícita:
`python iniciar_sistema.py --retomar-manutencao`. Executar o iniciador sem essa
opção preserva `modo_manutencao.json`, não roda o preflight e não cria monitor
ou watchdog. O Agendador do Windows continua sem autoridade para desfazer uma
pausa.

Depois de um preflight aprovado, a retomada ainda é provisória até monitor e
watchdog comprovarem estado ativo, PID vivo e trava exclusiva por 12 segundos
contínuos. Uma exceção ao criar qualquer componente, uma falha explícita ou o
timeout de estabilidade restauram imediatamente a manutenção com o motivo
`rollback_inicio_instavel`. O evento fica auditável e impede que o Agendador
transforme uma inicialização defeituosa em uma sequência de reinícios.

A regressão integral passou em 2.478 testes. A validação foi inteiramente
local: nenhum processo do bot foi iniciado, nenhuma fonte externa foi
consultada e nenhuma mensagem real foi enviada.

O rollback também abre um novo período no relógio prospectivo V30/V31. A
versão `exposicao-coleta-prospectiva-v2` reconhece o evento restaurado como
início de manutenção; depois de uma retomada futura, esse intervalo continuará
fora da idade operacional e nunca será confundido com coleta real.

## Gate central de exposicao prospectiva V31 — 10/09/2026

A V30 tornava os relogios prospectivos visiveis no status individual, mas a
auditoria central de prontidao ainda nao os consumia. Portanto, um operador
precisava cruzar manualmente quatro fotografias para saber se a ausencia de
amostra era uma pausa explicada ou uma falha de coleta.

A V31 inclui as quatro avaliacoes periodicas em `coletar_evidencias` e cria o
componente formal `exposicao_coleta_prospectiva`. Para cada avaliacao, o gate
exige custodia compativel, cronologia valida, efeitos da avaliacao bloqueados,
relogio V30 saudavel, nenhuma solicitacao de atencao e os seis efeitos do
proprio relogio exatamente falsos. Relogio ausente, versao divergente, ancora
ausente, telemetria degradada ou qualquer efeito ativo vira pendencia tecnica.

O gate participa de `operacao_continua` e da prontidao completa. Uma pausa
planejada continua aparecendo como pausa, mas nao esconde um relogio corrompido
ou uma coleta que ja estava interrompida. O resumo compacto agora entrega o
diagnostico agregado e o detalhamento por avaliacao, sem usar a exposicao como
prova de edge ou liberar mercado.

Na auditoria real, as quatro avaliacoes foram aceitas, totalizando sete
relogios de coorte: dois com exposicao confirmada e cinco sem exposicao por
manutencao planejada. Houve zero problema de custodia, cronologia, telemetria
ou efeito. O estado geral permaneceu `pausa_planejada`, com 11 pendencias
legitimas e nenhuma falha tecnica ativa.

A suite completa passou em 2.474 testes. O bot permaneceu em manutencao, sem
coleta nem Telegram real; as mensagens impressas pela suite pertencem a mocks.

## Relogio de exposicao prospectiva V30 — 10/09/2026

As avaliacoes prospectivas mostravam amostra zero sem distinguir duas causas
opostas: o bot poderia estar funcionando sem coletar, ou a coorte poderia ter
nascido depois de uma pausa manual. Essa ambiguidade permitia interpretar uma
espera planejada como falha do pipeline ou, no sentido contrario, deixar uma
falha anterior escondida pela manutencao atual.

A V30 cria `exposicao_coleta_prospectiva.py`. O modulo le a trilha append-only
de observabilidade com cache invalidado pelo tamanho e pela data do arquivo,
reconstroi pausas de manutencao encerradas e abertas e mede somente trabalho
confirmado: ciclos concluidos, ciclos falhos, partidas, tarefas, duracao real
de processamento, comparacoes de odds e cobertura BetsAPI. Tempo de parede
nunca vira amostra. O relogio operacional desconta apenas pausas explicitamente
marcadas, consolida periodos sobrepostos e falha fechado se a telemetria, a
ancora ou o estado de manutencao forem invalidos.

Sem nenhum ciclo, ate uma hora de tempo operacional e tratada como espera pelo
primeiro ciclo. Acima disso, o estado exige atencao. Uma pausa atual explica a
ausencia apenas quando a ancora nasceu durante ela ou quando ainda nao houve
uma hora operacional; assim, a pausa nao mascara um pipeline que ja estava
parado antes.

O relogio foi integrado ao limite comum de persistencia das quatro avaliacoes,
as assinaturas de runtime do monitor e do watchdog, os verificadores e o status
operacional. Ele e estritamente observacional: sinal, calibracao, prioridade,
promocao, reativacao e Telegram continuam explicitamente falsos.

Nas fotografias reais, a estrategia de espera pela odd confirmou 252 ciclos,
8.049 partidas somadas e 1.145 tarefas depois da ancora. Prioridade sazonal de
ligas e quarentena HT permanecem com zero ciclo porque suas ancoras foram
criadas durante a manutencao. O desajuste multifonte possui quatro relogios:
a coorte principal observou os mesmos 252 ciclos, enquanto o recorte executavel
e as convergencias de gols e escanteios nasceram durante a pausa e ainda nao
tiveram exposicao. O estado agregado e
`exposicao_parcial_com_coortes_em_pausa`, sem alegar vantagem executavel.

A suite completa passou em 2.471 testes e o `PRAGMA quick_check` retornou
`ok`. A manutencao permaneceu ativa, com zero processos Python e nenhum envio
real ao Telegram; as mensagens exibidas pela suite pertencem a mocks.

## Higiene de conexoes SQLite da suite V29 — 10/09/2026

A suite da V28 terminava aprovada, mas o coletor de lixo emitia um
`ResourceWarning` sobre uma conexao SQLite nao encerrada. Um rastreamento de
alocacao com 15 quadros executou os 2.462 testes e localizou a unica origem em
`test_proximo_gol_balanceado_sombra.py`: o teste idempotente abria um banco
`:memory:` sem registrar fechamento.

O fixture agora usa a limpeza garantida do `unittest`, que fecha a conexao
mesmo se a preparacao ou uma assercao falhar. Os 23 testes diretamente
envolvidos passaram com `ResourceWarning` promovido a erro. Em seguida, a
suite normal completa passou novamente em 2.462 testes, sem repetir o aviso.

O diagnostico confirmou que nao havia vazamento no modulo de probabilidade
historica nem no runtime do monitor. A mensagem de indisponibilidade historica
e deliberadamente exercitada por teste; os textos de Telegram vistos na suite
tambem pertencem a mocks. O bot permaneceu em manutencao e nenhum envio real
foi executado.

## Contrato explicito de efeitos observacionais V28 — 10/09/2026

A verificacao final da V27 mostrou que cada avaliador declarava apenas os
efeitos diretamente relacionados a sua funcao. Os demais apareciam ausentes
ou `null`. Embora o consumo atual os interpretasse como falsos, isso deixava o
contrato ambiguo para leitores futuros e para qualquer integracao que lesse o
estado persistido diretamente.

A V28 eleva a custodia para `custodia-execucao-avaliacao-v3`. No limite de
persistencia, o servico agora sobrescreve, sem confiar no avaliador, os seis
efeitos operacionais: aplicacao de sinais, calibracao, prioridade, promocao,
reativacao e Telegram. Todos precisam existir e ser exatamente o booleano
`false`.

O watchdog audita completude, tipo e valor antes de aceitar uma conclusao.
Campo ausente, `null`, valor de outro tipo ou qualquer `true` invalida a
custodia antes de expor amostras ou selos de vantagem. Alem disso, toda saida
publica dos quatro verificadores e normalizada novamente como fail-closed,
inclusive arquivo ausente, JSON invalido, versao antiga, falha e execucao
interrompida. O status apresenta `efeitos=bloqueados` ou os campos invalidos.

As quatro fotografias reais foram regeneradas apenas com o SQLite local:
espera pela odd V6 em 1,408 s, prioridade de ligas V3 em 0,010 s, desajuste
V11 em 0,692 s e quarentena HT V3 em 0,951 s. Todas ficaram concluidas sob
custodia V3, com cronologia valida, auditoria de efeitos valida e os seis
efeitos explicitamente falsos.

A suite completa passou em 2.462 testes. O bot permaneceu em manutencao, com
zero processos; as mensagens de Telegram exibidas pelos testes pertencem a
mocks e nenhum envio real foi realizado.

## Cronologia inviolavel das avaliacoes V27 — 10/09/2026

A auditoria da V26 encontrou uma brecha no calculo de frescor: datas no futuro
eram reduzidas a idade zero. Um documento adulterado, um relogio incorreto ou
uma restauracao com horario impossivel poderia, portanto, parecer recente por
tempo indefinido.

A V27 eleva o contrato comum para `custodia-execucao-avaliacao-v2` e recalcula
a cronologia sem confiar na idade gravada. O watchdog exige inicio,
atualizacao e, para conclusao ou falha, finalizacao e duracao finita nao
negativa. Ele rejeita inicio posterior a atualizacao, final anterior ao
inicio, divergencia entre finalizacao e atualizacao e qualquer instante mais
de 60 segundos no futuro. Execucao em andamento com idade ausente,
negativa ou nao finita tambem passa a ser invalida.

Qualquer problema cronologico falha fechado antes da leitura de amostras ou
selos positivos: sinal, calibracao, prioridade, promocao, reativacao e
Telegram permanecem bloqueados. O status agora exibe `cronologia=ok` ou a
causa exata da inconsistencia.

As quatro fotografias reais foram regeneradas somente a partir do SQLite:
espera pela odd V6 em 1,430 s (180 conclusivos, 179 jogos e 19 atingimentos de
faixa), prioridade de ligas V3 em 0,010 s (zero unidades), desajuste V11 em
0,672 s (3.814 comparacoes e 202 candidatos) e quarentena HT V3 em 0,846 s.
Todas terminaram com custodia V2 e cronologia valida, sem liberar vantagem ou
efeito operacional novo.

A suite completa passou em 2.459 testes e o `PRAGMA quick_check` retornou
`ok`. O bot permaneceu em manutencao, com zero processos e sem coleta,
promocao, reativacao ou Telegram real.

## Custodia comum das avaliacoes periodicas V26 — 10/09/2026

A protecao V25 cobria apenas o desajuste multifonte. A auditoria seguinte
encontrou o mesmo risco de estado antigo nas avaliacoes da espera pela odd,
prioridade sazonal de ligas e quarentena do fallback HT.

A V26 centraliza o protocolo em `custodia-execucao-avaliacao-v1`. As quatro
rotinas agora gravam atomicamente `em_execucao` antes de calcular, aceitam
`concluida` somente com a versao esperada e persistem `falha` sem copiar
amostras ou conclusoes anteriores. O envelope desativa simultaneamente sinal,
calibracao, prioridade, promocao, reativacao e Telegram. A telemetria fica
isolada depois da escrita, e uma execucao abandonada expira em 600 segundos.

Os watchdogs exigem tanto a versao estatistica quanto a versao da custodia.
Estado ausente, contrato divergente, falha ou abandono zeram qualquer selo de
vantagem antes da resposta. O modulo comum entrou nas assinaturas de runtime
do monitor e do watchdog, impedindo inicializacao silenciosa com codigo
parcialmente atualizado.

As fotografias reais foram regeneradas localmente em SQLite: espera pela odd
V6 em 4,343 s, prioridade de ligas V3 em 0,070 s, desajuste V11 em 2,529 s e
quarentena HT V3 em 1,620 s. Todas terminaram sob custodia compativel. A espera
tem 180 unidades conclusivas em 179 jogos e apenas 19 atingimentos de faixa,
sem vantagem comprovada; prioridade e quarentena ainda nao possuem unidades
prospectivas. A persistencia geral do desajuste permanece observacional e o
recorte executavel continua sem vantagem liberada.

A suite completa passou em 2.455 testes. O bot permaneceu em manutencao, com
zero processos, sem coleta, promocao ou Telegram real.

## Falha fechada da avaliacao multifonte V25 — 10/09/2026

A avaliacao de desajuste atualizava o arquivo apenas quando terminava com
sucesso. Se o calculo falhasse, o erro aparecia na telemetria, mas a ultima
fotografia saudavel permanecia no disco e podia continuar parecendo atual por
ate uma hora.

A V25 transforma a atualizacao em um protocolo persistente de tres estados.
Antes do calculo, o servico grava `em_execucao` sem transportar candidatos,
persistencia ou qualquer selo de vantagem. Ao terminar, substitui esse
marcador por `concluida`; em qualquer excecao, grava `falha` com diagnostico
redigido e todos os efeitos operacionais desativados. Uma queda abrupta deixa
o marcador em andamento, que o watchdog considera abandonado depois de 600
segundos. Assim, nem falha capturada, travamento nem encerramento entre etapas
reexpoem a avaliacao anterior.

O watchdog V11 so interpreta integridade, corroboracao e recortes quando o
estado de execucao e `concluida`. Nos demais estados ele apaga conclusoes
positivas da resposta, bloqueia inferencia e informa separadamente avaliacao
em curso, falha ou execucao interrompida. O status operacional agora mostra
execucao, saude, motivo, contagens da auditoria, fingerprint, progresso da
corroboracao e o bloqueio de inferencia.

A suite completa passou em 2.450 testes. A avaliacao real V11 terminou em
0,767 segundo e reproduziu 4.045 de 4.045 comparacoes validas, zero invalidas,
sem truncamento e com fingerprint
bc235e831a10c94aa0d2abb2935722534d2abe10d7b9da9d2078cf12af39c6ee.
As 3.814 comparacoes elegiveis e 202 candidatas continuam apenas
observacionais; a corroboracao prospectiva ainda tem zero fotografias em zero
jogos. O bot permaneceu em manutencao, sem coleta, promocao ou Telegram real.

## Replay integral das comparacoes multifonte V24 — 10/09/2026

As comparacoes de odds eram append-only e tinham SHA-256, mas a avaliacao de
desajuste confiava diretamente nos campos persistidos. Uma insercao forjada
com hash recalculado, um delta incorreto ou uma classificacao divergente
poderia contaminar persistencia, convergencia e a descoberta de vantagem.

A V24 centraliza o documento canonico da comparacao e recalcula o SHA-256,
precos, fonte e bookmaker de melhor cotacao, controle, deltas absoluto e
relativo, intervalo entre fontes, diferenca de minuto, compatibilidade da
bookmaker, estado e motivos. O estado e refeito a partir dos precos sem usar o
delta arredondado, preservando corretamente casos na fronteira de 5%.

A avaliacao V10 audita todas as linhas V4 antes de montar qualquer amostra.
Linhas invalidas ficam fora da estatistica e qualquer problema ou truncamento
bloqueia pronto_para_revisao, persistencia_comprovada e todos os selos de
vantagem dos recortes. O watchdog valida contagens, versoes, fingerprint e
coerencia do resultado; um arquivo de estado nao pode reativar esses selos
quando a cadeia estiver inconsistente.

O replay real em SQLite somente leitura confirmou 4.045 de 4.045 comparacoes
validas, zero problemas e fingerprint
bc235e831a10c94aa0d2abb2935722534d2abe10d7b9da9d2078cf12af39c6ee.
A suite completa passou em 2.442 testes, incluindo adulteracao com SHA-256
recalculado. Nenhuma regra ou alerta foi promovido. A prontidao permaneceu em
pausa_planejada, sem falha tecnica ativa, e nenhum Telegram real foi enviado.

## Corroboracao prospectiva da odd de entrada V23 — 10/09/2026

A fila rapida usava a API-Football como substituta quando a BetsAPI nao
encontrava a linha, mas nao obtinha uma fotografia independente quando a
cotacao da BetsAPI realmente atingia o alvo do sinal. Assim, uma cotacao
executavel podia ser materializada com contrato completo sem que o sistema
medisse naquele instante se outra fonte confirmava o mesmo preco.

A V23 consulta a API-Football uma unica vez quando a oferta principal atinge
o alvo. A chamada nao ocorre enquanto a odd ainda esta abaixo da faixa. A
oferta de controle precisa passar novamente pelo contrato completo
Over/Under, origem do grupo, identidade do evento, equipes, placar e
proveniencia temporal. Ela e anexada como controle e nunca substitui a oferta
selecionada da BetsAPI.

Quando duas fontes independentes sao validas, o SQLite congela as comparacoes
Over e Under em comparacoes_odds_fontes, identificadas pelo marcador
corroboracao_odd_entrada_rapida. A evidencia continua append-only e em modo
sombra. Indisponibilidade ou divergencia da fonte de controle nao aprova nem
reprova o sinal principal; fica isolada na telemetria.

A avaliacao V9 separa essa coorte por fotografia, jogo, par de fontes, estado
e selecao. Ela exige ao menos 30 fotografias em 15 jogos antes de permitir
revisao humana e proibe aplicacao ou promocao automatica. O watchdog falha
fechado se um estado V9 omitir ou adulterar esse recorte. A avaliacao tambem
reutiliza ancoras existentes sem escrita, permitindo auditoria genuina do
SQLite em modo somente leitura.

A suite completa passou em 2.439 testes. A leitura real encontrou 3.814
comparacoes historicas e 202 candidatos independentes, mas zero fotografias
V23, como esperado para uma evidencia criada apenas de forma prospectiva com
o bot pausado. Nenhuma regra foi promovida, nenhum Telegram real foi enviado
e a prontidao permaneceu em pausa_planejada, sem falha tecnica ativa.

## Custodia persistente de anomalias da curva V22 — 10/09/2026

A V21 bloqueava uma curva de odds matematicamente impossivel, mas a rota
rapida gravava a oferta selecionada antes de chegar a esse bloqueio. O motivo
aparecia na telemetria do ciclo, porém desaparecia após reinicio e a linha
individual podia permanecer no SQLite com aparencia de oferta normal.

A rechecagem agora envia ao banco a fotografia completa das odds. O SQLite
reconstitui de forma independente a curva do mesmo mercado, periodo, fonte,
bookmaker e grupo, e exige que a linha selecionada coincida tambem nos precos
Over e Under. Quando encontra duplicata contraditoria ou dominancia
impossivel, grava `anomalia-curva-odd-v1` no estado
`anomalia_curva_odd`, com todas as linhas canonicas usadas no calculo. Essa
evidencia e append-only, recebe SHA-256 e fica explicitamente marcada como nao
autorizada; ela nunca segue para comparacao multifonte, materializacao ou
Telegram.

A cadeia de custodia CLV V11 recalcula cada prova persistida. Ela confronta o
sinal, partida, mercado, linha, fonte, identidade externa, origem do grupo,
relogios, preco selecionado e motivo da coluna. Alterar o diagnóstico mesmo
com um novo hash valido torna a auditoria inconsistente. O ciclo tambem expoe
`anomalias_curva_odds` e preserva o motivo matematico exato na observabilidade.

A suite completa passou em 2.431 testes. A auditoria real somente leitura V22
confirmou 10.254 observacoes, 1.289 ofertas monitoradas, 1.562 payloads, zero
anomalias historicas, 12 gatilhos validos e zero problemas. O fingerprint
historico permaneceu
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
Nao houve migracao nem escrita na base real. A prontidao permaneceu em
`pausa_planejada`, sem falha tecnica ativa, e nenhum Telegram real foi enviado.

## Coerencia matematica da curva de odds V21 — 10/09/2026

Mesmo depois de provar a origem do grupo, um feed podia apresentar linhas
internamente dominadas. Em totais binarios sem possibilidade de devolucao,
Over 0,5 abrange todos os resultados de Over 1,5 e, portanto, nao pode pagar
mais; para Under, a ordem e inversa. Uma violacao nao representa edge: indica
mistura, atraso ou corrupcao da curva.

A camada `coerencia-curva-odds-v1` agora ordena apenas linhas terminadas em
0,5 do mesmo grupo comprovado. Ela valida Over e Under em conjunto, rejeita
duplicatas contraditorias e bloqueia a cotacao quando encontra dominancia
impossivel. Linhas de grupos diferentes e mercados sem prova suficiente nao
sao comparados, evitando criar uma falsa anomalia.

O diagnostico completo da curva fica congelado nas features do candidato. Um
bloqueio impede a cotacao CLV de ser criada, reprova o candidato e chega ao
gateway anterior ao Telegram. A rota rapida preserva na telemetria o motivo
exato, as linhas e o lado incoerente, em vez de reduzir toda ocorrencia a uma
falha generica de proveniencia. A protecao e estrutural e nao promove qualquer
regra, mercado ou alegacao de vantagem estatistica.

A suite completa passou em 2.425 testes. Nao houve migracao nem alteracao do
historico SQLite. O PackBall permaneceu em pausa planejada e nenhum Telegram
real foi enviado.

## Custodia ponta a ponta da origem do mercado V20 — 10/09/2026

A V19 provava que os lados da odd pertenciam ao mesmo grupo da casa, mas essa
identidade ainda nao acompanhava obrigatoriamente a cotacao congelada usada no
calculo sem vig e no CLV. Duas ofertas com mercado, linha, preco, fonte,
bookmaker e horario iguais, mas vindas de grupos diferentes, podiam parecer a
mesma cotacao em uma etapa posterior.

O contrato compartilhado `origem-mercado-odd-v1` agora participa da selecao da
oferta, da deteccao de ambiguidade, da cotacao congelada e da revalidacao antes
do envio. A rota rapida exige correspondencia exata com o grupo ja confirmado;
uma origem malformada ou divergente rejeita o candidato. Mesmo precos
economicamente identicos continuam ambiguos quando os IDs de grupo diferem.

Cotacoes com prova de grupo usam `cotacao-entrada-clv-v2` e carregam a origem
normalizada dentro da evidencia imutavel. O calculo de valor e a auditoria CLV
V20 verificam novamente fonte, bookmaker, linha, lados e assinatura do grupo.
O contrato V1 permanece aceito apenas para o historico e para coletores que nao
declararam essa prova; ele nao pode substituir uma V2 quando o sinal atual ja
possui origem confirmada.

A suite completa passou em 2.419 testes. A auditoria real somente leitura
confirmou 10.254 observacoes, 1.562 payloads, 12 gatilhos de custodia, zero
problemas e o fingerprint historico preservado
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
Nao houve migracao nem reescrita do SQLite. O PackBall permaneceu em pausa
planejada e nenhum Telegram real foi enviado.

## Origem sincronizada do grupo de mercado V19 — 10/09/2026

Uma resposta Bet365 pode conter mais de um grupo com o mesmo nome e a mesma
linha. O coletor anterior acumulava Over e Under por linha depois de percorrer
todos os grupos; assim, dois grupos individualmente incompletos podiam formar
um par artificial. A margem sem vig pareceria calculavel, embora os dois precos
nao pertencessem a mesma fotografia de mercado.

A BetsAPI agora monta e valida cada par dentro de um unico grupo antes de
considerar a linha. A regra vale para gols FT, gols HT e escanteios asiaticos.
Proximo gol somente existe quando Casa, Visitante e Sem gol aparecem juntos no
mesmo grupo correspondente ao ordinal atual. Grupos suspensos ou incompletos
continuam fechados, sem combinar dados de outro grupo.

Cada oferta nova carrega `origem-mercado-odd-v1`: fonte, identificador e nome
do grupo, linha, lados, bookmaker e o schema da prova. O validador central
confirma fonte, linha, conjunto exato de lados e a mesma casa de apostas. A
API-Football produz a mesma prova quando atua como fallback. Ausencia ou
divergencia bloqueia avaliacao, persistencia, materializacao e Telegram.

O SQLite registra novas evidencias como `oferta-monitorada-odd-v4`, preserva
V2/V3 e o legado sem reescrita e aplica a continuidade de identidade a V3 e
V4. A cadeia CLV V10/V19 distingue contrato V4 incompleto de origem de grupo
invalida, inclusive quando o payload adulterado possui hash correto.

A migracao foi precedida pelo backup verificado
`pre_migracao_20260910_031428.db`, SHA-256
`41ad81e21395fc6eb621cc8e78bbce7bea54755a4aa54d14881eadce434048a6`.
A suite completa passou em 2.414 testes. O banco real permaneceu compativel,
com 29 tabelas, 12 gatilhos de custodia, zero violacoes de chave estrangeira,
10.254 observacoes, zero problemas e fingerprint historico
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
O PackBall permaneceu em pausa planejada e nenhum Telegram real foi enviado.

## Correspondencia independente das equipes da odd V18 — 10/09/2026

A prova de identidade ja exigia nomes nao vazios, placar, fonte e ID externo,
mas o validador generico ainda confiava no marcador `confirmada` produzido pelo
coletor. Uma integracao defeituosa podia declarar uma oferta confirmada com
equipes diferentes e placar coincidentemente igual.

O avaliador agora normaliza novamente os dois nomes, remove variacoes comuns de
siglas e acentos e calcula a correspondencia de cada equipe contra a partida do
PackBall. Cada lado precisa atingir 0,76 e a media do par precisa atingir 0,84,
os mesmos pisos conservadores do pareador BetsAPI. A orientacao ja corrigida
pela fonte e respeitada, inclusive em eventos invertidos.

O estado revalidado pela API-Football passa os nomes esperados ao avaliador. O
SQLite repete a comparacao usando as equipes persistidas da partida, portanto
uma chamada direta nao consegue aceitar apenas um booleano `confirmada`. A
cadeia CLV V9/V18 tambem compara cada evidencia V3 ao cadastro historico da
partida e separa divergencia de equipes das demais falhas de identidade.

A suite completa passou em 2.410 testes, incluindo uma oferta com ID e placar
plausiveis, mas equipes erradas. A auditoria real permaneceu integra com 10.254
observacoes, 11 gatilhos de custodia, zero problemas e fingerprint
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
O PackBall permaneceu pausado e nenhum Telegram real foi enviado.

## Continuidade imutavel da identidade das odds V17 — 10/09/2026

A validacao V16 confirmava cada cotacao isoladamente, mas uma mesma fonte ainda
podia trocar o identificador externo entre duas leituras do mesmo sinal. Se os
nomes e o placar continuassem plausiveis, a segunda oferta poderia parecer
valida apesar de pertencer a outro evento.

A primeira evidencia V3 de cada combinacao sinal/fonte agora fixa o
identificador externo e a orientacao. Leituras posteriores da mesma fonte
precisam manter ambos; uma troca e recusada antes do `INSERT`. Um gatilho
SQLite repete a regra no nivel do banco para proteger tambem contra gravacoes
concorrentes ou chamadas que contornem o fluxo normal.

A coluna `evento_externo_id` passa a guardar o identificador da propria fonte
da odd, em vez da fixture auxiliar da API-Football. Os nomes observados tambem
vem da prova de identidade. A auditoria CLV V8/V17 confronta coluna e payload e
percorre toda a trajetoria para detectar qualquer quebra de continuidade.

O servico agora e fail-closed diante de qualquer recusa ou excecao ao persistir
a evidencia: ele nao compara fontes, nao materializa a entrada e nao envia
Telegram sem custodia aceita. Isso fecha uma rota em que uma avaliacao aprovada
podia continuar mesmo depois de o banco recusar sua prova.

A migracao aditiva foi precedida pelo backup verificado
`pre_migracao_20260910_024356.db`, com SHA-256
`1d7ec5914789ff77a759be2dfb54d86871679b82721b5423d2290a06c9e66b22`.
O banco real permaneceu compativel, com 29 tabelas, 11 gatilhos da cadeia CLV,
zero violacoes de chave estrangeira, 10.254 observacoes e zero problemas de
conteudo ou continuidade. A suite completa passou em 2.409 testes. O PackBall
permaneceu pausado e nenhum Telegram real foi enviado.

## Identidade externa vinculada a cada odd V16 — 10/09/2026

O contrato V15 provava que todos os lados pertenciam a mesma fotografia de
mercado, mas ainda precisava demonstrar que essa fotografia era do jogo
correto. Uma linha e um placar plausiveis podiam, em caso de pareamento externo
incorreto, parecer uma oportunidade valida de outra partida.

Toda nova oferta rapida agora carrega uma prova explicita de identidade do
evento: fonte, identificador externo, orientacao direta ou invertida, nomes
normalizados das equipes, similaridade do pareamento e placar normalizado. A
prova precisa estar confirmada e o placar precisa coincidir com o estado atual
do jogo. Identidade ausente, malformada ou divergente bloqueia a avaliacao, o
registro no SQLite, a materializacao e o envio do alerta.

A BetsAPI gera a prova a partir do pareador rigoroso ja usado na coleta. Quando
essa prova nao for valida, a linha nao e reaproveitada silenciosamente: a rota
pode tentar a API-Football, que precisa demonstrar sua propria identidade por
fixture persistida, orientacao e placar atual. Assim, uma fonte pode recuperar
a indisponibilidade da outra sem misturar partidas.

As novas evidencias usam o schema imutavel `oferta-monitorada-odd-v3`. A cadeia
CLV V7/V16 valida o contrato completo V3 e a identidade do evento, mantendo
compatibilidade de auditoria com V2 e classificando o historico anterior como
legado, sem reescrita retroativa.

A auditoria real permaneceu integra: 10.254 observacoes, 1.289 ofertas
monitoradas legadas, 1.562 payloads, zero problemas e fingerprint
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
A suite completa passou em 2.406 testes. O bot permaneceu pausado e nenhum
Telegram real foi enviado.

## Contrato completo e sincronizado de mercado V15 — 10/09/2026

A rota rapida de acompanhamento podia observar corretamente a odd escolhida,
mas o payload historico nao garantia sempre que o lado oposto do total — ou as
tres saidas de proximo gol — pertencia a mesma fotografia de mercado. Sem esse
contrato completo, uma odd aparentemente boa poderia refletir apenas margem da
casa, impedindo o calculo confiavel da probabilidade sem vig e do CLV.

Toda nova conversao de `gol_ht` e `gol_ft` agora exige Over e Under validos da
mesma oferta. `proximo_gol` exige Casa, Visitante e Sem gol completos, alem de
confirmar que a odd escolhida coincide com a selecao preservada. A ausencia de
qualquer lado bloqueia a observacao, a materializacao e o envio. A cotacao de
entrada e congelada novamente no instante da conversao, substituindo com
seguranca a odd baixa que originou a fila.

O SQLite grava as novas observacoes com o schema imutavel
`oferta-monitorada-odd-v2`. Uma mudanca em qualquer lado do mercado passa a ser
movimento material, mesmo quando o preco selecionado nao muda. A cadeia CLV
V6/V15 valida o contrato V2 e falha fechada diante de payload incompleto com
hash correto; as 1.289 observacoes anteriores continuam explicitamente
classificadas como legado, sem reescrever o passado.

A auditoria real permaneceu integra: 10.254 observacoes, 1.289 ofertas
monitoradas legadas, zero problemas e o mesmo fingerprint historico. A suite
completa passou em 2.404 testes. O bot permaneceu pausado e nenhum Telegram
real foi enviado.

## Proveniencia temporal dupla das odds V14 — 10/09/2026

O rechecador rapido validava a idade numerica informada pela fonte, mas ainda
nao demonstrava que ela era compativel com `coletado_em`. Uma resposta antiga
marcada incorretamente como idade zero poderia, portanto, parecer fresca e
atingir a faixa de entrada.

Toda cotacao rapida agora precisa trazer idade nao negativa, horario de coleta
interpretavel e indicador de cache booleano. O motor calcula novamente a idade
a partir do relogio da fonte, rejeita horario futuro ou cotacao acima de 30 s e
exige concordancia entre as duas idades com tolerancia maxima de 5 s. Cache
curto continua permitido quando ambas as provas confirmam o frescor; o cache
nao e confundido com cotacao velha.

O SQLite repete essa verificacao antes do `INSERT`, de modo que chamadas fora
do fluxo oficial nao conseguem contaminar a trilha imutavel. A materializacao
do alerta registra a prova temporal e o criterio
`relogio_da_fonte_coerente`. A cadeia CLV V5/V14 tambem revalida odd, fonte,
idade, cache, horario futuro, expiracao e divergencia dos relogios, falhando
fechada mesmo quando o hash do payload estiver correto.

Antes da mudanca, as 1.289 cotacoes reais foram medidas: nenhuma tinha campo
temporal ausente ou invalido, o atraso observado ficou entre -0,859 s e 30 s e
a maior divergencia entre os relogios foi 0,998 s. Valores numericos nao
finitos (`NaN`/infinito) tambem sao recusados antes da persistencia. Depois da
mudanca, a cadeia real permaneceu integra com zero problemas em todas as novas
categorias. A suite completa passou em 2.400 testes.

## Ordem causal das cotacoes rapidas V13 — 10/09/2026

Uma evidencia append-only ainda pode chegar atrasada por retorno de API,
repeticao de fila ou ajuste do relogio do host. Se essa linha fosse tratada
como a cotacao atual, ela poderia simular movimento de preco, contaminar a
comparacao entre fontes e liberar uma entrada com informacao que ja pertencia
ao passado.

O registro rapido agora compara cada instante com o maior horario ja
persistido para o mesmo sinal. Uma regressao continua gravada, com estado
`nova_observacao_fora_de_ordem`, mas recebe
`ordem_temporal_valida=false`: nao conta como `mudanca_material`, nao participa
da comparacao de fontes e bloqueia o envio antes da materializacao do alerta.
Empates de horario sao validos e o `id` append-only preserva sua ordem.

A cadeia CLV V4 tambem percorre as evidencias por ordem de insercao e mantem o
maior horario por referencia. Assim, todas as linhas que continuem atras do
maximo causal sao detectadas, e uma unica regressao faz a avaliacao V13 falhar
fechada para qualquer conclusao de vantagem.

No banco real foram verificadas 1.289 cotacoes em 381 referencias: zero
regressoes e um empate de horario valido. A auditoria completa permaneceu
integra, com 10.254 observacoes imutaveis e fingerprint
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.
A suite completa passou em 2.395 testes.

## Integridade do conteudo das odds V12 — 10/09/2026

Gatilhos imutaveis impedem alteracoes futuras, mas nao provam sozinhos que o
conteudo inserido originalmente era coerente. A trilha de fontes possui um
SHA-256 do payload, e a avaliacao anterior nao o recalculava nem confirmava o
vinculo entre a referencia, o sinal, a partida, o mercado e a linha.

A cadeia CLV V3 agora reprocessa todas as evidencias imutaveis. Para cada
payload ela valida formato e correspondencia do SHA-256; para ofertas
monitoradas tambem confere data, JSON, referencia ao sinal, partida, mercado,
linha e fonte. Um unico conflito torna a cadeia insalubre e mantem
`pode_informar_edge=false`, mesmo quando os dez gatilhos existem e a coorte
seria estatisticamente suficiente.

No banco real, a V12 auditou 10.254 observacoes imutaveis, incluindo 1.289
ofertas monitoradas e 1.562 payloads. Foram encontradas zero inconsistencias
em todas as categorias. O fingerprint atual das evidencias e
`615f693a6b70141ef20f8772ba2353eee035619d53c485d9754bf5bcdd52d36b`.

A suite completa passou em 2.393 testes, incluindo corrupcao deliberada de
hash com bloqueio fail-closed. O PackBall permaneceu pausado, sem processo
ativo e sem Telegram real.

## Trajetoria append-only das fontes de odds — 10/09/2026

A cadeia V10 protegia o preco congelado no sinal, os snapshots e a tabela de
odds, mas a trilha direta `observacoes_fontes_odds` ainda atualizava no lugar a
ultima leitura quando a cotacao se repetia. No banco real havia 1.289 ofertas
monitoradas em 381 referencias. Uma repeticao futura podia deslocar o horario
da observacao anterior e apagar parte da sequencia temporal sem alterar o
preco.

Cada oferta monitorada agora gera uma linha append-only, inclusive quando o
preco se repete. O retorno separa `nova_linha` de `mudanca_material`, portanto
a telemetria continua contando somente mudancas reais de cotacao. A linha
`consulta_monitoramento`, que funciona apenas como cursor de rodizio e nao
contem uma cotacao, permanece compacta e atualizavel.

Dois gatilhos novos impedem update ou delete de toda evidencia de fonte que
nao seja esse cursor operacional. Partidas com observacoes auditaveis tambem
nao sao removidas pela limpeza depois que seus snapshots expiram. A avaliacao
CLV V11 passou a exigir dez gatilhos e confirmou a cadeia V2 integra no banco
real, com fingerprint
`263aa1224d79c534fee511a523788034411f2355bdde493fed1d48a5011ac138`.

A migracao foi precedida pelo backup verificado
`pre_migracao_20260910_013517.db`; o backup diario compactado tambem passou em
checksum, integridade SQLite e chaves estrangeiras. A suite completa passou em
2.393 testes. O PackBall permaneceu pausado e nenhum Telegram real foi enviado.

## Relatorio CLV autocontido e fail-closed V10 — 10/09/2026

O pre-voo ja recusava um banco sem os gatilhos obrigatorios, mas o relatorio
CLV podia ser executado isoladamente sobre uma copia SQLite sem essas
protecoes. Quando a coorte chegasse a 120 partidas, essa copia ainda poderia
apresentar uma conclusao estatistica sem provar que sua populacao e seus
precos permaneceram imutaveis.

A avaliacao V10 agora audita diretamente oito gatilhos que congelam entregas,
sinais, snapshots e odds. Ela valida a presenca, a operacao/tabela protegida e
o uso de abort no SQLite, alem de expor um fingerprint das definicoes. Uma
coorte completa pode ficar estatisticamente pronta, mas `pode_informar_edge`
permanece falso se essa cadeia de custodia estiver ausente ou invalida.

A prontidao profissional transforma essa condicao em falha tecnica e o status
mostra se a inferencia esta bloqueada. No banco real, os oito gatilhos foram
encontrados e validados, com fingerprint
`2bd47448ec48bb5d0e6e9143896b1276d8df5937a7d95ca8f037b79249e54111`.
A coorte continua em 0/120, formando amostra e sem informar edge.

A suite completa passou em 2.393 testes. O PackBall permaneceu em manutencao,
sem processo ativo e sem Telegram real.

## Cadeia de custódia de snapshots e odds CLV — 10/09/2026

O horizonte de valor pos-alerta dependia de snapshots e odds observados ate
dez minutos depois da entrega. A retencao antiga preservava o snapshot de
entrada ligado diretamente ao sinal, mas podia apagar as observacoes futuras
de apoio depois de 180 dias. Isso faria uma entrada antes comparavel voltar a
parecer sem cotacao futura e permitiria que o diagnostico CLV mudasse pela
limpeza do banco, nao por nova evidencia.

`snapshots` e `odds` agora sao append-only: qualquer `UPDATE` e rejeitado pelo
SQLite. A exclusao tambem e bloqueada para o snapshot de entrada e para toda
observacao da mesma partida coletada depois da entrega e em ate dez minutos,
incluindo suas odds. A rotina de retencao usa a mesma definicao de entrada CLV
e preserva esse conjunto permanentemente; snapshots antigos sem relacao com
uma entrega ou fora do horizonte continuam sendo removidos normalmente.

Os quatro gatilhos novos sao obrigatorios no pre-voo. A migracao aditiva do
banco real foi feita com manutencao ativa, apos o backup
`pre_migracao_20260910_011918.db`. Esse backup e o diario compactado
`monitor_20260910.db.gz` passaram em integridade SQLite, checksum e chaves
estrangeiras. O banco real ficou compativel, com 29 tabelas, nenhum objeto
obrigatorio ausente e zero violacoes de FK.

A suite completa passou em 2.390 testes. O PackBall permaneceu pausado e
nenhum Telegram real foi enviado.

## Imutabilidade da coorte CLV no SQLite — 10/09/2026

A coorte fixa V9 ainda dependia dos campos de `sinais` e
`entregas_alertas`. A prova do Telegram ja protegia o identificador da
mensagem, mas uma repeticao idempotente de `registrar_entrega_alerta` podia
substituir `tentado_em` e `entregue_em`. Alteracoes posteriores no horario,
mercado, linha, odd, snapshot ou `features_json` tambem poderiam reordenar ou
reclassificar uma unidade sem mudar o fingerprint da regra.

O SQLite agora congela toda entrega de entrada confirmada: identidade, canal,
horarios e status nao podem ser alterados nem a linha pode ser removida. Depois
de uma entrada entregue, o sinal correspondente tambem congela partida,
snapshot, horario, mercado, linha, odd e features. Notificacoes de resultado,
correcao, espera de odd e monitoramento permanecem fora dessa protecao de
coorte e conservam suas transicoes legitimas. Canais `:correcao` tambem foram
excluidos explicitamente da leitura de entradas CLV.

Uma confirmacao idempotente repetida continua aceita e incrementa a telemetria
de tentativas, mas preserva os primeiros horarios de entrega. Os quatro novos
gatilhos sao obrigatorios na auditoria de esquema. A migracao aditiva do banco
real foi aplicada com o bot pausado e antecedida pelo backup verificado
`pre_migracao_20260910_010920.db`; o backup diario compactado tambem passou em
integridade, checksum e chaves estrangeiras. O esquema final tem 29 tabelas,
zero gatilhos/indices ausentes e zero violacoes de FK.

A suite completa passou em 2.389 testes. Nenhum processo foi iniciado e nenhum
Telegram real foi enviado.

## Coorte causal fixa do valor pos-alerta — 10/09/2026

A avaliacao V8 ainda repartia todas as entregas em 70%/30% usando a quantidade
existente no momento da consulta. Quando novas partidas chegavam, unidades que
antes pertenciam ao holdout podiam migrar para desenvolvimento. Isso tornava a
validacao dependente do futuro e permitia reutilizar parte do teste na etapa de
descoberta.

A V9 pre-registra uma coorte exclusiva das primeiras 120 partidas produzidas
pela instrumentacao nova de cotacao. As unidades 1–84 formam desenvolvimento e
85–120 formam um holdout fixo. Os 880 registros legados ficam fora; entregas
posteriores a 120 permanecem auditaveis, mas nao mudam os membros nem o
fingerprint da coorte. O tamanho de 36 no holdout permite manter pelo menos 30
observacoes comparaveis mesmo com o piso de 90% de cobertura.

Historico amplo, ultimas 100 entregas, recortes por mercado/regra/fonte e cada
particao isolada sao agora explicitamente nao inferenciais. A coorte completa
somente pode informar uma revisao quando a cotacao de entrada e o horizonte
atingirem a cobertura minima e o efeito reaparecer com o mesmo sinal em
desenvolvimento e holdout. Mesmo assim, decisao automatica, gate operacional e
promocao permanecem proibidos.

A linha de base real e 0/120, com 120 unidades faltantes. A suite completa
passou em 2.387 testes. O PackBall permaneceu pausado, sem processo do monitor
e sem Telegram real.

## Reserva operacional da cotacao pos-alerta — 10/09/2026

O agendador ja identificava alertas entregues que precisavam de uma nova
leitura de preco entre dois e dez minutos depois. Em filas congestionadas,
entretanto, a segunda ordenacao privilegiava partidas ainda capazes de gerar
novos sinais e podia empurrar uma partida tardia para alem do pequeno lote que
o monitor realmente visita. Assim, a cotacao futura executavel era perdida
mesmo quando seu acompanhamento ainda estava dentro do prazo.

O monitor agora reserva uma unica vaga entre as tres primeiras tarefas para o
acompanhamento de preco mais proximo de expirar. A reserva vale tambem quando a
partida ja saiu da janela de novos sinais, preserva prioridades criticas de
rechecagem e nao aumenta o lote, as navegacoes nem a quantidade de alertas. Os
diagnosticos registram a quantidade disponivel, a idade do acompanhamento, sua
presenca no top 3 e se a partida ja estava fora da janela de sinais.

Essa mudanca serve somente para completar a evidencia prospectiva de CLV; ela
nao altera score, criterio de envio, odd de entrada, resultado ou promocao de
mercado. A suite completa passou em 2.383 testes. O PackBall permaneceu em
manutencao, sem processo de monitoramento e sem envio real ao Telegram.

## Cobertura prospectiva da cotação de entrada — 10/09/2026

O diagnóstico de CLV histórico possui 880 partidas independentes, mas somente
203 são comparáveis (23,07%). A principal perda vem de cotações de entrada
legadas ausentes ou ambíguas. Como a cotação completa e imutável passou a ser
gravada depois que o monitor entrou em manutenção, misturar o legado com as
próximas entregas esconderia a qualidade real da instrumentação nova.

A avaliação V8 agora abre uma coorte prospectiva somente quando encontra
`cotacao_entrada_clv_estado`, campo persistido antes do resultado. Ela mede,
no total e por mercado, quantas entradas possuem o par binário completo (ou as
três vias de próximo gol), quantas são inválidas ou incompletas e quantas se
tornam comparáveis após o horizonte. Os 880 registros anteriores ficam fora
desse denominador. A instrumentação só será considerada suficiente após 30
partidas independentes e pelo menos 90% de cotações congeladas válidas.

A linha de base real é 0/0 porque o bot segue pausado; isso é esperado e não é
apresentado como falha nem como edge. A coorte é apenas observabilidade:
`pode_informar_edge=false`, gate operacional desligado e promoção automática
proibida. O status e a prontidão passaram a mostrar seu progresso. A suíte
completa passou em 2.382 testes sem iniciar processos ou enviar Telegram.

## Calibração causal V9 — 10/09/2026

A calibração oficial escolhia a primeira ocorrência somente dentro das linhas
que já possuíam um resultado calibrável. Uma entrada inicial pendente, `void`,
`sem_dado` ou com retorno corrompido podia desaparecer, permitindo que uma
ocorrência posterior da mesma partida ocupasse seu lugar. Além disso, o corte
treino/validação era conferido pelo horário de encerramento, embora a decisão
tenha sido tomada no horário do sinal.

A política `calibracao-score-odd-wilson-duplo-auc-ic-coorte-causal-v9` passa a
fixar, para cada mercado e versão exata da regra, o primeiro sinal aprovado de
cada partida usando apenas dados conhecidos na exposição. A coorte oficial é
formada pelas primeiras 100 partidas: 70 de desenvolvimento e 30 de validação,
ordenadas por `criado_em`. Somente depois da seleção são anexados resultado e
retorno. Pendências e liquidações inválidas ocupam a posição e bloqueiam a
ativação; uma repetição posterior já vencedora não pode substituí-las.

Cada liquidação exige timestamp coerente, número finito e compatibilidade
financeira exata: `green=odd-1`, `half_green=(odd-1)/2`, `half_red=-0,5` e
`red=-1`. A entrada direta do calibrador também rejeita retorno ausente ou com
sinal financeiro incompatível, em vez de convertê-lo silenciosamente em zero.
O monitoramento de drift usa as últimas 300 decisões válidas, sempre mantendo
o primeiro sinal de cada partida; um alerta recém-criado e ainda pendente não
derruba o modelo, mas uma nova liquidação altera o fingerprint e exige
reconciliação.

O recálculo causal da regra-base histórica `sinais-v6` reprovou todos os
mercados. Em `gol_ft`, a validação fixa teve ROI -18,87%, AUC 0,3616 e limite
inferior AUC95 0,1621. Em `proximo_gol`, o ROI foi +7,53% e a AUC 0,6267,
porém o limite inferior AUC95 foi apenas 0,4253, abaixo do mínimo 0,50. Esses
resultados são diagnóstico do legado e não representam as versões operacionais
atuais.

As sete versões que o runtime realmente acompanha foram então reconciliadas
individualmente: `gol_ft` V11b e `gol_ht` V8c ainda têm 0 unidades;
`proximo_gol` V10f tem 8; `proximo_escanteio` V9c tem 30;
`escanteios_ft_asiatico` V9d tem 43 exposições, 39 decisões válidas e quatro
liquidações não calibráveis (dois `void` e dois `sem_dado`); os dois mercados
asiáticos por tempo têm 0. Todas as calibrações exatas permanecem inativas. O
watchdog confirmou frescor e partições íntegros, sem calibração desatualizada;
nenhuma regra foi promovida e nenhum Telegram foi enviado. A suíte completa
passou em 2.380 testes, com o PackBall em manutenção.

## Avaliação causal V6 do contexto avançado — 10/09/2026

A avaliação anterior aplicava os filtros de resultado, odd e contexto antes do
`ROW_NUMBER` que escolhia a primeira ocorrência da partida. Com isso, uma
primeira entrada pendente, inválida ou sem contexto podia desaparecer e uma
entrada posterior já vencedora assumir seu lugar. A janela móvel dos 300
últimos resultados também permitia que a conclusão mudasse conforme observações
antigas saíam do recorte.

A V6 fixa primeiro o sinal aprovado mais antigo de cada partida, sem consultar
liquidação, odd ou presença do contexto. Só depois valida odd, resultado e
retorno. `green`, `half_green`, `void`, `half_red` e `red` precisam ser
financeiramente coerentes com a cotação; qualquer pendência, `sem_dado`, valor
não finito ou retorno incompatível ocupa a posição e bloqueia o fechamento da
coorte. Contexto ausente continua como desconhecido, em vez de excluir a
partida e favorecer o segmento com melhor cobertura.

Cada mercado ganhou uma coorte cronológica imutável de 300 partidas: 210 para
desenvolvimento e 90 para holdout. Uma variável contextual só fica pronta para
revisão quando a coorte está totalmente liquidada, os grupos “com” e “sem” têm
ao menos 30 unidades tanto no desenvolvimento quanto no holdout, e o efeito
ajustado para múltiplas comparações (`z=3`) reaparece com o mesmo sinal nos dois
períodos e na amostra total. Aplicação e promoção automáticas permanecem
proibidas.

A persistência passou a usar um fingerprint do estado completo da coorte. Uma
liquidação tardia gera nova fotografia histórica mesmo quando nenhum sinal novo
foi criado. Os 955 registros das metodologias anteriores continuam íntegros,
mas não contam como V6 nem autorizam revisão; nenhum estava marcado como pronto.

As sete âncoras V6 das regras atuais foram pré-registradas no SQLite em
`2026-09-10T00:15:12`, todas com zero unidades, e agora possuem gatilhos que
impedem alteração ou exclusão. O diagnóstico legado corrigido encontrou apenas
8 partidas de Próximo Gol, 30 de Próximo Escanteio e 43 de escanteios FT
asiáticos; neste último, 41 liquidações são válidas e 2 permanecem `sem_dado`.
Não existe evidência suficiente para promover nenhum filtro contextual. A suíte
completa passou em 2.377 testes, sem iniciar o bot ou enviar alertas reais.

## Avaliação V2 da quarentena do fallback HT — 10/09/2026

A avaliação das linhas históricas de Gol HT foi refeita para remover seleção
pelo resultado. A primeira candidata elegível de cada partida fica congelada
antes da liquidação; se estiver pendente ou inválida, uma repetição posterior
já encerrada não pode substituí-la. A partida inteira é a unidade independente
e não pode aparecer simultaneamente no braço de linhas altas e no controle
`Over 0.5 HT`.

A população decisória também ficou imutável: primeiras 100 partidas de cada
braço, sendo 70 para desenvolvimento e 30 para holdout. Tudo depois da unidade
100 é apenas diagnóstico. `green`, `half_green`, `void`, `half_red` e `red`
somente entram no cálculo quando odd e retorno são finitos, válidos e coerentes
com o contrato. Pendência ou inconsistência bloqueia a revisão.

O legado V1 foi recalculado sem poder decisório. Após a âncora antiga existiam
185 registros brutos; 139 pertenciam à regra/status comparáveis e viraram 111
partidas independentes. Linhas altas: 32 partidas, ROI -5,41%, IC95
[-35,23%; +24,40%]. Controle: 79 partidas, ROI -19,01%, IC95
[-38,94%; +0,92%]. Não há coorte fechada de 100 nem holdout de 30 nos dois
braços, portanto o histórico não comprova vantagem nem prejuízo.

A metodologia `avaliacao-quarentena-fallback-ht-prospectiva-v2` ganhou âncora
própria no SQLite em `2026-09-10T00:04:56`, com zero unidades no marco. Ela
aceita somente a regra `sinais-v8c-gol-ht-principal-sombra-prospectiva-100` em
status `simulacao`. O watchdog rejeita V1, regra/status divergentes e âncora não
pré-registrada; o status mostra unidades independentes, decisões brutas,
liquidações e holdout. A quarentena continua ativa, sem reativação ou Telegram
automáticos. A suíte completa passou em 2.372 testes com o bot em manutenção.

## Avaliação V2 da prioridade sazonal de ligas — 09/09/2026

A avaliação da fila por liga deixou de tratar cada repetição do mesmo jogo em
ciclos sucessivos como observação independente. O grupo é congelado na primeira
exposição da partida: liga de maior score naquele ciclo ou controle pontuado.
Processamentos posteriores continuam no diagnóstico e na latência, mas não
estreitam o intervalo estatístico. O limite passou a selecionar ciclos inteiros,
evitando cortar um ciclo ao meio e reclassificar artificialmente sua prioridade.

Cada sinal também é vinculado a uma única decisão da fila. Oportunidade aprovada
que também gerou aviso de espera conta uma vez, e o ROI inclui somente resultados
de sinais acionáveis; simulações e auditorias não são mais apresentadas como
retorno da estratégia. A medida principal é agora a proporção de partidas
expostas que produziram ao menos uma oportunidade, com mínimo de 100 partidas e
30 oportunidades independentes em cada braço.

O período legado foi recalculado apenas como diagnóstico. As 11.712 decisões
brutas correspondem a 873 partidas: 108 atribuídas à prioridade e 765 ao
controle. A prioridade produziu 1 oportunidade (0,93%) e o controle 15 (1,96%);
delta de -1,03 ponto percentual, IC95 de -3,05 a +3,87. Os antigos 402 e 977
“resultados” incluíam candidatos não acionáveis; os totais comparáveis são 1 e
15, insuficientes para decisão.

A metodologia V2 ganhou uma âncora própria em `2026-09-09T23:48:46`, iniciada
com zero partidas. Estados V1 falham fechados no watchdog, o arquivo entrou na
assinatura transitiva do supervisor e o status mostra partidas independentes,
decisões brutas, oportunidades e IC95. A avaliação nunca reordena a fila ou
promove ligas automaticamente. A suíte completa passou em 2.366 testes com o
PackBall em manutenção.

## Auditoria V3 do histórico de escanteios asiáticos — 09/09/2026

O avaliador histórico de `escanteios_ft_asiatico` passou de `JOIN` obrigatório
para `LEFT JOIN` com a liquidação. Primeiro ele fixa a primeira entrada de cada
partida dentro de sua coorte e somente depois verifica resultado, odd, linha e
retorno. Uma entrada inicial pendente ou inválida continua ocupando sua posição
e bloqueia a revisão; uma duplicata posterior já resolvida não pode substituí-la.

A população decisória agora é imutável: no máximo as primeiras 100 partidas,
com as primeiras 70 em desenvolvimento e as 30 seguintes em holdout. A unidade
101 e posteriores ficam apenas no diagnóstico. O corte não depende de quais
resultados já chegaram. A validação também rejeita linhas que não sejam inteira,
quarto, meia ou três quartos e confirma que `green`, `half_green`, `void`,
`half_red` e `red` possuem retorno compatível com a odd do contrato.

No SQLite real há 204 candidatas e 202 liquidações brutas válidas. A coorte
oficial elegível mantém 41 partidas válidas. Entre as entradas realmente
entregues existem 27 partidas independentes: 25 válidas (20 greens, 1 void e
4 reds; ROI histórico +52,86%) e 2 com resultado `sem_dado`. Como ainda não
existem 70 unidades, todas permanecem no desenvolvimento e o holdout correto é
zero — o antigo recorte móvel de 7 jogos deixou de ser apresentado como prova.
O histórico continua somente diagnóstico; a decisão operacional usa a coorte
prospectiva fixa pós-âncora. O portfólio read-only foi versionado como V11 e
expõe a versão histórica V3. A suíte completa passou em 2.359 testes, com o
PackBall em manutenção e sem promoção automática.

## Auditoria V5 da estratégia de aguardar odd — 09/09/2026

A avaliação anterior misturava a cotação inicial do sinal, snapshots normais do
PackBall e até observações anteriores ao aviso com as cotações realmente
executáveis depois do alerta. Isso criava vazamento temporal e fazia a espera
parecer melhor do que foi. A V5 considera como chegada à faixa somente a
primeira cotação `api_rapida_sem_packball`, posterior ou igual ao horário do
aviso e na mesma linha. A unidade decisória é o primeiro aviso por partida e
mercado, evitando que alertas repetidos do mesmo jogo inflem a amostra.

Uma entrada oficial agora também exige linhagem explícita: o sinal posterior
precisa ter sido materializado pela versão compartilhada
`acompanhamento-odd-api-rapido-v1` e carregar o `origem_sinal_id` exato do aviso.
Um sinal comum posterior da mesma partida, mercado, linha e canal não fecha mais
a fila nem entra no relatório como conversão da espera. Mercado, linha, canal,
Telegram confirmado e ordem temporal continuam sendo conferidos em conjunto.

Reprocessamento real preservado em
`avaliacao_acompanhamento_odd_estado.json`: 180 oportunidades independentes em
179 jogos, 19 chegadas à faixa (10,56%) e somente 2 entradas oficiais com
linhagem comprovada, contra 26 associações pela consulta antiga. O retorno
hipotético da espera foi +1,96% por aviso, mas o IC95 bootstrap foi de -0,87% a
+4,29%; a diferença para a entrada imediata foi -5,88 pontos percentuais, com
IC95 de -9,62 a -1,50. Portanto, não há vantagem comprovada, promoção
automática ou alteração das regras de sinais. A revisão dirigida passou em 422
testes e a suíte completa em 2.342; o bot permaneceu em manutenção e sem
processos Python durante a correção.

## Auditoria V8 do desajuste executável — 09/09/2026

O recorte observacional da Bet365 passou a iniciar os cinco minutos de
seguimento somente no instante em que **as duas fontes** já eram conhecidas.
Uma cotação da própria casa coletada antes da chegada da referência não pode
mais confirmar persistência nem reversão. O seguimento exige também o mesmo
placar e minuto não anterior ao estado que originou a oportunidade.

Para impedir correlação e vazamento entre desenvolvimento e holdout, tanto o
recorte observacional quanto a convergência de gols conservam somente a primeira
oportunidade de cada partida. A hipótese de convergência foi reaberta como
`convergencia-preco-bet365-prospectiva-v2`, com definição imutável e nova âncora
registrada no SQLite em `2026-09-09T22:54:34`. A coorte estava zerada nesse
instante, portanto nenhuma observação futura foi escolhida ou descartada após
conhecer seu resultado.

O watchdog agora exige `avaliacao-desajuste-odds-prospectiva-v8`; versões
anteriores ficam como `metodologia_desatualizada` e não podem expor selo de
persistência ou vantagem. O status principal mostra candidatos, seguimentos,
persistências e decisões dos recortes executáveis, sempre com aplicação
automática desativada. A suíte completa passou em 2.345 testes. O bot permaneceu
em manutenção e nenhuma regra, calibrador ou alerta Telegram foi promovido.

## Auditoria V7 do valor pós-alerta — 09/09/2026

O agregado principal de `avaliacao_clv_live.py` passou a usar somente a primeira
entrega de cada partida, escolhida cronologicamente antes de saber se haverá
cotação futura comparável. Mercados diferentes do mesmo jogo continuam nos
recortes individuais, mas o agregado partida/mercado é explicitamente marcado
como correlacionado e não pode informar nem decidir edge. O mesmo vale para o
diagnóstico de todas as entregas.

O corte 70/30 agora é feito sobre todas as unidades independentes e só depois
mede comparabilidade dentro de cada parte. Assim, a disponibilidade futura da
cotação não move partidas entre desenvolvimento e holdout. O diagnóstico exige
ao menos 90% de cobertura para informar edge, além da amostra e do IC95; abaixo
disso, médias positivas ou negativas permanecem apenas números exploratórios.

Na base real, 999 entregas formaram 986 unidades partida/mercado e 880 partidas
independentes. Somente 203 partidas foram comparáveis, cobertura de 23,07%.
Portanto, a V7 registra `cobertura_insuficiente_para_informar_edge`, com
`pode_informar_edge=false` e `pode_decidir_edge=false`. A separação cronológica
ficou em 616 partidas de desenvolvimento e 264 de holdout. A suíte completa
passou em 2.349 testes; o PackBall permaneceu pausado e nenhum sinal foi
alterado ou enviado.

## Auditoria V10 do portfólio de edge — 09/09/2026

O portfólio não descarta mais resultados pendentes antes de escolher sua
unidade independente. A primeira entrada entregue de cada partida é fixada
primeiro; só depois são conferidos resultado, retorno, odd e linhagem. Portanto,
uma duplicata posterior já resolvida não pode substituir retroativamente a
entrada inicial pendente. Resultado ausente ou inválido bloqueia a decisão.

Entradas oficiais, simulações genéricas e cada versão sombra agora formam
coortes separadas. O avaliador escolhe explicitamente a coorte operacional e
nunca soma métodos diferentes para completar amostra, ROI ou intervalo de
confiança. Cada coorte-base usa no máximo suas primeiras 100 partidas: 70 de
desenvolvimento e 30 de holdout. Entradas posteriores ficam fora da decisão,
preservadas apenas para diagnóstico.

Na base real, `proximo_gol` selecionou a coorte `aprovado`, com 3 partidas
válidas, e `proximo_escanteio` selecionou `aprovado`, com 16. Ambos permanecem
em `aguardando_amostra`; gols HT/FT usam seus validadores prospectivos próprios
e escanteios asiáticos continuam na coorte fixa pós-âncora. Nenhum mercado foi
considerado favorável e a promoção automática segue proibida. O status expõe
versão, decisão e coorte escolhida. A suíte completa passou em 2.355 testes,
sem iniciar o PackBall ou enviar Telegram.

## Auditoria V2 da referência histórica sem vig — 09/09/2026

`avaliacao_probabilidade_sem_vig.py` agora preserva todas as candidatas com
`LEFT JOIN`, fixa a primeira unidade de cada partida e coorte de seleção e só
então consulta resultado, retorno e mercado completo. Estados sucessivos de
“próximo gol” da mesma partida deixaram de ser tratados como jogos
independentes. Uma primeira unidade pendente não pode ser substituída por uma
posterior já resolvida.

O selo descritivo exige simultaneamente uma única coorte de seleção, resultados
independentes completos, dados válidos, pelo menos 100 partidas, IC95 positivo
para ROI e resíduo contra o preço sem vig e cobertura mínima de 90%. O
portfólio V10 expõe explicitamente que usa
`avaliacao-probabilidade-sem-vig-historica-v2` como referência; a camada segue
somente leitura e sem poder de promoção.

No histórico real de `proximo_gol`, 1.481 candidatas brutas viraram 671 unidades
partida/coorte; 14 primeiras unidades estão sem resultado válido, a cobertura é
85,08% e há três populações diferentes (`aprovado`, `auditoria` e
contrafactual). Logo, nenhuma vantagem é declarada. Em `proximo_escanteio`, há
30 partidas homogêneas e cobertura de 100%, ainda muito abaixo das 100 exigidas.
A suíte completa passou em 2.356 testes. O bot continuou em manutenção, sem
processos e sem alertas reais.

## Instalação reproduzível em outra máquina

Use Python 3.11 ou superior e instale exatamente o ambiente validado:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m playwright install msedge
```

O arquivo `requirements.txt` fixa as três dependências diretas do projeto; o
`requirements.lock.txt` fixa também as dependências transitivas. O pré-voo
compara as 12 versões instaladas com o lock e bloqueia um reinício quando há
pacote ausente, versão divergente, lock inválido ou Python anterior ao 3.11.
Credenciais, sessão PackBall, banco e arquivos `.env` não pertencem ao pacote
de instalação e devem ser transferidos por procedimento seguro separado.

## Conferência dinâmica da lista Ao Vivo

Cada linha extraída precisa exibir explicitamente minuto, intervalo ou marcador
de jogo ao vivo. Linhas encerradas e linhas sem estado reconhecível são
descartadas; jogos adiados ou futuros nunca completam artificialmente o
contador. O coletor compara a quantidade extraída com o contador da aba Ao Vivo
e repete a leitura uma única vez quando houver divergência.

Uma diferença de exatamente uma partida pode ser aceita somente na segunda
leitura, quando todas as linhas extraídas continuam explicitamente ao vivo. Isso
representa a transição normal de uma partida entrando ou terminando entre as
duas leituras e fica registrada como
`transicao_dinamica_status_explicito`. Diferenças maiores permanecem bloqueadas;
o limite não deve ser ampliado para ocultar falha de seletor ou carregamento.

Quando a divergência persiste, o diagnóstico guarda apenas título e texto dos
estados excluídos, sem cookies, armazenamento local, senha ou bearer. Um estado
legítimo novo só pode ser incorporado depois de observado e coberto por teste.
Em 01/08/2026, após reinício controlado, dois ciclos consecutivos confirmaram
39 partidas no contador e 39 extraídas; o segundo encerrou com API saudável e
nenhum bloqueio de fonte.

Ainda em 01/08/2026, o histórico real revelou o formato de acréscimos usado
pelo PackBall, como `94(5) '`, `48(2) '` e `96(9) '`. Esses valores representam
partidas em andamento e agora são aceitos tanto pelo extrator quanto pelo
diagnóstico. O título explícito `O jogo foi interrompido` continua excluído.
Após a correção, dois novos ciclos fecharam em 36/36 e 34/34; o segundo teve
API saudável e nenhum bloqueio. A suíte passou a 891 testes.

O contador visível pode incluir partidas com o título explícito
`O jogo foi interrompido`. O diagnóstico contabiliza essas linhas à parte e a
consistência usa `contador_ao_vivo_efetivo`, descontando somente interrupções
comprovadas. O contador bruto continua no log. Estados ambíguos não recebem o
desconto e continuam fechando o ciclo. A regra cobre inclusive duas ou mais
interrupções simultâneas; a suíte passou a 894 testes e o primeiro ciclo após o
reinício fechou normalmente em 34/34, sem bloqueios.

O relatório `auditoria_sistema.py` separa o estado atual da fila Telegram do
histórico de transições. Uma tentativa bem-sucedida mantém a intenção
`enviando` e a prova `entregue` como registros históricos distintos, mas a
fila atual considera somente a transição mais recente de cada par
`sinal_id/canal`. Assim, intenções já confirmadas não aparecem como mensagens
presas; o histórico completo continua preservado e auditável.
O campo `entregas_transitorias_superadas` conta explicitamente essas intenções
com prova final posterior. Já `integridade_telegram.envios_incertos` conta
somente tentativas sem desfecho após a tolerância. A auditoria profissional
agora incorpora toda a integridade Telegram em `saudavel`: entrega incerta,
erro persistente, confirmação inválida, resultado sem aviso ou duplicidade
degrada o relatório em vez de ficar escondida no histórico bruto.

Canais internos `gateway:*` não são entregas Telegram. Seus estados
`bloqueado` e `filtrado` aparecem em `decisoes_gateway`, separados da
`fila_telegram`. Dessa forma, a fila real mede apenas comunicações com o
provedor, enquanto decisões preventivas continuam disponíveis para auditoria.

Notificações operacionais novas guardam também um `resumo` curto e seguro,
formado somente pela primeira linha. Padrões de token, chave e senha são
redigidos antes da gravação; o corpo completo nunca é persistido nessa coluna.
Assim, `resolver_notificacao_operacional.py` consegue mostrar qual aviso deve
ser conferido quando a entrega ficar incerta, sem armazenar credenciais ou
conteúdo integral. Registros antigos permanecem intocados e podem ter resumo
ausente.

A mesma auditoria distingue snapshots de encerramento sem estatísticas de uma
falha de estatísticas durante o jogo. Fechamentos vindos da API podem conter
somente placar e status final, pois servem exclusivamente à liquidação. Eles não
são contados como falha da coleta ao vivo. Em 01/08/2026, os quatro snapshots
sem estatísticas das últimas 24 horas eram todos de finalização; a contagem
`ao_vivo_sem_estatisticas` ficou em zero.

## Pontuação candidata prospectiva

A pontuação `pontuacao-sombra-logistica-v1` é apenas um experimento
prospectivo. Quando um mercado alcança 60 resultados independentes, o watchdog
congela no SQLite um modelo treinado com aquele histórico e registra o último
`sinal_id` usado. Somente resultados de sinais posteriores entram na validação.

O modelo não muda a V6/V7, não filtra simulações, não libera mercado oficial e
não envia alertas por conta própria. Uma revisão humana só pode ser considerada
depois de pelo menos 30 resultados futuros e evidência de discriminação fora da
amostra. A avaliação V2 exige simultaneamente limite inferior de 95% da AUC
acima de 0,50, melhora mínima de 0,05 sobre a nota atual e Brier não pior que a
probabilidade implícita da odd. O painel mostra AUC e Brier da candidata ao lado
dos respectivos controles, incluindo explicitamente o limite inferior AUC95.
O mesmo detalhamento é apresentado para os challengers contextual e temporal
5/10/15, evitando que um estado inconclusivo apareça sem seu gate decisório.

A calibração oficial é reconciliada ao fim de cada ciclo somente quando a
amostra persistida diverge da calibração registrada. Isso inclui modelos ainda
inativos: se o resultado que completa a meta for salvo e uma falha ocorrer antes
da recalibração, o ciclo seguinte refaz a transição automaticamente. Modelos já
atuais não são regravados.

O watchdog reconhece a janela normal entre a gravação de um resultado e essa
reconciliação. Se o ciclo estiver ativo e o resultado tiver menos de cinco
minutos, registra `reconciliacao_em_andamento` sem enviar alerta ao Telegram.
Ao terminar o ciclo a calibração deve ficar atual; se o ciclo já tiver acabado
ou o atraso ultrapassar cinco minutos, a inconsistência volta a ser crítica e
gera o alerta normal. A tolerância reduz ruído sem esconder falha persistente.

O pré-voo faz a mesma comparação em modo somente leitura. Se encontrar apenas
uma calibração atrasada, marca `requer_reconciliacao_no_inicio` e permite a
partida corretiva; o monitor a atualiza durante `preparar()`, antes de abrir o
navegador. Falha de leitura do banco ou qualquer outra verificação do pré-voo
continua bloqueando o início.

## Reserva adaptativa do ciclo

Antes de iniciar outra partida, o monitor compara o tempo restante do orçamento
com o percentil 90 das últimas 30 durações reais e uma margem de três segundos.
Se a próxima leitura provavelmente ultrapassaria o orçamento, ela permanece na
fila sem ser marcada como concluída. Ao menos a primeira tarefa do ciclo sempre
é permitida. O log registra a reserva estimada e se ela encerrou a coleta
detalhada, permitindo medir velocidade e cobertura sem aumentar a frequência de
navegação no PackBall. As durações individuais ficam no log estruturado e são
restauradas no próximo início. Enquanto ainda existirem apenas registros
antigos, o percentil 95 histórico é usado como estimativa conservadora; valores
inválidos, negativos ou não finitos são ignorados.

## Iniciar

No PowerShell, dentro da pasta do projeto, a forma recomendada é:

```powershell
.\.venv\Scripts\Activate.ps1
python iniciar_sistema.py --retomar-manutencao
```

Para uma parada planejada, não encerre os processos à força. Execute:

```powershell
python parar_sistema.py
```

O pedido fica persistido em `modo_manutencao.json`. O monitor termina o ciclo
em andamento, fecha o navegador e tanto ele quanto o watchdog encerram sem
autorreinício. Para liberar a manutenção e retomar os dois processos, execute:

```powershell
python iniciar_sistema.py --retomar-manutencao
```

Durante ciclos longos, o monitor grava batimentos por etapa e após cada partida
detalhada. O watchdog considera a coleta ativa somente enquanto esse progresso
for recente; um batimento com mais de dois minutos ou uma falha posterior não
mascara uma coleta parada. O status mostra a etapa e a idade do último
progresso enquanto o ciclo está em andamento.

Um arquivo de manutenção ilegível é tratado de forma conservadora como pausa
ativa. Isso evita que uma gravação interrompida provoque reinícios inesperados.

Executar `python iniciar_sistema.py` sem a opção explícita não remove uma pausa
manual. Depois do preflight, qualquer falha ao abrir um componente ou qualquer
processo que não permaneça ativo e com trava por 12 segundos restaura
atomicamente a manutenção com o motivo `rollback_inicio_instavel`. Assim, a
tarefa automática não entra em ciclo de tentativas depois de uma retomada
incompleta.

Esse comando é idempotente: verifica as travas exclusivas e os PIDs, inicia o
watchdog oculto e abre o monitor/navegador visível somente quando estiverem
ausentes. Pode ser executado novamente sem criar cópias duplicadas.
Em uma partida a frio, o monitor é iniciado primeiro. O watchdog concede até
cinco minutos somente ao PID recém-aberto e apenas até o primeiro ciclo
concluído, evitando alerta falso de log antigo sem mascarar uma inicialização
realmente travada.

## Recuperação após reinício do Windows

O projeto inclui uma tarefa automática opcional que executa uma verificação a
cada cinco minutos enquanto o usuário está conectado. A verificação é
idempotente: se monitor e watchdog já estiverem ativos, não cria cópias; se os
dois tiverem parado ou o computador tiver reiniciado, abre novamente o monitor
com sua janela visível e o watchdog oculto.

Consulte o estado sem modificar o Windows:

```powershell
python autostart_windows.py --status
```

Depois de autorizar a alteração no Agendador de Tarefas, instale com:

```powershell
python autostart_windows.py --instalar
```

Para desfazer completamente:

```powershell
python autostart_windows.py --remover
```

A tarefa roda com privilégios limitados, somente na sessão interativa do
usuário, e chama `iniciar_automatico.py` por `pythonw.exe`, sem abrir um terminal
temporário a cada verificação. Cada execução grava resultado ou falha em
`autostart_ultima_execucao.json`. `status_bot.py` mostra se a recuperação está
instalada; preparar os arquivos não altera sozinho o Agendador do Windows.
O instalador também desativa as duas restrições padrão de energia do Agendador:
a tarefa pode iniciar e continuar quando o computador estiver usando bateria.
A instalação só é confirmada depois de consultar o XML real e validar ação,
intervalo, sessão, privilégio e essas duas opções de energia.
Cada execução agendada repete essa consulta diretamente e inclui no heartbeat
`autostart-heartbeat-v2` a prova do intervalo e das opções de bateria. Uma
consulta que apenas reaproveite o próprio heartbeat é recusada para evitar
evidência circular. Assim, mesmo quando o painel não possui permissão para
consultar o Agendador, ele comprova separadamente a execução e a definição.

Quando o processo desaparece e a coleta fica parada, o pré-voo de recuperação
considera essa condição recuperável e permite o reinício. Todos os demais
controles continuam obrigatórios: sessão, proteção do PackBall, banco,
integridade do Telegram, linhagem, backup, armazenamento e contador da API.
Uma recusa grava também a lista exata de verificações que impediram a retomada.
O painel só considera a execução agendada saudável quando houve sucesso ou uma
recusa protetiva esperada (manutenção manual ou cooldown do PackBall); uma
recusa por falha real de pré-voo não pode mais parecer uma recuperação válida.

No final do painel, a linha `escanteios asiáticos FT` separa explicitamente a
disponibilidade da fonte da liberação do mercado. Ela mostra as ofertas reais
anexadas pelo bet 32 da API-Football, a última evidência, a amostra independente
resolvida e quantos resultados ainda faltam. Fonte comprovada não substitui
calibração: o sinal oficial permanece bloqueado até o gate estatístico.

O mercado `escanteios_ft_asiatico` usa a versão prospectiva própria
`sinais-v7-ft-asiatico`. Ela considera a idade da oferta API-Football realmente
escolhida, sem herdar a idade do cache de outro mercado do PackBall. Ofertas
com mais de seis minutos continuam bloqueadas. A regra geral `sinais-v6` e suas
amostras de gols permanecem intactas; status, calibração e linhagem selecionam
a versão ativa pelo mercado.

Para iniciar apenas o monitor manualmente:

```powershell
.\.venv\Scripts\Activate.ps1
python monitor_ao_vivo.py
```

O navegador permanece visível. `Ctrl + C` interrompe aquela instância, mas o
watchdog poderá recuperá-la; para encerrar todo o sistema corretamente, use
`python parar_sistema.py`.
O comando `python status_bot.py` também informa `código=reinício pendente`
se os arquivos do monitor ou do watchdog forem modificados depois que o
respectivo processo iniciou. Cada componente tem uma assinatura SHA-256 própria
das dependências que realmente carrega.

## Sinais de simulação durante a calibração

Com `SINAIS_TESTE_ATIVO=1`, candidatos tecnicamente aprovados e com odd válida
podem ser enviados antes da calibração. Toda mensagem começa com
`🧪 SIMULAÇÃO — NÃO APOSTAR`, mostra nota técnica como algo diferente de
probabilidade e informa que ainda não existe confiança histórica calibrada.
Simulações usam controle de duplicidade e limite diário próprios, não consomem
o limite nem a exposição dos alertas oficiais e não liberam apostas automáticas.
O limite operacional atual é de 30 simulações por versão da regra por dia e 45
somando todas as versões. Assim, uma regra nova conserva espaço para teste mesmo
quando a anterior já enviou mensagens, mas nenhuma troca de versão cria volume
ilimitado. O limite oficial continua independente e conservador em 10 sinais
calibrados por dia. Esses tetos são configurados por
`LIMITE_DIARIO_SINAIS_TESTE` e `LIMITE_GLOBAL_SINAIS_TESTE`.
Dentro desses tetos, o Telegram envia no máximo uma simulação por combinação de
partida, mercado e versão da regra. Novas leituras da mesma combinação continuam
persistidas para evolução/auditoria, mas não gastam outra vaga diária.
Somente a primeira decisão tecnicamente aprovada dessa combinação pode se tornar
simulação. Uma leitura posterior nunca substitui a primeira apenas por ter nota
maior ou porque a cota estava cheia naquele instante. Registros históricos que
não obedeciam a essa regra permanecem no banco, mas ficam explicitamente
excluídos das métricas de acerto e ROI.
Cada simulação recebe liquidação green/red pelo mesmo backtest. Quando ela usa
uma leitura duplicada, fica com status `simulacao`: seu resultado aparece no
acompanhamento de testes, mas não aumenta a amostra da calibração oficial.
Depois da liquidação, o Telegram envia uma atualização idempotente com GREEN,
RED, meio green/red, devolvida, anulada ou sem dado e o retorno hipotético.
A atualização também informa o placar e o status usados na liquidação, a fonte
que confirmou o resultado e o horário da confirmação. Assim, o green/red pode
ser conferido sem depender apenas da mensagem de entrada.
Os textos enviados ao usuário traduzem os códigos internos de mercado, status,
fonte e motivos técnicos. Os códigos originais continuam preservados no SQLite
para auditoria, mas não aparecem como nomes crus no Telegram.
A mesma mensagem mostra o placar acumulado de GREEN/RED e o índice de acerto
calculado sobre resultados decididos, tanto no total quanto no mercado da
entrada. Simulações e sinais oficiais usam placares separados.
Mercados de total (`gol_ft`, `gol_ht` e over de escanteios) só são liquidados
depois do encerramento confirmado do jogo ou do período correspondente. Isso
evita falso green quando um gol é anulado ou o placar/estatística é corrigido.
O mercado `proximo_gol` também aguarda o encerramento da partida para confirmar
pelos eventos finais qual foi o primeiro gol válido depois da entrada; um gol
provisório anulado pelo VAR não pode definir o backtest.
Se uma liquidação histórica prematura for encontrada, o registro anterior é
preservado em `revisoes_resultados`, o sinal volta a ficar pendente e uma
mensagem de correção é enviada uma única vez para a simulação afetada.
O SQLite proíbe alterar diretamente uma liquidação. A exclusão só é aceita
quando já existe uma revisão correspondente a todos os valores anteriores,
inclusive `snapshot_id_liquidacao` e `fonte_resultado`. Esses campos históricos
e o motivo da revisão tornam-se imutáveis; apenas o estado de sua notificação
Telegram pode avançar. Revisões anteriores à implantação permanecem válidas.
Mensagens de entrada, resultado e correção exibem a versão da regra para que
cada decisão possa ser ligada à população correta do backtest.
`TELEGRAM_CHAT_ID_TESTE` pode apontar para um canal separado; quando ausente,
o bot usa o canal correspondente ao mercado mantendo o rótulo de simulação.
Se a API-Football devolver uma resposta vazia, inválida ou pertencente a outro
fixture, o ciclo continua, a ocorrência fica registrada como aviso e a partida
só volta a ser consultada depois do cooldown. Nenhum resultado é presumido.
Mesmo quando o `fixture_id` já está persistido, o finalizador reconfirma os dois
times e sua orientação na resposta final. Divergência bloqueia a liquidação e
fica como `erro_associacao`; o status e a auditoria também revalidam
retroativamente os nomes gravados em toda evidência API usada pelo backtest.
Na associação ao vivo, fixtures compatíveis são ordenadas por nomes, placar e
minuto. Se as duas melhores ficarem separadas por menos de 0,03, nenhuma é
aceita: a API fica ausente naquela leitura e o PackBall continua como fonte
principal. Respostas repetidas do mesmo `fixture_id` são deduplicadas antes de
calcular essa margem.
Antes do placar e do minuto, o pareador também exige categoria compatível nos
dois times. Marcadores femininos e faixas U15–U23 precisam coincidir entre
PackBall e API-Football. Assim, um jogo `U23` não pode herdar estatísticas do
time principal apenas porque os nomes, o 0–0 e o minuto são parecidos. Aliases
como `Sydney U20`/`Sydney FC U20` continuam permitidos por permanecerem na mesma
categoria. A rejeição é registrada como `categoria_equipes_incompativel`.
Cada snapshot conserva em `qualidade_json.associacao_api` o motivo e as
contagens do pareamento. O evento `ciclo_concluido` agrega `associado`,
`sem_fixtures`, `nomes_incompativeis`, `categoria_equipes_incompativel`, `placar_incompativel`,
`minuto_incompativel`, `associacao_ambigua` ou eventual erro. O painel mostra o
funil do último ciclo, permitindo distinguir falta normal de cobertura de uma
mudança súbita no formato ou na correspondência da fonte externa.
O watchdog compara três ciclos recentes com até vinte ciclos anteriores. Só
avisa queda de cobertura depois de volume mínimo e quando a taxa recente cai
para menos de um quarto de uma linha de base que antes associava ao menos 30%.
Três erros de processamento ou ambiguidade em metade de dez associações
comparáveis também geram aviso. Sem linha de base suficiente, o estado permanece
`formando_linha_de_base`, sem falso alarme e sem bloquear o PackBall.

Se nenhuma fonte conseguir produzir um estado final, a pendência somente vira
`sem_dado` depois de 72 horas, pelo menos seis tentativas e passagem por todas
as fontes esperadas. Esse resultado fica auditável, com retorno nulo, e não
entra nas métricas nem na calibração.

Para executar somente um ciclo de diagnóstico sem abrir janela:

```powershell
python monitor_ao_vivo.py --uma-vez --headless
```

## Consultar o estado

```powershell
python status_bot.py
```

Esse comando mostra volumes do banco, resultados avaliados, alertas entregues,
estado da calibração, último ciclo registrado e backups disponíveis.
Também resume separadamente as simulações por mercado: quantidade entregue,
resultados pendentes, greens, reds, taxa observada e ROI hipotético. Esses
números não são tratados como confiáveis enquanto a amostra for pequena.
As métricas experimentais usam no máximo um resultado por partida e mercado.
Mensagens repetidas da mesma partida continuam aparecendo em
`resolvidos_brutos`, mas não aumentam `n_independente` nem a taxa de acerto.
O experimento do filtro compara as simulações que passaram pelos limites com
as decisões descartadas, usando no mínimo 30 resultados em cada coorte. Além
dos deltas de acerto e ROI, o status mostra o intervalo de 95% da diferença.
Na versão `filtro-simulacoes-v2`, todos os candidatos aprovados e
pré-calibração da mesma leitura são avaliados antes do resultado: somente o de
maior nota pode seguir para o Telegram, mas cada candidato independente que
falhar nota ou qualidade recebe imediatamente um registro
`gateway:teste/filtrado`. Isso evita que a coorte descartada fique invisível
quando outro mercado da mesma partida foi o escolhido para envio. Candidatos
antigos nunca são preenchidos retroativamente.
Ele só marca `evidencia_favoravel` quando o ROI das enviadas é positivo, o
intervalo inteiro do ganho de ROI fica acima de zero e o acerto não apresenta
degradação. O diagnóstico nunca altera o filtro automaticamente.
As duas coortes exigem também o fingerprint exato da regra ativa. Decisões
legadas são preservadas no banco, mas não entram na comparação; uma decisão
posterior ao marco do experimento sem essa linhagem torna a auditoria
incompatível até a causa ser corrigida.
Uma nova versão do experimento abre um marco prospectivo próprio. A auditoria
reconhece os marcos anteriores para preservar o histórico, mas usa somente
decisões posteriores ao início da versão vigente.
O relatório de prontidão separa esse marco íntegro da eficácia comprovada. Com
menos de 30 resultados resolvidos em qualquer coorte, mostra
`pendente_amostra`; depois disso, somente `evidencia_favoravel`, incluindo os
intervalos de 95%, permite marcar o componente como `pronto`. A simulação e sua
liquidação continuam funcionando durante a coleta dessa evidência.
O watchdog acompanha essa transição. Ao atingir a amostra mínima, envia uma
única conclusão administrativa com as duas amostras, deltas e IC95. Se a
conclusão mudar posteriormente, envia a nova situação uma vez. Reiniciar o
processo não repete a mensagem, pois a assinatura notificada é preservada no
JSON e no SQLite. Essa rotina nunca modifica os limites do filtro.

### Diagnóstico isolado do TotalCorner

O TotalCorner é somente um candidato para comprovar odds asiáticas de
escanteios do primeiro tempo. Ele permanece fora do monitor, da calibração e
da prontidão. Para executar a prova, adicione temporariamente ao `.env`:

```text
TOTALCORNER_API_TOKEN=seu_token
```

Depois execute:

```powershell
python diagnostico_totalcorner.py
```

O comando faz exatamente uma consulta HTTPS à lista ao vivo, solicitando apenas
`cornerLineHalf`. O token nunca é escrito no relatório ou mostrado no
terminal. O resultado sanitizado fica em `totalcorner_diagnostico.json`, com
os campos de cantos, limites informados pelo provedor e eventuais candidatos
estruturais de sete posições. Linhas com três opções não são aceitas.

Mesmo quando encontra linha, Over e Under, o relatório mantém
`habilita_integracao_automatica=false`. Uma resposta real precisa ser revisada
antes de criar o adaptador, porque a documentação pública omite o exemplo de
`corner_half_list`. Sem token, o comando termina antes da rede. Não existe
retry automático, paginação ou chamada por partida.

### Diagnóstico offline da LSports para escanteios 2T

A documentação oficial da LSports é o primeiro candidato encontrado que lista
`2nd Half Corners Over/Under` com in-play e settlement. Isso ainda não comprova
que o pacote contratado entregará o mercado, seus provedores e sua liquidação
nas ligas do PackBall. Não inserir credenciais no projeto e não contratar antes
de receber uma amostra/trial real e o mapeamento escrito dos enums.

Salve a exportação recebida fora do `.env` em um objeto JSON com três campos:

```json
{
  "contrato": {
    "formato_preco": "decimal",
    "status_ativos": ["valor informado pelo provedor"],
    "status_liquidado": 3,
    "settlement_vencedor": ["valor informado pelo provedor"],
    "settlement_perdedor": ["valor informado pelo provedor"],
    "settlement_reembolso": ["valor informado pelo provedor"],
    "origem_mapeamento": "referência escrita do contrato/trial"
  },
  "snapshot": {},
  "liquidacao": {}
}
```

`snapshot` e `liquidacao` recebem as mensagens JSON originais correspondentes
ao mesmo fixture, mercado, linha e bets. Depois execute:

```powershell
python diagnostico_lsports_escanteios_2t.py `
  --entrada "C:\caminho\amostra_lsports_2t.json"
```

O comando é somente leitura, não usa rede, não lê `.env` e não grava o payload
bruto nem a referência textual do contrato no relatório. Em vez disso, grava
SHA-256 e tamanho da amostra, além do SHA-256 da referência dos enums, para
preservar proveniência sem expor o documento. Ele aceita apenas futebol com
fixture, liga e dois times
identificados; nome inequívoco de escanteios Over/Under do segundo tempo;
market/provider/bet IDs; duas opções na mesma linha e `BaseLine`; preço decimal,
status e `LastUpdate` válidos; e liquidação correspondente. Estar no segundo
tempo não transforma uma linha FT em 2T. `Exactly`, corrida, handicap de time,
terceira opção, linha divergente, suspensão ou enum sem origem falham fechados.
O cabeçalho da mensagem também é obrigatório: a atualização deve ter no máximo
15 minutos no instante do snapshot, a liquidação deve usar o tipo oficial `35`
e ocorrer cronologicamente depois da oferta. Isso impede que replay antigo seja
confundido com cotação ao vivo.

O arquivo `lsports_escanteios_2t_diagnostico.json` sempre mantém
`habilita_integracao_automatica=false`. Uma prova completa permite apenas
projetar uma coleta em sombra com cota, cache, circuit breaker, proveniência no
SQLite e nova calibração prospectiva; não libera alertas nem apostas.

### Bet365 como possível fonte complementar

`bet365_odds.py` contém somente o contrato de validação da futura fonte pública.
Ele exige correspondência exata dos dois times e da orientação, linha asiática
em quartos, odds decimais válidas e os dois lados Over/Under na mesma linha.
Mercados `Exactly`, corrida, handicap de time, opções suspensas, duplicadas ou
incompletas falham fechados. FT, 1T e 2T permanecem separados.

Essa fonte não participa do monitor, da calibração nem da prontidão enquanto a
página interna do evento não carregar de forma repetível e uma oferta real não
for persistida com evento, URL e horário. O adaptador não faz login, não realiza
aposta e nunca substitui silenciosamente PackBall ou API-Football.

As tentativas futuras serão gravadas em `observacoes_fontes_odds`, inclusive
quando o jogo não for encontrado, o painel não carregar, o mercado estiver
ausente/bloqueado ou a oferta for rejeitada. O status mostra contagens e a
última observação da Bet365 sem confundir o adaptador preparado com uma fonte
ativa ou comprovada. A tabela e seu índice fazem parte do contrato verificado
do banco e dos backups restauráveis.

O mesmo painel mostra os motivos e audita todo o histórico Bet365. Estado ou
período desconhecido, timestamp inválido/futuro, JSON corrompido, payload em
observação negativa ou oferta marcada como válida sem evento, times, URL,
bookmaker e pares Over/Under íntegros tornam a auditoria `inconsistente`.
`comprovada=sim` exige ao menos uma oferta válida que passe por todos esses
controles; a existência de tentativas não basta.

Para observar uma partida específica uma única vez:

```powershell
python diagnostico_bet365_controlado.py `
  --mandante "Time A" `
  --visitante "Time B"
```

O diagnóstico abre uma janela pública, faz uma navegação para a lista e no
máximo um clique no evento. Ele exige os dois nomes exatos e na mesma
orientação. Texto de mercado encontrado ainda é gravado como
`estrutura_dom_aguardando_mapeamento`, nunca como oferta válida. Bloqueio ou
verificação humana encerra a tentativa; não há retry automático.
Depois do clique, o diagnóstico exige que os dois times selecionados apareçam
no painel. Se a URL mudar mas o conteúdo continuar mostrando outro evento, a
tentativa fica como `painel_nao_carregou`, com o motivo
`evento_selecionado_nao_substituiu_painel`; ela nunca é interpretada como
ausência de mercado. A primeira observação real desse estado foi persistida em
25/07/2026 para `LAFC x Kansas City`, sem ativar a fonte.

Quando o usuário abrir o evento e o mercado manualmente, a captura pode ser
registrada sem depender do painel automatizado:

```powershell
python registrar_bet365_manual.py `
  --mandante-packball "Time A" `
  --visitante-packball "Time B" `
  --mandante-bet365 "Team A" `
  --visitante-bet365 "Team B" `
  --url-evento "https://www.bet365.bet.br/#/IP/EV123456C1" `
  --periodo "2T" `
  --mercado "Escanteios Asiáticos - 2º Tempo" `
  --linha "5.5" `
  --odd-over "1.80" `
  --odd-under "1.90" `
  --evidencia "C:\caminho\captura.png"
```

O arquivo precisa ser PNG, JPG ou WEBP e ter no máximo 15 MB. Ele é copiado
para `evidencias_bet365`, identificado por SHA-256 e vinculado à partida,
evento, URL, período e oferta. O registro recebe
`metodo_coleta=manual_usuario`. A evidência pode comprovar a existência da
oferta, mas `ativa_no_monitor` permanece falso; repetibilidade e calibração
independente continuam obrigatórias antes de qualquer sinal.

Para saber qual partida vale a conferência manual naquele instante:

```powershell
python fila_odds_manual.py
```

A fila usa somente o candidato mais recente de cada partida e período. Ela
inclui apenas notas a partir de 75 que passaram por todos os critérios técnicos
e foram rejeitadas exclusivamente por `odd_ao_vivo_indisponivel`. Pedidos com
baseline, janela, qualidade, evento recente ou odds vencidas ainda bloqueados
não aparecem. A validade padrão é de seis minutos; uma oferta Bet365 válida
registrada depois do candidato resolve automaticamente o pedido. A fila não
envia Telegram nem abre a Bet365 sozinha. O status mostra apenas a quantidade
pendente, a janela e o limiar utilizados.

O bloco `pendências de resultado` mostra sinais e partidas ainda abertas,
cobertura pela API, dependência exclusiva do PackBall, idade máxima, tentativas
e distribuição por mercado. Ele permite acompanhar objetivamente se a fila está
avançando ou se alguma fonte precisa de atenção.
O bloco `mapeamento de escanteios asiáticos por tempo` informa se o histórico
já comprovou linhas over/under de duas opções no 1º ou 2º tempo. Ocorrências
`Exactly` aparecem separadas e jamais habilitam sinais asiáticos.

O bloco `amostra temporal resolvida` separa a população independente usada na
calibração de score/odd dos registros que também possuem o schema temporal
atual. Ele mostra válidos, elegíveis, históricos, legado pré-fingerprint
excluído e cobertura total, além dos mercados com exclusões. O diagnóstico
sombra exige o mesmo fingerprint imutável usado pelo calibrador oficial.
Registros de outra linhagem ou de um schema anterior são preservados para
auditoria, mas não entram no estudo temporal v2 nem são convertidos retroativa
ou artificialmente.

O PackBall permanece como fonte primária. Quando ele não publica uma linha
asiática total válida, uma partida já associada com segurança à API-Football
pode receber o mercado ao vivo `Asian Corners`, bet 32. A mesma complementação
usa `Asian Corners (1st Half)`, bet 51, quando falta a linha válida do 1º tempo.
Cada bet possui cache global independente de cinco minutos, em vez de gerar uma
requisição por partida. A origem, bookmaker e idade ficam gravados junto da
odd; oferta suspensa, bloqueada, incompleta ou com mais de 360 segundos falha
fechada. O catálogo auditado em 21/07/2026 não contém `Asian Corners (2nd
Half)`: o mercado de três opções do 2º tempo continua classificado como
`Exactly` e não pode ser usado como substituto.

Na fronteira do PackBall, somente os sete títulos ao vivo explicitamente
mapeados são aceitos antes da normalização: próximo gol, total de gols, totais
por equipe e os três formatos conhecidos de escanteios. Títulos inesperados que
apenas contenham `Goal`, como `Total ShotOnGoal` ou `Goal Kicks`, e handicap de
gols são descartados. A API-Football é anexada depois e continua validada pelos
IDs próprios de bets. Essa defesa não altera a assinatura V6/V7 nem reinicia as
amostras de calibração.

O status `odds API Asian Corners FT/1T` mantém telemetria persistente, registra
o último bet consultado e separa consultas que retornaram alguma fixture,
respostas válidas sem cobertura e falhas de rede/API. Abaixo dele, os bets 32
e 51 aparecem individualmente com solicitações de fixture, correspondências,
ofertas anexadas e rejeitadas. Assim, uma oferta global sem amostra pode ser
atribuída objetivamente à ausência da fixture PackBall ou a uma linha suspensa,
bloqueada ou incompleta. Esses números não medem acerto e não habilitam mercado;
servem para auditar cobertura e consumo. As chamadas aparecem ainda na categoria
`odds` do contador diário, preservando o teto seguro e a reserva da franquia.
Cada rejeição de fixture correspondente também guarda seu motivo exato: fixture
bloqueada, interrompida ou finalizada; mercado ausente; ou par Over/Under
incompleto/suspenso. Estados de bloqueio são verificados tanto no nível externo
quanto dentro do objeto `status` retornado pela API.
O painel reconcilia a soma dos motivos com o total de rejeições. Registros
anteriores à telemetria v4 são preservados e aparecem como `sem diagnóstico
legado`; eles não recebem uma causa retroativa que não possa ser comprovada.

Quando uma linha real de duas opções for detectada, ela entra em mercados
independentes: `escanteios_1t` (somente entre 15–40 minutos) e
`escanteios_2t` (somente entre 50–87 minutos). Cada um acumula seus próprios
resultados e exige sua própria calibração mínima antes de qualquer alerta
oficial. O mercado do 1º tempo é liquidado apenas com um snapshot de intervalo.
O mercado do 2º tempo exige um total de escanteios do intervalo já persistido e
usa `total final - total do intervalo`; sem essa evidência, o candidato é
bloqueado ou o resultado permanece sem dado.

Por decisão operacional de 30/07/2026, os mercados asiáticos de escanteios do
1º e do 2º tempo estão suspensos por padrão enquanto não houver evidência de
retorno positivo. Com `ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS=0` (ou com a
variável ausente), a camada operacional descarta esses dois mercados antes de
qualquer persistência,
simulação ou alerta; a API-Football também não é consultada para o asiático 1T.
O asiático FT e o escanteio normal continuam independentes e não são afetados.
O histórico antigo permanece intacto para auditoria. Uma reativação futura
exige decisão explícita e `ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS=1`.

O watchdog acompanha esse mapeamento automaticamente. Na primeira evidência de
over/under com duas opções em cada período, envia ao administrador as linhas e
o horário da coleta e grava o marco em `watchdog_estado.json`. A notificação é
idempotente e só é considerada concluída depois de o Telegram confirmar a
entrega. Ofertas `Exactly` nunca acionam esse marco. A detecção habilita somente
coleta e amostra; não libera sinal oficial sem calibração independente.

## Capacidade da fila ao vivo

As coletas detalhadas têm orçamento operacional de 180 segundos por ciclo. Esse
é o limite para iniciar outra partida, não para interromper a última que já
começou. O tempo restante fica reservado para confirmar resultados, enviar
notificações e verificar backups. Um jogo que não começar dentro do orçamento
não é descartado nem marcado como coletado: volta à fila seguinte. A ordem usa
a urgência relativa ao intervalo rápido/lento e dá prioridade a partidas que
nunca foram abertas, evitando starvation.

O relógio do agendador é restaurado do SQLite após reinícios. Para cada partida,
o monitor recupera o último snapshot e o instante original da última odd fresca
(não o horário em que um cache foi reutilizado), converte ambos para idades do
relógio monotônico e retoma os intervalos rápido/lento. Assim, uma manutenção
não transforma artificialmente todos os jogos em tarefas novas; partidas
realmente atrasadas ou nunca coletadas continuam recebendo prioridade.

O status mostra tarefas agendadas, processadas e adiadas. Um ciclo isolado com
adiamentos é esperado em horários cheios. Quando a distribuição uniforme do
PackBall está ativa, a parte adiada representa o teto externo e a capacidade
fica como `limitada_packball`, sem falso alerta de saturação. Fora desse regime,
três ciclos consecutivos acumulando fila mudam a capacidade para `saturada` e
geram alerta administrativo.

O painel separa duas medidas de tempo. `capacidade interna` usa somente ciclos
sem limitação externa e aparece como `n/d` quando a distribuição do PackBall
está ativa. `janela total observada` inclui a espera intencional desse
limitador, permitindo acompanhar quanto do ciclo completo foi consumido sem
confundir espera de segurança com lentidão do processamento.

O excesso sobre 180 segundos também é medido em segundos. Ele é esperado
quando cabe dentro do p95 da última tarefa mais cinco segundos de margem. Três
ciclos consecutivos acima dessa tolerância mudam a capacidade para `degradada`
com o motivo `ciclo_excede_orcamento_mais_ultima_tarefa`; o limitador externo
não mascara esse travamento.

O limitador distribui as navegações por toda a janela de dez minutos, evitando
rajadas seguidas de pausas longas. O watchdog audita o intervalo mínimo, o teto
da janela e timestamps inválidos. Uma avaliação persistente compara o fluxo e a
cobertura temporal com os 12 ciclos anteriores. A mudança só fica `aprovado`
depois de pelo menos 12 ciclos e 45 minutos, sem pausa, mantendo no mínimo 75%
do fluxo e 80% da cobertura temporal da base. Bloqueio real ou falha de login
aciona os limites conservadores persistentes; essa proteção não libera aumento
automático de velocidade.

A transição do experimento também é idempotente no Telegram. O estado
`em_observacao` é silencioso. Uma aprovação ou rollback gera uma única mensagem
com ciclos, tempo, fluxo e cobertura; falha de entrega permanece para retry. Uma
regressão usa o alerta crítico de validação com essas mesmas métricas, evitando
duas mensagens para o mesmo evento. A aprovação mede somente a qualidade
operacional da coleta e nunca é apresentada como confiança de um sinal.

O watchdog também compara o desempenho recente de cada mercado simulado com
uma janela anterior independente. A janela padrão usa até 30 resultados
recentes contra 60 anteriores e só fica avaliável com pelo menos 20 e 30,
respectivamente. Uma deterioração exige ROI recente negativo, queda mínima de
dez pontos percentuais e intervalo aproximado de 95% da diferença totalmente
abaixo de zero. O alerta é único por conjunto de mercados e possui aviso de
recuperação. Antes do primeiro alerta, a queda precisa permanecer válida após
duas decisões independentes novas; verificações repetidas sem resultado novo
não aumentam essa confirmação. Essa supervisão nunca altera filtros ou
libera/bloqueia mercados automaticamente.

Cada avaliação associada a um resultado independente novo é preservada na
tabela SQLite `historico_drift_simulacoes`. A chave
`regra_versao + mercado + ultima_decisao_id` impede cópias geradas pelas
verificações de um minuto. O registro conserva janelas, ROI, intervalo de 95%,
taxas de acerto, estado e quantidade de confirmações. Gatilhos impedem
`UPDATE` e `DELETE`; o esquema, o índice e os gatilhos também são exigidos pelo
pré-voo e por todo backup restaurável. O status mostra o total preservado,
quantos mercados possuem histórico e o horário da última avaliação.

A prontidão profissional não aceita apenas a existência da tabela. Ela compara
a última decisão independente de cada mercado com sua evidência persistida.
Chave ausente, métricas divergentes, JSON inválido ou duplicação tornam o
componente `historico_drift` inconsistente, degradam a operação profissional e
bloqueiam uma eventual liberação oficial. A coleta bruta continua para não
perder dados, mas o problema fica explícito no watchdog e no status.

Na abertura da lista, uma falha transitória ao clicar ou avaliar a aba Ao Vivo
provoca uma segunda navegação automática no mesmo ciclo. Se o contador da aba
não existir, mas a lista estiver carregada, o coletor aceita exclusivamente as
linhas cujo próprio status comprova primeiro tempo, segundo tempo, intervalo ou
minuto ao vivo. Se nem a aba nem a estrutura da lista puderem ser validadas, o
ciclo falha com diagnóstico em vez de registrar falsamente zero partidas.

Dentro de cada partida, estatísticas e odds usam espera dinâmica: a coleta
prossegue assim que os elementos necessários são renderizados, mantendo os
limites máximos anteriores quando a página demora. A lista principal conserva
a espera completa porque seus jogos aparecem progressivamente. A telemetria do
ciclo registra tarefas com/sem odds e duração média/p95 por partida.

Fechamento do navegador ou do contexto Playwright é uma falha fatal de sessão,
não uma simples ausência de dados. Nessa situação o ciclo não persiste leitura
vazia e o navegador é reconstruído imediatamente; timeouts isolados de uma
fonte ainda usam os fallbacks seguros existentes.

Para auditar entradas e resultados somente da regra ativa:

```powershell
python auditar_simulacoes.py --limite 20
```

Use `--regra todas` apenas quando quiser comparar também versões históricas.

Para acompanhar a validação de cada mercado:

```powershell
python relatorio_backtest.py
```

O comando acima consulta somente a versão ativa das regras. Para auditar uma
versão arquivada sem misturar populações, informe-a explicitamente:

```powershell
python relatorio_backtest.py --regra sinais-v1
```

Métricas gerais, segmentos por liga/minuto/odd, pendências e últimos resultados
são sempre filtrados pela mesma versão solicitada.

O relatório exibe taxa bruta, ROI e intervalo de Wilson de 95%. Até 29 partidas
a amostra é `inconclusiva`; de 30 a 99 fica em `pre_validacao`; a partir de 100
torna-se `validavel`, ainda sujeita aos demais bloqueios da calibração.
Somente sinais tecnicamente aprovados com odd dentro da faixa operacional
configurada entram nessa amostra. Resultados fora da faixa continuam guardados
no banco para auditoria, mas não alteram confiança, ROI ou alertas públicos.

Entre 30 e 99 resultados, o calibrador persiste ainda um diagnóstico sombra
com corte cronológico 70/30, AUC da parte posterior, ROI agregado de validação e
contagens por célula. Ele serve apenas para encontrar cedo problemas da regra:
traz explicitamente `habilita_sinal_oficial=false`, não contém uma probabilidade
aplicável e não reduz a exigência mínima de 100 resultados independentes.

Hipóteses pré-registradas usam ainda um controle prospectivo excluído do corte.
A amostra selecionada precisa atingir o mínimo próprio, o controle precisa de
ao menos 10 partidas quando o alvo é 30, o ROI selecionado deve ser positivo e
o limite inferior de 95% da diferença de ROI contra o controle deve superar
zero. Sem controle suficiente o estado é `aguardando_controle`; média pontual
melhor que a baseline nunca confirma sozinha uma hipótese.
O alerta de conclusão repete essas evidências no Telegram e inclui a versão da
política de avaliação. Payload concluído por uma política antiga é recusado e
fica listado como incompatível, sem marcar a hipótese como notificada.

A política v7 exige também `sinais.regra_fingerprint` igual ao vínculo atual.
Os sinais anteriores à implantação desse campo permanecem integralmente no
SQLite e continuam disponíveis no relatório histórico e nas simulações, mas
não contam para ativar confiança ou Telegram oficial. Nenhum hash é preenchido
retroativamente. O painel separa `vinculados`, `legado preservado`, divergentes
e novos registros sem fingerprint; qualquer ausência posterior ao marco de
implantação bloqueia a validação.
O gatilho SQLite `trg_sinais_linhagem_imutavel` torna `regra_versao` e
`regra_fingerprint` imutáveis depois que o sinal é inserido. Isso também impede
um operador ou script de preencher manualmente o hash de um sinal legado. Uma
correção de lógica precisa gerar uma nova versão/população; nunca deve editar a
linhagem de sinais já registrados.
O gateway oficial repete essa conferência imediatamente antes da chamada ao
Telegram e também nos retries. Se a linhagem estiver indisponível ou o sinal
persistido não tiver exatamente o fingerprint atual, grava um bloqueio
`gateway:oficial` auditável e não envia nem mesmo um aviso de confiança baixa.
Marcos de 30/100 e notificações de ativação usam um identificador composto pela
versão da regra, política de calibração, fingerprint e instante do marco por
sinal. Portanto, a migração para v7 reinicia somente esses controles amostrais;
cotas de simulação e histórico operacional permanecem intactos.

A calibração usa os primeiros 100 resultados independentes como janela oficial
fixa. Depois de existir histórico posterior, uma janela separada com até 300
resultados recentes monitora drift sem retreinar o modelo. Uma queda
estatisticamente separada acompanhada de ROI negativo desativa o modelo e os
alertas; as regras nunca se reescrevem sozinhas.
As probabilidades são estimadas em células pré-definidas de nota técnica e odd
(`1.40–1.69`, `1.70–1.99` e `2.00–2.50`). Cada célula precisa de amostra mínima,
erro de calibração aceitável e ROI positivo no período cronológico de validação.
Uma célula reprovada não empresta a confiança de outra faixa de odd.

O status e a matriz de prontidão distinguem dois casos que não podem ser
confundidos: `pendente_amostra`, quando ainda faltam resultados independentes,
e `reprovado_validacao`, quando a amostra já passou pelo corte cronológico mas
falhou em algum gate. Nesse segundo caso ficam visíveis a quantidade realmente
usada na validação, ROI agregado, AUC, limite inferior de AUC95, erro de
calibração e número de células aprovadas. Uma ativação enviada ao Telegram
também inclui a amostra posterior, o ROI e a AUC que sustentaram a decisão.
Uma reprovação preliminar por classes totais desbalanceadas também é classificada
como validação final realizada ao alcançar 100 resultados, mesmo sem existir
uma AUC posterior calculável; ela nunca volta a aparecer como falta de amostra.
Ao alcançar 100 resultados sem aprovação, o watchdog também envia uma única
mensagem de validação final não aprovada, com motivo técnico, amostra posterior,
ROI e AUC disponíveis. A confirmação só é registrada depois do `message_id`;
uma falha de entrega é tentada novamente, sem liberar sinais oficiais.

Para auditar cobertura da API, qualidade, integridade do banco, sinais repetidos
e pendências antigas:

```powershell
python auditoria_sistema.py
```

O campo `saudavel` só permanece verdadeiro quando não existem violações de
chaves estrangeiras, grupos aprovados repetidos ou sinais abertos há mais de
180 minutos.
A auditoria também compara a política gravada em qualquer calibração ativa com
a faixa atual de odds. Um modelo ativo legado ou incompatível degrada a saúde e
fica impedido de ser tratado como validação profissional.

Cada atualização efetiva também é preservada em `historico_calibracoes`. O
conteúdo canônico do modelo recebe um hash SHA-256; por isso, executar novamente
a mesma calibração não cria uma versão artificialmente duplicada. A tabela
`calibracoes` continua representando somente o estado atual, enquanto o
histórico permite verificar quando e por que cada mercado foi ativado ou
desativado. A auditoria recalcula todos os hashes e degrada a saúde se encontrar
qualquer divergência.
Além da verificação por hash, gatilhos do próprio SQLite recusam qualquer
`UPDATE` ou `DELETE` em `historico_calibracoes`. O pré-voo e a validação dos
backups exigem esses gatilhos, evitando que uma cópia sem as garantias atuais
seja promovida como restaurável.

O estado atual também precisa estar vinculado exatamente a uma dessas versões:
mercado, versão da regra, tamanho da amostra, flag ativa, hash e JSON canônico
devem coincidir. O motor confere esse vínculo antes de aplicar a probabilidade;
se faltar ou divergir, retorna `modelo_sem_historico_imutavel` e bloqueia o
sinal oficial. O status mostra `histórico=vinculado` e `estado=coerente` para
cada mercado, além dos totais divergentes.

A seção `fila_telegram` mostra entregas, erros, recuperações e expirações. Uma
falha temporária é tentada novamente após dois minutos, no máximo três vezes.
Alertas com mais de dez minutos ou sinais já resolvidos não são reenviados.
Antes da primeira tentativa e de cada retry oficial, o gateway relê mercado,
linha, odd, nota, regra e status diretamente do SQLite e reaplica a calibração
atual. Se o modelo tiver sido desativado, ficar sem vínculo imutável ou produzir
probabilidade diferente da decisão persistida, a entrega é cancelada. O evento
fica registrado como `gateway:oficial`/`bloqueado`; qualquer ocorrência nas
últimas 24 horas degrada a auditoria Telegram e aparece no status para inspeção.
Imediatamente antes da chamada ao Telegram, o bot persiste uma linha
`enviando`. Um retry muda primeiro o erro anterior para `tentando` e conserva a
contagem acumulada máxima de três tentativas. Se houver resposta normal, a
intenção fica acompanhada de `entregue` ou `erro`; se o processo cair no meio,
o estado permanece sem conclusão. Após dois minutos, o watchdog classifica isso
como `envio incerto`, degrada a saúde e evita que uma confirmação externa
possível seja tratada automaticamente como falha segura para reenviar.

Enquanto existir qualquer entrega oficial em `enviando` ou `tentando`, o gateway
bloqueia novas exposições com `circuit_breaker_entrega_incerta`. Somente o retry
controlado do próprio sinal pode ignorar sua própria intenção pendente; outra
entrega incerta continua bloqueando-o. Simulações permanecem ativas porque não
representam exposição oficial.

Timeout, queda de conexão ou resposta do Telegram sem `message_id` durante um
envio oficial são gravados como `incerto`, mesmo que a exceção tenha sido
capturada normalmente. Esse estado não entra na fila automática de retry e é
mostrado imediatamente pelo watchdog, sem aguardar os dois minutos usados para
detectar uma queda de processo. A resolução deve ser feita com
`resolver_envio_incerto.py` após conferir a conversa no Telegram.
O alerta informa a quantidade de entregas incertas, avisa que novas entradas
oficiais estão pausadas e mostra o comando de consulta. Ele é reenviado somente
se surgir uma nova entrega incerta; ciclos sem mudança não repetem o aviso.

Uma resposta `ok=true` só conta como entrega quando contém `result.message_id`
positivo. O bot persiste uma prova sanitizada com provedor, destino, ID da
mensagem, `ok` e data técnica quando fornecida; não copia texto, nome de usuário
ou conteúdo do chat para esse campo. A prova é imutável e um mesmo par
destino/`message_id` não pode ser ligado a duas entregas. A auditoria também
confere o JSON, detecta reutilização entre entrada, resultado e correção e
separa as entregas antigas sem prova como legado informativo.

As notificações administrativas do watchdog usam uma fila separada em
`notificacoes_operacionais`. Antes da chamada externa, o hash do aviso, destino
e tentativa são persistidos; o texto não é guardado nessa fila. Uma confirmação
recente é reaproveitada após reinício sem chamar a rede novamente. Uma intenção
`enviando`/`tentando` sem conclusão bloqueia todos os destinos de fallback para
o mesmo evento, pois a mensagem pode ter sido recebida antes do crash.
Falhas persistentes só são avaliadas contra os destinos atualmente
configurados. Quando uma auditoria isolada não recebeu o contexto de
configuração, ela não reativa como incidente uma falha histórica de um destino
já removido; a ausência de destino continua sendo tratada separadamente pela
validação obrigatória da configuração. O status informa quantos destinos
ativos foram considerados na auditoria.

O estado completo de idempotência do watchdog também é espelhado atomicamente
na tabela `metadados` do SQLite a cada ciclo. Isso preserva marcos de amostra,
resumo diário, avisos de cota, calibração, risco, ritmo e drift mesmo que
`watchdog_estado.json` seja apagado ou corrompido. Na próxima verificação, o
watchdog prefere um JSON válido; se ele estiver ausente ou inválido, recupera
automaticamente a última cópia íntegra do SQLite antes de decidir qualquer
notificação. `python status_bot.py` mostra a origem usada e o horário do último
espelho. Falha nessa cópia degrada explicitamente a prontidão profissional.

Para listar notificações operacionais incertas:

```powershell
python resolver_notificacao_operacional.py
```

Após conferir o canal, confirme com o `message_id` externo:

```powershell
python resolver_notificacao_operacional.py --notificacao-id 12 `
  --resultado entregue --telegram-message-id 456 --confirmar
```

Se houver certeza de que não foi enviada, devolva-a à política normal de retry:

```powershell
python resolver_notificacao_operacional.py --notificacao-id 12 `
  --resultado nao_enviado --confirmar
```

Para listar esses casos sem alterar o banco:

```powershell
python resolver_envio_incerto.py
```

Depois de conferir manualmente o canal do Telegram, reconcilie exatamente o ID
mostrado. Se a mensagem estiver no canal:

```powershell
python resolver_envio_incerto.py --entrega-id 123 --resultado entregue `
  --telegram-message-id 456 --confirmar
```

Se houver certeza de que ela não foi enviada:

```powershell
python resolver_envio_incerto.py --entrega-id 123 --resultado nao_enviado --confirmar
```

A ferramenta nunca chama o Telegram. A primeira opção exige o `message_id`
visível da mensagem conferida, grava sua prova como `reconciliacao_manual`,
marca `entregue` e conta a exposição oficial; a segunda preserva
`nao_enviado_manual` e cria um erro
retentável sujeito ao prazo e ao teto normal. Sem `--confirmar`, nenhuma escrita
é aceita. Na dúvida, não reconcilie: mantenha o estado para investigação.

Em um segundo terminal, mantenha o watchdog ativo:

```powershell
.\.venv\Scripts\Activate.ps1
python watchdog.py
```

O watchdog usa `watchdog_instancia.lock`. Se outra cópia já estiver ativa, uma
segunda execução informa isso e encerra antes de ler, alertar ou sobrescrever o
estado. A trava é liberada automaticamente no encerramento normal ou por erro.
O processo registra PID e estado atômico em `watchdog_processo.json`. Uma falha
interna transitória durante uma verificação não encerra o supervisor: ela é
avisada ao administrador, a execução tenta novamente no ciclo seguinte e envia
confirmação quando se recuperar. `python status_bot.py` mostra se esse PID ainda
está realmente ativo.
O progresso da validação também fica gravado atomicamente no estado do
watchdog. O administrador recebe uma única notificação quando cada mercado
alcança 30 resultados independentes (pré-validação) e 100 (amostra validável).
Esses marcos não liberam sinais: Wilson, ROI, validação cronológica, calibração
por faixa e drift ainda precisam ser aprovados. Se o envio falhar, o marco não
é marcado como entregue e volta a ser tentado; cada versão da regra mantém seus
próprios marcos.
O painel e `relatorio_backtest.py` calculam também o ritmo dos últimos sete
dias usando exatamente a mesma amostra independente e elegível da calibração.
Com menos de cinco resultados não há prazo; com menos de três dias ou quinze
resultados, a data projetada aparece explicitamente como `preliminar`. A
estimativa serve para planejar coleta, não libera mercado nem prevê desempenho.

No relatório, `resultados_brutos` é o conjunto amplo usado para observar o
desempenho geral. `amostra_calibracao` contém somente resultados independentes,
elegíveis, vinculados à regra e aceitos pelo calibrador; apenas ela reduz
`faltam_calibracao`. O relatório compara essa contagem com o mesmo resumo usado
pela prontidão e falha fechado se houver divergência. Assim, uma quantidade
alta de resultados brutos nunca pode ser apresentada como meta de calibração
atingida. Nomes com caracteres não suportados pelo terminal são substituídos
na impressão sem interromper o restante da auditoria.

A descoberta de odds asiáticas por período também é fail-safe. O status cruza
três evidências: ofertas de duas opções realmente persistidas, catálogo ao vivo
da API e contadores de consultas/ofertas anexadas por mercado. A presença do
nome `Asian Corners (1st Half)` no catálogo não comprova cobertura enquanto
nenhuma oferta real tiver sido anexada. Mercados `Exactly` de três opções são
contados como evidência rejeitada e nunca habilitam `escanteios_1t` ou
`escanteios_2t`. Os diagnósticos `catalogada_sem_oferta_real`,
`catalogada_aguardando_coleta` e `somente_exactly_tres_opcoes` explicam a causa
do bloqueio sem inventar uma fonte.
O progresso separa `resultados_resolvidos`, `amostra_modelo` e
`sinais_pendentes`. O campo `faltam_resultados_reais` usa somente resultados
encerrados; sinais abertos nunca antecipam a meta de 100 nem encurtam
artificialmente o prazo. Uma diferença temporária entre a amostra resolvida e
a amostra do modelo indica apenas que a próxima calibração ainda incorporará
os resultados recém-finalizados.
Quando um modelo realmente passa por todos os critérios e muda para ativo, o
watchdog envia uma notificação administrativa específica; atingir apenas 100
não basta. Se drift, revisão ou nova validação o desativar, envia outro aviso e
os sinais oficiais daquele mercado param imediatamente. As transições são
idempotentes e uma falha do Telegram permanece pendente para nova tentativa.
O mesmo estado controla avisos de franquia da API-Football. O administrador é
avisado uma única vez por dia ao cruzar 80%, 95% e 100% do teto seguro de 7.000
chamadas. Falha no Telegram não marca o aviso como entregue, e a virada da data
reinicia somente esses marcos. A leitura usa o contador local e não consome uma
requisição da API.
Às 18h locais, o watchdog envia um resumo operacional diário idempotente usando
somente o SQLite: saúde da coleta, oportunidades aprovadas, resultados
independentes, greens/reds, ROI hipotético, pendências, alertas oficiais,
simulações, consumo da API e progresso por mercado até 100. O horário pode ser
alterado por `HORA_RESUMO_DIARIO` (0 a 23). Falha no Telegram não marca o dia
como concluído; o watchdog tenta novamente nos ciclos seguintes.

No Windows, a verificação usa `OpenProcess` e `GetExitCodeProcess`; nenhum sinal
é enviado ao processo apenas para descobrir se ele continua vivo.

Ele avisa o `TELEGRAM_ADMIN_ID` quando a coleta ficar mais de cinco minutos sem
atualização e envia outra mensagem quando o funcionamento for recuperado.
O heartbeat usa somente eventos `ciclo_concluido`: mensagens de erro recentes
não escondem uma coleta parada. Três falhas consecutivas também colocam a saúde
em estado degradado.
Além do heartbeat, o watchdog abre o banco em modo somente leitura e acompanha
o funil estatístico. Ele alerta o administrador sobre pendências acima de três
horas, amostra estagnada, novos resultados `sem_dado` e qualquer calibração
ativa incompatível. Problemas estatísticos não reiniciam o processo nem geram
sinais; a reinicialização automática continua restrita à falha real da coleta.

A mesma validação audita continuamente a cadeia do Telegram. Ela confere se
todo resultado de uma simulação entregue recebeu seu aviso, se não existem
avisos sem resultado, erros de entrega persistentes, correções vencidas ou
resultados enviados em duplicidade. Há tolerância curta para o processamento
normal da fila; depois dela, qualquer inconsistência degrada a saúde exibida
por `status_bot.py` e registrada em `watchdog_estado.json`.

O funil operacional recente só é avaliado depois de dez snapshots ao vivo em
uma janela de 30 minutos. Abaixo disso, o estado informa ausência de jogos ou
amostra operacional insuficiente sem gerar alarme. Com volume suficiente, menos
de 90% dos snapshots com candidatos é falha crítica; menos de 20% com odds ao
vivo estruturadas é aviso de possível cobertura baixa ou quebra do parser.

Alertas de qualidade da API ou do funil informam explicitamente que o monitor
e o PackBall continuam ativos. Oscilações não críticas durante o mesmo incidente
não geram mensagens repetidas; uma nova causa crítica ainda provoca escalada.
Quando um destino Telegram de fallback falha, mas o mesmo aviso é comprovadamente
entregue em outro destino configurado, a operação é considerada saudável.

## Dataset temporal para pesquisa

Execute sem alterar o banco de produção:

```powershell
python relatorio_dataset_temporal.py
```

O relatório usa somente sinais aprovados, odds elegíveis, resultados reais e a
regra ativa. Conta no máximo a primeira decisão de cada partida por mercado,
valida que odd e linha das features coincidem com o sinal e rejeita estrutura
ausente ou divergente. A divisão 70/30 é feita pela data em que o candidato foi
criado, mantendo observações futuras fora do desenvolvimento. Cada dataset tem
fingerprint SHA-256 para que uma revisão de resultado ou feature seja detectada.
Esse dataset não altera a nota nem libera Telegram; ele prepara a análise
posterior quando houver amostra independente suficiente.

O mesmo comando inclui uma avaliação sombra pré-registrada de nota técnica,
ritmo de chutes, ritmo de escanteios e pressão máxima nas três janelas. Com
menos de 100 resultados ela permanece `inconclusiva` e não exibe desempenho de
features. A partir de 100, o sentido “maior/melhor” ou “menor/melhor” é definido
somente nos 70% iniciais; cobertura e AUC são medidas nos 30% cronologicamente
posteriores. Features com menos de 80% de cobertura ou classes insuficientes
são recusadas. O relatório é pesquisa sombra e nunca altera sinais sozinho.
Essas coberturas também aparecem em `python status_bot.py`.
Se o processo do monitor tiver realmente encerrado de forma inesperada, o
watchdog o inicia novamente, respeitando intervalo mínimo de cinco minutos entre
tentativas. Um encerramento normal com `Ctrl + C` não é reiniciado.
Uma trava exclusiva do sistema operacional impede que uma abertura manual e uma
recuperação automática criem dois monitores simultâneos. Se já houver uma
instância ativa, a segunda encerra antes de abrir o navegador ou coletar dados.

## Configuração segura no `.env`

Variáveis utilizadas:

- `PACKBALL_EMAIL` e `PACKBALL_PASSWORD`
- `API_FOOTBALL_KEY`
- `API_LIMITE_DIARIO` (padrão: 7500)
- `API_RESERVA_DIARIA` (padrão: 500; o bot para em 7000)
- `API_LIMITE_DETALHES_DIARIO` (padrão: 2000)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID_GOLS` (ou o legado `TELEGRAM_CHAT_ID`)
- `TELEGRAM_CHAT_ID_ESCANTEIOS`
- `LIMITE_DIARIO_SINAIS` (padrão: 10)
- `ODD_MINIMA_SINAL` (padrão: 1.40)
- `ODD_MAXIMA_SINAL` (padrão: 2.50)
- `LIMITE_EXPOSICAO_DIARIA` em unidades (padrão: 5)
- `LIMITE_REDS_CONSECUTIVOS_OFICIAIS` (padrão: 3 em 24 horas)
- `LIMITE_PERDA_DIARIA_OFICIAL` em unidades (padrão: 3)
- `WATCHDOG_REINICIO_AUTOMATICO` (`1` por padrão; use `0` para somente alertar)
- `HORA_RESUMO_DIARIO` (0 a 23; padrão: 18, no horário local do computador)

Nunca envie o conteúdo do `.env` ou de `packball_session.json`. Ambos estão
ignorados pelo controle de versão.

O consumo da API fica em `api_football_uso.json`, com uma cópia recuperável em
`api_football_uso.json.bak`. Os dois arquivos são validados estruturalmente e
gravados por substituição atômica. Se o principal falhar, o bot conserva a
contagem da cópia; se nenhum contador for confiável, assume preventivamente que
o teto seguro já foi consumido, bloqueia novas chamadas e avisa o administrador.
Ele nunca volta silenciosamente para zero. `python status_bot.py` mostra se o
contador está válido, recuperável ou bloqueado, além do consumo e saldo seguro
do dia.

A janela diária segue a virada oficial da API às 00:00 UTC. Depois de cada
resposta, o bot reconcilia o contador com `x-ratelimit-requests-limit` e
`x-ratelimit-requests-remaining`. Se o provedor indicar consumo maior, a
diferença é registrada como `externo`. Esse ajuste é recalculado como uma
fotografia a cada cabeçalho válido e pode diminuir depois de uma virada UTC
observada com atraso; as categorias de tentativas locais nunca diminuem, e o
total usado para bloqueio permanece sempre o maior entre local e provedor. Um
limite de plano menor que o configurado passa a prevalecer, sempre mantendo a
reserva. Os cabeçalhos por minuto também bloqueiam novas chamadas durante a
janela restante quando chegam a zero.
Na inicialização, o endpoint oficial `/status`, que não consome a franquia
diária, confirma imediatamente o consumo mesmo que todas as consultas de jogos
sejam atendidas pelo cache. Se estiver indisponível, a inicialização continua
com o contador local conservador e a próxima resposta normal tenta reconciliar.

As respostas recentes da API-Football também ficam em `cache_api_football`, no
SQLite principal. O cache é separado por endpoint: lista geral por 10 minutos,
estatísticas por 15, eventos por 1, resultados por 30 e odds ao vivo por 5.
Esses prazos continuam valendo depois de reiniciar o processo, evitando gastar
novamente a franquia com uma resposta que ainda é recente. Registros expirados,
JSON corrompido, categoria desconhecida ou horário futuro nunca são aceitos. O
preflight, o watchdog e `python status_bot.py` auditam esse cache; a coleta segue
para a rede de forma segura se ele estiver indisponível.
O evento `ciclo_concluido` e o painel também mostram acertos, gravações,
descartes e falhas do cache em cada ciclo, permitindo medir a economia real da
franquia e diagnosticar contenção do SQLite sem interromper a coleta.

`python status_bot.py` mostra greens, reds e pendentes por tipo de entrada,
separando simulações de alertas oficiais. Também exibe o total oficial do dia e
o estado do circuit breaker.
O resumo diário já existente no Telegram inclui somente os mercados que
começaram a formar o challenger contextual V4. Antes do congelamento, mostra
amostra de treino e classes green/red; depois, mostra o tamanho do treino
congelado e o avanço da validação futura. Esse bloco é informativo, permanece
em modo sombra e não cria uma mensagem adicional.

`python prontidao_profissional.py` produz a matriz completa de evidências. Ela
distingue `pronto`, `pendente_amostra`, `bloqueado_fonte`, operação degradada e
autorização externa. Use `--exigir-completo` em uma auditoria formal; enquanto
qualquer requisito estiver pendente, o comando retorna código 1. O painel mostra
um resumo e libera cada mercado isoladamente somente quando sua calibração real
estiver ativa e a operação/Telegram estiverem saudáveis.
A matriz possui ainda o componente `modelos_sombra`, que informa separadamente
a integridade da pontuação temporal e do challenger contextual, os modelos já
congelados e qualquer mercado incompatível. Corrupção em um desses modelos
degrada `operacao_continua`, mesmo que o modelo nunca seja aplicado
automaticamente aos sinais.
O componente `historico_contexto` confere a trilha imutável das avaliações
contextuais. Cada linha precisa conter JSON válido e repetir exatamente a
regra, o último sinal, a amostra, o estado e a decisão gravados nas colunas.
Qualquer divergência aparece no watchdog, bloqueia o pré-voo e degrada a
prontidão profissional sem interromper a coleta que ainda estiver saudável.

Cada mercado também expõe o diagnóstico de corte sombra. O corte é escolhido
somente na parte antiga do histórico e avaliado uma única vez na parte futura.
Se a validação futura não superar a base com retorno positivo, a prontidão
registra `corte_sombra_apto=false`, mantém o mercado pendente e não altera
automaticamente nenhuma regra.

A matriz inclui ainda o diagnóstico da amostra oficial antes da calibração:
quantidade, acerto, IC95, ROI, lucro e AUC. Com menos de 30 resultados ela
permanece `amostra_inicial`; depois disso, ROI não positivo aparece como
`desempenho_desfavoravel_pre_validacao`, enquanto ROI positivo é apenas
`desempenho_positivo_ainda_nao_comprovado`. Nenhum desses rótulos ativa sinais:
o gate completo de 100 resultados e a política de calibração continuam
obrigatórios.

O resumo diário administrativo também separa greens e reds por mercado. Todas
as contagens de oportunidades, resultados e pendências da amostra oficial
exigem o fingerprint vinculado à regra atual; registros legados com o mesmo
nome de versão ficam excluídos. Os nomes dos mercados aparecem em linguagem
clara no Telegram. Quando o circuit breaker oficial atinge o limite, o watchdog
avisa uma única vez no Telegram; após a normalização, envia uma única
confirmação de recuperação.
Esse bloqueio pausa somente novas entradas oficiais: coleta, liquidação e
simulações continuam normalmente para preservar a amostra.

No progresso de calibração, cada mercado mostra resultados independentes já
resolvidos, primeiras decisões ainda pendentes e o potencial atual após essas
liquidações. Uma leitura posterior da mesma partida/mercado nunca é contada
como pendência adicional nem como atalho para chegar às 100 observações.

Se `TELEGRAM_ADMIN_ID` estiver inválido ou apontar para outro bot, alertas
administrativos tentam automaticamente `TELEGRAM_CHAT_ID` e depois o canal de
gols, sem duplicar uma entrega confirmada. O resumo diário também espera o
primeiro ciclo real após uma inicialização, evitando alerta durante partida a
frio.

`python status_bot.py` mostra somente se cada integração está configurada; ele
jamais imprime tokens, senhas ou chaves. O monitor não inicia se credenciais do
PackBall estiverem ausentes, se limites não forem numéricos, se as odds estiverem
invertidas ou se o reinício automático não estiver definido como `0` ou `1`.

## Backups

Ao iniciar e também durante a operação contínua, o monitor garante no máximo um
backup por dia em `backups/` e conserva 14 dias. Ao virar a data, a primeira
coleta cria ou verifica a cópia; se falhar, o ciclo seguinte tenta novamente.
Além disso, cria uma cópia periódica verificada em cada janela de 6 horas e
conserva as oito mais recentes (aproximadamente dois dias de pontos adicionais).
O backup é feito pela API de backup do SQLite, inclusive com WAL ativo.
Backups nomeados de pré-reinício conservam somente as cinco cópias mais recentes,
sempre removendo também o manifesto correspondente à cópia excedente.
Quando uma atualização adiciona tabelas ou colunas, `iniciar_sistema.py`
identifica o esquema anterior antes do pré-voo. Com monitor e watchdog parados,
ele cria primeiro um `pre_migracao_*.db` com `integrity_check`, verificação de
chaves estrangeiras, SHA-256 e manifesto próprio. Somente depois aplica a
migração aditiva, confere o contrato novo e regenera o backup diário compatível.
Se algum processo ainda estiver usando o banco ou qualquer verificação falhar,
a migração e o reinício são recusados. As cinco cópias pré-migração mais
recentes são preservadas; elas validam a integridade do formato antigo sem
fingir compatibilidade com o runtime novo.
Depois da cópia, o sistema executa `PRAGMA integrity_check`, calcula SHA-256 e
grava um manifesto ao lado do arquivo. Um backup que não passar nessas etapas é
considerado inválido.
Além da integridade física, a verificação exige todas as tabelas e colunas do
contrato atual do bot, o gatilho obrigatório de imutabilidade da linhagem e
executa `PRAGMA foreign_key_check`. Assim, um SQLite que
abre normalmente, mas pertence a uma versão antiga ou possui relações quebradas,
não é aceito como restaurável. Se a cópia diária existente for incompatível, o
monitor cria e verifica uma nova a partir do banco ativo, arquiva a anterior com
prefixo `invalido_` e somente então promove a substituta. As três cópias inválidas
mais recentes ficam preservadas para auditoria.
O watchdog concede dez minutos de tolerância após a meia-noite e depois alerta
se o backup do dia estiver ausente ou não passar na verificação.
Também verifica a cada minuto o ponto restaurável mais recente, considerando
backups diários, periódicos e de pré-reinício. O estado fica degradado se essa
cópia for inválida ou tiver mais de 6 horas e 15 minutos, que é o RPO máximo
supervisionado da operação.
Para não reler um arquivo grande a cada minuto, a verificação é reutilizada
enquanto tamanho e data do banco e do manifesto permanecerem inalterados.

Para verificar o backup mais recente sem alterar o banco ativo:

```powershell
python verificar_backup.py
```

Use `python verificar_backup.py --registrar` apenas para criar o manifesto de
uma cópia antiga que já tenha passado na verificação.
Use `python verificar_backup.py --recriar` para regenerar com a API de backup do
SQLite a cópia diária ausente ou incompatível; o banco ativo continua aberto
somente como origem e a cópia anterior é preservada.

## Retenção e espaço em disco

A tabela `sinais` mantém índices persistentes para consultas por partida e
estado, unidade independente e snapshot de origem. As rotinas de finalização,
deduplicação, backtest e retenção não dependem da criação de índices automáticos
temporários à medida que o histórico cresce.

Na inicialização e a cada mudança de data, o monitor confirma o backup diário
antes da manutenção, executa checkpoint passivo do WAL e remove somente
snapshots antigos sem evidência aprovada. Se o backup falhar, a limpeza não é
executada e volta a ser tentada no ciclo seguinte. Sinais aprovados, resultados
e entregas Telegram são preservados.

`monitor_eventos.jsonl` gira ao atingir 5 MB e `monitor_registros.jsonl` ao
atingir 20 MB, mantendo cinco cópias anteriores. A auditoria marca a operação
como degradada quando o disco possui menos de 512 MB livres.
O watchdog verifica o espaço a cada minuto e também alerta se o arquivo WAL
ultrapassar 512 MB, permitindo intervenção antes de falha de gravação.
Além dos limites imediatos, ele conserva uma amostra horária do tamanho conjunto
do SQLite e do WAL durante 72 horas. Depois de pelo menos seis horas observadas,
estima o crescimento diário e os dias restantes até a reserva mínima. Uma
projeção inferior a 30 dias degrada a saúde e gera alerta antecipado, sem apagar
histórico automaticamente. O painel `status_bot.py` mostra banco, WAL, espaço
livre, crescimento e previsão; oscilações curtas do WAL não formam tendência.

Falhas parciais são isoladas por fonte. Se a coleta de odds falhar depois de as
estatísticas terem sido lidas, as estatísticas são preservadas e o último bloco
de odds persistido é usado sem gerar movimentação artificial. O evento
`fonte_falhou` registra a fonte, o tipo do erro e o fallback empregado.
O horário original das odds acompanha o cache através dos snapshots. Se a idade
conhecida ultrapassar 360 segundos, o motor adiciona o bloqueio
`odds_desatualizadas` e não aprova sinal até obter preço recente. Uma tentativa
de atualização que falha não avança o relógio do agendador de odds.

## Fechamento dos resultados

O monitor acompanha primeiro o PackBall. Quando uma partida com sinal pendente
sai da aba Ao Vivo, ele consulta sua página individual, confirma o status final
e grava o placar. São verificadas no máximo três partidas por ciclo e uma mesma
página só é revisitada após dez minutos. Quando houver cobertura, a API-Football
também complementa a confirmação e os escanteios finais.
Se a partida tiver desaparecido da lista cedo, mas a página individual ainda
mostrar minuto e placar, o bot grava um snapshot de recuperação. Nesse snapshot
ele pode liquidar somente condições já comprovadas, como o lado do próximo gol
ou um over já atingido; derrotas e mercados indefinidos continuam pendentes até
o encerramento confirmado.
Cada consulta de encerramento fica registrada em `consultas_finalizacao`, com
fonte, horário, estado, placar e eventual erro. O cooldown de dez minutos é
persistente e continua válido depois de reiniciar o programa.
O mesmo cooldown vale para a API-Football, inclusive quando o jogo terminou mas
alguma estatística final ainda está ausente. Nessa situação, o sinal permanece
pendente para uma nova fonte; ausência de dado nunca é convertida em `void`.
Partidas realmente canceladas, abandonadas ou anuladas encerram os sinais como
`void`. Para gol HT, a liquidação usa exclusivamente o placar do intervalo;
gols do segundo tempo nunca entram nessa amostra.
Se o encerramento estiver confirmado, mas o dado indispensável continuar
ausente após 24 horas, pelo menos três tentativas e consulta a todas as fontes
disponíveis, o sinal recebe `sem_dado`. Esse estado é terminal e auditável, mas
não conta como green, red, void, retorno, ROI ou amostra de calibração.

## Recuperar o banco

1. Encerre o monitor com `Ctrl + C`.
2. Renomeie `monitor_packball.db` para preservar o arquivo atual.
3. Copie o backup escolhido de `backups/` para `monitor_packball.db`.
4. Execute `python status_bot.py` para validar a cópia.
5. Inicie novamente o monitor.

Não restaure o banco enquanto o monitor estiver aberto.

## Regras de segurança dos sinais

- PackBall continua sendo a fonte principal.
- Ausência na API-Football não elimina uma partida.
- Uma confirmação da API só é aceita quando nomes, orientação, placar e minuto
  são contextualmente compatíveis; o mesmo fixture não confirma duas partidas
  no mesmo ciclo.
- A orientação casa/visitante da API fica persistida por partida e é reutilizada
  no fechamento de placar, escanteios, intervalo e eventos.
- Tentativas com erro também entram no controle conservador da franquia diária.
- Sem partidas no PackBall, a lista ao vivo da API não é consultada; a API
  continua reservada para associação ou fechamento de jogos primários.
- Divergência crítica de placar bloqueia o sinal.
- Nota técnica não é probabilidade.
- A calibração conta no máximo uma observação por partida e mercado.
- A validação cronológica exige que notas técnicas maiores ordenem greens acima
  de reds com AUC mínimo de 0,55 e limite inferior aproximado de 95% do AUC em
  pelo menos 0,50; AUC 0,50 equivale a ordenação aleatória.
- Backtest público, calibração e Telegram usam a mesma faixa operacional de odds.
- A regra ativa `sinais-v4` só aprova candidato com odd ao vivo estruturada entre
  1,40 e 2,50. Nos mercados Over, a linha precisa ainda não estar ganha e um
  único gol ou escanteio adicional precisa produzir vitória integral; linhas já
  vencidas ou que exigem dois ou mais eventos são rejeitadas. As versões v1/v2/v3
  permanecem arquivadas e suas amostras não são misturadas com a v4.
- Janelas de 5/10/15 minutos registram a duração real da referência e são
  descartadas quando excedem o alvo em mais de três minutos.
- Antes de ordenar a fila, o monitor projeta quais dessas janelas cada revisita
  realmente conseguirá fechar usando o histórico restaurado em memória e o
  período atual da partida. Uma vaga existente do ciclo prioriza 15 e 10
  minutos quando os jogos em foco cobrem somente 5; não é criada navegação
  adicional. O diagnóstico do ciclo registra candidatas longas, cobertura do
  foco e as janelas reservadas.
- Cada candidato novo persiste essas medições em `sinais.features_json`, usando
  o esquema atual `features-temporais-v2`. Taxas por minuto só são calculadas
  quando
  existe duração real observada; campo ausente permanece `null` e nunca vira
  zero inventado. Registros anteriores à implantação permanecem com `{}` e não
  devem ser misturados em futuros estudos de features sem filtrar a versão.
- A v2 registra as taxas de chutes e escanteios também separadas entre mandante
  e visitante. O watchdog recalcula total e taxas a partir do par e da duração;
  qualquer incoerência matemática invalida o vetor. Registros v1 permanecem
  preservados para auditoria, mas não entram no dataset v2.
- O vetor temporal é uma base de pesquisa e auditoria. Ele ainda não altera a
  pontuação da regra `sinais-v4`; uma mudança futura de decisão exigirá replay,
  validação cronológica e uma nova versão de regra.
- Cada versão é vinculada por SHA-256 aos arquivos que formam a decisão, à
  versão das features e à faixa efetiva de odds. Se qualquer componente mudar
  mantendo o mesmo nome `sinais-vN`, o monitor falha fechado antes de recalibrar
  ou gerar novas amostras, o watchdog acusa divergência e o pré-voo recusa o
  reinício. A correção é criar uma nova versão, nunca atualizar o hash antigo.
  A auditoria lista o componente exato (`arquivo:...`, `versao_features` ou a
  faixa efetiva de odds) que divergiu. As assinaturas dos processos têm ainda um
  teste de fechamento dos imports locais, impedindo que um módulo novo fique
  fora da detecção de `reinício pendente`.
  A primeira adoção cria uma âncora separada no SQLite. Depois disso, a ausência
  do vínculo é tratada como corrupção e não como convite para recalcular o hash;
  somente restaurar o registro comprovado ou criar uma nova versão permite
  continuar. Uma âncora ausente com vínculo ainda íntegro pode ser reconstruída
  sem alterar o fingerprint registrado.
- O watchdog mede candidatos e snapshots íntegros após o primeiro registro do
  esquema. Qualquer regressão posterior para JSON ausente, inválido, mercado
  divergente ou janelas incompletas degrada a validação. `status_bot.py` mostra
  cobertura e, separadamente, disponibilidade e duração realmente medida para
  5/10/15 minutos.
- Mercados de gol exigem ao menos dois chutes recentes ou aceleração positiva;
  `proximo_gol` também exige chute recente do lado apontado como dominante.
- Ao trocar a versão da regra, o funil operacional começa no primeiro snapshot
  que realmente gerou candidato da nova versão. Snapshots da versão anterior
  não reduzem artificialmente a cobertura; esse marco permanece estável mesmo
  quando a calibração é atualizada em ciclos posteriores.
- O motor recusa diretamente qualquer calibração ativa cuja versão, população,
  unidade amostral ou faixa de odds não corresponda à política atual.
- A política atual também exige os Wilson de desenvolvimento e validação, com
  a confiança conservadora exatamente igual ao menor dos dois; modelo ausente,
  incompleto ou incoerente é recusado sem recorrer à taxa bruta.
- Em `proximo_gol`, uma diferença de placar com gols dos dois times não comprova
  a ordem. O bot consulta eventos da API sob demanda e só liquida quando a
  sequência reconstrói exatamente o placar; sem essa prova, mantém a pendência.
- A confiança enviada usa o menor limite inferior de Wilson de 95% entre o
  desenvolvimento e a validação cronológica posterior, não apenas a taxa
  bruta observada.
- A célula de confiança combina nota técnica e faixa de odd e precisa ter ROI
  positivo na amostra cronológica posterior.
- O backtest reconhece devolução, meia vitória e meia derrota em linhas
  asiáticas de gols e escanteios.
- Mercados `Exactly` de escanteios têm três opções e ficam tipados e separados
  por total, 1º tempo e 2º tempo; eles nunca são tratados como linha asiática.
- Movimentações de odds são comparadas por categoria, escopo e linha; total da
  partida, time da casa e time visitante não podem sobrescrever uns aos outros.
- Telegram só envia quando existe calibração posterior com pelo menos 100
  resultados, validação cronológica e o menor Wilson dos dois períodos atinge
  a confiança histórica mínima de 75%.
- Mesmo depois da calibração, o canal oficial recebe no máximo uma entrada por
  partida, mercado e versão da regra. Uma oportunidade posterior pertence a
  outra população e é bloqueada, ainda que já tenham passado 15 minutos.
- O sistema não executa apostas automaticamente.

## Verificação do código

Execute a suíte offline antes de qualquer reinício controlado:

```powershell
python -m unittest discover -q
```

Além dos testes unitários, a suíte percorre uma partida simulada por coleta
PackBall, confirmação API-Football, odds, evolução temporal, SQLite, geração de
sinais e liquidação no backtest. Sem calibração válida, o teste confirma que o
Telegram permanece bloqueado.

A suíte também constrói 300 partidas independentes em banco isolado para provar
o caminho positivo: recalibração real, validação cronológica, AUC com intervalo
de confiança, ROI por célula e Wilson conservador. Somente depois desses gates o
candidato seguinte recebe confiança e chega ao canal oficial. O transporte é
simulado no teste; nenhum Telegram real é enviado durante a suíte.

Para reunir todas as verificações de pré-reinício em uma execução somente
leitura, use:

```powershell
python preflight_reinicio.py
```

O resultado só informa `pronto_para_reinicio: true` quando configuração, sessão
PackBall (cookie ou `localStorage`), `quick_check` do SQLite, backup do dia,
coleta recente, contador da API, disco/WAL, integridade Telegram e a suíte
completa estiverem
saudáveis. Tokens,
senhas, cookies e valores do armazenamento local nunca são impressos.
O pré-voo também abre o banco somente para leitura e confere os hashes, versões,
mercados e conjuntos de features de todos os modelos de pontuação congelados,
tanto o modelo temporal quanto o challenger com contexto API. Enquanto ainda
não há amostra para criar um modelo, a ausência é normal; depois do
congelamento, qualquer incompatibilidade impede o reinício.
Um `envio incerto`, bloqueio recente do gateway, erro persistente, resultado sem
aviso ou aviso órfão faz `pronto_para_reinicio` permanecer falso até a evidência
ser inspecionada ou concluída; o pré-voo é somente leitura e não apaga o estado.

## Replay histórico offline

Para reconstruir cronologicamente todas as decisões sem escrever no banco de
produção, execute:

```powershell
python replay_historico.py
```

A origem abre em modo somente leitura. Cada snapshot é copiado para um SQLite
temporário, os candidatos são gerados com estatísticas, evolução, qualidade e
odds disponíveis naquele instante, e a liquidação usa apenas snapshots
posteriores. O arquivo temporário, WAL e SHM são removidos ao terminar. O replay
não cria calibração ativa, não envia Telegram e não aumenta a amostra oficial.
Use `--destino caminho.db` somente quando quiser conservar uma cópia de pesquisa.

O replay preserva também o horário original de cada odd. Uma cotação com mais de
seis minutos é bloqueada na simulação da mesma forma que na operação ao vivo. A
saída inclui `funil_por_mercado`, com quantidade gerada, aprovada, rejeitada,
duplicada, presença de odd estruturada/elegível e contagem dos bloqueios. O mesmo
funil aparece em `python relatorio_backtest.py` para a versão consultada.
O replay registra no banco temporário a mesma âncora e o mesmo fingerprint da
regra usados em produção. A saída `analise_temporal` comprova essa linhagem,
informa o fingerprint do dataset e, por mercado, mede cobertura das features,
discriminação temporal e um único corte sombra: o corte é escolhido somente nos
70% iniciais e avaliado nos 30% finais. O campo é sempre rotulado como pesquisa
offline e nunca incorpora o replay à calibração oficial.
O relatório separa também as métricas do histórico bruto das métricas da
população oficial vinculada ao fingerprint atual. Acerto, ROI, IC95 e AUC do
legado nunca são apresentados como se pertencessem à amostra que pode calibrar
o mercado.
Cada resultado também grava `snapshot_id_liquidacao` e `fonte_resultado`.
Assim, a auditoria aponta diretamente qual observação e qual fonte (`packball`
ou `api_football`) comprovaram o green/red. Encerramentos sem evidência ficam
explicitamente marcados como `sem_dado` e não entram na taxa de acerto.
O status e o watchdog conferem continuamente partida, horário e fonte desses
vínculos. Uma inconsistência degrada a validação e dispara alerta ao
administrador, sem interromper a coleta bruta.

### Cotação de entrada preservada para CLV live

Novos candidatos rastreáveis gravam em `features_json.cotacao_entrada_clv` a
cotação sincronizada efetivamente usada na decisão. Mercados binários conservam
linha, Over e Under; `proximo_gol` conserva Casa, Visitante e Sem Gol. A prova
inclui também fonte, bookmaker, horário, idade e indicador de cache. Nenhum lado
ausente é estimado e ofertas diferentes empatadas no instante mais recente são
tratadas como ambíguas, sem congelamento.

`python avaliacao_clv_live.py` prefere essa prova nos sinais novos e usa a
reconstrução pelo snapshot somente para o legado. A evidência congelada falha
fechada se mercado, linha/seleção, odd escolhida, fonte, bookmaker ou frescor
divergirem; cache e cotação com mais de 120 segundos não entram na comparação.
O relatório separa `congelada_v1`, `congelada_v1_invalida` e
`snapshot_legado`, permitindo medir a cobertura sem reescrever o histórico.
Esse diagnóstico continua somente leitura e não libera mercado, muda filtro ou
envia Telegram.

### Vantagem oficial exige mercado completo sem vig

O rastro `valor_mercado_conservador` usa a versão
`valor-mercado-calibrado-conservador-v6`. Um sinal oficial só pode ser tratado
como vantagem quando, no mesmo instante e na mesma origem da odd escolhida,
existir o par Over/Under completo ou, em `proximo_gol`, as três vias Casa,
Visitante e Sem Gol. O gate exige simultaneamente valor esperado conservador
de pelo menos 2% e probabilidade calibrada não inferior à probabilidade de
mercado após a retirada da margem da casa.

Antes de normalizar as probabilidades, a V6 valida o overround do mercado
completo. A faixa operacional ampla é de -2% a 20%: ela preserva uma pequena
margem negativa como possível desajuste real, mas rejeita valores extremos que
normalmente indicam lados de instantes/bookmakers diferentes ou preço
corrompido. O diagnóstico CLV aplica a mesma proteção tanto na entrada quanto
na cotação futura, impedindo que uma observação incoerente contamine o
aprendizado. O status expõe separadamente quantas referências foram bloqueadas
por `margem_bookmaker_incoerente`.

A cotação congelada em `features_json.cotacao_entrada_clv` é a referência
prioritária. Se ela existir mas estiver incompleta, adulterada ou divergente do
contrato, o fluxo falha fechado e não tenta substituir a prova por outra oferta
do snapshot. Todo candidato novo recebe também
`features_json.cotacao_entrada_clv_estado`, que distingue `congelada_v1`,
`oferta_ambigua`, `oferta_nao_localizada` e
`mercado_incompleto_ou_invalido`. A reconstrução pelo snapshot permanece
somente para candidatos legados que não possuam nem a prova nem esse marcador.
Os bloqueios distinguem EV
insuficiente, ausência de referência sem vig e falta de vantagem contra o
mercado sem vig, facilitando a auditoria operacional.

Na revalidação, não basta o cálculo persistido coincidir com um novo cálculo.
O par sem vig também precisa coincidir com a prova congelada, incluindo lados,
seleção, fonte e bookmaker. Assim, alterar conjuntamente a referência e o
resultado calculado continua sendo detectado. Uma prova completa que tenha
sido ignorada pelo cálculo também invalida o rastro antes do Telegram.

O comando `python status_bot.py` configura sua saída como UTF-8 antes de montar
o painel. Isso impede que símbolos estatísticos encerrem o relatório em consoles
Windows originalmente abertos como CP1252; streams sem suporte à reconfiguração
continuam funcionando sem alteração.

O funil operacional de geração de candidatos usa somente snapshots produzidos
pela análise detalhada. Snapshots adicionais com versão
`recuperacao-packball-v1`, criados exclusivamente para liquidar resultados ou
recuperar o corte regulamentar, são contabilizados separadamente e não entram
no denominador de cobertura. Eles não representam uma oportunidade de sinal
perdida.

### Capacidade e latência da coleta

O status mostra a latência média, p95 e máxima dos ciclos. Para a etapa
detalhada, também informa a utilização média, p95 e máxima do orçamento numa
janela móvel dos 20 ciclos ativos mais recentes. Ciclos sem tarefas agendadas
não entram nessa janela.

O watchdog considera a fila saturada após três ciclos consecutivos com tarefas
adiadas por capacidade interna. Ciclos limitados intencionalmente pelo ritmo
distribuído do PackBall ficam fora desse cálculo. Nos demais ciclos ativos, ele
gera degradação preventiva quando três ciclos consecutivos usam pelo menos 85%
do orçamento de coleta detalhada, mesmo que ainda não exista adiamento. Um ciclo
ativo abaixo desse limiar encerra a sequência de pressão.

### Recuperação mútua dos processos

O watchdog continua responsável por reiniciar o monitor quando o processo da
coleta termina. Em sentido inverso, o monitor confere o processo do watchdog no
início e a cada ciclo contínuo. Se o watchdog tiver encerrado, o monitor o
reinicia oculto; a trava de instância impede duplicação. Reinícios e falhas
dessa supervisão ficam no log de eventos e aparecem em `python status_bot.py`.
Assim, a morte isolada de qualquer um dos dois processos não deixa o sistema
sem recuperação automática enquanto o outro continuar ativo.
Quando a trava do monitor fica livre, mas o estado anterior ainda indica
`ativo` ou `falha`, o watchdog reinicia na verificação seguinte mesmo que o
último ciclo ainda seja recente. O intervalo mínimo entre reinícios continua
evitando uma sequência acelerada quando a inicialização falha repetidamente.
Uma exceção fatal também grava o evento `processo_falhou` no log e conserva no
arquivo `monitor_processo.json` o tipo e uma mensagem curta da causa. Tokens,
chaves de API e senhas presentes acidentalmente no texto são redigidos antes
da persistência. O painel exibe a última causa fatal preservada no log, sem
depender da janela do terminal que encerrou.
O iniciador grava `iniciando` antes de criar o processo. Falha ao criar o
processo vira `falha`; uma inicialização que não chega a adquirir a trava pode
ser repetida pelo watchdog depois de 60 segundos de tolerância e quando a
coleta estiver parada. Estado ausente ou ilegível também não impede a
recuperação quando não existe instância confirmada.
Depois de criar um componente, o iniciador agora exige estado `ativo`, PID
respondendo e trava exclusiva ocupada por 12 segundos contínuos. Uma queda
durante a abertura do Playwright deixa de ser registrada como início bem
sucedido: o launcher retorna `inicio_falhou`, preserva a causa sanitizada e o
heartbeat do Agendador fica não saudável já na mesma execução. Componentes que
já estavam ativos não passam por essa espera e continuam idempotentes.
Uma parada criada por `python parar_sistema.py` é a exceção explícita: nesse
modo, os dois encerram graciosamente e não tentam recuperar um ao outro.

A existência da instância é confirmada pela trava exclusiva mantida aberta pelo
sistema operacional (`monitor_instancia.lock` ou `watchdog_instancia.lock`). O
PID permanece no painel para diagnóstico, mas sozinho não bloqueia um reinício,
pois o Windows pode reutilizar números de processos encerrados. O status mostra
PID e trava separadamente e marca a instância como `confirmada` somente quando
ambos concordam. Uma trava ocupada também evita duplicação quando o arquivo de
estado ainda não terminou de ser atualizado.

Uma pendência com mais de 180 minutos não é tratada como travada se ainda
recebeu snapshot nos últimos 30 minutos, pois copas podem ter prorrogação e
pênaltis. Ela vira falha quando deixa de receber observações; após 360 minutos,
o teto absoluto prevalece mesmo que a página continue repetindo o mesmo estado.

Em partidas com prorrogação ou pênaltis, os mercados deste bot continuam sendo
de tempo regulamentar. A API usa `score.fulltime`; eventos após o minuto 90 são
ignorados. No PackBall, o corte utiliza o último snapshot entre 90 e 99 minutos
imediatamente anterior ao estado `BREAK`. Escanteios finais de AET/PEN só são
liquidados quando esse snapshot regulamentar existe; sem ele, o sinal permanece
pendente para outra evidência e pode terminar como `sem_dado`.
Quando esse corte já está persistido, a liquidação ocorre diretamente pelo
SQLite, sem esperar a partida sair da lista ao vivo nem reabrir sua página.

Antes de aplicar confiança histórica, o calibrador compara a quantidade de
partidas independentes e o horário do último resultado com o registro da
calibração ativa. Se houver resultado ainda não incorporado, o candidato recebe
`modelo_desatualizado`, não pode virar sinal oficial e o watchdog degrada a
validação até a recalibração automática concluir.
Calibrações inativas que ficaram apenas um resultado atrás recebem uma janela
operacional de cinco minutos para a reconciliação automática, inclusive entre
ciclos. Nesse intervalo o estado aparece como reconciliação em andamento e não
gera aviso transitório no Telegram. Se continuar divergente após a janela, o
alerta `calibracao_inativa_desatualizada` é emitido normalmente. Uma calibração
ativa fora de um ciclo em andamento continua alertando imediatamente; além
disso, o próprio motor bloqueia qualquer modelo ativo cujo frescor não confira.
Além da quantidade/data, a política v4 grava um fingerprint SHA-256 dos IDs,
partidas, notas, odds, resultados e retornos usados. Alterar um green/red ou
retorno preservando o mesmo tamanho da amostra também invalida o modelo.

### Conclusão do experimento do filtro

O experimento prospectivo que compara sinais enviados e candidatos filtrados
tem uma única análise final por versão, limites e fingerprint da regra. Assim
que as duas coortes alcançam a amostra mínima, o watchdog grava no SQLite a
decisão e toda a evidência usada. Dois gatilhos impedem alteração ou exclusão
desse registro.

Resultados posteriores não reabrem a mesma análise. Se a vantagem não foi
comprovada, o filtro permanece apenas como regra de simulação e o experimento
fica corretamente encerrado; ele não bloqueia a evolução dos demais
componentes e também não pode virar favorável por inspeções repetidas. Uma
nova tentativa exige outra versão registrada antecipadamente. A auditoria
continua somente leitura; a conclusão é gravada antes dela, numa etapa
explícita e supervisionada do watchdog.

### Versão ativa por mercado nos relatórios

Mercados com correção prospectiva localizada são auditados pela própria
linhagem. Atualmente, `escanteios_ft_asiatico` usa
`sinais-v7-ft-asiatico`; os demais mercados permanecem em `sinais-v6`.
O drift, seu histórico persistente e o resumo diário usam esse mapa. Resultados
antigos continuam imutáveis no SQLite, mas não contam como amostra da versão
ativa de outro mercado.

### Disjuntor das notificações operacionais

Após três falhas recentes do mesmo destino, os avisos operacionais entram em
pausa por cinco minutos. Durante a pausa, nenhuma nova intenção é criada e não
há repetição acelerada. Ao terminar o intervalo, somente uma mensagem funciona
como sonda: se for confirmada pelo Telegram, as falhas anteriores deixam de
degradar o painel; se falhar, inicia-se outra pausa.

O disjuntor não interrompe PackBall, API-Football, gravação SQLite nem a
avaliação de sinais. Uma indisponibilidade operacional contida também não
impede um reinício corretivo pelo Agendador do Windows, desde que não existam
envios incertos, provas inválidas ou reutilizadas.

### Liberação tardia do Chrome

Depois de uma parada segura, o Windows pode levar alguns segundos para liberar
todos os recursos do Chrome. A abertura do monitor repete automaticamente um
`PermissionError` transitório até três vezes, com espera crescente. Se o
navegador já tiver sido criado parcialmente, ele é fechado antes da repetição.
Outros tipos de erro continuam falhando normalmente e permanecem visíveis no
watchdog.
# Contexto avançado da API-Football

O contexto pré-jogo é armazenado em `snapshots.contexto_api_json` e usa o cache
`cache_api_football` na categoria `contexto`. O status mostra a cobertura de
forma, H2H, escalações, desfalques, temporada, previsão, classificação,
histórico detalhado, estatísticas e jogadores ao vivo, além da concordância
entre as métricas das duas fontes. A coleta é auxiliar e isolada: erro ou
lentidão não interrompe o pipeline ao vivo. O limite diário seguro continua em
7.000, com 500 chamadas reservadas para resultados e recuperação.

`contexto-pre-jogo-v3` acrescenta:

- classificação da liga, forma da tabela, pontos e saldo de gols;
- até dez partidas recentes combinadas por uma única consulta `fixtures?ids`,
  com médias de gols, escanteios, chutes, chutes no gol e xG a favor/contra;
- todas as métricas úteis já presentes em `fixtures/statistics`, incluindo
  posse, chutes por zona, bloqueios, passes, defesas, cartões e xG;
- resumo de `fixtures/players` apenas para jogos que já passaram pelo filtro
  mínimo de atividade, com produção ofensiva e até três destaques por equipe;
- gols, cartões, VAR e substituições de `fixtures/events`.

`contexto-pre-jogo-v4` acrescenta a referência de odds pré-jogo da própria
API-Football. A consulta usa `/odds?fixture=...`, cache persistente de doze
horas e a categoria de cota `odds_pre_jogo`. O snapshot não guarda o payload
bruto: conserva somente a linha central de gols e escanteios, mediana das odds,
probabilidade Over sem margem, dispersão e até vinte evidências compactas.

Os IDs de bets pré-jogo não são confundidos com os IDs ao vivo. O parser aceita
somente mercados FT cujo nome indique total de gols ou escanteios e que tenham
o par completo Over/Under na mesma linha. Mercados por time, primeiro/segundo
tempo, handicap, exato, faixa, ímpar/par e pares incompletos são rejeitados.
Cada casa fornece no máximo sua linha principal ou mais equilibrada. O campo
`consenso_suficiente` exige ao menos duas casas e dispersão máxima de 1 gol ou
2 escanteios. Essa referência permanece em modo sombra.

Antes das páginas detalhadas, o monitor associa somente as partidas PackBall
agendadas e consulta seus IDs em lotes de até 20 por `fixtures?ids`. Quando o
provedor inclui `events`, `lineups`, `statistics` e `players` na resposta, o
mesmo payload alimenta todos esses resumos sem novas chamadas. Campos ausentes
continuam usando os endpoints específicos apenas para jogos que já passaram
pelo filtro mínimo de atividade. Falha ou retorno parcial do lote preserva a
fixture simples e não interrompe o PackBall. O ciclo registra quantas partidas
foram associadas, solicitadas, retornadas e incorporadas para permitir medir
cobertura, economia de chamadas e regressão de latência.

O snapshot guarda somente esses resumos compactos. Payloads completos
permanecem no cache da API e expiram pelo TTL. Snapshots v1/v2 continuam
legíveis e não são reescritos. Estatísticas individuais ao vivo têm cache
próprio de cinco minutos; classificação usa uma hora e contexto histórico,
doze horas. Isso permite aprofundar a análise sem repetir chamadas nem
alongar severamente todos os jogos do ciclo.

Rollback operacional: a palavra combinada `VOLTARAPI` significa definir
`API_CONTEXTO_AVANCADO_ATIVO=0` e reiniciar de forma controlada. Isso desliga
somente o enriquecimento avançado; histórico, V6/V7, PackBall, estatísticas
ao vivo e odds permanecem preservados.

O comando `python status_bot.py` também mostra a amostra independente e o
desempenho do contexto por mercado. O relatório é observacional: segmentos
precisam de 30 resultados com a variável e 30 sem ela para ficarem prontos
para revisão humana, sem promoção automática.

O watchdog persiste a evolução somente quando aparece um novo resultado
independente. O histórico é imutável e não participa dos bloqueios do motor:
uma falha nesse relatório gera atenção operacional, mas não interrompe PackBall,
Telegram ou as regras V6/V7.

Na avaliação, `desconhecido` significa ausência de cobertura da API. Esses
casos não entram nem no grupo “com” nem no grupo “sem”; a cobertura de cada
variável deve ser analisada junto com amostra, ROI e intervalo de confiança.

A política `avaliacao-contexto-sombra-v5` calcula o intervalo ajustado do delta
de ROI com `z=3.0` e avalia apenas hipóteses previamente permitidas para cada
mercado. “Avaliável” significa apenas amostra suficiente; “conclusivo” exige
intervalo totalmente positivo ou negativo. Nenhum desses estados promove
regras automaticamente. A v5 pré-registra também volume ofensivo da API, xG
ao vivo, perfil histórico de gols e perfil histórico de escanteios. Dados de
classificação e jogadores são coletados para auditoria, mas não viram filtro
até existir uma hipótese específica registrada antes da amostra. Linhas
pré-jogo altas (gols a partir de 2,5; escanteios a partir de 9,0) também são
hipóteses prospectivas separadas e só são conhecidas quando o consenso acima
é suficiente.

## Challenger contextual prospectivo

`pontuacao-contexto-sombra-logistica-v1` combina, por mercado, o vetor ao vivo
V2 com o contexto `contexto-pre-jogo-v4`: forma, H2H, médias de temporada,
histórico detalhado, xG, estatísticas live da API, escalações, desfalques e
consenso pré-jogo de gols ou escanteios. Apenas o contexto gravado no mesmo
snapshot que originou o sinal é aceito; dados obtidos depois não podem entrar.
Totais que combinam mandante e visitante só são conhecidos quando os dois
lados estão presentes; ausência parcial não é convertida em zero nem em total
incompleto. A cobertura de cada feature é exposta junto da avaliação.

O challenger forma uma população própria de partidas com fixture API válida e
ao menos quatro features contextuais conhecidas. Ele exige 60 resultados
independentes e no mínimo 15 greens e 15 reds antes de congelar pesos, médias,
desvios, fingerprint e marco no SQLite. A chave usa o prefixo imutável
`pontuacao_sombra:` e, portanto, não pode ser alterada ou apagada.

Depois do congelamento, somente sinais com ID posterior entram na validação.
São necessários exatamente os primeiros 30 resultados futuros. Essa janela,
seu último sinal e seu fingerprint ficam fixos; resultados posteriores aparecem
apenas como disponibilidade adicional e não recalculam a decisão. Isso evita
selecionar um ponto favorável depois de observar repetidamente a mesma
hipótese. O estado só fica favorável para revisão
humana quando o limite inferior de 95% da AUC supera 0,50, a AUC melhora pelo
menos 0,05 sobre a nota atual e o Brier não é pior que a probabilidade implícita
da odd. Não há aplicação automática e as regras V6/V7 permanecem intactas.

O watchdog envia um aviso idempotente quando o modelo contextual é congelado e
outro quando sua janela fixa de 30 resultados termina. Falha de Telegram mantém
o marco pendente para nova tentativa. Resultado favorável é apenas candidato à
revisão humana; resultado contrário ou inconclusivo é avisado como não
promovível. Nenhum desses alertas altera uma regra ou libera sinal oficial.

Os testes de regressão verificam o congelamento de todas as métricas usadas no
gate, não apenas da lista de sinais: AUC, Brier e estado dos challengers simples,
contextual e temporal 5/10/15 permanecem idênticos quando chegam o 31º resultado
e os posteriores.

## Janela fixa da calibração oficial

A política `calibracao-score-odd-wilson-duplo-auc-ic-janela-fixa-v8` congela
os primeiros 100 resultados independentes de cada linhagem: 70 para
desenvolvimento e os 30 seguintes para validação cronológica. O 101º resultado
e os posteriores não podem alterar probabilidades, AUC, ROI nem a decisão
original. Isso impede aprovação por tentativas sucessivas.

Separadamente, até as 300 observações mais recentes monitoram drift. Essa
janela pode suspender um modelo quando houver deterioração estatística e ROI
negativo, mas nunca retreina ou reabre a janela oficial. Uma nova tentativa de
calibração exige nova política ou linhagem registrada.

Os marcos Telegram de 30/100 e as transições de calibração são identificados
pela linhagem real de cada mercado — versão da regra, fingerprint e início da
população — e não pela versão da política estatística. Assim, uma migração de
política não repete avisos já entregues. Mercados com regras próprias, como
escanteios asiáticos FT, mantêm marcadores independentes.

A pré-validação de 30–99 resultados usa a mesma fronteira da decisão final:
até o 70º resultado, todos pertencem ao desenvolvimento; do 71º ao 99º, apenas
os resultados novos preenchem progressivamente a validação de 30. A prévia
nunca recalcula uma divisão percentual móvel. O painel mostra os dois alvos,
os faltantes e métricas somente da validação já observada.

Enquanto a validação ainda está incompleta, o painel também classifica o
recorte observado como `aguardando_validacao`, `inconclusiva_classes`,
`favoravel_mas_inconclusiva` ou `desfavoravel_no_recorte_atual`. A explicação
lista separadamente AUC abaixo de 0,55, limite inferior do AUC abaixo de 0,50
e ROI não positivo. Essa tendência é apenas diagnóstico: não antecipa nem
substitui a decisão imutável dos 100 resultados.

## Retentativa do driver Playwright

A inicialização do driver pode falhar no Windows antes mesmo de o Chrome abrir,
por exemplo quando a criação do pipe interno recebe `PermissionError`. O
monitor repete essa etapa até três vezes, com espera de 2 e 4 segundos, antes
de falhar de forma fechada para o watchdog. Uma recuperação transitória é
registrada na observabilidade. Essa retentativa não abre páginas adicionais,
não repete login e não aumenta as solicitações ao PackBall.

Após um reinício, a prontidão compara o horário do último espelho persistido
com o início da instância atual do watchdog. Se o espelho ainda pertence ao
processo anterior, o estado exibido é `supervisao_inicializando`: nenhum
mercado é liberado, mas o período normal de partida a frio não é rotulado como
falha operacional. Assim que o watchdog grava a primeira verificação da nova
instância, todos os gates voltam a ser avaliados normalmente. Horários ausentes
ou inválidos continuam falhando de forma fechada.

## Gate operacional do Telegram oficial

Uma probabilidade calibrada não é suficiente para autorizar a entrega. No
instante imediatamente anterior ao envio oficial, o gateway consulta novamente
o componente `operacao_continua` da prontidão profissional. Somente o estado
`pronto` permite prosseguir para a revalidação do modelo, limites de risco e
Telegram.

Estados `inicializando` ou `degradado`, ausência do validador e erro durante a
consulta bloqueiam a entrega e registram a decisão em `entregas_alertas` no
canal técnico do gateway. Sinais oficiais e simulações obedecem ao mesmo gate
operacional. Assim, o painel e o caminho real de envio não dependem apenas da
informação exibida ao operador.

## Ciclo fail-closed e preservação do Green/Red

Os sinais ficam pendentes em memória até a varredura inteira terminar. Se
PackBall, API-Football, odds, processamento ou supervisão falhar em qualquer
ponto, a trava permanece ativa até o ciclo seguinte. Nenhum sinal ou resultado
é enviado nesse ciclo. Candidatos ainda não entregues são marcados como
`rejeitado` com o motivo `operacao_degradada_no_ciclo`, portanto não entram no
backtest nem alteram a contagem de Green/Red. Snapshots parciais podem ser
preservados para diagnóstico, mas recebem `apto_para_liquidacao=false`.

A lista Ao Vivo tambÃ©m participa desse gate. Quando o contador visÃ­vel do
PackBall diverge da quantidade de partidas extraÃ­das, o coletor recarrega a
pÃ¡gina uma vez para eliminar um estado transitÃ³rio da SPA. Se a segunda
leitura continuar diferente, registra `lista_packball_inconsistente` e mantÃ©m
todo o ciclo fechado: nÃ£o finaliza resultados, nÃ£o envia sinais ou retries e
nÃ£o altera Green/Red. A lista parcial continua disponÃ­vel apenas para
diagnÃ³stico e priorizaÃ§Ã£o futura.

Se a pÃ¡gina abrir sem botÃ£o, linhas ou fallback validÃ¡vel em trÃªs ciclos
consecutivos, o monitor nÃ£o continua recarregando indefinidamente. Ele ativa
`lista_packball_nao_validada` por 15 minutos, registra
`circuit_breaker_packball` e nÃ£o faz nova navegaÃ§Ã£o durante a pausa. Ao fim do
prazo, a recuperaÃ§Ã£o volta a tentar de forma automÃ¡tica; uma nova sequÃªncia de
trÃªs falhas renova a proteÃ§Ã£o.

O preflight tambÃ©m decodifica somente o campo `exp` do JWT armazenado em
`packballBearer`; o valor do token nunca aparece em log ou diagnÃ³stico. Se o
bearer estiver vencido, a sessÃ£o Ã© classificada como `sessao_expirada`. Depois
que qualquer pausa de acesso termina, o iniciador realiza uma Ãºnica renovaÃ§Ã£o
automÃ¡tica, salva o novo `storage_state` e repete o preflight. Falha de login
ativa a pausa longa existente e impede repetiÃ§Ãµes pelo agendador.

A tarefa `PackBall Monitor Profissional` executa a cada cinco minutos. Durante
o circuit breaker, cada heartbeat Ã© recusado sem iniciar processos. ApÃ³s o
prazo, uma coleta parada por `falhas_consecutivas` sÃ³ Ã© considerada
recuperÃ¡vel quando o motivo persistido Ã© exatamente
`lista_packball_nao_validada`; outras falhas continuam bloqueadas.

Quando a tentativa automÃ¡tica nÃ£o sair de `/login` em 30 segundos, o heartbeat
registra somente `erro_renovacao` e `causa_renovacao` (nomes de classes, nunca
mensagem, token ou senha) e ativa `falha_login_packball` por seis horas. NÃ£o
limpe essa pausa para repetir automaticamente. Com o operador presente, a
recuperaÃ§Ã£o controlada Ã©:

```powershell
python packball_login.py --manual --autorizar-nova-tentativa
```

Esse comando autoriza uma Ãºnica tentativa visÃ­vel, espera a conclusÃ£o manual e
sÃ³ salva `packball_session.json` depois que a URL deixa `/login`. Em seguida,
`python iniciar_sistema.py` executa novamente todo o preflight.

Depois de cada ciclo concluÃ­do, o monitor consulta o `storage_state` do mesmo
contexto que navegou no PackBall. O arquivo persistido sÃ³ Ã© trocado quando o
contexto contÃ©m um JWT com `exp` futuro e estritamente posterior ao atual. A
gravaÃ§Ã£o usa arquivo temporÃ¡rio e substituiÃ§Ã£o atÃ´mica. Bearer vencido,
opaco, ausente ou mais antigo nÃ£o pode regredir `packball_session.json`; o log
`sessao_packball_persistida` guarda apenas `expira_em`.

## Autonomia da cota API-Football

O contador usa dias UTC. A fotografia devolvida pelo provedor só reduz o saldo
quando `cota_provedor_dia` coincide com o dia atual; após a virada UTC, a
fotografia anterior permanece preservada apenas como histórico até a
ressincronização gratuita de `/status`. O painel identifica explicitamente o
dia das duas referências e informa se a fotografia foi aplicada ao saldo
atual, evitando confundir um restante antigo com a franquia recém-renovada.

O enriquecimento antecipado de fixtures é apenas uma otimização de fila e tem
teto padrão de 40 partidas por ciclo (duas chamadas agrupadas). Foco, partidas
novas e revisitas na janela de 5 a 8 minutos têm prioridade. O teto diminui
automaticamente quando a cota segura ou a cota de detalhes se aproxima do fim;
ele pode ser ajustado por `API_FIXTURES_DETALHADAS_MAX_CICLO` entre 0 e 100.

Odds e contexto detalhado não são consultados para uma leitura que já esteja
matematicamente impedida de atingir o limiar do motor. Quando a leitura pode
virar sinal, o fluxo continua completo: odds necessárias, estatísticas ao vivo,
jogadores e contexto são coletados antes da decisão. Assim, a economia ocorre
somente em partidas sem possibilidade de aprovação e não reduz a qualidade de
um candidato real.

## Aviso preventivo da sessao PackBall

O watchdog audita a expiracao persistida sem registrar o bearer. Por padrao,
envia um unico aviso administrativo quando restarem 48 horas ou menos,
deduplicado pela data de expiracao. Depois de uma renovacao que leve a sessao
para fora dessa janela, envia uma unica confirmacao de recuperacao. Esse aviso
e preventivo: nao enfraquece os gates de sinais nem expoe token ou senha.

## Challenger temporal longo V2

O estudo `pontuacao-longa-logistica-v2` mede se a evolução real de pressão,
chutes e escanteios em 5, 10 e 15 minutos separa melhor Green de Red do que a
nota atual. Ele não reutiliza os resultados que motivaram sua criação: cada
mercado recebe no SQLite uma âncora imutável e somente sinais com ID posterior
podem participar.

Um registro só é elegível quando as três janelas estão completas e todas as
taxas de chutes, escanteios e pressão média existem. Os primeiros 60 resultados
independentes posteriores à âncora formam o treino; os 30 seguintes formam
uma validação congelada. Resultados posteriores não mudam a decisão.

O challenger permanece sempre em modo sombra e nunca altera V6/V7 nem libera
sinal automaticamente. Mesmo depois dos 30 resultados, ele apenas fica apto
para revisão quando o limite inferior de 95% da AUC supera 0,50, melhora ao
menos 0,05 sobre a nota atual e apresenta Brier menor que a probabilidade
implícita da odd. A integridade da âncora, do modelo, das features e dos hashes
é conferida pelo watchdog e pelo pré-voo de reinício.

O Telegram não envia mensagem quando a âncora é criada nem a cada resultado.
Ele registra e repete com segurança somente dois marcos: o congelamento dos 60
treinos e a conclusão da validação fixa de 30. O resumo diário passa a mostrar
o progresso 5/10/15 apenas depois do primeiro resultado elegível, evitando
sete linhas vazias e notificações sem ação útil.

A prontidão profissional usa a mesma auditoria do pré-voo. Se qualquer âncora,
hash, conjunto de features ou modelo 5/10/15 ficar incompatível, o componente
`modelos_sombra` degrada a operação contínua e o gateway oficial permanece
fechado. A ausência normal de modelo enquanto os 60 treinos ainda estão sendo
formados continua íntegra e não é tratada como pane.

Essa proteção também faz parte da verificação de restauração. Um backup só é
válido quando SQLite, esquema, chaves estrangeiras, checksum e todos os
envelopes sombra persistidos estão íntegros. A auditoria confere os modelos
temporal/contextual e, no V2, também linhagem, âncora e o vínculo exato do
modelo com ela. A verificação não monta dataset nem treina modelos, portanto
continua adequada ao backup periódico.

## Proteção contra starvation da fila ao vivo

Quando a quantidade de partidas ao vivo supera o orçamento seguro do ciclo,
o monitor continua usando exatamente a mesma cota de navegação. Antes das
demais reservas, porém, ele garante uma vaga para a partida com leitura mais
atrasada acima de 20 minutos. Jogos novos, partidas em foco e fechamentos das
janelas de 5, 10 e 15 minutos continuam na fila; nenhuma tarefa adicional é
criada.

Cada ciclo registra separadamente a idade das tarefas agendadas, processadas e
adiadas, além da quantidade acima de 20 minutos. O diagnóstico da priorização
informa quantas estavam atrasadas, se uma foi reservada e a idade escolhida.
Em 01/08/2026, a primeira execução real da proteção resgatou uma leitura com
9.426,903 segundos, reduziu os atrasados de 15 para 14 e manteve PackBall
34/34, sem pausa preventiva nem falha da API.

O painel operacional exibe quantos jogos acima de 20 minutos foram processados
e adiados, a maior idade restante e se a reserva foi aplicada. O watchdog só
trata isso como falha se houver partidas antigas e nenhuma delas for resgatada
por três ciclos consecutivos. Congestionamento normal com resgate progressivo
permanece saudável e não gera alerta repetitivo.

### Priorização temporal sob carga alta

Quando há 15 ou mais tarefas ao vivo, a fila reserva até duas vagas iniciais
para revisitas capazes de fechar janelas de 5, 10 ou 15 minutos. A partida mais
atrasada e os focos do agendador continuam protegidos, e uma partida inédita
permanece na fila. A mudança apenas reordena o mesmo orçamento: não cria
navegações extras nem altera o ritmo seguro do PackBall.

### Challenger prospectivo Gol FT por odd atual — 03/08/2026

O filtro **movimento_gols.odd_atual >= 1.66** é acompanhado em modo sombra
pela hipótese imutável **gol_ft_odd_atual_min_166_v1_20260803**. O marco
prospectivo é 03/08/2026 18:40:54 e a amostra mínima é de 30 resultados
independentes. Não há aplicação automática, liberação de Gol FT nem alteração
dos demais mercados. A confirmação exige ROI selecionado positivo e limite
inferior do intervalo de 95% do delta de ROI acima de zero, com grupo de
controle suficiente.

Uma variante conservadora, **gol_ft_odd_166_minuto_max_82_v1_20260803**,
acompanha simultaneamente a odd mínima de 1,66 com minuto máximo 82. Ela não
substitui nem altera a hipótese-base durante a coleta; ambas começam do zero e
só podem ser comparadas após amostra futura suficiente.

### Gol HT com limite prospectivo de 28 minutos — 03/08/2026

O Gol HT usa a versão isolada **sinais-v8b-gol-ht-max28**. O minuto 28 ainda
pode gerar candidato quando todos os demais critérios são satisfeitos; a
partir do minuto 29 o bloqueio **fora_da_janela_gol_ht_max_28** impede nova
entrada. A amostra antiga de sinais-v6 permanece preservada e não é misturada
com a nova população.

Em 29/08/2026, a separação prospectiva dos braços HT confirmou que a rota
`gol-ht-capacidade-times-poisson-v1` continuava desfavorável (14 resultados,
6 greens, 8 reds, ROI -25,7%). A configuração operacional fixa
`GOLS_CAPACIDADE_HT_V1_GRUPO_ATIVO=0`: o braço permanece coletando somente em
sombra e não volta ao Telegram por mudança de padrão ou reinício. Reativá-lo
exige alterar explicitamente a variável para `1`. Essa decisão não suspende as
coortes independentes HT 0-0/minuto 20, HT antecipado ou HT contextual V2b.

Na mesma revisão, o braço `gol-ft-capacidade-times-poisson-v1` apresentou 7
resultados entregues (2 greens, 5 reds, ROI -58,0%). Ele também permanece
somente em sombra com `GOLS_CAPACIDADE_FT_V1_GRUPO_ATIVO=0`. O rollback é
independente por mercado e não afeta Gol FT antecipado 2T nem Gol FT contextual
V2b.
## Priorização de odds e exploração flexível de gols

Uma leitura de odds só avança o relógio do agendador quando encontra ao menos
uma oferta ao vivo utilizável de gols ou escanteios. Página acessível sem oferta
não é tratada como sucesso: a nova tentativa ocorre na próxima coleta elegível,
sempre dentro do limitador de navegação do PackBall. Entre tarefas equivalentes,
odds vencidas e revisitas capazes de fechar as janelas de 5, 10 e 15 minutos
recebem prioridade sem aumentar o orçamento de navegações do ciclo.
Sob carga alta, as primeiras vagas são distribuídas entre uma oportunidade
pontuada pela API, uma partida nova e revisitas temporais/foco. Partidas apenas
atrasadas continuam na fila, mas não ocupam automaticamente a primeira vaga.

O experimento operacional de 04/08/2026 usa elegibilidade de coleta a cada 180
segundos e um limitador proporcional de 8 navegações por 180 segundos. A taxa
média permanece próxima da configuração anterior de 28 por 600 segundos; o
circuit breaker e a pausa preventiva continuam obrigatórios.

`exploracao-atividade-gols-v1` mede uma flexibilização mínima exclusivamente em
modo sombra. Ela aceita apenas Gol FT/HT que já possua odd atual, qualidade de
dados de pelo menos 80 e nota técnica de pelo menos 65, e cujo único bloqueio
seja atividade recente insuficiente. Cada partida produz no máximo uma decisão
por mercado. Essas decisões usam o estado `simulacao`, são liquidadas pelo
backtest, não entram na calibração oficial, não são enviadas ao Telegram e nunca
são aplicadas automaticamente.

Em 08/08/2026, os 43 resultados conhecidos de Gol FT da versão v1 foram
congelados como desenvolvimento. A mesma definição passou a gravar somente
novos jogos como `exploracao-atividade-gols-validacao-v2`. Gol FT e Gol HT são
avaliados separadamente e precisam de pelo menos 30 resultados futuros antes
de uma revisão independente. Atingir 30 apenas libera a revisão estatística:
não aprova a regra, não altera a calibração e não envia sinal ao Telegram.

## TheStatsAPI como apoio reversível ao PackBall

A TheStatsAPI funciona como fonte auxiliar: pode ajudar a priorizar qual jogo
acionável o PackBall deve confirmar primeiro, mas não autoriza sinais sozinha.
As regras, a calibração, o Telegram e a liquidação continuam protegidos. O
histórico auxiliar usa tabelas separadas e pode permanecer no banco mesmo se a
assinatura da API for encerrada.

O retorno ao funcionamento anterior não exige apagar arquivos nem dados. Para
desligar a integração, defina `THESTATSAPI_SOMBRA_ATIVA=0` no `.env`, faça uma
parada segura e inicie novamente o sistema. Sem a chave da TheStatsAPI, a
integração também fica desativada automaticamente. Nesses dois casos não há
chamada, prioridade auxiliar, bloqueio de fonte ou dependência nova no fluxo
PackBall + API-Football.

Frase operacional combinada: **VOLTAR SEM THESTATS**. Ela significa desativar
somente essa integração pelo recurso acima, preservar todo o histórico e nunca
reverter ou apagar o restante do projeto.

## Compactação segura e retomada operacional V52 — 11/09/2026

A manutenção explícita `compactar_backups_legados.py` opera em modo de
previsualização por padrão. A execução exige modo de manutenção ativo e
monitor/watchdog encerrados. Cada SQLite é verificado antes da compactação e o
arquivo `.db.gz` passa por checksum, descompactação e nova verificação SQLite;
o original só é removido depois do round-trip completo. Em bloqueio transitório
do Windows, os dois formatos válidos são preservados e a limpeza fica pendente
para nova tentativa.

O lote real compactou dez backups válidos e recuperou 18.591,4 MB. O watchdog
mediu uma redução física total de 18.596,4 MB e cerca de 68 GB livres após a
manutenção. `monitor_20260906.db` apresentou esquema legado incompatível, foi
preservado sem alteração e recebeu um marcador auditável para não ser tentado
indefinidamente. O arquivo de nome não gerenciado
`pre_escanteios_ft_prospectivo_20260909_203204.db` também permaneceu intocado.

Quedas materiais de armazenamento agora reiniciam a estimativa de crescimento
no novo patamar, preservando em resumo a quantidade de amostras, o último nível
e o total recuperado. Oscilações pequenas do WAL continuam na mesma série. No
estado real, a tendência foi reancorada em aproximadamente 21,3 GB e o falso
alerta `crescimento_armazenamento_critico` desapareceu.

O login PackBall passou a herdar exatamente o mesmo intervalo, teto, janela e
distribuição usados pelo monitor. Isso elimina o intervalo de 12 segundos que
criava uma degradação temporária após renovação de sessão. A auditoria final
registrou ritmo seguro de 19,25 segundos, mínimo observado de 19 segundos com a
tolerância prevista, zero violações e zero excesso de janela.

Após a retomada, o ciclo de 11/09/2026 00:02:49 processou 3 de 3 partidas, sem
adiamentos, falhas de cache/API, bloqueios de fonte ou pausa preventiva. O
backup diário `monitor_20260911.db.gz` foi criado e verificado. A prontidão
encerrou em `coleta_profissional_em_validacao`, sem falha técnica ativa; as 11
pendências restantes dependem de amostras futuras, controle experimental ou
backup externo. A regressão direcionada passou em 654/654 testes. Nenhuma regra
de sinal HT ou FT foi alterada nesta manutenção.

## Funil causal do Gol FT e telemetria persistente V53 — 11/09/2026

As regras operacionais, os limites, a calibração, a promoção de sinais e os
envios ao Telegram de Gol HT e Gol FT permaneceram inalterados. A V53 adicionou
somente observabilidade causal: o filtro preciso de Gol FT agora informa quantos
candidatos chegaram, quantos foram elegíveis e quais motivos bloquearam os
demais, sem consultar resultados ou entregas para tomar a decisão.

Na base real, o funil preciso encontrou 11 decisões independentes: 4 elegíveis
e 7 recusadas. Cinco recusas ocorreram por minuto fora da janela e duas por
histórico de faixa insuficiente. A coorte continua pequena, com 4 resultados
válidos, 2 greens e 2 reds; portanto, não há evidência suficiente para afrouxar
ou endurecer o FT.

O diagnóstico do gerador passou a ser persistido em cada snapshot para formar
histórico prospectivo por ramo. As duas primeiras observações reais do FT no
segundo tempo ocorreram aos minutos 56 e 54 e foram bloqueadas, uma por faixa
histórica não confirmada e outra por odd fora da faixa. Duas observações não
permitem concluir tendência nem vantagem.

O agendador pré-live também passou a usar o relógio injetado de forma consistente
no encerramento, nas tentativas e na retenção, eliminando expiração dependente
da data do computador em testes e simulações. Isso não altera critérios de sinal.

A regressão integral passou em 2.545/2.545 testes. Após reinício controlado, o
monitor, o watchdog, o pré-live e a navegação PackBall ficaram ativos; o ciclo
confirmado de 11/09/2026 00:22:12 terminou saudável, sem falha técnica ativa.

## Quase-candidatos causais do Gol FT V54 — 11/09/2026

O Gol FT passou a acompanhar, somente em sombra, dois possíveis desajustes do
filtro preciso. O braço `minuto_61_75` testa exclusivamente a extensão do
minuto máximo de 60 para 75. O braço `historico_8_11` testa exclusivamente a
redução do histórico mínimo de 12 para 8 gols na faixa comparável. Um candidato
só entra se, depois da substituição desse único valor, todos os demais critérios
originais forem aprovados. Falhar em duas barreiras exclui o jogo dos dois
braços.

Cada braço congela os primeiros 60 jogos, separados em 42 de desenvolvimento e
18 de holdout. Uma revisão favorável exige pelo menos 55 resultados válidos,
meta de 75% de greens, ROI positivo com limite inferior do IC95 acima de zero,
desempenho positivo tanto no desenvolvimento quanto no holdout e vantagem sobre
a referência conservadora de 1/odd. Os primeiros 25 resultados formam um
checkpoint fixo de segurança.

A seleção não consulta resultados nem entregas, não modifica sinais, odds,
qualidade, atividade ou fontes e não envia Telegram. A promoção e a reativação
automáticas permanecem proibidas. A âncora foi registrada em
11/09/2026 00:37:58; por isso a coorte começou corretamente em zero e não usa os
11 casos anteriores como validação.

A regressão integral passou em 2.554/2.554 testes. Monitor, watchdog e pré-live
carregaram os hashes novos. O primeiro ciclo posterior à retomada terminou às
00:40:41 com 2 partidas, sem falha técnica; a validação e as duas coortes ficaram
saudáveis. Nenhuma regra operacional de HT ou FT foi alterada.

## Liquidações asiáticas explicáveis V55 — 11/09/2026

A integridade da calibração passou a separar três classes que antes apareciam
somadas como `invalidas`: devolução contratual (`void/push`), partida encerrada
sem resultado utilizável e falha técnica real de odd, retorno ou relógio. Os
contadores antigos e todos os bloqueios conservadores foram preservados; a
mudança é exclusivamente de observabilidade e não converte devolução em green
ou red.

Na coorte real de escanteios asiáticos FT foram selecionadas 43 partidas: 39
liquidações binárias válidas e 4 não calibráveis pelo modelo genérico. A nova
decomposição provou que essas quatro são 3 devoluções legítimas, 1 encerramento
sem dado e 0 falhas técnicas. O validador asiático prospectivo dedicado continua
sendo a fonte correta para green, half-green, void, half-red, red e ROI; sua
coorte futura de 100 candidatos segue independente e ainda não alterou o mercado.

Nenhuma regra operacional, faixa de odd, geração de sinal ou envio de HT/FT foi
alterado pela V55. A regressão integral passou em 2.555/2.555 testes. Após a
retomada controlada, monitor, watchdog e pré-live carregaram os hashes atuais;
o primeiro ciclo encerrou às 00:50:58 com 2 partidas, zero falhas consecutivas
e sem pausa preventiva.

## Cobertura do motor por versões operacionais V56 — 11/09/2026

O watchdog deixou de considerar apenas a versão padrão `sinais-v6` ao auditar
se cada snapshot recente recebeu candidatos. A supervisão agora reconhece o
conjunto exato de versões operacionais vigentes de Gol FT, Gol HT, próximo gol
e escanteios, mantendo compatibilidade com auditorias que informem uma única
versão.

Essa correção elimina um falso alerta produzido quando um snapshot não tinha
registro `sinais-v6`, mas possuía decisões válidas das regras especializadas.
Na janela real auditada, a leitura antiga indicava 13/15 snapshots (86,7%); a
leitura completa comprovou 16/16 (100%), com odds estruturadas em 15/16. A
auditoria integral de validação voltou a ficar saudável, sem motivos ou avisos.

A detecção continua falhando fechado quando nenhuma das versões informadas gera
candidato. Não houve alteração em candidatos, filtros, calibração, Telegram,
HT ou FT; mudou apenas a interpretação da cobertura pelo supervisor. Os 409
testes diretamente relacionados e a regressão integral de 2.556 testes
passaram. Após a retomada controlada, os três processos carregaram os hashes
atuais; o ciclo de 01:02:24 processou 1/1 tarefa e o watchdog confirmou
validação saudável, cobertura 13/13, zero falhas e nenhuma pausa preventiva.

## Referência independente de odds em sombra V57 — 11/09/2026

A investigação do desajuste de preços encontrou 46 observações válidas da
Bet365/BetsAPI, mas nenhuma comparação independente na mesma linha. A causa era
estrutural: quando a BetsAPI fornecia o mercado operacional, esse mercado era
retirado antes da consulta à The Odds API. Assim, o sistema não tinha uma
segunda cotação comparável e não podia comprovar vantagem de preço.

A V57 adicionou uma amostragem independente e estritamente observacional para
odds de gols FT já cobertas pela BetsAPI. A coleta é limitada a 2 jogos por
ciclo, 30 reservas por dia e uma consulta por jogo a cada 10 minutos. As
reservas são persistidas antes da chamada externa para impedir rajadas após
falhas ou reinícios. A cotação independente é salva no SQLite como
`referencia_sombra`, separada da odd operacional.

Essa referência nunca é incorporada às odds usadas pelo motor. Ela não aprova
sinal, não altera HT ou FT, não envia Telegram e não permite promoção
automática. O avaliador prospectivo só forma pares exatos de mercado, período,
linha, lado, placar, minuto e instante, e continua exigindo fontes distintas.
Até surgirem partidas naturalmente elegíveis, nenhuma vantagem deve ser
considerada comprovada.

A regressão integral passou em 2.562/2.562 testes e o preflight autorizou a
retomada. A primeira tentativa de reinício ficou sem permissão para abrir o
navegador e foi encerrada com segurança; a retomada com a permissão correta
restaurou PackBall, monitor, watchdog e pré-live. O ciclo de 01:23:29 terminou
com sucesso, sem partidas ao vivo naquele instante; em seguida o watchdog
confirmou estado saudável, zero falhas consecutivas e nenhuma pausa preventiva.
As regras de HT e FT permaneceram inalteradas.

## Supervisão da referência independente V58 — 11/09/2026

A coleta sombra de odds ganhou uma auditoria automática no watchdog. Cada
ciclo agora registra se havia mercado de gols FT elegível na BetsAPI, se a
consulta independente foi realmente reservada e quantas cotações chegaram ao
SQLite. Somente uma chamada que consumiu reserva conta como tentativa; ausência
de jogos, cooldown e limite diário não são classificados como falha.

Três tentativas reservadas consecutivas sem nenhuma cotação persistida geram
um aviso de cobertura. Três falhas técnicas consecutivas são identificadas
separadamente. Uma cotação persistida encerra a sequência e comprova a
recuperação. Como essa investigação é observacional, o aviso nunca bloqueia o
motor, não muda HT/FT, não envia sinal e não promove estratégia.

A reserva também passou a permanecer visível quando a consulta externa falha
depois de consumir orçamento, evitando o falso diagnóstico de que a chamada
nunca ocorreu. Os módulos afetados passaram em 532 testes e a regressão
integral em 2.567/2.567. O preflight completo autorizou a retomada. Monitor,
watchdog e pré-live carregaram os novos códigos; o ciclo de 01:35:27 terminou
com sucesso e o watchdog confirmou estado saudável, zero falhas e nenhuma
pausa. Como não havia partidas ao vivo, a nova auditoria registrou corretamente
`sem_oportunidade`, sem aviso.

## Circuito persistente da fonte independente V59 — 11/09/2026

O circuito de proteção da The Odds API, antes mantido apenas na memória, passou
a persistir falhas consecutivas, motivo e prazo de bloqueio. Depois de três
falhas transitórias, novas chamadas ficam suspensas por 120 segundos; respostas
401, 403 ou 429 preservam o bloqueio de 15 minutos. Reiniciar o bot não apaga
mais essa proteção nem permite gastar novas reservas durante o intervalo.

Ao final do prazo, uma tentativa controlada é liberada automaticamente. Se ela
funcionar, falhas e bloqueio são zerados e a recuperação fica persistida; se
falhar, o circuito volta a proteger o orçamento. O status e a telemetria dos
ciclos agora mostram estado, falhas, motivo e tempo restante. A proteção não
altera filtros, sinais, HT, FT ou Telegram.

A regressão integral passou em 2.568/2.568 testes e o preflight completo
autorizou o reinício. Monitor, watchdog e pré-live carregaram os novos códigos.
O ciclo de 01:45:49 terminou com sucesso; o watchdog ficou saudável, com zero
falhas, nenhuma pausa e supervisão da referência em `sem_oportunidade`. O
circuito ativo foi confirmado fechado, persistente e com recuperação automática.

## Estado resiliente da fonte independente V60 — 11/09/2026

O controle local da The Odds API passou a usar arquivo principal e backup
atômico. Se o principal estiver inválido, o cliente recupera cotas, reservas e
circuito pelo backup, registra a origem da recuperação e volta a gravar uma
cópia principal válida. Isso evita que uma corrupção isolada apague limites ou
libere chamadas indevidas após reinício.

Se principal e backup estiverem inválidos ao mesmo tempo, o cliente falha
fechado: considera esgotado o limite diário local, preserva a reserva mensal e
não executa chamadas externas. O watchdog identifica esse estado como incidente
da referência independente. Como a fonte continua estritamente em sombra, o
incidente não altera candidatos, regras, sinais, Telegram, HT ou FT.

O estado persistente e o circuito agora aparecem na telemetria mesmo em ciclos
sem partidas. O status informa se a origem foi principal ou backup e se o
controle está saudável ou bloqueado. Os 545 testes dos componentes afetados e a
regressão integral de 2.572/2.572 passaram; o preflight autorizou a retomada.
Após o reinício controlado, monitor, watchdog e pré-live ficaram ativos. O ciclo
de 02:00:27 terminou saudável, com zero falhas e nenhuma pausa, registrando
estado principal saudável, backup presente, fail-closed inativo e circuito
fechado. O FT permaneceu ativo em modo operacional, sem mudança de regra.

## Diversidade do orçamento independente V61 — 11/09/2026

A amostragem sombra da The Odds API passou a limitar cada partida a duas
consultas por dia. A primeira registra a referência independente e a segunda,
somente depois do intervalo de dez minutos, permite uma confirmação temporal.
Consultas adicionais no mesmo jogo são recusadas sem consumir cota, preservando
as 30 reservas diárias para partidas distintas. A contagem é persistente entre
reinícios e zera apenas na mudança legítima do dia UTC.

Além do teto diário, cada ciclo reserva pelo menos uma das duas vagas de coleta
para uma partida ainda não observada: no máximo uma confirmação temporal pode
ser feita no mesmo ciclo. Assim, uma partida repetida não consegue ocupar as
duas consultas do lote e impedir a descoberta de um jogo novo.

O estado principal e o backup agora carregam a mesma revisão lógica. Se houver
uma queda entre as duas gravações, a inicialização escolhe a revisão mais nova e
repara automaticamente a cópia atrasada. Se a reserva não puder ser persistida,
a consulta externa é bloqueada antes da rede. Isso elimina a possibilidade de
consumir orçamento sem um registro durável.

O status mostra partidas distintas, maior repetição e teto por jogo. A
telemetria preserva esses dados inclusive em ciclos vazios. Nada dessa camada é
usado para aprovar apostas, alterar HT/FT ou enviar Telegram; ela apenas acelera
a formação da coorte independente que medirá desajustes reais.

Os módulos afetados passaram nos testes direcionados e a regressão integral em
2.577/2.577. O preflight de 02:23:42 aprovou banco, configuração, sessão,
dependências, coleta e testes. O primeiro ciclo encontrou uma
tela transitória do PackBall sem a lista Ao Vivo e falhou fechado; o mesmo
processo recuperou automaticamente no ciclo de 02:15:41. O watchdog então
confirmou estado saudável, zero falhas e nenhuma pausa preventiva. Monitor,
watchdog, pré-live e FT ficaram ativos, sem mudança de regra. Um novo ciclo às
02:25:02 confirmou na telemetria o teto de duas amostras por jogo/dia, uma
confirmação repetida por ciclo e prioridade explícita para partidas novas.

## Migração imediata do estado independente V62 — 11/09/2026

O controle legado válido da The Odds API agora recebe uma revisão lógica já na
inicialização. A migração grava principal e backup sem consumir reserva diária,
sem chamar a rede e sem esperar que apareça uma partida elegível. Se qualquer
gravação falhar, a fonte independente fica bloqueada de forma conservadora; os
sinais oficiais continuam isolados dessa camada sombra.

A regressão integral passou em 2.578/2.578 testes e o preflight de 02:28:44
autorizou a retomada. Após a parada completa dos três processos, monitor,
watchdog e pré-live reiniciaram com os hashes atuais. O ciclo de 02:29:51
terminou saudável, sem pausa, e exibiu revisão 1, origem principal, backup
presente e fail-closed inativo. Os dois arquivos persistidos ficaram idênticos.
O FT permaneceu `ativo_manual`; nenhuma condição HT/FT ou entrega Telegram foi
alterada.

## Auditoria de representatividade da referência V63 — 11/09/2026

Cada tentativa futura da amostragem sombra da The Odds API agora fica gravada
separadamente no SQLite, inclusive quando o provedor não encontra o evento ou
não cobre a competição. O registro identifica se era uma partida nova ou uma
confirmação temporal, a posição ocupada na fila, o total de tarefas do ciclo,
a fila operacional, liga e minuto. A escolha continua sendo feita antes de
conhecer o resultado.

Uma consulta sombra sem cotação não pode mais herdar por engano uma oferta da
The Odds API usada no fluxo operacional. Isso preserva a causalidade da
amostra e impede que uma ausência pareça disponibilidade. O status só avalia
concentração no começo ou no fim da fila depois de 30 tentativas futuras com
contexto; antes disso informa `aguardando_30_amostras`. Dados antigos não são
retroclassificados.

Os 303 testes diretamente afetados e a regressão integral de 2.579/2.579
passaram. O banco principal foi migrado com `quick_check=ok`, e o backup diário
de 2,68 GB foi regenerado, compactado e verificado. Monitor, watchdog e
pré-live reiniciaram com os hashes atuais. Como as 30 reservas independentes
do dia já haviam sido usadas antes da implantação, a nova coorte começa nas
próximas tentativas legítimas, sem chamadas extras. A camada continua
estritamente observacional: não muda HT/FT, sinais, Telegram ou promoção.
O primeiro ciclo real terminou às 11:21:48 com 76 partidas encontradas, oito
tarefas processadas, todas com odds utilizáveis, API saudável, zero bloqueios
por fonte, zero falhas consecutivas e nenhuma pausa preventiva.

## Edge multifonte sem margem da casa V64 — 11/09/2026

O avaliador de preço passou a exigir o mercado binário completo nas duas
fontes: Over e Under da mesma linha, período, placar, minuto e janela temporal.
A margem de cada bookmaker é removida antes da comparação. A probabilidade
sem vig da fonte independente é usada apenas para medir o valor esperado da
odd Over executável na Bet365; diferenças de margem entre casas não podem mais
ser confundidas com vantagem real.

Fotografias com bookmaker desconhecida, fontes não independentes, mercado
incompleto ou margem implausível são descartadas. A definição foi
pré-registrada de forma imutável no SQLite antes da primeira observação. A
coorte é prospectiva e fixa em 60 partidas independentes, dividida em 42 para
desenvolvimento e 18 para holdout; a primeira revisão metodológica exige ao
menos 30 partidas e 15 jogos distintos. Até haver resultados e convergência
suficientes, a conclusão permanece `vantagem_executavel_comprovada=false`.

Uma inspeção histórica exploratória encontrou 11 fotografias completas e um
candidato com EV sem vig estimado em 5,0%. Esse achado não é prova, não entra
na coorte futura e não autoriza promoção. A camada continua em sombra: não
altera HT, FT, pré-live, sinais, Telegram ou prioridade. O watchdog valida o
contrato, isola qualquer dado inconsistente e nunca transforma adulteração em
vantagem.

Os 378 testes dos componentes afetados e a regressão integral de
2.582/2.582 passaram. O preflight de 11:36:49 aprovou banco, backup, sessão,
dependências e configuração. Monitor, watchdog e pré-live reiniciaram com os
hashes atuais. O primeiro ciclo V64 terminou às 11:45:22 com 69 partidas,
cinco tarefas processadas, todas com odds utilizáveis, API saudável, zero
bloqueios por fonte, zero falhas consecutivas e nenhuma pausa preventiva. A
âncora futura do edge sem vig foi gravada às 11:45:18, com zero observações
anteriores aceitas, como exigido. O FT permaneceu `ativo_manual`.

## Liquidação prospectiva do edge por mercado V65 — 11/09/2026

A avaliação sem margem passou a acompanhar o resultado final de cada candidato
selecionado depois da nova política imutável. Gols FT e escanteios FT formam
coortes próprias, evitando que mercados com comportamento e liquidação
diferentes sejam somados na mesma conclusão. Para esta primeira prova entram
somente linhas terminadas em `.5`, nas quais não existe devolução; linhas
inteiras e quarter lines permanecem fora até receberem metodologia específica.

Cada mercado terá 60 partidas independentes, divididas em 42 de desenvolvimento
e 18 de holdout. O relatório compara EV previsto, ROI realizado, taxa de green,
calibração, Brier score e intervalos de confiança. Uma revisão só pode chamar o
resultado de favorável após pelo menos 50 liquidações totais, 35 no
desenvolvimento e 15 no holdout, com ROI positivo nas duas partes e limite
inferior do intervalo de 95% do ROI total acima de zero.

O watchdog valida a cronologia, as contagens, a partição e a política; qualquer
adulteração isola apenas essa experiência. Mesmo uma conclusão estatística
favorável continuará sem efeito automático: não muda HT, FT, pré-live,
prioridade, Telegram ou aprovação de sinais.

Os 566 testes dos componentes afetados e a regressão integral de 2.588/2.588
passaram. O preflight de 11:59:01 aprovou banco, backups, sessão, dependências,
configuração e reinício seguro. Monitor, watchdog e pré-live retomaram com os
hashes atuais. O primeiro ciclo V65 terminou às 12:09:02 com 77 partidas, seis
tarefas processadas, todas com odds utilizáveis, API saudável, zero bloqueios
por fonte, zero falhas consecutivas e nenhuma pausa preventiva. A política de
liquidação foi registrada às 12:08:59 com zero candidatos anteriores aceitos;
o watchdog confirmou avaliação, edge e liquidação saudáveis. O FT permaneceu
`ativo_manual`.

## Probabilidade individual causal e prospectiva V66 — 11/09/2026

A taxa histórica geral deixou de ser tratada como se fosse a chance individual
de um jogo. O novo avaliador parte da probabilidade implícita na odd e só tenta
aprender o desvio explicado pelo contexto disponível antes do resultado, como
tempo restante, momento ao vivo e perfis ofensivo e defensivo das equipes. A
validação usa três cortes temporais independentes, sem treinar com partidas do
futuro.

Um modelo só pode iniciar a coorte prospectiva se superar simultaneamente a odd
e a taxa observada por pelo menos 0,002 de Brier, mantiver erro de calibração em
no máximo 0,10 e não regredir materialmente em nenhum corte. Depois disso ainda
serão exigidas 60 previsões futuras imutáveis, divididas em 42 de
desenvolvimento e 18 de holdout, com revisão mínima de 50 resultados e partição
35/15. A previsão precisa ser registrada antes da liquidação.

Na implantação, os dois mercados foram corretamente recusados. No HT, 90
validações tiveram Brier 0,23923 contra 0,23819 da odd; no FT, 0,22802 contra
0,22646. Como menor é melhor, o modelo contextual ficou ligeiramente pior nos
dois casos. Nenhuma definição foi congelada, nenhuma previsão futura foi
aceita e nenhuma probabilidade foi exibida ou usada nos sinais.

As definições e previsões futuras são protegidas contra alteração e exclusão no
SQLite. O watchdog valida versão, hashes, cronologia, partição e contagens. A
camada permanece estritamente em sombra: aplicação em sinais, calibração,
prioridade, promoção, reativação e Telegram estão todas desativadas.

A regressão integral passou em 2.598/2.598 testes. O preflight bloqueou a
primeira tentativa até que os dois gatilhos imutáveis fossem migrados e o backup
diário fosse regenerado. Uma inicialização sob permissão restrita do Windows
falhou fechada antes da coleta; a retomada controlada com a permissão correta
recuperou os três processos. O primeiro ciclo real terminou às 12:43:12 com 94
partidas, oito tarefas processadas, seis com odds utilizáveis, API saudável,
zero bloqueios por fonte e nenhuma pausa preventiva. A avaliação V66 ficou
saudável e íntegra, e o watchdog confirmou que ela não influencia HT, FT ou
Telegram.

## Referência individual sem margem V67 — 11/09/2026

A referência da probabilidade individual deixou de usar `1 / odd` diretamente.
O avaliador agora reconstrói, no mesmo snapshot, o par binário Over/Under e
remove a margem da casa antes de comparar o modelo contextual. Fotografias sem
par exato, ambíguas ou com margem inválida são descartadas. A cobertura mínima
é 95%; a implantação encontrou 100% no HT e 99,66% no FT, com margens médias de
7,96% e 7,67%, respectivamente.

Essa mudança evita atribuir ao modelo uma melhora que veio apenas da remoção do
overround. O modelo continua tendo de melhorar o Brier da referência sem margem
em pelo menos 0,002, manter erro de calibração em até 0,10 e não regredir mais de
0,01 em nenhum dos três cortes temporais. A consulta à referência é anterior ao
resultado e não usa o placar final.

A nova prova rejeitou corretamente os dois mercados. No HT, o Brier foi
0,23914 contra 0,23729 do mercado sem margem; no FT, 0,22705 contra 0,22699.
Nenhuma definição foi congelada e nenhuma previsão prospectiva foi liberada.
Sinais, regras HT/FT, calibração oficial, prioridade e Telegram seguem sem
qualquer influência dessa camada.

Os 672 testes direcionados e a regressão integral de 2.605/2.605 passaram. O
preflight de retomada aprovou as verificações obrigatórias, monitor, watchdog e
pré-live iniciaram com os hashes atuais, e o primeiro ciclo V67 terminou às
13:07:38 com 124 partidas, 28 tarefas agendadas, cinco processadas, duas com
odds utilizáveis, API saudável, zero sinais bloqueados por fonte e nenhuma
pausa preventiva. Às 13:08:31, o watchdog reconheceu a versão V67, permaneceu
saudável, com zero falhas consecutivas e a avaliação em formação.

## Pré-seleção de cobertura da referência V68 — 11/09/2026

A amostragem da fonte independente passou a consultar primeiro o catálogo de
competições, cujo custo estimado é zero, e só reserva uma oportunidade diária
quando país e campeonato possuem cobertura compatível. A verificação de país é
obrigatória porque nomes genéricos, como `Premier League`, existem em vários
países. Esse refinamento evita gastar a cota limitada em partidas que não
podem produzir uma comparação útil.

O diagnóstico anterior encontrou 30 reservas distribuídas por 16 partidas,
mas apenas uma oferta disponível. A inspeção real do catálogo confirmou a
2. Bundesliga como coberta e descartou corretamente a Premier League do
Bahrein; nenhuma consulta de eventos ou odds foi feita e o consumo permaneceu
inalterado. O intervalo temporal máximo de 60 segundos entre fontes não foi
relaxado.

Os 640 testes direcionados e a regressão integral de 2.610/2.610 passaram. O
primeiro ciclo final V68 terminou às 13:35:21 em 161,036 segundos, com 136
partidas e API saudável. Duas partidas elegíveis na BetsAPI foram descartadas
antes da reserva por falta de cobertura, economizando duas oportunidades; não
houve reserva, consulta ou efeito em sinais. Às 13:36:32, o watchdog validou as
duas pré-seleções, os dois descartes e as duas reservas economizadas, mantendo
saúde normal, zero falhas consecutivas e nenhuma pausa preventiva. Monitor,
watchdog e pré-live permanecem ativos. A mudança é somente de auditoria em
sombra e não altera HT, FT, pré-live, prioridade, Telegram ou aprovação.

## Pareamento gratuito do evento antes da reserva V69 — 11/09/2026

Depois de confirmar país e campeonato, a amostragem independente agora exige
também o pareamento forte da partida antes de reservar uma consulta de odds.
Essa etapa usa o endpoint gratuito de eventos e valida mandante, visitante,
orientação e janela de início. Somente um evento inequivocamente pareado pode
consumir a pequena cota diária; ausência, ambiguidade ou falha permanecem fora
da reserva e são persistidas para auditoria.

Uma prova real, feita em estado temporário, pareou Nürnberg x Hannover 96 com
o evento da 2. Bundesliga e similaridade de 94,44%. Houve consulta de catálogo
e eventos, mas nenhuma consulta de odds, nenhuma reserva e consumo zero do
provedor. Os novos contadores distinguem eventos pareados, descartados e a
economia específica desse filtro; o watchdog verifica suas somas e falha
fechado diante de adulteração.

Os 644 testes direcionados e a regressão integral de 2.614/2.614 passaram. O
preflight integral liberou a retomada e o primeiro ciclo V69 terminou às
13:55:03 com 139 partidas, 28 tarefas agendadas, cinco processadas, três com
odds utilizáveis, API saudável, zero bloqueios por fonte e nenhuma pausa. Não
houve partida elegível na BetsAPI nesse ciclo, portanto a nova ramificação não
foi forçada artificialmente. Às 13:55:41, o watchdog confirmou o ciclo e
permaneceu saudável, com zero falhas. Monitor, watchdog e pré-live estão ativos;
HT, FT, pré-live, prioridade, Telegram e aprovação de sinais não foram alterados.

## Amostragem independente ampliada com orçamento protegido V70 — 11/09/2026

A auditoria de prontidão mostrou que o gargalo profissional continua sendo a
falta de amostra prospectiva de preço justo, e não uma falha de envio. Antes de
aumentar a coleta, duas hipóteses foram testadas e recusadas: exigir concordância
temporal PackBall/API-Football não melhorou gols na amostra exploratória, e uma
recalibração temporal simples do mercado sem margem piorou o Brier no HT em
0,00472 e no FT em 0,00178. Nenhuma das duas foi ligada aos sinais.

A documentação oficial da The Odds API também confirma que os mercados
adicionais usados pelo projeto precisam ser consultados por evento; portanto,
não existe consulta em lote equivalente que preserve esses mercados. Com as
pré-seleções gratuitas V68/V69 já ativas, o teto de amostragem independente foi
ampliado de 30 para 60 reservas por dia. Permanecem os limites de duas reservas
por partida/dia e duas por ciclo, o teto geral de 600 créditos/dia e a reserva
mensal intocável de 2.000 créditos.

No momento da decisão, o provedor informava 19.752 créditos restantes. Mesmo no
pior caso de 60 consultas pagas por dia durante 30 dias, o consumo seria 1.800,
abaixo dessa reserva operacional. A validação carregou exatamente 60/dia, duas
por jogo e duas por ciclo, mantendo `aplicacao_sinais=false` e `telegram=false`.
A regressão integral passou em 2.614/2.614 testes. A mudança acelera a coleta da
prova de edge; ela não aumenta artificialmente a probabilidade, não promove
modelo e não altera HT, FT, pré-live ou alertas oficiais.

A prova no processo de produção foi concluída no primeiro ciclo após a retomada,
encerrado às 14:14:19. O runtime carregou `limite_diario=60`, preservou duas
reservas por jogo, manteve `aplicacao_sinais=false`, `telegram=false` e
`promocao_automatica=false`. Nesse ciclo, três partidas passaram pela
pré-seleção de cobertura, duas foram consideradas cobertas, uma oferta nova foi
consultada, pareada e persistida em sombra, e duas reservas pagas foram
economizadas ao descartar competição/evento inválido antes da consulta. O
provedor encerrou o ciclo com 249 créditos usados e 19.751 restantes. O
watchdog permaneceu saudável, com zero falhas consecutivas e sem pausa
preventiva; o monitor iniciou normalmente o ciclo seguinte.

## Referência independente multitemporal combinada V71 — 11/09/2026

A V70 ampliou o número de partidas observáveis, mas a auditoria do código
revelou uma assimetria: a amostragem sombra solicitava somente gols FT, embora
o cliente da The Odds API já suportasse gols HT e escanteios asiáticos FT. A
documentação oficial recomenda combinar vários mercados no mesmo pedido para
reduzir chamadas e respostas 429. O custo, porém, continua sendo a quantidade
de mercados multiplicada pela região; por isso ele não foi tratado como uma
consulta gratuita.

O cliente agora faz uma única requisição por evento com todos os mercados
compatíveis, em ordem determinística, e reserva antecipadamente o custo real de
um, dois ou três créditos. O amostrador aceita somente a interseção que a
Bet365/BetsAPI comprovou existir entre `gol_ft`, `gol_ht` e
`escanteios_ft_asiatico`. Assim, começa a formar referência independente para
HT e escanteios sem criar mercados, sem misturar períodos e sem fazer qualquer
alteração no motor de sinais.

O pior caso local é de 180 créditos/dia para 60 amostras com os três mercados,
abaixo do teto geral de 600/dia. O cliente continua bloqueando antes da chamada
se ela ultrapassar o teto diário ou invadir a reserva mensal de 2.000 créditos.
Toda a coleta permanece com `aplicacao_sinais=false`, `telegram=false` e
`promocao_automatica=false`.

A regressão específica passou em 286/286 testes e a regressão integral em
2.616/2.616. O primeiro ciclo de produção da V71 terminou às 14:28:37 com 140
partidas, quatro tarefas, API saudável, zero falhas e nenhuma pausa preventiva.
Nenhuma tarefa daquele ciclo possuía um mercado suportado simultaneamente na
BetsAPI, então a amostragem fez zero reservas e zero consultas, como exigido.
Isso prova o comportamento de segurança; a primeira observação combinada real
ainda precisa ocorrer naturalmente antes de validar cobertura ou utilidade.

## Auditoria causal por mercado e custo V72 — 11/09/2026

Para impedir que volume agregado esconda a ausência de cobertura em um mercado,
cada ciclo agora registra separadamente, para `gol_ft`, `gol_ht` e
`escanteios_ft_asiatico`, quantas partidas foram elegíveis, quantos mercados
foram efetivamente consultados e quantos receberam oferta completa. O mesmo
resumo registra créditos estimados reservados, quantidade de consultas
combinadas e o maior número de mercados em uma chamada.

O watchdog passou a conferir as identidades causais desses contadores. Mercados
anexados não podem superar mercados consultados; consultados não podem superar
elegíveis; a soma anexada precisa coincidir com os mercados persistidos; uma
consulta combinada precisa possuir pelo menos dois mercados; e o custo deve
ficar entre uma e três unidades por reserva e cobrir o maior pedido. Qualquer
inconsistência produz `amostragem_referencia_multimercado_inconsistente` e
requer atenção, sem autorizar sinais, Telegram ou promoção.

A regressão direcionada passou em 524/524 testes e a integral em 2.618/2.618.
O primeiro ciclo de produção terminou às 14:42:19 com 146 partidas e sete
tarefas. Seis avaliações não possuíam mercado comum na BetsAPI; os contadores
ficaram coerentemente em zero para reserva, consulta, persistência, custo e
combinação. A verificação read-only do watchdog classificou a telemetria como
saudável, sem inconsistências, e os três processos permaneceram ativos.

## Circuito persistente da BetsAPI V73 — 11/09/2026

A investigação da primeira janela V72 confirmou que a ausência de amostra não
era perda silenciosa na mescla: na única partida com dado BetsAPI persistido, a
fonte ofereceu somente `proximo_gol`; não havia `gol_ft`, `gol_ht` nem
`escanteios_ft_asiatico` comum para uma comparação independente segura. O
filtro continuou fechado e não consumiu crédito para fabricar cobertura.

A mesma auditoria encontrou uma falha de recuperação: contagem de erros e
tempo de bloqueio da BetsAPI existiam somente na memória. Uma reinicialização
podia apagar o backoff após HTTP 401, 403 ou 429 e voltar a chamar o provedor
antes do prazo. A V73 persiste falhas consecutivas, instante de desbloqueio,
motivo e atualização no estado atômico já utilizado pela fonte. Reinícios agora
restauram o circuito; falhas HTTP transitórias também abrem backoff após três
ocorrências, e uma resposta válida fecha e persiste a recuperação.

Se o próprio estado do circuito não puder ser salvo, novas chamadas ficam
bloqueadas na instância e o watchdog deixa de considerar a BetsAPI uma fonte
oficial disponível para encobrir degradação da API-Football. O diagnóstico do
ciclo expõe circuito aberto, tempo restante, motivo, persistência e recuperação
automática. A mudança protege a coleta e o orçamento; não altera condições HT,
FT, pré-live, probabilidade, prioridade ou texto de entrada.

Os 520 testes direcionados e a regressão integral de 2.623/2.623 passaram. A
validação cobre reinício durante HTTP 429, recuperação após o prazo, soma de
falhas temporárias entre reinícios, falha de persistência em modo fechado e a
interpretação correspondente pelo watchdog.

A retomada real iniciou monitor, watchdog e pré-live às 14:55:57. Durante o
primeiro ciclo, três falhas transitórias consecutivas da BetsAPI abriram o
backoff de 120 segundos e o novo estado foi gravado com persistência saudável.
Após o prazo, uma tentativa controlada ainda encontrou a fonte indisponível,
incrementou a sequência para quatro e renovou o backoff, sem rajada de chamadas.
O ciclo terminou às 15:00:38 com 122 partidas, quatro tarefas processadas, API-
Football saudável, zero sinais bloqueados e nenhuma pausa. Às 15:01:53, o
watchdog reconheceu o circuito V73 persistido, permaneceu saudável e confirmou
o último ciclo; os três processos continuaram ativos.

## Referência independente sincronizada com a entrada V74 — 11/09/2026

A avaliação V73 encontrou 128 observações rápidas da Bet365, mas nenhuma
contraparte independente dentro do mesmo placar, minuto, linha e janela máxima
de 60 segundos. A causa era temporal: a amostragem da The Odds API acontecia no
ciclo completo e podia chegar muito depois da fila rápida que detectava a
entrada. A V74 aproxima essa fotografia do instante real da decisão.

Quando a fila dedicada encontra uma odd BetsAPI/Bet365 válida de gols HT ou FT,
ela pode consultar no máximo uma referência independente por rodada. Antes de
gastar crédito, continuam obrigatórios os filtros gratuitos de campeonato e de
evento; os limites persistentes por dia, partida, cooldown, orçamento mensal e
circuitos dos provedores permanecem valendo. Linha, período, lados do mercado,
times, orientação e placar recebem identidade explícita antes da persistência.

A referência é gravada como observação append-only e comparada apenas quando a
linha é exatamente a mesma. A consulta ocorre depois da materialização de um
alerta já aprovado, portanto não acrescenta latência à entrega. Odds usadas pelo
motor operacional não são modificadas. Toda a nova ramificação declara e o
watchdog exige `aplicacao_sinais=false`, `telegram=false` e
`promocao_automatica=false`; contadores impossíveis tornam o trabalhador
insalubre em vez de encobrir a falha.

Foram aprovados 678 testes direcionados e a regressão integral de 2.629/2.629.
Um teste ponta a ponta adicional cria uma cotação BetsAPI/Bet365 e uma
referência The Odds/Pinnacle no mesmo instante, comprova a custódia das duas
fontes no SQLite e exige que o avaliador forme exatamente um par temporal da
mesma partida, mercado, linha e placar.
Monitor, watchdog e pré-live foram retomados às 15:23:41. Na primeira auditoria
após a inicialização, o watchdog confirmou o monitor e o trabalhador rápido
ativos, a integridade da referência sincronizada e nenhum efeito sobre sinais.
O primeiro ciclo terminou às 15:28:21 com 122 partidas, cinco tarefas
processadas, cinco coletas de odds bem-sucedidas, API saudável, zero sinais
bloqueados e nenhuma pausa. Às 15:29:39, o watchdog confirmou esse ciclo e
permaneceu saudável, com zero falhas; monitor, watchdog e pré-live continuaram
respondendo.
Uma observação real depende de surgir naturalmente uma fila BetsAPI/Bet365 de
gols HT ou FT que também passe pelos filtros da fonte independente; ela não será
fabricada para antecipar a prova prospectiva.

## Evidência sincronizada acumulada V75 — 11/09/2026

Os contadores V74 descreviam somente a última rodada de 15 segundos. Uma
referência real podia ser corretamente persistida no SQLite e, ainda assim,
deixar de aparecer no estado operacional assim que a rodada seguinte viesse
vazia. A V75 mantém os números da rodada para diagnóstico imediato e acrescenta
um livro acumulado persistente, preservado entre rodadas e reinícios.

O acumulado registra rodadas, tentativas, reservas, consultas, linhas exatas,
auditorias, observações, comparações, créditos estimados, motivos e o instante
da última evidência. Estados legados são migrados a partir da última rodada sem
descartar uma captura já existente. O watchdog valida versão, contadores não
negativos, ordem causal, limite de duas comparações por observação, monotonia
em relação à rodada atual e ausência de efeitos em sinais ou Telegram. Estado
corrompido ou contagem impossível falha de forma fechada.

O relatório de status passou a mostrar lado a lado rodada atual e acumulado.
Isso não altera HT, FT, pré-live, seleção, odd ou texto das entradas: transforma
a evidência temporária em base auditável para uma futura decisão de promoção,
que continua dependente de amostra prospectiva e vantagem líquida comprovada.

Foram aprovados 370 testes direcionados e a regressão integral de 2.633/2.633.
Os testes cobrem acúmulo entre rodadas, sobrevivência a reinício, migração do
estado legado, rejeição de causalidade impossível, rejeição de acumulado menor
que a rodada e apresentação no status.

Monitor, watchdog e pré-live foram retomados às 15:53:30. O estado legado foi
migrado automaticamente; às 15:55 o trabalhador já preservava seis rodadas no
acumulado, com integridade válida e efeitos nulos em sinais e Telegram. Na
auditoria seguinte, o watchdog permaneceu saudável, reconheceu o acumulado V75
presente e íntegro e confirmou o trabalhador ativo. Como ainda não surgiu uma
fila real elegível, tentativas, observações e comparações continuam em zero por
ausência natural, sem fabricação de evidência.

## Prioridade causal da referência no alerta enviado V76 — 11/09/2026

A auditoria do caminho V74 revelou que uma decisão já reprovada pelo motor
podia usar a única vaga de referência independente da rodada. A coleta
continuava em sombra e não alterava o sinal, mas gastava orçamento e podia
impedir a fotografia do próximo alerta realmente enviado. Isso também deixava
a população observacional misturar reprovações com entradas executadas.

A V76 reserva a consulta sincronizada somente para o alerta que terminou a
materialização com estado `enviado`. Decisão reprovada, falha de custódia,
falha de materialização e bloqueio/duplicidade não consultam a fonte externa.
O Telegram é executado antes da referência; portanto a consulta não acrescenta
latência, não autoriza e não bloqueia a entrada.

Um funil novo registra avaliações, aprovações, reprovações, ofertas presentes,
bloqueios de custódia/materialização, alertas enviados, fontes Bet365
executáveis, seleções para consulta, supressões pelo limite da rodada e o motivo
exato das exclusões. O funil é acumulado entre reinícios e distingue tentativas
anteriores à instrumentação sem inventar suas etapas intermediárias. O watchdog
verifica as relações causais e rejeita, por exemplo, tentativa sem alerta
enviado ou acumulado menor que a rodada. O status mostra o principal gargalo.

Foram aprovados 410 testes direcionados e a regressão integral de 2.637/2.637.
Os testes provam que reprovação e materialização bloqueada não gastam a vaga,
que dois alertas enviados respeitam o limite de uma referência por rodada, que
o funil sobrevive ao reinício e que estados causalmente impossíveis falham de
forma fechada. HT, FT, pré-live e critérios de Telegram permanecem inalterados.

Monitor, watchdog e pré-live foram retomados às 16:09:32. O trabalhador migrou
o acumulado anterior e carregou o funil V76 íntegro; às 16:10 já preservava 26
rodadas. Às 16:11:37, o watchdog confirmou trabalhador ativo, referência e
funil acumulado presentes e íntegros, com `aplicacao_sinais=false` e
`telegram=false`. Ainda não houve alerta Bet365 elegível após a implantação;
os zeros do funil representam ausência real de oportunidade, não perda do
estado.

## Coorte causal da referência posterior ao envio V77 — 11/09/2026

A V77 transforma a fotografia independente coletada depois do Telegram em uma
coorte prospectiva ligada ao `sinal_id` exato que foi realmente entregue. Uma
observação só entra na análise se o banco comprovar a entrega, se a referência
for posterior a ela e se partida, mercado, período e linha coincidirem. A fonte
executável precisa ser BetsAPI/Bet365 e a contraparte precisa ser The Odds API
em outro bookmaker, com os dois lados do mercado e margem plausível.

Gols HT e FT são avaliados separadamente. Em cada mercado, o avaliador congela
até 60 sinais com vantagem sem margem estimada de pelo menos 2% e até 60
sinais enviados sem essa vantagem para controle. Os 60 sinais de vantagem são
particionados antes dos resultados em 42 de desenvolvimento e 18 de holdout.
A revisão humana exige pelo menos 50 resultados no total, 35 no
desenvolvimento, 15 no holdout e 30 no controle, além de limite inferior do
intervalo de 95% positivo para o ROI total e para a diferença de ROI contra o
controle, com ROI positivo nas duas partições.

Isso mede se o desajuste realmente separa sinais melhores dos demais; não
melhora o green imediatamente. A camada continua declarando
`aplicacao_sinais=false`, `altera_calibracao=false`,
`altera_prioridade=false`, `telegram=false` e
`promocao_automatica=false`. O watchdog recalcula contagens, partições,
liquidação, cronologia e decisão; inconsistência bloqueia a inferência.

Os testes direcionados passaram em 522/522 casos e a regressão integral em
2.639/2.639. A coorte foi pré-registrada no SQLite às 16:37:56, antes da
retomada. Monitor, watchdog e pré-live voltaram ativos; o primeiro ciclo V77
terminou às 16:44:02 com 32 partidas, seis tarefas processadas, API saudável,
zero falhas e nenhuma pausa. A avaliação V15 e a auditoria independente do
watchdog classificaram a nova referência como saudável, ainda com zero
fotografias. Até surgir um alerta Bet365 elegível de forma natural, a coorte
deve permanecer vazia; nenhum dado será fabricado para acelerar a conclusão.

## Custódia completa da referência posterior ao envio V78 — 11/09/2026

A V78 endurece a coorte V77 antes de sua primeira amostra real. Como a V77
ainda tinha zero fotografias, a nova versão pôde começar limpa sem descartar
evidência válida. A fotografia só entra quando o SQLite comprova a cadeia
completa `origem -> leitura técnica -> sinal materializado -> entrega`, com os
mesmos identificadores gravados no alerta realmente enviado.

Além de partida, mercado e linha, a V78 exige o mesmo placar no snapshot do
sinal, na materialização rápida, na auditoria e na identidade do evento da
fonte independente. Também exige linha exata, odd fresca, horário de publicação
da bookmaker, horário de recebimento da resposta, idade coerente da cotação e
resposta recebida depois da entrega. Cotações com origem, placar, relógio ou
frescor não comprovados ficam fora da análise em vez de contaminarem o edge.

A avaliação passou para V16, a auditoria para V6 e a coorte imutável para V2.
Ela foi pré-registrada no SQLite às 16:57:22 com zero auditorias e zero
fotografias. Foram aprovados 708/708 testes direcionados e 2.640/2.640 na
regressão integral, incluindo prova de aceitação da cadeia válida e rejeição de
linhagem adulterada. HT, FT, pré-live, filtros, calibração, prioridade e
Telegram permanecem inalterados; a camada continua com todos os efeitos
operacionais bloqueados.

Monitor, watchdog e pré-live foram retomados às 16:59:27. O primeiro ciclo V78
terminou às 17:02:46 com 12 partidas, quatro tarefas, zero falhas e nenhuma
pausa. Às 17:04:08, o watchdog confirmou a avaliação V16, a coorte V2 e sua
auditoria saudáveis, sem problemas e sem efeitos operacionais.

## Referência individual sem margem nas análises V79 — 11/09/2026

A auditoria do modelo individual foi repetida antes de qualquer mudança de
sinal. O modelo contextual não superou a melhor referência disponível: no
walk-forward de HT, seu Brier agregado ficou 0,001855 pior que o mercado sem
margem; em FT, nenhuma regularização testada alcançou a melhora mínima de
0,002 pré-registrada. Portanto, nenhum modelo foi promovido e nenhum filtro
HT/FT foi alterado.

As mensagens experimentais passam a aproveitar essa evidência de maneira
honesta. Quando a própria fotografia da entrada contém um par Over/Under
completo e sincronizado, ou as três opções Casa/Visitante/Sem Gol de Próximo
Gol, o resumo mostra a probabilidade implícita normalizada sem a margem da
casa e a margem observada. O texto a identifica como referência de preço do
instante, não como previsão ou garantia. Se faltar sincronia, origem, lado
oposto ou plausibilidade da margem, o bloco é omitido.

A mudança não decide, autoriza, bloqueia nem prioriza sinais e não modifica
calibração, resultado ou Telegram oficial. Foram aprovados 126/126 testes
direcionados e 2.643/2.643 na regressão integral.

Após a implantação, a primeira tentativa de retomada ficou sem acesso ao
navegador e foi encerrada de forma segura. A retomada com a permissão
operacional correta abriu o PackBall normalmente. Monitor, watchdog e pré-live
ficaram ativos; o ciclo encerrado às 17:23:39 processou seis partidas e cinco
tarefas, com zero falhas, nenhuma pausa preventiva e trabalhador rápido de
odds ativo.

## Tentativa Telegram com estado único V80 — 11/09/2026

A auditoria encontrou uma tentativa antiga de análise que aparecia duas vezes:
uma linha permanecia em `enviando` e outra era criada como `incerto` após um
timeout. Era uma única tentativa lógica e não dois envios. Isso não duplicou
um sinal confirmado, mas distorcia o total de pendências e tornava a
reconciliação mais confusa.

O fluxo principal, o canal de teste e o aviso de probabilidade insuficiente
agora preservam o token da reserva e transformam a própria linha reservada em
`entregue` ou `incerto`. A confirmação positiva continua exigindo o
`message_id` retornado pelo Telegram. Timeout permanece incerto e sem retry
automático; o sistema não inventa o desfecho de uma chamada cuja resposta não
foi recebida.

Para o legado, a listagem e o watchdog contam apenas a pendência mais recente
de cada par sinal/canal, sem apagar registros e sem marcá-los manualmente. A
anomalia de 03/09 passou de duas contagens para uma pendência real, ainda
aguardando conferência humana. Uma linha antiga substituída não pode mais ser
reconciliada isoladamente.

Foram aprovados 439/439 testes direcionados e a regressão integral de
2.644/2.644, cobrindo sucesso, timeout, aviso insuficiente, simulação,
recuperação, concorrência e deduplicação histórica. Mercados, filtros,
calibração, prioridade e critérios HT/FT não foram alterados.

Monitor, watchdog e pré-live foram retomados às 17:35. O trabalhador rápido
voltou ativo e sem navegar no PackBall. O primeiro ciclo V80 terminou às
17:39:58 com sete partidas, seis tarefas processadas, zero falhas de API e
nenhuma pausa preventiva. A auditoria registrou zero incertezas oficiais e uma
única incerteza histórica no canal de análise, que não interrompe novas
análises e continua aguardando conferência humana.

## Liquidação neutra e ROI por exposição V81 — 11/09/2026

A calibração binária não transforma mais um `void` íntegro em liquidação
inválida. A devolução continua registrada em sua posição cronológica, exige
odd válida, retorno exatamente zero e relógios coerentes, mas não recebe rótulo
artificial de green ou red. O alvo oficial passa a ser as primeiras 100
liquidações binárias encontradas nas primeiras 300 exposições ordenadas. O
preenchimento pode saltar somente devoluções; resultado ausente, `sem_dado` ou
inconsistência continuam bloqueando o modelo.

Diversidade, partição temporal e frescor usam a mesma coorte. A política de
calibração foi elevada para V10, invalidando de forma segura qualquer modelo
antigo que não declare essa linhagem. Nenhuma regra é promovida automaticamente.

O relatório histórico agora separa amostra binária de exposições liquidadas.
A taxa de acerto usa green/red; ROI e yield usam todas as apostas encerradas,
incluindo `void` com retorno zero. Também se escolhe a primeira exposição de
cada partida antes de anexar a liquidação, evitando que um resultado posterior
substitua retrospectivamente uma devolução ou dado ausente.

Na regra ativa de escanteios asiáticos, a leitura auditada passou a mostrar 39
decisões binárias, três devoluções e 42 exposições liquidadas. O acerto permanece
87,18%, mas o ROI correto é 56,94%, e não 61,3%. A liquidação `sem_dado` de
América x Austin foi mantida: a evidência aponta prorrogação e não separa com
segurança os cantos dos 90 minutos.

Dois challengers simples de recalibração individual também foram recusados no
holdout temporal: FT ficou 0,002432 e HT 0,000653 piores em Brier que o mercado
sem margem. Foram aprovados 480/480 testes direcionados e 2.649/2.649 na
regressão integral.

Monitor, watchdog e pré-live foram retomados às 17:57:37. O primeiro ciclo V81
terminou às 18:01:42 com quatro partidas, duas tarefas processadas, zero falhas
de API, nenhuma pausa preventiva e PackBall consistente. O trabalhador rápido
de odds voltou ativo em cadência de 15 segundos. Às 18:03:35, o watchdog já
reconhecia o ciclo concluído, os três processos responsivos, a política de
calibração V10 e a coorte asiática com 39 decisões binárias, três `voids`
neutros e somente um `sem_dado` bloqueante. A etapa de notificações encerrou
sem erro e não houve alteração nos critérios ou envios HT/FT.

## Ponte causal pré-live/API V82 — 11/09/2026

Uma auditoria das decisões FT entre 5 e 25 minutos encontrou 50 bloqueios por
contexto pré-jogo indisponível em 167 decisões. Em 48 deles, o motivo era a
partida não aparecer ou não casar na lista global ao vivo da API. Isso eliminava
oportunidades antes mesmo de os filtros esportivos serem avaliados.

O monitor agora pode usar o fixture ID exato que já foi identificado pelo
pré-live para pedir o detalhe da partida omitida. A ponte aceita apenas contexto
de qualidade pelo menos 80, com modelo presente e criado antes do horário de
início. A resposta detalhada ainda precisa confirmar que o jogo está ao vivo e
passar novamente por nomes, placar, minuto e categoria. Agendado, encerrado,
nome incompatível ou relógio incoerente continuam rejeitados.

A consulta usa a mesma cota e o mesmo limite de capacidade do enriquecimento
normal. O contexto pré-live não aprova entrada, não altera probabilidade, não
promove prioridade e não contorna odds, pressão, finalizações ou qualquer gate
HT/FT. Seu efeito é somente permitir que uma partida real omitida chegue ao
motor normal para ser julgada com todos os filtros.

No banco atual foram encontrados 12 contextos causais do dia; uma reconstrução
somente de leitura associou três partidas atuais, inclusive uma ainda não
publicada. Foram aprovados 191/191 testes direcionados e 2.653/2.653 na regressão
integral, incluindo recuperação por ID e rejeição de fixture ainda agendado.

Na primeira tentativa de retomada, o monitor ficou fail-closed porque o
navegador não recebeu permissão do ambiente. Os componentes foram encerrados de
forma segura e reiniciados no contexto operacional correto. O primeiro ciclo
V82 terminou às 18:32:40: oito partidas encontradas, seis tarefas processadas,
duas adiadas pelo orçamento normal do ciclo, zero falhas de API e nenhuma pausa
preventiva. Não havia fixture causal omitido elegível naquele instante, portanto
a ponte ficou disponível e registrou zero recuperações, sem forçar consulta.
Monitor, watchdog, pré-live e trabalhador rápido permaneceram ativos e
responsivos; o watchdog terminou saudável e sem problemas.

## Separação honesta das exposições por fonte V83 — 11/09/2026

O relatório de valor das fontes não mistura mais resultados que pertencem a
experimentos diferentes. Cada entrada é separada por entrega oficial ou teste,
versão da regra, estratégia e status. Mensagens auxiliares de resultado,
cancelamento, correção ou espera de odd também deixam de ser contadas como uma
nova aposta.

A revisão dos dados mostrou por que essa separação é importante. O agregado HT
da BetsAPI aparecia com 60 resultados, 45% de acerto e ROI de -20,61%, mas todas
essas exposições eram simulações enviadas ao canal de teste; não havia entrega
oficial. O prejuízo se concentrava sobretudo em versões antigas V3 e V4. O ramo
antecipado atual tinha sete greens em oito exposições atribuídas à fonte, uma
amostra pequena demais para promover ou condenar a fonte.

Resultados de candidatos rejeitados agora são explicitamente tratados como
contrafactuais, e mesmo um estrato descritivo grande não autoriza conclusão
causal sem referência pareada. Isso impede desligar uma fonte ou alterar filtros
por causa de uma média contaminada. Os critérios esportivos, odds, prioridade,
calibração e sinais HT/FT não foram alterados nesta versão.

Foram aprovados 12/12 testes direcionados e 2.658/2.658 na regressão integral.

Monitor, watchdog e pré-live foram retomados às 18:44:44. O primeiro ciclo V83
terminou às 18:48:56 com dez partidas, sete tarefas processadas e três adiadas
normalmente para o ciclo seguinte. Houve zero falhas de API e nenhuma pausa
preventiva. O watchdog ficou saudável, sem motivo de alerta, e o trabalhador
rápido de odds voltou ativo, sem falhas e sem erro.

## Contribuição de preço pareada ao sinal V84 — 11/09/2026

O relatório de fontes agora mede separadamente a contribuição do preço. Uma
comparação só pertence a uma entrada quando sinal, fotografia, mercado,
período, linha, lado, fonte, bookmaker e odd coincidem. Ligar duas cotações
apenas porque vieram da mesma partida é proibido: uma comparação de escanteios,
por exemplo, não pode explicar um sinal de gols.

Cada sinal conta no máximo uma vez. Havendo mais de uma referência, o relatório
prioriza fonte e bookmaker independentes e depois o menor intervalo temporal.
Mesma bookmaker e casa não identificada permanecem visíveis para diagnóstico,
mas não comprovam vantagem. Nos pares independentes, o relatório calcula a
diferença da odd e quanto ela teria alterado o retorno mantendo exatamente o
mesmo resultado contratual.

O gate exige pelo menos 30 partidas homogêneas na mesma regra, estratégia, modo
e status, além de limite inferior positivo no intervalo de 95%. Mesmo quando
cumprido, o estado é apenas `apto_revisao_preco`; sinais, calibração, Telegram e
promoção automática continuam inalterados.

Na base real dos últimos 30 dias foram encontrados quatro sinais entregues com
par exato de gols FT. Três tinham bookmaker parcial e um comparava a mesma
bookmaker; não houve qualquer referência independente. A conclusão correta é
continuar coletando, sem transformar diferenças antigas ou incompletas em
filtro. Foram aprovados 17/17 testes direcionados e 2.663/2.663 na regressão
integral.

Como o relatório não é carregado pelo motor em execução, não foi necessário
interromper a produção. Às 19:00:46, monitor, watchdog e pré-live permaneciam
ativos, o watchdog estava saudável e sem falhas, e o trabalhador rápido de odds
seguia ativo sem erro. O ciclo concluído às 19:00:37 teve zero falhas de API.

## Melhor preço exato prospectivo em sombra V85 — 11/09/2026

O monitor agora registra, em tempo real, se havia outra cotação melhor para o
mesmo contrato quando um candidato foi formado. A comparação exige igualdade de
mercado, período, linha e seleção. Também exige fonte e bookmaker independentes,
cotação congelada e idade máxima de 360 segundos. Ofertas incompletas, linha
diferente, mesma fonte, mesma casa ou cotação velha são recusadas.

A observação fica apenas em `features.melhor_preco_sombra`. Ela não muda a odd
do candidato, a probabilidade, os bloqueios, o status, os critérios HT/FT ou a
mensagem do Telegram. Melhor preço pode elevar o retorno de um green e o valor
esperado, mas não aumenta por si só a chance de o evento esportivo acontecer.

O relatório prospectivo usa apenas a primeira fotografia de cada partida dentro
de um estrato homogêneo. São necessárias pelo menos 30 partidas comparáveis e
um limite inferior positivo no intervalo de 95% para liberar somente uma revisão
humana do seletor. Não existe promoção automática.

Foram aprovados 2.675/2.675 testes. Após parada e retomada seguras, o primeiro
ciclo V85 terminou às 19:18:14 com 11 partidas, oito tarefas processadas, três
adiadas normalmente, lista consistente, zero falhas de rede e nenhuma pausa
preventiva. O banco recebeu 45 observações reais; todas mantiveram
`aplicacao_sinais=false`. Ainda não houve um par independente exato, portanto a
decisão operacional correta continua sendo coletar sem alterar os sinais.

## Ponte da referência separada ao melhor preço V86 — 11/09/2026

A auditoria do primeiro ciclo V85 revelou um desacoplamento correto, porém
incompleto: a cotação independente era persistida em
`odds_referencia_sombra`, enquanto o comparador recebia apenas a estrutura de
odds operacionais. A referência existia para análise histórica, mas não podia
formar a fotografia prospectiva do mesmo instante.

O serviço agora entrega as duas estruturas separadamente ao medidor. A
referência nunca é mesclada às odds operacionais e continua sem autoridade para
escolher preço, aprovar candidato, alterar probabilidade, bloquear sinal ou
enviar Telegram. O registro informa se a referência foi consultada, quantas
ofertas exatas vieram de cada camada e qual camada forneceu a eventual melhor
alternativa.

O medidor passou para `melhor-preco-exato-sombra-v2-referencia-separada` e o
relatório para `coorte-melhor-preco-exato-sombra-v2`. O relatório ignora
fotografias da versão anterior, evitando misturar períodos com coberturas de
coleta diferentes. Continuam obrigatórios mesmo contrato, período, linha e
seleção, oferta completa, fonte e bookmaker distintos, idade máxima de 360
segundos e proveniência íntegra.

Foram aprovados 218 testes direcionados e 2.677 testes integrais. Após parada e
retomada seguras, o primeiro ciclo V86 terminou às 19:40:49 com dez partidas,
oito tarefas processadas, duas adiadas normalmente, lista consistente, zero
falhas de rede e nenhuma pausa preventiva. Watchdog e trabalhador rápido ficaram
saudáveis, sem falhas e com integridade da referência sombra confirmada.

O SQLite recebeu 41 observações V86 em oito partidas, todas com aplicação em
sinais e Telegram falsa. Nenhum jogo desse primeiro ciclo produziu uma nova
referência: houve competição não coberta, evento não pareado ou cota diária já
utilizada. O relatório permanece honestamente em `sem_evidencia_prospectiva`;
a próxima prova esperada é o primeiro evento novo coberto pelas duas fontes.

## Supervisão da ponte de melhor preço V87 — 12/09/2026

A ponte de referência separada agora possui um supervisor próprio, somente de
leitura, que examina no SQLite a coorte atual
`melhor-preco-exato-sombra-v3-supervisionada`. Fotografias das versões
anteriores ficam isoladas e não podem contaminar o diagnóstico atual.

O supervisor confere se aplicação em sinais, calibração, Telegram e promoção
automática continuam falsas. Também valida contagens de ofertas, fonte e
bookmaker distintos, odds e diferença válidas, relação de preço, camada da
oferta e correspondência entre a referência persistida e a referência recebida
pelo comparador. Falta de cobertura ou de par exato é estado normal de coleta;
uma inconsistência estrutural gera atenção e somente vazamento operacional
declarado torna a saúde global crítica.

Foram aprovados 428 testes direcionados e 2.684 testes integrais. Após parada e
retomada seguras, o primeiro ciclo V87 terminou às 15:41:17 com 147 partidas na
lista, seis tarefas processadas, 22 adiadas pelo orçamento normal, lista
consistente, zero falhas de rede e nenhuma pausa preventiva. O watchdog ficou
saudável e o trabalhador rápido permaneceu ativo, sem erro ou falhas.

A primeira comparação independente exata foi comprovada em produção para
Zagłębie Lubin x Katowice, no mercado de gols FT acima de 1,5: a cotação
selecionada era Bet365/BetsAPI @1,50 e a referência separada era Pinnacle/The
Odds API @1,50. A diferença foi zero, portanto isso comprova o funcionamento da
ponte, mas não uma vantagem de preço. O supervisor registrou 45 observações em
sete partidas, três comparações exatas e zero violações de efeito, estrutura ou
persistência.

O relatório contém três estratos da mesma partida — candidato rejeitado,
simulação e auditoria — e apenas uma partida distinta. Nenhuma alteração no
seletor está autorizada. A próxima decisão exige pelo menos 30 partidas
distintas e homogêneas, além do limite estatístico já definido. Até lá, a V87
melhora a confiança e a rastreabilidade da coleta, não a taxa de green por si só.

## Preço justo independente no instante da decisão V88 — 12/09/2026

A comparação prospectiva agora distingue uma odd nominalmente maior de uma
vantagem executável. Para cada contrato exato, a V88 exige o mercado completo
da referência independente: Over e Under nas linhas binárias ou as três
seleções no Próximo Gol. A margem da bookmaker precisa ser plausível antes de
ser removida.

Com a referência sem vig, o medidor calcula a probabilidade justa independente,
o ponto de equilíbrio da odd selecionada, a diferença em pontos percentuais e o
valor esperado. A referência usada nesse cálculo é escolhida por frescor e por
identidade determinística, nunca pela maior odd. Assim, o relatório não escolhe
retrospectivamente a fonte que melhor confirma uma suposta vantagem.

O cálculo permanece em `features.melhor_preco_sombra.valor_justo_sombra` e não
altera candidato, odd escolhida, bloqueio, prioridade, HT, FT, probabilidade do
motor, Telegram ou promoção. O supervisor recalcula a matemática, confere
fonte e bookmaker distintas, margem, estados e todos os indicadores de efeito.
Qualquer divergência estrutural gera atenção; qualquer efeito operacional
declarado continua crítico.

Foram aprovados 680 testes direcionados e 2.691 testes integrais. Após retomada
segura, o primeiro ciclo V88 terminou às 16:01:47 com 79 partidas, cinco tarefas
processadas, 23 adiadas normalmente pelo orçamento, lista consistente, zero
falhas de rede e nenhuma pausa preventiva.

A primeira avaliação real ocorreu em Atlético Mineiro x Fluminense, Over 0,5
FT. A odd executável da Bet365/BetsAPI era 1,3636 e a referência da
Pinnacle/The Odds API era 1,33. Apesar de a odd executável ser nominalmente
maior, a referência sem margem estimou 70,8972%, abaixo dos 73,3353% exigidos
para empatar naquela odd. O EV foi -3,3246%, classificado corretamente como
`sem_desajuste_favoravel` e sem gerar qualquer sinal.

Às 16:04:19, o watchdog estava saudável, o trabalhador rápido ativo e a coorte
V88 possuía 40 observações em sete partidas, um par independente com preço justo
e zero violações de efeito, estrutura, persistência ou matemática. O relatório
continua em coleta: são necessárias pelo menos 30 partidas distintas no mesmo
estrato e limite inferior positivo do IC95 do EV para liberar apenas revisão
humana, nunca promoção automática.

## Sincronismo causal do preço justo V89 — 12/09/2026

A revisão da V88 encontrou uma brecha metodológica: linha e odds recentes não
provavam sozinhas que as duas casas ainda refletiam o mesmo estado do jogo. Uma
cotação anterior a um gol poderia ser comparada com outra posterior ao gol e
produzir um falso desajuste.

A V89 exige agora identidade confirmada do evento nas duas ofertas, com os
mesmos mandante, visitante e placar. Também exige intervalo máximo de 60
segundos entre as fontes. A oferta operacional precisa coincidir em fonte,
bookmaker, odd e instante com a cotação congelada do candidato. Se qualquer
prova faltar, a diferença nominal continua disponível para diagnóstico, mas o
bloco de preço justo fica em `sem_referencia_sem_vig_sincronizada`.

Medidor, cálculo sem vig e relatório foram versionados. As três avaliações V88
permanecem preservadas como histórico, porém não entram na nova coorte. Foram
aprovados 683 testes direcionados e 2.694 testes integrais, incluindo placar
divergente, intervalo acima de 60 segundos e oferta operacional incompatível.

Após retomada segura, o primeiro ciclo V89 terminou às 16:23:31 com 64 partidas,
seis tarefas processadas, 22 adiadas pelo orçamento normal, lista consistente,
zero falhas de rede e nenhuma pausa preventiva. Watchdog e trabalhador rápido
ficaram saudáveis e ativos.

A primeira prova real ocorreu em Grêmio x Vasco, Over 1,5 FT. Bet365/BetsAPI
oferecia 1,4444; a Pinnacle/The Odds API indicava probabilidade sem vig de
73,1809%, contra ponto de equilíbrio de 69,2329%, resultando em EV de +5,7025%.
As duas fontes mostravam placar 1–0 e estavam separadas por 22,377 segundos.

Mesmo com edge positivo, o candidato foi rejeitado porque havia zero
finalizações nos cinco minutos recentes e o histórico de cinco minutos era
insuficiente. A cópia de auditoria permaneceu silenciosa. Isso confirma o
isolamento correto: preço favorável não contorna evidência esportiva fraca.

O supervisor registrou 37 observações em seis partidas e duas avaliações
sincronizadas referentes a uma única partida, com zero violações. O relatório
permanece em coleta. A próxima revisão exige pelo menos 30 partidas distintas,
resultados posteriores e evidência de melhora real de ROI no mesmo estrato.

## Resultado prospectivo do preço justo V90 — 12/09/2026

A V90 transforma o diagnóstico de preço justo em uma avaliação de resultado
sem alterar as entradas. Cada sinal novo grava antecipadamente a política
`validacao-resultado-valor-justo-sincronizado-v1`, incluindo seu fingerprint,
os grupos, o tamanho da coorte e os critérios de revisão. A mudança do medidor
para `melhor-preco-exato-sombra-v6-resultado-prospectivo` começa uma amostra
nova; registros V89 permanecem preservados, mas não podem ser reaproveitados.

A unidade independente é o primeiro sinal com preço justo sincronizado de cada
partida e mercado. Apenas `aprovado`, `simulacao` e `auditoria` são liquidáveis;
um candidato `rejeitado` nunca é usado para alegar green, red ou vantagem. A
escolha acontece antes de consultar o resultado e permanece fixa mesmo se uma
reavaliação posterior da mesma partida já tiver sido liquidada.

Cada mercado congela os primeiros 100 candidatos: 70 de desenvolvimento e 30
de holdout. Uma revisão exige no mínimo 80 resultados, sendo 55/25 nas duas
partições, ao menos 30 casos com edge e 30 controles, além de oito casos de
cada grupo no holdout. O edge precisa ter ROI positivo, superar o controle no
desenvolvimento e no holdout e manter o limite inferior de 95% da diferença de
ROI acima de zero. Mesmo assim, o estado liberado é somente revisão humana;
aplicação em sinais, calibração, Telegram e promoção continuam falsas.

O validador também confere cronologia, resultado e retorno. Liquidação anterior
ao sinal, resultado desconhecido, retorno ausente ou `void` diferente de zero
gera uma violação visível no watchdog. O supervisor passou ainda a exigir que
o schema e a fonte da identidade do evento correspondam às duas cotações.

Foram aprovados 116 testes direcionados e 2.698 testes integrais. Após retomada
segura, monitor, watchdog e pré-live carregaram os hashes atuais. O primeiro
ciclo V90 terminou às 16:46:56 com 48 partidas, seis tarefas processadas, 22
adiadas pelo orçamento normal, lista consistente, zero falhas de API e nenhuma
pausa preventiva. O SQLite recebeu 31 observações V6 em seis partidas, todas
com política íntegra e zero violações. Nenhuma possuía ainda preço justo
sincronizado elegível; a coorte de resultado permanece honestamente em
`aguardando_candidatos`.

## Cota independente orientada a candidatos V91 — 12/09/2026

A referência independente deixou de ser consultada antes da decisão esportiva.
Agora o bot conclui as políticas do candidato e somente considera gastar cota
quando o mercado sobreviveu, o status é liquidável e a cotação executável da
Bet365/BetsAPI está congelada com proveniência válida. Mercados já representados
por um candidato V6 sincronizado na mesma partida são ignorados.

Para jogos cujas duas consultas diárias foram consumidas pela metodologia
anterior, existe uma única recuperação de coorte. Ela só é pedida depois dessa
seleção final e continua submetida ao limite diário, reserva mensal, cooldown,
circuito de falhas, pareamento prévio do evento e orçamento do ciclo. Depois da
terceira reserva, qualquer nova tentativa do mesmo jogo no dia é bloqueada.

A auditoria regular passou para
`amostragem-referencia-sombra-auditoria-v5` e registra explicitamente a
solicitação, a aplicação e o limite efetivo da recuperação. O mecanismo não
altera sinais, HT, FT, probabilidade, calibração, prioridade ou Telegram.

Foram aprovados 317 testes direcionados e 2.701 testes integrais. A validação
em produção deve aguardar uma oportunidade real com candidato liquidável e
cotação Bet365 congelada; não encontrar essa combinação em um ciclo é um estado
normal, não uma falha operacional.

Monitor, watchdog e pré-live foram retomados com os hashes atuais. O primeiro
ciclo V91 terminou às 17:07:03 com 31 partidas, seis tarefas processadas e 22
adiadas pelo orçamento normal. A lista ficou consistente, não houve falha de
rede nem pausa preventiva. Nenhum dos seis jogos possuía candidato liquidável
com cotação Bet365 congelada; por isso o novo filtro registrou seis exclusões,
fez zero reservas e não desperdiçou consulta independente.

O supervisor permaneceu saudável sobre 111 observações em 14 partidas, com uma
comparação independente exata e zero violações de efeito, estrutura,
persistência, preço justo ou política de resultado. A prova real da auditoria
V5 e da recuperação da terceira consulta acontecerá somente quando surgir a
combinação elegível; isso não bloqueia o funcionamento do bot.

## Cobertura causal das auditorias silenciosas V92 — 12/09/2026

A V91 selecionava a referência depois das políticas esportivas, porém antes de
as cópias silenciosas com status `auditoria` serem criadas. Assim, um descarte
promissor podia estar corretamente destinado à medição de resultado e ainda
parecer apenas `rejeitado` no instante em que a cota independente era decidida.

A V92 usa o mesmo classificador puro tanto para prever quanto para materializar
essa auditoria. Somente o descarte que satisfaz integralmente a política de
auditoria, possui cotação Bet365/BetsAPI congelada e ainda não formou coorte no
mesmo jogo pode pedir a referência. Rejeitados comuns e bloqueios estruturais
continuam excluídos. A consulta permanece em sombra: o status original não é
alterado, o Telegram não recebe o caso e nenhum critério de HT ou FT é afrouxado.

O banco forneceu uma prova concreta da lacuna: logo após o primeiro ciclo V91,
um candidato de gol FT @1,3636, pontuação 65 e cotação Bet365 congelada tornou-se
auditoria silenciosa sem comparação independente. Esse é precisamente o caso
que a V92 passa a cobrir. Foram aprovados 318 testes direcionados e 2.702 testes
integrais antes da retomada operacional.

Monitor, watchdog e pré-live foram retomados com hashes atuais. O primeiro
ciclo V92 terminou às 17:24:42 com 31 partidas, dez tarefas processadas e 18
adiadas normalmente, lista consistente, zero falhas de rede e nenhuma pausa
preventiva. A nova rota reconheceu antecipadamente três auditorias elegíveis.
Duas foram barradas porque a competição não era coberta e uma porque o evento
não foi pareado na fonte independente. Todos os descartes ocorreram antes da
reserva: zero cota desperdiçada e nenhum caso silencioso foi enviado ao
Telegram. A primeira comparação independente exata dessa rota ainda depende
de surgir uma auditoria em competição e evento cobertos.

## Referência multibookmaker API-Football V93 — 12/09/2026

Quando um candidato V92 não encontra oferta na The Odds API, o monitor pode
agora consultar a resposta global em cache da API-Football e procurar outra
bookmaker. Bet365 é sempre excluída, pois já é a cotação executável recebida
pela BetsAPI. A referência precisa conter Over e Under da mesma linha.

As bookmakers alternativas são ordenadas pelo nome e limitadas a cinco, sem
considerar qual odd favorece o candidato. A comparação só se torna causal se a
fixture foi fortemente associada, o placar da API coincide com o PackBall, os
nomes pertencem à partida interna e as duas cotações respeitam a janela de 60
segundos. Cache antigo pode permanecer como diagnóstico nominal, mas não vira
preço justo sincronizado.

A rota é exclusivamente observacional. Não altera status, odd de entrada,
seleção, HT, FT, calibração, prioridade nem Telegram. Pode ser desativada por
`API_FOOTBALL_REFERENCIA_SOMBRA_ATIVA=0`. Foram aprovados 394 testes
direcionados e 2.704 testes integrais antes da retomada.

Na retomada real, os três processos iniciaram com os hashes esperados. O
primeiro ciclo V93 terminou em 229,328 segundos, com 34 partidas, 10 tarefas
processadas, 18 adiadas, lista consistente, zero falhas de rede e sem pausa
preventiva. A fallback API-Football foi invocada em três candidatos de gols FT
e, como nenhuma bookmaker independente oferecia par Over/Under válido naquele
instante, retornou vazio nos três casos. Nenhum sinal foi bloqueado, criado ou
alterado por essa ausência; a validação recusou fabricar preço justo.

## Supervisão da referência API-Football V94 — 12/09/2026

O arquivo `supervisao_referencia_api_football.py` audita em modo somente leitura
os diagnósticos V93 e as odds de referência realmente persistidas no mesmo
snapshot. Ausência de bookmaker alternativa é informativa e não bloqueia o
bot. A supervisão exige mercados suportados, listas sem duplicidade, Bet365
excluída, contadores coerentes, identidade confirmada de evento e todos os
efeitos operacionais desativados.

Uma referência declarada precisa existir na tabela `odds` como
`referencia_sombra`, com fonte `api_football`, bookmaker alternativa, fixture,
times e placar válidos. Divergência estrutural gera atenção; qualquer declaração
de efeito em sinais, calibração ou Telegram é crítica. O status e o watchdog
expõem tentativas, referências, mercados, partidas, consultas e violações.

Foram aprovados 691 testes integrados e 2.709 testes integrais. No banco real,
a primeira auditoria encontrou 19 snapshots em 13 partidas, quatro tentativas,
nenhuma bookmaker alternativa disponível e zero violações. O estado correto é
`coletando_sem_bookmaker_alternativa`, preservando HT e FT sem alteração.

Após a retomada, os hashes de monitor e watchdog carregados coincidiram com os
arquivos atuais. O primeiro ciclo V94 terminou às 18:06:36 com 30 partidas,
oito tarefas processadas, 20 adiadas pelo orçamento normal, lista consistente,
zero falhas de rede e nenhuma pausa preventiva. O watchdog voltou ao estado
saudável após a janela esperada da manutenção e confirmou o supervisor V94
saudável, com zero violações.

## Transferência do edge por origem V95 — 12/09/2026

A validação de preço justo continua escolhendo o primeiro candidato de cada
partida e mercado, porém agora possui uma prova adicional pré-registrada. Desde
`2026-09-12T18:20:00-04:00`, candidatos `aprovado` ou `simulacao` formam a
coorte acionável e candidatos `auditoria` formam uma coorte silenciosa separada.
O status usado na separação já existia antes do resultado e não é reclassificado
depois do encerramento.

Cada origem preserva a coorte fixa de 100 casos por mercado, dividida em 70 de
desenvolvimento e 30 de holdout, com os mesmos mínimos de liquidação, equilíbrio
entre edge/controle, ROI e intervalo de confiança da V90. O relatório somente
chama a vantagem de transferível se ela for confirmada nas duas origens. Assim,
um bom resultado restrito aos casos descartados não será usado para justificar
mudança nas entradas reais, e o inverso também não será suficiente.

A política e seu SHA-256 ficam disponíveis no relatório. A nova verificação é
somente leitura e não muda sinais, HT, FT, calibração, prioridade, odds ou
Telegram.

Na primeira retomada, o ciclo V95 terminou às 18:29:40 com 25 partidas e nove
análises detalhadas, watchdog saudável e nenhuma pausa preventiva. A coorte foi
registrada como `aguardando_candidatos_pos_ancora`, o estado correto enquanto
nenhum preço justo sincronizado pós-marco se tornou acionável ou auditoria.

Esse ciclo revelou também um falso alerta do supervisor V94: uma associação de
fixture/placar recusada antes da consulta não contém, corretamente, detalhes por
mercado. O supervisor passou para V2 e agora aceita somente esses motivos
terminais com zero consulta, zero retorno e zero bookmaker. Se detalhes faltarem
após qualquer consulta, a falha fechada permanece. O snapshot real voltou a
saudável, com 13 tentativas, três consultas estimadas e zero violações. Foram
aprovados 383 testes direcionados e 2.713 testes integrais antes da retomada
final.

Na retomada final, monitor, watchdog e pré-live carregaram hashes idênticos aos
arquivos testados e permaneceram responsivos. A inicialização transitória foi
recuperada automaticamente e o ciclo concluiu às 18:44:56 com 26 partidas e
nove análises detalhadas, sem pausa preventiva. A auditoria final encontrou 669
observações em 28 partidas, três pares exatos e zero violações de efeito,
estrutura, persistência, valor ou política. O supervisor API-Football V2 ficou
saudável com 15 tentativas, três consultas estimadas e zero violações.

## Capacidade multibookmaker adaptativa V96 — 12/09/2026

A auditoria do payload real mostrou uma limitação que precisava ficar
explícita: no bet 25, a API-Football devolveu 21 fixtures e mercados de gols,
mas nenhuma lista com a identidade das bookmakers. A odd agregada continua útil
para as funções operacionais já existentes, porém não prova independência em
relação à Bet365 e, portanto, não pode virar preço justo externo.

A V96 aprende e persiste essa capacidade separadamente para gols FT, gols HT e
escanteios asiáticos FT. Depois de uma resposta não vazia sem nomes de casas,
somente a tentativa extra de referência é suspensa por seis horas. As consultas
operacionais da API-Football, a confirmação de partidas e os mercados usados
pelo fluxo normal permanecem intactos. Uma nova resposta operacional com nomes
de bookmakers reativa a referência imediatamente; ao fim de seis horas, a rota
também volta a sondar sozinha. Para diagnóstico controlado, a sondagem pode ser
forçada com `API_FOOTBALL_REFERENCIA_FORCAR_SONDAGEM=1`.

O arquivo `api_football_referencia_capacidade_estado.json` registra amostras,
fixtures, identidades encontradas, ausências consecutivas, consultas evitadas e
a próxima sondagem por bet. Essa telemetria segue para cada snapshot. O
supervisor V3 confere os totais contra os detalhes por mercado e mantém falha
fechada para qualquer contradição ou efeito operacional declarado. O status
mostra quantas consultas extras foram evitadas e quais mercados ainda não
oferecem identidade de bookmaker.

Foram aprovados 646 testes integrados e 2.718 testes integrais. Nenhuma regra
HT/FT, entrada, probabilidade, calibração ou mensagem Telegram foi alterada.

Após a retomada, monitor, watchdog e pré-live ficaram ativos com hashes
carregados idênticos aos arquivos aprovados. O primeiro ciclo V96 terminou às
19:08:07 em 221,606 segundos, com 33 partidas e oito análises detalhadas, sem
pausa preventiva. A capacidade real registrou 38 fixtures no bet de gols FT e
32 no asiático de escanteios FT, ambas sem identidade de bookmaker. Às
19:06:10, um candidato de gol FT acionou a fallback e a V96 evitou a primeira
consulta adicional redundante.

O supervisor V3 ficou saudável sobre 97 snapshots em 23 partidas, com uma
consulta evitada, nenhum preço independente fabricado e zero violações de
efeito, estrutura ou persistência. O estado informativo correto passou a ser
`capacidade_bookmaker_indisponivel_observada`; HT, FT e Telegram continuaram
operacionais no ciclo seguinte.

## Validação prospectiva do veto por preço justo negativo V97 — 12/09/2026

A V97 transforma a comparação externa de odds em um experimento prospectivo
de segurança. Desde `2026-09-12T19:30:00-04:00`, o primeiro sinal de cada
partida, mercado e origem é congelado antes do resultado como candidato a veto
quando o valor esperado calculado pela referência independente é menor ou
igual a -5%. Os demais casos com preço justo válido formam o controle. Casos
sem referência sincronizada permanecem inelegíveis e não são reinterpretados.

O limite não foi escolhido a partir dos reds históricos. A política, a âncora
e a definição SHA-256 foram fixadas com o bot parado. Candidatos realmente
acionáveis (`aprovado` e `simulacao`) e auditorias silenciosas (`auditoria`)
formam estratos separados, cada um com coorte fixa de 120 casos por mercado,
80 para desenvolvimento e 40 para holdout. A eventual utilidade do veto só
pode ser declarada se o grupo negativo tiver retorno estatisticamente pior que
o controle, com intervalo de confiança superior abaixo de zero, e o efeito se
repetir em desenvolvimento, holdout e nas duas origens.

Esta camada não bloqueia entradas, não muda probabilidade, HT, FT, prioridade,
calibração ou Telegram e não promove regras automaticamente. Ela mede se reds
estão concentrados em cotações economicamente desfavoráveis sem sacrificar
sinais antes de existir amostra suficiente. Qualquer adoção futura depende de
evidência completa e revisão humana.

Foram aprovados 422 testes direcionados e 2.722 testes integrais. Antes da
retomada, o banco operacional ficou saudável no estado
`aguardando_candidatos_pos_ancora`, com zero candidato pós-marco e zero
violação. Esse é o estado inicial esperado e preserva integralmente o
comportamento atual do bot.

Monitor, watchdog e pré-live foram retomados com hashes carregados idênticos
aos arquivos aprovados. O primeiro ciclo V97 terminou às 19:29:35 em 223,336
segundos, com 45 partidas, oito análises detalhadas, zero falhas de rede e
nenhuma pausa preventiva. A reserva de tempo encerrou a coleta detalhada de
forma controlada, adiando 20 tarefas sem perder a consistência da lista.

Após o ciclo, o supervisor permaneceu saudável sobre 852 observações em 37
partidas, sete comparações independentes exatas e zero violações de efeito,
estrutura ou persistência. A coorte V97 ainda está corretamente em
`aguardando_candidatos_pos_ancora`; nenhuma entrada foi bloqueada ou alterada.
