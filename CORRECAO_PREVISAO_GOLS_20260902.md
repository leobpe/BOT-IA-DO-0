# Correção de direção das previsões — 02/09/2026

## Problema corrigido

As rotas HT 0–0/min20 e FT tendência extraíam apenas o número de
`previsao_provedor.over_under`. Assim, `-3.5` podia contar como apoio a over
2,5 no HT, e `-2.5` como apoio à tendência 1,5–2,5 no FT.

A leitura compartilhada em `previsao_gols_provedor.py` exige direção explícita:
`+2.5`/`over 2.5` significam over; `-2.5`/`under 2.5`, under. Aceita vírgula
decimal e o sinal de menos Unicode. Dados ambíguos ou sem direção não viram
evidência favorável. Under não é veto global: os demais apoios válidos continuam
contando pelas regras existentes.

Limites direcionais por equipe, como `+1.5` e `-2.5`, não são mais tratados como
médias de gols esperados. A soma exige duas estimativas pontuais completas,
finitas e não negativas; ausência de dado não equivale a zero.

## Preservado

- Janelas de minuto, placares, linhas, odds e qualidade mínima.
- Histórico geral/mandante/visitante e os apoios por linha do FT.
- Filtro de chutes recentes do HT, incluindo a nova versão técnica.
- Métodos não relacionados, pré-live, escanteios, Scanner e sessão PackBall.
- Registros anteriores, resultados e entregas oficiais.

As duas rotas e suas âncoras passam de v3 para v4 para registrar a mudança
sem modificar as âncoras imutáveis anteriores. O novo arquivo integra a
verificação de versão em execução do monitor e supervisor. As autorizações
de envio existentes permanecem; não foi ativado nenhum método desativado.

## Verificação

- 54 testes específicos passaram.
- Suíte completa: 2.038 testes passaram.
- Casos cobertos: over/under, sinais e vírgula, dados ausentes/ambíguos,
  faixas que não são médias, outros apoios válidos, preservação das âncoras v3
  e filtro de chutes aplicado ao HT v4.
- Reinício validado: monitor, supervisor e pré-live ativos; código do monitor
  e supervisor atualizado; âncoras HT/FT v4 válidas. Os hashes das duas
  âncoras v3 permaneceram idênticos após o reinício.

Esta correção não garante acertos e não atribui todas as perdas anteriores
a esse erro. Não recalcula resultados passados nem os transfere para a
estatística da nova versão técnica.
