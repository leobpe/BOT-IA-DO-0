import socket


class VerificadorConectividade:
    def __init__(self, host="packball.com", porta=443, timeout=5, conector=None):
        self.host = host
        self.porta = porta
        self.timeout = timeout
        self.conector = conector or socket.create_connection

    def disponivel(self):
        try:
            conexao = self.conector(
                (self.host, self.porta), timeout=self.timeout
            )
            if hasattr(conexao, "close"):
                conexao.close()
            return True
        except OSError:
            return False
