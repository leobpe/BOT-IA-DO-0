# Servidores MCP do projeto

O arquivo `.mcp.json` na raiz declara os servidores MCP que o Claude Code carrega
ao abrir este repositorio. Nao e preciso rodar `/mcp` para adicionar o que ja
esta declarado aqui — na primeira vez o Claude Code pede aprovacao do servidor
vindo do repositorio, e basta aceitar. Use `/mcp` para conferir o estado da
conexao ou para adicionar servidores so seus, fora do projeto.

## playwright

Servidor oficial `@playwright/mcp`, fixado na versao `0.0.82`.

Da ao agente controle de um navegador real: navegar, ler a pagina como snapshot
de acessibilidade, clicar, preencher formularios, inspecionar requisicoes de
rede, executar JS na pagina e tirar screenshots. Sao 25 ferramentas
`browser_*`.

Por que neste projeto: a coleta de odds (`packball_jogos.py`,
`mapear_odds_ao_vivo.py`, `diagnostico_lista_packball.py`) depende de seletores
que quebram quando o site muda de layout. Com este servidor o agente inspeciona
a pagina ao vivo e corrige o seletor a partir do DOM real, em vez de deduzir
pelo codigo antigo.

### Escolhas da configuracao

    "args": ["-y", "@playwright/mcp@0.0.82",
             "--browser", "chrome", "--viewport-size", "1440,900"]

- `--browser chrome` usa o **Google Chrome ja instalado na maquina**, nao o
  Chromium empacotado pelo Playwright. Isso e proposital: os scripts do projeto
  abrem `channel="chrome"` (`packball_login.py`, `packball_jogos.py`,
  `verificar_packball_controlado.py`), entao o agente enxerga a pagina com o
  mesmo binario e o mesmo fingerprint que a coleta em producao — o que importa
  em sites que fazem deteccao de bot. Efeito colateral bom: nao baixa nada.
- **Sem `--headless`**, tambem de proposito: `packball_jogos.py` e
  `mapear_odds_ao_vivo.py` rodam com `headless=False`. Rodar headless muda o
  fingerprint e pode gerar um bloqueio que nao acontece na coleta real.
  Acrescente `--headless` se quiser rodar sem janela.
- Versao fixada. `@latest` mudaria o conjunto de ferramentas sem aviso entre
  sessoes.

### Requisitos

- Node.js (testado na v22). O `npx` baixa o pacote na primeira execucao.
- Google Chrome instalado. Para usar Edge, troque para `--browser msedge`
  (`diagnostico_lista_packball.py` e `mapear_odds_ao_vivo.py` usam
  `channel="msedge"`). Para o Chromium do Playwright, use
  `--browser chromium` e rode antes `npx playwright install chromium`.

### Perfil e sessao

O servidor mantem um perfil persistente **proprio**, fora do repositorio: ele
usa apenas o binario do Chrome, nao o seu perfil pessoal, entao suas abas e
logins do dia a dia nao sao tocados. Logins feitos pelo agente sobrevivem entre
execucoes nesse perfil separado, que tambem e independente do
`packball_session.json` usado pelos scripts Python — os dois nao compartilham
estado. Para comecar limpo a cada execucao, acrescente `--isolated`.

### Cuidados

- O perfil persistente guarda cookies de sessao dos sites em que o agente logar.
  Fica fora do repositorio, mas nao e um diretorio criptografado.
- `browser_evaluate` e `browser_run_code_unsafe` executam JavaScript arbitrario
  na pagina aberta. Pense antes de aprovar em site onde voce esta autenticado.
- Credenciais continuam no `.env` (ja ignorado pelo git). Nao passe login e
  senha no texto do pedido ao agente.

### Sessoes remotas (Claude Code na web)

Este servidor foi pensado para rodar na **sua maquina**. Em sessoes remotas o
container nao tem Chrome instalado, e a politica de rede do ambiente nega
`CONNECT` para hosts externos — ou seja, navegacao real nao funciona la, seja
qual for a configuracao. O servidor ate sobe e lista as ferramentas, mas
qualquer `browser_navigate` para fora falha com `ERR_TUNNEL_CONNECTION_FAILED`.

Use o Playwright MCP localmente. Nas sessoes web, siga com leitura de codigo,
analises e testes que nao dependam de rede externa.
