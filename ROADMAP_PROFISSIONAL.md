# Roadmap profissional do Bot PackBall

## Estado esportivo sem mistura de odds V110 — 13/09/2026

- [x] Usar a coorte prospectiva fixa para localizar a lacuna: duas das cinco
  entradas instrumentadas eram PackBall e não recebiam estado rápido.
- [x] Separar formalmente a observação esportiva da comparação de preço.
- [x] Permitir estado API-Football para entrada PackBall no modo
  `somente_estado`, sem anexar cotação futura de outra fonte ou bookmaker.
- [x] Preservar para BetsAPI/Bet365 o modo `estado_e_preco`, exigindo mesma
  linha, fonte, bookmaker, evento e instante válidos.
- [x] Versionar a coleta V4 e a evidência V3, mantendo V1/V2/V3 legíveis para
  compatibilidade histórica.
- [x] Elevar avaliação/custódia para V26/V15 e auditar a fonte do estado contra
  a fonte imutável do sinal.
- [x] Fazer o watchdog rejeitar telemetria em que `somente_estado` exceda o
  total de consultas sem oferta futura.
- [x] Preservar isolamento operacional: nenhum filtro, sinal, HT, FT,
  Telegram, probabilidade ou promoção automática foi alterado.
- [x] Aprovar 660 testes integrados e 2.766/2.766 na regressão integral.
- [x] Auditar 11.714 observações reais com V26/V15, cadeia saudável e zero
  problema de integridade antes da retomada.
- [x] Retomar monitor, watchdog e pré-live com PIDs reais 29472, 45124 e 48792,
  três travas e hashes do runtime iguais ao código aprovado.
- [x] Confirmar o trabalhador V4 ativo, íntegro, sem falha e sem efeitos sobre
  sinais ou Telegram.
- [x] Concluir o primeiro ciclo V110 às 00:45:06: três partidas, três tarefas
  processadas, três pareamentos BetsAPI, dez mercados, lista consistente e
  zero falha de rede, adiamento ou pausa.
- [x] Confirmar no ciclo seguinte, encerrado às 00:45:30, o watchdog saudável,
  sem falhas consecutivas e reconhecendo a coleta V4 íntegra.

## Desfecho rápido por contagem de escanteios V109 — 13/09/2026

- [x] Confirmar no payload real da API-Football que a consulta detalhada já
  transporta `Corner Kicks` junto de placar e minuto, sem nova requisição.
- [x] Incluir o par de escanteios, respeitando a orientação das equipes, no
  estado rápido coletado dois a dez minutos após o alerta.
- [x] Validar contadores inteiros e não negativos antes de persistir a
  fotografia; dado ausente continua ausente e dado inválido falha fechado.
- [x] Versionar a evidência de estado V2, preservar leitura das evidências V1
  e manter cada registro imutável e protegido por SHA-256 no SQLite.
- [x] Fazer a avaliação de escanteios asiáticos liquidar pelo evento real
  quando a contagem ultrapassa a linha, mesmo que a odd futura tenha sumido.
- [x] Preservar o preço futuro para contratos ainda abertos e manter próximo
  escanteio como `somente_snapshot`, sem inventar uma fonte independente.
- [x] Manter a V109 estritamente observacional: nenhum sinal, filtro, HT, FT,
  Telegram, probabilidade, calibração ou promoção automática foi alterado.
- [x] Aprovar 658 testes integrados e 2.763/2.763 na regressão completa.
- [x] Auditar o SQLite real com avaliação V25/custódia V14 saudável, 11.711
  observações verificadas e zero problema de integridade.
- [x] Retomar os três processos com PIDs reais 47008, 34620 e 42368, três
  travas e hashes atuais; trabalhador rápido V3 saudável e sem efeitos.
- [x] Concluir o primeiro ciclo V109 às 00:22:54: cinco partidas, cinco tarefas
  agendadas, quatro processadas, três pareamentos Bet365, dez mercados
  anexados, lista consistente e zero falha de rede ou pausa preventiva.
- [x] Confirmar às 00:24:39 o watchdog saudável sobre ciclo posterior, zero
  falha consecutiva e cobertura CLV íntegra, sem efeito em sinais/Telegram.

## Cobertura pós-alerta dos mercados de escanteios V108 — 12/09/2026

- [x] Auditar a carteira completa e identificar que a coleta rápida V107
  ainda não fotografava a linha asiática FT de escanteios.
- [x] Incluir `escanteios_ft_asiatico` na fila rápida, exigindo a mesma linha
  Bet365 e o par Over/Under completo, sem substituir contrato ou bookmaker.
- [x] Estender a validação de origem, evento, relógio, curva e margem sem vig
  ao contrato asiático antes de aceitar sua fotografia futura.
- [x] Manter `proximo_escanteio` nos snapshots PackBall, pois a BetsAPI não
  fornece esse mercado; declarar a limitação em vez de fabricar cobertura.
- [x] Versionar a coleta V2 e fazer o watchdog verificar a lista exata dos
  quatro mercados rápidos e do único mercado dependente de snapshot.
- [x] Preservar isolamento total: nenhuma dessas medições gera sinal, envia
  Telegram, promove filtro ou altera HT, FT, gols e escanteios.
- [x] Aprovar 681 testes focados, a regressão integral de 2.763/2.763 testes e
  a auditoria real V24/V13 dos cinco mercados, sem problema de integridade.
- [x] Retomar monitor, watchdog e pré-live com três PIDs reais, três travas e
  hashes de runtime iguais ao código testado; trabalhador V2 ativo, cobertura
  declarada completa e zero falha inicial.
- [x] Concluir o primeiro ciclo V108 às 23:55:11: 12 partidas, 12 tarefas
  agendadas, 6 processadas, 6 pareamentos Bet365, 16 mercados anexados e zero
  falha de rede.
- [x] Confirmar na supervisão das 23:56:59 um ciclo V108 novo reconhecido,
  watchdog e trabalhador saudáveis, zero falha consecutiva, nenhuma pausa,
  cobertura dos mercados íntegra e nenhum efeito em sinais ou Telegram.

## Movimento da odd após o alerta V107 — 12/09/2026

- [x] Criar uma coleta rápida e independente para fotografar a mesma linha
  Bet365 entre dois e dez minutos depois de cada alerta realmente entregue.
- [x] Vincular cada fotografia ao sinal, partida, mercado e linha exatos,
  validando o estado da partida pela API-Football antes da gravação.
- [x] Registrar também a ausência real da cotação e o encerramento da partida,
  impedindo que reds terminais desapareçam da avaliação e elevem a taxa por
  viés de sobrevivência.
- [x] Manter indisponibilidades técnicas como tentativas pendentes; uma falha
  de fonte não é convertida em falsa ausência de mercado.
- [x] Tornar o estado pós-alerta imutável no SQLite e auditar referências,
  janela temporal, cotação vinculada, duplicidades e isolamento operacional.
- [x] Isolar completamente essa observação: ela não gera alerta, não envia
  Telegram e não altera filtros, aprovação, calibração, HT, FT, próximo gol,
  escanteios ou pré-live.
- [x] Fazer o watchdog expor falhas dessa medição sem derrubar o fluxo de
  sinais; somente uma violação de isolamento torna o sistema não saudável.
- [x] Aprovar a regressão integral de 2.758/2.758 testes e a auditoria real da
  avaliação V23 sem problemas de integridade.
- [x] Retomar monitor, watchdog e pré-live com três PIDs reais, três travas e
  hashes de runtime conferidos; coleta rápida ativa, sem falhas e ainda sem
  alerta elegível na janela logo após a retomada.
- [x] Concluir o primeiro ciclo V107 às 23:32:54: 16 partidas, 16 tarefas
  agendadas, 7 processadas, 6 pareamentos Bet365, 14 mercados anexados e zero
  falha de rede; supervisão seguinte saudável, sem pausa e com coleta CLV
  isolada saudável.

## Proveniência reproduzível da vantagem histórica V106 — 12/09/2026

- [x] Identificar que hash e imutabilidade protegiam a fotografia depois da
  gravação, mas não provavam que seu conteúdo correspondia às linhas originais
  de sinais, partidas, entregas, resultados e odds no SQLite.
- [x] Recarregar o sinal de origem e conferir identidade da coorte, relógio
  causal, janela fixa e custódia executável BetsAPI/Bet365 antes da leitura.
- [x] Recalcular integralmente a fotografia com as evidências do banco e exigir
  o mesmo conteúdo canônico antes de mostrar taxa, ROI ou vantagem robusta.
- [x] Detectar inclusive alteração da base com um hash interno novamente válido,
  recusando a apresentação como `base_historica_divergente`.
- [x] Integrar a reprodução ao carregamento individual e à auditoria contínua
  do watchdog, expondo quantas fotografias tiveram origem reproduzida.
- [x] Manter falha fechada limitada à apresentação: filtros, geração, aprovação,
  calibração, HT, FT, escanteios, pré-live e Telegram permanecem inalterados.
- [x] Aprovar 53 testes focados, 464 integrados e a regressão completa de
  2.750/2.750 testes.
- [x] Retomar monitor, watchdog e pré-live com hashes carregados iguais aos
  atuais, três PIDs reais ativos e três travas corretas.
- [x] Concluir o primeiro ciclo V106 às 22:53:54: 28 partidas, 28 tarefas
  agendadas, 8 processadas, 6 pareamentos Bet365, 17 mercados anexados, API
  saudável, zero falhas de rede e circuito BetsAPI fechado.
- [x] Confirmar na supervisão seguinte o ciclo reconhecido, watchdog saudável,
  zero falhas consecutivas, nenhuma pausa, auditor V4 saudável e custódia em
  nove de nove gatilhos; estado `sem_registros` é correto antes do próximo
  alerta elegível V4.

## Robustez temporal e risco do histórico executável V105 — 12/09/2026

- [x] Identificar que um ROI positivo ainda podia parecer mais confiável do
  que era quando muitas entradas se concentravam no mesmo dia.
- [x] Versionar uma fotografia V4 nova e causal, preservando V2 e V3, com
  partida, liga e horário de envio de cada unidade executável Bet365.
- [x] Calcular intervalo de confiança de 95% do ROI com variância robusta CR1
  agrupada por dia, além do intervalo t por entrada já existente.
- [x] Medir dias e ligas distintos, concentração na maior liga, ROI da metade
  antiga e recente, maior sequência de reds e drawdown máximo em unidades.
- [x] Só rotular vantagem histórica robusta com no mínimo 30 entradas em 10
  dias, limites inferiores positivos nos dois intervalos e ROI positivo nas
  duas metades temporais.
- [x] Manter amostras pequenas, concentradas ou temporalmente instáveis como
  inconclusivas, sem convertê-las em probabilidade individual ou entrada.
- [x] Proteger a fotografia V4 contra atualização, exclusão e substituição e
  manter V2/V3 protegidas, totalizando nove de nove gatilhos SQLite íntegros.
- [x] Preservar filtros, geração, aprovação, calibração e frequência dos
  sinais HT, FT, próximo gol, escanteios e pré-live.
- [x] Aprovar 52 testes focados e a regressão integral de 2.749/2.749 testes.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais, PIDs reais e as
  três travas de instância corretas.
- [x] Concluir o primeiro ciclo V105 às 22:35:22: 30 partidas, 28 tarefas
  agendadas, 8 processadas, 7 pareamentos Bet365, 21 mercados anexados, API
  saudável, zero falhas de rede e circuitos das fontes fechados.
- [x] Confirmar na supervisão seguinte o ciclo reconhecido, watchdog saudável,
  zero falhas consecutivas, nenhuma pausa e custódia V2/V3/V4 íntegra.

## Rentabilidade histórica executável V104 — 12/09/2026

- [x] Corrigir a interpretação que comparava taxa histórica de acertos com a
  odd atual, pois muitos greens não garantem lucro quando o preço é baixo.
- [x] Criar a fotografia V3 somente com sinais realmente enviados e odds
  executáveis da BetsAPI/Bet365, conferindo matematicamente cada retorno:
  `odd - 1` no green e `-1` no red para uma unidade apostada.
- [x] Persistir a evidência por entrada, unidades acumuladas, ROI histórico,
  odd média realmente executada e intervalo de confiança de 95% de Student.
- [x] Excluir e contabilizar liquidações sem prova financeira coerente, sem
  estimar lucro a partir da odd atual ou de preços de outra fonte.
- [x] Tornar a mensagem conservadora: amostras menores que 30 permanecem
  inconclusivas; vantagem histórica só pode ser indicada quando o limite
  inferior do intervalo de ROI fica acima de zero.
- [x] Manter a odd atual apenas como referência de preço de equilíbrio, sem
  apresentá-la como prova de vantagem individual ou promessa de acerto.
- [x] Preservar a custódia V2 e adicionar três gatilhos para V3, totalizando
  seis de seis proteções SQLite contra atualização, exclusão e substituição.
- [x] Preservar integralmente os filtros, aprovação, calibração e frequência
  dos sinais HT, FT, próximo gol, escanteios e pré-live.
- [x] Aprovar 589 testes direcionados e integrados e a regressão completa de
  2.746/2.746 testes.
- [x] Retomar monitor, watchdog e pré-live com hashes carregados iguais aos
  atuais e as três travas de instância corretas.
- [x] Concluir o primeiro ciclo V104 às 22:13:03: 34 partidas, 28 tarefas
  agendadas, 8 processadas, 7 pareamentos Bet365 e 20 mercados anexados, com
  circuitos das fontes fechados e sem pausa preventiva.
- [x] Confirmar na supervisão seguinte o watchdog saudável, zero falhas
  consecutivas e a custódia V2/V3 íntegra em seis de seis gatilhos.

## Custódia nativa da taxa histórica V103 — 12/09/2026

- [x] Identificar que o SHA-256 V102 detectava alteração comum, mas não
  impedia alguém de substituir simultaneamente o conteúdo e o próprio hash.
- [x] Criar custódia SQLite específica para cada chave V2, com gravação única
  e bloqueios nativos de atualização, remoção e substituição posterior.
- [x] Auditar não apenas a presença, mas a semântica dos três gatilhos; falhar
  fechado na leitura e na nova gravação se qualquer proteção desaparecer ou
  for redefinida.
- [x] Incluir os gatilhos no contrato obrigatório do esquema e o novo módulo
  nas assinaturas de runtime do monitor e do watchdog.
- [x] Preservar alertas e regras esportivas: falha de apresentação não muda
  HT, FT, aprovação, calibração nem entrega do sinal.
- [x] Aprovar 632 testes direcionados e integrados e a regressão completa de
  2.743/2.743 testes.
- [x] Migrar a base real com três de três gatilhos íntegros, hashes carregados
  iguais aos atuais, três travas corretas, 33 tabelas compatíveis, nenhum
  elemento obrigatório ausente e zero violação de chave estrangeira.
- [x] Retomar monitor, watchdog e pré-live e concluir o primeiro ciclo V103 às
  21:50:23: 35 partidas, 7 tarefas processadas, 4 pareamentos Bet365, 10
  mercados anexados, API saudável, zero falhas de rede, zero bloqueios de
  fonte e nenhuma pausa preventiva.
- [x] Confirmar na supervisão seguinte o watchdog saudável, reconhecendo o
  ciclo V103 e a custódia SQLite íntegra em três de três gatilhos.

## Integridade imutável da taxa histórica V102 — 12/09/2026

- [x] Identificar que a estimativa V2 era congelada antes do Telegram, mas o
  conteúdo persistido ainda podia ser alterado no SQLite sem detecção própria.
- [x] Versionar e assinar por SHA-256 a política completa da coorte executável,
  incluindo fonte, bookmaker, janela, prior, unidade e corte temporal.
- [x] Selar cada fotografia com hash do conteúdo canônico antes da primeira
  tentativa de envio e reutilizar exatamente a mesma fotografia nas edições.
- [x] Validar versão, política, hash, população, contadores, IDs independentes,
  taxa observada e cálculo Beta(1,1) antes de apresentar qualquer percentual.
- [x] Falhar fechado diante de adulteração, vínculo divergente ou sinal de
  origem ausente, sem afetar filtros, calibração ou entrega do alerta.
- [x] Criar auditoria somente leitura de todos os registros V2 e integrá-la à
  supervisão do watchdog como inconsistência operacional explícita.
- [x] Confirmar a base real saudável e vazia de V2 antes do primeiro alerta
  novo, sem retropreencher mensagens antigas nem reutilizar registros V1.
- [x] Aprovar 348 testes integrados e a regressão integral de 2.740/2.740.
- [x] Retomar monitor, watchdog e pré-live com hashes carregados iguais aos
  atuais e as três travas corretas; confirmar a auditoria V102 saudável em
  `sem_registros` e o primeiro ciclo real às 21:28:21, com 38 partidas, 8
  tarefas processadas, 6 pareamentos Bet365, 18 mercados anexados, API
  saudável, zero bloqueios de fonte e nenhuma pausa preventiva.

## Taxa histórica exibida alinhada à execução V101 — 12/09/2026

- [x] Identificar que a taxa descritiva mostrada no Telegram ainda podia
  combinar resultados entregues com odds PackBall, API-Football e Bet365.
- [x] Criar uma coorte V2 exclusiva de entregas cuja fotografia congelada
  comprove integralmente a mesma oferta BetsAPI/Bet365 executável.
- [x] Revalidar fonte, casa, mercado, linha ou seleção, odd, lados, horário,
  cache e origem de mercado antes de contar cada green ou red.
- [x] Fazer a seleção da primeira exposição executável por partida, sem uma
  entrega agregada anterior expulsar a primeira Bet365 válida posterior.
- [x] Impedir que um alerta de fonte mista herde uma taxa Bet365 e informar
  explicitamente quando não existir histórico comparável.
- [x] Preservar o recorte causal anterior ao alerta, a janela fixa de 90 dias,
  o Beta(1,1), o intervalo de Wilson e a separação entre descrição e
  probabilidade individual calibrada.
- [x] Congelar os novos números sob chave V2, sem reinterpretar nem apagar os
  registros V1 já exibidos em mensagens antigas.
- [x] Auditar a base real: o último próximo gol Bet365 possui zero resultados
  executáveis comparáveis; um Gol HT possui 1, enquanto 30 entregas de fontes
  ou provas incompatíveis são corretamente excluídas.
- [x] Aprovar 146 testes diretamente ligados à apresentação e a regressão
  integral de 2.737/2.737 testes.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais e confirmar o
  primeiro ciclo real V101 às 21:09:33: 38 partidas, 8 tarefas processadas,
  odds nas 8 e BetsAPI/Bet365 nas 8, API saudável, zero falhas de rede, zero
  bloqueio de fonte e nenhuma pausa preventiva.
- [x] Confirmar o watchdog saudável após o ciclo, com o sucesso V101
  reconhecido e o ciclo seguinte iniciado normalmente.

## Calibração alinhada à execução Bet365 V100 — 12/09/2026

- [x] Auditar a composição real das amostras das regras operacionais e
  confirmar que a calibração V10 não exigia fonte, bookmaker nem fotografia
  congelada da cotação usada na entrada.
- [x] Confirmar na base real que, entre 9 resultados da regra atual de
  próximo gol, somente 1 possui prova BetsAPI/Bet365 V2 completa; os outros
  8 pertencem a universos de preço diferentes.
- [x] Confirmar que os 30 resultados de próximo escanteio e os 39 de
  escanteios FT da regra atual não possuem essa mesma prova executável.
- [x] Criar a política de calibração V11 cuja população contém somente
  sinais aprovados com oferta BetsAPI/Bet365 íntegra, congelada e revalidada.
- [x] Fazer a pré-seleção da fonte antes da independência por partida, para
  uma leitura agregada anterior não expulsar a primeira Bet365 executável.
- [x] Vincular a fotografia da cotação ao fingerprint do modelo e falhar
  fechado se a custódia for adulterada.
- [x] Impedir que um modelo executável forneça probabilidade a um candidato
  de PackBall, API-Football, outra casa ou prova incompleta.
- [x] Alinhar progresso, diversidade, partição temporal, frescor, preflight,
  watchdog e auditoria à mesma população executável.
- [x] Preservar os históricos de fontes mistas como pesquisa, sem tratá-los
  como prova suficiente para uma futura entrada oficial.
- [x] Aprovar 427 testes integrados e a regressão integral final de
  2.734/2.734 testes.
- [x] Retomar monitor, watchdog e pré-live, reconciliar as calibrações V11 e
  confirmar hashes, travas e snapshot saudável.
- [x] Concluir o primeiro ciclo real V100 às 20:50:16: 54 partidas, 9 tarefas
  detalhadas, odds utilizáveis nas 9, BetsAPI/Bet365 em 8, API saudável,
  zero falha de rede, zero bloqueio de fonte e nenhuma pausa preventiva.
- [ ] Acumular 100 resultados executáveis por regra e manter qualquer modelo
  oficial desativado até desenvolvimento 70/holdout 30, AUC, IC95, erro de
  calibração, ROI, diversidade e drift aprovarem a ativação.

## Coorte executável de escanteios FT V99 — 12/09/2026

- [x] Confirmar que a coorte prospectiva V2 aceitava candidatos de qualquer
  fonte/casa e, portanto, poderia provar um edge impossível de executar.
- [x] Preservar a V2 como diagnóstico imutável, sem apagar ou reinterpretar
  seu histórico.
- [x] Criar uma coorte causal V3 nova, fixa em 100 partidas com divisão
  cronológica desenvolvimento 70/holdout 30 e checkpoint de segurança em 25.
- [x] Exigir que todo membro possua fotografia V2 íntegra e congelada da
  mesma oferta BetsAPI/Bet365 aceita pelo gateway oficial.
- [x] Impedir que odds agregadas, casa desconhecida, linha divergente ou prova
  incompleta ocupem uma vaga; registrar essas exclusões e seus motivos em
  tabela SQLite imutável própria.
- [x] Revalidar conteúdo e hash de membros e exclusões ao ler a coorte,
  falhando fechado diante de adulteração.
- [x] Fazer somente a V3 executável decidir o edge dos escanteios no portfólio
  e no circuit breaker; a V2 aparece apenas como comparação diagnóstica.
- [x] Expor a V3, sua fonte/casa, progresso, exclusões e decisão no watchdog e
  no status; incluir o novo módulo nas assinaturas de monitor/watchdog e na
  auditoria dos relógios causais.
- [x] Aprovar 428 testes integrados diretamente relacionados e a regressão
  integral final de 2.732/2.732 testes.
- [x] Aprovar o preflight, registrar a âncora às 20:15:53 e retomar monitor,
  watchdog e pré-live com PIDs, hashes e travas atuais.
- [x] Concluir o primeiro ciclo real V99 às 20:21:27: 48 partidas, 9 tarefas
  detalhadas, 19 adiadas pela reserva segura, API saudável, zero falha de
  rede, zero bloqueio de fonte e nenhuma pausa preventiva.
- [x] Confirmar no snapshot seguinte do watchdog a V3 saudável, alinhada à
  execução e com zero violação; a coorte começou vazia e causal.
- [ ] Observar o primeiro candidato futuro de escanteios com fotografia
  BetsAPI/Bet365 íntegra e confirmar sua entrada na V3 ou a exclusão exata.
- [ ] Fechar os 100 casos e liberar revisão humana somente se ROI, IC95,
  desenvolvimento, holdout, taxa positiva e referência sem vig passarem.

## Custódia executável no gateway oficial V98 — 12/09/2026

- [x] Confirmar no SQLite que candidatos historicamente aprovados podiam
  carregar odd agregada do PackBall ou API-Football sem bookmaker declarada.
- [x] Preservar essas fontes para observação, backtest e simulação, sem
  confundi-las com um preço que o usuário consegue executar.
- [x] Exigir, somente para futura entrada oficial, fotografia imutável V2 da
  cotação BetsAPI/Bet365 com mercado, linha ou seleção, todos os lados,
  horário, idade, cache, odd e origem de mercado coerentes.
- [x] Falhar fechado se candidato, features e prova congelada divergirem,
  sem procurar preço substituto no histórico.
- [x] Manter simulações e formação de amostra intactas; o novo gate não altera
  HT, FT, geração, calibração nem promoção automática.
- [x] Preservar no gateway o motivo específico
  `cotacao_oficial_nao_executavel` e expor contagens no status operacional.
- [x] Auditar a base real: ainda não há candidato simultaneamente aprovado,
  calibrado e criado sob o novo marcador; portanto nenhum sinal existente foi
  removido retroativamente.
- [x] Aprovar 362 testes diretamente relacionados e a regressão integral final
  de 2.728/2.728 testes.
- [x] Aprovar o preflight transacional, retomar monitor, watchdog e pré-live
  com hashes e travas atuais e observar a recuperação do primeiro snapshot
  transitório do watchdog sem reinício indevido.
- [x] Concluir o primeiro ciclo real V98 às 19:56:03: 45 partidas, 8 tarefas
  detalhadas, 21 adiadas pelo orçamento seguro, API saudável, zero falha de
  cache/rede, zero bloqueio de fonte e nenhuma pausa preventiva.
- [ ] Observar o primeiro candidato futuro simultaneamente calibrado e apto
  para o gateway, confirmando em produção a aceitação BetsAPI/Bet365 ou o
  bloqueio específico da cotação não executável.

## Funil causal do HT antecipado preciso V51 — 10/09/2026

- [x] Separar decisões do gerador, partidas independentes, decisões elegíveis
  e rejeições do filtro HT antecipado preciso.
- [x] Consolidar o último motivo das partidas ainda sem elegibilidade e expor
  o gargalo atual no resumo de prontidão profissional.
- [x] Garantir por contrato que o diagnóstico não consulta resultados nem
  entregas e não altera sinais, Telegram ou promoção.
- [x] Comprovar na base real que houve uma decisão em uma partida após a
  âncora, rejeitada por finalizações no gol insuficientes.
- [x] Preservar integralmente as regras HT e o FT principal `sinais-v6`.
- [x] Aprovar 593 testes relacionados de validação, prontidão, monitor e
  watchdog.
- [x] Retomar os três componentes e concluir ciclo real com três de três
  tarefas processadas, API saudável e nenhuma pausa preventiva.
- [ ] Acumular decisões futuras suficientes antes de avaliar qualquer ajuste
  nos limiares ou promoção do HT.

## Separação explícita entre experimento e entrada V50 — 10/09/2026

- [x] Rotular toda mensagem do grupo de teste como análise experimental que
  não representa entrada.
- [x] Diferenciar `GREEN/RED DA SIMULAÇÃO` e retorno hipotético dos resultados
  e do ROI oficial.
- [x] Identificar a taxa histórica como propriedade da coorte do método, não
  como chance individual da partida.
- [x] Exibir ponto de equilíbrio da odd, margem histórica bruta e intervalo de
  Wilson de 95% sem usar esses números como autorização de entrada.
- [x] Classificar o valor como inconclusivo quando a faixa de incerteza inclui
  o ponto de equilíbrio.
- [x] Preservar filtros, canais, limites, calibração e gates oficiais.
- [x] Aprovar 317 testes relacionados e reconstruir o alerta real que motivou
  a correção.
- [x] Reiniciar de forma controlada e concluir ciclo real saudável com o novo
  código.
- [ ] Continuar coletando a coorte prospectiva; somente uma probabilidade
  calibrada, validação temporal e edge conservador podem promover uma rota.

## Custódia independente das fontes de odds V49 — 10/09/2026

- [x] Auditar separadamente os recortes observacional executável e de
  convergência de preço usados pela avaliação V12.
- [x] Exigir contagens não negativas e somas coerentes por fonte e por origem.
- [x] Aceitar somente as origens observacionais autorizadas e a versão exata
  do contrato de fontes.
- [x] Exigir Bet365 como bookmaker executável e contraparte independente em
  ambos os recortes.
- [x] Falhar fechado como `contrato_fontes_invalido` diante de adulteração,
  ausência ou inconsistência, sem afetar sinais ou Telegram.
- [x] Expor fontes, origens, independência e saúde do contrato no status.
- [x] Aprovar 22 testes direcionados, 656 testes integrados e todos os 177
  módulos isolados do preflight.
- [x] Interromper com segurança uma abertura do navegador sem permissão e
  repetir o reinício sem duplicar processos.
- [x] Retomar monitor, watchdog e pré-live; concluir o primeiro ciclo com 12
  partidas, cinco tarefas, zero falhas e nenhuma pausa preventiva.
- [ ] Aguardar observações futuras multifonte nas chaves prospectivas V5/V3 e
  decidir somente após coorte e holdout pré-registrados suficientes.

## Retomada idempotente de resultados asiáticos V48 — 10/09/2026

- [x] Manter o sistema em manutenção após o rollback transacional detectar a
  violação de integridade, sem desativar gatilhos nem apagar evidências.
- [x] Isolar o único resultado afetado e comprovar o ciclo repetido entre
  `sem_dado`, recuperação multifonte como `void` e reabertura indevida.
- [x] Reconhecer como terminal o resultado de escanteios FT produzido pelo
  contrato forte de total estável, encerramentos PackBall e confirmações da
  API-Football, inclusive quando o desfecho é `void`.
- [x] Manter observações genéricas, fontes únicas e confirmações incompletas
  fora dessa exceção.
- [x] Preservar o histórico append-only e o resultado real sem alteração.
- [x] Aprovar 113 testes direcionados e validar zero reaberturas numa cópia do
  banco de produção.
- [x] Aprovar o preflight integral e retomar monitor, watchdog e pré-live com
  supervisão saudável e nenhum alerta de falha.

## Referência assíncrona de odds nos snapshots V47 — 10/09/2026

- [x] Auditar as 125 observações rápidas reais e comprovar que as 125 exclusões
  decorreram da ausência de uma segunda fonte de gols na mesma linha.
- [x] Preservar o bloqueio fail closed: sem referência independente exata não
  existe candidato de desajuste.
- [x] Recuperar, somente para as linhas já monitoradas, contrapartes que já
  estavam persistidas nos snapshots do SQLite.
- [x] Exigir mesma partida, mercado, período, linha, seleção, placar e minuto,
  além de fonte independente e janela temporal válida.
- [x] Impedir que outra bookmaker vinda do mesmo provedor seja contada como
  confirmação independente.
- [x] Expor por fonte e por origem quais observações formaram cada recorte.
- [x] Abrir chaves prospectivas novas para o observacional V5 e para a
  convergência de preço V3, sem reaproveitar membros antigos.
- [x] Manter filtros, sinais e Telegram inalterados e bloquear promoção
  automática.
- [x] Aprovar 20 testes específicos e 523 testes integrados.
- [ ] Aguardar partidas futuras com duas fontes exatas e decidir somente após
  coorte, seguimentos, resultados e holdout pré-registrados suficientes.

## Auditoria automática dos relógios de coorte V46 — 10/09/2026

- [x] Formalizar que sinais ao vivo usam horário local sem offset e bilhetes
  pré-live V12 usam UTC com offset.
- [x] Auditar definição, hash, presença e equivalência dos dois relógios das
  quatro coortes prospectivas atuais ligadas a `sinais`.
- [x] Amostrar os 200 sinais recentes e os 152 bilhetes V12 reais, rejeitando
  timestamp inválido ou pertencente ao contrato temporal oposto.
- [x] Integrar a auditoria somente leitura ao preflight e bloquear a retomada
  quando qualquer contrato estiver inconsistente.
- [x] Aprovar cinco testes específicos e 42 testes combinados de auditoria e
  preflight, mantendo filtros, Telegram e processos operacionais inalterados.

## Relógio causal das coortes prospectivas V45 — 10/09/2026

- [x] Confirmar no banco real que `sinais.criado_em` usa horário local sem
  offset e que três âncoras antigas usavam UTC com offset.
- [x] Versionar HT antecipado preciso, FT antecipado preciso e escanteios FT
  asiáticos para V2 sem alterar ou apagar suas definições V1.
- [x] Preservar UTC com offset para auditoria e usar um segundo campo no
  relógio local dos sinais para a seleção causal e o corte histórico.
- [x] Fazer a definição falhar fechado se qualquer relógio obrigatório estiver
  ausente ou adulterado.
- [x] Manter o único membro da V1 de HT como histórico separado e iniciar as
  três V2 vazias, sem backfill e sem consultar resultados.
- [x] Aprovar 21 testes específicos, 547 testes integrados e todos os 176
  módulos do preflight integral.
- [x] Registrar as três âncoras V2 no banco de produção, retomar monitor,
  watchdog e pré-live e concluir o primeiro ciclo com 38 partidas, 7 tarefas,
  zero falhas e sem pausa preventiva.
- [ ] Aguardar as coortes futuras V2 e decidir somente após os tamanhos,
  holdouts e intervalos de confiança pré-registrados serem satisfeitos.

## Quase-candidatos prospectivos de Próximo Gol V44 — 10/09/2026

- [x] Converter a auditoria exploratória de descartes em duas hipóteses
  prospectivas pré-registradas, sem selecionar unidades pelo resultado.
- [x] Isolar o braço de odd 1,65–1,99 do braço de atividade com chute dominante
  e impedir que uma partida entre nos dois braços.
- [x] Congelar 60 partidas por braço, com desenvolvimento 42 e holdout 18, em
  tabela SQLite vinculada ao hash imutável da definição.
- [x] Excluir em modo fail closed cartão vermelho, odd vencida, fonte ruim e
  qualquer bloqueio não explicitamente permitido.
- [x] Exigir ROI com intervalo de 95%, replicação temporal e vantagem sobre a
  referência conservadora `1/odd` antes de liberar somente revisão manual.
- [x] Impedir Telegram, aplicação em sinais, promoção e reativação automáticas.
- [x] Integrar registro, sincronização, watchdog, hash de runtime e status.
- [x] Corrigir antes da primeira inclusão a diferença entre UTC da auditoria e
  o relógio local sem offset de `sinais.criado_em`, versionando a definição V2.
- [x] Aprovar 554 testes direcionados dos componentes afetados.
- [x] Aprovar os 176 módulos do preflight integral, registrar a âncora V2 no
  banco de produção e concluir o primeiro ciclo com 41 partidas e 7 tarefas,
  sem falha e com início normal do ciclo seguinte.
- [ ] Aguardar 60 membros e resultados suficientes em cada braço; somente uma
  revisão humana futura pode decidir se alguma hipótese merece novo teste.

## Auditoria contrafactual dos descartes V43 — 10/09/2026

- [x] Reutilizar as auditorias silenciosas já liquidadas sem criar sinais ou
  acessos adicionais.
- [x] Fixar a primeira unidade por `partida+estado_de_gols` antes do resultado,
  impedindo substituição oportunista por repetição posterior.
- [x] Separar pendente, resultado válido e resultado inválido e calcular ROI
  somente quando retorno e desfecho forem coerentes.
- [x] Estratificar a auditoria pela distância técnica observada no instante da
  decisão.
- [x] Rotular o estudo como exploratório, não pré-registrado e incapaz de
  alterar filtro, sinais, Telegram ou promoção automática.
- [x] Expor no status a fotografia inicial de quatro estados, 0 green, 1 red e
  3 pendentes, sem inferir desvantagem pela única unidade resolvida.
- [x] Aprovar 53 testes direcionados sem pausar o PackBall ou escrever no banco.

## Proteção de risco no funil marginal V42 — 10/09/2026

- [x] Excluir do denominador do funil as cópias de auditoria silenciosa, que
  servem à liquidação contrafactual e não são novas decisões técnicas.
- [x] Expor separadamente candidatos tecnicamente completos, candidatos que
  também atravessam o gate e os bloqueios adicionais de risco.
- [x] Confirmar que o primeiro estado tecnicamente completo foi barrado por
  cartão vermelho, sem remover essa proteção.
- [x] Confirmar que o primeiro estado a uma condição técnica de distância
  ainda possuía bloqueio adicional de atividade recente.
- [x] Integrar o resumo ao `status_bot.py` sem alterar monitor, filtros,
  Telegram, calibração ou promoção.
- [x] Aprovar 51 testes direcionados e executar o status real com código zero,
  mantendo os três processos Python do sistema ativos.

## Diagnóstico marginal do Próximo Gol V41 — 10/09/2026

- [x] Separar o funil cumulativo de aprovação do diagnóstico marginal, para
  que uma primeira trava zerada não esconda os gargalos técnicos seguintes.
- [x] Medir a melhor proximidade por `partida+estado_de_gols` no mesmo
  snapshot, sem combinar critérios satisfeitos em momentos diferentes.
- [x] Excluir resultados da análise de proximidade e manter o relatório
  somente leitura, sem efeito em sinais, Telegram ou promoção automática.
- [x] Auditar 103 linhas e 52 estados prospectivos: zero candidatos técnicos
  completos, distância mínima de dois critérios em cinco estados, odd curta
  presente em 6 e pressão balanceada em 9.
- [x] Recusar um relaxamento oportunista de apenas um limite, pois nenhum
  estado observado foi barrado por somente um critério.
- [x] Aprovar 19 testes direcionados mantendo o PackBall ativo.
- [ ] Reavaliar a distribuição marginal após exposição operacional suficiente
  e formular um novo braço somente se surgir uma hipótese pré-registrável que
  preserve preço executável, pressão e confirmação ofensiva no mesmo snapshot.

## Liquidação conservadora e preflight resiliente V40 — 10/09/2026

- [x] Recuperar escanteios FT asiáticos somente quando o total terminal
  permanecer invariável desde uma leitura multifonte apta no fim do tempo
  regulamentar.
- [x] Exigir três confirmações PackBall, dez minutos de estabilidade e duas
  confirmações finais independentes da API-Football.
- [x] Manter `sem_dado` quando houver qualquer mudança posterior que possa
  pertencer à prorrogação.
- [x] Revisar o sinal 338536 para `void` e preservar o sinal 204367 como
  indeterminado, com trilha de auditoria.
- [x] Ampliar o prazo global do preflight para 300 segundos.
- [x] Exigir três execuções limpas em processos novos para reconhecer uma
  falha comum isolada como transitória.
- [x] Bloquear imediatamente falha nativa e bloquear qualquer falha comum que
  reapareça durante as confirmações.
- [x] Aprovar 36 testes do preflight, 38 do finalizador e os 174 módulos da
  suíte completa.
- [x] Retomar monitor e watchdog e confirmar o primeiro ciclo com 45 partidas
  seguido do início normal do próximo ciclo.

## Preflight isolado por módulo V39 — 10/09/2026

- [x] Reproduzir a falha nativa do Python 3.14 no preflight executado no mesmo
  ambiente externo necessário ao navegador.
- [x] Provar que o teste indicado no instante da queda passa isoladamente e
  que a causa é o estado acumulado entre módulos.
- [x] Identificar também falsos negativos causados por configuração temporária
  herdada por módulos posteriores da mesma suíte.
- [x] Executar cada arquivo de testes em processo local descartável,
  sequencial e sem janela, preservando a cobertura integral.
- [x] Manter timeout global, ambiente limpo e bloqueio imediato diante de
  qualquer teste reprovado, sem retries que possam mascarar defeitos.
- [x] Tornar módulo, código de saída e falha nativa visíveis no diagnóstico.
- [x] Aprovar no ambiente real os 174 módulos e 2.501 testes em 84,122
  segundos, sem Telegram real.

## Retomada resiliente e armazenamento robusto V38 — 10/09/2026

- [x] Trocar a projeção sensível aos extremos pela mediana Theil–Sen das
  inclinações entre pares de amostras válidas.
- [x] Preservar a variação bruta entre extremos como evidência separada no
  diagnóstico, sem usá-la para interromper a operação.
- [x] Confirmar que um salto único de backup não gera alerta permanente e que
  crescimento linear sustentado continua sendo detectado.
- [x] Aplicar a política oficial de retenção e remover dois backups
  pré-reinício antigos e não protegidos, preservando redundância recente.
- [x] Reconciliar o backup diário antes do preflight quando o banco já estiver
  no esquema atual, evitando bloqueio após migração interrompida.
- [x] Excluir da lista de falhas efetivas avisos contidos e explicitamente
  aprovados para reinício.
- [x] Recuperar o último ciclo concluído e falhas posteriores mesmo quando a
  rotação do JSONL ocorrer durante um ciclo em andamento.
- [x] Preservar e revalidar o backup SQLite original quando somente a etapa de
  compressão falhar, registrando aviso sem derrubar a coleta.
- [x] Manter falha fechada se a compressão e o backup original estiverem
  inválidos.
- [x] Aprovar 254 testes direcionados dos componentes alterados e 2.499 testes
  integrais sem Telegram
  real.

## Ritmo operacional auditável por coorte V37 — 10/09/2026

- [x] Calcular ritmo separadamente para cada versão e coorte, sem somar metas
  que podem receber a mesma partida.
- [x] Exigir no mínimo 5 unidades independentes e 24 horas operacionais
  confirmadas antes de estimar dias restantes.
- [x] Marcar o ritmo como preliminar até reunir 15 unidades e 72 horas; só
  então classificá-lo como observado.
- [x] Reconstruir exposição por sequências de ciclos do monitor e impedir que
  lacunas offline ou simples tempo de parede sejam tratados como coleta.
- [x] Exigir cobertura da telemetria desde a âncora da coorte para permitir a
  extrapolação.
- [x] Normalizar âncoras UTC para a hora local dos eventos históricos antes de
  calcular a janela.
- [x] Integrar pré-live, HT, FT, Próximo Gol balanceado e escanteios FT
  asiáticos ao relógio de prontidão, preservando coortes e validadores.
- [x] Manter o prazo global e a data indisponíveis, inclusive quando algum
  método individual adquirir ritmo, pois ainda existem gates independentes.
- [x] Confirmar no estado real pausa planejada, ausência de falha técnica,
  nove compromissos quantificados e zero ritmos extrapoláveis.
- [x] Aprovar 159 testes direcionados e 2.491 testes integrais sem iniciar o
  bot ou enviar Telegram real.

## Prazo de prontidão baseado em coortes V36 — 10/09/2026

- [x] Suspender explicitamente o calendário de prontidão durante manutenção e
  impedir que tempo de parede seja apresentado como coleta.
- [x] Recusar data e quantidade de dias enquanto não existir ritmo
  prospectivo da versão e coorte exatas.
- [x] Expor cada meta causal separadamente e declarar que coortes não podem ser
  somadas para estimar esforço ou prazo.
- [x] Incluir o seletor pré-live e a coorte CLV no mesmo diagnóstico de
  faltantes dos mercados ao vivo.
- [x] Recuperar do validador aninhado candidatos, resultados e faltantes dos
  métodos FT ativos, sem perder a auditoria completa do portfólio.
- [x] Confirmar no banco real nove compromissos quantificados, maior meta 120,
  calendário suspenso, pausa planejada e ausência de falha técnica.
- [x] Aprovar 120 testes direcionados e 2.486 testes integrais sem iniciar o
  bot ou enviar Telegram real.

## Gate central do worker de treinamento V35 — 10/09/2026

- [x] Reutilizar o autoteste isolado na coleta central de evidências de
  prontidão, sem acoplá-lo ao fluxo de reinício.
- [x] Exigir saúde, estado permitido e protocolo exato antes de aprovar o
  worker de treinamento.
- [x] Fazer falha do worker degradar `operacao_continua` e permanecer visível
  como pendência técnica mesmo durante manutenção planejada.
- [x] Expor no resumo operacional estado, tentativas, recuperação transitória,
  motivo e duração do autoteste.
- [x] Confirmar o diagnóstico real em `pausa_planejada`, sem falha técnica,
  com o worker pronto em 57,948 ms na primeira tentativa.
- [x] Aprovar 181 testes direcionados e 2.484 testes integrais sem iniciar o
  bot ou enviar Telegram real.

## Autoteste do worker no preflight V34 — 10/09/2026

- [x] Provar localmente, antes da retomada, que o worker pode ser criado e
  responder ao protocolo restrito com a custódia do processo pai ativa.
- [x] Usar desafio efêmero para impedir que saída vazia ou obsoleta pareça uma
  resposta válida.
- [x] Bloquear o preflight diante de falha de processo, timeout, protocolo ou
  resposta incompatível, sem expor detalhes internos do erro.
- [x] Tornar tentativas e recuperação transitória visíveis no diagnóstico.
- [x] Confirmar o autoteste real em 54,424 ms, na primeira tentativa.
- [x] Aprovar 86 testes direcionados e 2.482 testes integrais sem abrir fonte
  externa, enviar Telegram ou remover a manutenção manual.

## Treinamento numérico isolado V33 — 10/09/2026

- [x] Reproduzir a corrupção numérica intermitente dos ajustes logísticos nos
  runtimes Python 3.13 e 3.14, em vez de tratá-la como teste instável.
- [x] Isolar os treinamentos contextual e de janelas longas em processo local
  descartável, sem bloquear nem corromper o monitor principal.
- [x] Aplicar timeout de cinco segundos, até três tentativas e processo oculto
  no Windows.
- [x] Vincular o worker ao PID vivo do chamador e autoencerrá-lo em até 250 ms
  se perder a custódia, impedindo processos órfãos após interrupção.
- [x] Distinguir erros determinísticos de dados de falhas transitórias do
  runtime e nunca persistir saída incompleta ou incompatível.
- [x] Revalidar versão, configuração, features, mercado e amostra antes de
  aceitar cada modelo.
- [x] Persistir no modelo a auditoria das tentativas e falhas recuperadas.
- [x] Incluir helper e worker nas assinaturas do monitor e do watchdog.
- [x] Aprovar 100 treinos isolados entre Python 3.13/3.14, 40 treinos dos dois
  challengers integrados, 148 testes direcionados e 2.480 testes integrais.
- [x] Preservar manutenção manual, ausência de Telegram real e efeitos dos
  challengers bloqueados.

## Retomada manual transacional V32 — 10/09/2026

- [x] Exigir a opção explícita `--retomar-manutencao` para que o iniciador
  manual tenha autoridade de remover uma pausa persistida.
- [x] Preservar a manutenção, não executar preflight e não criar processos
  quando o iniciador comum for aberto por engano.
- [x] Manter a autorrecuperação do Windows sem autoridade para desfazer uma
  pausa manual.
- [x] Restaurar a manutenção se monitor ou watchdog falharem ao ser criados,
  inclusive quando o primeiro componente já tiver sido iniciado.
- [x] Restaurar a manutenção diante de falha explícita ou ausência de estado,
  PID e trava durante a confirmação de estabilidade.
- [x] Persistir o motivo `rollback_inicio_instavel` e registrar a ocorrência
  na trilha de observabilidade sem expor a mensagem bruta do erro.
- [x] Fazer o relógio `exposicao-coleta-prospectiva-v2` reconhecer o rollback
  como início de pausa histórica, sem contabilizá-lo como coleta ou amostra.
- [x] Atualizar os procedimentos de parada, retomada e transferência para o
  novo comando explícito.
- [x] Aprovar 72 testes direcionados e 2.478 testes integrais, preservando a
  pausa real e sem iniciar processos ou enviar Telegram.

## Gate central de exposicao prospectiva V31 — 10/09/2026

- [x] Fazer a coleta de evidencias revalidar diretamente as quatro avaliacoes
  periodicas, sem confiar apenas no ultimo espelho geral do watchdog.
- [x] Criar um diagnostico agregado para custodia, cronologia, efeitos e
  relogios V30, com detalhamento por avaliacao.
- [x] Exigir versao exata, ancora presente, telemetria saudavel e nenhum pedido
  de atencao antes de aceitar cada relogio.
- [x] Auditar os seis efeitos do proprio relogio e degradar diante de campo
  ausente, tipo divergente ou valor ativo.
- [x] Incluir o gate em `operacao_continua` e na prontidao profissional, sem
  transformar exposicao em edge ou liberar sinais.
- [x] Provar que manutencao planejada nao esconde relogio degradado nem remove
  a classificacao de pendencia tecnica.
- [x] Expor o diagnostico no resumo compacto de prontidao.
- [x] Auditar o estado real: quatro avaliacoes, sete relogios, duas coortes com
  exposicao, cinco pausadas e zero problemas.
- [x] Aprovar 2.474 testes e preservar pausa manual, efeitos operacionais
  bloqueados e nenhum Telegram real.

## Relogio de exposicao prospectiva V30 — 10/09/2026

- [x] Separar falta de amostra por pausa planejada de pipeline ativo sem
  coleta, sem usar tempo de parede como substituto de observacao real.
- [x] Reconstruir pausas encerradas e abertas pela trilha de observabilidade,
  consolidar sobreposicoes e desconta-las do relogio operacional.
- [x] Contar apenas ciclos concluidos, falhas, partidas, tarefas, duracao real,
  comparacoes de odds e cobertura BetsAPI posteriores a cada ancora.
- [x] Tratar ancora futura ou invalida, telemetria indisponivel e estado de
  manutencao invalido como situacoes que exigem atencao.
- [x] Detectar mais de uma hora operacional sem ciclo, inclusive quando uma
  manutencao posterior poderia esconder que o pipeline ja estava parado.
- [x] Manter relogios independentes para a coorte principal, o recorte de
  desajuste executavel e as convergencias prospectivas de gols e escanteios.
- [x] Integrar a exposicao ao limite comum de persistencia, aos hashes de
  runtime, aos quatro verificadores do watchdog e ao status operacional.
- [x] Preservar os seis efeitos observacionais como `false`, sem sinal,
  calibracao, prioridade, promocao, reativacao ou Telegram automatico.
- [x] Regenerar as quatro fotografias reais: espera pela odd com 252 ciclos,
  8.049 partidas e 1.145 tarefas; ligas e HT sem exposicao por manutencao; e
  desajuste com uma de quatro coortes observada e tres em pausa planejada.
- [x] Aprovar 2.471 testes, `PRAGMA quick_check=ok`, manutencao ativa, zero
  processos Python e nenhum Telegram real.

## Higiene de conexoes SQLite da suite V29 — 10/09/2026

- [x] Reproduzir o `ResourceWarning` observado na suite com rastreamento de
  alocacao, sem atribui-lo por proximidade a mensagem de probabilidade.
- [x] Localizar a unica conexao perdida no fixture SQLite em memoria do
  challenger de proximo gol balanceado.
- [x] Registrar fechamento garantido pela infraestrutura do `unittest`,
  inclusive quando o teste falha antes de chegar ao final.
- [x] Aprovar 23 testes relacionados com `ResourceWarning` tratado como erro.
- [x] Aprovar novamente os 2.462 testes completos sem o aviso de conexao nao
  encerrada.
- [x] Confirmar que o vazamento era da suite, nao do runtime produtivo, e que
  nenhum efeito operacional ou Telegram real foi acionado.

## Contrato explicito de efeitos observacionais V28 — 10/09/2026

- [x] Identificar que estados concluidos ainda deixavam alguns efeitos
  operacionais ausentes ou `null`, apesar de serem somente observacionais.
- [x] Elevar a custodia para `custodia-execucao-avaliacao-v3` e definir os
  seis campos obrigatorios: sinal, calibracao, prioridade, promocao,
  reativacao e Telegram.
- [x] Sobrescrever todos os seis como booleano `false` no limite comum de
  persistencia, sem confiar no retorno individual de nenhum avaliador.
- [x] Auditar completude, tipo e valor no watchdog e invalidar a custodia se
  houver campo ausente, `null`, tipo incorreto ou valor `true`.
- [x] Normalizar toda saida publica dos quatro verificadores como fail-closed,
  cobrindo tambem erro precoce, arquivo ausente e metodologia antiga.
- [x] Expor `efeitos=bloqueados` ou os campos invalidos no status operacional.
- [x] Provar por regressao que ate um estado persistido com `telegram=true` e
  selo positivo e bloqueado e devolvido com todos os efeitos falsos.
- [x] Regenerar as quatro fotografias reais sob custodia V3, cronologia valida
  e contrato completo, sem liberar qualquer vantagem operacional.
- [x] Aprovar 2.462 testes, manter manutencao ativa, zero processos e nenhum
  Telegram real.

## Cronologia inviolavel das avaliacoes V27 — 10/09/2026

- [x] Identificar que o calculo anterior limitava idade negativa a zero e
  permitia que uma data muito futura parecesse fresca indefinidamente.
- [x] Elevar o contrato comum para `custodia-execucao-avaliacao-v2` e auditar
  inicio, atualizacao, finalizacao e duracao sem confiar na idade persistida.
- [x] Aceitar no maximo 60 segundos de diferenca futura de relogio e rejeitar
  inicio posterior a atualizacao, final anterior ao inicio e divergencia de
  finalizacao maior que um segundo.
- [x] Rejeitar duracao ausente, negativa ou nao finita em conclusao/falha e
  idade invalida em execucao ainda aberta.
- [x] Fazer os quatro watchdogs bloquearem amostras, selos de vantagem, sinal,
  calibracao, prioridade, promocao, reativacao e Telegram diante de cronologia
  impossivel.
- [x] Expor `cronologia=ok` ou os problemas concretos no status operacional.
- [x] Cobrir cronologia valida, futuro forjado, ordem impossivel, duracao NaN e
  idade ausente com testes de regressao fail-closed.
- [x] Regenerar as quatro fotografias reais sob custodia V2 e comprovar
  cronologia valida em todas, sem liberar qualquer efeito operacional novo.
- [x] Aprovar 2.459 testes, `PRAGMA quick_check=ok`, manutencao ativa, zero
  processos e nenhum Telegram real.

## Custodia comum das avaliacoes periodicas V26 — 10/09/2026

- [x] Auditar todas as rotinas periodicas e localizar o mesmo risco de estado
  antigo na espera pela odd, prioridade de ligas e quarentena HT.
- [x] Centralizar o protocolo em `custodia-execucao-avaliacao-v1`, sem manter
  quatro implementacoes de seguranca divergentes.
- [x] Gravar `em_execucao` antes do calculo e aceitar `concluida` somente com
  versao estatistica e custodia exatamente compativeis.
- [x] Persistir `falha` sem copiar amostras, recortes ou conclusoes positivas
  da rodada anterior.
- [x] Desativar no envelope sinal, calibracao, prioridade, promocao,
  reativacao e Telegram.
- [x] Fazer os quatro watchdogs falharem fechados diante de custodia ausente,
  estado invalido, erro ou execucao abandonada por mais de 600 segundos.
- [x] Isolar falha da telemetria e rejeitar o resultado de um avaliador que
  retorne versao ou contrato de custodia inesperado.
- [x] Incluir o modulo comum nas assinaturas transitivas do monitor e do
  watchdog.
- [x] Regenerar as quatro fotografias reais: espera V6, ligas V3, desajuste
  V11 e quarentena HT V3, todas concluidas e com custodia compativel.
- [x] Aprovar 2.455 testes, manter todas as conclusoes observacionais e
  preservar manutencao ativa, zero processos e nenhum Telegram real.

## Falha fechada da avaliacao multifonte V25 — 10/09/2026

- [x] Identificar que uma excecao deixava a ultima avaliacao saudavel no disco
  e permitia que ela parecesse atual por ate uma hora.
- [x] Gravar um marcador `em_execucao` antes de iniciar qualquer calculo, sem
  copiar candidatos, persistencia ou selos positivos da rodada anterior.
- [x] Substituir atomicamente o marcador por `concluida` somente depois de a
  avaliacao integral ser calculada e persistida.
- [x] Persistir `falha` com erro redigido e efeitos operacionais desativados
  quando o avaliador ou a escrita final produzirem excecao.
- [x] Tratar como interrompida uma execucao deixada em andamento por mais de
  600 segundos, cobrindo queda abrupta entre inicio e conclusao.
- [x] Fazer o watchdog V11 ignorar todo resultado positivo quando a execucao
  nao estiver concluida e distinguir avaliando, falha e abandono.
- [x] Isolar falha da telemetria depois da persistencia, impedindo que um erro
  apenas observacional invalide um resultado ja salvo com sucesso.
- [x] Expor no status a execucao, saude, motivo, auditoria integral,
  fingerprint, corroboracao e bloqueio de inferencia.
- [x] Aprovar 2.450 testes e reavaliar o SQLite real em 0,767 segundo, com
  4.045/4.045 comparacoes validas, zero invalidas e fingerprint
  bc235e831a10c94aa0d2abb2935722534d2abe10d7b9da9d2078cf12af39c6ee.
- [x] Manter a avaliacao observacional, a promocao automatica desligada e o
  bot em manutencao, sem coleta ou Telegram real.

## Replay integral das comparacoes multifonte V24 — 10/09/2026

- [x] Identificar que imutabilidade e hash persistido nao bastavam quando o
  avaliador nao recalculava a evidencia antes de usa-la.
- [x] Centralizar os campos canonicos e reproduzir o SHA-256 de cada
  comparacao V4 diretamente a partir do SQLite.
- [x] Recalcular melhor preco, fonte, bookmaker, controle, deltas, intervalo,
  minuto, compatibilidade, estado e motivos sem confiar nas colunas derivadas.
- [x] Usar os precos originais, e nao o delta arredondado, nas fronteiras dos
  limiares de desajuste.
- [x] Excluir linhas invalidas de toda amostra e bloquear inferencia quando
  houver corrupcao, inconsistencia ou auditoria truncada.
- [x] Propagar o bloqueio para persistencia, convergencia e todos os selos de
  vantagem executavel, mantendo aplicacao e Telegram desativados.
- [x] Fazer o watchdog validar a versao V10, as contagens, o fingerprint e a
  coerencia da cadeia antes de expor qualquer conclusao positiva.
- [x] Provar em teste que uma alteracao com SHA-256 recalculado continua sendo
  detectada pela matematica e que um estado inconsistente falha fechado.
- [x] Aprovar 2.442 testes e reproduzir 4.045 de 4.045 comparacoes reais, com
  zero invalidas e fingerprint
  bc235e831a10c94aa0d2abb2935722534d2abe10d7b9da9d2078cf12af39c6ee.
- [x] Manter o bot em pausa_planejada, sem promocao automatica ou Telegram
  real.

## Corroboracao prospectiva da odd de entrada V23 — 10/09/2026

- [x] Identificar que a API-Football era apenas fallback e nao controlava a
  cotacao BetsAPI no instante em que ela atingia o alvo.
- [x] Consultar a fonte de controle somente no alvo, sem consumir chamadas
  adicionais durante as observacoes abaixo da faixa.
- [x] Revalidar contrato Over/Under, origem do grupo, identidade do evento,
  equipes, placar e relogio de cada fonte de forma independente.
- [x] Preservar a BetsAPI como oferta principal e anexar a API-Football apenas
  como fotografia de controle, sem alterar a decisao do sinal.
- [x] Persistir Over e Under de forma append-only em
  comparacoes_odds_fontes, com marcador prospectivo especifico.
- [x] Isolar indisponibilidade ou divergencia da fonte de controle sem
  bloquear um sinal principal que ja passou por todos os gates vigentes.
- [x] Criar a avaliacao V9 por fotografia e jogo, com minimo de 30 fotografias
  e 15 jogos antes de revisao e promocao automatica proibida.
- [x] Fazer o watchdog exigir e expor o novo recorte, falhando fechado quando
  um documento V9 estiver incompleto.
- [x] Permitir reavaliacao com ancoras existentes contra SQLite somente
  leitura, sem INSERT OR IGNORE desnecessario.
- [x] Aprovar 2.439 testes e auditar 3.814 comparacoes historicas e 202
  candidatos, com zero fotografias V23 retroativas.
- [x] Manter a prontidao em pausa_planejada, sem falha tecnica, sem
  promocao de regra e sem Telegram real.

## Custodia persistente de anomalias da curva V22 — 10/09/2026

- [x] Identificar que o bloqueio V21 acontecia depois da persistencia da oferta
  individual e sobrevivia apenas na telemetria transitória do ciclo.
- [x] Entregar a fotografia completa das odds ao SQLite e reconstruir a curva
  dentro da camada de custodia, sem confiar no diagnóstico do chamador.
- [x] Exigir correspondencia exata de mercado, periodo, grupo, linha e dos dois
  precos da oferta selecionada antes de considerar uma curva comparavel.
- [x] Persistir inversoes e duplicatas contraditorias como
  `anomalia-curva-odd-v1`, com as linhas canonicas e o cálculo reproduzivel.
- [x] Tornar a anomalia append-only, protegida por SHA-256 e explicitamente nao
  autorizada para comparacao, materializacao ou Telegram.
- [x] Fazer a cadeia CLV V11 recalcular a prova e detectar adulteracao do
  diagnóstico mesmo quando o hash do payload também for recalculado.
- [x] Expor a contagem `anomalias_curva_odds` e o motivo matematico exato na
  observabilidade da rechecagem rapida.
- [x] Aprovar 2.431 testes e auditar em modo somente leitura 10.254 observacoes,
  1.289 ofertas e 1.562 payloads reais, com zero anomalias e zero problemas.
- [x] Preservar o fingerprint historico, evitar migracao, manter a prontidao em
  `pausa_planejada` sem falha tecnica e nao enviar Telegram real.

## Coerencia matematica da curva de odds V21 — 10/09/2026

- [x] Identificar que uma cotacao completa e do grupo correto ainda podia
  conter uma curva de linhas logicamente impossivel.
- [x] Formalizar a ordem de dominancia dos mercados Over e Under para linhas
  binárias terminadas em 0,5.
- [x] Comparar somente linhas com a mesma assinatura de grupo, fonte e
  bookmaker, sem misturar mercados vizinhos de origem diferente.
- [x] Rejeitar duplicatas contraditorias e inversoes de preco em qualquer lado
  da curva selecionada.
- [x] Persistir o diagnostico da curva nas features e impedir o congelamento da
  cotacao quando a estrutura estiver incoerente.
- [x] Propagar o bloqueio ate o status do candidato e o gateway anterior ao
  Telegram, sem transformar a anomalia em suposta vantagem.
- [x] Expor na telemetria o motivo exato, as linhas e o lado incoerente para
  medir ocorrencias por ciclo sem depender de inspecao manual.
- [x] Incluir o novo modulo nas assinaturas de runtime do monitor e watchdog.
- [x] Aprovar 2.425 testes, preservar o SQLite sem migracao e manter o PackBall
  pausado, sem Telegram real.

## Custodia ponta a ponta da origem do mercado V20 — 10/09/2026

- [x] Identificar que a prova do grupo podia se perder entre a oferta validada,
  a cotacao congelada, o calculo sem vig e a auditoria CLV.
- [x] Centralizar a normalizacao e a assinatura de
  `origem-mercado-odd-v1` em um unico contrato compartilhado.
- [x] Considerar ambiguas duas cotacoes com os mesmos precos e horarios quando
  vierem de grupos distintos da casa de apostas.
- [x] Fazer a rota rapida selecionar somente a oferta cuja origem coincide com
  o grupo ja confirmado e bloquear origem malformada ou divergente.
- [x] Criar `cotacao-entrada-clv-v2` com a origem do mercado incorporada a
  evidencia imutavel da decisao.
- [x] Revalidar fonte, bookmaker, linha, lados e assinatura do grupo no calculo
  de valor e no gateway que antecede o Telegram.
- [x] Fazer a auditoria CLV V20 distinguir cotacoes congeladas V1 e V2,
  mantendo compatibilidade historica sem permitir downgrade do contrato atual.
- [x] Incluir o novo modulo na assinatura de codigo do monitor e do watchdog.
- [x] Aprovar 2.419 testes e auditar 10.254 observacoes e 1.562 payloads reais,
  com 12 gatilhos e zero problemas.
- [x] Preservar o SQLite sem migracao, manter o PackBall pausado e nao enviar
  Telegram real durante a mudanca.

## Origem sincronizada do grupo de mercado V19 — 10/09/2026

- [x] Reproduzir o risco de um Over e um Under da mesma linha serem combinados
  apesar de pertencerem a grupos Bet365 diferentes e incompletos.
- [x] Montar pares apenas dentro de cada grupo para gols FT, gols HT e
  escanteios asiaticos, descartando qualquer grupo incompleto ou suspenso.
- [x] Exigir as tres selecoes de proximo gol dentro do mesmo grupo e do ordinal
  correspondente ao placar atual.
- [x] Vincular cada nova oferta a fonte, ID/nome do grupo, linha, lados e
  bookmaker por meio de `origem-mercado-odd-v1`.
- [x] Fazer BetsAPI e API-Football emitirem a mesma prova e validar tambem que a
  casa da oferta coincide com a casa declarada pela origem.
- [x] Bloquear avaliacao, SQLite, materializacao e Telegram quando a prova do
  grupo estiver ausente, incompleta ou divergente.
- [x] Versionar novas evidencias como `oferta-monitorada-odd-v4`, preservar
  todo o historico e auditar V2, V3 e V4 sem reescrita retroativa.
- [x] Estender a continuidade imutavel de identidade a V3/V4 e elevar a cadeia
  CLV para V10, com 12 gatilhos presentes e validos.
- [x] Criar e verificar `pre_migracao_20260910_031428.db`, SHA-256
  `41ad81e21395fc6eb621cc8e78bbce7bea54755a4aa54d14881eadce434048a6`.
- [x] Aprovar 2.414 testes e auditar 10.254 observacoes reais com zero
  problemas, mantendo o fingerprint historico intacto.
- [x] Manter o PackBall pausado e nao enviar Telegram real durante a mudanca.

## Correspondencia independente das equipes da odd V18 — 10/09/2026

- [x] Identificar que `confirmada=true`, nomes preenchidos e placar coerente
  ainda nao provavam que os nomes pertenciam a partida do PackBall.
- [x] Normalizar novamente nomes, acentos e siglas comuns no validador central,
  sem confiar exclusivamente no resultado declarado pela integracao.
- [x] Exigir similaridade minima de 0,76 por equipe e media minima de 0,84 para
  o par orientado, alinhada ao pareador BetsAPI.
- [x] Propagar mandante e visitante ao estado revalidado pela API-Football para
  aplicar a checagem antes da avaliacao da faixa de odd.
- [x] Repetir no SQLite a comparacao contra as equipes persistidas da partida,
  bloqueando tambem chamadas diretas com identidade autodeclarada.
- [x] Fazer a cadeia CLV V9/V18 auditar as equipes de toda evidencia V3 e expor
  uma categoria especifica para divergencia de nomes.
- [x] Aprovar 2.410 testes e auditar 10.254 observacoes reais com 11 gatilhos,
  zero problemas e fingerprint historico preservado.
- [x] Manter o PackBall pausado e não enviar Telegram real durante a mudanca.

## Continuidade imutavel da identidade das odds V17 — 10/09/2026

- [x] Identificar que duas cotacoes individualmente validas ainda podiam trocar
  de evento externo durante a trajetoria do mesmo sinal.
- [x] Fixar identificador externo e orientacao na primeira evidencia V3 de cada
  combinacao sinal/fonte e recusar qualquer alteracao posterior.
- [x] Repetir a invariavel em um gatilho SQLite `BEFORE INSERT`, protegendo
  gravacoes concorrentes e rotas laterais.
- [x] Gravar em `evento_externo_id` o ID real da fonte da odd e preencher os
  nomes observados a partir da prova validada.
- [x] Tornar a rota de envio fail-closed quando a evidencia nao for persistida
  ou sua gravacao gerar excecao, sem comparacao ou materializacao posterior.
- [x] Fazer a cadeia CLV V8/V17 confrontar coluna e payload e detectar troca de
  ID ou orientacao ao longo da mesma referencia e fonte.
- [x] Criar e verificar o backup pre-migracao
  `pre_migracao_20260910_024356.db` antes de instalar o novo gatilho.
- [x] Confirmar 29 tabelas compativeis, 11 gatilhos de custodia, zero violacoes
  de chave estrangeira e zero problemas em 10.254 observacoes reais.
- [x] Aprovar 2.409 testes, mantendo o PackBall pausado e sem Telegram real.

## Identidade externa vinculada a cada odd V16 — 10/09/2026

- [x] Identificar que um mercado completo ainda podia pertencer ao evento
  errado se o pareamento da fonte externa falhasse.
- [x] Vincular cada nova oferta a fonte, identificador externo, orientacao,
  equipes normalizadas, similaridade e placar normalizado.
- [x] Exigir identidade confirmada e placar coerente com o jogo atual antes de
  avaliar, persistir, materializar ou enviar uma entrada.
- [x] Gerar a prova BetsAPI a partir do pareador rigoroso, inclusive quando a
  ordem casa/visitante vier invertida.
- [x] Permitir recuperacao pela API-Football somente com fixture persistida,
  orientacao conhecida e placar atual coerente.
- [x] Versionar novas evidencias como `oferta-monitorada-odd-v3`, preservar V2
  e manter as 1.289 ofertas anteriores explicitamente como legado.
- [x] Fazer a cadeia CLV V7/V16 falhar fechada diante de identidade V3 ausente,
  malformada ou vinculada a placar divergente, mesmo com hash correto.
- [x] Auditar 10.254 observacoes e 1.562 payloads reais com zero problemas e
  fingerprint historico preservado.
- [x] Aprovar 2.406 testes, mantendo a pausa e sem Telegram real.

## Contrato completo e sincronizado de mercado V15 — 10/09/2026

- [x] Medir o legado real e confirmar que 1.289 ofertas rapidas historicas nao
  carregavam o lado oposto no payload imutavel.
- [x] Exigir o par Over/Under completo e valido em toda nova leitura de
  `gol_ht` e `gol_ft`.
- [x] Exigir Casa, Visitante e Sem gol na mesma fotografia de `proximo_gol`,
  confirmando a correspondencia entre selecao e odd escolhida.
- [x] Bloquear observacao, materializacao e envio quando o contrato estiver
  incompleto, sem fabricar precos ausentes.
- [x] Congelar novamente a cotacao CLV no instante exato da conversao rapida,
  sem reutilizar a odd baixa que criou a fila.
- [x] Tratar alteracao de qualquer lado do mercado como movimento material,
  inclusive quando a odd selecionada permanecer igual.
- [x] Versionar novas evidencias como `oferta-monitorada-odd-v2` e preservar
  as 1.289 linhas legadas sem reescrita retroativa.
- [x] Fazer a cadeia CLV V6/V15 falhar fechada para um contrato V2 incompleto,
  mesmo quando seu hash estiver correto.
- [x] Auditar 10.254 observacoes reais, com zero problemas e fingerprint
  historico preservado.
- [x] Aprovar 2.404 testes, mantendo a pausa e sem Telegram real.

## Proveniencia temporal dupla das odds V14 — 10/09/2026

- [x] Identificar que `idade_segundos` isolada podia declarar frescor sem ser
  confrontada com o horario real `coletado_em` da fonte.
- [x] Exigir idade valida, horario interpretavel e indicador booleano de cache
  em toda cotacao usada pela rechecagem rapida.
- [x] Recalcular a idade, rejeitar relogio futuro ou atraso acima de 30 s e
  limitar a divergencia entre os dois relogios a 5 s.
- [x] Permitir cache curto somente quando as duas provas temporais forem
  coerentes, evitando reduzir sinais por uma proibicao arbitraria de cache.
- [x] Repetir a validacao no SQLite antes do `INSERT`, sem permitir que uma
  chamada lateral envenene a trilha de custodia imutavel.
- [x] Persistir a prova temporal no alerta convertido e incluir
  `relogio_da_fonte_coerente` entre os criterios revalidados.
- [x] Fazer a cadeia CLV V5/V14 auditar odd, fonte, idade, cache, horario
  futuro, expiracao e divergencia, inclusive contra payload com hash valido.
- [x] Medir 1.289 cotacoes reais: zero campos invalidos, atraso de -0,859 s a
  30 s e divergencia maxima de 0,998 s; confirmar zero problemas apos a regra.
- [x] Recusar `NaN`, infinito e odds menores ou iguais a 1 antes de qualquer
  persistencia ou decisao operacional.
- [x] Aprovar 2.400 testes, preservando a pausa e sem Telegram real.

## Ordem causal das cotacoes rapidas V13 — 10/09/2026

- [x] Distinguir ordem de insercao da ordem temporal real em cada trajetoria
  `acompanhamento_odd:<sinal>`.
- [x] Comparar uma nova leitura com o maior instante ja persistido, mantendo
  no historico qualquer linha atrasada sem permitir que ela vire estado atual.
- [x] Marcar a regressao como `ordem_temporal_valida=false`, sem contabiliza-la
  como mudanca material de preco.
- [x] Bloquear a materializacao do alerta e a comparacao entre fontes quando a
  observacao recebida estiver fora de ordem.
- [x] Fazer a cadeia CLV V4 falhar fechada diante de qualquer regressao e
  detectar inclusive varias leituras ainda atras do mesmo maximo causal.
- [x] Auditar o banco real: 1.289 cotacoes, 381 referencias, zero regressoes e
  um empate de horario valido, ordenado pelo identificador append-only.
- [x] Aprovar 2.395 testes, incluindo regressao temporal deliberada no banco e
  bloqueio operacional de uma cotacao que atingiria a odd-alvo.

## Integridade semantica das evidencias de odds V12 — 10/09/2026

- [x] Distinguir imutabilidade futura de validade do conteudo originalmente
  inserido na trilha de fontes de odds.
- [x] Recalcular o SHA-256 de cada payload e rejeitar hash ausente, malformado,
  divergente, sem payload ou JSON invalido.
- [x] Validar nas ofertas monitoradas a referencia ao sinal e a coerencia de
  partida, mercado, linha, fonte e identificador dentro do payload.
- [x] Incorporar a auditoria de conteudo a cadeia CLV V3 e falhar fechada se
  existir qualquer inconsistencia, mesmo com todos os gatilhos presentes.
- [x] Expor quantidades, problemas por categoria e fingerprint das evidencias
  na prontidao e no status operacional.
- [x] Auditar o banco real: 10.254 observacoes imutaveis, 1.289 ofertas
  monitoradas, 1.562 payloads e zero problemas.
- [x] Aprovar 2.393 testes, incluindo corrupcao deliberada, mantendo o bot em
  manutencao e sem Telegram real.

## Trajetoria imutavel das fontes de odds — 10/09/2026

- [x] Identificar que cotacoes repetidas na trilha rapida sobrescreviam o
  horario e o hash da observacao anterior, ocultando parte do historico.
- [x] Persistir cada oferta monitorada em uma nova linha, mesmo sem mudanca de
  preco, mantendo `mudanca_material` separado da existencia da evidencia.
- [x] Preservar o cursor `consulta_monitoramento` como estado operacional
  compacto, pois ele nao representa preco nem entra na prova de valor.
- [x] Bloquear update e delete de todas as demais observacoes de fonte por
  dois gatilhos SQLite obrigatorios.
- [x] Impedir a retencao de apagar a identidade da partida enquanto existir
  uma observacao de fonte auditavel ligada a ela.
- [x] Atualizar o CLV para V11/cadeia V2, exigir dez gatilhos e confirmar no
  banco real a cadeia integra, sem liberar inferencia ou mercado.
- [x] Aplicar migracao aditiva apos o backup verificado
  `pre_migracao_20260910_013517.db`; validar tambem o backup diario compactado.
- [x] Aprovar 2.393 testes com manutencao ativa e sem Telegram real.

## Avaliacao CLV autocontida V10 — 10/09/2026

- [x] Identificar que o relatorio CLV isolado podia consultar uma copia do
  SQLite sem provar que a populacao e os precos estavam protegidos.
- [x] Auditar dentro da propria avaliacao os oito gatilhos de imutabilidade de
  entregas, sinais, snapshots e odds, incluindo operacao/tabela e abort.
- [x] Expor gatilhos presentes, ausentes, definicoes invalidas e fingerprint
  das definicoes para tornar a cadeia de custodia observavel.
- [x] Separar `pronta_estatisticamente` de `pronta_para_conclusao` e falhar
  fechada: sem custodia integra, nenhuma vantagem pode ser informada mesmo com
  efeito positivo e replicado.
- [x] Transformar custodia ausente/invalida em falha tecnica na prontidao e
  mostrar o bloqueio de inferencia no status operacional.
- [x] Validar os oito gatilhos no banco real; coorte em 0/120, estado
  `formando_coorte_fixa`, custodia integra e `pode_informar_edge=false`.
- [x] Aprovar 2.393 testes mantendo o PackBall pausado e sem Telegram real.

## Cadeia de custodia dos precos pos-alerta — 10/09/2026

- [x] Identificar que a retencao preservava o snapshot de entrada, mas podia
  apagar snapshots e odds posteriores usados no horizonte CLV de dez minutos.
- [x] Tornar `snapshots` e `odds` append-only no SQLite, rejeitando qualquer
  alteracao posterior da evidencia coletada.
- [x] Impedir exclusao do snapshot de entrada e das observacoes da mesma
  partida entre a entrega e dez minutos, com suas odds associadas.
- [x] Alinhar a rotina de retencao a definicao da populacao CLV, preservando o
  horizonte probatorio sem impedir a limpeza de dados antigos nao relacionados.
- [x] Tornar os quatro gatilhos obrigatorios no pre-voo e aplicar a migracao
  aditiva ao banco real somente apos backup pre-migracao verificado.
- [x] Confirmar banco real compativel com 29 tabelas, nenhum objeto ausente e
  zero violacoes de FK; validar checksums e integridade SQLite dos backups
  `pre_migracao_20260910_011918.db` e `monitor_20260910.db.gz`.
- [x] Aprovar 2.390 testes com o PackBall em manutencao e sem Telegram real.
- [ ] Na retomada autorizada, observar a primeira unidade prospectiva e
  confirmar que a cotacao futura permanece disponivel depois do ciclo de
  retencao antes de usar CLV em qualquer revisao manual.

## Imutabilidade da populacao CLV — 10/09/2026

- [x] Corrigir a confirmacao idempotente que podia sobrescrever os horarios
  originais de uma entrega ja confirmada.
- [x] Congelar no SQLite identidade, canal, horarios e status de toda entrega
  de entrada confirmada e impedir sua exclusao.
- [x] Congelar partida, snapshot, horario, mercado, linha, odd e features do
  sinal depois que sua entrada for entregue, sem impedir mudancas legitimas de
  status operacional que nao alteram a evidencia da coorte.
- [x] Excluir notificacoes de resultado e `:correcao` da populacao CLV e
  preservar o fluxo auditado de reabertura/correcao de liquidacoes.
- [x] Tornar os quatro gatilhos obrigatorios no pre-voo e na auditoria de
  compatibilidade do esquema.
- [x] Aplicar a migracao aditiva ao banco real somente apos backup
  pre-migracao verificado; confirmar 29 tabelas, nenhum objeto ausente, zero
  violacoes de FK e backup diario compactado integro.
- [x] Aprovar 2.389 testes mantendo o PackBall em manutencao e sem Telegram.

## Coorte fixa de CLV/mark-to-market — 10/09/2026

- [x] Remover a divisao 70%/30% movel, que permitia a uma unidade migrar do
  holdout para desenvolvimento conforme novas partidas chegavam.
- [x] Pre-registrar antes da primeira entrega nova uma coorte de 120 partidas
  instrumentadas: 84 para desenvolvimento e 36 para holdout fixo.
- [x] Excluir os 880 registros legados antes da selecao e manter entregas apos
  a unidade 120 fora da composicao e do fingerprint da coorte.
- [x] Exigir coorte completa, ao menos 90% de cobertura da cotacao de entrada,
  ao menos 90% de comparabilidade em cada particao e 30 comparaveis por bloco.
- [x] Exigir que o efeito reapareca com o mesmo sinal no desenvolvimento e no
  holdout para marcar vantagem ou desvantagem replicada.
- [x] Marcar historico amplo, janelas moveis, recortes exploratorios e cada
  particao isolada como nao inferenciais; somente a coorte conjunta pode
  informar revisao manual.
- [x] Manter `pode_decidir_edge=false`, gate desligado e promocao automatica
  proibida; aprovar 2.387 testes com manutencao ativa e nenhum envio real.
- [ ] Na retomada autorizada, completar 120 partidas instrumentadas e revisar
  manualmente apenas se cobertura e replicacao satisfizerem todos os criterios.

## Reserva de coleta do preco futuro — 10/09/2026

- [x] Identificar que a priorizacao final podia remover do lote real uma
  cotacao pos-alerta ja agendada quando a partida passava da janela de novos
  sinais.
- [x] Reservar uma unica posicao entre as tres primeiras para o acompanhamento
  mais proximo de expirar, sem aumentar acessos, navegacoes ou alertas.
- [x] Preservar rechecagens criticas e expor quantidade de acompanhamentos,
  idade, presenca no top 3 e acionabilidade da partida nos diagnosticos.
- [x] Confirmar que a reserva coleta apenas evidencia prospectiva: nao muda
  score, odd de entrada, decisao, liquidacao nem autorizacao de mercado.
- [x] Aprovar 2.383 testes com manutencao ativa e nenhum envio real.
- [ ] Na retomada autorizada, medir a cobertura das primeiras 30 partidas
  instrumentadas e investigar qualquer perda ainda dominante antes de usar o
  CLV como evidencia de vantagem.

## Coorte prospectiva de cobertura da cotação de entrada — 10/09/2026

- [x] Separar as entregas produzidas pelo pipeline novo dos 880 registros
  legados do CLV; o legado permanece auditável, mas não entra no denominador
  da instrumentação futura.
- [x] Definir a coorte pela presença do estado de cotação persistido no
  instante da decisão, antes de comparabilidade, movimento futuro ou resultado.
- [x] Contabilizar cotação completa congelada, cotação inválida, oferta ambígua
  ou incompleta e comparabilidade posterior, no total e por mercado.
- [x] Exigir ao menos 30 partidas independentes e 90% de cotações de entrada
  válidas para considerar a instrumentação suficiente, sem transformar essa
  verificação em gate de sinal ou promoção automática.
- [x] Expor a coorte na prontidão profissional e no status. A linha de base
  real está corretamente em 0 entregas instrumentadas e 880 legadas porque o
  mecanismo foi instalado depois da pausa.
- [x] Aprovar 2.382 testes com o PackBall em manutenção, sem envio real ou
  ativação de mercado.
- [ ] Após retomada autorizada, formar as primeiras 30 partidas da coorte e
  corrigir a origem dominante de perda se a cobertura ficar abaixo de 90%.

## Calibração oficial por coorte causal — 10/09/2026

- [x] Selecionar o primeiro sinal elegível de cada partida antes de consultar
  resultado, retorno ou horário de liquidação; uma ocorrência posterior não
  pode substituir a primeira por já estar resolvida ou ter sido vencedora.
- [x] Congelar as primeiras 100 exposições independentes, com desenvolvimento
  1–70 e validação 71–100 ordenados por `criado_em`, não por encerramento.
- [x] Fazer pendências, `void`, `sem_dado`, timestamps inválidos e retornos
  incompatíveis permanecerem visíveis e bloquearem a ativação da coorte em vez
  de desaparecerem do denominador.
- [x] Validar a coerência financeira integral e asiática; impedir que chamadas
  diretas ao calibrador convertam retorno ausente/inválido em zero.
- [x] Separar o modelo fixo do monitoramento móvel: o drift usa até 300 decisões
  válidas recentes, mantendo uma decisão por partida, e uma nova exposição
  ainda sem resultado não invalida o modelo em uso.
- [x] Invalidar modelos V8 e anteriores com a política
  `calibracao-score-odd-wilson-duplo-auc-ic-coorte-causal-v9`, expor no status
  unidades, válidas, pendentes, inválidas e prova de seleção pré-resultado.
- [x] Recalcular o diagnóstico histórico da regra-base `sinais-v6`.
  `gol_ft`: ROI holdout -18,87%, AUC 0,3616; `proximo_gol`: ROI +7,53%,
  AUC 0,6267, mas limite inferior AUC95 0,4253. Esses números não pertencem
  às versões operacionais atuais e não autorizam promoção.
- [x] Reconciliar separadamente as sete versões exatas acompanhadas pelo
  runtime. Todas ficaram inativas: `gol_ft` V11b 0 unidades, `gol_ht` V8c 0,
  `proximo_gol` V10f 8, `proximo_escanteio` V9c 30,
  `escanteios_ft_asiatico` V9d 43 exposições/39 válidas/4 inválidas e os dois
  mercados asiáticos por tempo com 0. O watchdog confirmou partições e
  frescor íntegros, sem calibração desatualizada.
- [x] Aprovar 2.380 testes sem iniciar o bot, enviar Telegram ou promover regra.
- [ ] Formar novas coortes das versões atuais até 100 unidades íntegras e só
  revisar mercados cuja vantagem seja positiva, financeiramente coerente e
  replicada no holdout. Corrigir separadamente os dois `sem_dado` de
  escanteios asiáticos sem reinterpretar os resultados conhecidos.

## Contexto avançado causal com holdout fixo — 10/09/2026

- [x] Corrigir a seleção que filtrava liquidação/contexto antes de escolher a
  primeira partida e podia substituir uma entrada inicial ausente por uma
  ocorrência posterior vencedora.
- [x] Fixar a primeira entrada aprovada de cada partida antes de resultado,
  odd e cobertura contextual; pendências e dados desconhecidos permanecem na
  população e impedem conclusão oportunista.
- [x] Validar a coerência financeira de odd, resultado e retorno, incluindo
  liquidações asiáticas e `void`, sem transformar ausência em retorno zero.
- [x] Substituir a janela móvel por coorte fixa de 300 partidas em cada mercado,
  com desenvolvimento 1–210 e holdout 211–300 determinados previamente.
- [x] Exigir pelo menos 30 unidades nos grupos “com” e “sem” em ambas as
  partições, correção de múltiplas comparações (`z=3`) e replicação do mesmo
  efeito no holdout antes de marcar qualquer variável como conclusiva.
- [x] Versionar como `avaliacao-contexto-sombra-causal-v6`; fazer os 955
  registros antigos permanecerem auditáveis, porém inelegíveis para revisão
  V6. Nenhum registro legado estava marcado como pronto.
- [x] Persistir cada mudança real da coorte por fingerprint, inclusive quando
  uma liquidação chega sem novo sinal, e proteger as sete âncoras contra update
  ou delete no SQLite.
- [x] Pré-registrar as regras atuais em `2026-09-10T00:15:12`, com zero unidades
  decisórias; atualizar status/watchdog e aprovar 2.377 testes sem iniciar o
  bot, promover regra ou enviar Telegram.
- [ ] Coletar 300 partidas e 300 liquidações válidas por mercado; revisar uma
  variável apenas se houver os mínimos nos dois braços e replicação integral
  no holdout fixo. Até lá, toda leitura de contexto permanece diagnóstica.

## Quarentena causal do fallback HT — 10/09/2026

- [x] Fixar a primeira candidata elegível por partida antes de consultar a
  liquidação; uma repetição posterior resolvida não substitui uma entrada
  inicial pendente ou inválida.
- [x] Impedir que a mesma partida atravesse os braços de linhas altas e
  controle `Over 0.5 HT`, preservando cruzamentos posteriores somente na
  auditoria.
- [x] Congelar as primeiras 100 partidas de cada braço, com desenvolvimento
  1–70 e holdout 71–100 definidos previamente; unidades posteriores são apenas
  diagnóstico.
- [x] Validar resultado, odd e retorno para liquidações integrais e asiáticas,
  falhando fechado quando houver ausência, valor não finito ou incoerência do
  contrato.
- [x] Recalcular o legado sem poder decisório: 185 registros brutos, 139
  elegíveis e 111 jogos independentes. Linhas altas 32 jogos, ROI -5,41%, IC95
  [-35,23%; +24,40%]; controle 79 jogos, ROI -19,01%, IC95
  [-38,94%; +0,92%]. Nenhuma conclusão causal foi autorizada.
- [x] Pré-registrar a V2 no SQLite em `2026-09-10T00:04:56`, iniciada com zero
  unidades e limitada à regra/status declarados; rejeitar V1 e metadados
  incompatíveis no watchdog.
- [x] Cobrir a dependência na assinatura do supervisor, expor a coorte no
  status e aprovar a regressão integral de 2.372 testes sem iniciar o bot,
  enviar Telegram ou reativar o fallback.
- [ ] Coletar 100 partidas e 100 liquidações válidas por braço, incluindo
  holdout fixo de 30 em cada um, antes de qualquer revisão manual. A quarentena
  permanece ativa e a promoção automática proibida.

## Prioridade de ligas sem pseudorreplicação — 09/09/2026

- [x] Trocar a unidade decisória de linha/ciclo repetido pela primeira exposição
  independente de cada partida, preservando repetições apenas no diagnóstico de
  processamento e latência.
- [x] Selecionar ciclos completos antes do limite, congelar o braço de cada jogo
  na primeira exposição e manter cruzamentos posteriores no braço originalmente
  atribuído.
- [x] Vincular cada sinal a uma única decisão da fila, deduplicar a união entre
  candidato aprovado e aviso de espera e excluir do ROI resultados de
  simulações/auditorias não acionáveis.
- [x] Recalcular o legado sem poder decisório: 11.712 decisões viraram 873 jogos
  independentes. Prioridade 1/108 oportunidades (0,93%), controle 15/765
  (1,96%), delta -1,03 p.p., IC95 [-3,05; +3,87]. Nenhuma vantagem ou regressão
  ficou comprovada.
- [x] Pré-registrar `avaliacao-prioridade-ligas-gols-prospectiva-v2` em
  `2026-09-09T23:48:46`, com zero unidades no marco; exigir 100 jogos e 30
  oportunidades por braço antes de revisão.
- [x] Fazer o watchdog rejeitar V1, cobrir a nova dependência na assinatura de
  reinício e expor a coorte causal no status. Regressão integral aprovada em
  2.366 testes, sem reordenar fila, iniciar o bot ou enviar alertas reais.
- [ ] Coletar prospectivamente a nova coorte V2 até os mínimos pré-registrados;
  escolher ligas individualmente somente depois de replicação fora da amostra.

## Coorte causal dos escanteios asiáticos históricos — 09/09/2026

- [x] Selecionar a primeira entrada por partida e coorte antes de consultar o
  resultado, usando `LEFT JOIN`; pendências e dados inválidos não podem ser
  substituídos por sinais posteriores já liquidados.
- [x] Congelar as primeiras 100 unidades independentes, com desenvolvimento
  1–70 e holdout 71–100 definidos antes do resultado. Unidades posteriores são
  apenas diagnóstico e não alteram ROI ou intervalo decisórios.
- [x] Validar a estrutura da linha asiática e a coerência entre resultado, odd
  e retorno para green, half-green, void, half-red e red, falhando fechado em
  qualquer corrupção.
- [x] Reprocessar a base real: 204 candidatas, 202 liquidações brutas válidas,
  41 unidades oficiais elegíveis e 27 entregues independentes. Das entregues,
  25 são válidas e 2 têm `sem_dado`; portanto, a coorte está incompleta e o
  holdout correto ainda possui zero jogos.
- [x] Manter esse histórico fora da decisão operacional quando a validação
  prospectiva pós-âncora existe; atualizar o portfólio read-only para V11 e
  expor `avaliacao-edge-escanteios-asiaticos-v3` na prontidão/status.
- [x] Aprovar 153 testes dirigidos e a regressão integral de 2.359 testes sem
  iniciar processos, enviar Telegram ou promover filtros.
- [ ] Aguardar a coorte prospectiva fixa alcançar os marcos pré-registrados;
  não usar o ROI histórico positivo como justificativa de ativação.

## Correção de causalidade da espera de odd — 09/09/2026

- [x] Remover vazamento temporal: faixa executável usa apenas cotação rápida
  coletada depois do aviso, nunca a odd inicial, snapshot normal ou observação
  pré-alerta.
- [x] Tornar a coorte independente pelo primeiro aviso de cada
  partida/mercado, mantendo todos os alertas apenas como diagnóstico.
- [x] Exigir `origem_sinal_id` exato e a versão compartilhada da materialização
  rápida para reconhecer uma entrada oficial ou encerrar a fila. Um sinal
  comum posterior, mesmo na linha correta, não é conversão da estratégia.
- [x] Invalidar estados metodológicos anteriores no watchdog e expor no status
  versão, conversão da faixa, ROI com IC95 e quantidade de execuções oficiais
  vinculadas. A política permanece sem aplicação automática.
- [x] Reprocessar o SQLite real: 180 conclusões independentes/179 jogos, 19
  faixas (10,56%), 2 entradas oficiais exatas, ROI hipotético por aviso +1,96%
  com IC95 [-0,87%, +4,29%]. O resultado é inconclusivo e não autoriza promover
  a espera como vantagem.
- [x] Validar banco, fila, materialização, Telegram, avaliação, status,
  watchdog e assinatura de reinício: 422 testes dirigidos e 2.342 testes na
  suíte completa aprovados.
- [ ] Obter pelo menos 30 execuções oficiais independentes com linhagem V5 e
  desfecho real antes de qualquer nova decisão operacional; faltam 28. Revisar
  somente com intervalo de confiança pré-registrado, sem escolher
  retrospectivamente mercados, minutos ou odds vencedores.

## Independência causal do desajuste de odds — 09/09/2026

- [x] Iniciar o relógio de persistência da Bet365 somente quando a cotação
  executável e a referência já forem conhecidas; preços anteriores à detecção
  não contam como seguimento.
- [x] Exigir placar inalterado e minuto não regressivo durante o seguimento.
- [x] Limitar os recortes executáveis de observação e convergência à primeira
  oportunidade por partida, impedindo que o mesmo resultado apareça mais de
  uma vez ou atravesse desenvolvimento e holdout.
- [x] Pré-registrar no SQLite a definição imutável
  `convergencia-preco-bet365-prospectiva-v2` antes da primeira amostra. Âncora:
  `2026-09-09T22:54:34`; candidatos existentes no marco: zero.
- [x] Invalidar no watchdog a metodologia V7 e anteriores, zerar selos
  decisórios incompatíveis e expor o recorte executável no status principal.
- [x] Verificar causalidade, independência, watchdog, assinatura de reinício e
  integração: suíte completa de 2.345 testes aprovada, sem ativar sinais.
- [ ] Coletar a coorte futura fechada de 60 partidas, com pelo menos 50
  seguimentos e 50 resultados (42 desenvolvimento/18 holdout), antes de uma
  revisão manual. Promoção automática continua proibida.

## Independência e cobertura do CLV live — 09/09/2026

- [x] Alterar a unidade primária do agregado para a primeira entrega por
  partida, escolhida antes do filtro de comparabilidade. Um mesmo evento não
  pode contar como vários jogos por aparecer em mercados diferentes.
- [x] Preservar recortes independentes por mercado, mas rotular os agregados
  partida/mercado e todas as entregas como diagnósticos correlacionados, sem
  permissão para informar ou decidir edge.
- [x] Fixar o corte cronológico 70/30 sobre todas as partidas e somente depois
  medir as cotações comparáveis em cada parte, evitando seleção pelo dado
  futuro disponível.
- [x] Exigir cobertura mínima de 90% para qualquer selo informativo de edge.
  A base real tem 999 entregas, 986 unidades partida/mercado, 880 partidas e
  apenas 203 comparáveis (23,07%); por isso a média observada permanece
  exploratória e o estado é `cobertura_insuficiente_para_informar_edge`.
- [x] Expor no status versão, unidade independente, 203/880 comparáveis,
  cobertura, mínimo exigido e decisão fail-closed. Aplicação e gate operacional
  continuam desligados.
- [x] Validar seleção pré-comparabilidade, correlação intrajogo, cobertura,
  corte cronológico, prontidão, status e assinatura de reinício: 2.349 testes
  aprovados, sem iniciar processos ou enviar Telegram.
- [ ] Formar uma coorte futura com cotação de entrada congelada e pelo menos
  90% de cobertura antes de reavaliar o CLV como evidência auxiliar de edge.

## Coortes causais do portfólio de edge — 09/09/2026

- [x] Selecionar a primeira entrada entregue por partida antes de consultar o
  resultado; uma duplicata resolvida não substitui a unidade inicial pendente.
- [x] Usar `LEFT JOIN` para preservar ausência de resultado e bloquear a
  decisão quando qualquer unidade da coorte fixa estiver pendente ou inválida.
- [x] Separar entradas `aprovado`, simulação genérica e cada versão sombra;
  nenhuma combinação entre métodos pode completar amostra, ROI ou IC95.
- [x] Congelar por coorte as primeiras 100 partidas, com fronteira fixa de 70
  para desenvolvimento e 30 para holdout. Unidades posteriores permanecem
  auditáveis, mas não alteram a decisão original.
- [x] Expor no status a versão V10, a decisão de cada mercado e a coorte
  efetivamente selecionada, mantendo promoção automática desativada.
- [x] Reprocessar a base real: `proximo_gol` usa `aprovado` com 3/100 partidas;
  `proximo_escanteio` usa `aprovado` com 16/100. Ambos aguardam amostra, nenhum
  mercado é favorável e nenhuma regra foi alterada.
- [x] Validar pendência anterior à duplicata, separação oficial/sombra, coorte
  fixa 70/30, gate oficial, prontidão, status e reinício: 2.355 testes
  aprovados com o bot em manutenção.
- [ ] Completar cada coorte prospectiva e revisar manualmente somente após
  resultado integral, preço sem vig com cobertura mínima e replicação positiva
  no holdout. Promoção automática continua proibida.

## Referência histórica sem vig causal — 09/09/2026

- [x] Preservar candidatas sem resultado no carregamento e escolher a primeira
  unidade por partida/coorte antes de validar desfecho ou reconstruir preço.
- [x] Tratar estados sucessivos de próximo gol do mesmo jogo como correlacionados
  para inferência; somente uma unidade por partida entra em cada coorte.
- [x] Exigir uma coorte homogênea, resultados completos, dados válidos, 100
  partidas, cobertura mínima de 90% e IC95 positivo de ROI e resíduo antes de
  exibir qualquer vantagem estatística descritiva.
- [x] Vincular no relatório do portfólio a versão exata
  `avaliacao-probabilidade-sem-vig-historica-v2`, tornando visível a metodologia
  usada para a referência de mercado.
- [x] Reprocessar `proximo_gol`: 1.481 candidatas, 671 unidades independentes,
  14 primeiras unidades pendentes/inválidas, cobertura de 85,08% e três coortes;
  vantagem descritiva falsa. Reprocessar `proximo_escanteio`: 30 partidas,
  cobertura de 100%, ainda sem amostra mínima.
- [x] Validar duplicata posterior, correlação entre estados do jogo, cobertura,
  integração com portfólio, prontidão, status e reinício: 2.356 testes aprovados
  sem ativar sinais.
- [ ] Reavaliar separadamente cada coorte somente quando atingir 100 partidas
  completas e 90% de cobertura, preservando o diagnóstico histórico como
  evidência auxiliar e nunca como promoção automática.

## Probabilidade individual — protocolo inicial de 02/09/2026

- **Estado: não ativada.** Ambos os modelos iniciais falharam no limite de calibração pré-fixado. O usuário esclareceu depois que deseja notícias, escalações e jogadores; o protótipo ainda não inclui essas camadas. Diagnóstico, limitações e etapas pendentes em `ANALISE_PROB_INDIVIDUAL_20260902.md`. Não confundir esta pesquisa offline com a estimativa histórica atualmente ativa.
- Escopo inicial: Over de gols HT/FT de meia linha. Camada informativa, sem mudar regras de entrada. O usuário corrigiu o pedido: a média do método não é a probabilidade pedida.
- Antes de consultar os resultados da validação: modelo logístico regularizado L2=0,5, 400 iterações, passo 0,08. Variáveis: tempo restante, placar, quantidade de gols ainda necessária, odd, ataque de cada time contra defesa rival, H2H com pelo menos três jogos, chutes/pressão/xG recentes e vermelhos quando conhecidos. Ausência não vira zero; features com menos de 50% de cobertura no treino são omitidas, com rastreabilidade. Efeitos de método/linhagem e segmento são separados dentro de cada mercado.
- Janela 90 dias de entregas reais resolvidas, primeira entrada por partida/mercado. Nenhum resultado de candidato não entregue, duplicata, void/parcial, snapshot futuro, cache atualizado depois do envio ou resultado conhecido depois do corte pode entrar. Histórico de diversas versões do mesmo mercado é usado para aprender relações condicionais, com identificação de versão; isto não significa que um método novo esteja validado.
- Protocolo fixo: pelo menos 80 jogos de treino, 15 greens e 15 reds; validação nos últimos 20% ou 30 jogos, o que for maior, com pelo menos cinco de cada classe. Purga do treino qualquer resultado ainda desconhecido no início da validação. Brier não mais que 0,01 acima da média constante do treino e erro agregado de calibração <=0,15 para apresentação inicial. Comparação com odd bruta também registrada, sem afirmar que 1/odd é probabilidade justa. Não otimizar corte de envio ou ROI nessa amostra.
- Mesmo aprovação inicial não autoriza o rótulo “calibrada” ou promessa de lucro. Saída será estimativa individual em validação; modelos insuficientes não receberão percentual inventado. Sem suporte na própria versão/segmento ou fora do domínio, manter indisponibilidade explícita. Mercados de cantos/pré-live aguardam confirmação do escopo solicitado.

## Probabilidade histórica por acertos — 02/09/2026

- Pedido explícito: estimar por acertos anteriores. Nova apresentação para sinais ao vivo não calibrados: porcentagem histórica suavizada + greens/reds usados. Não é probabilidade individual, validação de rentabilidade ou garantia; pré-live e probabilidade calibrada já existente permanecem como antes.
- Fórmula fixa Beta(1,1): `(greens + 1) / (greens + reds + 2)`, evitando exibir 100% em sequências curtas. Pelo menos cinco jogos para mostrar o número; abaixo de 30, aviso de amostra inicial. Estes mínimos são de apresentação, não atestado de confiabilidade.
- Janela fixa de 90 dias, mesma versão de método, mercado, fingerprint e linhagens disponíveis. Só entregas efetivamente confirmadas no Telegram, com green/red e retorno coerente. Exclui sombra não entregue, aviso de aguardar odd, edições, pendentes, void, half green/red e sem dado. Uma primeira entrada por partida na coorte, sem escolher o resultado melhor entre duplicatas.
- Corte estritamente anterior à criação da entrada, tanto para envio quanto para liquidação da base. Exclui o próprio sinal e a própria partida. Resultado conhecido depois não pode ensinar uma previsão anterior. A faixa de Wilson 95% e os IDs da base ficam no registro auditável.
- A estimativa é congelada antes do POST em `metadados`, chave `probabilidade_acertos:v1:sinal:ID`; retries e edições de resultado recuperam esse valor, não o recalculam com o resultado novo. Sinais legados não ganham porcentagem retroativa. Features de decisão, calibração e ROI não são sobrescritos.
- Trata-se de histórico agregado do método: não distingue cada odd, time ou minuto, e não comprova que proteções adicionadas sem mudança de versão sejam eficazes. Não usar para anunciar confiança individual ou alterar exposição/critério de entrada. Uma previsão contextual calibrada exigiria validação futura separada.
- Conferência real somente leitura às 13:14:32: referência HT00 v3, excluindo a própria partida, 42 greens/26 reds, estimativa 61,4%, Wilson95 49,9–72,4%. FT tendência v3: 4/1, estimativa 71,4%, Wilson95 37,6–96,4% (amostra muito pequena). Não são percentuais enviados retrospectivamente. Consulta local levou aproximadamente 10–12 ms por referência, sem API ou navegador adicional.
- Rollback isolado: `PROBABILIDADE_ACERTOS_ATIVA=0` e recarga controlada; volta ao formato anterior, preservando o registro. `RESUMO_FORCA_SINAIS_ATIVO=0` continua desligando todo o rodapé. Nenhum método/filtro/odd-alvo novo ativado; under continua aguardando escopo.
- Verificação e ativação: 1.984 testes aprovados (incluindo vazamento temporal, duplicidade, preservação do valor em green/red e isolamento de transações). Pré-voo aprovado; recarga controlada concluída. Monitor PID 8348 e watchdog PID 13556 ativos com trava própria e código atualizado; pré-live PID 30668 ativo. Não foram enviados exemplos manualmente ao Telegram nem alteradas mensagens antigas; sessão/Scanner preservados.

## Formato numérico dos sinais — 02/09/2026

- Por preferência explícita do usuário, a classificação textual de força abaixo foi substituída por probabilidade em porcentagem. Nenhum método ou critério de entrada mudou.
- Rota calibrada: exibir o percentual calibrado já validado pelo gateway. Rotas V2b/Poisson V1: exibir apenas a estimativa específica registrada pelo método da entrada, com aviso de modelo não calibrado. Não reaproveitar probabilidade de uma outra rota presente nos diagnósticos.
- Pré-live: exibir a probabilidade bruta do bilhete inteiro já calculada, como estimativa não calibrada; nunca usar a média das pernas. Avisos de escalação pendente continuam presentes.
- Métodos sem probabilidade específica mostram indisponibilidade. Nota técnica, taxa histórica de greens e inverso da odd não viram chance de acerto. Ausência, números inválidos e limites 0/1 não geram percentuais fictícios ou promessa de certeza.
- Mantido rollback da apresentação: `RESUMO_FORCA_SINAIS_ATIVO=0`. Resultados e cálculos existentes permanecem inalterados.
- Verificação: 1.968 testes aprovados. Recarga controlada concluída, monitor PID 26388 e watchdog PID 21872 ativos com código atualizado; pré-live PID 26804 ativo. Pedido adicional de under 1T/2T aguarda confirmação de escopo (ao vivo/pré-live); nenhum mercado under novo foi ativado nesta alteração de formato.

## Clareza da força dos sinais — 02/09/2026 (formato substituído a pedido)

- A pedido do usuário, mensagem informa evidências fortes, parciais, com ressalvas ou não classificadas. É descrição dos apoios registrados, não classificação validada de taxa de acerto nem nova regra de entrada.
- Ao vivo, a leitura forte exige apoio explícito do histórico da linha, tendência direta do período no PackBall, atividade recente já classificada forte pelo próprio método e qualidade >=80. Fallback do mesmo histórico não conta como confirmação adicional. Ausência de evidência não equivale a aprovação; exceções e divergências ficam visíveis.
- A nota bruta deixa de ocupar o rodapé compacto. Probabilidade bruta, edge, odd baixa e nota 100 não se transformam em chance real. Percentual calibrado só aparece na rota de entrega que já exige calibração válida; nas demais, explicitar que o acerto ainda não é calibrado.
- Pré-live considera todas as pernas: histórico 15 jogos/4 por mando, escalações e critérios V11 já registrados. Uma perna limitada impede chamar a combinação de forte. Lista usa uma linha compacta; bilhetes individuais mostram a base e ressalva.
- Apenas apresentação: nenhum gerador, filtro, mercado, odd-alvo, regra de risco, ROI ou método ativo foi alterado. O resultado futuro não entra na classificação da evidência original. Rollback da explicação: `RESUMO_FORCA_SINAIS_ATIVO=0` e recarga controlada.
- Verificação e ativação: 1.966 testes aprovados; reinício controlado confirmado. Monitor PID 29368 e watchdog PID 20784 ativos, travas próprias e código atualizado; pré-live PID 21612 retomado. Scanner e sessão sem edição.

## Proteção de atualidade histórica de 02/09/2026 — antes do Telegram

- Incidente: sinal 324329, Blacks Power × Police, Over 1,5 FT aos 55 minutos. O histórico disponível tinha um jogo de 2026 e 14 de 2023; quantidade de jogos não equivalia a histórico atual. A projeção temporal também usava distribuição sazonal baseada em um jogo.
- Nova proteção `validade-historico-gols-envio-v1`, sem trocar geradores, odds ou métodos ativos: antes da entrega, confere as datas dos jogos efetivamente usados nos últimos 15 disponíveis e, quando usado, no histórico Top de dez jogos por mando.
- Limite de atualidade adotado: 365 dias. Datas ausentes/futuras, cache indisponível ou diferente do resumo que sustentou a decisão bloqueiam o envio dependente desse histórico. Não transformar ausência de dados em aprovação. Cache recém-consultado não rejuvenesce uma partida de 2023.
- Projeção contextual que usa distribuição de gols por minuto da temporada exige pelo menos dez jogos na amostra de cada distribuição usada. Não alterar o cálculo para fabricar confiança: impedir a entrega quando o suporte é insuficiente.
- Conferência exclusivamente local no SQLite/cache, sem chamadas adicionais às APIs e sem abrir páginas extras do PackBall. Vale também para conversão da fila silenciosa quando a odd chega ao alvo. O bloqueio fica em `gateway:validade_historico`; não há mensagem de funil no canal.
- Hipóteses HT guardadas anteriormente (histórico individual de 50% e chutes recentes) continuam **não aplicadas**. Esta é uma proteção de dados, não a ativação daqueles filtros.
- Rollback isolado: `VALIDADE_HISTORICO_GOLS_ATIVA=0` e recarga controlada. Não apagar resultados antigos ou misturar o antes/depois da nova proteção ao comparar desempenho.
- Verificação: 1.950 testes aprovados. Reprodução somente leitura do sinal 324329 retorna `historico_antigo`, com 14 jogos antigos; teste integrado confirma que chegar à odd-alvo não contorna o bloqueio. Fluxo com histórico atual permanece funcional.
- Ativação: recarga controlada concluída em 02/09/2026 às 11:10 locais, após pré-voo aprovado. Monitor PID 7704 e watchdog PID 6228 com código atualizado, processo vivo e trava própria confirmados; pré-live PID 11500 retomado. Terminal visível e arquivo de sessão do PackBall preservados, sem edição do Scanner.

## Registro de análise de 02/09/2026 — HT/J1, sem mudança de regras

- Análise retrospectiva preservada em [ANALISE_HT_J1_20260902.md](ANALISE_HT_J1_20260902.md), com evidências das 61 entradas enviadas até o sinal 322020.
- Total: 38 greens / 23 reds, ROI +12,99%; desde 31/08: 7 greens / 11 reds, ROI −30,39%. Resultados passados não comprovam vantagem futura.
- Hipóteses não aplicadas: histórico individual HT >=50% retiraria 2 reds e 5 greens; zero chutes na janela recente retiraria 4 reds e 2 greens, em apenas seis casos. Dados ausentes permanecem separados de zero.
- A validação pré-registrada separada de 100 candidatos foi inconclusiva. Preservar a amostra, comparar resultados futuros e não alterar regras/filtros sem nova autorização do usuário.

## Revisão operacional de 01/09/2026 — acompanhamento de odds

- [x] Monitorar odds em silêncio, sem publicar avisos de espera ou resultados
  hipotéticos. Observações não são entregas e não entram no ROI enviado.
- [x] Usar na conversão a cotação recém-confirmada, com a mesma linha, placar,
  período e limites de frescor; manter o gateway operacional antes do envio.
- [x] Alinhar a rechecagem rápida à política de Telegram já habilitada: uma
  rota experimental autorizada não exige promoção artificial à calibração
  oficial. Métodos desativados continuam bloqueados.
- [x] Preservar observação e odd originais e permitir somente uma primeira
  decisão válida vinculada a elas. Duplicatas e alterações retroativas da
  evidência de pesquisa continuam vedadas; backups antigos continuam
  compatíveis e a proteção é migrada ao abrir o banco.
- [x] Integrar a fila silenciosa aos geradores de gols ativos, consultando a
  política de envio atual, sem reativar versões legadas. A análise condicional
  usa o preço-alvo, mas persiste a odd real e não consome a coorte de pesquisa.
  A conversão recalcula o mesmo método no minuto/preço atuais, confere a
  linhagem e respeita a exposição já aberta. HT com mínimo próprio de 1,44
  não é convertido indevidamente em 1,40. Leituras técnicas dos novos métodos
  vencem em 120 segundos sem renovação; consultar preço não renova pressão.
  A fila separa método e linha. Rollback isolado:
  `ACOMPANHAMENTO_METODOS_GOLS_ATIVO=0` e recarga controlada do monitor.
- [x] Verificação: suíte completa de 1.929 testes aprovada; após acrescentar
  os casos de exposição aberta e leitura vencida, 268 testes direcionados
  aprovados. Integração isolada confirmou observação a 1,22, envio a 1,44,
  nenhuma probabilidade calibrada inventada e ROI somente da entrega real.
- [x] Corrigir revogação de análises durante a espera da odd. Uma leitura
  posterior reprovada ou um ciclo técnico novo sem candidato elegível impede
  reutilizar a aprovação anterior. Uma aprovação técnica posterior pode
  retomar a mesma observação silenciosa. A conferência ocorre na fila, antes
  da materialização, no pré-envio e na reserva atômica do Telegram. Snapshots
  apenas de preço/finalização não renovam evidência técnica. Falha reproduzida
  antes da correção; suíte completa de 1.935 testes aprovada, incluindo
  reprovação durante a consulta da API e depois da materialização.
- [ ] Concluir a validação estatística prospectiva dos mercados e definir
  com o usuário o destino de backup fora do computador. A auditoria atual
  não comprovou a conclusão profissional nem vantagem estatística geral.
  Conferência de 01/09 à noite: C:, D: e E: pertencem ao mesmo dispositivo
  físico (`device:7:0`, partições 3, 5 e 6); copiar entre essas unidades não
  resolve a pendência. O SHA-256 do backup local `periodico_20260901_18.db.gz`
  confere com seu manifesto. Falta destino externo autorizado; não copiar
  para D:/E: tratando essas partições como discos independentes.

## Validação operacional de 01/08/2026

- [x] Tornar a contagem da lista Ao Vivo resistente a transições reais. Linhas
  encerradas ou ambíguas são excluídas, uma diferença de uma partida só é
  tolerada na segunda leitura com estado ao vivo explícito, e diferenças maiores
  continuam fechando o ciclo. Estados não reconhecidos são diagnosticados sem
  acessar credenciais. A suíte completa passou a 890 testes.
- [x] Validar a alteração em produção após reinício controlado. Dois ciclos
  consecutivos fecharam em 39/39 partidas; o segundo registrou API saudável,
  zero falhas de rede e nenhum bloqueio de fonte. Novos candidatos preservaram
  PackBall e API-Football em `features_json` e ficaram pendentes até resultado
  real, sem alterar antecipadamente Green/Red.
- [x] Corrigir o minuto com acréscimos entre parênteses observado em produção
  (`94(5) '`, `48(2) '`, `96(9) '`). O extrator e o diagnóstico compartilham o
  mesmo formato, enquanto partidas explicitamente interrompidas permanecem
  fora. Após reinício controlado, os ciclos fecharam em 36/36 e 34/34, com API
  saudável e zero bloqueios no segundo. A suíte passou a 891 testes.
- [x] Separar, na auditoria, a fila Telegram atual do histórico de transições.
  Intenções `enviando` que possuem uma prova posterior `entregue` deixaram de
  parecer pendentes, sem apagar nenhuma evidência. A fila real ficou sem envios
  presos e a suíte completa passou a 892 testes.
- [x] Integrar a cadeia completa do Telegram ao estado geral da auditoria.
  Transições `enviando` já encerradas aparecem como superadas, enquanto uma
  entrega realmente incerta, confirmação inválida, erro persistente ou aviso
  ausente passa a reprovar `saudavel`. Em 02/08/2026, os oito registros
  históricos eram transições superadas e havia zero envio incerto.
- [x] Separar snapshots de finalização sem estatísticas de falhas reais da
  coleta ao vivo. Os quatro casos recentes eram confirmações finais pela API,
  não geraram candidatos, e a métrica correta mostrou zero leituras ao vivo sem
  estatísticas nas últimas 24 horas. A suíte passou a 893 testes.
- [x] Separar decisões internas `gateway:*` das entregas Telegram. A fila real
  passou a mostrar somente 735 entregas confirmadas; um bloqueio preventivo e
  129 filtros permanecem preservados em `decisoes_gateway`, sem parecer falha
  de comunicação.
- [x] Criar contador efetivo da aba Ao Vivo para descontar somente partidas
  explicitamente interrompidas. O contador bruto permanece auditável, estados
  ambíguos continuam bloqueados e múltiplas interrupções não derrubam toda a
  coleta. A suíte passou a 894 testes; após reinício, o primeiro ciclo normal
  fechou em 34/34, com API saudável e nenhum bloqueio.

## Objetivo

Transformar o monitor atual em um sistema profissional, resiliente e mensurável
de análise de partidas ao vivo. O PackBall permanece como fonte principal e a
API-Football funciona como confirmação complementar quando houver cobertura.

O sistema não deve tratar pontuação técnica como probabilidade real antes de
existirem histórico suficiente, backtest e calibração.

## Estado atual

- [x] Reconciliar a corrida entre contador Ao Vivo e cartoes encerrados: uma
  linha so entra quando comprova minuto, intervalo ou rotulo live, mesmo
  enquanto a SPA ainda mantem cartoes encerrados/ambiguos visiveis. Qualquer
  diferenca restante continua fail-closed.
- [x] Tratar entrada/saida concorrente de exatamente uma partida como
  transicao dinamica somente apos a segunda leitura e com todos os cartoes em
  estado ao vivo explicito. Diferencas maiores continuam bloqueando o ciclo e
  o diagnostico preserva contador, extraidos e diferenca tolerada.

- [x] Expiracao da sessao PackBall auditada preventivamente pelo watchdog:
  aviso unico nas ultimas 48 horas, confirmacao apos renovacao e nenhuma
  exposicao de token ou senha. O modulo de sessao integra a assinatura
  transitiva do watchdog; suite completa com 887 testes.

- [x] Login automático no PackBall
- [x] Navegador visível e sessão persistente
- [x] Entrada automática na aba Ao Vivo
- [x] Coleta de placar, minuto e equipes
- [x] Coleta de pressão, chutes, ataques, posse e escanteios
- [x] Coleta de odds ao vivo de gols e escanteios
- [x] Histórico temporário de 5, 10 e 15 minutos
- [x] API-Football como confirmação opcional
- [x] Enriquecer em modo sombra com forma, H2H, escalações, desfalques,
  temporada, previsão, classificação, histórico detalhado de gols/chutes/
  escanteios/xG, estatísticas e jogadores ao vivo
- [x] Compactar os dados avançados nos snapshots e manter os payloads completos
  somente no cache com TTL por tipo
- [x] Pré-registrar e medir por mercado as hipóteses de xG, volume ofensivo e
  histórico de gols/escanteios sem alterar automaticamente os sinais
- [x] Agrupar em uma chamada até 20 fixtures PackBall associadas e reutilizar
  eventos, escalações, estatísticas e jogadores incorporados pela API,
  preservando fallback isolado e telemetria de cobertura
- [x] Cache e limites de consumo da API
- [x] Não consultar a lista ao vivo da API quando o PackBall estiver sem jogos
- [x] Respeitar franquia de 7.500 requisições por dia, com reserva de 500
- [x] Contabilizar tentativas da API mesmo quando a resposta falha
- [x] Validar e manter cópia recuperável do contador da API, bloqueando novas
  chamadas em vez de assumir zero quando nenhum estado for confiável
- [x] Avisar o administrador uma única vez em 80%, 95% e 100% do teto seguro
  diário da API sem gastar requisições adicionais
- [x] Jogos sem cobertura da API continuam pelo PackBall
- [x] Persistência temporal após reiniciar o programa
- [ ] Motor de sinais validado
- [ ] Alertas automáticos profissionais
  - Auditoria de 31/08/2026: entrega de teste e política compacta estão prontas,
    com 762 provas por `message_id`, zero envio incerto e zero resultado sem
    aviso. A rota oficial permanece corretamente em `pendente_evidencia_real`:
    há 494 sinais aprovados no canal experimental, mas ainda nenhum método
    calibrado elegível; promoção retroativa continua proibida.

## Fase 1 — Banco de dados e histórico persistente

- [x] Criar banco SQLite
- [x] Criar tabelas de partidas, snapshots, odds, eventos, sinais e resultados
- [x] Vincular cada resultado ao snapshot e à fonte exata da liquidação
- [x] Migrar ou importar os registros úteis do JSONL
- [x] Impedir duplicidade de snapshots
- [x] Restaurar histórico de 5/10/15 minutos após reinicialização
- [x] Criar retenção e limpeza controlada de dados antigos
- [x] Manter índices persistentes para finalização, grupos independentes e
  vínculo sinal/snapshot, evitando índices automáticos temporários com o
  crescimento do histórico
- [x] Preservar sinais aprovados e resultados durante a retenção
- [x] Rotacionar logs e JSONL com cópias recuperáveis
- [x] Registrar versão/origem de cada dado: PackBall ou API-Football

Critério de conclusão: reiniciar o monitor sem perder a evolução temporal e
consultar rapidamente o histórico completo de qualquer partida.

## Fase 2 — Arquitetura modular

- [x] Separar coletor PackBall
- [x] Separar coletor de odds
- [x] Manter API-Football isolada
- [x] Criar módulo de banco de dados
- [x] Criar módulo de evolução temporal
- [x] Criar módulo de sinais
- [x] Criar módulo Telegram
- [x] Manter um monitor principal pequeno e coordenador

Critério de conclusão: alterações em um coletor não quebram os demais módulos.

## Fase 3 — Qualidade e normalização dos dados

- [x] Normalizar nomes de equipes
- [x] Normalizar ligas
- [x] Normalizar mercados e estruturar linhas/odds
- [x] Associar IDs estáveis do PackBall e da API
- [x] Repetir uma vez a leitura quando o contador Ao Vivo divergir das linhas
  extraÃ­das e, se a diferenÃ§a persistir, fechar o ciclo inteiro sem sinal,
  liquidaÃ§Ã£o, retry ou alteraÃ§Ã£o de Green/Red
- [x] Pausar por 15 minutos, sem novas navegaÃ§Ãµes, quando trÃªs ciclos
  consecutivos nÃ£o conseguirem validar botÃ£o, linhas ou fallback Ao Vivo
- [x] Validar a expiraÃ§Ã£o do `packballBearer` sem expor seu valor, renovar a
  sessÃ£o uma Ãºnica vez apÃ³s a pausa e bloquear novas tentativas se o login
  falhar
- [x] Comprovar a retomada pelo Agendador do Windows a cada cinco minutos,
  sem furar o circuit breaker ou mascarar outras falhas de coleta
- [x] Sincronizar apÃ³s ciclo saudÃ¡vel o bearer renovado em memÃ³ria, aceitando
  somente JWT vÃ¡lido e mais novo, com substituiÃ§Ã£o atÃ´mica e log sem segredo
- [x] Comparar minuto e placar entre fontes
- [x] Validar nomes, orientação, placar e minuto antes de associar a API
- [x] Exigir também categoria compatível nos dois times antes da associação:
  feminino e faixas U15–U23 não podem ser confundidos com equipes principais,
  preservando aliases seguros dentro da mesma categoria
- [x] Impedir reutilização do mesmo fixture em duas partidas no mesmo ciclo
- [x] Persistir e respeitar a orientação da API também no fechamento
- [x] Medir idade/atraso de cada dado
- [x] Marcar campos ausentes ou inconsistentes
- [x] Criar pontuação de qualidade dos dados
- [x] Bloquear análise quando houver divergência crítica

Critério de conclusão: cada snapshot informa origem, completude, atraso e
confiabilidade técnica dos dados.

## Fase 4 — Evolução temporal profissional

- [x] Calcular deltas de chutes e escanteios em 5/10/15 minutos
- [x] Calcular média, pico e tendência da pressão
- [x] Medir minutos de domínio de cada equipe
- [x] Detectar aceleração e desaceleração ofensiva
- [x] Detectar mudanças após gol, cartão vermelho ou intervalo
- [x] Separar primeiro e segundo tempo
- [x] Tratar reinício/reset de estatísticas da fonte
- [x] Persistir em cada candidato um vetor versionado com chutes, escanteios,
  pressão, domínio e taxas medidas nas janelas de 5/10/15 minutos
- [x] Versionar o vetor temporal como v2 com taxas separadas por equipe e
  validação matemática entre contadores, totais, duração e taxas derivadas

Critério de conclusão: as tendências continuam corretas mesmo quando pressão
oscila ou o site redefine algum contador.

## Fase 5 — Coleta eficiente e operação contínua

- [x] Priorizar candidatos antes de abrir páginas detalhadas
- [x] Medir no watchdog episódios e duração acumulada da perda de prioridade
  do Scanner, mantendo a lista Ao Vivo como cobertura segura. A auditoria de
  31/08/2026 confirmou 33 ciclos observados, dois episódios históricos e
  311 segundos no total; o Scanner terminou saudável e novamente prioritário.
  A validação integral posterior aprovou 1.816 testes sem regressões.
- [x] Evitar reabrir odds sem atividade suficiente usando cache rastreável
- [x] Preservar o horário original das odds em cache e bloquear preço com mais
  de seis minutos
- [x] Repetir cedo a coleta de odds quando a atualização falhar
- [x] Medir duração real de cada ciclo
- [x] Definir filas rápidas e lentas de atualização
- [x] Ordenar a fila por urgência relativa e priorizar jogos nunca processados,
  evitando que partidas lentas fiquem indefinidamente sem coleta
- [x] Reservar tempo do ciclo para finalização e adiar o excedente sem marcar a
  tarefa como concluída ou remover o jogo do PackBall
- [x] Evitar iniciar a última coleta quando o percentil 90 das durações reais,
  acrescido de margem, já não cabe no orçamento; preservar ao menos uma tarefa
  por ciclo e auditar cada interrupção pela reserva adaptativa
- [x] Restaurar após reinício as últimas durações reais usadas pela reserva
  adaptativa, com compatibilidade conservadora para logs antigos que possuíam
  apenas o percentil 95, sem alterar a fila nem a frequência do PackBall
- [x] Reabrir páginas travadas
- [x] Repetir a navegação da lista após falha transitória ao clicar/evaluar a
  aba Ao Vivo e preservar o erro diagnóstico se a segunda tentativa falhar
- [x] Usar os status comprovadamente ao vivo das linhas como fallback quando o
  contador da aba desaparecer, sem confundir página quebrada com zero jogos
- [x] Renovar sessão automaticamente
- [x] Reiniciar navegador após falhas consecutivas
- [x] Reiniciar o processo do monitor após encerramento inesperado
- [x] Persistir a tentativa de inicialização e recuperar processo que falhe
  antes de registrar estado ativo, inclusive com estado ausente ou ilegível
- [x] Impedir duas instâncias simultâneas com trava do sistema operacional
- [x] Impedir também duas instâncias simultâneas do watchdog
- [x] Registrar PID do watchdog e recuperar seu laço após exceção transitória
- [x] Verificar PIDs no Windows sem enviar sinal ao processo
- [x] Detectar ausência de internet
- [x] Continuar do último estado após reinício
- [x] Criar iniciador único e idempotente para monitor e watchdog
- [x] Preparar tarefa idempotente e removível do Windows para recuperar os dois
  processos em até cinco minutos, preservando o monitor visível
- [x] Instalar e validar a tarefa automática no Windows com autorização do
  usuário
- [x] Permitir que a autorrecuperação trate `coleta_parada` como motivo para
  reiniciar, sem dispensar os demais controles do pré-voo, e registrar quais
  verificações recusaram cada tentativa
- [x] Impedir que uma tentativa agendada recusada por falha real de pré-voo
  apareça no painel como recuperação saudável
- [x] Evitar alerta falso do watchdog durante partida a frio do monitor
- [x] Finalizar pelo PackBall partidas que saíram da aba Ao Vivo
- [x] Recuperar snapshots de partidas que somem cedo da lista sem fingir status
  final
- [x] Usar a API para complementar resultados quando houver cobertura
- [x] Revalidar times e orientação da fixture API no fechamento, sem confiar
  apenas no ID persistido, e auditar retroativamente essa correspondência
- [x] Rejeitar pareamento API ambíguo quando as duas melhores fixtures ficam
  separadas por menos de três pontos percentuais de similaridade
- [x] Persistir e exibir por ciclo o motivo de cada pareamento API aceito ou
  recusado, separando ausência, nomes, placar, minuto e ambiguidade
- [x] Formar linha de base própria do pareamento API e alertar queda relativa,
  erros repetidos ou ambiguidade excessiva sem exigir cobertura universal
- [x] Persistir tentativas, estados observados e erros de finalização
- [x] Isolar falhas parciais de estatísticas e odds, preservando dados válidos
  e registrando o fallback usado
- [x] Preservar cooldown de consultas de resultado após reinicialização
- [x] Não converter estatística final ausente em devolução
- [x] Liquidar gol HT somente com placar válido do primeiro tempo
- [x] Separar o resultado dos 90 minutos de prorrogação e pênaltis, usando
  `score.fulltime` da API ou o snapshot PackBall anterior ao `BREAK`
- [x] Ignorar gols e escanteios da prorrogação nos mercados regulamentares;
  manter pendente quando não existir evidência segura do corte
- [x] Liquidar diretamente pelo snapshot regulamentar persistido, sem depender
  de nova abertura da página durante a prorrogação
- [x] Encerrar pendências irrecuperáveis como `sem_dado` sem contaminar métricas
- [x] Encerrar como `sem_dado` pendências sem estado final após 72 horas e
  seis tentativas em todas as fontes esperadas, sem presumir green ou red
- [x] Tolerar respostas vazias, inválidas ou de outro fixture na finalização
  pela API, registrando aviso e cooldown sem derrubar o ciclo
- [x] Restaurar do SQLite os relógios de coleta e odds após reinício, mantendo
  a idade original do cache e evitando uma rajada artificial de todos os jogos
- [x] Persistir no SQLite o cache da API-Football por endpoint, conservando os
  mesmos TTLs após reinício e descartando respostas expiradas, corrompidas ou
  com relógio futuro antes que possam influenciar a coleta
- [x] Reconciliar o consumo local com os cabeçalhos oficiais de cota diária e
  por minuto, contabilizando chamadas externas sem reduzir o total conservador
  e usando a virada oficial do dia em UTC
- [x] Tratar como reconciliação normal, por até cinco minutos, uma calibração
  inativa que ficou um resultado atrás entre ciclos, evitando aviso transitório
  no Telegram sem relaxar o bloqueio de modelos oficiais ativos
- [x] Auditar no pré-voo a integridade dos modelos de pontuação em sombra,
  incluindo o challenger com contexto API, e recusar reinício quando o hash,
  a versão, o mercado ou o conjunto de features de um modelo congelado
  estiverem incompatíveis; ausência de modelo durante a formação da amostra
  continua sendo um estado válido

Critério de conclusão: funcionamento prolongado sem intervenção e sem ciclos
presos em botões ocultos ou páginas quebradas.

## Fase 6 — Motor de sinais

- [x] Criar regras independentes para gol FT, gol HT e próximo gol
- [x] Criar regras independentes para over e próximo escanteio
- [x] Pré-registrar um challenger temporal V2 independente, com janelas
  completas de 5/10/15 minutos, 60 resultados futuros para treino e os 30
  seguintes para validação fixa, sem alterar automaticamente a regra ativa
- [ ] Mapear no PackBall as linhas asiáticas de escanteios do 1º e 2º tempo
  sem confundir o mercado `Exactly` de três opções com o asiático de duas opções
  - Auditoria integral em 28/07/2026: 104.503 registros de odds foram
    verificados no SQLite. Foram encontradas 2.400 ofertas `Exactly` de 1º
    tempo e 2.477 de 2º tempo, todas com três opções; nenhuma ocorrência bruta
    de `Asian/Asiático` por tempo foi encontrada. Portanto, a lacuna atual é
    da fonte e não do parser. A V6 foi mantida intacta para preservar sua
    linhagem e sua amostra prospectiva.
- [x] Integrar como complemento o bet ao vivo 51 `Asian Corners (1st Half)` da
  API-Football, com cache global de cinco minutos, associação por fixture,
  proveniência e bloqueio de ofertas suspensas, incompletas ou vencidas
- [x] Usar também o bet 32 `Asian Corners` como fallback FT somente quando o
  PackBall não trouxer uma linha total válida de duas opções, com cache isolado
  do 1º tempo e a mesma validação fail-safe
- [x] Separar telemetria dos bets 32/51 e distinguir oferta global, fixture
  correspondente, oferta anexada e oferta rejeitada, identificando se a falta
  de amostra vem da fonte, do pareamento ou da validade da linha
- [x] Persistir o motivo exato de cada rejeição dos bets 32/51 e falhar fechado
  também para estados bloqueados, interrompidos ou finalizados dentro de `status`
- [ ] Encontrar uma fonte real de duas opções para escanteios asiáticos do 2º
  tempo; o catálogo API-Football auditado em 21/07/2026 oferece apenas o mercado
  de três opções, que permanece corretamente excluído
  - Nova auditoria em 30/07/2026: TotalCorner documenta linha de escanteios FT
    e de primeiro tempo, mas não comprova uma linha asiática exclusiva do 2º
    tempo; a API exige VIP e limita 30 requisições/minuto. AnySport documenta
    `Corners Asian Handicap (1st Half)`, porém para o 2º tempo lista somente o
    mercado de três opções; odds ao vivo exigem o plano Pro de 199 USDT/mês.
    Soccer Football Info também documenta apenas FT e 1º tempo. Nenhuma dessas
    opções fecha a lacuna de 2T, portanto não houve compra nem integração
    especulativa.
  - O TotalCorner tornou-se candidato somente para suprir 1T: a documentação
    lista `cornerLineHalf` e `cornerHalfList`, e a assinatura Advanced custa
    28 euros/30 dias ou 5 euros/1 dia. Também oferece um dia de VIP por
    verificação telefônica. Antes de criar adaptador, exigir uma resposta JSON
    real ao vivo que prove linha, Over, Under, horário e cobertura; documentação
    com o exemplo de `corner_half_list` omitido não é evidência suficiente.
  - Nova auditoria integral em 09/09/2026: 251.685 odds ao vivo confirmam
    20.917 estruturas asiáticas FT, mas zero em 1T e 2T. O 1T contém 9.163
    ocorrências `Exactly`; o 2T contém 9.464, todas corretamente excluídas.
    O bet 32 acumulou 7.249 consultas e 12.498 ofertas FT anexadas; o bet 51
    acumulou 222 consultas e nenhuma oferta 1T. Assim, a ausência por tempo
    continua sendo da fonte, não do normalizador.
  - A tabela oficial de cobertura LSports lista `2nd Half Corners Over/Under`
    em prematch, in-play e settlement. Foi criado o diagnóstico offline
    `diagnostico_lsports_escanteios_2t.py`, que exige fixture, liga, dois times,
    período explícito no nome, market/provider/bet IDs, Over e Under na mesma
    linha/base, odds decimais, status ativos documentados, timestamps com fuso
    e liquidação correspondente. O cabeçalho temporal também é obrigatório,
    atualizações acima de 15 minutos são recusadas e settlement precisa usar o
    tipo oficial 35 e ser posterior ao snapshot. `Exactly`, mercado FT apenas
    visto durante o 2T, IDs divergentes e enums não documentados falham
    fechados. A amostra e a origem escrita dos enums recebem fingerprints
    SHA-256; o payload bruto e o texto da origem não são copiados ao relatório.
    O relatório nunca ativa a fonte e só considera possível o próximo estágio
    em sombra após oferta e liquidação reais do mesmo contrato. Os 12 testes
    dirigidos e a suíte integral de 2.317 testes passaram em 09/09/2026. O item
    permanece aberto até chegar uma amostra/trial real e o mapeamento escrito
    dos enums.
- [x] Preparar um adaptador isolado para a página pública da Bet365, com
  pareamento exato de times e validação fail-safe de Over/Under, período, linha,
  odd, suspensão, duplicidade e rejeição de `Exactly`; manter a fonte desligada
  até o painel real de mercados carregar e fornecer evidência persistível
- [x] Criar telemetria SQLite genérica para fontes de odds complementares,
  registrando tentativa, evento, times, período, mercado, rejeição, oferta, URL
  e horário; incluir a Bet365 no painel mesmo enquanto permanece desligada
- [x] Criar diagnóstico Bet365 controlado por partida, limitado a uma aba, uma
  lista e um evento, sem login/aposta; exigir nomes exatos, registrar
  jogo ausente/ambíguo, bloqueio, carregamento ou mercado candidato e nunca
  promover texto ainda não mapeado a oferta válida
- [x] Confirmar os dois times no painel após o clique e classificar URL de
  evento com conteúdo antigo como painel não carregado, sem fingir que o
  mercado de escanteios está ausente
- [x] Auditar a integridade persistida da fonte Bet365 e expor no painel
  estados, motivos, corrupção, inconsistências e comprovação real separada de
  simples tentativas
- [x] Permitir captura manual auditável da Bet365 com partida PackBall, evento,
  URL, período, linha, duas odds, imagem preservada, SHA-256 e método de coleta,
  mantendo a fonte desligada do monitor
- [x] Gerar fila manual idempotente apenas quando o candidato de escanteios
  1T/2T passou em todos os critérios e depende exclusivamente da odd, com
  validade curta e resolução automática após evidência Bet365 posterior
- [x] Auditar automaticamente catálogo, consultas, ofertas anexadas e mercados
  `Exactly`, mantendo 1T/2T bloqueados até existir uma oferta real de duas
  opções persistida
- [x] Separar e tipar as linhas `Exactly` de escanteios do total, 1º e 2º tempo
  para que nunca sejam usadas como linha asiática de duas opções
- [x] Separar odds, regras, liquidação e amostras de escanteios do 1º e 2º tempo
  e exigir calibração independente antes de liberar cada mercado
- [x] Incorporar minuto, placar, tendência e movimentação da odd
- [x] Exigir odd ao vivo estruturada e dentro da faixa antes de aprovar
- [x] Versionar a mudança como `sinais-v2` sem misturar amostra v1
- [x] Versionar como `sinais-v3` a correção das janelas temporais e a exigência
  de atividade ofensiva recente, sem misturar amostras v1/v2
- [x] Versionar como `sinais-v4` a padronização dos mercados Over para exatamente
  mais um evento com vitória integral, sem misturar a amostra v3
- [x] Vincular criptograficamente cada `regra_versao` à lógica de decisão,
  versão das features e faixa de odds; bloquear inicialização, calibração e
  pré-voo se o código mudar sem criar uma nova versão da regra
- [x] Identificar nominalmente o componente divergente da linhagem e garantir
  por teste que as assinaturas do monitor/watchdog fechem todos os imports locais
- [x] Ancorar a primeira adoção de cada versão e bloquear definitivamente a
  readoção silenciosa se o vínculo for apagado depois da inicialização
- [x] Gravar o fingerprint em cada novo sinal e restringir a calibração oficial
  v7 às observações com linhagem comprovada, preservando o legado apenas para
  pesquisa/simulação sem preencher hashes retroativamente
- [x] Tornar `regra_versao` e `regra_fingerprint` imutáveis por gatilho do
  próprio SQLite; impedir inclusive um `UPDATE` manual que tente promover um
  sinal legado à população oficial, e exigir o gatilho no pré-voo e nos backups
- [x] Chavear marcos 30/100 e transições da calibração pela população oficial
  de cada mercado (regra + fingerprint + marco), sem repetir avisos quando
  muda somente a política estatística e reiniciando apenas o mercado cuja
  definição amostral realmente mudou
- [x] Exigir qualidade mínima dos dados
- [x] Impedir sinais duplicados
- [x] Limitar também alertas oficiais a uma entrada independente por partida,
  mercado e versão, igualando entrega, backtest e calibração
- [x] Criar pontuação técnica de 0 a 100
- [x] Não chamar pontuação de probabilidade antes da calibração
- [x] Auditar a discriminação da nota por AUC na validação cronológica e impedir
  ativação quando a pontuação não ordenar risco melhor que o acaso, incluindo
  intervalo de confiança para não aprovar oscilação de amostra pequena
- [x] Exigir ordem comprovada para liquidar mercados de próximo gol

Critério de conclusão: cada sinal contém mercado, odd, motivos objetivos,
qualidade dos dados e regra/versionamento usados.

## Fase 7 — Backtest e calibração

- [x] Registrar todo candidato, inclusive os rejeitados
- [x] Congelar uma pontuação candidata logística por mercado em modo sombra,
  com modelo e marco imutáveis no SQLite; treinar somente no histórico
  disponível no registro e avaliar exclusivamente sinais posteriores, sem
  alterar V6/V7, filtros, calibração ou alertas automaticamente
- [x] Endurecer a avaliação da pontuação candidata para impedir revisão baseada
  apenas em AUC: além de discriminar e superar a nota atual, a probabilidade
  precisa ter Brier não pior que a odd. A política de avaliação foi versionada
  como `avaliacao-pontuacao-sombra-janela-fixa-v2`, sem alterar o modelo, a
  âncora ou a janela futura congelada.
- [x] Separar a versão da política de avaliação do fingerprint do modelo
  congelado e fixar o hash compatível em teste de regressão. A prova no banco
  real preservou os modelos de Gol FT e Próximo Gol; o painel passou a expor
  Brier candidata/odd. A suíte completa passou a 901 testes.
- [x] Tornar a decisão dos challengers totalmente explicável no painel. Score
  simples, contexto API e temporal 5/10/15 agora exibem AUC candidata/atual,
  limite inferior AUC95 e Brier candidata/odd. A prova real mostrou que o
  contextual de Gol FT em 28/30 tem AUC 0,5867 e Brier ligeiramente melhor,
  porém limite inferior AUC95 de apenas 0,373; portanto continua corretamente
  bloqueado e sem promoção automática.
- [x] Ampliar a prova de janela fixa dos challengers. Além do fingerprint e da
  AUC, os testes agora congelam explicitamente Brier e estado após os primeiros
  30 resultados futuros nos modelos simples, contextual e temporal 5/10/15.
  O 31º resultado não pode transformar retrospectivamente uma conclusão.
- [x] Tornar notificações operacionais incertas identificáveis sem persistir o
  texto completo. Novos registros guardam somente a primeira linha redigida,
  exibida pela ferramenta de reconciliação; tokens, chaves, senhas e o corpo da
  mensagem não entram no resumo. O histórico antigo foi preservado e a suíte
  completa passou a 902 testes.
- [x] Preparar um challenger contextual separado que combina as features ao
  vivo com forma, H2H, temporada, histórico detalhado, xG, estatísticas live,
  escalações, desfalques e consenso de odds pré-jogo da API V4; exigir 60
  resultados independentes (mínimo de 15 por classe), congelar o modelo no
  SQLite e avaliar somente os 30 resultados posteriores, sem aplicação
  automática
- [x] Fixar a validação dos dois modelos de pontuação nos primeiros 30
  resultados posteriores à âncora, com fingerprint próprio, impedindo
  reavaliação oportunista com o 31º resultado ou seguintes
- [x] Registrar resultado final e retorno hipotético
- [x] Impedir green provisório em totais antes do encerramento do período,
  reabrir liquidações históricas prematuras e notificar correções
- [x] Tornar liquidações imutáveis no SQLite e permitir reabertura somente após
  revisão coerente com todos os valores, snapshot e fonte anteriores; preservar
  a evidência da revisão contra alteração ou exclusão
- [x] Liquidar corretamente linhas asiáticas inteiras e de quarto
- [x] Calcular acerto, yield, ROI, drawdown e sequência de perdas
- [x] Calcular intervalo de confiança de 95% para a taxa de acerto
- [x] Classificar amostras como inconclusivas, pré-validação ou validáveis
- [x] Avaliar por liga, mercado, minuto e faixa de odd
- [x] Preparar dataset temporal versionado, independente por partida/mercado,
  com fingerprint e separação cronológica sem substituir a primeira decisão
  por um candidato posterior
- [x] Pré-registrar comparação sombra das variáveis 5/10/15, definindo direção
  somente no desenvolvimento e calculando AUC apenas na validação posterior
- [x] Calibrar por célula de nota técnica e faixa de odd
- [x] Exigir ROI positivo da célula na validação cronológica
- [x] Separar dados de desenvolvimento e validação
- [x] Evitar ajuste excessivo com validação cronológica posterior
- [x] Usar uma unidade amostral independente por partida na calibração
- [x] Usar também partidas independentes nas métricas públicas
- [x] Calibrar somente a população elegível pela mesma faixa de odds do Telegram
- [x] Separar no progresso a amostra resolvida, a amostra incorporada ao modelo
  e os sinais pendentes, sem contar entradas abertas na meta de 100
- [x] Aplicar o menor Wilson entre desenvolvimento e validação à confiança
  exibida
- [x] Recusar modelo incompleto ou incoerente sem fallback para taxa bruta
- [x] Congelar o modelo oficial nos primeiros 100 resultados independentes e
  reservar até as 300 partidas mais recentes somente para monitoramento de
  drift, sem permitir que elas retreinem ou reabram a decisão
- [x] Detectar drift em janela recente de 30 partidas
- [x] Preservar no SQLite cada avaliação nova de drift por mercado e resultado,
  com deduplicação, índice, resumo operacional e gatilhos de imutabilidade
- [x] Exigir continuidade e coerência desse histórico na prontidão profissional,
  bloqueando liberação oficial diante de chave ausente ou métrica divergente
- [x] Desativar automaticamente modelo com queda significativa e ROI negativo
- [x] Detectar calibração ativa atrasada em relação à amostra/último resultado
- [x] Detectar também calibração ainda inativa atrasada e reconciliá-la no
  ciclo seguinte sem regravar modelos já atuais, protegendo a transição
  automática de 99 para 100 resultados contra falha entre liquidação e
  recalibração
- [x] Bloquear no próprio calibrador o uso de modelo ativo desatualizado, mesmo
  antes do alerta do watchdog
- [x] Vincular cada modelo a um fingerprint SHA-256 da amostra independente,
  detectando revisão de resultado mesmo sem mudança na quantidade ou horário
- [x] Preservar um histórico imutável de cada versão efetiva da calibração,
  com hash SHA-256 e deduplicação de recalibrações idênticas
- [x] Impor a imutabilidade do histórico também por gatilhos SQLite e exigir
  essas garantias estruturais no pré-voo e em todo backup restaurável
- [x] Exigir no motor e na auditoria que a calibração atual corresponda
  exatamente a uma versão imutável por mercado, regra, amostra, estado, hash e
  JSON canônico; qualquer divergência bloqueia o sinal oficial
- [x] Produzir aos 30–99 resultados um diagnóstico sombra cronológico de AUC,
  ROI e células observadas, explicitamente incapaz de ativar sinais oficiais
- [x] Exigir no diagnóstico temporal sombra o mesmo fingerprint da população
  oficial, excluindo registros legados para impedir seleção de cortes por outra
  linhagem
- [x] Separar no relatório resultados brutos da amostra independente realmente
  usada pelo calibrador, incluindo acerto, ROI, IC95 e AUC próprios para cada
  população; calcular a meta somente pela segunda e falhar fechado diante de
  divergência com a prontidão
- [ ] Calibrar faixas de confiança com resultados reais
- [x] Desativar alertas de regras sem amostra ou desempenho suficiente
- [x] Isolar repetições do mesmo sinal aberto para não inflar a amostra

Critério de conclusão: qualquer percentual exibido corresponde ao desempenho
observado fora da amostra usada para criar a regra.

## Fase 8 — Telegram profissional

- [x] Enviar somente sinais aprovados e calibrados
- [x] Manter simulações pré-calibração claramente rotuladas, limitadas e
  contabilizadas separadamente dos alertas oficiais
- [x] Limitar Telegram de teste a uma simulação por partida, mercado e versão,
  preservando o teto diário para experimentos independentes
- [x] Separar a cota diária de simulações por regra e manter teto global entre
  versões, evitando que uma regra antiga bloqueie o teste da versão ativa
- [x] Exigir que a simulação seja a primeira decisão independente da
  partida/mercado/regra e excluir leituras posteriores das métricas históricas
- [x] Liquidar simulações sem inflar a amostra oficial e notificar seu resultado
  no Telegram de forma idempotente
- [x] Comparar o filtro das melhores simulações com a coorte descartada usando
  amostras independentes, intervalo de 95% para acerto/ROI e decisão
  conservadora sem aplicação automática
- [x] Versionar como `filtro-simulacoes-v2` o registro prospectivo de todos os
  descartes comparáveis da mesma leitura, mesmo quando outro mercado foi
  escolhido para o Telegram; proibir backfill após conhecer o resultado
- [x] Vincular o experimento do filtro ao fingerprint exato da regra ativa,
  excluir o legado das duas coortes e degradar a validação se uma decisão nova
  aparecer fora dessa linhagem
- [x] Separar na prontidão profissional a integridade técnica do experimento da
  evidência estatística do filtro; exigir 30 resultados resolvidos em cada
  coorte e vantagem favorável com IC95 antes de chamar o filtro de pronto
- [x] Supervisionar automaticamente a conclusão do experimento e notificar uma
  única vez quando a amostra ficar avaliável ou quando a decisão mudar entre
  vantagem comprovada e não comprovada, sem alterar limites automaticamente
- [x] Expor na prontidão de cada mercado o corte temporal escolhido apenas no
  desenvolvimento e seu resultado na validação futura, mantendo o mercado
  pendente quando o corte não comprovar vantagem fora da amostra
- [x] Expor acerto, IC95, ROI, lucro e AUC da amostra oficial ainda não
  calibrada, distinguindo desempenho preliminar positivo de desempenho
  desfavorável sem liberar sinais antes do gate completo
- [x] Separar `pendente_amostra` de `reprovado_validacao` e preservar ROI, AUC,
  limite inferior de AUC95, erro e células da validação cronológica final no
  watchdog, status, prontidão e alerta de ativação
- [x] Separar canais de gols e escanteios
- [x] Incluir partida, minuto, placar, mercado e odd
- [x] Incluir no resultado o placar e status da liquidação, a fonte que
  confirmou o green/red e o horário da confirmação
- [x] Mostrar motivos e qualidade dos dados
- [x] Traduzir códigos internos de motivos, mercados, status e fontes para
  linguagem clara em entradas, resultados e correções
- [x] Vincular oportunidades, resultados e pendências do resumo diário ao
  fingerprint oficial atual, excluindo legado mesmo com a mesma versão nominal
- [x] Alertar quando confiança for insuficiente sem indicar entrada
- [x] Atualizar/cancelar sinal quando ocorrer evento invalidante
- [x] Registrar entrega e impedir duplicidade
- [x] Exigir `message_id` na confirmação de todas as mensagens de sinal,
  persistir prova sanitizada e imutável por destino e detectar confirmação
  inválida ou reutilizada sem reclassificar o histórico legado
- [x] Reenviar falhas temporárias com fila persistente e tentativas limitadas
- [x] Expirar alertas antigos e não reenviar sinais já resolvidos
- [x] Revalidar no gateway do Telegram o sinal persistido e a calibração atual
  antes de toda entrega oficial, inclusive retries; mudança ou desativação
  cancela o envio em vez de reutilizar probabilidade antiga
- [x] Persistir bloqueios do gateway e incluí-los na auditoria contínua da
  integridade Telegram
- [x] Revalidar no gateway e em todo retry o fingerprint persistido do sinal
  contra a linhagem atual; legado, ausência ou divergência bloqueiam a entrega
- [x] Persistir a intenção antes da chamada externa e marcar retries como
  `tentando`, impedindo reenvio cego após crash entre a confirmação do Telegram
  e o registro local; estados incertos são alertados pelo watchdog
- [x] Bloquear qualquer nova exposição oficial enquanto existir outra entrega
  oficial em `enviando` ou `tentando`; permitir somente o retry controlado do
  próprio sinal e manter simulações independentes desse disjuntor
- [x] Classificar timeout ou resposta inválida durante envio oficial como
  `incerto`, sem retry automático; incluir o estado imediatamente no watchdog e
  na reconciliação manual, preservando o erro original e a intenção de envio
- [x] Fornecer reconciliação manual auditável para confirmar uma entrega
  incerta ou devolvê-la à fila somente após conferir o Telegram, sem editar o
  SQLite diretamente nem enviar mensagem pela ferramenta
- [x] Incluir avisos de risco e maioridade

Critério de conclusão: todo alerta é rastreável até o snapshot e a regra que o
geraram.

## Fase 9 — Observabilidade, testes e segurança

- [x] Registrar batimentos durante ciclos longos e fazer o watchdog distinguir
  progresso recente de coleta realmente travada, sem mascarar batimento vencido
  ou falha posterior
- [x] Auditar automaticamente a prontidão profissional por componente,
  separando saúde operacional, calibração por mercado, provas Telegram,
  fontes asiáticas e recuperação do Windows sem liberar sinais por engano

- [x] Logs estruturados e resumidos
- [x] Métricas de uptime, erros, latência e consumo de API
- [x] Reconciliar a cota diária como `max(tentativas locais, consumo do
  provedor)`, corrigindo ajuste externo obsoleto após a virada UTC sem reduzir
  chamadas locais auditáveis
- [x] Alertas quando coleta parar
- [x] Basear o watchdog no último ciclo concluído, não em qualquer log recente
- [x] Detectar sequência de falhas mesmo com o processo ainda ativo
- [x] Supervisionar separadamente a saúde do funil de validação
- [x] Registrar tarefas agendadas, processadas e adiadas e alertar saturação
  somente após três ciclos consecutivos acumulando fila
- [x] Separar no painel o uso de capacidade interna do tempo total observado
  sob limitação externa, exibindo `n/d` em vez de porcentagens inexistentes
- [x] Diferenciar o término esperado da última tarefa após o orçamento de um
  excesso anormal recorrente e degradar a operação após três ocorrências
- [x] Notificar uma única vez os marcos independentes de 30/100 por mercado e
  por versão da regra, sem liberar alertas prematuramente
- [x] Notificar de forma idempotente ativação e desativação real de cada
  calibração, repetindo a entrega se o Telegram falhar
- [x] Notificar também a primeira validação final reprovada ao alcançar 100
  resultados, com motivo e métricas disponíveis, sem repetir mensagens nem
  liberar o mercado; falha no Telegram permanece elegível para nova tentativa
- [x] Classificar como validação final realizada toda reprovação após 100
  resultados, inclusive classes desbalanceadas sem AUC calculável, mantendo o
  motivo técnico explícito em vez de voltar ao estado `pendente_amostra`
- [x] Medir ritmo de resultados independentes por mercado e estimar o prazo
  até 100, rotulando previsões curtas como preliminares
- [x] Enviar resumo operacional diário idempotente pelo watchdog, sem consumir
  API externa e com nova tentativa se o Telegram não confirmar
- [x] Incluir no mesmo resumo diário, sem criar nova notificação, somente os
  mercados que já iniciaram o challenger contextual, mostrando treino, classes
  green/red, modelo congelado e validação futura
- [x] Notificar de forma idempotente o congelamento e a conclusão da janela
  fixa do challenger contextual, repetir após falha de entrega e deixar
  explícito que nenhuma promoção é automática
- [x] Aplicar os mesmos marcos idempotentes ao challenger temporal 5/10/15 V2
  e incluir seu progresso no resumo diário somente após existir ao menos um
  resultado elegível, sem enviar aviso pela simples criação da âncora
- [x] Persistir em outbox SQLite a intenção dos alertas administrativos antes
  da rede, exigir `message_id`, deduplicar entre destinos após reinício e nunca
  reenviar automaticamente uma intenção de resultado externo incerto
- [x] Não reclassificar falha histórica de destino removido quando a auditoria
  estiver sem contexto de configuração
- [x] Fornecer reconciliação manual auditável para notificações operacionais
  incertas, exigindo o ID externo quando a entrega for confirmada
- [x] Auditar continuamente a cadeia do Telegram, detectando resultado sem
  aviso, aviso órfão, erro persistente, correção pendente e entrega duplicada
- [x] Auditar a coerência entre `message_id` persistido e confirmação sanitizada
  do Telegram, incluindo resultados e correções de simulações
- [x] Auditar continuamente integridade e cobertura do vetor temporal
  versionado, incluindo disponibilidade e duração medida em 5/10/15 minutos
- [x] Medir crescimento real do SQLite em janela móvel e alertar quando a
  projeção indicar menos de 30 dias até a reserva mínima de disco
- [x] Detectar e avisar uma única vez a primeira linha asiática real de
  escanteios do 1º/2º tempo, mantendo `Exactly` fora do marco
- [x] Distinguir ausência de jogos de quebra recente em candidatos ou odds
- [x] Recusar modelo ativo incompatível antes de chegar ao Telegram
- [x] Expor na prontidão profissional a integridade separada do modelo temporal
  e do challenger contextual, incluindo mercados inconsistentes, e degradar a
  operação se qualquer modelo congelado falhar na auditoria
- [x] Estender o mesmo gate ao challenger temporal 5/10/15 V2: âncora ou modelo
  incompatível agora degrada a operação contínua e bloqueia o gateway oficial,
  enquanto estudo íntegro ainda sem modelo permanece um estado válido
- [x] Validar estruturalmente cada registro do histórico de contexto contra seu
  JSON imutável, detectando conteúdo inválido, amostra/estado divergentes e
  duplicidade; incluir o controle no watchdog, pré-voo e prontidão
- [x] Garantir por teste que um modelo sombra inconsistente gere atenção sem
  encerrar o watchdog por falha ao construir a própria lista de avisos
- [x] Testes unitários de parsers, evolução e regras
- [x] Testes com retornos salvos do PackBall e API-Football
- [x] Teste ponta a ponta offline de PackBall, API, odds, evolução, SQLite,
  sinais, backtest e bloqueio do Telegram sem calibração
- [x] Teste ponta a ponta da ativação oficial com 300 partidas independentes,
  validação/AUC/Wilson e entrega apenas do candidato seguinte no canal oficial
- [x] Pré-voo somente leitura para reinício, sem exibir credenciais de sessão
- [x] Expor no pré-voo o frescor de calibrações ativas e inativas; permitir
  reinício corretivo quando a única divergência puder ser reconciliada pelo
  monitor antes de abrir o navegador, sem mascarar banco ilegível ou qualquer
  outra verificação reprovada
- [x] Impedir pré-voo enquanto a auditoria Telegram tiver entrega incerta,
  bloqueio de gateway ou outra inconsistência persistente
- [x] Backup verificado antes da implantação com retenção das cinco cópias mais
  recentes
- [x] Replay cronológico offline sem look-ahead e sem contaminar produção
- [x] Preservar a idade original das odds no replay e bloquear preços antigos
- [x] Vincular o replay à âncora criptográfica da regra e produzir
  automaticamente a análise temporal 70/30, cobertura de features,
  discriminação fora da amostra e corte sombra sem promover o resultado
- [x] Exibir funil por mercado e motivos de rejeição sem misturar versões
- [x] Proteção de credenciais e arquivos sensíveis
- [x] Validar credenciais e limites de risco sem exibir segredos
- [x] Bloquear inicialização com configuração numérica insegura
- [x] Backup automático do banco
- [x] Verificar integridade SQLite e checksum SHA-256 de cada backup
- [x] Exigir esquema atual completo e zero violações de chave estrangeira antes
  de considerar um backup restaurável
- [x] Recusar também backup com modelo sombra ou âncora temporal 5/10/15
  corrompida, incompatível com a linhagem ou desvinculada do modelo; a
  verificação lê somente envelopes e hashes, sem treinar ou montar datasets
- [x] Regenerar cópia diária incompatível preservando a anterior para auditoria
- [x] Evitar deadlock de implantação por esquema antigo: antes do pré-voo,
  preservar backup pré-migração verificável, recusar DDL com processos ativos,
  aplicar somente a migração aditiva e criar novo backup diário compatível
- [x] Criar e verificar backup ao virar o dia mesmo sem reiniciar o monitor
- [x] Alertar backup diário ausente ou inválido após tolerância da meia-noite
- [x] Criar ponto de recuperação verificado a cada janela de 6 horas, mantendo
  oito cópias periódicas além dos backups diários e de pré-reinício
- [x] Alertar se o ponto de recuperação mais recente estiver inválido ou superar
  o RPO operacional de 6 horas com 15 minutos de tolerância
- [x] Executar retenção e checkpoint tipado do WAL somente após backup confirmado
- [x] Gerar manifesto auditável para recuperação
- [x] Monitorar espaço livre e executar checkpoint seguro do WAL
- [x] Alertar continuamente espaço livre abaixo de 512 MB ou WAL excessivo
- [x] Procedimento documentado de recuperação
- [x] Auditoria de cobertura, pendências e integridade referencial

Critério de conclusão: falhas são detectadas, explicadas e recuperadas sem
corromper o histórico.

## Fase 10 — Gestão de risco e uso responsável

- [x] Limite diário de sinais
- [x] Bloqueio por dados insuficientes
- [x] Separar análise de execução de apostas (não existe executor)
- [x] Não automatizar apostas durante validação
- [x] Não prometer lucro ou taxa de acerto não comprovada
- [x] Incluir limites de exposição, faixa de odds e avisos de risco

Critério de conclusão: o sistema comunica incerteza e não transforma uma
pontuação técnica em garantia financeira.

## Próxima ação

Manter a coleta contínua e acumular no mínimo 100 resultados reais por mercado.
Depois, revisar a validação cronológica, a taxa de acerto, ROI, drawdown e
sequência de perdas. Somente mercados que passarem pelos critérios objetivos
terão calibração e alertas automáticos ativados.

O acompanhamento usa apenas resultados resolvidos para calcular quanto falta.
Sinais pendentes aparecem separadamente e não antecipam a amostra profissional.

### Marco operacional de 20–21/07/2026

- Regra preparada para ativação: `sinais-v4`.
- Amostra ativa inicial: zero resultados independentes; alertas permanecem
  bloqueados até validação real.
- Históricos `sinais-v1`, `sinais-v2` e `sinais-v3` preservados apenas para
  auditoria e separados dos relatórios, segmentos e pendências da v4.
- Suíte validada no ambiente do monitor: 320 testes aprovados.
- Liquidações auditáveis por `snapshot_id_liquidacao` e `fonte_resultado`, com
  migração segura do histórico e distinção explícita de `sem_dado`.
- Status, auditoria e watchdog verificam automaticamente se cada liquidação
  pertence à partida, horário e fonte corretos; inconsistências degradam a
  validação e geram alerta administrativo.
- Partidas longas com snapshots recentes não geram falso alerta após 180
  minutos; ausência de observação degrada a saúde e há teto absoluto de 360
  minutos para páginas que permaneçam congeladas como se estivessem ativas.
- Liquidação de copas usa exclusivamente o placar/estatísticas do tempo
  regulamentar; eventos de AET/PEN não contaminam o backtest de 90 minutos.
- Calibrações ativas têm frescor conferido pela amostra independente e pelo
  último resultado; modelo atrasado não chega ao Telegram.
- Política de calibração `calibracao-score-odd-wilson-duplo-auc-ic-linhagem-v7`: modelo
  guarda hash SHA-256 e intervalo temporal da amostra exata que o produziu e
  precisa passar pelos limites de discriminação AUC com intervalo de confiança.
- Simulações no Telegram não repetem o mesmo grupo independente
  `partida + mercado + versão`; candidatos repetidos continuam no banco.
- O painel audita continuamente odds de escanteios do 1º e 2º tempo e
  distingue linhas asiáticas de duas opções do mercado `Exactly`; no histórico
  verificado em 21/07 ainda não havia linha asiática válida nesses períodos.
- A API-Football passa a complementar somente o asiático do 1º tempo quando o
  PackBall não o oferece. O status identifica a fonte da evidência; o 2º tempo
  continua bloqueado até surgir uma linha real de duas opções.
- Os mercados `escanteios_1t` e `escanteios_2t` têm candidatos, liquidação,
  amostra, calibração, status e canal Telegram independentes. O primeiro fecha
  somente no intervalo; o segundo exige total de intervalo persistido e fecha
  pela diferença até o final. Evidência ausente nunca vira green ou red.
- Primeira liquidação de simulação validada em produção: over 5,5 gols em
  Bayswater City 1–5 Sydney, green a odd 1,83, com uma única notificação.
- Auditoria posterior identificou liquidações prematuras por placares que
  ainda podiam ser corrigidos. Em 21/07, 32 resultados foram retirados da
  amostra, preservados em `revisoes_resultados` e recolocados na fila final,
  incluindo oito liquidações antecipadas do mercado próximo gol;
  duas simulações afetadas receberam correção no Telegram.
- Monitor e watchdog saudáveis, backup diário íntegro, pontos de recuperação
  verificados a cada 6 horas e fila de resultados pendentes monitorada por
  idade, fonte, tentativas e mercado.
- Observabilidade de capacidade inclui média, p95 e máximo da latência e do uso
  do orçamento em janela móvel; três ciclos ativos consecutivos acima de 85%
  geram alerta preventivo antes de a fila começar a adiar partidas.
- Monitor e watchdog se supervisionam mutuamente: cada processo recupera a
  morte isolada do outro sem criar instâncias duplicadas, registrando a ação no
  log e no painel operacional.
- Paradas planejadas usam um modo de manutenção persistente e fail-safe; os
  processos encerram após o ciclo em andamento sem disputar autorreinícios, e
  somente `iniciar_sistema.py --retomar-manutencao` libera explicitamente a
  retomada.
- Autorrecuperação e inicialização usam a trava exclusiva do sistema operacional
  como prova da instância; PID reutilizado não mascara processo morto e PID
  desatualizado não cria processo duplicado.
- Monitor e watchdog registram assinaturas SHA-256 independentes do código
  carregado; o painel aponta separadamente qualquer reinício pendente.
- O painel separa o placar green/red das simulações do placar oficial, mostra
  greens, reds e pendentes por tipo de entrada, além dos totais oficiais do
  dia, e nunca usa testes como lucro real.
- Sinais oficiais têm circuit breaker independente: novas entradas param após
  três reds consecutivos em 24 horas ou três unidades de perda realizada no
  dia. Simulações continuam coletando evidência sem furar esse bloqueio.
- O watchdog notifica de forma idempotente a ativação e a recuperação do
  circuit breaker; o resumo diário discrimina green/red por mercado.
- [x] Espelhar no SQLite o estado completo e idempotente do watchdog e
  recuperá-lo automaticamente quando o JSON estiver ausente ou corrompido,
  impedindo repetição de marcos e avisos após reinício.
- O progresso diário até 100 separa amostra resolvida e primeiras decisões
  pendentes por mercado, sem contar candidatos posteriores da mesma partida.
- O acesso ao PackBall distribui a cota uniformemente na janela, audita o
  intervalo e o teto observados e preserva uma base anterior para decidir o
  experimento somente após 12 ciclos e 45 minutos. Bloqueio real aciona
  rollback persistente; incidentes continuam registrados após rotação do log.
- A prontidão profissional exige ritmo auditado como seguro e experimento
  aprovado (ou rollback seguro). Um teste ainda em observação aparece como
  pendência explícita e não pode ser confundido com conclusão profissional.
- Simulações possuem supervisão móvel independente por mercado: 30 resultados
  recentes são comparados com até 60 anteriores, com amostras mínimas, ROI e
  intervalo de 95% da diferença. Queda sustentada e recuperação geram alertas
  idempotentes; o primeiro alerta exige duas decisões novas consecutivas e
  nunca provoca ajuste automático da regra.
- Consumo da API-Football no dia: 93 de 7.500 requisições; limite interno de
  segurança em 7.000 e reserva de 500.

### Marco operacional de 26/07/2026

- Regra ativa versionada como `sinais-v6`, com fingerprint próprio, marco de
  início e experimento de filtro vinculados; amostras anteriores permanecem
  preservadas e não são misturadas na calibração oficial.
- Os escanteios foram separados em quatro categorias independentes:
  escanteio normal, asiático FT, asiático 1T e asiático 2T. Odds `Exactly`
  continuam excluídas dos mercados asiáticos.
- A movimentação de odds passou a incluir o tipo do mercado na chave. Isso
  impede que uma linha normal e uma asiática de mesmo período e valor sejam
  confundidas.
- Corrigida a chave do mercado próximo gol após a tipagem das odds. A suíte
  completa validou a alteração com 657 testes aprovados.
- Primeiro ciclo real da `sinais-v6`: 13 partidas ao vivo encontradas, seis
  processadas, nenhuma falha de fonte e nenhum `IndexError`. Os sete mercados
  foram avaliados; ausência de odd válida resultou em rejeição fail-safe.
- As linhas asiáticas FT detectadas automaticamente têm proveniência
  `api_football`. A Bet365 permanece desligada da coleta automática e só possui
  evidência manual auditável; as mensagens operacionais agora exibem a fonte
  real, sem atribuí-la ao PackBall.
- A calibração oficial da `sinais-v6` começa com amostra independente zero.
  Simulações podem continuar, mas nenhum mercado será apresentado como
  profissional ou como probabilidade calibrada antes de cumprir os critérios
  objetivos.
- A hipótese sombra `proximo_gol_minuto_56_v6_20260726` foi pré-registrada,
  vinculada ao fingerprint da v6 e protegida por gatilhos SQLite imutáveis.
  O watchdog acompanha 30 resultados futuros independentes, notifica uma única
  vez a confirmação ou refutação e nunca aplica o corte automaticamente.
- Auditoria após a migração: operação contínua, pré-voo, API-Football, backup,
  Telegram de teste, ritmo PackBall, recuperação Windows, linhagem e hipóteses
  sombra tecnicamente prontos. Permanecem apenas pendências estatísticas
  (amostra, drift, filtro e primeira entrega oficial) e fontes externas reais
  de duas opções para escanteios asiáticos 1T/2T.
- Suíte completa após as proteções de hipótese: 667 testes aprovados.
- Primeiro ciclo ponta a ponta real da `sinais-v6` confirmado em 26/07:
  sinal 63440, Bulls Academy W x Gladesville Ravens W, mercado `gol_ht`,
  linha 1,5 e odd 1,50. O alerta inicial foi entregue no Telegram (mensagem
  1131); o monitor revisitou a partida aos 26, 34, 41 e 47+1 minutos sem
  liquidar prematuramente; o snapshot 13291 confirmou o intervalo em 0-1 e
  gerou RED de -1,00u pela fonte PackBall. O resultado foi entregue uma única
  vez no Telegram (mensagem 1133), entrou como a primeira amostra independente
  temporal da v6 e criou os primeiros registros íntegros de drift geral e de
  `gol_ht`.
- A independência entre mercados simultâneos também foi confirmada em produção:
  no intervalo de Central Coast II x Bulls Academy em 0-0, o `gol_ht` 63615
  foi liquidado como RED pela API-Football e notificado no Telegram (mensagem
  1134), enquanto o `proximo_gol` 63616 permaneceu pendente para o segundo
  tempo. A calibração `gol_ht` avançou para duas partidas independentes sem
  contaminar a amostra de `proximo_gol`.
- O painel operacional passou a exibir os checkpoints de calibração arquivados
  por versão, explicitando que não entram na regra ativa e verificando o
  vínculo criptográfico de cada checkpoint com o histórico imutável. V1–V5
  estão vinculadas; o V4 permanece verificável com `gol_ft=83`, `gol_ht=17`,
  `proximo_gol=40` e `proximo_escanteio=22`. A mudança elimina a ambiguidade
  entre reiniciar uma calibração e apagar seu histórico.
- Suíte completa após essa melhoria de observabilidade: 668 testes aprovados.
- A primeira liquidação real de `proximo_gol` da v6 acompanhou toda a partida
  Central Coast II x Bulls Academy. O sinal 63616 previa o visitante, mas o
  histórico persistido comprovou que a casa marcou primeiro
  (`0-0 → 1-0 → 1-1 → 1-3`), produzindo RED somente após o encerramento.
  Um pênalti perdido rotulado como evento `Goal` pela API foi corretamente
  ignorado, e divergências temporárias de placar não causaram liquidação
  antecipada.
- A proveniência da liquidação deixou de ser escolhida pela mera presença de
  uma fonte no snapshot: placar e eventos da API precisam concordar com a
  evidência usada; em divergência, o resultado aponta para o PackBall. O caso
  real terminou vinculado ao snapshot 13390 e à fonte `packball`. A mudança
  foi carregada em produção com monitor/watchdog únicos e atualizados.
- A calibração v6 avançou para duas partidas independentes em `proximo_gol`;
  a hipótese sombra de minuto maior ou igual a 56 recebeu seu primeiro
  resultado futuro (1/30), sem aplicação automática.
- Suíte completa após a correção de proveniência: 670 testes aprovados.
- A retomada operacional de 26/07 também foi validada ponta a ponta. Uma
  execução restrita do watchdog produziu falhas locais de rede sem qualquer
  comprovante do provedor; esses registros foram preservados como histórico de
  erro. Após a inicialização no contexto correto, as notificações 98 e 99 foram
  entregues com os comprovantes Telegram 1139 e 1140. A auditoria reconheceu a
  recuperação posterior sem apagar nem reclassificar falhas antigas.
- O pré-voo de 26/07 às 03:10 aprovou configuração, sessão e ritmo do PackBall,
  SQLite, Telegram, notificações operacionais, cache API-Football, linhagem v6,
  backup, coleta, armazenamento e franquia da API. Monitor e watchdog estavam
  ativos em instância única, e a suíte completa permaneceu em 670 testes
  aprovados.
- Um replay offline atualizado reaplicou a v6 a 13.415 snapshots históricos,
  sem acessar PackBall/API nem alterar o banco operacional. Foram obtidas 152
  partidas independentes em `gol_ft` (81 greens, 71 reds, ROI -13,40% e AUC
  0,4716). Isso comprova que o histórico V4 não foi perdido e pode servir de
  baseline, mas também comprova que ele não deve ser transplantado para a
  calibração oficial v6: o filtro FT atual ainda não demonstrou vantagem.
- O replay passou a registrar a âncora e o fingerprint v6 no banco temporário
  e a executar automaticamente a análise das features 5/10/15 em divisão
  cronológica 70/30. Em FT houve cobertura integral de 152 vetores. O corte
  `chutes_5min/minuto <= 0,3914`, escolhido somente no desenvolvimento, reduziu
  a perda futura, mas ainda produziu ROI de -0,56% em 27 partidas; por isso foi
  rejeitado e não alterou o motor ativo.
- O watchdog passou a calcular e persistir as auditorias durante a partida a
  frio sem enviar alertas de qualidade antes do primeiro ciclo completo. A
  correção evita falsos avisos de cobertura API na inicialização, passou nos
  670 testes e foi carregada reiniciando somente o watchdog, sem interromper o
  monitor ou o navegador PackBall.
- A auditoria de prontidão revelou que a coorte filtrada v1 permanecia zerada
  porque candidatos reais de 72,5–74,5 pontos não eram registrados quando
  outro mercado da mesma partida vencia a seleção do Telegram. O experimento
  `filtro-simulacoes-v2` corrige isso prospectivamente: conserva um único envio,
  congela cada descarte independente antes do resultado e reconhece marcos de
  versões anteriores sem misturar amostras. Nenhum dos casos já conhecidos foi
  preenchido retroativamente.
- A v2 iniciou em 26/07 às 03:24:16, vinculada ao fingerprint da `sinais-v6`,
  com zero decisões herdadas e auditoria íntegra. Monitor e watchdog foram
  retomados com código atualizado; o pré-voo ficou aprovado sem falhas. A suíte
  completa após a mudança contém 674 testes aprovados.
- Um teste ponta a ponta adicional comprovou o contrato completo da v2 em
  SQLite isolado: dois candidatos aprovados na mesma leitura produziram uma
  única entrega Telegram; o candidato de 72,5 pontos foi congelado como
  `gateway:teste/filtrado` sem chamar o transporte; um snapshot futuro liquidou
  ambos; e a comparação encontrou exatamente uma unidade enviada e uma
  filtrada. A suíte completa passou a 675 testes aprovados.
- A auditoria local do catálogo de 266 mercados da API-Football, realizada sem
  nova requisição, confirmou `Asian Corners (1st Half)` no ID 51, mas 217
  consultas históricas não produziram nenhuma oferta anexável. Para o 2T, o
  único total específico encontrado foi `Total Corners (3way) (2nd Half)`,
  que não é equivalente ao asiático de duas opções e permanece excluído.
- O histórico SQLite confirmou a mesma ausência: 1T contém somente 193
  observações `Exactly` e 2T contém 204 `Exactly`/corrida, todas rejeitadas
  corretamente para fins asiáticos. O FT possui fonte real comprovada e 160
  ofertas asiáticas estruturadas. Nenhum mercado foi renomeado ou preenchido
  por aproximação.
- A matriz de validação passou a tratar reprovação após 100 resultados como
  validação final realizada mesmo quando o motivo é classes desbalanceadas e
  ainda não existe AUC calculável. O contrato foi coberto pela suíte completa,
  agora com 694 testes aprovados.
- A avaliação das hipóteses sombra ganhou grupo de controle prospectivo
  disjunto e intervalo de 95% para a diferença de ROI. A hipótese só pode ser
  confirmada com ROI selecionado positivo, controle mínimo e limite inferior
  acima de zero; média pontual favorável não basta. A hipótese de próximo gol
  a partir do minuto 56 continua imutável e sem aplicação automática. A suíte
  completa passou a 695 testes.
- A documentação oficial da TotalCorner foi auditada antes de qualquer
  integração: ela comprova `cornerLine`/`cornerList` para FT e
  `cornerLineHalf`/`cornerHalfList` para o primeiro tempo, mas não comprova uma
  linha asiática exclusiva de 2T. Nenhum conector foi criado por inferência.
  O arquivo `FONTES_ODDS_SEGURAS.md` preserva o comparativo e o gate obrigatório
  para testar trials sem expor tokens ou misturar mercados não equivalentes.
- O alerta Telegram de hipótese sombra passou a exibir controle, ROI do
  controle, diferença de ROI, IC95 e versão da política. Uma conclusão produzida
  por avaliação antiga é recusada e não consome a notificação idempotente. A
  suíte completa passou a 696 testes.
- O painel `status_bot.py` passou a mostrar o mesmo contrato da hipótese:
  progresso selecionado e de controle, faltantes separados, diferença de ROI,
  IC95 e versão da política. A saída real foi validada com a hipótese ativa e a
  suíte completa passou a 697 testes.
- O experimento `filtro-simulacoes-v2` atingiu as duas amostras mínimas e sua
  primeira conclusão foi congelada prospectivamente no SQLite: 57 resultados
  enviados contra 31 filtrados, diferença de ROI de -0,2253 e IC95
  `[-0,6372; 0,1866]`. A vantagem não foi comprovada, portanto o filtro não foi
  promovido. A conclusão é imutável e resultados futuros não podem alterar
  essa decisão; novo teste exige nova versão. A gravação foi separada da
  auditoria somente leitura, novos backups compatíveis foram criados e a suíte
  completa passou a 701 testes.
- A BetsAPI foi confirmada apenas como candidata externa: o endpoint v2
  documenta `Asian Corners` (mercado 4) e `1st Half Asian Corners` (mercado 7)
  com origem Bet365, mas não documenta o equivalente asiático do segundo
  tempo. Nenhuma integração foi ativada sem token, amostra real, controle de
  cota e prova de pareamento com os jogos do PackBall.
- A recuperação automática do Windows foi instalada e exercitada no Agendador
  real: encontrou monitor e watchdog já ativos sem duplicar processos. O
  instalador agora exige que a tarefa possa iniciar e continuar também na
  bateria, valida essas opções no XML e remove uma instalação incompleta se o
  ajuste falhar. O heartbeat real confirmou monitor PID 39344 e watchdog PID
  12720 já ativos.
- O heartbeat do Agendador foi versionado como `autostart-heartbeat-v2` e agora
  preserva prova direta da definição real: tarefa instalada, intervalo de cinco
  minutos e início/continuidade na bateria. Evidência circular baseada no
  próprio heartbeat falha fechada. A execução real confirmou todos os campos,
  o painel passou a exibi-los e a suíte completa passou a 707 testes.
- A cobertura de escanteios asiáticos FT foi revalidada sem nova chamada:
  o bet 32 possuía 700 consultas, 524 respostas globais e 365 ofertas reais
  anexadas, com última anexação em 28/07/2026 às 18:50:39. O painel agora
  diferencia essa fonte comprovada da calibração ainda em 3/100 resultados,
  evitando interpretar disponibilidade de odd como liberação de sinal. A suíte
  completa passou a 708 testes.
- A auditoria do funil FT encontrou 19 ofertas API-Football com idade própria
  válida (0–285 segundos) bloqueadas indevidamente pela idade global do cache
  PackBall; quatro tinham somente esse bloqueio. A correção foi isolada em
  `sinais-v7-ft-asiatico`, com fingerprint e marco próprios, sem alterar o
  fingerprint da V6 nem reiniciar suas 61 amostras de gols FT. Ofertas realmente
  vencidas continuam bloqueadas. Backup pré-reinício válido foi criado, o
  pré-voo completo passou, a suíte ficou em 713 testes e o primeiro ciclo real
  da V7 concluiu com 5 jogos, 2 processados, nenhuma tarefa adiada e 2 candidatos
  FT vinculados sem divergência. Monitor, watchdog e recuperação do Windows
  foram confirmados ativos após o reinício controlado.
- A observabilidade passou a respeitar a versão ativa de cada mercado. O drift
  e o resumo diário não misturam mais os dois resultados asiáticos arquivados
  da V6 com a população `sinais-v7-ft-asiatico`: a V7 aparece corretamente com
  zero resultados resolvidos até receber sua primeira simulação elegível.
  O histórico de drift grava a versão individual em cada mercado e o resumo
  Telegram inclui exceções prospectivas sem perder os mercados que continuam
  na V6. A suíte completa passou a 716 testes.
- O canal operacional do Telegram ganhou disjuntor persistente contra
  tempestade de notificações: três falhas recentes pausam novos envios por
  cinco minutos e liberam somente uma sonda de recuperação. A indisponibilidade
  observada era causada pelo proxy restrito herdado de uma inicialização via
  Codex; o sistema foi reiniciado pela tarefa nativa do Windows, recuperou o
  Telegram com prova de entrega e zerou os erros persistentes. O pré-voo agora
  permite reinício corretivo quando a única falha é operacional e está contida,
  sem relaxar integridade, banco ou provas. A suíte completa passou a 718
  testes.

- A abertura do Chrome passou a tolerar a liberação tardia de recursos após
  reinícios: `PermissionError` transitório gera até três tentativas com espera
  crescente, e qualquer navegador parcialmente aberto é fechado antes da nova
  tentativa. O reinício real pelo Agendador estabilizou monitor e watchdog na
  primeira confirmação, sem nova falha fatal. A suíte completa passou a 720
  testes.
- A reserva adaptativa passou a persistir as durações individuais no log e a
  restaurar até 30 observações após reinício, usando o p95 dos registros antigos
  somente como compatibilidade conservadora. A suíte completa passou a 742
  testes. No primeiro ciclo real após a implantação, as 30 durações foram
  restauradas, 5 de 17 tarefas foram processadas e a coleta detalhada terminou
  em 168,260 segundos dentro do orçamento de 180 segundos, sem aumentar o ritmo
  de acesso ao PackBall.
- A auditoria do funil em 29/07/2026 confirmou que o limite de mensagens do
  Telegram não limita o backtest: dos 41 candidatos `gol_ft` aprovados nas 24
  horas observadas, 40 já estavam liquidados internamente e somente a partida
  ainda ao vivo permanecia pendente. A mesma auditoria confirmou 220 consultas
  reais do bet 51 sem nenhuma oferta global; a suspensão temporária desse bet
  evita desperdício de cota e não oculta uma fonte 1T disponível. O bet 32
  continuava anexando ofertas FT, enquanto não surgiu fonte asiática 2T de duas
  opções.
- A recuperação da calibração passou a abranger também modelos inativos. Uma
  falha entre a liquidação e a recalibração não pode mais deixar silenciosamente
  a amostra em 99: o watchdog distingue atraso ativo/inativo e o monitor
  reconcilia somente linhas divergentes no ciclo seguinte. A suíte completa
  passou a 747 testes. Após a implantação, as sete calibrações inativas
  corresponderam exatamente às amostras e fingerprints atuais; `gol_ft` avançou
  para 82 resultados e o modelo sombra registrou corretamente sua primeira
  observação futura, sem alterar V6.
- O pré-voo passou a auditar as mesmas calibrações em modo somente leitura.
  Divergência de amostra aparece como `requer_reconciliacao_no_inicio` e não
  impede o reinício corretivo porque `preparar()` recalibra antes de abrir o
  navegador; banco ausente, ilegível ou outro controle reprovado continuam
  bloqueando a partida. A suíte completa passou a 749 testes.
- O gateway oficial ganhou um disjuntor global de exposição incerta. Se houver
  queda entre o envio ao Telegram e a confirmação local, nenhum novo sinal
  oficial é enviado até a reconciliação; retries controlados do próprio sinal
  continuam possíveis e simulações não são bloqueadas. A suíte completa passou
  a 751 testes.
- Falhas de transporte durante o envio oficial deixaram de ser presumidas como
  não entrega. Timeout, queda de conexão ou resposta sem prova agora criam
  `incerto`, param novos retries e exigem conferência manual no Telegram.
  Intenções antigas que já possuem conclusão posterior não acionam o disjuntor.
  A suíte completa passou a 753 testes.
- O contexto avançado passou a capturar a linha pré-jogo de gols e escanteios
  pelo endpoint oficial `/odds`, com cache de doze horas, parser fechado para
  pares Over/Under e consenso entre casas. IDs pré-jogo e ao vivo permanecem
  separados. A referência fica congelada no snapshot em
  `contexto-pre-jogo-v4`; as hipóteses de linha alta entram somente na avaliação
  prospectiva `avaliacao-contexto-sombra-v5` e não alteram V6/V7. A primeira
  observação real identificou e eliminou `Total ShotOnGoal` do grupo de gols;
  depois da correção, o consenso real ficou em 11 casas para gols e 7 para
  escanteios. A suíte completa passou a 768 testes.
- A entrada de odds ao vivo do PackBall ganhou uma segunda lista fechada em
  Python, além da seleção no navegador. Somente os sete mercados já mapeados
  chegam ao normalizador; `ShotOnGoal`, `Goal Kicks`, handicap ou qualquer
  título futuro ambíguo são descartados antes do motor. A proteção foi colocada
  na fronteira para manter intactos os fingerprints e as amostras V6/V7. A
  suíte completa passou a 769 testes.
- O pré-voo e a matriz de prontidão passaram a auditar explicitamente os hashes,
  versões, mercados e features dos modelos temporal e contextual em sombra.
  Modelo ausente durante a formação da amostra é válido; modelo congelado
  incompatível bloqueia o reinício e degrada a operação. A suíte completa
  passou a 778 testes.
- O primeiro resultado prospectivo com `contexto-pre-jogo-v4` fechou em
  29/07/2026: o sinal 97934, `gol_ft`, foi liquidado como red pelo PackBall e
  entrou automaticamente no challenger com oito features contextuais válidas.
  O funil avançou de 0 para 1/60, preservou a classe 0/1, excluiu corretamente
  as 86 observações anteriores sem V4 e não modificou V6 nem enviou sinal
  oficial.
- A auditoria do histórico contextual deixou de confiar apenas na existência
  das linhas: cada payload agora é parseado e comparado com regra, último sinal,
  amostra, estado e decisão persistidos. Durante essa revisão foi corrigida uma
  falha de ordem no watchdog que poderia encerrá-lo ao tentar avisar sobre um
  modelo sombra inconsistente. Pré-voo e prontidão passaram a falhar fechado
  nessa condição. Os dois primeiros payloads, anteriores ao versionamento
  interno, permanecem identificados como legado válido e imutável. A suíte
  completa passou a 785 testes; após a recarga isolada do watchdog, o histórico
  real ficou íntegro com 12 registros e a operação permaneceu pronta.
- O resumo diário do Telegram passou a incorporar, no mesmo envio idempotente,
  somente os mercados que iniciaram o challenger V4. A prévia real exibiu
  `gol_ft` em 2/60, com uma classe green e uma red; mercados ainda zerados foram
  omitidos. A mudança não consulta API, não navega no PackBall e não cria
  mensagem adicional.
- A validação prospectiva dos modelos temporal e contextual passou a usar uma
  janela fixa com os primeiros 30 resultados posteriores ao congelamento.
  Testes adicionaram resultados 31–40 e comprovaram que AUC, fingerprint e
  decisão não mudam. O watchdog também passou a avisar, com retry idempotente,
  o congelamento e a conclusão contextual sem promoção automática. A suíte
  completa passou a 791 testes e a recarga isolada manteve o monitor ativo.

## Regras permanentes do projeto

1. PackBall é a fonte principal; ausência na API não remove partidas.
2. API-Football é confirmação complementar e deve respeitar a franquia.
3. Dados ausentes nunca devem ser inventados.
4. Sinais exigem rastreabilidade e histórico.
5. Nenhum percentual de confiança é divulgado sem calibração.
6. Toda mudança relevante precisa de teste proporcional ao risco.
# Contexto avançado API-Football em modo sombra (29/07/2026)

- O monitor passou a coletar, com cache persistente, forma recente dos dois
  times, confrontos diretos, escalações, desfalques, estatísticas da temporada
  e previsão do provedor quando a competição oferece esses dados.
- Métricas equivalentes de PackBall e API-Football (chutes, chutes no gol e
  escanteios) são comparadas e congeladas no snapshot.
- O contexto usa orçamento máximo de 8 segundos por partida em cada passagem.
  O restante é completado nos ciclos seguintes; falhas auxiliares não afetam a
  leitura ao vivo principal.
- Todos os campos permanecem em `modo=sombra`: não alteram V6/V7 nem liberam
  sinais até que sua contribuição para ROI e acerto seja comprovada.
- A avaliação `avaliacao-contexto-sombra-v3` usa o primeiro sinal aprovado de
  cada partida/mercado e compara grupos com/sem forma superior, H2H de gols,
  desfalques desequilibrados, escalações confirmadas e concordância entre
  fontes. Uma variável só fica pronta para revisão com pelo menos 30 resultados
  nos dois grupos; nunca há aplicação automática.
- Cada avanço da amostra é preservado em
  `historico_avaliacao_contexto`. A chave mercado/regra/último sinal impede
  duplicação, e gatilhos SQLite proíbem alteração ou exclusão das avaliações
  já observadas.
- As variáveis usam três estados: verdadeiro, falso e desconhecido. Dados não
  oferecidos pela competição ficam fora dos dois grupos e aparecem na métrica
  de cobertura; portanto, ausência de escalação ou estatística não contamina o
  grupo de controle.
- O schema `contexto-pre-jogo-v2` resume estatísticas da temporada e previsão
  do provedor antes de congelar o snapshot. Em 100 snapshots reais, o payload
  médio caiu de 21 KB para 2,8 KB (redução de 86,5%); respostas completas
  continuam somente no cache com TTL.
- Mesmo após 30 resultados em cada grupo, a variável só fica conclusiva quando
  o intervalo de 95% do delta de ROI não atravessa zero. Evidência favorável
  também exige ROI positivo no grupo com a variável; caso contrário, permanece
  inconclusiva ou é classificada como evidência contrária.
- As hipóteses são pré-registradas por mercado. Mercados de escanteio não
  testam retrospectivamente H2H de gols, por exemplo. A família usa `z=3.0`,
  mais conservador que o intervalo isolado de 95%, para reduzir falsos
  positivos causados pelas múltiplas comparações.
- [x] Congelar a calibração oficial na política de janela fixa v8: primeiros
  100 resultados independentes divididos em 70 de desenvolvimento e 30 de
  validação, sem reabrir a decisão com resultados posteriores. Manter uma
  janela separada de até 300 observações somente para monitoramento de drift.
  A suíte completa passou a 792 testes.
- [x] Separar a identidade dos marcos Telegram da versão da política de
  calibração. Migrações estatísticas preservam avisos 30/100 já entregues,
  enquanto uma nova linhagem reinicia somente o mercado afetado. A linhagem
  própria de escanteios asiáticos FT deixou de compartilhar implicitamente a
  identidade da regra geral. A suíte completa passou a 795 testes.
- [x] Alinhar a pré-validação de 30–99 resultados à janela oficial fixa:
  desenvolvimento preservado nos primeiros 70 e validação acumulada somente
  do 71º ao 100º. O painel deixou de exibir a divisão proporcional móvel que
  não corresponderia à decisão final. A suíte completa passou a 797 testes.
- [x] Tornar a pré-validação explicável sem antecipar a decisão final. O painel
  agora identifica a tendência provisória do recorte e informa objetivamente
  se AUC, limite inferior do AUC ou ROI estão abaixo dos gates registrados.
  O diagnóstico continua incapaz de liberar sinais oficiais.
- [x] Proteger a inicialização do próprio driver Playwright contra
  `PermissionError` transitório anterior à abertura do Chrome. A retentativa
  exponencial é limitada, observável e não gera navegação ou login duplicado.
- [x] Distinguir o espelho antigo do watchdog durante a partida a frio. A
  prontidão agora usa os horários persistidos para mostrar
  `supervisao_inicializando`, mantendo mercados bloqueados sem emitir o falso
  diagnóstico de operação degradada antes da primeira auditoria da instância.
- [x] Fechar o caminho oficial do Telegram com a mesma prontidão operacional
  exibida no painel. Mesmo um modelo calibrado é bloqueado no último instante
  quando a operação está inicializando/degradada, o validador está ausente ou
  sua consulta falha; cada bloqueio fica auditável no SQLite.
- [x] Auditar preventivamente a primeira transição real de 99 para 100
  resultados da janela fixa. Foram comprovados o corte cronológico 70/30, a
  reprovação sem ativação por AUC/ROI insuficientes, a notificação idempotente
  do julgamento final e o congelamento dos challengers prospectivos. Em
  30/07/2026, `gol_ft` estava em 95/100 e a tendência parcial desfavorável
  permanecia apenas diagnóstica, sem reiniciar a amostra nem liberar oficial.
- [x] Comprovar que um challenger temporal ou contextual marcado como
  `favoravel_para_revisao` continua incapaz de substituir uma calibração
  oficial reprovada. A promoção exige uma nova regra pré-registrada e nova
  validação prospectiva; a suíte completa passou a 808 testes.
- [x] Comprovar o fluxo pós-reprovação: a janela oficial permanece congelada,
  resultados posteriores entram somente no drift e nos challengers, e as
  simulações rotuladas continuam formando evidência prospectiva sem serem
  tratadas como sinais oficiais. A suíte completa passou a 809 testes.
- [x] Preparar o diagnóstico isolado do TotalCorner para comprovar, com uma
  única consulta e sem paginação ou retentativa, se a resposta real oferece
  linha asiática de escanteios do primeiro tempo com Over e Under. O token
  nunca é persistido, a integração automática permanece desabilitada e uma
  linha de três opções é rejeitada. Quatro testes dedicados elevaram a suíte
  completa para 813 testes.
- [x] Suspender prospectivamente os mercados `escanteios_1t` e
  `escanteios_2t` por decisão operacional enquanto não houver evidência de ROI
  positivo. A suspensão é o padrão, impede novos candidatos e evita chamadas
  API-Football de asiático 1T, sem apagar o histórico nem afetar escanteio
  normal ou asiático FT. A reativação exige uma chave operacional explícita.
  A filtragem ocorre fora da fórmula para preservar a linhagem e a calibração
  existentes. A suíte completa passou a 817 testes.
- [x] Executar o pós-mortem da reprovação de `gol_ft` na janela fixa de 100
  partidas. A liquidação e as linhas estavam íntegras; a falha encontrada foi
  de generalização e ordenação da nota. As faixas 80–89 e 90–100 pioraram
  fortemente na validação, enquanto 70–79 permaneceu positiva nos dois
  recortes. O achado será testado apenas de forma prospectiva e sombra, sem
  reabrir a regra v6 ou liberar sinais automaticamente.
- [x] Ampliar a análise de Gol FT para 117 resultados e três blocos
  cronológicos. A hipótese de nota baixa falhou no bloco posterior. O padrão
  composto com até 3 gols atuais e até 3 chutes nos últimos 5 minutos foi o
  candidato de maior cobertura com ROI positivo nos três blocos, mas seu IC95
  ainda cruza zero. Ele começou uma validação prospectiva própria, em zero,
  sem promoção automática. O avaliador sombra passou a aceitar critérios
  compostos imutáveis e a suíte completa passou a 818 testes.
- [x] Eliminar starvation na fila detalhada sob muitos jogos simultâneos. A
  idade de agendadas/processadas/adiadas passou a ser observável e revelou
  partidas antigas sempre deslocadas por reservas novas, temporais e por API.
  O monitor agora reserva uma única vaga para a leitura mais atrasada acima de
  20 minutos, sem aumentar navegações nem remover as demais prioridades. A
  suíte completa passou a 895 testes e a primeira prova real resgatou uma
  partida com cerca de 2h37 de atraso, reduzindo o estoque antigo em um ciclo.
- [x] Supervisionar regressões do resgate da fila antiga. O status agora expõe
  processadas/adiadas acima de 20 minutos e a maior espera restante; o watchdog
  degrada somente após três ciclos consecutivos com partidas antigas e zero
  resgates. Dois ciclos reais reduziram a maior espera adiada de cerca de 104
  para 64 minutos, com listas 34/34 e 30/30 e API saudável. A suíte completa
  passou a 897 testes.
- [x] Impedir que uma partida antiga coincidente com a vaga periódica seja
  reservada duas vezes. A ordenação preserva cardinalidade e unicidade mesmo
  nesse caso raro; a suíte completa passou a 898 testes.
- [x] Alinhar a fila temporal congestionada ao requisito mínimo do motor de
  sinais. Uma janela de 5 minutos agora tem precedência sobre revisitas apenas
  de 10/15 minutos quando ainda não existe cobertura mínima, sem aumentar
  navegações nem remover foco, exploração ou resgate de atrasados. No primeiro
  ciclo real após o reinício, o monitor processou quatro partidas, fechou uma
  janela de 5 e uma de 15 minutos, resgatou uma tarefa acima de 20 minutos e
  manteve a validação geral saudável.
- [x] Impedir que partidas acima de 86 minutos ocupem as vagas de foco,
  seguimento temporal ou oportunidade API, pois já estão fora de todos os
  mercados operacionais ativos. Elas continuam disponíveis na fila normal e
  no finalizador. A prova em produção identificou e retirou um foco tardio,
  fechou uma janela válida de 5 minutos, resgatou uma tarefa antiga e manteve
  PackBall, API, monitor, watchdog e validação saudáveis.
- [x] Substituir o máximo histórico da nota pela melhor nota do snapshot mais
  recente ao formar o foco. A auditoria de 83 partidas recentes encontrou 13
  dos 28 focos antigos já abaixo do limiar atual. Após a correção, o primeiro
  ciclo real operou com quatro focos atuais, processou quatro detalhes, fechou
  janelas de 5 e 15 minutos, resgatou duas tarefas antigas e permaneceu
  saudável em todas as fontes e supervisões.
- [x] Tornar observável o funil prospectivo da regra de próximo gol, separando
  minuto válido, histórico de 5 minutos, atividade recente, odd mínima,
  ausência de outros bloqueios e aprovação. O supervisor persiste também os
  principais motivos de rejeição. A primeira leitura real após o reinício
  auditou 60 decisões, 43 dentro da janela, oito com histórico de 5 minutos,
  zero com atividade ofensiva suficiente e zero violações da regra; assim a
  falta de amostra deixou de parecer falha de login ou de odds.
- [x] Retirar partidas em `Intervalo/HT` das vagas de foco, seguimento temporal,
  novidade e oportunidade API, mantendo-as na fila normal e no finalizador.
  Quatro das nove primeiras janelas de 5 minutos haviam sido formadas durante
  o intervalo e eram necessariamente inativas. No primeiro ciclo corrigido,
  16 partidas em intervalo ficaram fora das prioridades, uma janela ativa de
  5 e outra de 10 minutos foram fechadas, uma tarefa antiga foi resgatada e a
  validação permaneceu saudável, sem violações nem acessos extras.
- [x] Separar no funil de próximo gol a cobertura independente de odds:
  disponível, fresca em até seis minutos e acima do mínimo de 1,66. A
  conferência dos candidatos temporais mostrou que as odds presentes eram
  realmente novas e que as ausências vinham da fonte, não de cache vencido.
  Após o reinício, o supervisor auditou 76 decisões, 42 odds disponíveis e
  frescas, 35 acima do mínimo e zero violações da regra.
- [x] Criar rechecagem prioritária após gol sem elevar a carga do PackBall.
  Quando a leitura mais recente é bloqueada apenas para aguardar a
  estabilização do mercado, a partida retorna ao foco em até dois minutos e
  exige odds novas. A prioridade vale somente até o minuto 75, ignora
  Intervalo/HT e substitui uma vaga existente em vez de abrir uma navegação
  adicional. Bloqueios de snapshots antigos não são reutilizados. A suíte
  completa passou a 955 testes e o pré-voo permaneceu integralmente saudável.
  No primeiro ciclo real, uma rechecagem pós-evento foi agendada e processada,
  com odds novas, quatro detalhes no total, lista 182/182 e ambas as fontes
  saudáveis.
- [x] Supervisionar a entrega efetiva das rechecagens pós-gol. O painel e o
  estado persistente do watchdog agora expõem agendadas/processadas e a
  sequência de ciclos sem atendimento; três omissões consecutivas degradam a
  operação com motivo específico, enquanto uma leitura concluída recupera a
  supervisão. A suíte completa passou a 957 testes. Após o reinício, o estado
  real registrou 1/1 rechecagem e zero ciclos omitidos, com os dois processos
  ativos e código atualizado.
- [x] Tornar explícitas no painel as pendências da prontidão profissional, com
  requisito e estado individuais. A leitura real deixou claro que Gol FT está
  `reprovado_validacao`, enquanto Telegram oficial e quatro outros mercados
  aguardam evidência futura; a contagem isolada já não esconde a causa.
- [x] Pré-registrar um novo challenger de Gol FT após a reprovação da regra
  antiga: movimento do Over com delta até +0,31 e odd atual até 2,00. No
  histórico, o corte teve 51/76 greens e ROI +5,0% no desenvolvimento, positivo
  nas três fatias, e 10/11 greens nos 30 finais. Como houve busca entre vários
  cortes, essa evidência serve somente para gerar a hipótese. A avaliação
  prospectiva começou imutavelmente em 08/08/2026 09:59:33, com 0/30 resultados,
  controle mínimo de 10, IC95 obrigatório e aplicação automática desligada.
- [x] Auditar a baixa formação de amostra por mercado. Em escanteios, o
  gargalo comprovado é externo: `proximo_escanteio` recebeu odd PackBall em
  apenas 78 de 3.327 decisões, e o asiático FT recebeu odd API-Football em
  seis; nenhuma regra foi afrouxada. Em Gol HT, o gargalo corrigível era o
  prazo curto, com somente nove aprovações antes do minuto 28.
- [x] Aplicar prioridade por vencimento ao Gol HT sem aumentar navegações. Uma
  leitura-base nova entre os minutos 10–22 e um seguimento temporal até o
  minuto 28 passam à frente de oportunidades tardias dentro das vagas já
  existentes; base, seguimento e oportunidade ficaram observáveis
  separadamente. A suíte completa passou a 961 testes. O primeiro ciclo real
  não encontrou partida nessa janela e registrou os três indicadores como
  falsos, sem fabricar reserva ou sinal.
- [x] Garantir que a prioridade Gol HT seja executável no orçamento real, não
  apenas marcada. A reserva com vencimento mais próximo ocupa uma das quatro
  primeiras posições; foco permanece primeiro quando existe e o resgate da
  fila antiga continua entre as três primeiras. Em produção, um seguimento HT
  foi garantido no top 4 e processado, fechando uma janela real de 5 minutos,
  enquanto duas tarefas antigas também foram resgatadas. Nenhuma navegação foi
  adicionada.
- [x] Corrigir a leitura truncada da lista ao vivo em dias de grande volume. O
  limite fixo de 12 rolagens deixava a extração parada em 266 partidas quando o
  contador do PackBall passava de 300. A rolagem agora é calculada pelo total
  esperado, permanece limitada e encerra cedo quando completa, sem abrir abas
  ou criar tentativas adicionais de login. Um teste com 320 partidas protege o
  cenário e a suíte completa passou a 962 testes. Em produção, dois ciclos
  consecutivos leram 314/314; o segundo fechou com API saudável, watchdog
  saudável, nenhuma pausa preventiva e nenhum bloqueio de fonte.
- [x] Tornar o rollback de capacidade do PackBall realmente conservador. Duas
  definições duplicadas faziam a última configuração permitir mais acessos que
  o ritmo normal. A configuração ficou única (26 segundos e teto 7 por janela)
  e o próprio controle agora recusa iniciar se um rollback reduzir o intervalo
  efetivo ou aumentar o teto de navegações. A suíte passou a 964 testes e o
  pré-reinício validou configuração, sessão, banco, API, Telegram e backups.
  Após reinício controlado, o primeiro ciclo foi fechado preventivamente
  durante a inicialização e o seguinte comprovou 321/321 partidas, API
  saudável, nenhuma pausa e nenhum bloqueio de fonte.
- [x] Diagnosticar a repetição ocasional da lista sem acelerar o PackBall. A
  telemetria real mostrou uma primeira renderização com contador 320 e somente
  8 linhas, seguida por 318/318 após nova navegação. Uma tentativa experimental
  de repetir apenas a varredura no mesmo DOM foi testada, mas uma ocorrência
  real continuou em 12 linhas; ela foi refutada e removida. Permanecem a
  telemetria por tentativa e a confirmação conservadora anterior, sem custo
  adicional. Os ciclos observados continuaram consistentes e o experimento de
  ritmo recuperou para aprovado, com retenção de fluxo de 76,51% ante mínimo
  de 75% e retenção temporal superior à base.
- [x] Desacoplar a odd asiática FT da API-Football da navegação de odds do
  PackBall. A auditoria encontrou 1.890 estruturas `Asian Corners` persistidas,
  mas a complementação da API era descartada sempre que o agendador não abria
  a aba de odds do site. A API agora pode anexar sua resposta global cacheada
  independentemente dessa navegação, preservando minuto 15–87, frescor,
  preferência por uma linha PackBall válida e todos os bloqueios do motor. Não
  há novo acesso ao PackBall. A suíte completa passou a 965 testes; a anexação
  real permanece condicionada à oferta da API para a fixture processada.
- [x] Priorizar, dentro dos espaços de coleta já existentes, partidas que já
  possuem uma oferta válida de `Asian Corners` no cache global da API-Football.
  A consulta é compartilhada com a anexação individual, respeita validade e
  cota, não abre partidas adicionais no PackBall e nunca contorna as
  prioridades de vencimento do Gol HT. A suíte completa passou a 967 testes.
  No primeiro ciclo real, a lista fechou em 337/337, a API identificou 88
  fixtures com oferta válida, 80 delas estavam na fila e uma oportunidade foi
  garantida entre as quatro primeiras análises. As quatro tarefas tiveram odds,
  a API permaneceu saudável e nenhuma navegação extra foi feita no PackBall.
  O segundo ciclo confirmou 336/336 em uma única leitura, repetiu a prioridade
  asiática no top 4, recuperou janelas temporais de 5 e 15 minutos e fechou sem
  qualquer bloqueio de fonte.
- [x] Fechar o ciclo entre a prioridade asiática e a anexação efetiva da odd.
  Antes, a fila reconhecia `Asian Corners`, mas o processamento ainda podia
  esperar o motor pedir o mercado antes de anexar a própria odd. A indicação
  cacheada agora autoriza a consulta da fixture já associada, preservando
  minuto, frescor, linha, qualidade e todos os bloqueios do motor. A telemetria
  separa prioridades processadas, anexações reais e prioridades sem anexo. A
  suíte completa passou a 969 testes. Em produção, um ciclo anexou três ofertas
  reais (linhas 4,5, 8,5 e 9,5); após o reinício final, dois ciclos consecutivos
  fecharam com 3/3 anexações, zero sem anexo, listas 180/180 e 172/173 durante
  transição dinâmica, API saudável, nenhuma navegação extra no PackBall e o
  segundo ciclo sem qualquer bloqueio de fonte. Linhas que ainda exigem mais
  de um escanteio continuam corretamente rejeitadas e não inflam a calibração.
- [x] Priorizar linhas asiáticas FT que realmente possam vencer com um único
  escanteio, sem relaxar o motor. A API expõe agora a oferta por fixture no
  mesmo cache global; o lote detalhado cruza a linha com `Corner Kicks` dos
  dois times e só marca o alvo quando `total atual <= linha <= total + 0,5`.
  Jogos com oferta asiática passaram a ocupar vagas dentro do mesmo lote de 40
  detalhes, sem elevar as duas chamadas máximas do lote nem navegar mais no
  PackBall. A suíte passou a 971 testes. Em produção, 25 e 24 jogos asiáticos
  entraram nos dois primeiros lotes; os dois ciclos anexaram 3/4 e 3/3 ofertas,
  a API permaneceu saudável e o segundo fechou sem bloqueios. Nenhuma linha
  atendia ao alvo de um escanteio — as diferenças observadas eram de 2,5 a 9 —
  e o bot corretamente registrou zero em vez de fabricar oportunidade.
- [x] Criar uma hipótese prospectiva separada para `Asian Corners` que exige
  múltiplos escanteios, sem modificar fingerprints, regra oficial ou histórico
  imutável. O estudo `exploracao-asiatico-ft-multiplos-v1` exige minuto 20–70,
  nota >=75, qualidade >=85, histórico de 5 minutos, atividade recente, odd
  operacional e distância máxima de 3,5 cantos. O estado é sempre `simulacao`,
  fica excluído da calibração oficial e possui teste explícito que impede sua
  seleção pelo Telegram. A suíte passou a 974 testes e o pré-reinício confirmou
  todas as linhagens oficiais intactas. Em dois ciclos reais, API e PackBall
  ficaram saudáveis e o segundo fechou 158/158 sem bloqueios; nenhum caso
  cumpriu todos os gates, portanto nenhuma amostra foi fabricada. A hipótese
  permanece ativa aguardando a primeira decisão prospectiva elegível.

### Validação futura isolada da exploração de gols — 08/08/2026

- [x] Congelar `exploracao-atividade-gols-v1` como desenvolvimento após 43
  resultados conhecidos de Gol FT, sem promovê-la para sinais oficiais.
- [x] Iniciar `exploracao-atividade-gols-validacao-v2` com a mesma definição,
  contabilizando somente jogos futuros e separando Gol FT de Gol HT.
- [x] Exigir ao menos 30 resultados futuros por mercado antes de liberar uma
  revisão independente; nenhuma aplicação automática ou envio ao Telegram.
- [x] Pré-registrar antes do primeiro resultado futuro a política estatística
  `avaliacao-exploracao-gols-v1`: além de 30 resultados por mercado, uma
  evidência favorável exige ROI e lucro positivos e limite inferior do IC95
  do ROI acima de zero. A política possui hash e gatilhos imutáveis no SQLite;
  resultado favorável libera somente revisão independente, nunca promoção ou
  Telegram automático. Registrada em 08/08/2026 13:46:41 com a V2 ainda em
  0 resultados resolvidos.
- [x] Garantir independência por partida, mercado e versão da exploração no
  próprio SQLite. Uma trava `BEFORE INSERT` impede novas repetições sem apagar
  legado, e o relatório usa `ROW_NUMBER` para deduplicação defensiva caso um
  banco antigo já contenha duplicatas. A auditoria real confirmou 56 decisões,
  56 partidas únicas e zero duplicidades; os resultados históricos permaneceram
  FT 28/15 (ROI +9,37%) e HT 8/5 (ROI +0,92%).
- [x] Tornar imutável cada decisão experimental após a inserção. Gatilhos do
  SQLite bloqueiam qualquer `UPDATE` ou `DELETE` do sinal sombra; resultados e
  revisões continuam na cadeia auditável separada. A retenção foi testada para
  preservar tanto a exploração antiga quanto seu snapshot, inclusive após 400
  dias, sem impedir a migração de bancos legados.
- [x] Eliminar o spam de alertas de validação causado por métricas na fronteira
  do limite. Cobertura de odds/API, saturação e regressão de ritmo agora exigem
  três ciclos consecutivos; a recuperação também exige três ciclos saudáveis.
  A mesma causa oscilante respeita cooldown de seis horas e causas simultâneas
  são agrupadas. Falhas estruturais críticas continuam imediatas, e nenhuma
  trava de dados ou calibração foi relaxada.

### Coortes e observabilidade operacional — 09/08/2026

- [x] Descontinuar somente na avaliação ativa as duas hipóteses de Gol FT com
  corte fixo de odd 1,66, preservando suas definições imutáveis para auditoria.
  A validação `exploracao-atividade-gols-validacao-v2` permanece independente.
- [x] Versionar Próximo Gol como `sinais-v10e-proximo-gol-faixa-global-max75`,
  usando a faixa operacional comum de odds 1,40–2,50 e mantendo o minuto máximo
  75. As coortes antigas 1,66 foram preservadas e não se misturam à nova.
- [x] Padronizar odds do Telegram em duas casas decimais sem arredondar o valor
  persistido ou usado nos cálculos.
- [x] Corrigir o painel para reconhecer versões específicas ativas por mercado.
  Checkpoints de Gol HT, Próximo Gol e escanteios não aparecem mais como
  inativos quando são a exceção operacional vigente.
- [x] Reconciliar automaticamente intenções de alerta operacional abandonadas
  após interrupção. Registros antigos passam a `incerto`, nunca são reenviados
  cegamente e deixam de manter atenção permanente quando uma entrega posterior
  comprova a recuperação do mesmo destino. A ambiguidade permanece auditável.
- [x] Impedir que uma sequência concentrada em poucos dias ou ligas seja
  promovida como sinal oficial. Além dos 100 resultados independentes e dos
  critérios estatísticos existentes, a janela oficial congelada precisa cobrir
  no mínimo 7 datas distintas e 5 ligas. O bloqueio é exclusivo da entrega
  oficial: não apaga amostras, não reinicia calibrações e não interrompe as
  simulações. O painel mostra amostra, dias, ligas e o motivo do bloqueio.
- [x] Tornar a parada de manutenção cooperativa durante o ciclo. O monitor
  verifica o pedido após a lista Ao Vivo, entre consultas de liquidação, após o
  enriquecimento da API, entre cada partida detalhada e durante a espera do
  próximo ciclo. A tarefa em andamento termina de forma atômica e os alertas
  ainda não revalidados são invalidados antes do fechamento. Isso reduz a
  espera máxima normal de um ciclo completo para uma única navegação, sem
  encerramento forçado nem risco desnecessário ao SQLite. No teste real, a
  versão anterior levou 141 segundos para encerrar; após carregar a proteção,
  o mesmo pedido encerrou monitor e navegador em 32,6 segundos, com estado
  final `encerrado` e sem processo forçado.
- [x] Separar do contador efetivo as partidas explicitamente fora do tempo
  regulamentar (`Prorrogação`, `ET`, pênaltis/PEN). Elas continuam visíveis no
  contador bruto e no diagnóstico, mas não bloqueiam jogos regulamentares nem
  entram nos mercados do bot. Estados novos ou ambíguos não são descontados e
  continuam fechando o ciclo. A correção não cria navegações adicionais. Após
  o reinício, os ciclos reais fecharam 133/134 e 135/136 como transições
  dinâmicas comprovadas; o segundo terminou com API saudável, zero bloqueio de
  fonte e nenhuma linha fora do tempo regulamentar presente naquele instante.
- [x] Eliminar a perda transitória do primeiro ciclo após reinício. O monitor
  agora aguarda, antes de abrir o PackBall, um espelho novo e persistido do
  watchdog; a espera é limitada, interrompível por manutenção e não relaxa os
  gates usados no envio. A resposta real do endpoint gratuito `/status` da
  API-Football passou a confirmar sua saúde mesmo quando a lista de fixtures
  vem do cache, evitando sacrificar o primeiro ciclo. Indicadores históricos
  do watchdog continuam alertando, mas não bloqueiam um ciclo cuja API,
  PackBall, processos e dados atuais estejam saudáveis. A lista também deixou
  de aceitar zero jogos sem contador explícito: ela recarrega e falha fechada
  se não conseguir provar a aba Ao Vivo. A suíte passou a 1.006 testes. No
  reinício real de 09/08/2026, a supervisão liberou a navegação em cerca de 7
  segundos e o primeiro ciclo fechou 109/109, com quatro partidas detalhadas,
  quatro com odds, API saudável, zero falhas e zero bloqueios de fonte.
- [x] Restaurar o maior ritmo PackBall já comprovado sem pausas: distribuição
  uniforme de aproximadamente 21,929 segundos e teto global de 28 navegações
  por 10 minutos, sempre em uma única aba. O rollback automático permanece
  mais conservador, em 24 navegações por 10 minutos, caso o site apresente o
  primeiro sinal de excesso. O ciclo real validado operou nesse regime sem
  bloqueio; a duração observada por partida (aproximadamente 41 segundos) foi
  maior que o intervalo mínimo, mostrando que o carregamento detalhado, e não
  o limitador, é o gargalo atual.
- [x] Tornar também a espera entre verificações do watchdog interrompível por
  manutenção. O intervalo de 60 segundos passou a ser dividido em passos de
  um segundo, sem mudar a frequência normal das verificações. Isso preserva a
  recuperação automática e elimina a espera imprevisível para atualizações.
  A suíte passou a 1.007 testes e a parada real, após carregar a mudança,
  encerrou monitor e watchdog de forma limpa em 1,31 segundo, sem finalização
  forçada nem perda de estado. O sistema foi religado ao final.
- [x] Auditar se estatísticas e odds poderiam ser extraídas em uma única rota
  para dobrar a capacidade sem aumentar solicitações. Um diagnóstico temporário
  foi executado dentro da navegação de odds já existente, sem criar acessos
  extras, em três partidas reais de ligas diferentes. Em todas, a rota de odds
  apresentou apenas `Expectativa de escanteios` e `Média de escanteios`; não
  continha pressão, chutes ou ataques. A tentativa de unificação foi rejeitada
  por evidência, pois apagaria dados essenciais do motor. O diagnóstico foi
  removido após a medição e a suíte permaneceu com 1.007 testes aprovados. As
  duas navegações por partida são, portanto, necessárias no layout atual; o
  ganho futuro deve vir de fonte estruturada ou mudança comprovada do site.
- [x] Corrigir aliases comprovados na associação PackBall/API-Football sem
  ampliar a comparação aproximada de forma perigosa. Consultas controladas ao
  provedor confirmaram os confrontos `Baranovichi x Bate Borisov` (fixture
  1525935) e `MVV x Jong Utrecht` (fixture 1551743), enquanto o PackBall usa
  `Baranovichi x BATE` e `MVV Maastricht x Jong FC Utrecht`. A normalização
  agora reconhece somente siglas explicitamente grafadas em maiúsculas e
  contidas como palavra inteira no outro nome; placar, minuto, categoria,
  segundo time e margem entre candidatos continuam obrigatórios. Palavras
  comuns como `United` não recebem esse tratamento. Quando não há associação,
  o diagnóstico passa a persistir os três candidatos nominais mais próximos,
  permitindo distinguir um alias futuro de uma partida sem cobertura. A busca
  do provedor não encontrou `AD Pemba`, portanto `Ferroviário Maputo x AD
  Pemba` permaneceu corretamente sem alias inventado. A suíte completa passou
  a 1.010 testes aprovados. Após o reinício, o primeiro ciclo real confirmou
  79/79 partidas na lista, quatro jogos detalhados, quatro associações API,
  quatro coletas de odds, API saudável, zero falha de cache, zero bloqueio de
  fonte e nenhum bloqueio do PackBall.
- [x] Transformar a melhor pista temporal atual de Gol FT em uma hipótese
  prospectiva auditável, sem promover o resultado exploratório. A divisão
  histórica móvel encontrou `janelas.5.escanteios_por_minuto >= 0,1786`: no
  desenvolvimento foram 29 green/15 red e ROI +11,45%; na fatia exploratória,
  21 green/4 red e ROI +37,78%. Como essa busca testou vários cortes e sua
  divisão muda com a chegada de dados, ela foi explicitamente classificada
  apenas como geradora de hipótese. A definição
  `gol_ft_ritmo_escanteios_5m_v1_20260809` foi congelada no SQLite em
  09/08/2026 13:20:46, vinculada ao fingerprint de `sinais-v6`, iniciando em
  zero resultados. Ela exige 30 casos selecionados futuros, 10 controles
  contemporâneos, ROI/lucro positivos e limite inferior do IC95 da diferença
  de ROI acima de zero. Não altera regra nem envia sinal automaticamente.
  A supervisão passou a preservar também a versão, a linhagem de cada mercado
  e a lista real de pistas aptas, eliminando a inconsistência visual que
  mostrava detalhe apto com cabeçalho vazio. A integridade confirmou oito
  hipóteses imutáveis válidas e a suíte completa passou a 1.012 testes.
- [x] Limitar o crescimento do cache persistente da API-Football pelo TTL real
  de cada categoria. A implementação anterior só apagava registros com mais de
  24 horas, embora detalhes ao vivo e eventos deixassem de ser reutilizáveis em
  60 segundos; a auditoria encontrou 873/1.073 itens expirados e 94,51 MB sem
  utilidade operacional, dos quais 87,5 MB eram detalhes ao vivo. A limpeza
  agora ocorre dentro da própria transação de gravação, no máximo uma vez a
  cada cinco minutos, preservando catálogo, contexto pré-jogo e qualquer item
  ainda válido conforme seu TTL. Tabelas históricas de partidas, snapshots,
  odds, sinais e resultados não são tocadas. Na limpeza controlada, o cache
  caiu de 98,64 MB para 4,13 MB, 25.542 páginas ficaram disponíveis para
  reutilização interna e o `quick_check` permaneceu `ok`. Após o reinício e
  novas gravações reais, o cache ficou em 202 itens, 4,56 MB e zero expirados.
  A suíte completa passou a 1.014 testes aprovados.
- [x] Concluir com medição justa o experimento do ritmo máximo seguro do
  PackBall. Pausas explicitamente registradas como manutenção passaram a ser
  descontadas apenas da janela de tempo do teste; carregamentos lentos, filas e
  atrasos normais continuam contando. Isso removeu 18,45 minutos de nove
  intervenções técnicas sem mascarar desempenho operacional. Após 12 ciclos e
  45 partidas detalhadas, o regime `21,929s / 28 acessos em 10min` foi aprovado:
  fluxo de 9,71 partidas por 10 minutos contra 9,26 da base (retenção 104,86%),
  cobertura temporal de foco 66,67% contra 53,85% (retenção 123,81%), odds em
  100% das partidas processadas, zero pausa do PackBall e nenhum motivo de
  regressão. A configuração máxima comprovada foi mantida. A nova distinção
  entre manutenção e lentidão possui teste positivo e contraprova sem marcação;
  a suíte completa passou a 1.015 testes.
- [x] Preparar o núcleo para instalação reproduzível em outro computador e,
  futuramente, exposição por uma API própria. As três dependências diretas
  foram fixadas nas versões atualmente comprovadas e um lock completo passou
  a registrar as 12 dependências diretas e transitivas. O pré-voo verifica
  Python 3.11+, presença e versão exata de cada pacote, validade e SHA-256 do
  lock; qualquer divergência impede o reinício em vez de produzir comportamento
  diferente silenciosamente. O ambiente real foi confirmado com Python
  3.14.6, 12/12 pacotes corretos, lock
  `782fa6a596055a888563a3fdc2930ed695899f86cc72c32843102acfbbc97143` e
  pré-voo integral pronto, sem falhas. O procedimento de instalação separa
  explicitamente código de credenciais, sessão e banco. A suíte completa
  passou a 1.019 testes.
- [x] Separar pendencias tecnicas de espera estatistica na auditoria de
  prontidao. Cada requisito pendente agora recebe uma categoria explicita:
  `pendencia_tecnica`, `aguardando_dados_reais`, `modelo_reprovado` ou
  `dependencia_externa`; o resumo tambem informa `falha_tecnica_ativa`. Na
  verificacao real de 09/08/2026, monitor e watchdog estavam ativos, nao havia
  falha tecnica, cinco requisitos aguardavam dados reais e Gol FT permanecia
  corretamente identificado como modelo reprovado. A suite completa passou a
  1.020 testes.
- [x] Tornar observavel a fila prospectiva das hipoteses sombra. O avaliador
  agora diferencia resultados liquidados de candidatos ainda pendentes, sem
  incluir estes ultimos no ROI nem no tamanho da amostra. O painel informa o
  total pendente e sua divisao entre corte e controle. A primeira leitura real
  da hipotese `gol_ft_ritmo_escanteios_5m_v1_20260809` mostrou zero resultados
  liquidados e um controle aguardando liquidacao, em vez de aparentar ausencia
  total de atividade. A suite completa passou a 1.022 testes.
- [x] Identificar a origem exata de bloqueios operacionais nas liquidacoes.
  O gate fail-closed agora diferencia runtime aguardando reinicio, processos
  inativos, espelho ou persistencia do watchdog, API-Football nao confirmada,
  pausa preventiva do PackBall e degradacao anterior no mesmo ciclo. Os campos
  `motivo_bloqueio` e `fonte_bloqueio` seguem junto da telemetria, evitando
  interpretar manutencao local como queda da API. A suite completa passou a
  1.023 testes.
- [x] Expor a recuperacao prospectiva de mercados reprovados na prontidao.
  Cada mercado agora lista suas hipoteses sombra com corte, estado, amostras do
  grupo selecionado e controle, pendencias, ROI, delta e intervalo de confianca,
  sempre com aplicacao automatica desabilitada. Assim, Gol FT continua
  corretamente reprovado para uso oficial, mas o caminho de recuperacao fica
  mensuravel pela mesma auditoria consumivel por uma futura API. Na leitura
  real, havia duas hipoteses em formacao e tres refutadas. A suite completa
  passou a 1.024 testes.
- [x] Profissionalizar o diagnostico do funil recente sem alterar regras. O
  relatorio somente-leitura agora separa observacoes e partidas unicas, mostra
  gargalos por mercado e classifica cobertura de odds, cobertura temporal,
  qualidade, fontes e criterios da regra. Apenas bloqueios reais sao exibidos;
  motivos informativos deixaram de aparecer como se fossem rejeicoes. Para nao
  tratar a primeira visita naturalmente sem historico como falha persistente,
  os gargalos usam somente a observacao mais recente de cada mercado/partida.
  A leitura confirmou que a regra atual de Proximo Gol usa a faixa global; a
  mencao a 1,66 existia somente na coorte antiga. A suite passou a 1.025 testes.
- [x] Incluir todos os pontos de recuperacao na observabilidade de disco. A
  metrica anterior projetava apenas banco e WAL (aproximadamente 809 MB), embora
  37 backups SQLite ocupassem outros 18,5 GB. O watchdog agora mede banco, WAL e
  backups, informa quantidade e tamanho dos arquivos e reinicia a serie
  historica ao mudar a definicao da metrica, evitando um falso pico de
  crescimento. Nenhum backup foi removido nem a retencao foi reduzida. A suite
  completa passou a 1.026 testes.
- [x] Auditar a aplicacao da retencao sem remover arquivos e corrigir a ordem
  de antiguidade. Backups com nomes descritivos eram ordenados lexicalmente, o
  que poderia selecionar um arquivo mais novo no lugar do mais antigo. A data
  comprovada no manifesto passou a ser a fonte primaria, com `mtime` como
  fallback. A auditoria real encontrou um unico excedente, o backup
  `pre_migracao_linhagem_20260721_2129.db` de 78,2 MB; ele foi somente marcado
  para revisao, pois a aplicacao automatica permanece desligada. A suite passou
  a 1.027 testes.
- [x] Implementar recuperacao automatica e conservadora do SQLite no inicio.
  Corrupcao comprovada ou ausencia inesperada do banco agora seleciona o ponto
  compativel mais recente por manifesto, valida checksum, esquema e modelos,
  testa uma copia temporaria e somente entao faz a troca atomica. O banco
  danificado, WAL e SHM ficam preservados em quarentena; processos ativos,
  backups adulterados e ausencia de copia valida bloqueiam a operacao sem
  substituir dados. O ultimo reparo fica persistido e visivel no status. Os
  cenarios de corrupcao, fallback para backup anterior, banco ausente e falha
  segura foram testados sem tocar na base real. A suite completa passou a
  1.035 testes.
- [x] Notificar no Telegram cada recuperacao real do banco exatamente uma vez.
  O watchdog usa o evento persistido pela restauracao, registra tentativa e
  retry de dois minutos e reconcilia a confirmacao existente no SQLite apos
  uma interrupcao, evitando duplicar o aviso. O status mostra se a confirmacao
  esta pendente, entregue ou em erro. Ausencia do evento nao gera mensagem. A
  suite completa passou a 1.038 testes.
- [x] Detectar corrupcao do SQLite durante a operacao e encadear a recuperacao
  sem intervencao manual. O watchdog executa `quick_check` a cada dez minutos,
  diferencia dano comprovado de bloqueio ou indisponibilidade transitoria e
  somente no primeiro caso solicita manutencao, alerta o Telegram e encerra o
  fluxo antes das demais auditorias. O alerta abre o banco em modo estrito e
  nao cria uma base vazia quando o arquivo desapareceu. A tarefa agendada pode
  entao iniciar o preflight, restaurar atomicamente o backup valido e preservar
  a base anterior em quarentena. O encadeamento completo foi provado em banco
  isolado; a suite completa passou a 1.046 testes.
- [x] Tornar a auditoria periodica do banco um requisito formal de prontidao.
  O relatorio profissional exige estado integro, verificacao com no maximo 20
  minutos e ausencia de recuperacao pendente; evidencia antiga, ausente ou
  corrompida aparece como pendencia tecnica e impede declarar operacao
  profissional. A coleta real exporta diretamente o espelho persistido pelo
  watchdog. A suite completa passou a 1.048 testes.

## Politica permanente de sombra e substituicao de metodos — 12/08/2026

- Todo metodo, versao ou fingerprint novo nasce em **sombra**, sem entrada nem
  resultado no Telegram. O gateway usa bloqueio por padrao: somente uma
  allowlist versionada e explicita pode entrar no grupo de simulacoes.
- V3 Gol FT permanece exclusivamente em sombra. V2-controle Gol FT foi
  autorizado no grupo apenas como **SIMULACAO — NAO APOSTAR**; seu historico
  anterior nao sera enviado retroativamente e ele nao foi promovido a oficial.
- Gol FT v6 e Gol HT v8b permanecem em sombra por desempenho negativo. Proximo
  Gol v10e, Proximo Escanteio v9c e Escanteio Asiatico FT v9d permanecem no
  grupo de simulacoes, ainda sem classificacao oficial.
- Um challenger nunca substitui automaticamente o metodo ativo por causa de
  uma sequencia curta. A comparacao usa uma coorte futura pre-registrada, regra
  e fingerprint imutaveis, unidade fixa, resultados independentes e a mesma
  janela cronologica do controle ativo.
- Para ser considerado realmente superior, o challenger precisa de pelo menos
  100 resultados futuros validos, ROI positivo, limite inferior do intervalo
  de confianca de 95% do ROI acima de zero, holdout final de pelo menos 50
  resultados com ROI positivo e superioridade sobre o ativo na mesma janela.
  Fontes, odds, liquidacao e proveniencia tambem precisam estar integras.
- Mesmo cumprindo os criterios, a troca exige uma nova versao de politica e
  uma decisao registrada. Nao existe promocao ou substituicao automatica.

## Supervisao formal Bet365/TheStats — 29/08/2026

- [x] Incluir a fonte complementar Bet365/TheStats na auditoria profissional.
  A prontidao agora compara a configuracao persistida com o ultimo ciclo real,
  exige modo oficial fail-closed quando autorizado, confirma que o PackBall
  continua primario e detecta divergencias de Telegram, calibracao ou gate de
  sinal. Coleta sombra e desativacao intencional continuam estados coerentes;
  uma fonte oficial sem diagnostico inicia como sincronizacao, sem inventar
  disponibilidade. O primeiro ciclo real auditado pareou 16 de 37 jogos,
  persistiu 503 ofertas, executou 33 chamadas e terminou sem erro. A suite
  completa passou a 1.693 testes e a auditoria final confirmou operacao pronta,
  fonte pronta e nenhuma falha tecnica ativa.

- [x] Separar esgotamento normal da cota API-Football de defeito tecnico. A
  prontidao agora mostra consumo, limite seguro, saldo e proximo reset UTC;
  saldo zero vira `aguardando_reset_cota`, classificado como dependencia
  externa, enquanto contador corrompido, cache ou pareamento incoerentes ainda
  degradam tecnicamente o sistema. Nenhum limite foi ampliado e os gates de
  confirmacao permanecem fechados sem cota. Na virada real de 30/08 UTC, o
  contador passou de 7.000/7.000 para 21/7.000 e o provedor confirmou 7.479
  requisicoes restantes; o espelho do watchdog convergiu no ciclo seguinte.
  A suite completa passou a 1.697 testes.

- [x] Tornar explicita a diferenca entre entrega real em canal experimental e
  prova de rota oficial no Telegram. A auditoria encontrou 708 mensagens de
  entrada confirmadas por `message_id`: 493 pertenciam a sinais com status
  interno aprovado e 215 a simulacoes, mas todas usavam destino marcado como
  teste. Elas agora aparecem no painel sem serem promovidas retroativamente;
  a prova oficial continua zero ate existir um metodo calibrado elegivel e uma
  entrega no destino oficial. A suite completa passou a 1.698 testes e a
  leitura real terminou com operacao pronta e nenhuma falha tecnica ativa.

- [x] Garantir a repeticao do pre-live quando uma falha temporaria ocorre no
  fim da janela normal do slot. Antes, uma tentativa iniciada dentro das tres
  horas permitidas podia agendar o retry cinco minutos depois e ficar
  imediatamente inelegivel por ultrapassar a propria janela. O agendador agora
  concede uma extensao curta e limitada de 30 minutos somente para repeticoes
  temporarias, sem manter chamadas durante o restante do dia nem bloquear
  indefinidamente os horarios seguintes. O caso real das 17:00 repetiu as
  20:29 depois da renovacao da cota; a capacidade segura voltou de zero para
  6.874 chamadas. A suite completa passou a 1.700 testes. Depois da recarga,
  o PackBall concluiu um ciclo com 49 jogos, a API-Football voltou saudavel e
  a Bet365/TheStats entregou odds em 17 de 17 consultas. A auditoria final
  confirmou operacao pronta e nenhuma falha tecnica ativa.

- [x] Tornar permanente o diagnostico do fluxo das amostras ativas. A
  prontidao agora usa a contagem real de partidas do ultimo ciclo e o horario
  do candidato mais recente de cada mercado operacional para distinguir
  ausencia legitima de jogos de interrupcao do funil. Bracos raros continuam
  visiveis, mas nao degradam a operacao apenas por nao gerar candidato em vinte
  minutos; mercados de escanteios por periodo suspensos tambem nao produzem
  falso alarme. A suite completa passou a 1.704 testes. Depois da recarga do
  runtime, um ciclo real concluiu com 46 partidas, os cinco mercados ativos
  apresentaram fluxo recente, monitor, watchdog e pre-live ficaram ativos e a
  auditoria retornou operacao pronta, sem falha tecnica ativa.

## Referencia sem vig e frequencia do Proximo Gol — 08/09/2026

- [x] Corrigir a referencia de preco do mercado de Proximo Gol. Como esse
  mercado possui tres desfechos (Casa, Visitante e Sem gol), o sistema agora
  preserva obrigatoriamente as tres odds do mesmo snapshot e normaliza a
  probabilidade pela soma das tres probabilidades implicitas. Pares
  contraditorios entre fontes falham fechados; fonte e bookmaker declarados
  sao usados para desambiguar sem trocar mercado, selecao, odd, nota ou status.
  O rastro persistido passou para
  `valor-mercado-calibrado-conservador-v4`, e o gateway revalida o trio antes
  de qualquer entrega oficial.
- [x] Criar avaliacao historica somente-leitura do preco sem vig. O relatorio
  `avaliacao_probabilidade_sem_vig.py` reconstruiu exatamente 732 de 839
  estados independentes de Proximo Gol (87,25%). A populacao ampla nao mostrou
  vantagem comprovada: 381 greens e 351 reds, ROI de -4,95%, intervalo de 95%
  do ROI entre -11,78% e +1,87%. Portanto, favoritismo da casa de apostas nao
  sera usado isoladamente para ampliar sinais.
- [x] Cruzar a referencia de mercado com as duas rotas tecnicas estudadas. A
  regra estrita teve mercado completo em 8/8 entradas, mas somente 5 greens e
  3 reds. A hipotese balanceada teve referencia completa em 11/12 entradas;
  nessa cobertura foram 9 greens e 2 reds, ROI de +22,61%, mas o intervalo de
  95% ainda inclui retorno negativo. O resultado e promissor apenas para
  validacao prospectiva: aplicacao de sinais, Telegram e promocao automatica
  continuam desabilitados. O bot permaneceu em pausa manual durante todo o
  trabalho. A suite completa passou a 2.147 testes. Os testes de pre-live
  tambem passaram a isolar a configuracao do ambiente real, evitando falso
  erro quando o perfil operacional salvo difere do perfil exercitado no teste.

## Auditoria de edge por mercado sem mistura de coortes — 08/09/2026

- [x] Impedir que sinais oficiais, contrafactuais e exploracoes em sombra
  sejam somados para declarar vantagem. A avaliacao generica agora identifica
  a coorte de selecao e nunca marca edge quando a populacao e heterogenea.
  Isso corrigiu uma conclusao preliminar enganosa do Escanteio Asiatico FT,
  que misturava a politica oficial com duas exploracoes de multiplas linhas.
- [x] Criar `avaliacao_edge_escanteios_asiaticos.py`, somente leitura, com
  independencia por partida e coorte, liquidacao integral de green,
  half-green, void, half-red e red, pareamento Over/Under no mesmo snapshot,
  segmentacao por tipo de linha, fonte, liga e semana, alem de corte
  cronologico 70/30. Brier e desvio contra o mercado so usam linhas .5;
  linhas inteiras e de quarto sao julgadas pelo retorno efetivamente
  liquidado, sem serem falsamente convertidas em apostas binarias.
- [x] Auditar sem misturar a elegibilidade da regra com a entrega real do
  Escanteio Asiatico FT v9d. A regra produziu 41 partidas independentes
  elegiveis (34 greens, 5 reds e 2 voids; ROI +58,33%), mas somente 25 tiveram
  entrada realmente entregue (20 greens, 4 reds e 1 void; ROI +52,86%). A
  populacao primaria de decisao passou a ser a entregue. Seu holdout final tem
  apenas 7 jogos (5 greens e 2 reds), ROI +32,36%, com intervalo de 95% ainda
  cruzando zero. A evidencia continua promissora, mas insuficiente para alterar
  a regra: faltam 100 entregas e 30 no holdout com limite inferior positivo.
- [x] Criar `avaliacao_portfolio_edge.py` para as cinco rotas selecionadas no
  runtime. A versao inicial mostrou que Gol FT v11b e Gol HT v8c nao
  representavam os bracos experimentais realmente entregues; essa leitura
  legada deixou de ser usada como decisao dos mercados de gols. Nenhum mercado
  atende hoje simultaneamente amostra, preco justo, ROI e intervalo de
  confianca. A prontidao profissional expoe esse gate e impede declarar o
  portfolio completo enquanto o edge de cada mercado nao for comprovado.
  Nao houve promocao automatica, e o bot permaneceu pausado.

## Frequencia controlada do Proximo Gol — 08/09/2026

- [x] Separar o limiar de envio experimental do Proximo Gol do corte global.
  A regra tecnica permanece intacta em qualidade 100, pico de pressao 70,
  minuto maximo 75, odd abaixo de 2,00, conversao historica e tendencia de
  liga. Somente o segundo gate do canal de teste passou de 75 para 70 nesse
  mercado; os demais continuam em 75. Nos oito candidatos que haviam vencido
  todas as protecoes, quatro foram barrados apenas pelo antigo corte de 75 e
  terminaram em 3 greens e 1 red. Com o corte isolado, sete dos oito seriam
  encaminhaveis; o oitavo continuaria corretamente bloqueado por exposicao ja
  aberta na mesma partida.
- [x] Preservar o bloqueio de tendencia com amostra PackBall insuficiente. A
  coorte contrafactual desse motivo teve 27 jogos, 14 greens e 13 reds, ROI de
  -18,70%; afrouxa-la aumentaria volume justamente no segmento que perdeu.
  A politica de roteamento foi versionada como
  `roteamento-simulacoes-teste-v9`, com rollback operacional pela remocao de
  `PONTUACAO_MINIMA_PROXIMO_GOL_TESTE`. O bot permaneceu em pausa manual.

## Portfolio aderente aos metodos realmente entregues — 08/09/2026

- [x] Corrigir o painel de edge de Gol HT e Gol FT para avaliar as versoes que
  efetivamente chegam ao Telegram. A versao v3 le o identificador do metodo em
  `features_json`, exige entrega confirmada no canal de teste, ancora temporal
  registrada, linhagem homogenea e apenas a primeira entrada por
  partida/mercado. A regra-base antiga continua visivel somente como evidencia
  legada e nao decide mais o estado dos bracos ativos.
- [x] Alinhar o painel e a prontidao com a configuracao validada. O recurso FT
  contextual V2b deixou de ser lido diretamente do ambiente e so entra no
  portfolio quando a chave validada esta ativa e o circuit breaker persistente
  esta saudavel e aberto. A pontuacao isolada do Proximo Gol e as duas flags
  contextuais V2 tambem passaram por validacao fail-closed.
- [x] Medir o portfolio configurado em 08/09 sem misturar metodos desligados.
  Os bracos ativos sao HT antecipado, FT antecipado no 1o tempo e FT antecipado
  no 2o tempo. As amostras com referencia sem vig sao, respectivamente, 28,
  0 e 71; por isso todos permanecem em coleta e nenhuma mudanca de limite foi
  promovida. O painel exige validador prospectivo favoravel, pelo menos 95
  precos pareados, cobertura minima de 90% e limites inferiores positivos para
  ROI e residuo contra o mercado. A suite completa passou a 2.165 testes. O
  modo de manutencao permaneceu ativo e nenhum processo do bot foi iniciado.

## Protecao por metodo e nova leitura do Proximo Gol — 08/09/2026

- [x] Criar um circuit breaker persistente e isolado para cada braco de gol
  antecipado. HT, FT no 1o tempo e FT no 2o tempo podem ser suspensos
  separadamente; um resultado ruim nao desliga os outros mercados. A suspensao
  automatica exige pelo menos 95 resultados prospectivos, linhagem homogenea,
  decisao estatistica desfavoravel e limite superior do intervalo de 95% do
  ROI abaixo de zero. O estado e reversivel por comando explicito, gera aviso
  deduplicado e falha fechado se o arquivo persistido estiver corrompido.
- [x] Fazer o portfolio e a prontidao respeitarem o mesmo estado operacional
  usado pelo gateway do Telegram. Metodos suspensos ficam identificados como
  bloqueados e deixam de entrar na avaliacao de edge, sem desaparecer do
  diagnostico e sem promover substitutos automaticamente. Na leitura atual
  nao existe suspensao: os tres bracos configurados continuam liberados e
  formando amostra.
- [x] Reavaliar a baixa frequencia do Proximo Gol sem atribui-la apenas a nota
  do canal. Em 72 horas, o maior gargalo da melhor tentativa por partida foi o
  pico de pressao 70 (187 partidas), seguido da faixa de odd (151) e qualidade
  completa (121). A regra principal possui somente 8 resultados independentes,
  5 greens e 3 reds, com ROI de +0,45%; a exploracao mais ampla possui 86,
  52 greens e 34 reds, com ROI de -1,51%. Assim, a regra principal nao foi
  afrouxada indiscriminadamente. O corte de nota isolado permanece em 70 e a
  hipotese balanceada continua separada, silenciosa e prospectiva, relaxando
  somente pressao quando ha chute recente, dominio medio e odd curta.
- [x] Validar a integracao completa apos as mudancas. A suite passou a 2.173
  testes. O modo de manutencao continua ativo; nenhuma regra foi promovida e
  nenhum envio retroativo foi realizado.
- [x] Endurecer a prova de valor da hipotese balanceada sem endurecer sua
  geracao. A validacao v3 agora exige, alem de ROI total com IC95 inferior
  positivo e ROI positivo em desenvolvimento/holdout, cobertura de referencia
  sem vig de pelo menos 90% e residuo de acerto contra o mercado com IC95
  inferior positivo tanto no total quanto no holdout. ROI positivo sem preco
  comparavel nao pode mais ser rotulado como edge.
- [x] Corrigir a populacao decisoria de Proximo Gol e Proximo Escanteio no
  portfolio v4. Candidatos apenas aprovados internamente deixaram de inflar a
  amostra: agora contam somente entradas com entrega terminal confirmada,
  excluindo gateway, resultado e aviso de green antecipado. A leitura real
  caiu de 8 candidatos para 3 entradas de Proximo Gol (2 greens, 1 red, ROI
  -3,33%) e confirmou 16 entradas de Proximo Escanteio (12 greens, 4 reds, ROI
  +14,13%). Ambos continuam sem edge comprovado porque os intervalos de 95%
  cruzam zero. A suite completa passou a 2.176 testes; o bot permaneceu
  pausado.
- [x] Exigir replicacao cronologica do edge no portfolio v6, sem tornar o
  gerador de alertas mais rigido. Proximo Gol e Proximo Escanteio agora usam
  apenas entradas entregues, separam os primeiros 70% para desenvolvimento e
  os 30% finais para holdout e so podem ser considerados favoraveis com pelo
  menos 100 resultados totais, 30 no holdout, cobertura de preco sem vig de
  90% e limites inferiores positivos para ROI e residuo contra o mercado nas
  duas leituras. Os bracos ativos de gol antecipado usam a mesma prova com 95
  precos totais e 28 no holdout. Uma amostra completa que falhar nesses
  criterios passa a ser explicitamente marcada como vantagem nao comprovada
  ou nao replicada, em vez de permanecer indefinidamente como aguardando.
- [x] Validar a mudanca sem religar o servico. Os testes direcionados passaram
  em 93/93 e a suite completa em 2.178 testes. A leitura atual mantem zero
  mercados favoraveis para promocao manual: Proximo Gol tem 3 entregas,
  Proximo Escanteio 16, HT antecipado 28 precos e FT antecipado do 2o tempo
  71. O modo de manutencao permaneceu ativo e nao houve promocao automatica.
- [x] Fechar a divergencia entre o painel de edge e o gateway oficial. A
  avaliacao v7 agora oferece um gate por candidato que reconstrói somente a
  coorte entregue da versao exata prestes a ser enviada. O monitor consulta
  esse gate no instante do alerta e falha fechado com
  `edge_portfolio_nao_comprovado`; resultado de outra regra, mercado ou
  challenger em sombra nao pode autorizar a entrada. Simulacoes sem
  probabilidade calibrada continuam livres para formar amostra e nenhuma
  decisao promove uma regra automaticamente. Na leitura real, as cinco rotas
  atuais continuam corretamente bloqueadas para Telegram oficial por falta
  de edge completo/holdout.
- [x] Incluir todo o calculo do edge nos fingerprints de runtime e carteira.
  Alteracao em portfolio, referencia sem vig ou avaliacao asiatica agora exige
  reinicio coerente e abre epoca auditavel, evitando processo antigo com gate
  diferente do codigo em disco.
- [x] Reforcar a persistencia atomica encontrada durante a regressao ampla.
  Estado de uso da BetsAPI e sessao do PackBall passaram a usar temporario
  unico, cinco tentativas com backoff para bloqueio transitorio do Windows e
  limpeza garantida. A suite completa passou em 2.185 testes. O bot continuou
  pausado e nenhuma chamada externa ou envio Telegram foi executado.
- [x] Tratar a baixa frequencia do Proximo Gol sem reduzir a qualidade de
  dados. A regra precisa permanece inalterada (qualidade 100, pico de pressao
  70 e minuto maximo 75) e ganhou um braco complementar, separado e
  reversivel, para a faixa de pressao 55--69. Esse braco exige qualidade 100,
  odd 1,40--1,59, ao menos um chute recente do lado dominante, vantagem de
  pressao media de 10 e pontuacao tecnica minima 60. No recorte historico
  gerador da hipotese houve 12 entradas independentes, 9 greens e 3 reds
  (75%; ROI +12,39%), mas a amostra ainda e pequena: por isso a V10i pode ser
  exibida somente como `Proximo Gol balanceado — grupo de teste`, nunca como
  alerta oficial, sem calibracao nem promocao automatica. O rollback e
  `PROXIMO_GOL_BALANCEADO_GRUPO_ATIVO=0`.
- [x] Versionar tambem o roteamento e a nota minima desse braco na carteira
  operacional. Os testes direcionados passaram em 117/117 e a suite completa
  em 2.188 testes. O modo de manutencao permaneceu ativo e nenhum processo do
  bot ficou em execucao.

## Validacao de preco nos mercados ao vivo — 09/09/2026

- [x] Criar uma auditoria somente leitura para verificar se cada alerta obteve
  valor real contra a cotacao posterior, alem do resultado green/red. A leitura
  compara exatamente mercado, linha, fonte e bookmaker entre 2 e 10 minutos
  apos a entrega; usa probabilidades sem vig e valor terminal 1/0 quando o
  contrato ja foi liquidado. Linhas asiaticas inteiras ou fracionadas sem
  modelagem segura de push/meio-green ficam excluidas.
- [x] Cobrir Gol FT, Gol HT, Proximo Gol, Proximo Escanteio e Escanteios FT
  asiatico sem alterar geradores, Telegram ou gates oficiais. Na leitura atual,
  218 de 999 entregas possuem comparacao exata (21,82%). O residuo medio total
  foi +6,84 pontos percentuais, mas a mediana foi -3,66 e o holdout de 65 sinais
  ainda cruzou zero no IC95 (-0,07 a +10,18 pontos). Portanto, a leitura geral
  nao autoriza declarar edge nem afrouxar os filtros.
- [x] Separar a evidência por mercado. Gol HT teve 96 comparacoes e media de
  +7,12 pontos com IC95 positivo no conjunto completo; Gol FT teve 73 e IC95
  cruzando zero; Proximo Gol teve 32 e IC95 cruzando zero; Proximo Escanteio e
  Escanteios FT tiveram apenas 7 e 10 comparacoes, respectivamente. A auditoria
  foi integrada a prontidao profissional como diagnostico informativo, sem
  promocao automatica. Os 116 testes direcionados passaram e o bot permaneceu
  em manutencao.
- [x] Separar falta de cotacao de resultado ruim na auditoria V3. Cada mercado,
  versao, fonte e bookmaker agora preserva o total consultado, comparaveis,
  cobertura e motivos de exclusao, alem das metricas de valor. A janela movel
  das ultimas 100 entregas mostrou 71% de cobertura, contra 21,82% no legado
  completo, evidenciando melhora real da persistencia recente sem apagar a
  lacuna historica. Nas ultimas 30 entregas de cada mercado, a cobertura foi
  76,67% no Gol HT, 70% no Gol FT, 43,33% no Proximo Gol, 23,33% no Proximo
  Escanteio e 20% nos Escanteios FT asiaticos. Esses numeros orientam a coleta;
  nao liberam mercado nem alteram sinal.
- [x] Fechar prospectivamente a principal lacuna da auditoria de preco. Uma
  entrega de Gol HT, Gol FT, Proximo Gol, Proximo Escanteio ou Escanteios FT
  agora agenda uma unica cotacao posterior a partir de dois minutos e antes de
  dez minutos. O agendador compara o instante-alvo com a ultima odd persistida,
  portanto nao repete a visita depois de uma coleta bem-sucedida e tenta de
  novo se a coleta falhar. Entradas originadas em fonte auxiliar preservam o
  mercado que precisa ser solicitado novamente.
- [x] Isolar essa revisita da geracao de sinais. Quando o jogo nao estaria
  naturalmente vencido para uma analise normal, a tarefa apenas persiste o
  snapshot/odds e permite liquidar sinais existentes; nao salva candidato novo
  nem chama o despachante Telegram. Uma visita que ja seria normal continua
  com o comportamento normal. O recurso e auditavel na carteira e reversivel
  por `ACOMPANHAMENTO_PRECO_POS_ALERTA_ATIVO=0`. A suite completa passou em
  2.203 testes, com manutencao manual preservada e sem processo do bot iniciado.
- [x] Tornar a nova cobertura observavel por ciclo e por periodo. O monitor
  registra quantos acompanhamentos de preco foram agendados, processados,
  coletaram alguma odd e persistiram snapshot; o funil calcula as taxas sem
  confundir coleta disponivel com pareamento exato do contrato, que continua
  sendo responsabilidade da auditoria CLV V3.
- [x] Detectar indisponibilidade persistente da cotacao posterior sem criar um
  novo gate de sinal. O watchdog ignora ciclos sem demanda, tolera ate duas
  coletas aplicaveis degradadas e gera aviso operacional na terceira falha
  consecutiva. Uma coleta completa zera a sequencia. O diagnostico declara
  explicitamente `altera_sinais=false`; portanto nao aprova, bloqueia ou
  promove mercado e serve apenas para proteger a qualidade da evidencia.
- [x] Validar a instrumentacao completa sem executar o servico. Os testes
  direcionados passaram em 563/563 e a suite completa em 2.207/2.207. O modo
  de manutencao permaneceu ativo durante a verificacao.

## Cadencia controlada do Proximo Gol — 09/09/2026

- [x] Confirmar no banco, sem atribuir a raridade apenas a falha de coleta, o
  motivo da baixa cadencia. Nas 72 horas anteriores a pausa, a melhor tentativa
  por partida de Proximo Gol foi bloqueada pela pressao pico minima em 160
  partidas e pela faixa de odd em 131; a odd ao vivo estava ausente em 62. A
  regra oficial nao foi afrouxada com base nessa leitura retrospectiva.
- [x] Preparar corretamente a validacao prospectiva do braco balanceado V10i.
  A definicao imutavel foi registrada no SQLite em 09/09/2026 13:19:32, com
  coorte iniciando em 0/40; nenhum resultado anterior entrou como confirmacao.
  O braco relaxa somente a pressao de 70 para a faixa 55--69 quando preserva
  qualidade 100, chute recente, dominio medio de 10, nota 60, minuto maximo 75
  e odd 1,40--1,59. Telegram oficial e promocao automatica permanecem falsos;
  o destino permitido e somente o grupo de teste.
- [x] Tornar ativacao, roteamento e nota do balanceado explicitamente
  auditaveis na configuracao. O grupo de teste agora falha no pre-voo se for
  ligado com o gerador desligado, e valores nao binarios ou nota fora de 0--100
  sao rejeitados. O status mostra coorte, G/R/P, ROI, candidatos por 24 horas e
  gargalo interno, usando dinamicamente a faixa de odd vigente da regra.
- [x] Criar antes da ancora o ponto local verificado
  `pre_reinicio_20260909_131852.db.gz`, com manifesto e checksum. A suite
  completa passou em 2.210/2.210. O monitor permaneceu em manutencao e nenhum
  alerta foi enviado durante a alteracao.
- [x] Proteger prospectivamente o grupo de teste contra uma degradacao clara
  sem contaminar a coorte fixa. O checkpoint usa sempre os 20 primeiros
  candidatos independentes (nao recalcula o teste opcionalmente a cada nova
  observacao) e suspende o envio do V10i somente se o limite superior do IC95
  do ROI ficar abaixo de zero. Ao concluir os 40 resultados, o grupo fecha de
  qualquer forma e aguarda revisao humana. O estado e persistente, atomico,
  falha fechado se corrompido e exige reativacao manual; a geracao e a
  liquidacao das simulacoes continuam em silencio. O watchdog registra e
  notifica a suspensao uma unica vez, e o status distingue grupo ativo/pausado.
  Nenhuma regra oficial ou outro mercado e alterado por esse circuit breaker.
  A regressao completa passou em 2.219/2.219 testes; manutencao continuou ativa
  e monitor, watchdog e pre-live permaneceram encerrados.
- [x] Integrar o balanceado ao painel de prontidao por mercado. O Proximo Gol
  agora aparece como portfolio prospectivo: a regra precisa preserva seus
  8/100 resultados e a V10i mostra separadamente 0/40, versao, G/R/P, ROI,
  checkpoint fixo, funil, circuit breaker, gerador, destino de teste e ausencia
  de promocao automatica. Um challenger sombra nao rebaixa uma futura regra
  oficial ja comprovada. A leitura real ficou sem falha tecnica ativa e a suite
  completa passou em 2.221/2.221 testes, sem iniciar os processos.

## Proximo Gol balanceado com fluxo maior — 09/09/2026

- [x] Separar falta de envio causada pela pausa operacional da raridade da
  regra. O servico continua em manutencao manual desde 08/09/2026 e, por isso,
  nao poderia produzir alertas novos. Ainda assim, a V10i tambem era rara: no
  recorte historico controlado produziu 12 entradas independentes, com 9
  greens e 3 reds. A ausencia de alertas durante a pausa nao foi tratada como
  evidencia de desempenho da regra.
- [x] Versionar a alternativa V10j sem alterar nem apagar a ancora V10i. O novo
  braco continua aceitando somente candidatos cujo unico impedimento seja
  pressao, ou pressao junto de qualidade entre 95 e 99,99. Preserva todos os
  demais bloqueios, exige minuto maximo 75, ao menos um chute recente do lado
  dominante, vantagem de pressao media de 10, nota tecnica minima 60 e odd
  curta entre 1,40 e 1,64. O pico minimo passa de 55 para 50 e a qualidade de
  100 para 95; a odd maxima exclusiva passa de 1,60 para 1,65.
- [x] Medir o corte antes da coleta prospectiva, sem apresenta-lo como prova.
  No mesmo historico gerador de hipotese, a V10j encontrou 17 entradas, 13
  greens e 4 reds (76,47%; ROI +15,92%). Na divisao cronologica 70/30 foram
  8/3 no desenvolvimento (ROI +11,28%) e 5/1 no holdout (ROI +24,44%). A
  amostra e pequena e a escolha foi exploratoria; portanto a regra permanece
  apenas no grupo de teste, sem Telegram oficial, calibracao ou promocao
  automatica.
- [x] Congelar a nova definicao no SQLite antes da primeira observacao futura.
  A ancora V10j foi registrada em 09/09/2026 13:46:52 com hash
  `26408358342d05ebd6c5e8e28eb827cb118aea2949cf6e4d086f862710860d69` e
  coorte nova em 0/40. O checkpoint fixo de 20 entradas e o circuit breaker
  persistente continuam protegendo somente esse grupo. O bot permaneceu
  pausado e nenhum alerta foi enviado durante a mudanca. A regressao completa
  passou em 2.223/2.223 testes.

## Resultado auditavel de cada selecao pre-live — 09/09/2026

- [x] Confirmar no banco real que o fluxo de resultado nao era apenas teorico.
  Existem 44 listas pre-live persistidas, 41 ja editadas com resultado, 3
  entregas individuais e as 3 ja editadas. A base contem 176 bilhetes
  preliminares green, 125 red, 1 anulado e 6 ainda pendentes; cinco dos
  pendentes chegaram a alguma lista ou entrega publicada.
- [x] Mostrar o desfecho de cada perna nas multiplas. A edicao individual
  identifica cada jogo com green, red, anulada ou pendente, e a lista diaria
  ganhou um resumo compacto por perna sem esconder o resultado geral do
  bilhete.
- [x] Corrigir a atualizacao incremental de uma multipla perdida cedo. Antes,
  o primeiro red encerrava o bilhete e marcava a mensagem como editada; o
  desfecho posterior das outras pernas podia nao voltar ao Telegram. Cada
  entrega agora guarda uma assinatura do resultado geral e das pernas. Toda
  mudanca nessa assinatura reabre exatamente uma edicao idempotente. A
  assinatura das listas tambem passou a incluir as pernas.
- [x] Evitar que uma mensagem antiga impossivel de editar deixe resultados
  novos para tras. As filas de edicao priorizam as publicacoes mais recentes.
  O esquema real recebeu a coluna `resultado_sha256`; nenhuma mensagem foi
  enviada ou editada durante a migracao porque a manutencao continua ativa.
  Os 126 testes direcionados de repositorio, liquidacao, agendador, Telegram e
  prontidao passaram integralmente; a regressao completa fechou em
  2.226/2.226.

## Validacao prospectiva do filtro pre-live preciso — 09/09/2026

- [x] Separar o desempenho historico da nova regra. O legado V12 publicou 116
  bilhetes resolvidos, com 71 greens, 45 reds e ROI de -6,15%; os 25 mais
  recentes tiveram 11 greens, 14 reds e ROI de -32,24%. Esses dados justificam
  cautela, mas permanecem apenas como diagnostico e nao entram como prova nem
  como gatilho de suspensao da regra nova.
- [x] Congelar antes da primeira observacao uma coorte prospectiva imutavel de
  60 candidatos elegiveis pelo filtro `filtro-pre-live-preciso-v1`, dividida
  cronologicamente em 42 de desenvolvimento e 18 de holdout. O teste exige ao
  menos 55 resultados validos no total, 38 no desenvolvimento e 16 no holdout,
  alem de ROI positivo nos tres recortes. A comparacao contra a probabilidade
  sem margem precisa cobrir ao menos 90% das entradas e ter limite inferior do
  IC95 acima de zero no total e no holdout. Nao existe promocao ou reativacao
  automatica.
- [x] Persistir a inclusao de cada candidato no SQLite no instante da primeira
  elegibilidade, congelando ordem, odd e conteudo. Alteracoes posteriores do
  bilhete nao mudam quem entrou nem os dados usados na avaliacao. Lacunas,
  adulteracao, definicao divergente ou banco inconsistente fazem a auditoria
  falhar fechada.
- [x] Adicionar um checkpoint fixo nos 25 primeiros candidatos. Se o IC95 do
  ROI desse recorte ficar integralmente negativo, somente a entrega pre-live
  precisa e suspensa; a coleta, persistencia e liquidacao em sombra continuam.
  Ao completar os 60 resultados a entrega tambem para para revisao manual. O
  watchdog registra uma unica notificacao e nenhum filtro de HT, FT, Proximo
  Gol ou escanteios e alterado por esse circuit breaker.
- [x] Registrar a definicao V2 em 09/09/2026 18:09:11 UTC, com hash
  `26e096f667ea4b38edd1756d0133f688bf55660029f762f97d9f0029c8d0f07c`.
  A coorte permanece em 0/60 e, portanto, ainda nao comprova vantagem. O backup
  `backups/pre_live/pre_live_20260909_180911.db` foi validado por `quick_check`
  e SHA-256
  `f7135aebf67a53068c411ac43035d536b460b1c4a7f5d5f1e8c70ab911f06b37`.
  A regressao completa passou em 2.245/2.245 testes; o modo de manutencao
  permaneceu ativo, nenhum processo Python ficou aberto e nenhuma consulta ou
  mensagem externa foi executada.

## Filtro prospectivo do Gol HT antecipado — 09/09/2026

- [x] Separar hipotese historica de confirmacao futura. O braco HT antecipado
  original tinha 75 resultados resolvidos (48 greens e 27 reds, taxa de 64%).
  O recorte exploratorio mais seletivo encontrou 21 casos, com 16 greens e
  5 reds (76,19%; ROI +31,9%); na divisao cronologica da base foram 13/4 no
  desenvolvimento e 3/1 no holdout. Como os limiares foram escolhidos depois
  de observar esse historico, esses numeros nao provam uma taxa futura de 75%.
- [x] Versionar o filtro filtro-gol-ht-antecipado-preciso-v1 sem apagar o
  gerador original. Para a entrega, ele exige minuto 10--28, odd fresca e fora
  de cache entre 1,40 e 2,00, qualidade minima 80, janela recente valida com
  ao menos dois chutes, ao menos dois chutes no gol acumulados com pares
  consistentes e faixa historica confirmada com pelo menos 12 gols. O rollback
  e explicito por FILTRO_GOL_HT_ANTECIPADO_PRECISO_ATIVO=0.
- [x] Congelar uma coorte prospectiva de 60 partidas antes de qualquer leitura
  de resultado ou entrega, com 42 casos de desenvolvimento e 18 de holdout.
  A decisao exige ao menos 55 resultados validos, taxa de green total minima
  de 75%, ROI total com limite inferior do IC95 positivo, ROI positivo em
  desenvolvimento e holdout e vantagem conservadora sobre 1/odd no total e
  no holdout. Nao ha promocao automatica nem promessa de acerto.
- [x] Registrar a ancora imutavel em 09/09/2026 18:31:17 UTC, com hash
  38fd315a942023a0a26160be63df7c0a2dda6a8475967eb1cbaa19eb32472f1a.
  A coorte comecou em 0/60; nenhum sinal antigo foi reaproveitado como prova.
  O ponto de recuperacao backups/pre_reinicio_20260909_142033.db, SHA-256
  007433a4043cca7be95a8c2c0f49354bc4828fd4bdd6b794c7a787f0e50843f1,
  e o banco ativo passaram em quick_check.
- [x] Isolar a protecao operacional. Um checkpoint usa sempre os primeiros
  25 casos e suspende somente a entrega deste HT se o IC95 do ROI ficar
  integralmente negativo. A coorte tambem fecha ao completar 60 resultados.
  Corrupcao de definicao, coorte ou estado falha fechada; coleta e liquidacao
  sombra continuam. O watchdog notifica uma unica vez e o painel de prontidao
  trata o novo filtro como metodo efetivo, mantendo a coorte antiga somente
  como diagnostico. Os 686 testes direcionados passaram com o bot em
  manutencao e sem envio externo. A regressao completa passou em
  2.267/2.267 testes.

## Filtro prospectivo do Gol FT antecipado no 2T — 09/09/2026

- [x] Separar descoberta historica de confirmacao futura. O braco 2T original
  tinha 287 partidas resolvidas, com 184 greens e 103 reds (64,1%; ROI
  -0,15%). O recorte exploratorio escolhido encontrou 59 casos, com 46 greens
  e 13 reds (77,97%; ROI +13,28%); o holdout cronologico exploratorio teve
  15/2. Como os limiares foram escolhidos depois de observar esses dados,
  nenhum desses numeros e tratado como prova de vantagem futura.
- [x] Versionar o filtro `filtro-gol-ft-antecipado-preciso-v2` sem apagar o
  gerador original. Ele se aplica somente ao metodo 2T exato e exige minuto
  46--60, odd fresca e fora de cache entre 1,40 inclusive e 1,90 exclusiva,
  qualidade minima 80, duas evidencias ao vivo distintas, faixa historica
  confirmada com ao menos 12 gols, janela de cinco minutos integra e ao menos
  um chute recente. Pares e totais de chutes e chutes no gol precisam ser
  consistentes. O rollback e explicito por
  `FILTRO_GOL_FT_ANTECIPADO_PRECISO_ATIVO=0`.
- [x] Congelar uma coorte prospectiva de 60 partidas, dividida em 42 de
  desenvolvimento e 18 de holdout, antes de qualquer leitura de resultado ou
  entrega. A decisao exige ao menos 55 resultados validos, taxa total minima
  de 75%, limite inferior do IC95 do ROI positivo, ROI positivo em
  desenvolvimento e holdout e vantagem conservadora sobre `1/odd` no total e
  no holdout. Nao existe promocao, reativacao ou promessa automatica.
- [x] Registrar a ancora imutavel em 10/09/2026 00:09:50 UTC, com hash
  `8a269eb2f6f69df78a8a269b3ecaddd1900f14df56d218a991993969920fa921`.
  A coorte comecou em 0/60 e nenhum resultado antigo foi reaproveitado. Antes
  da migracao, o ponto `backups/pre_reinicio_20260909_200906.db` foi validado
  por `quick_check`, chaves estrangeiras e SHA-256
  `a47b6c8dbc8874faf15dff2895eeec25fac5f3ed9a0b96aaf1d631a327635959`.
- [x] Isolar o circuit breaker deste filtro. O checkpoint usa os primeiros 25
  casos e suspende somente a entrega FT 2T precisa se o IC95 do ROI ficar
  integralmente negativo; a coleta sombra continua. Corrupcao de definicao,
  coorte ou estado falha fechada. O watchdog notifica uma unica vez, existe
  comando manual de suspensao/reativacao e o hash do runtime cobre filtro,
  validador e controle.
- [x] Integrar o metodo ao gateway Telegram, watchdog, configuracao, painel de
  prontidao e avaliacao de edge. O portfolio FT mantem o braco 1T separado e
  substitui apenas a avaliacao legada do 2T pela coorte precisa. Nenhuma
  promocao e automatica. Os 448 testes direcionados e a regressao integral de
  2.285/2.285 testes passaram com o bot em manutencao.

## Validacao prospectiva dos escanteios FT asiaticos — 09/09/2026

- [x] Separar o indicio historico da confirmacao futura. A regra exata
  `sinais-v9d-ft-asiatico-max86` apresentou no diagnostico anterior 41 casos
  independentes resolvidos, com 34 greens, 2 voids, 5 reds e ROI de +58,33%,
  distribuidos por 28 ligas e 3 fontes. O recorte entregue tambem foi positivo,
  mas o holdout ainda era pequeno. Como esse historico participou da descoberta
  e da selecao da regra, ele agora aparece somente como diagnostico e nao pode
  comprovar edge, liberar Telegram oficial ou promover o mercado.
- [x] Congelar uma coorte prospectiva imutavel dos primeiros 100 candidatos da
  versao exata, um por partida, dividida cronologicamente em 70 de
  desenvolvimento e 30 de holdout. O teste preserva a liquidacao asiatica
  completa (`green`, `half_green`, `void`, `half_red`, `red`), exclui void da
  taxa direcional e exige taxa positiva total minima de 75%, ao menos 90
  resultados validos, ROI total com limite inferior do IC95 positivo e ROI
  positivo em desenvolvimento e holdout.
- [x] Exigir vantagem contra preco de mercado sem margem, sem misturar linhas
  asiaticas incompatíveis. A referencia precisa cobrir pelo menos 90% dos
  resultados no total e no holdout. O residuo binario observado menos mercado
  usa apenas linhas de meio gol, com ao menos 45 observacoes no total e 12 no
  holdout, e precisa ter limite inferior do IC95 acima de zero nos dois
  recortes. Linhas inteiras e quartos continuam validas para ROI e liquidacao,
  mas nao sao convertidas incorretamente em eventos binarios.
- [x] Proteger somente esse mercado com circuit breaker persistente e atomico.
  O checkpoint usa sempre os primeiros 25 casos e suspende a entrega apenas se
  o limite superior do IC95 do ROI ficar abaixo de zero. A coorte fecha aos 100
  para revisao humana, sem reativacao ou promocao automatica. Corrupcao de
  definicao, coorte ou estado falha fechada; a coleta sombra e os outros
  mercados permanecem inalterados. O watchdog notifica uma unica vez.
- [x] Integrar registro, sincronizacao, gateway Telegram, hashes de runtime,
  watchdog, portfolio de edge e prontidao profissional. O status operacional
  agora mostra a coorte prospectiva em vez de usar a amostra historica como
  prova, incluindo estados asiaticos, checkpoint, referencia sem margem e
  controle isolado. A ancora foi registrada em 10/09/2026 00:32:29 UTC, com
  hash
  `de2b9e0640a134f150463307e443cc081f460fd2ae9a7636b2fb71ed1186daf8`,
  iniciando realmente em 0/100.
- [x] Preservar antes da ancora o snapshot manual
  `backups/pre_escanteios_ft_prospectivo_20260909_203204.db`, com
  2.628.317.184 bytes, `quick_check=ok` e SHA-256
  `4964ca1ab265913cc342443671eaac60360e18d4d123354f007bfd7e34fbb50e`.
  Uma auditoria posterior identificou que esse nome nao pertence aos padroes
  aceitos pelo seletor automatico e o arquivo nao tinha manifesto; portanto,
  ele permanece somente como snapshot manual e nao e tratado como ponto de
  recuperacao automatica. A regressao integral passou em 2.298/2.298 testes.
- [x] Criar depois da ancora um ponto de recuperacao no formato oficial
  `backups/pre_reinicio_20260909_205306.db.gz`, com manifesto e selecao
  automatica comprovados. O contêiner possui 469.866.640 bytes e SHA-256
  `56712da0b3978b147500e966bc3b620337c8f4e2458fe055784216461df225b9`;
  o SQLite restaurado possui 2.628.317.184 bytes e SHA-256
  `fb80463f54e24cde1a238a91595b65038fbb335753c4ed123a1df9ffadfe94c0`.
  O drill integral confirmou checksum, `quick_check=ok`, esquema compativel,
  zero violacoes de chaves estrangeiras, modelos sombra integros e remocao dos
  temporarios. A verificacao semantica na copia restaurada confirmou a ancora
  de 10/09/2026 00:32:29 UTC, o hash exato da definicao e a coorte em 0/100.
  A prontidao real permaneceu em `pausa_planejada`, sem falha tecnica ativa,
  sem iniciar processos Python do bot nem realizar envio externo.

## CLV live independente e sem falso desajuste — 09/09/2026

- [x] Corrigir a pseudorreplicacao da auditoria de preco V3. A avaliacao V4
  usa como evidencia principal somente a primeira entrega de cada partida e
  mercado, antes de saber se ela sera comparavel. Alertas repetidos da mesma
  partida permanecem apenas em um diagnostico agregado e nao estreitam o IC95.
  A segmentacao por regra, fonte e bookmaker tambem conserva uma observacao
  independente por partida dentro de cada estrato.
- [x] Substituir o critico normal fixo por intervalo t de Student nas amostras
  pequenas. Nenhum estado recebe rotulo favoravel ou desfavoravel com menos de
  30 comparacoes, mesmo quando a media observada parece positiva. A metrica e
  explicitamente auxiliar: pode informar a investigacao de edge, mas nunca
  decide liberacao, filtro, Telegram ou promocao sozinha.
- [x] Separar valor mark-to-market de movimento de odd entre sobreviventes.
  Liquidacoes por evento antes de dois minutos continuam no mark-to-market com
  valor terminal 1/0, evitando descartar justamente os contratos resolvidos.
  A variacao de odd dos contratos ainda abertos aparece separadamente e marcada
  como condicionada a sobrevivencia; o relogio naturalmente reduz a
  probabilidade de Overs sem evento, por isso essa queda nao pode ser tratada
  como evidencia contra o sinal.
- [x] Reavaliar o banco sem alterar operacao. Das 999 entregas brutas, 986 sao
  primeiras observacoes independentes e 218 possuem valor comparavel. O
  mark-to-market medio foi +6,84 pontos percentuais, IC95 de +3,74 a +9,94,
  mas agrega regras historicas heterogeneas e permanece apenas informativo. Os
  160 contratos sobreviventes com nova cotacao cairam em media 5,27 pontos;
  esse numero foi corretamente classificado como diagnostico com vies de
  sobrevivencia, incapaz de aprovar ou reprovar edge. Por mercado, apenas Gol
  HT atingiu amostra minima e IC95 positivo no mark-to-market; Gol FT e Proximo
  Gol continuam inconclusivos, e os dois mercados de escanteios permanecem com
  amostra insuficiente.
- [x] Integrar a V4 aos hashes de runtime e ao resumo de prontidao sem criar um
  novo gate. O operador agora ve cobertura, mark-to-market e leitura por
  mercado sem precisar abrir o relatorio integral. Os 124 testes direcionados
  e a regressao integral de 2.303/2.303 testes passaram. O modo de manutencao
  permaneceu ativo, sem iniciar o monitor ou enviar mensagens externas.
- [x] Eliminar nos sinais futuros a perda da cotacao exata de entrada. A camada
  de proveniencia agora congela em `features_json` o par sincronizado
  Over/Under, ou as tres vias de Proximo Gol, junto de fonte, bookmaker,
  horario, idade e cache. Pares incompletos e ofertas distintas empatadas no
  instante mais recente nao sao completados nem escolhidos arbitrariamente.
  A avaliacao CLV V5 prefere a prova congelada, valida sua aderencia ao sinal e
  falha fechada diante de adulteracao, cache, idade acima de 120 segundos ou
  divergencia de contrato; sinais antigos continuam pela reconstrucao legada.
  O relatorio passou a expor a origem da evidencia. No banco atual, as 986
  primeiras entregas independentes ainda sao historicas: 959 chegaram ate a
  etapa de reconstrucao como `snapshot_legado`, 19 nao tinham proveniencia e 8
  eram linhas nao binarias. A cobertura comparavel permaneceu 218/986, como
  esperado, sem reescrever o passado. Os 31 testes direcionados passaram; a
  regressao integral passou em 2.323/2.323 testes. O modo de manutencao
  permaneceu ativo, sem iniciar o monitor nem enviar mensagens externas.
- [x] Corrigir a falha de observabilidade descoberta na verificacao real: em
  console Windows CP1252, `status_bot.py` encerrava ao imprimir simbolos como
  menor-ou-igual. A saida agora e configurada como UTF-8 com substituicao
  segura antes do primeiro texto. O teste reproduz o stream CP1252 e o relatorio
  real terminou com codigo zero, exibindo a prontidao `pausa_planejada`, 11
  pendencias explicadas, nenhum mercado oficial e nenhuma instancia Python.
- [x] Fechar o falso desajuste entre probabilidade calibrada e odd isolada. A
  versao `valor-mercado-calibrado-conservador-v5` somente aprova vantagem
  oficial quando ha mercado completo, sincronizado e rastreavel para retirar a
  margem da casa: par Over/Under nos mercados binarios ou Casa/Visitante/Sem
  Gol em Proximo Gol. Alem do EV conservador minimo de 2%, a probabilidade do
  modelo precisa superar a referencia sem vig. A cotacao congelada tem
  prioridade e, quando invalida, falha fechada sem procurar uma substituta no
  snapshot. O gateway diferencia falta de referencia, falta de vantagem sem
  vig e EV baixo nos registros de bloqueio. Os 413 testes de integracao
  direcionados e a regressao integral de 2.327/2.327 testes passaram, com
  manutencao preservada e sem envio externo.
- [x] Impedir que uma cotacao futura recusada pela proveniencia volte pelo
  fallback historico. Todo candidato novo agora persiste o estado da tentativa
  de congelamento (`congelada_v1`, ambigua, nao localizada ou incompleta). Se a
  prova nao foi produzida, o gate sem vig falha fechado; somente um registro
  realmente legado, sem prova e sem marcador, pode reconstruir o par pelo
  snapshot. A regressao integral passou em 2.328/2.328 testes.
- [x] Vincular a integridade do rastro de valor à cotacao congelada, e nao
  apenas à autorreproducao do calculo. A auditoria agora compara o par
  Over/Under ou as tres vias, a selecao, a fonte e o bookmaker com a prova de
  entrada. Uma adulteracao coordenada do par e do calculo, ou um calculo que
  ignore uma prova completa disponivel, falha fechada antes do Telegram. Os
  240 testes direcionados e a regressao integral de 2.330/2.330 passaram.
- [x] Validar a plausibilidade do overround antes de usar uma referência sem
  vig. A amostra reconstruível continha 323 pares binários entre 4,2% e 9,3%
  de margem e 69 mercados de três vias entre 8,5% e 14,7%. A V6 adotou uma
  proteção deliberadamente ampla de -2% a 20%, preservando todos os casos
  observados e pequenos underrounds potencialmente reais, mas bloqueando
  mistura temporal/de bookmaker ou preço corrompido. O gate Telegram registra
  motivo próprio, a auditoria/status conta esses bloqueios e o CLV recusa tanto
  entrada quanto cotação futura incoerente. A avaliação real continuou em
  218/986 sinais independentes comparáveis, sem alterar o banco nem enviar
  Telegram. Os 265 testes direcionados e a regressão integral de 2.339/2.339
  passaram; o painel real reconheceu a V6 saudável, com zero anomalias atuais.

## Prontidao sem processo pre-live fantasma — 09/09/2026

- [x] Remover a dependencia exclusiva do ultimo snapshot do watchdog para a
  saude do agendador pre-live. A prontidao agora revalida o PID e a trava no
  instante da leitura usando a mesma auditoria autoritativa da operacao. Se a
  verificacao falhar, o estado falha fechado em vez de reutilizar uma saude
  antiga.
- [x] Expor `status_processo`, resposta do PID, estado da trava, estado anterior
  do watchdog e a divergencia entre snapshots. Durante manutencao, processo
  realmente encerrado com SQLite e backup integros passa a ser descrito como
  `pausa_planejada`, sem virar falso `ativo` nem falsa falha tecnica.
- [x] Confirmar no estado real que o PID 25708 esta encerrado, nao responde e
  nao possui trava ativa, apesar do snapshot antigo ainda dizer `ativo`. Os 3
  testes direcionados e a regressao integral de 2.305/2.305 testes passaram.
  A leitura final permaneceu em `pausa_planejada`, com 11 pendencias explicadas
  e nenhuma falha tecnica ativa; nenhum servico ou envio externo foi iniciado.

## Observabilidade da virada de cota API-Football — 09/09/2026

- [x] Eliminar a aparente contradicao entre o saldo local do novo dia UTC e a
  ultima fotografia do provedor. O limitador ja aplicava corretamente apenas a
  fotografia cujo dia coincide com o contador atual; o painel, porem, exibia a
  leitura anterior como "cota confirmada" sem mostrar a data. A validacao agora
  persiste `cota_provedor_dia` e `cota_provedor_vigente`, e o status mostra os
  dois dias, o horario UTC legivel e se a fotografia realmente participa do
  saldo. Os testes confirmaram que 2.532 restantes em 08/09 nao reduzem os
  7.000 seguros renovados em 09/09. A regressao integral passou em
  2.332/2.332 testes.

## Resiliência de armazenamento e ritmo de login V52 — 11/09/2026

- [x] Estender a compactação verificada às famílias gerenciadas de backup
  diário, periódico, pré-reinício, pré-migração e inválido. Arquivos de nomes
  desconhecidos continuam fora da automação.
- [x] Tornar a remoção pós-round-trip resiliente a bloqueios transitórios do
  Windows. Se o original permanecer ocupado, a cópia SQLite e o gzip já
  verificado são preservados; não há troca de uma cópia válida por falha de
  limpeza.
- [x] Criar lote explícito de manutenção, limitado e observável. A ferramenta
  apenas mostra candidatos por padrão, recusa execução com processos ativos,
  continua com arquivos independentes quando encontra um legado incompatível
  e nunca remove o arquivo recusado.
- [x] Registrar legados estruturalmente incompatíveis por tamanho e `mtime`,
  preservando-os e evitando tentativas automáticas infinitas. Se o arquivo
  mudar, o marcador deixa de corresponder e ele volta a ser validado.
- [x] Compactar dez backups reais válidos com round-trip completo. A economia
  informada pelo lote foi 18.591,4 MB; a redução física medida pelo watchdog
  foi 18.596,4 MB. Um backup de esquema antigo foi preservado e um arquivo não
  gerenciado ficou intocado.
- [x] Reancorar a tendência após redução material comprovada, guardando o
  resumo da série anterior. O novo patamar físico ficou em aproximadamente
  21,3 GB, com cerca de 68 GB livres e sem falso alerta de esgotamento.
- [x] Unificar o limitador de navegação do login e do monitor PackBall. O teste
  real terminou com distribuição ativa, intervalo efetivo de 19,25 segundos,
  mínimo observado de 19 segundos, zero violações e zero excesso da janela.
- [x] Confirmar a retomada real: 3/3 partidas processadas, nenhuma adiada,
  fontes saudáveis, backup diário compacto verificado e prontidão em
  `coleta_profissional_em_validacao`, sem falha técnica. As regras HT e FT não
  foram alteradas por esta etapa. A regressão direcionada passou em 654/654
  testes.

## Funil causal do Gol FT e telemetria persistente V53 — 11/09/2026

- [x] Adicionar ao filtro preciso de Gol FT um funil causal pós-âncora que mede
  decisões recebidas, elegíveis, recusadas e motivos de bloqueio, sem consultar
  resultados, entregas ou alterar promoção e Telegram.
- [x] Confirmar no banco real 11 decisões independentes, 4 elegíveis e 7
  recusadas: 5 por minuto fora da janela e 2 por histórico de faixa
  insuficiente. A coorte de 2 greens e 2 reds continua inconclusiva.
- [x] Persistir nos snapshots o diagnóstico do gerador de gols antecipados e
  separar o histórico pelos ramos HT, FT primeiro tempo e FT segundo tempo.
- [x] Validar as duas primeiras observações reais do ramo FT segundo tempo:
  ambas bloqueadas, uma por faixa histórica não confirmada e outra por odd fora
  da faixa. A amostra não autoriza ajuste de regra.
- [x] Corrigir o relógio determinístico do agendador pré-live no encerramento,
  retry e retenção, sem alterar critérios de entrada.
- [x] Passar a regressão integral em 2.545/2.545 testes e confirmar após reinício
  controlado monitor, watchdog, pré-live e PackBall ativos. O ciclo de
  11/09/2026 00:22:12 ficou saudável, sem falha técnica. Nenhuma regra HT ou FT
  foi modificada pela V53.

## Quase-candidatos causais do Gol FT V54 — 11/09/2026

- [x] Criar dois braços prospectivos mutuamente exclusivos para testar apenas
  um limite do FT preciso por vez: minuto 61–75 e histórico de 8–11 gols.
- [x] Exigir que a substituição do único limite testado faça o candidato passar
  por todos os demais critérios originais. Jogos com duas ou mais falhas não
  entram nas coortes.
- [x] Congelar 60 jogos por braço, com desenvolvimento 42 e holdout 18, meta de
  75%, ROI e IC95 positivos, comparação conservadora com 1/odd e checkpoint de
  segurança nos primeiros 25 resultados.
- [x] Garantir seleção anterior ao resultado e sem leitura de entregas. Telegram,
  sinais, qualidade, atividade, odds, fontes, promoção e reativação automáticas
  permanecem inalterados.
- [x] Registrar a âncora real em 11/09/2026 00:37:58, começando ambas as coortes
  em zero sem reutilizar os 11 casos observados antes da hipótese.
- [x] Passar a regressão integral em 2.554/2.554 testes e confirmar os hashes
  carregados de monitor e watchdog. O ciclo de 00:40:41 processou 2 partidas,
  terminou saudável e manteve HT e FT operacionais sem mudança de regra.

## Liquidações asiáticas explicáveis V55 — 11/09/2026

- [x] Separar, sem afrouxar qualquer gate, devoluções contratuais, encerramentos
  sem dado e falhas técnicas dentro da coorte causal da calibração.
- [x] Preservar `invalidas` e `pendentes_ou_invalidas` para que nenhum `void` ou
  dado ausente seja silenciosamente substituído por outro resultado conhecido.
- [x] Confirmar na base real a decomposição dos quatro casos: 3 `void`, 1
  `sem_dado` e 0 falhas técnicas, sobre 43 exposições independentes.
- [x] Manter o validador prospectivo asiático dedicado como método correto para
  retornos fracionários e ROI. A coorte fixa futura continua em 0/100 e não há
  promoção automática.
- [x] Manter inalteradas todas as regras, odds, sinais e entregas de HT e FT.
- [x] Passar a regressão integral em 2.555/2.555 testes e confirmar a retomada
  dos três processos com hashes atuais. O primeiro ciclo pós-reinício terminou
  às 00:50:58, saudável, com 2 partidas, zero falhas e sem pausa preventiva.

## Cobertura do motor por versões operacionais V56 — 11/09/2026

- [x] Corrigir a auditoria de candidatos para aceitar todas as versões exatas
  atualmente roteadas por mercado, em vez de observar somente `sinais-v6`.
- [x] Preservar a chamada com uma única versão para auditorias direcionadas e
  manter o bloqueio quando nenhuma versão autorizada produzir candidato.
- [x] Comprovar na base real que os dois snapshots antes classificados como
  ausentes continham decisões das versões especializadas atuais.
- [x] Corrigir a cobertura real de 13/15 (86,7%) para 16/16 (100%), mantendo a
  cobertura de odds separada em 15/16.
- [x] Executar a validação integral real com resultado saudável, sem motivos e
  sem avisos, sem alterar regras, sinais, HT, FT ou Telegram.
- [x] Aprovar 409 testes relacionados e a regressão integral de 2.556 testes;
  retomar os três processos com hashes atuais e confirmar ciclo real de 1/1
  tarefa, cobertura 13/13, zero falhas e nenhuma pausa preventiva.

## Referência independente de odds em sombra V57 — 11/09/2026

- [x] Identificar a causa das 46 observações Bet365/BetsAPI sem referência na
  mesma linha: mercados já anexados eram excluídos antes da consulta à The Odds
  API, impedindo comparação independente.
- [x] Criar amostragem sombra de gols FT limitada a 2 jogos por ciclo, 30
  reservas diárias e intervalo mínimo de 10 minutos por jogo, com orçamento e
  cooldown persistidos antes da chamada externa.
- [x] Persistir a cotação independente no SQLite como `referencia_sombra`, sem
  misturá-la à odd operacional entregue ao motor de sinais.
- [x] Permitir ao avaliador prospectivo recuperar essa fonte somente em pares
  exatos de mercado, período, linha, lado, placar, minuto e instante, mantendo a
  exigência de fontes distintas.
- [x] Expor no status consumo, jogos, mercados e comparações da amostragem,
  declarando explicitamente que ela não altera HT/FT, Telegram ou promoção.
- [x] Passar a regressão integral em 2.562/2.562 testes e o preflight completo.
  Após corrigir a permissão de abertura do navegador, confirmar ciclo real às
  01:23:29, watchdog saudável, zero falhas e nenhuma pausa preventiva.
- [ ] Acumular pares independentes prospectivos naturais antes de concluir se
  existe vantagem de preço; amostra vazia ou pequena não autoriza mudança de
  regra nem promoção automática.

## Supervisão da referência independente V58 — 11/09/2026

- [x] Registrar por ciclo oportunidades de gols FT cobertas pela BetsAPI,
  reservas consumidas e mercados independentes persistidos no SQLite.
- [x] Contar como tentativa somente uma chamada efetivamente reservada, sem
  penalizar ciclos sem jogo, cooldown ou limite diário.
- [x] Alertar após três tentativas reais sem cobertura e distinguir três falhas
  técnicas consecutivas de simples ausência do evento no provedor.
- [x] Encerrar automaticamente a sequência degradada quando uma cotação sombra
  for persistida, mantendo o diagnóstico de recuperação observável.
- [x] Preservar no diagnóstico a reserva consumida mesmo quando a chamada
  externa falhar depois dela.
- [x] Manter essa supervisão fora do motor: não altera HT/FT, não bloqueia
  sinais, não envia Telegram e não promove estratégias.
- [x] Aprovar 532 testes dos módulos afetados e a regressão integral de
  2.567/2.567; confirmar preflight saudável e ciclo real às 01:35:27, com
  watchdog saudável, zero falhas e estado correto `sem_oportunidade`.

## Circuito persistente da fonte independente V59 — 11/09/2026

- [x] Persistir falhas consecutivas, motivo e prazo do circuito da The Odds
  API para que reiniciar o processo não elimine a proteção.
- [x] Bloquear novas reservas sombra enquanto o circuito estiver aberto,
  distinguindo esse motivo do limite diário e do orçamento do provedor.
- [x] Preservar os intervalos conservadores já existentes: 120 segundos após
  três falhas transitórias e 15 minutos para HTTP 401, 403 ou 429.
- [x] Liberar automaticamente uma tentativa após o prazo e zerar o circuito de
  forma persistente somente após resposta válida.
- [x] Expor no status e na telemetria estado, quantidade de falhas, motivo e
  tempo restante, sem alterar HT/FT, sinais ou Telegram.
- [x] Aprovar a regressão integral de 2.568/2.568 testes e o preflight; confirmar
  ciclo real às 01:45:49, watchdog saudável, zero falhas, nenhuma pausa e
  circuito fechado com recuperação automática.

## Estado resiliente da fonte independente V60 — 11/09/2026

- [x] Gravar o estado da The Odds API de forma atômica, mantendo cópia principal
  e backup válido de cotas, reservas e circuito persistente.
- [x] Recuperar automaticamente pelo backup quando somente o arquivo principal
  estiver corrompido, expondo a origem e o indicador de recuperação.
- [x] Falhar fechado quando principal e backup estiverem irrecuperáveis,
  impedindo novas reservas e chamadas externas sem esquecer o orçamento.
- [x] Fazer o watchdog sinalizar esse incidente da referência independente sem
  bloquear nem modificar HT, FT, sinais oficiais ou Telegram.
- [x] Preservar circuito e controle na telemetria mesmo quando o ciclo não tiver
  partidas, e mostrar origem/saúde no status operacional.
- [x] Aprovar 545 testes dos componentes afetados, a regressão integral de
  2.572/2.572 e o preflight completo.
- [x] Retomar monitor, watchdog e pré-live e confirmar o ciclo de 02:00:27:
  saudável, zero falhas, sem pausa, estado principal válido, backup presente,
  fail-closed inativo, circuito fechado e FT ativo sem alteração de regra.

## Diversidade do orçamento independente V61 — 11/09/2026

- [x] Limitar a duas consultas sombra por partida/dia: uma referência inicial e
  uma confirmação temporal após o cooldown, sem consumir a cota em repetições.
- [x] Persistir contagens por partida e renovar o limite somente na virada do
  dia UTC, mantendo o comportamento após reinício.
- [x] Preservar as 30 reservas diárias para mais jogos distintos, acelerando a
  formação da coorte necessária para investigar desajuste de preço real.
- [x] Reservar em cada ciclo pelo menos uma das duas vagas para uma partida
  nova, aceitando no máximo uma confirmação temporal repetida por ciclo.
- [x] Versionar logicamente principal e backup, escolher a revisão mais nova e
  reparar automaticamente a cópia atrasada após interrupção parcial.
- [x] Bloquear a consulta de rede se a reserva não puder ser persistida, sem
  permitir consumo externo não contabilizado.
- [x] Expor diversidade, repetição e teto por jogo no status e na telemetria de
  ciclos vazios, sem alterar HT, FT, sinais oficiais ou Telegram.
- [x] Aprovar os testes afetados, a regressão integral de 2.577/2.577 e o
  preflight completo de 02:23:42.
- [x] Confirmar recuperação automática de uma tela transitória sem lista Ao
  Vivo: ciclo seguinte concluído às 02:15:41, watchdog saudável, zero falhas,
  nenhuma pausa e todos os processos, inclusive FT, ativos.
- [x] Confirmar em ciclo real às 02:25:02 a política de diversidade: duas
  amostras por jogo/dia, uma confirmação repetida por ciclo e prioridade para
  partidas novas, sem qualquer efeito sobre HT, FT ou Telegram.

## Migração imediata do estado independente V62 — 11/09/2026

- [x] Detectar um estado válido legado ainda sem revisão e materializar a nova
  proteção já na inicialização, sem aguardar uma chamada externa futura.
- [x] Gravar principal e backup com a mesma primeira revisão, preservando
  integralmente consumo, reservas, cooldown e circuito existentes.
- [x] Não consumir cota, não acessar a rede e falhar fechado se a migração não
  puder ser persistida.
- [x] Aprovar 265 testes direcionados, a regressão integral de 2.578/2.578 e o
  preflight completo de 02:28:44.
- [x] Reiniciar os três processos de forma controlada e confirmar no ciclo de
  02:29:51 revisão 1, cópias idênticas, estado saudável, zero falhas e nenhuma
  pausa preventiva.
- [x] Manter FT `ativo_manual` e preservar todas as condições HT/FT, sinais
  oficiais, Telegram e promoção automática.

## Auditoria de representatividade da referência V63 — 11/09/2026

- [x] Persistir no SQLite cada tentativa sombra futura, inclusive evento não
  encontrado e competição sem cobertura, sem confundi-la com consulta
  operacional da mesma fonte.
- [x] Registrar tipo da amostra, posição e tamanho da fila, fila operacional,
  liga e minuto, sempre escolhidos antes do resultado.
- [x] Impedir que uma tentativa sombra sem oferta herde uma cotação operacional
  existente e gere falsa cobertura.
- [x] Medir concentração da amostragem na fila somente após 30 contextos
  prospectivos; antes disso declarar explicitamente amostra insuficiente.
- [x] Não retroclassificar registros antigos e não usar a nova auditoria em
  filtros, HT/FT, sinais, Telegram ou promoção automática.
- [x] Aprovar 303 testes direcionados e a regressão integral de 2.579/2.579;
  migrar o SQLite com integridade `ok` e regenerar o backup diário compatível.
- [x] Retomar monitor, watchdog e pré-live com os hashes atuais. Como o limite
  independente de 30 reservas já estava esgotado, iniciar a coorte nas
  próximas tentativas naturais, sem ampliar orçamento nem fazer chamadas
  artificiais.
- [x] Confirmar o primeiro ciclo real às 11:21:48: 76 partidas, oito tarefas
  processadas com odds utilizáveis, API saudável, nenhum bloqueio por fonte,
  zero falhas consecutivas e nenhuma pausa preventiva.
- [ ] Revisar o viés de posição somente quando houver pelo menos 30 tentativas
  prospectivas auditadas e manter qualquer promoção dependente de evidência
  independente suficiente.

## Edge multifonte sem margem da casa V64 — 11/09/2026

- [x] Exigir Over e Under completos nas duas fontes e a mesma linha, período,
  estado do jogo e janela temporal antes de calcular qualquer vantagem.
- [x] Remover separadamente a margem de cada bookmaker e comparar a odd Over
  executável da Bet365 com a probabilidade sem vig da fonte independente.
- [x] Descartar bookmaker desconhecida, fontes não independentes, mercado
  binário incompleto e margem fora da faixa plausível.
- [x] Pré-registrar no SQLite uma definição imutável com EV mínimo de 2%,
  seleção anterior ao resultado e uma fotografia independente por partida.
- [x] Fixar coorte prospectiva de 60 partidas, com desenvolvimento 42 e
  holdout 18; revisar somente depois de 30 partidas e 15 jogos distintos.
- [x] Manter o recorte estritamente em sombra, sem alterar HT, FT, pré-live,
  prioridade, sinais oficiais, Telegram ou promoção automática.
- [x] Fazer o watchdog sanitizar o recorte, bloquear inferência interna quando
  houver inconsistência e impedir alegação prematura de vantagem.
- [x] Aprovar 378 testes direcionados, a regressão integral de 2.582/2.582 e o
  preflight completo de 11:36:49.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais; confirmar o ciclo
  de 11:45:22 com 69 partidas, cinco tarefas com odds utilizáveis, API
  saudável, zero falhas, zero bloqueios por fonte e nenhuma pausa preventiva.
- [ ] Aguardar a coorte futura iniciada às 11:45:18; não usar o diagnóstico
  histórico exploratório de 11 fotografias/um candidato como prova.
- [ ] Considerar influência operacional somente após resultados completos,
  convergência favorável e aprovação independente no holdout.

## Liquidação prospectiva do edge por mercado V65 — 11/09/2026

- [x] Pré-registrar uma política imutável de liquidação antes de aceitar
  candidatos da nova avaliação.
- [x] Separar gols FT e escanteios FT em coortes independentes, sem misturar
  suas taxas, retorno ou calibração.
- [x] Limitar a primeira prova às linhas `.5`, excluindo linhas inteiras e
  quarter lines que exigem tratamento de push e meia devolução.
- [x] Liquidar somente com snapshot final posterior à seleção do candidato e
  expor violações de cronologia como evidência inválida.
- [x] Medir EV previsto, ROI realizado, taxa de green, calibração, Brier score
  e intervalos de confiança em total, desenvolvimento e holdout.
- [x] Exigir por mercado 60 candidatos, 50 resultados, partição mínima 35/15,
  ROI positivo nas duas partes e IC95 inferior do ROI total acima de zero.
- [x] Fazer o watchdog validar e sanitizar toda a liquidação, isolando o
  experimento sem degradar o monitor principal.
- [x] Manter aplicação em sinais, HT, FT, pré-live, prioridade, Telegram e
  promoção automática explicitamente desativadas.
- [x] Aprovar 566 testes direcionados, 2.588/2.588 testes integrais e o
  preflight completo de 11:59:01.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais e confirmar o
  primeiro ciclo às 12:09:02: 77 partidas, seis tarefas com odds utilizáveis,
  API saudável, zero falhas, nenhum bloqueio por fonte e nenhuma pausa.
- [x] Confirmar política registrada às 12:08:59, coorte inicialmente vazia,
  watchdog saudável e FT preservado em `ativo_manual`.
- [ ] Aguardar candidatos e resultados futuros separados por mercado; nenhuma
  leitura histórica anterior à política entra como prova.
- [ ] Submeter eventual resultado favorável a revisão independente antes de
  qualquer proposta de influência operacional.

## Probabilidade individual causal e prospectiva V66 — 11/09/2026

- [x] Separar a taxa histórica do método da probabilidade individual de cada
  sinal, impedindo que uma porcentagem agregada seja apresentada como chance
  calibrada do jogo.
- [x] Usar a probabilidade implícita na odd como ponto de partida e aprender
  somente o desvio contextual anterior ao resultado, incluindo tempo restante
  e perfis ofensivo e defensivo.
- [x] Validar em três cortes temporais de 30 sinais, sem vazamento do futuro, e
  exigir melhora mínima de Brier de 0,002 contra a odd e a taxa observada.
- [x] Exigir erro de calibração máximo de 0,10 e impedir aprovação quando algum
  corte regredir mais de 0,01 contra a odd.
- [x] Pré-registrar qualquer modelo aprovado antes da primeira previsão futura
  e formar coorte imutável de 60 sinais, com desenvolvimento 42 e holdout 18.
- [x] Proteger definições e previsões contra alteração/exclusão no SQLite e
  validar hashes, cronologia, contagens e partição no watchdog.
- [x] Manter sinais, HT, FT, calibração, prioridade, promoção, reativação e
  Telegram explicitamente desativados nessa experiência.
- [x] Reprovar corretamente o modelo atual: HT com Brier 0,23923 versus 0,23819
  da odd e FT com 0,22802 versus 0,22646, sem congelar definição nem aceitar
  previsões prospectivas.
- [x] Aprovar 2.598/2.598 testes integrais, migrar os gatilhos imutáveis,
  regenerar o backup e recuperar de forma fail-closed uma recusa de permissão
  do navegador no Windows.
- [x] Confirmar o primeiro ciclo real às 12:43:12: 94 partidas, oito tarefas,
  seis com odds utilizáveis, API saudável, zero bloqueios por fonte, nenhuma
  pausa preventiva e avaliação V66 saudável e íntegra.
- [ ] Permitir o início da coorte futura somente quando uma versão posterior
  superar de fato a odd nos três cortes temporais; não afrouxar os critérios
  apenas para produzir mais probabilidades.
- [ ] Propor qualquer influência operacional somente após coorte prospectiva
  completa, holdout favorável e revisão independente.

## Referência individual sem margem V67 — 11/09/2026

- [x] Substituir `1 / odd` pela probabilidade sem margem reconstruída do par
  Over/Under exato e sincronizado no mesmo snapshot.
- [x] Descartar pares incompletos, ambíguos ou com margem implausível e exigir
  cobertura mínima de 95% antes de validar qualquer modelo.
- [x] Confirmar cobertura de 100% no HT e 99,66% no FT, com margem média da casa
  de 7,96% e 7,67%, respectivamente.
- [x] Manter três cortes temporais sem vazamento, melhora mínima de Brier de
  0,002, erro de calibração máximo de 0,10 e tolerância por corte de 0,01.
- [x] Reprovar corretamente o modelo atual: HT 0,23914 versus 0,23729 e FT
  0,22705 versus 0,22699 da referência sem margem.
- [x] Impedir congelamento de definição ou previsão prospectiva após a recusa e
  manter sinais, regras HT/FT, prioridade, calibração e Telegram inalterados.
- [x] Fazer o watchdog validar versão, cobertura, origem da referência,
  cronologia, ausência de consulta ao resultado e efeitos operacionais nulos.
- [x] Aprovar 672 testes direcionados e a regressão integral de 2.605/2.605.
- [x] Retomar monitor, watchdog e pré-live e confirmar o primeiro ciclo V67 às
  13:07:38: 124 partidas, cinco tarefas processadas, duas com odds utilizáveis,
  API saudável, zero bloqueios por fonte e nenhuma pausa preventiva.
- [x] Confirmar às 13:08:31 watchdog saudável, versão V67 compatível e zero
  falhas consecutivas.
- [ ] Manter a camada em formação até que uma versão futura supere de fato a
  referência sem margem; não reduzir o rigor apenas para gerar probabilidades.

## Pré-seleção de cobertura da referência V68 — 11/09/2026

- [x] Verificar cobertura no catálogo da fonte independente antes de consumir
  uma reserva diária de amostragem.
- [x] Exigir compatibilidade de país além do nome da competição, evitando
  falsos positivos em nomes genéricos como `Premier League`.
- [x] Manter o limite temporal entre fontes em 60 segundos, sem trocar maior
  volume por comparações antigas ou enganosas.
- [x] Persistir decisões de pré-seleção e expor cobertas, descartadas e reservas
  economizadas no ciclo, status e watchdog.
- [x] Fazer o watchdog validar a consistência dos contadores e exigir atenção
  quando cobertas mais descartadas não corresponderem ao total inspecionado.
- [x] Aprovar 640 testes direcionados e a regressão integral de 2.610/2.610.
- [x] Confirmar em catálogo real, sem consumir cota, a cobertura da 2.
  Bundesliga e o descarte da Premier League do Bahrein.
- [x] Confirmar no primeiro ciclo V68, às 13:35:21, duas pré-seleções, dois
  descartes e duas reservas economizadas, com API e watchdog saudáveis, zero
  falhas consecutivas e nenhuma pausa preventiva.
- [x] Manter sinais, HT, FT, pré-live, prioridade, Telegram e promoção
  automática explicitamente inalterados.
- [ ] Medir o aumento de comparações independentes após a próxima renovação da
  cota diária; a economia de reservas é comprovada, mas o ganho de cobertura
  ainda precisa de observação prospectiva.

## Pareamento gratuito do evento antes da reserva V69 — 11/09/2026

- [x] Exigir país e campeonato cobertos antes de iniciar o pareamento da
  partida na fonte independente.
- [x] Consultar gratuitamente a lista de eventos e validar os dois times,
  orientação e janela de início antes de consumir uma reserva de odds.
- [x] Recusar ausência ou ambiguidade de evento antes da reserva, preservando
  o limite diário para partidas que realmente podem oferecer comparação.
- [x] Persistir a decisão causal e expor eventos pareados, descartados e
  reservas economizadas especificamente pelo novo filtro.
- [x] Corrigir o status para não chamar de economia uma partida válida apenas
  impedida por cooldown ou limite diário.
- [x] Fazer o watchdog validar as novas somas e falhar fechado diante de
  contadores impossíveis ou adulterados.
- [x] Confirmar em fonte real Nürnberg x Hannover 96, com 94,44% de
  similaridade, sem consulta de odds, sem reserva e com consumo zero.
- [x] Aprovar 644 testes direcionados e a regressão integral de 2.614/2.614.
- [x] Retomar monitor, watchdog e pré-live e confirmar o primeiro ciclo V69 às
  13:55:03, com API saudável, zero bloqueios e nenhuma pausa preventiva.
- [x] Manter sinais, HT, FT, pré-live, prioridade, Telegram e promoção
  automática explicitamente inalterados.
- [ ] Medir após a renovação diária quantas reservas antes perdidas em
  `evento_nao_encontrado` passam a produzir ofertas e comparações válidas.

## Amostragem independente ampliada com orçamento protegido V70 — 11/09/2026

- [x] Confirmar pela prontidão que o gargalo atual é a amostra prospectiva de
  preço justo, com nenhum mercado ainda liberado para operação oficial.
- [x] Recusar como filtro a concordância temporal entre PackBall e API-Football:
  a análise exploratória por partida não mostrou melhora nos mercados de gol.
- [x] Recusar uma recalibração simples do mercado sem margem após ela piorar o
  Brier temporal em 0,00472 no HT e 0,00178 no FT.
- [x] Confirmar na documentação oficial que os mercados adicionais usados pelo
  projeto só podem ser consultados por evento, sem atalho equivalente em lote.
- [x] Elevar a amostragem independente de 30 para 60 reservas/dia somente após
  V68/V69 passarem a eliminar competição e evento inválidos antes do gasto.
- [x] Preservar duas reservas por partida/dia, duas por ciclo, teto geral de 600
  créditos/dia e reserva mensal intocável de 2.000 créditos.
- [x] Comprovar folga de orçamento: 19.752 créditos disponíveis; pior caso de
  1.800 créditos em 30 dias sob o novo teto.
- [x] Validar a configuração efetiva com 60/dia e efeitos nulos em sinais e
  Telegram, e aprovar a regressão integral de 2.614/2.614 testes.
- [x] Confirmar o primeiro ciclo de produção após a retomada: runtime em 60/dia,
  uma nova oferta consultada, pareada e persistida em sombra, duas reservas
  economizadas pela pré-seleção, watchdog saudável, zero falhas e nenhuma pausa.
- [ ] Acumular prospectivamente ofertas úteis, comparações independentes e jogos
  distintos após a retomada; o primeiro ciclo prova funcionamento, não edge.
- [ ] Manter qualquer promoção bloqueada até desenvolvimento, holdout e
  intervalo de confiança comprovarem vantagem líquida contra o preço justo.

## Referência independente multitemporal combinada V71 — 11/09/2026

- [x] Identificar que a amostragem sombra cobria somente gols FT apesar de HT e
  escanteios asiáticos FT já serem suportados pelo cliente independente.
- [x] Combinar mercados compatíveis em uma única requisição por evento, em
  ordem determinística, conforme recomendação oficial do provedor.
- [x] Contabilizar e reservar o custo real de um a três mercados antes da
  chamada; nunca tratar pedido combinado como um único crédito.
- [x] Generalizar a amostragem somente para mercados previamente comprovados
  na Bet365/BetsAPI: `gol_ft`, `gol_ht` e `escanteios_ft_asiatico`.
- [x] Comprovar proteção de orçamento: pior caso de 180 créditos/dia, abaixo do
  teto geral de 600, com reserva mensal de 2.000 preservada pelo cliente.
- [x] Preservar isolamento completo de sinais, Telegram e promoção automática.
- [x] Aprovar 286/286 testes das áreas afetadas e 2.616/2.616 na regressão total.
- [x] Confirmar primeiro ciclo de produção às 14:28:37: 140 partidas, quatro
  tarefas, API saudável, zero falhas, nenhuma pausa e nenhum gasto quando não
  havia mercado comum elegível.
- [ ] Observar a primeira partida real com dois ou três mercados comuns e
  confirmar no SQLite períodos, custo, ofertas completas e sincronismo.
- [ ] Medir separadamente cobertura e edge de FT, HT e escanteios; não promover
  um mercado usando a evidência acumulada por outro período.

## Auditoria causal por mercado e custo V72 — 11/09/2026

- [x] Expor por mercado as contagens de elegibilidade, consulta e anexação da
  referência independente, sem misturar HT, FT e escanteios.
- [x] Expor custo estimado reservado, consultas combinadas e quantidade máxima
  de mercados por chamada em cada ciclo.
- [x] Fazer o watchdog rejeitar anexações acima de consultas, consultas acima de
  elegibilidade, soma persistida divergente, custo impossível ou combinação
  declarada com menos de dois mercados.
- [x] Manter a auditoria observacional, sem alteração de sinal, Telegram ou
  promoção automática.
- [x] Aprovar 524/524 testes direcionados e 2.618/2.618 na regressão integral.
- [x] Confirmar o primeiro ciclo real às 14:42:19: 146 partidas, sete tarefas,
  seis sem mercado comum, todos os novos contadores em zero e auditoria
  multimercado saudável.
- [ ] Confirmar os mesmos invariantes quando surgir a primeira consulta real
  com dois ou três mercados e confrontar o resumo com o SQLite.

## Circuito persistente da BetsAPI V73 — 11/09/2026

- [x] Confirmar no SQLite que a primeira ausência V72 foi legítima: a única
  oferta BetsAPI daquele recorte continha apenas `proximo_gol`, sem mercado HT,
  FT ou escanteios compatível com a referência independente.
- [x] Persistir contagem de falhas, bloqueio, motivo e instante de atualização
  do circuito BetsAPI para impedir que um reinício contorne o backoff.
- [x] Preservar o bloqueio de 15 minutos para HTTP 401/403/429 e aplicar o
  backoff transitório após três falhas HTTP ou de transporte consecutivas.
- [x] Fechar e persistir automaticamente o circuito depois de resposta válida.
- [x] Bloquear novas chamadas na instância quando o estado do circuito não
  puder ser persistido, mantendo comportamento seguro diante de falha de disco.
- [x] Expor motivo, tempo restante, saúde da persistência e recuperação no
  diagnóstico de ciclo e impedir que o watchdog trate estado não persistido
  como fonte oficial capaz de mascarar degradação da API-Football.
- [x] Aprovar 520/520 testes direcionados e 2.623/2.623 na regressão integral.
- [x] Confirmar após a retomada o circuito persistente em produção: três
  falhas transitórias abriram backoff de 120 segundos, a tentativa controlada
  posterior renovou o bloqueio sem rajada, e o watchdog permaneceu saudável.
- [x] Confirmar o primeiro ciclo V73 às 15:00:38 com 122 partidas, quatro
  tarefas, API-Football saudável, zero sinais bloqueados e nenhuma pausa.
- [ ] Continuar aguardando a primeira amostra V71/V72 realmente combinada;
  ausência de mercado comum não autoriza relaxar o filtro.

## Referência independente sincronizada com a entrada V74 — 11/09/2026

- [x] Identificar o gargalo temporal: 128 observações rápidas Bet365 e zero
  pares independentes válidos porque a referência chegava em outro placar,
  minuto ou linha.
- [x] Amostrar a The Odds API na fila rápida somente para `gol_ft` e `gol_ht`
  já comprovados pela BetsAPI/Bet365.
- [x] Limitar a uma tentativa independente por rodada e preservar todos os
  limites persistentes de dia, jogo, cooldown, orçamento e circuito.
- [x] Exigir identidade forte de evento e origem exata de mercado, incluindo
  orientação, placar, período, linha, lados e bookmaker.
- [x] Persistir a referência append-only sem alterar as odds operacionais e
  comparar somente a mesma linha dentro da janela temporal válida.
- [x] Fazer a consulta depois da entrega quando o sinal já estiver aprovado,
  evitando latência adicional no Telegram.
- [x] Expor tentativa, reserva, consulta, linha exata, auditoria, observação,
  comparação e custo estimado no trabalhador e no watchdog.
- [x] Fazer o watchdog rejeitar contagens causais impossíveis ou qualquer
  declaração de influência da referência sobre sinais.
- [x] Provar ponta a ponta em SQLite a formação de exatamente um par temporal
  entre BetsAPI/Bet365 e The Odds/Pinnacle na mesma linha, placar e instante.
- [x] Aprovar 678/678 testes direcionados e 2.629/2.629 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live às 15:23:41 e confirmar trabalhador
  rápido ativo, referência íntegra e efeitos nulos sobre sinais e Telegram.
- [x] Confirmar o primeiro ciclo V74 às 15:28:21: 122 partidas, cinco tarefas,
  cinco coletas de odds bem-sucedidas, API saudável, zero bloqueios e nenhuma
  pausa; watchdog saudável e com zero falhas às 15:29:39.
- [ ] Aguardar a primeira fila real elegível e comprovar no SQLite o par
  temporal exato; ausência natural não deve ser substituída por dado fabricado.
- [ ] Promover qualquer filtro somente após amostra prospectiva suficiente,
  holdout e vantagem líquida comprovada contra o preço independente.

## Evidência sincronizada acumulada V75 — 11/09/2026

- [x] Preservar os contadores da rodada atual para diagnóstico imediato.
- [x] Acrescentar acumulado persistente de rodadas, tentativas, reservas,
  consultas, linha exata, auditorias, observações, comparações e custo estimado.
- [x] Manter o acumulado entre rodadas vazias e reinícios do processo.
- [x] Migrar a última rodada V74 legada sem perder evidência já capturada.
- [x] Persistir motivos e instante da última evidência sincronizada.
- [x] Fazer o watchdog validar versão, não negatividade, cadeia causal, limite
  de comparações, monotonia contra a rodada e efeitos operacionais nulos.
- [x] Fazer estado corrompido ou contagem impossível falhar de forma fechada.
- [x] Expor rodada e acumulado no relatório de status sem alterar sinais.
- [x] Aprovar 370/370 testes direcionados e 2.633/2.633 na regressão integral.
- [x] Retomar os três processos às 15:53:30 e confirmar o acumulado V75
  presente e íntegro, trabalhador ativo e watchdog saudável.
- [ ] Aguardar a primeira observação real elegível; promoção continua proibida
  sem amostra prospectiva, holdout e vantagem líquida comprovada.

## Prioridade causal da referência no alerta enviado V76 — 11/09/2026

- [x] Detectar que uma decisão reprovada podia consumir a única vaga de
  referência independente da rodada, reduzindo a cobertura de entradas reais.
- [x] Reservar a consulta sincronizada somente para materialização concluída
  com estado `enviado`, sempre depois do Telegram.
- [x] Impedir gasto de referência em reprovação, falha de custódia, falha de
  materialização, bloqueio ou duplicidade.
- [x] Instrumentar o funil causal completo até fonte Bet365 executável e vaga
  efetivamente selecionada para consulta.
- [x] Acumular funil e exclusões entre reinícios, preservando separadamente as
  tentativas anteriores à instrumentação sem fabricar sua origem.
- [x] Fazer o watchdog recusar tentativa sem passagem pelo alerta enviado,
  contagens causais impossíveis ou acumulado menor que a rodada.
- [x] Expor o funil acumulado e seu principal gargalo no relatório de status.
- [x] Preservar integralmente HT, FT, pré-live, regras, odds e Telegram.
- [x] Aprovar 410/410 testes direcionados e 2.637/2.637 na regressão integral.
- [x] Retomar os três processos às 16:09:32 e confirmar o funil V76 presente
  e íntegro, trabalhador ativo e watchdog saudável às 16:11:37.
- [ ] Aguardar alerta real Bet365 elegível e comprovar que a referência veio
  depois do envio e formou o par temporal exato sem alterar a entrada.

## Coorte causal da referência posterior ao envio V77 — 11/09/2026

- [x] Vincular cada fotografia independente ao identificador exato do sinal
  realmente entregue, recusando observações sem prova no livro de entregas.
- [x] Exigir que a referência seja coletada depois do envio e que partida,
  mercado, período e linha coincidam com o alerta executável.
- [x] Aceitar somente BetsAPI/Bet365 como lado executável e The Odds API em
  bookmaker independente como referência, ambos com par binário plausível.
- [x] Pré-registrar coortes separadas de 60 sinais para `gol_ft` e `gol_ht`,
  com divisão fixa de 42 no desenvolvimento e 18 no holdout.
- [x] Manter um controle contemporâneo de alertas enviados sem edge para medir
  se a seleção melhora de fato o ROI, e não apenas coincide com bons jogos.
- [x] Exigir 50 resultados edge, 35 no desenvolvimento, 15 no holdout e 30 no
  controle antes de permitir somente uma sinalização para revisão humana.
- [x] Exigir limite inferior positivo nos intervalos de 95% do ROI e do delta
  contra o controle, além de ROI positivo em desenvolvimento e holdout.
- [x] Fazer o watchdog rejeitar violação de cronologia, contagem, partição,
  resultado, intervalo, decisão ou qualquer efeito operacional prematuro.
- [x] Expor auditorias, fotografias, edge, controle, resultados e decisão por
  mercado no relatório de status.
- [x] Preservar HT, FT, pré-live, prioridade, calibração e Telegram sem
  mudanças até vantagem prospectiva ser comprovada e revisada.
- [x] Aprovar 522/522 testes direcionados.
- [x] Aprovar a regressão integral em 2.639/2.639 testes.
- [x] Pré-registrar a coorte às 16:37:56, retomar monitor, watchdog e
  pré-live e confirmar o primeiro ciclo V77 às 16:44:02, com 32 partidas,
  seis tarefas, zero falhas, nenhuma pausa e auditoria V15 saudável.
- [ ] Aguardar a primeira referência real posterior a um alerta elegível e
  comprovar o vínculo causal no SQLite sem fabricar evidência.

## Custódia completa da referência posterior ao envio V78 — 11/09/2026

- [x] Substituir a coorte V77 ainda vazia por uma V2 pré-registrada, sem
  transportar observações da metodologia anterior.
- [x] Exigir a linhagem exata `origem -> leitura técnica -> sinal enviado` da
  materialização rápida gravada no próprio alerta entregue.
- [x] Exigir os critérios revalidados de placar inalterado, linha exata e odd
  fresca antes de aceitar a fotografia independente.
- [x] Conferir o mesmo placar no snapshot do sinal, na materialização, na
  auditoria e na identidade do evento da fonte de referência.
- [x] Persistir e conferir publicação, recebimento e idade da cotação, com
  frescor máximo de 120 segundos e resposta posterior ao alerta.
- [x] Fazer a avaliação V16 excluir linhagem, placar, horário ou frescor não
  comprovados em vez de estimar vantagem com evidência contaminada.
- [x] Preservar `aplicacao_sinais=false`, `altera_calibracao=false`,
  `altera_prioridade=false`, `telegram=false` e
  `promocao_automatica=false`.
- [x] Provar em teste a aceitação da cadeia íntegra e a rejeição de linhagem
  adulterada.
- [x] Aprovar 708/708 testes direcionados e 2.640/2.640 na regressão integral.
- [x] Pré-registrar a V2 às 16:57:22 com zero auditorias/fotografias e retomar
  monitor, watchdog e pré-live às 16:59:27.
- [x] Confirmar o primeiro ciclo V78 às 17:02:46, com 12 partidas, quatro
  tarefas, zero falhas e nenhuma pausa.
- [x] Confirmar às 17:04:08 que o watchdog reconhece avaliação V16, coorte V2
  e auditoria saudáveis, sem problemas nem efeitos operacionais.
- [ ] Aguardar a primeira referência real posterior a um alerta Bet365
  elegível e provar a cadeia completa sem fabricar evidência.

## Referência individual sem margem nas análises V79 — 11/09/2026

- [x] Reavaliar o challenger individual HT/FT contra o preço sem margem e
  recusar promoção: no walk-forward, HT ficou 0,001855 de Brier pior que o
  mercado e FT também não atingiu a melhora mínima pré-registrada.
- [x] Fazer a análise experimental mostrar a probabilidade implícita da
  partida sem margem quando existir par Over/Under ou trio de Próximo Gol
  completo e sincronizado.
- [x] Validar a margem estrutural e omitir referência incompleta, misturada ou
  implausível, sem reconstrução aproximada.
- [x] Rotular explicitamente a informação como referência de preço, não como
  previsão nem garantia do bot.
- [x] Preservar integralmente seleção, filtros, prioridade, calibração,
  liquidação e entrega HT/FT; a mudança é apenas informativa.
- [x] Aprovar 126/126 testes direcionados e 2.643/2.643 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live com novos processos, confirmar ciclo
  às 17:23:39 com seis partidas, cinco tarefas, zero falhas e trabalhador de
  odds ativo.
- [ ] Observar a primeira análise real com referência sincronizada e confirmar
  no Telegram que o bloco corresponde à fotografia exata da entrada.

## Tentativa Telegram com estado único V80 — 11/09/2026

- [x] Corrigir o envio principal, de teste e de aviso insuficiente para
  finalizar no próprio claim reservado, preservando seu token e sua prova.
- [x] Fazer sucesso, timeout e recuperação representarem uma única tentativa
  persistida em vez do par artificial `enviando` mais estado final.
- [x] Manter timeout como `incerto`, sem reenvio automático e sem presumir que
  a mensagem chegou ou deixou de chegar ao Telegram.
- [x] Deduplicar apenas a leitura das pendências históricas pelo par lógico
  sinal/canal, escolhendo a tentativa pendente mais recente.
- [x] Impedir reconciliação manual de uma pendência histórica já substituída
  por outra mais recente do mesmo sinal e canal.
- [x] Confirmar que a única anomalia histórica aparece como uma pendência, não
  duas, e preservar sua exigência de conferência humana.
- [x] Aprovar 439/439 testes direcionados e 2.644/2.644 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live às 17:35, confirmar trabalhador
  rápido ativo e primeiro ciclo V80 às 17:39:58: sete partidas, seis tarefas,
  zero falhas, nenhuma pausa e uma única pendência histórica de análise.

## Liquidação neutra e ROI por exposição V81 — 11/09/2026

- [x] Confirmar no SQLite que os três `voids` da regra asiática ativa são
  devoluções contratuais coerentes, com retorno zero, e não corrupção.
- [x] Manter `void` fora do alvo binário sem convertê-lo em green/red e sem
  removê-lo da ordem causal das exposições.
- [x] Permitir que a coorte alcance 100 liquidações binárias dentro das
  primeiras 300 exposições, preenchendo apenas devoluções íntegras e sem
  consultar qual decisão posterior foi green ou red.
- [x] Manter `sem_dado`, retorno incompatível, odd inválida e relógio incoerente
  em modo fail-closed, ainda bloqueando calibração e envio oficial.
- [x] Fazer a auditoria de diversidade, partição e frescor usar exatamente a
  mesma definição da coorte do modelo.
- [x] Corrigir o ROI para dividir o lucro por todas as exposições liquidadas,
  inclusive devoluções, preservando a taxa de acerto apenas em green/red.
- [x] Escolher a primeira exposição de cada partida antes de anexar o resultado,
  impedindo substituir retrospectivamente um `void` ou `sem_dado` por sinal
  posterior vencedor.
- [x] Recalcular em leitura a regra asiática ativa: 39 decisões binárias, 3
  devoluções, 42 exposições liquidadas, acerto de 87,18% e ROI honesto de
  56,94% (antes aparecia 61,3% por ignorar as devoluções no denominador).
- [x] Preservar como `sem_dado` a partida América x Austin: houve prorrogação
  e o total regulamentar de cantos não pode ser inferido com segurança.
- [x] Recusar dois recalibradores individuais simplificados no holdout temporal:
  FT piorou o Brier em 0,002432 e HT em 0,000653 contra o preço sem margem.
- [x] Aprovar 480/480 testes direcionados e 2.649/2.649 na regressão integral.
- [x] Retomar os três processos, confirmar a recalibração V10 no primeiro
  ciclo e verificar watchdog, trabalhador rápido e Telegram sem regressão.

## Ponte causal pré-live/API V82 — 11/09/2026

- [x] Auditar 167 decisões FT entre 5 e 25 minutos e localizar 50 bloqueios por
  contexto pré-jogo indisponível; 48 vieram de incompatibilidade/ausência na
  lista global da API, e não dos filtros esportivos do sinal.
- [x] Reaproveitar somente contextos pré-live calculados antes do início, com
  fixture ID exato, modelo presente e qualidade de contexto de pelo menos 80.
- [x] Consultar o fixture ID detalhado quando a lista ao vivo omitir o jogo,
  dentro da mesma cota e capacidade já controladas.
- [x] Revalidar status ao vivo, nomes, placar, minuto e categoria antes de
  entregar a partida ao motor normal; jogos agendados ou encerrados falham
  fechados.
- [x] Impedir que o contexto pré-live aprove, promova ou envie sinais por si só;
  odds, pressão, finalizações, qualidade e todos os gates HT/FT permanecem.
- [x] Confirmar 12 contextos causais no dia e, em reconstrução de leitura,
  associar três partidas atuais, incluindo uma omitida da lista publicada.
- [x] Aprovar 191/191 testes direcionados e 2.653/2.653 na regressão integral.
- [x] Retomar os três processos e confirmar o primeiro ciclo real V82 às
  18:32:40, com oito partidas, seis tarefas processadas, zero falhas de API,
  nenhuma pausa preventiva e todos os componentes responsivos.

## Separação honesta das exposições por fonte V83 — 11/09/2026

- [x] Detectar que o relatório de fontes misturava entregas de teste,
  estratégias antigas e resultados contrafactuais de candidatos rejeitados.
- [x] Separar cada exposição por modo de entrega, versão da regra, estratégia
  sombra e status, preservando o agregado apenas como visão descritiva.
- [x] Excluir mensagens derivadas como resultado, cancelamento, aguardar odd e
  correção para que não sejam contadas como novas entradas.
- [x] Confirmar que as 60 liquidações HT atribuídas à BetsAPI eram simulações
  de teste, com zero entregas oficiais, e que o prejuízo estava concentrado em
  estratégias antigas incompatíveis com o ramo antecipado atual.
- [x] Impedir conclusão causal sobre custo-benefício de uma fonte enquanto não
  houver comparação temporal pareada suficiente no mesmo mercado e estratégia.
- [x] Preservar integralmente os critérios esportivos, odds, prioridade e
  entregas HT/FT; a mudança corrige medição e futuras decisões de calibração.
- [x] Aprovar 12/12 testes direcionados e 2.658/2.658 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live e confirmar o primeiro ciclo V83
  às 18:48:56, com dez partidas, sete tarefas processadas, três adiadas pelo
  orçamento normal, zero falhas de API e nenhuma pausa preventiva.

## Contribuição de preço pareada ao sinal V84 — 11/09/2026

- [x] Impedir que comparações apenas da mesma partida sejam atribuídas ao sinal
  quando mercado, período, linha ou lado forem diferentes.
- [x] Exigir coincidência de sinal entregue, fotografia, fonte, bookmaker e odd
  antes de reconhecer o preço efetivamente escolhido.
- [x] Separar referência independente, mesma bookmaker e bookmaker parcial;
  somente fontes e casas distintas podem medir contribuição de preço.
- [x] Deduplicar múltiplas comparações do mesmo sinal, priorizando referência
  independente e o menor intervalo temporal.
- [x] Calcular o ganho de preço para o mesmo resultado contratual, incluindo
  `half_green`, `half_red` e `void`, sem atribuir à fonte o resultado do jogo.
- [x] Exigir 30 partidas no mesmo estrato de regra, estratégia, modo e status,
  com limite inferior positivo do intervalo de 95%, antes de marcar vantagem
  de preço somente como apta à revisão.
- [x] Manter aplicação em sinais, calibração, Telegram e promoção automática
  explicitamente bloqueadas.
- [x] Auditar os dados reais: quatro sinais tinham par exato, mas três possuíam
  bookmaker parcial e um comparava a mesma casa; zero referências independentes
  e nenhuma mudança operacional foram autorizadas.
- [x] Aprovar 17/17 testes direcionados e 2.663/2.663 na regressão integral.
- [x] Confirmar que a implantação analítica não interrompeu produção: três
  processos ativos, watchdog saudável, trabalhador rápido sem erro e ciclo
  das 19:00:37 com zero falhas de API.
- [ ] Acumular naturalmente 30 pares independentes homogêneos; não preencher
  ausência de evidência com comparações de outro mercado ou da mesma casa.

## Melhor preço exato prospectivo em sombra V85 — 11/09/2026

- [x] Medir prospectivamente se o seletor atual, orientado primeiro por frescor,
  deixou disponível uma odd melhor para exatamente o mesmo contrato.
- [x] Cobrir gols FT/HT, próximo gol, próximo escanteio e escanteios asiáticos
  FT, 1T e 2T sem alterar candidato, probabilidade, status ou bloqueios.
- [x] Exigir mesmo mercado, período, linha e seleção; mercados binários precisam
  dos dois lados e próximo gol precisa das três seleções válidas.
- [x] Exigir cotação congelada, fonte, bookmaker e idade máxima de 360 segundos;
  linha diferente, cotação velha, oferta incompleta, mesma fonte ou mesma casa
  falham fechadas.
- [x] Persistir a observação somente em `features.melhor_preco_sombra`, com
  aplicação em sinais, calibração, Telegram e promoção automática desativadas.
- [x] Deduplicar fotografias repetidas da mesma partida e exigir 30 partidas
  homogêneas, além de limite inferior positivo no intervalo de 95%, para marcar
  uma possível vantagem apenas como apta à revisão do seletor.
- [x] Aprovar 233/233 testes direcionados e 2.675/2.675 na regressão integral.
- [x] Retomar os três processos e confirmar o primeiro ciclo V85 às 19:18:14:
  11 partidas, oito tarefas processadas, três adiadas normalmente, lista
  consistente, zero falhas de rede e nenhuma pausa preventiva.
- [x] Confirmar 45 observações prospectivas reais no primeiro ciclo, todas com
  `aplicacao_sinais=false`; nenhuma comparação independente exata ficou pronta.
- [ ] Acumular naturalmente 30 pares independentes exatos e homogêneos antes de
  considerar qualquer mudança no seletor de preços.

## Ponte da referência separada ao melhor preço V86 — 11/09/2026

- [x] Identificar no banco que a referência independente já era persistida em
  `odds_referencia_sombra`, mas não chegava ao comparador prospectivo V85.
- [x] Entregar ao comparador as odds operacionais e a referência em estruturas
  separadas, sem mesclar a referência no motor, na odd escolhida ou na fila.
- [x] Registrar a camada de origem de cada preço e contagens separadas de ofertas
  operacionais e de referência para tornar a ausência de par diagnosticável.
- [x] Manter igualdade estrita de mercado, período, linha e seleção, além de
  fonte e bookmaker distintos, par completo, frescor e proveniência íntegra.
- [x] Versionar o medidor e a coorte como V2, impedindo misturar fotografias V85
  anteriores à ponte com as novas observações prospectivas V86.
- [x] Manter aplicação em sinais, calibração, Telegram e promoção automática
  explicitamente falsas e cobertas por teste de integração do serviço.
- [x] Aprovar 218/218 testes direcionados e 2.677/2.677 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live e confirmar o primeiro ciclo V86 às
  19:40:49: dez partidas, oito processadas, duas adiadas, lista consistente,
  zero falhas de rede e nenhuma pausa preventiva.
- [x] Confirmar no SQLite 41 observações V86 em oito partidas, todas sem efeito
  operacional; nenhuma recebeu referência nova porque os jogos vistos não
  estavam cobertos, não foram pareados ou já tinham usado a cota diária.
- [x] Confirmar watchdog saudável, trabalhador rápido ativo, zero falhas e
  integridade da referência sombra verdadeira após a retomada.
- [x] Observar o primeiro evento novo coberto pelas duas fontes e comprovar no
  SQLite uma comparação independente exata, concluído pela coorte V87 sem
  qualquer revisão operacional automática.

## Supervisão da ponte de melhor preço V87 — 12/09/2026

- [x] Criar um supervisor somente de leitura no SQLite para conferir a ponte
  entre a referência separada e a medição prospectiva de melhor preço.
- [x] Isolar fotografias antigas em coortes anteriores e iniciar a coorte V3,
  impedindo que registros sem os novos campos sejam tratados como falha atual.
- [x] Validar os bloqueios de efeito operacional, os contadores de ofertas, a
  identidade de fonte e bookmaker, a relação de preço e a ponte de persistência.
- [x] Tratar falta de cobertura ou de par exato como coleta incompleta, e não
  como falha do bot; somente vazamento operacional declarado degrada a saúde.
- [x] Expor o estado do supervisor no status e protegê-lo pelo watchdog sem
  alterar HT, FT, probabilidade, calibração, Telegram ou seleção de odds.
- [x] Aprovar 428/428 testes direcionados e 2.684/2.684 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live e confirmar o primeiro ciclo V87 às
  15:41:17: 147 jogos, seis tarefas processadas, 22 adiadas pelo orçamento
  normal, lista consistente, zero falhas de rede e nenhuma pausa preventiva.
- [x] Comprovar o primeiro par independente exato em produção: Zagłębie Lubin x
  Katowice, gols FT acima de 1,5, Bet365/BetsAPI @1,50 contra Pinnacle/The Odds
  API @1,50; diferença zero e relação equivalente, sem alegar vantagem.
- [x] Confirmar watchdog saudável, trabalhador rápido ativo, 45 observações em
  sete partidas e zero violações de efeito, estrutura ou persistência.
- [x] Confirmar no relatório três estratos da mesma partida, uma única partida
  distinta, diferença média zero e nenhuma promoção automática.
- [ ] Acumular naturalmente 30 partidas distintas no mesmo estrato homogêneo
  antes de autorizar qualquer revisão humana do seletor de preços.

## Preço justo independente no instante da decisão V88 — 12/09/2026

- [x] Separar diferença nominal de odd e vantagem real: uma cotação maior não
  é mais tratada como indício de edge sem remover a margem da referência.
- [x] Exigir mercado completo e sincronizado: Over/Under nas linhas binárias ou
  três seleções no Próximo Gol, com margem da bookmaker em faixa plausível.
- [x] Calcular probabilidade independente sem vig, ponto de equilíbrio da odd
  executável, vantagem em pontos percentuais e valor esperado prospectivo.
- [x] Escolher a referência de valor por frescor e identidade determinística,
  nunca pela odd mais favorável à hipótese, evitando seleção retrospectiva.
- [x] Manter preço justo, edge e classificação integralmente em sombra, com
  sinais, HT, FT, calibração, Telegram e promoção automática desativados.
- [x] Fazer o supervisor recalcular a matemática, conferir independência das
  fontes/bookmakers e detectar qualquer efeito ou telemetria adulterada.
- [x] Ampliar o relatório com amostra, partidas distintas, EV médio, IC95 e um
  gate de pelo menos 30 partidas homogêneas que libera apenas revisão humana.
- [x] Aprovar 680/680 testes direcionados e 2.691/2.691 na regressão integral.
- [x] Retomar os três processos com hashes atuais e confirmar o primeiro ciclo
  V88 às 16:01:47: 79 partidas, cinco tarefas processadas, 23 adiadas pelo
  orçamento normal, lista consistente, zero falhas e nenhuma pausa preventiva.
- [x] Comprovar cálculo real em Atlético Mineiro x Fluminense, Over 0,5 FT:
  Bet365/BetsAPI @1,3636, Pinnacle/The Odds API @1,33, probabilidade justa
  70,8972%, ponto de equilíbrio 73,3353% e EV -3,3246%; sem vantagem.
- [x] Confirmar watchdog saudável, trabalhador rápido ativo, 40 observações em
  sete partidas, uma avaliação de preço justo e zero violações.
- [x] Encerrar a coorte V88 sem promoção ao identificar que ela ainda não
  armazenava prova explícita de mesmo placar e sincronismo entre as fontes;
  a coleta válida recomeça na metodologia V89.

## Sincronismo causal do preço justo V89 — 12/09/2026

- [x] Exigir identidade de evento confirmada nas odds executável e independente,
  com mandante, visitante e placar exatamente iguais antes de calcular edge.
- [x] Exigir diferença temporal máxima de 60 segundos entre as duas cotações e
  persistir o intervalo real usado em cada observação.
- [x] Exigir que a oferta operacional observada coincida em fonte, bookmaker,
  odd e instante com a cotação congelada do candidato.
- [x] Manter a comparação nominal de preço disponível para diagnóstico quando
  o estado divergir, mas impedir que ela seja chamada de preço justo ou edge.
- [x] Versionar medidor, cálculo e relatório, isolando as avaliações V88 que não
  possuíam a nova prova causal e reiniciando a coorte sem transportar resultados.
- [x] Validar placar divergente, intervalo acima de 60 segundos e cotação
  operacional divergente como falhas fechadas do cálculo de valor.
- [x] Aprovar 683/683 testes direcionados e 2.694/2.694 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais e confirmar o
  primeiro ciclo V89 às 16:23:31: 64 partidas, seis tarefas processadas, 22
  adiadas pelo orçamento normal, lista consistente, zero falhas e nenhuma pausa.
- [x] Comprovar a primeira observação sincronizada em Grêmio x Vasco, Over 1,5
  FT: placar 1–0 nas duas fontes, intervalo de 22,377 s, Bet365 @1,4444,
  probabilidade Pinnacle sem vig 73,1809% e EV de +5,7025%.
- [x] Confirmar que o edge não contorna os critérios esportivos: a observação
  foi rejeitada por zero finalizações recentes e histórico de 5 min insuficiente;
  a cópia de auditoria permaneceu silenciosa.
- [x] Confirmar watchdog saudável, trabalhador rápido ativo, 37 observações em
  seis partidas, duas avaliações sincronizadas da mesma partida e zero violações.
- [ ] Acumular pelo menos 30 partidas distintas e resultados posteriores no
  mesmo estrato antes de avaliar se edge sincronizado melhora ROI de fato.

## Resultado prospectivo do preço justo V90 — 12/09/2026

- [x] Congelar em cada nova observação, antes do resultado, a política
  `validacao-resultado-valor-justo-sincronizado-v1` e seu SHA-256.
- [x] Reiniciar a coorte na V6 sem transportar as observações V89, garantindo
  que nenhum resultado conhecido participe da seleção da amostra.
- [x] Escolher somente o primeiro sinal elegível de cada partida e mercado;
  sinais `rejeitado` nunca entram na liquidação de edge ou controle.
- [x] Separar `desajuste_favoravel` e `controle_sem_desajuste`, com retorno,
  ROI, IC95, taxa direcional, Brier e viés de calibração por mercado.
- [x] Congelar por mercado 100 candidatos em ordem temporal: 70 para
  desenvolvimento e 30 para holdout, sem janela móvel ou substituição de um
  candidato pendente por outro cujo resultado já seja conhecido.
- [x] Exigir 80 liquidações, 55 no desenvolvimento, 25 no holdout, pelo menos
  30 edge, 30 controles e representação dos dois grupos no holdout antes de
  liberar somente revisão humana.
- [x] Exigir ROI edge positivo, superior ao controle nos dois períodos e
  limite inferior positivo do IC95 da diferença; nunca promover sozinho.
- [x] Validar que `encerrado_em` seja posterior ao sinal, que green/red/void e
  retorno sejam coerentes e que resultados inválidos tornem a supervisão não
  saudável.
- [x] Reforçar a identidade das fontes exigindo schema e fonte da identidade
  do evento coerentes com a cotação executável e a referência.
- [x] Expor a coorte no relatório, status e watchdog, mantendo HT, FT,
  calibração, seleção, prioridade e Telegram inalterados.
- [x] Aprovar 116/116 testes direcionados e 2.698/2.698 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais. O primeiro ciclo
  V90 terminou às 16:46:56 com 48 jogos, seis tarefas processadas, 22 adiadas
  normalmente, lista consistente, zero falhas de rede e nenhuma pausa.
- [x] Confirmar 31 observações V6 em seis partidas, política íntegra em todas,
  supervisor e watchdog saudáveis e zero violações; ainda não houve um preço
  justo sincronizado elegível para iniciar a liquidação da nova coorte.
- [ ] Acumular os 100 primeiros candidatos e resultados posteriores de cada
  mercado; qualquer vantagem continuará sem efeito até revisão independente.

## Cota independente orientada a candidatos V91 — 12/09/2026

- [x] Adiar a consulta de preço independente até o candidato atravessar as
  políticas finais e possuir cotação executável Bet365/BetsAPI congelada.
- [x] Excluir rejeitados, linhas sem proveniência e mercados que já formaram
  candidato sincronizado no mesmo jogo, evitando consumo sem valor estatístico.
- [x] Preservar a pré-seleção gratuita de competição e evento antes de qualquer
  reserva de créditos na The Odds API.
- [x] Permitir somente uma consulta adicional de recuperação quando as duas
  vagas antigas daquele jogo já foram usadas antes da criação da coorte V90.
- [x] Manter limite diário, cooldown, circuito, reserva mensal e limite por
  ciclo obrigatórios também na recuperação; uma quarta tentativa é bloqueada.
- [x] Versionar a auditoria regular como V5 e persistir se a recuperação foi
  solicitada/aplicada e qual limite efetivo protegeu o jogo.
- [x] Manter a consulta inteiramente em sombra, sem alterar seleção, HT, FT,
  probabilidade, calibração, Telegram ou promoção automática.
- [x] Aprovar 317/317 testes direcionados e 2.701/2.701 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live com hashes atuais e confirmar o
  primeiro ciclo V91 às 17:07:03: 31 partidas, seis tarefas processadas, 22
  adiadas normalmente, lista consistente, zero falhas e nenhuma pausa.
- [x] Confirmar que os seis jogos do ciclo não tinham candidato Bet365
  liquidável: zero reservas e seis descartes explicados, sem desperdiçar cota.
- [x] Confirmar supervisor saudável sobre 111 observações em 14 partidas, uma
  comparação exata e zero violações de efeito, estrutura, ponte ou política.
- [ ] Aguardar a primeira oportunidade real elegível V91 para comprovar em
  produção a auditoria V5 e, se necessário, a recuperação única da terceira
  consulta; a ausência dessa combinação em um ciclo permanece normal.

## Cobertura causal das auditorias silenciosas V92 — 12/09/2026

- [x] Identificar que a coleta V91 acontecia antes da materialização das cópias
  `auditoria`, deixando descartes promissores sem referência independente.
- [x] Extrair um classificador único e sem persistência para prever exatamente
  os descartes que formarão auditoria silenciosa depois do snapshot.
- [x] Permitir coleta de referência apenas para essa auditoria prevista quando
  a cotação Bet365/BetsAPI estiver congelada e o mercado ainda não tiver coorte.
- [x] Continuar excluindo rejeitados comuns, bloqueios estruturais, odds fora da
  faixa, baixa pontuação, outras fontes e mercados não suportados.
- [x] Manter o candidato original rejeitado e preservar sinais, HT, FT,
  calibração, prioridade, Telegram e promoção automática sem qualquer efeito.
- [x] Confirmar no SQLite uma oportunidade real perdida após a V91: auditoria
  de gol FT @1,3636, pontuação 65, cotação Bet365 congelada e sem par externo.
- [x] Aprovar 318/318 testes direcionados e 2.702/2.702 na regressão integral.
- [x] Retomar os três processos com hashes atuais e confirmar o primeiro ciclo
  V92 às 17:24:42: 31 partidas, dez tarefas processadas, 18 adiadas pelo
  orçamento normal, lista consistente, zero falhas e nenhuma pausa.
- [x] Comprovar em produção três auditorias previstas e priorizadas antes da
  materialização; duas competições sem cobertura e um evento não pareado foram
  descartados antes da reserva, com zero cota desperdiçada e zero sinal enviado.
- [ ] Aguardar uma auditoria prevista em competição e evento cobertos para
  comprovar o primeiro par independente exato V5 dessa nova rota.

## Referência multibookmaker API-Football V93 — 12/09/2026

- [x] Adicionar uma segunda rota de referência sombra quando a The Odds API
  não devolver oferta para o candidato já priorizado pela V92.
- [x] Consultar na API-Football apenas gols FT, gols HT e escanteios asiáticos
  FT, reutilizando o cache global de cinco minutos por mercado.
- [x] Excluir Bet365 e aceitar somente bookmakers alternativas com mercado
  Over/Under completo; nunca reutilizar a mesma casa da cotação executável.
- [x] Ordenar bookmakers por identidade lexical e limitar a cinco, sem olhar o
  tamanho da odd e sem selecionar retrospectivamente a referência favorável.
- [x] Exigir fixture fortemente associada, placar API igual ao PackBall e
  identidade causal completa antes de permitir comparação sincronizada.
- [x] Manter a nova fonte somente em sombra e sem efeito em seleção, sinais,
  HT, FT, calibração, prioridade, Telegram ou promoção automática.
- [x] Disponibilizar rollback imediato por
  `API_FOOTBALL_REFERENCIA_SOMBRA_ATIVA=0`.
- [x] Aprovar 394/394 testes direcionados e 2.704/2.704 na regressão integral.
- [x] Retomar monitor, watchdog e pré-live com hashes carregados iguais aos
  arquivos atuais e validar o primeiro ciclo V93 em produção.
- [x] Confirmar no primeiro ciclo real 34 partidas, 10 tarefas processadas,
  18 adiadas, lista consistente, zero falhas de rede e nenhuma pausa
  preventiva. A rota V93 foi acionada em três candidatos e recusou todos de
  modo seguro por ausência de bookmaker independente válida.
- [ ] Observar a primeira bookmaker alternativa real da API-Football com linha
  e placar sincronizados; até lá, manter a rota exclusivamente em sombra.

## Supervisão da referência API-Football V94 — 12/09/2026

- [x] Criar auditor somente leitura do SQLite para a rota multibookmaker V93.
- [x] Tratar ausência de outra bookmaker como coleta normal, sem degradar HT,
  FT, prioridade, calibração ou Telegram.
- [x] Conferir mercados suportados, contadores, exclusão obrigatória da Bet365,
  efeitos desativados e coerência entre pareamento declarado e odds realmente
  persistidas no mesmo snapshot.
- [x] Classificar vazamento operacional declarado como crítico e telemetria
  inconsistente como atenção, sem transformar falta de cobertura em falha.
- [x] Expor tentativas, referências, partidas, consultas e violações no status
  e no estado persistente do watchdog.
- [x] Incluir o novo supervisor na assinatura transitiva de código do watchdog.
- [x] Aprovar 691/691 testes integrados e 2.709/2.709 na regressão integral.
- [x] Validar o banco real: 19 snapshots, 13 partidas, quatro tentativas, zero
  falsas referências e zero violações de efeito, estrutura ou persistência.
- [x] Retomar os três processos e confirmar o primeiro ciclo real V94 às
  18:06:36: 30 partidas, oito tarefas processadas, 20 adiadas pelo orçamento
  normal, lista consistente, zero falhas de rede e nenhuma pausa preventiva.
- [x] Confirmar o watchdog novamente saudável após a manutenção, com o
  supervisor V94 saudável, quatro tentativas históricas e zero violações.

## Transferência do edge por origem V95 — 12/09/2026

- [x] Identificar que a validação V90 agregava candidatos acionáveis e cópias
  de auditoria silenciosa no mesmo placar de edge e controle.
- [x] Pré-registrar antes de novos resultados o marco
  `2026-09-12T18:20:00-04:00`, a definição SHA-256 e os dois estratos fixos.
- [x] Separar `aprovado`/`simulacao` como candidatos acionáveis e `auditoria`
  como auditorias silenciosas, usando apenas o status congelado antes do jogo.
- [x] Manter coortes independentes de 100 por mercado em cada origem, com o
  mesmo desenvolvimento 70/holdout 30 e os mesmos limites conservadores V90.
- [x] Exigir vantagem completa nos dois estratos para declará-la transferível;
  uma vantagem agregada isolada deixa de ser evidência suficiente.
- [x] Expor composição e estado da transferência no status e no watchdog, sem
  alterar sinais, HT, FT, calibração, prioridade, Telegram ou promoção.
- [x] Corrigir o supervisor da referência API-Football para aceitar uma recusa
  segura anterior à consulta, sem tolerar detalhes ausentes após uma consulta.
- [x] Aprovar 383/383 testes do supervisor e 2.713/2.713 na regressão integral.
- [x] Confirmar o primeiro ciclo V95 às 18:29:40: 25 partidas, nove análises,
  watchdog saudável, nenhuma pausa preventiva e coorte V95 registrada.
- [x] Retomar após a correção do supervisor e confirmar o ciclo às 18:44:56:
  26 partidas, nove análises, três processos responsivos, hashes coincidentes,
  15 tentativas de referência e zero violações em todos os supervisores.
- [ ] Acumular separadamente os primeiros acionáveis e auditorias silenciosas
  pós-marco; a ausência inicial de candidatos sincronizados é esperada.

## Capacidade multibookmaker adaptativa V96 — 12/09/2026

- [x] Comprovar no payload real do bet 25 que 21 fixtures continham odds, mas
  nenhuma estrutura `bookmakers`; a odd agregada sem nome da casa continua
  proibida como suposta referência independente.
- [x] Persistir por mercado a quantidade de amostras, fixtures, fixtures com
  bookmaker, nomes disponíveis, ausências consecutivas e próxima sondagem.
- [x] Suprimir somente a consulta adicional de referência quando uma resposta
  não vazia já comprovou ausência de identidade, preservando integralmente as
  consultas operacionais normais da API-Football.
- [x] Reabrir a sondagem automaticamente após seis horas e imediatamente com
  `API_FOOTBALL_REFERENCIA_FORCAR_SONDAGEM=1`, evitando desativação permanente
  caso o provedor passe a expor bookmakers no futuro.
- [x] Fazer uma resposta operacional posterior com bookmakers recuperar a
  capacidade automaticamente, inclusive após reinício do processo.
- [x] Expor consultas realmente realizadas, consultas evitadas e mercados sem
  identidade no diagnóstico persistido, status e supervisor somente leitura.
- [x] Falhar fechado se os novos contadores, motivos ou efeitos declarados não
  coincidirem com os detalhes de cada mercado.
- [x] Manter seleção, HT, FT, calibração, prioridade, Telegram e promoção
  automática inalterados; esta camada conserva cota e qualidade causal.
- [x] Aprovar 646/646 testes integrados e 2.718/2.718 na regressão integral.
- [x] Retomar os três processos com hashes atuais e comprovar em produção a
  primeira amostra V96, sua supressão persistente e o próximo ciclo saudável.
- [x] Confirmar no ciclo encerrado às 19:08:07: 33 partidas, oito análises,
  watchdog saudável, nenhuma pausa, 38 fixtures de gols FT e 32 de escanteios
  FT sem identidade; uma consulta extra de gol FT foi evitada às 19:06:10.
- [x] Auditar 97 snapshots em 23 partidas: estado V3 informativo, uma consulta
  evitada e zero violações de efeito, estrutura ou persistência.

## Validação prospectiva do veto por preço justo negativo V97 — 12/09/2026

- [x] Pré-registrar, antes de qualquer novo resultado, o marco
  `2026-09-12T19:30:00-04:00`, a política imutável e seu SHA-256.
- [x] Classificar em sombra cada primeiro sinal de partida/mercado/origem como
  `veto_preco_negativo`, `controle_nao_veto` ou inelegível sem preço justo.
- [x] Fixar o candidato a veto em valor esperado externo menor ou igual a
  -5%, sem ajustar o limite aos reds já observados.
- [x] Separar candidatos acionáveis (`aprovado`/`simulacao`) de auditorias
  silenciosas (`auditoria`) e exigir comprovação independente nos dois grupos.
- [x] Congelar coortes de 120 por mercado e origem, com desenvolvimento 80 e
  holdout 40, mínimos por grupo e intervalos de confiança conservadores.
- [x] Exigir pior retorno do grupo veto no total, desenvolvimento e holdout;
  coincidência agregada isolada não autoriza mudança operacional.
- [x] Manter o estudo sem efeito em sinais, HT, FT, calibração, prioridade,
  Telegram ou promoção automática até revisão humana após evidência completa.
- [x] Integrar a validação ao supervisor, status e assinatura transitiva do
  monitor e watchdog, com falha fechada para adulteração da classificação.
- [x] Aprovar 422/422 testes direcionados e 2.722/2.722 na regressão integral.
- [x] Validar o SQLite operacional: estado saudável
  `aguardando_candidatos_pos_ancora`, zero candidatos e zero violações antes
  da retomada.
- [x] Retomar os três processos com os hashes V97 e confirmar o primeiro ciclo
  real às 19:29:35: 45 partidas, oito análises, zero falhas de rede, nenhuma
  pausa e nenhuma alteração no volume ou na seleção de sinais.
- [x] Confirmar o supervisor saudável sobre 852 observações em 37 partidas,
  sete comparações exatas e zero violações de efeito, estrutura ou persistência.
- [ ] Acumular a coorte prospectiva; somente depois dos mínimos completos
  decidir manualmente se preço justo negativo merece veto de segurança.
