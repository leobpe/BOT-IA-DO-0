# PackBall Monitor

Monitor de partidas de futebol ao vivo que coleta dados do PackBall, cruza
evidências complementares, aplica regras conservadoras de elegibilidade e
envia alertas informativos ao Telegram. O sistema registra cada decisão,
cotação e resultado para permitir auditoria, calibração e acompanhamento
posterior.

> **Uso responsável:** este projeto não realiza apostas automaticamente, não
> garante lucro e não transforma uma nota técnica em probabilidade individual.
> Qualquer decisão financeira é exclusiva do usuário. Use somente se for maior
> de idade e de acordo com as regras aplicáveis na sua região.

## O que o sistema faz

- Monitora partidas ao vivo e pré-live com dados do PackBall.
- Trabalha com mercados de gols, próximo gol e escanteios.
- Confirma contextos com fontes auxiliares quando disponíveis, sem substituir a
  fonte principal de forma silenciosa.
- Aplica filtros de tempo, placar, estatísticas recentes, odds, qualidade de
  dados e limites de risco antes de qualquer alerta.
- Envia alertas e mensagens administrativas ao Telegram.
- Registra sinais, cotações, resultados, greens, reds, pendências e coortes no
  banco SQLite.
- Mantém backup, pré-voo, watchdog, auditorias e trilha de eventos para uma
  operação recuperável.

## Mercados cobertos

Os módulos existentes contemplam, conforme a configuração e a calibração
disponíveis:

| Grupo | Mercados |
| --- | --- |
| Gols | Gol no 1º tempo, over de gols FT e próximo gol |
| Escanteios | Próximo escanteio e linhas asiáticas FT |
| Escanteios por período | Linhas asiáticas de 1º e 2º tempo, quando habilitadas explicitamente |

Um mercado só deve gerar alerta oficial quando os seus próprios gates de dados,
preço, risco e calibração estiverem aprovados. Ausência de evidência não é
tratada como aprovação.

## Arquitetura resumida

```text
PackBall / fontes auxiliares
            |
            v
     coleta e normalização
            |
            v
 filtros + motor de sinais + limites de risco
            |
            +--> SQLite: decisões, snapshots, resultados e auditorias
            |
            +--> Telegram: alertas operacionais e administrativos
            |
            v
 backup, watchdog, pré-voo e relatórios
```

## Requisitos

- Windows 10/11 recomendado.
- Python 3.11 ou superior.
- Conta com acesso válido ao PackBall.
- Um bot e um chat/canal do Telegram para receber alertas.
- Chave da API-Football se quiser usar os recursos que dependem dela.
- Internet e Microsoft Edge, usado pelo Playwright.

## Instalação

No PowerShell, entre na pasta do projeto e crie o ambiente isolado:

```powershell
cd "C:\Users\Leonardo\Documents\BOT IA DO 0"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m playwright install msedge
```

O arquivo `requirements.lock.txt` fixa as versões validadas do ambiente. Evite
trocar dependências ou usar outra versão do Python sem executar os testes e o
pré-voo novamente.

## Configuração

Crie um arquivo chamado `.env` na raiz do projeto. Nunca publique esse arquivo.

```dotenv
# Acesso PackBall
PACKBALL_EMAIL=seu_email
PACKBALL_PASSWORD=sua_senha

# Telegram
TELEGRAM_BOT_TOKEN=token_do_seu_bot
TELEGRAM_ADMIN_ID=seu_id_no_telegram
TELEGRAM_CHAT_ID_GOLS=id_do_chat_ou_canal_de_gols
TELEGRAM_CHAT_ID_ESCANTEIOS=id_do_chat_ou_canal_de_escanteios

# API-Football (opcional para os módulos que a utilizam)
API_FOOTBALL_KEY=sua_chave
API_LIMITE_DIARIO=7500
API_RESERVA_DIARIA=500
API_LIMITE_DETALHES_DIARIO=2000

# Proteções operacionais
LIMITE_DIARIO_SINAIS=10
ODD_MINIMA_SINAL=1.40
ODD_MAXIMA_SINAL=2.50
LIMITE_EXPOSICAO_DIARIA=5
LIMITE_REDS_CONSECUTIVOS_OFICIAIS=3
LIMITE_PERDA_DIARIA_OFICIAL=3
WATCHDOG_REINICIO_AUTOMATICO=1
HORA_RESUMO_DIARIO=18

# 1 habilita linhas asiáticas de escanteios por período; 0 as mantém suspensas.
ESCANTEIOS_ASIATICOS_PERIODOS_ATIVOS=0
```

Os valores apresentados são referências operacionais do projeto, não uma
recomendação de aposta. Ajuste limites somente após analisar histórico,
amostra, risco e capacidade de acompanhamento.

## Primeiro acesso ao PackBall

Se a sessão ainda não existir ou expirar, faça o login manual:

```powershell
.\.venv\Scripts\python.exe .\packball_login.py --manual --autorizar-nova-tentativa
```

Conclua o login na janela aberta. A sessão local não deve ser enviada ao GitHub.

## Como iniciar e parar manualmente

O sistema está configurado para ser iniciado manualmente. Para iniciar monitor
e watchdog depois de uma pausa planejada:

```powershell
cd "C:\Users\Leonardo\Documents\BOT IA DO 0"
.\.venv\Scripts\python.exe .\iniciar_sistema.py --retomar-manutencao
```

Para parar com segurança:

```powershell
.\.venv\Scripts\python.exe .\parar_sistema.py
```

Não finalize processos à força quando puder usar `parar_sistema.py`: a parada
planejada é persistida e evita uma retomada indevida pelo watchdog.

Para uma coleta única de diagnóstico, sem abrir navegador visível:

```powershell
.\.venv\Scripts\python.exe .\monitor_ao_vivo.py --uma-vez --headless
```

## Consultar o estado

```powershell
.\.venv\Scripts\python.exe .\status_bot.py
```

O painel de status apresenta, entre outros pontos, o estado de processos,
coleta, backup, calibração, integrações, resultados e pendências. Para uma
checagem mais ampla antes de uma retomada controlada:

```powershell
.\.venv\Scripts\python.exe .\preflight_reinicio.py
```

## Inicialização automática opcional

A inicialização automática é opcional e permanece desligada até ser instalada
explicitamente. Consulte o estado:

```powershell
.\.venv\Scripts\python.exe .\autostart_windows.py --status
```

Para instalar ou remover a tarefa do Windows:

```powershell
.\.venv\Scripts\python.exe .\autostart_windows.py --instalar
.\.venv\Scripts\python.exe .\autostart_windows.py --remover
```

Use essa função somente se realmente quiser que o Windows recupere o monitor
automaticamente. A remoção não apaga o projeto nem o banco de dados.

## Segurança e dados sensíveis

Antes de publicar qualquer alteração, confirme que estes itens **não** serão
enviados ao repositório:

- `.env`, senhas, tokens e chaves de API;
- `packball_session.json`, cookies e dados de sessão;
- arquivos SQLite (`*.db`, `*.db-wal`, `*.db-shm`);
- logs, estados de execução, locks e backups.

O `.gitignore` do projeto já protege os principais arquivos. Mesmo assim,
revise sempre o conteúdo com `git status` antes de fazer commit.

## Testes e qualidade

Antes de alterar regras operacionais ou iniciar uma nova versão, execute:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -q
.\.venv\Scripts\python.exe .\preflight_reinicio.py
```

Os testes são offline e cobrem componentes como coleta, regras, armazenamento,
calibração, envio e liquidação simulada. O pré-voo é uma verificação de
segurança: uma recusa precisa ser investigada antes de retomar a operação.

## Estrutura principal

| Arquivo ou área | Responsabilidade |
| --- | --- |
| `iniciar_sistema.py` | Pré-voo e retomada manual controlada |
| `parar_sistema.py` | Parada planejada e persistente |
| `monitor_ao_vivo.py` / `servico_monitor.py` | Entrada e serviço de monitoramento ao vivo |
| `motor_sinais.py` | Avaliação e direcionamento de candidatos |
| `mercados.py` | Catálogo de mercados e habilitações operacionais |
| `banco.py` | Persistência SQLite e auditorias de integridade |
| `bot.py` | Comandos do bot Telegram |
| `status_bot.py` | Painel de estado e observabilidade |
| `watchdog.py` / `processo_monitor.py` | Supervisão de processos |
| `autostart_windows.py` | Tarefa opcional de inicialização no Windows |
| `OPERACAO.md` | Manual técnico detalhado e histórico operacional |
| `test_*.py` | Suíte de testes automatizados |

## Telegram

Depois de configurar o token e iniciar o bot de comandos, os comandos mais
úteis são:

- `/start` — apresenta o bot;
- `/sinais` — consulta informativa de sinais;
- `/oddsmanual` — lista solicitações de conferência manual de odds para o
  administrador;
- `/meuid` — mostra seu ID de usuário;
- `/chatid` — mostra o ID do chat atual;
- `/ajuda` — mostra os comandos disponíveis.

## Publicar no GitHub

O aviso mostrado no VS Code — `Make sure you configure your "user.name" and
"user.email" in git` — significa apenas que o Git ainda não sabe qual nome e
e-mail registrar nos commits. Execute uma vez no PowerShell, substituindo pelos
seus dados (de preferência o e-mail vinculado ao GitHub):

```powershell
git config --global user.name "Seu Nome"
git config --global user.email "seu-email@exemplo.com"
```

Confira:

```powershell
git config --global --get user.name
git config --global --get user.email
```

Em seguida, dentro desta pasta:

```powershell
git status
git add .
git commit -m "Documenta o projeto PackBall"
```

No VS Code, depois disso, o botão **Commit** deve funcionar. Para enviar ao
GitHub, publique o repositório pelo painel de Controle de Código-Fonte ou
configure um remoto do seu repositório privado. Nunca coloque token, senha ou
o conteúdo do `.env` no README, no commit ou em uma mensagem.

## Documentação adicional

O documento [OPERACAO.md](OPERACAO.md) contém detalhes técnicos sobre critérios
de segurança, coortes, auditorias, recuperação, fontes de odds e histórico das
evoluções do sistema.

---

Projeto de uso privado. Antes de tornar o repositório público, revise a
documentação, os dados versionados e defina uma licença adequada.

