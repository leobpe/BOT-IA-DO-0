# Continuidade do projeto PackBall no segundo computador

## Meta principal

Evoluir o bot PackBall para um sistema profissional e resiliente de monitoramento ao vivo, com historico temporal persistente, SQLite, validacao API-Football, motor de sinais calibrado por backtest, alertas Telegram, observabilidade, recuperacao automatica e operacao continua segura.

Esta meta ainda nao foi concluida. A calibracao dos mercados continua em desenvolvimento e nenhum resultado deve ser tratado como garantia de lucro.

## Estado da transferencia

- O sistema foi parado com seguranca no computador principal antes da copia.
- O pacote verificado foi criado como `PackBall_transferencia`.
- A verificacao registrou 216 arquivos, 216 checksums validos e banco SQLite integro.
- O banco transferido contem o historico e as calibracoes acumuladas.
- A pasta `.venv` nao foi transferida de proposito e deve ser recriada no segundo computador.
- Nunca executar o bot nos dois computadores simultaneamente.

## Primeiro procedimento no segundo computador

1. Trabalhar com a pasta copiada localmente, preferencialmente em `Documents\BOT IA DO 0`, e nao diretamente no HD externo.
2. Nao iniciar o monitor antes de concluir a verificacao e a instalacao.
3. No terminal da pasta do projeto, executar:

   `py instalar_secundario.py --somente-verificar`

4. Se a verificacao indicar que o computador esta pronto, executar:

   `py instalar_secundario.py`

5. Analisar integralmente a saida do preflight antes de iniciar o bot.
6. Somente depois da aprovacao do preflight, usar:

   `.\.venv\Scripts\python.exe iniciar_sistema.py --retomar-manutencao`

   `.\.venv\Scripts\python.exe status_bot.py`

7. Instalar o inicio automatico somente depois do primeiro funcionamento validado:

   `.\.venv\Scripts\python.exe autostart_windows.py --instalar`

## Regras operacionais importantes

- Se o PackBall mostrar bloqueio ou excesso de solicitacoes, nao insistir no login nem repetir navegacoes.
- Se a sessao do PackBall tiver expirado, executar `python packball_login.py` uma unica vez para login manual e salvar a sessao.
- Nao enviar ou calibrar sinais quando uma fonte obrigatoria estiver indisponivel ou quando os dados estiverem incompletos.
- PackBall e API-Football devem ser combinados: PackBall como cobertura e leitura ao vivo; API-Football como validacao e enriquecimento quando houver correspondencia.
- Preservar o historico existente. Nao zerar tabelas, estatisticas, calibracoes ou resultados.
- Alteracoes de regras devem ser avaliadas prospectivamente e com protecao contra sobreajuste.
- Nao transformar nota tecnica em probabilidade e nao prometer taxa de acerto ou lucro.

## Estado conhecido dos mercados na ultima revisao

- A infraestrutura e a operacao estavam saudaveis antes da parada para transferencia.
- Nenhum mercado estava liberado como oficialmente calibrado.
- Gol FT possuia amostra ampla, mas a regra geral havia sido reprovada na validacao por ROI negativo. Cortes retrospectivos nao podem ser promovidos sem validacao prospectiva.
- Gol HT, proximo gol, proximo escanteio e escanteios FT asiaticos ainda precisavam ampliar suas amostras.
- O maior gargalo tecnico observado era a falta de historico recente de cinco minutos em parte das partidas, relacionada ao tempo necessario para navegar com seguranca por estatisticas e odds no PackBall.

## Arquivos principais para leitura inicial

- `TRANSFERENCIA_OUTRO_COMPUTADOR.md`
- `instalar_secundario.py`
- `transferir_projeto.py`
- `preflight_reinicio.py`
- `iniciar_sistema.py`
- `status_bot.py`
- `monitor_ao_vivo.py`
- `prontidao_profissional.py`
- `analisar_erros_gol_ft.py`

## Orientacao para o novo chat do Codex

Antes de alterar qualquer codigo, leia este arquivo e `TRANSFERENCIA_OUTRO_COMPUTADOR.md`, confirme a integridade do pacote e inspecione o estado real do banco e dos processos. Continue a meta acima sem reiniciar o projeto, sem apagar o historico e sem iniciar o sistema no segundo computador ate o preflight ser aprovado.
