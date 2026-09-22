# Transferência do computador principal para o secundário

O pacote contém o banco histórico, regras, configurações, token do Telegram,
chave da API-Football e sessão autenticada do PackBall. Ele é confidencial.

O computador secundário passará a ser a única máquina que executa o bot. O
principal continuará com uma cópia para manutenção, mas o monitor não deve ser
iniciado nele enquanto o secundário estiver operando.

## 1. No computador antigo

Solicite a parada segura:

```powershell
python parar_sistema.py
```

Espere o ciclo atual terminar e confirme:

```powershell
python transferir_projeto.py --auditar
```

Quando monitor e watchdog aparecerem como `parado`, crie o pacote em uma pasta
vazia de um pendrive ou disco externo:

```powershell
python transferir_projeto.py "E:\PackBall_transferencia"
```

Por padrão, a pasta grande de backups não é duplicada. O banco principal já
leva todo o histórico e é copiado por uma operação SQLite consistente. Para
levar também todos os pontos antigos de recuperação:

```powershell
python transferir_projeto.py "E:\PackBall_transferencia" --incluir-backups
```

O arquivo `manifesto_transferencia.json` registra os tamanhos e checksums de
todos os arquivos copiados.

## 2. No computador novo

Instale Python 3.11 ou superior e Microsoft Edge. Copie a pasta do pacote para
`Documentos`, abra o PowerShell nessa pasta e primeiro confirme que a cópia
chegou completa:

```powershell
py transferir_projeto.py --verificar-pacote .
```

O resultado precisa mostrar `Pacote recebido: ÍNTEGRO` e `Banco SQLite:
íntegro`. Se aparecer `REPROVADO`, não inicie o bot e refaça a cópia.

O instalador pode conferir o computador e realizar toda a preparação sem
iniciar o bot:

```powershell
py instalar_secundario.py --somente-verificar
py instalar_secundario.py
```

Como alternativa, os mesmos passos podem ser executados manualmente:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
python -m playwright install chromium
python preflight_reinicio.py
python iniciar_sistema.py --retomar-manutencao
python status_bot.py
```

Depois de confirmar que monitor, watchdog, PackBall e Telegram estão saudáveis,
instale a inicialização automática no computador secundário:

```powershell
python autostart_windows.py --instalar
python autostart_windows.py --status
```

Se a sessão do PackBall não for aceita no computador novo, execute uma única
vez `python packball_login.py` e faça o login manual. Não deixe as duas máquinas
rodando juntas: duas instâncias do Telegram entram em conflito e acessos
simultâneos ao PackBall podem provocar bloqueio.

O início automático do Windows é específico de cada computador e deve ser
configurado novamente depois que o funcionamento manual estiver confirmado.

## 3. Regra de operação depois da troca

- Secundário: bot ativo continuamente e inicialização automática instalada.
- Principal: usado para acompanhar ou editar, sem executar monitor/watchdog.
- Para devolver a operação ao principal, faça novamente a mesma transferência
  no sentido contrário; nunca copie o banco enquanto uma máquina está ativa.
- Antes de formatar ou alterar o secundário, mantenha o pacote e ao menos um
  backup validado em outro dispositivo.
