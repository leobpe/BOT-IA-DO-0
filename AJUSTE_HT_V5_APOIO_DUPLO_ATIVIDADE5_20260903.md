# HT 0-0 v5: apoio duplo e atividade recente

Aplicado em 03/09/2026 somente à rota HT 0-0 entre 20 e 28 minutos.

## Critérios obrigatórios

- placar 0-0 e linha Over 0.5 HT;
- odd mínima 1.44 e qualidade de dados mínima 80;
- evidência pré-jogo de Over 2.5;
- evidência histórica de ambas marcam;
- janela válida dos últimos 5 minutos, aceitando a tolerância temporal existente de 5 a 8 minutos;
- pelo menos um chute total confirmado nessa janela;
- sem reset ou inconsistência na contagem de chutes.

Os critérios de Over 2.5 e ambas marcam agora precisam ocorrer juntos. A leitura de
Over/Under corrigida na v4 foi preservada. Cartão vermelho continua registrado sem
veto automático. Os demais métodos e controles do bot não foram alterados.

## Segurança e reversão

A versão recebeu nova linhagem e nova âncora prospectiva, sem sobrescrever as
âncoras v3 e v4. O filtro independente de chutes recentes também reconhece a v5.

Reversão operacional imediata da rota: `GOL_HT_00_MIN20_GRUPO_ATIVO=0`.

Para voltar exatamente à seleção anterior, restaurar a implementação v4 e sua
âncora correspondente após parar o sistema com segurança.

## Evidência que motivou o ajuste

Na análise retrospectiva disponível, a combinação de apoio duplo e atividade
recente selecionou 15 greens e 5 reds entre v3/v4. Esse recorte serve como hipótese
de melhoria, não como garantia de desempenho futuro. A v5 inicia sua própria
validação prospectiva.
