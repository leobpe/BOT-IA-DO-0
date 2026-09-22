import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from banco import auditar_compatibilidade
from mercados import MERCADOS_CALIBRADOS
from pontuacao_contexto_sombra import (
    carregar_modelo as carregar_modelo_pontuacao_contexto_sombra,
)
from pontuacao_longa_sombra import (
    carregar_ancora_pontuacao_longa,
    carregar_modelo_pontuacao_longa,
)
from pontuacao_sombra import carregar_modelo_pontuacao_sombra
from versoes_regras import versao_regra_para_mercado


def identificar_dispositivo_armazenamento(caminho):
    """Identifica o dispositivo fisico, nao apenas a letra da unidade.

    No Windows, C:, D: e E: podem ser particoes do mesmo SSD. O numero do
    dispositivo retornado pelo sistema evita classificar essa separacao
    logica como um backup externo. Em outros sistemas, ``st_dev`` identifica
    o dispositivo montado. Falhas retornam estado desconhecido e nunca sao
    promovidas silenciosamente a copia fora do dispositivo.
    """
    caminho = Path(caminho).expanduser().resolve()
    raiz = caminho.anchor
    if os.name != "nt":
        try:
            return {
                "saudavel": True,
                "metodo": "stat_st_dev",
                "identificador": f"st_dev:{os.stat(raiz or caminho).st_dev}",
                "raiz": raiz,
                "motivo": None,
            }
        except OSError as erro:
            return {
                "saudavel": False,
                "metodo": "stat_st_dev",
                "identificador": None,
                "raiz": raiz,
                "motivo": type(erro).__name__,
            }

    if raiz.startswith("\\\\"):
        # Uma raiz UNC e externa ao disco local, mas duas pastas no mesmo
        # compartilhamento devem conservar o mesmo identificador.
        partes = [parte for parte in raiz.strip("\\").split("\\") if parte]
        identificador = (
            "unc:" + "\\".join(partes[:2]).casefold()
            if len(partes) >= 2 else None
        )
        return {
            "saudavel": bool(identificador),
            "metodo": "windows_unc_share",
            "identificador": identificador,
            "raiz": raiz,
            "motivo": None if identificador else "raiz_unc_invalida",
        }

    try:
        import ctypes
        from ctypes import wintypes

        class StorageDeviceNumber(ctypes.Structure):
            _fields_ = [
                ("device_type", wintypes.DWORD),
                ("device_number", wintypes.DWORD),
                ("partition_number", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]
        kernel32.DeviceIoControl.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        volume = raiz.rstrip("\\/")
        if len(volume) != 2 or volume[1] != ":":
            raise ValueError("raiz_windows_nao_suportada")
        identificador_volume = f"\\\\.\\{volume}"
        compartilhamento = 0x00000001 | 0x00000002 | 0x00000004
        abrir_existente = 3
        handle = kernel32.CreateFileW(
            identificador_volume,
            0,
            compartilhamento,
            None,
            abrir_existente,
            0,
            None,
        )
        handle_invalido = ctypes.c_void_p(-1).value
        if handle == handle_invalido:
            raise OSError(ctypes.get_last_error(), "CreateFileW")
        try:
            numero = StorageDeviceNumber()
            retornados = wintypes.DWORD()
            ioctl_storage_get_device_number = 0x002D1080
            sucesso = kernel32.DeviceIoControl(
                handle,
                ioctl_storage_get_device_number,
                None,
                0,
                ctypes.byref(numero),
                ctypes.sizeof(numero),
                ctypes.byref(retornados),
                None,
            )
            if not sucesso:
                raise OSError(ctypes.get_last_error(), "DeviceIoControl")
        finally:
            kernel32.CloseHandle(handle)
        return {
            "saudavel": True,
            "metodo": "windows_storage_device_number",
            "identificador": (
                f"device:{numero.device_type}:{numero.device_number}"
            ),
            "raiz": raiz,
            "particao": int(numero.partition_number),
            "motivo": None,
        }
    except (AttributeError, OSError, TypeError, ValueError) as erro:
        return {
            "saudavel": False,
            "metodo": "windows_storage_device_number",
            "identificador": None,
            "raiz": raiz,
            "motivo": type(erro).__name__,
        }


def comparar_dispositivos_armazenamento(origem, destino):
    origem_info = identificar_dispositivo_armazenamento(origem)
    destino_info = identificar_dispositivo_armazenamento(destino)
    comparavel = bool(
        origem_info.get("saudavel")
        and destino_info.get("saudavel")
        and origem_info.get("identificador")
        and destino_info.get("identificador")
    )
    fora_dispositivo = (
        origem_info["identificador"] != destino_info["identificador"]
        if comparavel else None
    )
    return {
        "comparavel": comparavel,
        "fora_dispositivo": fora_dispositivo,
        "origem": origem_info,
        "destino": destino_info,
    }


class BackupBanco:
    PADROES_COMPACTAVEIS = (
        "monitor_????????.db",
        "periodico_*.db",
        "pre_reinicio_*.db",
        "pre_migracao_*.db",
        "invalido_*.db",
    )
    SUFIXO_INCOMPATIVEL = ".compactacao-incompativel.json"

    def __init__(
        self, pasta, retencao_dias=14, manter_pre_reinicio=5,
        manter_invalidos=3, manter_periodicos=8,
        intervalo_periodico_horas=6, pasta_espelho=None, compactar=None,
    ):
        self.pasta = Path(pasta)
        self.retencao_dias = retencao_dias
        self.manter_pre_reinicio = int(manter_pre_reinicio)
        self.manter_invalidos = int(manter_invalidos)
        self.manter_periodicos = int(manter_periodicos)
        self.intervalo_periodico_horas = int(intervalo_periodico_horas)
        self.pasta_espelho = (
            Path(pasta_espelho).expanduser()
            if pasta_espelho else None
        )
        # A classe permanece legada por padrão para que bibliotecas, testes e
        # ferramentas offline não mudem de formato por efeito colateral do
        # ambiente. Os entrypoints de produção passam a opção explicitamente.
        self.compactar = bool(compactar) if compactar is not None else False
        self.ultima_compactacao = None
        self.arquivo_estado_espelho = (
            self.pasta / "backup_espelho_estado.json"
        )
        if self.intervalo_periodico_horas <= 0:
            raise ValueError("Intervalo do backup periódico deve ser positivo.")

    @staticmethod
    def _existente_para_destino(destino):
        destino = Path(destino)
        if destino.is_file():
            return destino
        compactado = Path(f"{destino}.gz")
        return compactado if compactado.is_file() else destino

    def _finalizar_formato(self, destino):
        destino = Path(destino)
        if not self.compactar:
            return destino
        from backup_compactado import compactar_backup_verificado

        resultado = compactar_backup_verificado(
            destino, remover_original=True
        )
        self.ultima_compactacao = dict(resultado or {})
        if not resultado.get("saudavel"):
            # Compressão economiza espaço, mas não é o ponto de recuperação.
            # Se o SQLite original continua íntegro, preservá-lo é mais seguro
            # do que derrubar toda a coleta por uma falha transitória de I/O.
            # A tentativa e o fallback ficam disponíveis ao serviço para
            # observabilidade; uma falha que também comprometa o original
            # continua fatal e fechada.
            original = verificar_arquivo_backup(
                destino, criar_manifesto=True
            )
            if original.get("valido"):
                self.ultima_compactacao.update({
                    "saudavel": False,
                    "fallback_original": True,
                    "original_preservado": str(destino),
                    "original_valido": True,
                    "motivo_compactacao": resultado.get("motivo"),
                })
                return destino
            raise RuntimeError(
                "Compactacao do backup falhou depois da verificacao: "
                f"{resultado.get('estado')}:{resultado.get('motivo')}"
            )
        self.ultima_compactacao["fallback_original"] = False
        return Path(resultado["caminho"])

    @staticmethod
    def _glob_formatos(pasta, padrao_db):
        pasta = Path(pasta)
        itens = list(pasta.glob(padrao_db))
        itens.extend(pasta.glob(f"{padrao_db}.gz"))
        return list(dict.fromkeys(itens))

    @staticmethod
    def _stem_logico(arquivo):
        arquivo = Path(arquivo)
        nome = arquivo.name[:-3] if arquivo.name.endswith(".gz") else arquivo.name
        return Path(nome).stem

    def criar_diario(self, conexao_origem, agora=None):
        self.ultima_compactacao = None
        agora = agora or datetime.now()
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / f"monitor_{agora:%Y%m%d}.db"
        existente = self._existente_para_destino(destino)
        if existente.exists():
            verificacao = verificar_arquivo_backup(
                existente, criar_manifesto=True
            )
            if not verificacao["valido"]:
                if existente.suffix == ".gz":
                    if not self._compactado_obsoleto_mas_integro(
                        verificacao
                    ):
                        raise RuntimeError(
                            "Backup compactado diario existente e invalido: "
                            f"{verificacao.get('motivo')}"
                        )
                    self._substituir_compactado_obsoleto(
                        conexao_origem, existente, agora
                    )
                else:
                    self._substituir_invalido(
                        conexao_origem, existente, agora
                    )
                self._remover_invalidos_excedentes()
                final = self._existente_para_destino(destino)
                if final == destino:
                    final = self._finalizar_formato(destino)
                self._replicar_espelho(final, agora)
                return final, True
            # A verificacao diaria tambem funciona como reconciliacao da
            # retencao. Se uma limpeza anterior foi interrompida depois que o
            # backup valido nasceu, nao espere o dia seguinte para tentar de
            # novo. Pontos protegidos continuam excluidos pela propria regra.
            self._remover_antigos(agora)
            self._remover_invalidos_excedentes()
            self._replicar_espelho(existente, agora)
            return existente, False

        self._criar_verificado(conexao_origem, destino, agora)
        destino = self._finalizar_formato(destino)
        self._remover_antigos(agora)
        self._replicar_espelho(destino, agora)
        return destino, True

    def criar_pre_reinicio(self, conexao_origem, agora=None):
        self.ultima_compactacao = None
        agora = agora or datetime.now()
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / f"pre_reinicio_{agora:%Y%m%d_%H%M%S}.db"
        if destino.exists():
            raise FileExistsError(f"Backup de pré-reinício já existe: {destino}")
        self._criar_verificado(conexao_origem, destino, agora)
        destino = self._finalizar_formato(destino)
        self._remover_pre_reinicio_excedentes()
        self._replicar_espelho(destino, agora)
        return destino

    def criar_pre_migracao(self, conexao_origem, agora=None):
        """Preserva o banco antigo antes de uma migracao aditiva de esquema.

        Esse ponto de recuperacao nao exige o esquema do codigo novo, pois ele
        existe justamente para guardar a versao anterior. Ainda assim, SQLite,
        chaves estrangeiras, manifesto e checksum precisam estar integros.
        """
        self.ultima_compactacao = None
        agora = agora or datetime.now()
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / f"pre_migracao_{agora:%Y%m%d_%H%M%S}.db"
        if destino.exists():
            raise FileExistsError(
                f"Backup de pre-migracao ja existe: {destino}"
            )
        conexao_destino = sqlite3.connect(destino)
        try:
            conexao_origem.backup(conexao_destino)
        finally:
            conexao_destino.close()
        verificacao = verificar_backup_pre_migracao(
            destino, criar_manifesto=True, agora=agora
        )
        if not verificacao["valido"]:
            destino.unlink(missing_ok=True)
            caminho_manifesto(destino).unlink(missing_ok=True)
            raise RuntimeError(
                "Backup de pre-migracao nao passou na integridade: "
                f"{verificacao['motivo']}"
            )
        self._remover_pre_migracao_excedentes()
        self._replicar_espelho(destino, agora, pre_migracao=True)
        return destino

    def criar_periodico(self, conexao_origem, agora=None):
        self.ultima_compactacao = None
        agora = agora or datetime.now()
        self.pasta.mkdir(parents=True, exist_ok=True)
        inicio_hora = (
            agora.hour // self.intervalo_periodico_horas
        ) * self.intervalo_periodico_horas
        inicio_janela = agora.replace(
            hour=inicio_hora, minute=0, second=0, microsecond=0
        )
        destino = self.pasta / (
            f"periodico_{inicio_janela:%Y%m%d_%H}.db"
        )
        existente = self._existente_para_destino(destino)
        if existente.exists():
            verificacao = verificar_arquivo_backup(
                existente, criar_manifesto=True
            )
            if not verificacao["valido"]:
                if existente.suffix == ".gz":
                    if not self._compactado_obsoleto_mas_integro(
                        verificacao
                    ):
                        raise RuntimeError(
                            "Backup compactado periodico existente e "
                            "invalido: "
                            f"{verificacao.get('motivo')}"
                        )
                    self._substituir_compactado_obsoleto(
                        conexao_origem, existente, agora
                    )
                else:
                    self._substituir_invalido(
                        conexao_origem, existente, agora
                    )
                self._remover_invalidos_excedentes()
                final = self._existente_para_destino(destino)
                if final == destino:
                    final = self._finalizar_formato(destino)
                self._replicar_espelho(final, agora)
                return final, True
            self._remover_periodicos_excedentes()
            self._remover_invalidos_excedentes()
            self._replicar_espelho(existente, agora)
            return existente, False
        self._criar_verificado(conexao_origem, destino, agora)
        destino = self._finalizar_formato(destino)
        self._remover_periodicos_excedentes()
        self._replicar_espelho(destino, agora)
        return destino, True

    def _gravar_estado_espelho(self, estado):
        self.pasta.mkdir(parents=True, exist_ok=True)
        temporario = self.arquivo_estado_espelho.with_suffix(
            f".json.{uuid4().hex}.tmp"
        )
        try:
            temporario.write_text(
                json.dumps(estado, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporario.replace(self.arquivo_estado_espelho)
        finally:
            temporario.unlink(missing_ok=True)

    def _replicar_espelho(self, origem, agora, pre_migracao=False):
        """Replica um backup verificado sem comprometer o backup local.

        A falha da unidade externa é registrada e isolada: nunca apaga nem
        invalida o ponto de recuperação que já foi criado localmente.
        """
        if self.pasta_espelho is None:
            return {"configurado": False, "estado": "nao_configurado"}
        origem = Path(origem)
        destino = self.pasta_espelho / origem.name
        manifesto_origem = caminho_manifesto(origem)
        identificador = uuid4().hex
        temporario = self.pasta_espelho / (
            f".{origem.name}.{identificador}.tmp"
        )
        manifesto_temporario = caminho_manifesto(temporario)
        agora_iso = agora.replace(microsecond=0).isoformat()
        try:
            if self.pasta_espelho.resolve() == self.pasta.resolve():
                raise ValueError("espelho_igual_ao_backup_local")
            self.pasta_espelho.mkdir(parents=True, exist_ok=True)
            dispositivos = comparar_dispositivos_armazenamento(
                origem, self.pasta_espelho
            )
            manifesto_local = json.loads(
                manifesto_origem.read_text(encoding="utf-8")
            )
            estado_anterior = {}
            try:
                estado_anterior = json.loads(
                    self.arquivo_estado_espelho.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                pass
            if (
                destino.is_file()
                and caminho_manifesto(destino).is_file()
                and estado_anterior.get("saudavel") is True
                and estado_anterior.get("destino") == str(destino.resolve())
                and estado_anterior.get("checksum_sha256")
                    == manifesto_local.get("sha256")
                and destino.stat().st_size == origem.stat().st_size
            ):
                estado = {
                    **estado_anterior,
                    "configurado": True,
                    "saudavel": True,
                    "estado": "replica_existente_confirmada",
                    "confirmado_em": agora_iso,
                    "fora_dispositivo": dispositivos.get(
                        "fora_dispositivo"
                    ),
                    "dispositivos": dispositivos,
                    "erro": None,
                }
                self._gravar_estado_espelho(estado)
                self._aplicar_retencao_espelho(agora)
                return estado
            shutil.copy2(origem, temporario)
            shutil.copy2(manifesto_origem, manifesto_temporario)
            if pre_migracao:
                verificacao = verificar_backup_pre_migracao(temporario)
            elif origem.name.endswith(".db.gz"):
                from backup_compactado import verificar_backup_compactado
                verificacao = verificar_backup_compactado(temporario)
                verificacao["valido"] = bool(
                    verificacao.get("saudavel")
                )
            else:
                verificacao = verificar_backup(temporario)
            if not verificacao["valido"]:
                raise RuntimeError(
                    "replica_nao_passou_integridade:"
                    f"{verificacao.get('motivo')}"
                )
            temporario.replace(destino)
            manifesto_temporario.replace(caminho_manifesto(destino))
            verificacao_final = (
                verificar_backup_pre_migracao(destino)
                if pre_migracao else verificar_arquivo_backup(destino)
            )
            if not verificacao_final["valido"]:
                raise RuntimeError(
                    "replica_final_nao_passou_integridade:"
                    f"{verificacao_final.get('motivo')}"
                )
            estado = {
                "configurado": True,
                "saudavel": True,
                "estado": "replicado_e_verificado",
                "origem": str(origem.resolve()),
                "destino": str(destino.resolve()),
                "replicado_em": agora_iso,
                "checksum_sha256": verificacao_final.get(
                    "checksum_sha256"
                ),
                "fora_dispositivo": dispositivos.get("fora_dispositivo"),
                "dispositivos": dispositivos,
                "erro": None,
            }
            self._gravar_estado_espelho(estado)
            self._aplicar_retencao_espelho(agora)
            return estado
        except Exception as erro:
            estado = {
                "configurado": True,
                "saudavel": False,
                "estado": "falha_replicacao",
                "origem": str(origem.resolve()),
                "destino": str(destino),
                "replicado_em": agora_iso,
                "fora_dispositivo": None,
                "erro": type(erro).__name__,
                "detalhe": str(erro)[:240],
            }
            try:
                self._gravar_estado_espelho(estado)
            except OSError:
                pass
            return estado
        finally:
            temporario.unlink(missing_ok=True)
            manifesto_temporario.unlink(missing_ok=True)

    def _aplicar_retencao_espelho(self, agora):
        if self.pasta_espelho is None:
            return []
        gerenciador = BackupBanco(
            self.pasta_espelho,
            retencao_dias=self.retencao_dias,
            manter_pre_reinicio=self.manter_pre_reinicio,
            manter_invalidos=self.manter_invalidos,
            manter_periodicos=self.manter_periodicos,
            intervalo_periodico_horas=self.intervalo_periodico_horas,
        )
        removidos = []
        removidos.extend(gerenciador._remover_antigos(agora))
        removidos.extend(gerenciador._remover_pre_reinicio_excedentes())
        removidos.extend(gerenciador._remover_pre_migracao_excedentes())
        removidos.extend(gerenciador._remover_periodicos_excedentes())
        removidos.extend(gerenciador._remover_invalidos_excedentes())
        return removidos

    @staticmethod
    def _criar_verificado(conexao_origem, destino, agora):
        conexao_destino = sqlite3.connect(destino)
        try:
            conexao_origem.backup(conexao_destino)
        finally:
            conexao_destino.close()
        verificacao = verificar_backup(
            destino, criar_manifesto=True, agora=agora
        )
        if not verificacao["valido"]:
            destino.unlink(missing_ok=True)
            caminho_manifesto(destino).unlink(missing_ok=True)
            raise RuntimeError(
                f"Backup recém-criado não passou na integridade: "
                f"{verificacao['motivo']}"
            )

    def _substituir_invalido(self, conexao_origem, destino, agora):
        sufixo = agora.strftime("%Y%m%d_%H%M%S")
        arquivado = self.pasta / f"invalido_{destino.stem}_{sufixo}.db"
        if arquivado.exists():
            arquivado = self.pasta / (
                f"invalido_{destino.stem}_{sufixo}_{agora.microsecond:06d}.db"
            )
        candidato = self.pasta / f".novo_{destino.stem}_{sufixo}.db"
        manifesto_candidato = caminho_manifesto(candidato)
        candidato.unlink(missing_ok=True)
        manifesto_candidato.unlink(missing_ok=True)
        try:
            self._criar_verificado(conexao_origem, candidato, agora)
            manifesto_atual = caminho_manifesto(destino)
            destino.replace(arquivado)
            if manifesto_atual.exists():
                manifesto_atual.replace(caminho_manifesto(arquivado))
            candidato.replace(destino)
            manifesto_candidato.replace(caminho_manifesto(destino))
        finally:
            candidato.unlink(missing_ok=True)
            manifesto_candidato.unlink(missing_ok=True)
        verificacao = verificar_backup(destino)
        if not verificacao["valido"]:
            raise RuntimeError(
                "Backup diário regenerado não passou na verificação final: "
                f"{verificacao['motivo']}"
            )
        return arquivado

    @staticmethod
    def _compactado_obsoleto_mas_integro(verificacao):
        """Distingue migração aditiva de corrupção do contêiner gzip.

        Um backup criado antes de uma tabela nova continua sendo um ponto de
        recuperação SQLite íntegro, embora não possa mais ocupar o nome do
        backup diário do esquema atual. Checksum, quick-check e chaves
        estrangeiras precisam estar comprovados; qualquer outro motivo
        continua falhando fechado.
        """
        return bool(
            verificacao.get("motivo")
            == "esquema_ou_relacoes_incompativeis"
            and verificacao.get("integridade_sqlite") is True
            and verificacao.get("checksum_confere") is True
            and not verificacao.get("violacoes_chaves_estrangeiras")
        )

    def _substituir_compactado_obsoleto(
        self, conexao_origem, existente, agora
    ):
        """Rotaciona backup gzip de esquema anterior sem apagar o original."""
        existente = Path(existente)
        sufixo = agora.strftime("%Y%m%d_%H%M%S")
        stem_logico = self._stem_logico(existente)
        arquivado = self.pasta / (
            f"invalido_{stem_logico}_{sufixo}.db.gz"
        )
        if arquivado.exists():
            arquivado = self.pasta / (
                f"invalido_{stem_logico}_{sufixo}_"
                f"{agora.microsecond:06d}.db.gz"
            )
        identificador = uuid4().hex
        candidato_db = self.pasta / (
            f".novo_{stem_logico}_{sufixo}_{identificador}.db"
        )
        candidato_gz = Path(f"{candidato_db}.gz")
        manifesto_candidato = caminho_manifesto(candidato_gz)
        manifesto_existente = caminho_manifesto(existente)
        manifesto_arquivado = caminho_manifesto(arquivado)
        try:
            self._criar_verificado(conexao_origem, candidato_db, agora)
            candidato_gz = self._finalizar_formato(candidato_db)
            verificacao_nova = verificar_arquivo_backup(candidato_gz)
            if not verificacao_nova["valido"]:
                raise RuntimeError(
                    "Backup compactado regenerado nao passou na verificacao: "
                    f"{verificacao_nova.get('motivo')}"
                )

            existente.replace(arquivado)
            if manifesto_existente.exists():
                manifesto_existente.replace(manifesto_arquivado)
            try:
                candidato_gz.replace(existente)
                manifesto_candidato.replace(manifesto_existente)
            except Exception:
                existente.unlink(missing_ok=True)
                manifesto_existente.unlink(missing_ok=True)
                arquivado.replace(existente)
                if manifesto_arquivado.exists():
                    manifesto_arquivado.replace(manifesto_existente)
                raise
        finally:
            candidato_db.unlink(missing_ok=True)
            caminho_manifesto(candidato_db).unlink(missing_ok=True)
            candidato_gz.unlink(missing_ok=True)
            manifesto_candidato.unlink(missing_ok=True)

        verificacao_final = verificar_arquivo_backup(existente)
        if not verificacao_final["valido"]:
            raise RuntimeError(
                "Backup compactado regenerado nao passou na verificacao "
                f"final: {verificacao_final.get('motivo')}"
            )
        return arquivado

    def _remover_antigos(self, agora):
        removidos = []
        for arquivo in self._glob_formatos(
            self.pasta, "monitor_????????.db"
        ):
            if self._protegido_retencao(arquivo):
                continue
            try:
                data = datetime.strptime(
                    self._stem_logico(arquivo).removeprefix("monitor_"),
                    "%Y%m%d",
                )
            except ValueError:
                continue
            if (agora - data).days > self.retencao_dias:
                arquivo.unlink()
                manifesto = caminho_manifesto(arquivo)
                manifesto.unlink(missing_ok=True)
                removidos.append(arquivo)
        return removidos

    def _remover_pre_reinicio_excedentes(self):
        arquivos = self._ordenar_por_antiguidade(
            item for item in self._glob_formatos(
                self.pasta, "pre_reinicio_*.db"
            )
            if not self._protegido_retencao(item)
        )
        excedentes = max(len(arquivos) - self.manter_pre_reinicio, 0)
        removidos = []
        for arquivo in arquivos[:excedentes]:
            arquivo.unlink()
            caminho_manifesto(arquivo).unlink(missing_ok=True)
            removidos.append(arquivo)
        return removidos

    def _remover_pre_migracao_excedentes(self):
        arquivos = self._ordenar_por_antiguidade(
            item for item in self._glob_formatos(
                self.pasta, "pre_migracao_*.db"
            )
            if not self._protegido_retencao(item)
        )
        excedentes = max(len(arquivos) - self.manter_pre_reinicio, 0)
        removidos = []
        for arquivo in arquivos[:excedentes]:
            arquivo.unlink()
            caminho_manifesto(arquivo).unlink(missing_ok=True)
            removidos.append(arquivo)
        return removidos

    def _remover_periodicos_excedentes(self):
        arquivos = self._ordenar_por_antiguidade(
            item for item in self._glob_formatos(
                self.pasta, "periodico_*.db"
            )
            if not self._protegido_retencao(item)
        )
        excedentes = max(len(arquivos) - self.manter_periodicos, 0)
        removidos = []
        for arquivo in arquivos[:excedentes]:
            arquivo.unlink()
            caminho_manifesto(arquivo).unlink(missing_ok=True)
            removidos.append(arquivo)
        return removidos

    def _remover_invalidos_excedentes(self):
        arquivos = self._ordenar_por_antiguidade(
            item for item in self._glob_formatos(
                self.pasta, "invalido_*.db"
            )
            if not self._protegido_retencao(item)
        )
        excedentes = max(len(arquivos) - self.manter_invalidos, 0)
        removidos = []
        for arquivo in arquivos[:excedentes]:
            arquivo.unlink()
            caminho_manifesto(arquivo).unlink(missing_ok=True)
            removidos.append(arquivo)
        return removidos

    @staticmethod
    def _ordenar_por_antiguidade(arquivos):
        def chave(arquivo):
            manifesto = caminho_manifesto(arquivo)
            try:
                dados = json.loads(manifesto.read_text(encoding="utf-8"))
                criado_em = datetime.fromisoformat(dados["criado_em"])
                instante = criado_em.timestamp()
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                try:
                    instante = arquivo.stat().st_mtime
                except OSError:
                    instante = float("inf")
            return instante, arquivo.name

        return sorted((Path(item) for item in arquivos), key=chave)

    @staticmethod
    def _protegido_retencao(arquivo):
        try:
            manifesto = json.loads(
                caminho_manifesto(arquivo).read_text(encoding="utf-8")
            )
        except (OSError, TypeError, json.JSONDecodeError):
            return False
        if manifesto.get("protegido_retencao") is True:
            return True
        manifesto_sqlite = manifesto.get("manifesto_sqlite")
        return bool(
            isinstance(manifesto_sqlite, dict)
            and manifesto_sqlite.get("protegido_retencao") is True
        )

    def compactar_legado_mais_antigo(self, agora=None):
        """Migra no máximo um backup gerenciado antigo por chamada.

        O original só é removido pelo compactador depois do round-trip completo
        (checksum, descompressão e verificação SQLite). Pontos de migração,
        reinício e cópias inválidas também podem ser compactados, mas continuam
        sujeitos à mesma retenção e preservam a classificação no manifesto.
        Arquivos de nomes desconhecidos ficam fora da manutenção automática.
        """
        if not self.compactar:
            return {
                "saudavel": True,
                "estado": "compactacao_desligada",
                "executado": False,
            }
        candidatos = self.listar_legados_compactaveis()
        if not candidatos:
            return {
                "saudavel": True,
                "estado": "nenhum_backup_legado",
                "executado": False,
            }
        origem = candidatos[0]
        tamanho_original = origem.stat().st_size
        from backup_compactado import compactar_backup_verificado

        resultado = compactar_backup_verificado(
            origem,
            agora=agora,
            remover_original=True,
        )
        if not resultado.get("saudavel"):
            self.registrar_legado_incompativel(origem, resultado, agora)
            return {
                **resultado,
                "executado": True,
                "origem": origem.name,
                "original_preservado": origem.exists(),
            }
        destino = Path(resultado["caminho"])
        tamanho_compactado = destino.stat().st_size
        return {
            **resultado,
            "executado": True,
            "origem": origem.name,
            "destino": destino.name,
            "tamanho_original_mb": round(
                tamanho_original / (1024 * 1024), 1
            ),
            "tamanho_compactado_mb": round(
                tamanho_compactado / (1024 * 1024), 1
            ),
            "espaco_liberado_mb": round(
                max(tamanho_original - tamanho_compactado, 0)
                / (1024 * 1024),
                1,
            ),
            "original_preservado": origem.exists(),
        }

    def caminho_marcador_incompativel(self, arquivo):
        arquivo = Path(arquivo)
        return Path(f"{arquivo}{self.SUFIXO_INCOMPATIVEL}")

    def registrar_legado_incompativel(self, arquivo, resultado, agora=None):
        """Registra incompatibilidade estrutural sem alterar o backup original."""
        arquivo = Path(arquivo)
        motivos_permanentes = {
            "esquema_ou_relacoes_incompativeis",
            "modelos_sombra_incompativeis",
        }
        if (
            resultado.get("estado") != "origem_invalida"
            or resultado.get("motivo") not in motivos_permanentes
            or not arquivo.is_file()
        ):
            return False
        if arquivo.parent.resolve() != self.pasta.resolve():
            raise ValueError("backup_fora_da_pasta_gerenciada")
        estado = arquivo.stat()
        _gravar_json_atomico(
            self.caminho_marcador_incompativel(arquivo),
            {
                "versao": "backup-legado-incompativel-v1",
                "arquivo": arquivo.name,
                "motivo": resultado.get("motivo"),
                "tamanho_bytes": estado.st_size,
                "mtime_ns": estado.st_mtime_ns,
                "registrado_em": (agora or datetime.now()).replace(
                    microsecond=0
                ).isoformat(),
                "original_preservado": True,
            },
        )
        return True

    def _legado_marcado_incompativel(self, arquivo):
        arquivo = Path(arquivo)
        try:
            marcador = json.loads(
                self.caminho_marcador_incompativel(arquivo).read_text(
                    encoding="utf-8"
                )
            )
            estado = arquivo.stat()
        except (OSError, TypeError, json.JSONDecodeError):
            return False
        return bool(
            marcador.get("versao") == "backup-legado-incompativel-v1"
            and marcador.get("arquivo") == arquivo.name
            and marcador.get("tamanho_bytes") == estado.st_size
            and marcador.get("mtime_ns") == estado.st_mtime_ns
            and marcador.get("original_preservado") is True
        )

    def listar_legados_compactaveis(self):
        """Lista somente arquivos SQLite de famílias gerenciadas conhecidas."""
        candidatos = []
        for padrao in self.PADROES_COMPACTAVEIS:
            candidatos.extend(
                item for item in self.pasta.glob(padrao)
                if item.is_file() and not item.name.endswith(".db.gz")
                and not self._legado_marcado_incompativel(item)
            )
        return self._ordenar_por_antiguidade(set(candidatos))

    def auditar_retencao(self, agora=None):
        """Planeja a retencao vigente sem remover nenhum arquivo."""
        agora = agora or datetime.now()
        candidatos = []
        protegidos = []
        for arquivo in self._glob_formatos(self.pasta, "*.db"):
            if self._protegido_retencao(arquivo):
                protegidos.append(arquivo)
        for arquivo in self._glob_formatos(
            self.pasta, "monitor_????????.db"
        ):
            if self._protegido_retencao(arquivo):
                continue
            try:
                data = datetime.strptime(
                    self._stem_logico(arquivo).removeprefix("monitor_"),
                    "%Y%m%d",
                )
            except ValueError:
                continue
            if (agora - data).days > self.retencao_dias:
                candidatos.append(("diario_expirado", arquivo))
        for categoria, padrao, manter in (
            ("pre_reinicio_excedente", "pre_reinicio_*.db", self.manter_pre_reinicio),
            ("pre_migracao_excedente", "pre_migracao_*.db", self.manter_pre_reinicio),
            ("periodico_excedente", "periodico_*.db", self.manter_periodicos),
            ("invalido_excedente", "invalido_*.db", self.manter_invalidos),
        ):
            arquivos = self._ordenar_por_antiguidade(
                item for item in self._glob_formatos(self.pasta, padrao)
                if not self._protegido_retencao(item)
            )
            excedentes = max(len(arquivos) - int(manter), 0)
            candidatos.extend((categoria, item) for item in arquivos[:excedentes])
        itens = []
        for categoria, arquivo in candidatos:
            try:
                tamanho = arquivo.stat().st_size
            except OSError:
                tamanho = 0
            itens.append({
                "categoria": categoria,
                "arquivo": arquivo.name,
                "tamanho_mb": round(tamanho / (1024 * 1024), 1),
            })
        return {
            "saudavel": not itens,
            "candidatos_remocao": itens,
            "quantidade": len(itens),
            "tamanho_mb": round(
                sum(item["tamanho_mb"] for item in itens), 1
            ),
            "protegidos": len(protegidos),
            "protegidos_mb": round(sum(
                item.stat().st_size for item in protegidos
            ) / (1024 * 1024), 1),
            "aplicacao_automatica": True,
        }


def caminho_manifesto(caminho_backup):
    return Path(f"{Path(caminho_backup)}.manifest.json")


def verificar_backup_espelho(
    pasta_backups, pasta_espelho=None, agora=None,
    limite_horas=7, verificar_integridade=True,
):
    """Audita a ultima replica externa sem tornar o boot dependente dela."""
    pasta_backups = Path(pasta_backups)
    agora = (agora or datetime.now()).replace(microsecond=0)
    if not pasta_espelho:
        return {
            "saudavel": True,
            "saudavel_para_reinicio": True,
            "configurado": False,
            "estado": "nao_configurado",
            "motivo": None,
            "fora_dispositivo": False,
            "pronto_profissional": False,
        }
    estado_path = pasta_backups / "backup_espelho_estado.json"
    try:
        estado = json.loads(estado_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        estado = {}
        erro_estado = "estado_espelho_ausente"
    except (OSError, json.JSONDecodeError):
        estado = {}
        erro_estado = "estado_espelho_invalido"
    else:
        erro_estado = None
    destino_texto = estado.get("destino") if estado else None
    destino = Path(destino_texto) if destino_texto else None
    try:
        replicado_em = datetime.fromisoformat(estado.get("replicado_em"))
        referencia_frescor = datetime.fromisoformat(
            estado.get("confirmado_em") or estado.get("replicado_em")
        )
        idade_horas = max(
            (agora - referencia_frescor).total_seconds() / 3600, 0
        )
    except (TypeError, ValueError):
        replicado_em = None
        referencia_frescor = None
        idade_horas = None
    fresco = bool(idade_horas is not None and idade_horas <= limite_horas)
    arquivo_presente = bool(destino and destino.is_file())
    integridade = None
    if verificar_integridade and arquivo_presente:
        try:
            manifesto = json.loads(
                caminho_manifesto(destino).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            manifesto = {}
        integridade = (
            verificar_backup_pre_migracao(destino)
            if manifesto.get("tipo") == "pre_migracao"
            else verificar_arquivo_backup(destino)
        )
    integridade_ok = bool(
        integridade.get("valido") if integridade is not None
        else estado.get("saudavel")
    )
    dispositivos = comparar_dispositivos_armazenamento(
        estado.get("origem") or pasta_backups,
        destino or pasta_espelho,
    )
    fora_dispositivo = dispositivos.get("fora_dispositivo")
    if erro_estado:
        motivo = erro_estado
    elif not estado.get("saudavel"):
        motivo = estado.get("erro") or "ultima_replicacao_falhou"
    elif not arquivo_presente:
        motivo = "replica_ausente"
    elif not fresco:
        motivo = "replica_desatualizada"
    elif not integridade_ok:
        motivo = (integridade or {}).get("motivo") or "replica_invalida"
    else:
        motivo = None
    saudavel = motivo is None
    return {
        "saudavel": saudavel,
        "saudavel_para_reinicio": True,
        "configurado": True,
        "estado": "replicado_e_verificado" if saudavel else "requer_atencao",
        "motivo": motivo,
        "fora_dispositivo": fora_dispositivo,
        "pronto_profissional": bool(
            saudavel and fora_dispositivo is True
        ),
        "dispositivos": dispositivos,
        "destino": str(destino) if destino else None,
        "replicado_em": (
            replicado_em.replace(microsecond=0).isoformat()
            if replicado_em else None
        ),
        "confirmado_em": (
            referencia_frescor.replace(microsecond=0).isoformat()
            if referencia_frescor else None
        ),
        "idade_horas": round(idade_horas, 2) if idade_horas is not None else None,
        "limite_horas": float(limite_horas),
        "integridade_verificada": verificar_integridade,
        "integridade": integridade,
    }


def calcular_sha256(caminho, bloco=1024 * 1024):
    resumo = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        while True:
            dados = arquivo.read(bloco)
            if not dados:
                break
            resumo.update(dados)
    return resumo.hexdigest()


def verificar_backup_pre_migracao(
    caminho, criar_manifesto=False, agora=None
):
    """Valida um backup anterior sem exigir o esquema do runtime novo."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {"valido": False, "motivo": "arquivo_ausente"}
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro&immutable=1"
        conexao = sqlite3.connect(uri, uri=True)
        try:
            integridade = [
                str(item[0])
                for item in conexao.execute("PRAGMA integrity_check")
            ]
            violacoes = len(
                conexao.execute("PRAGMA foreign_key_check").fetchall()
            )
        finally:
            conexao.close()
    except (sqlite3.DatabaseError, OSError, TypeError, ValueError) as erro:
        return {
            "valido": False,
            "motivo": "integridade_sqlite_falhou",
            "erro": type(erro).__name__,
        }
    sqlite_integro = integridade == ["ok"] and violacoes == 0
    checksum = calcular_sha256(caminho) if sqlite_integro else None
    manifesto_path = caminho_manifesto(caminho)
    manifesto = None
    if manifesto_path.exists():
        try:
            manifesto = json.loads(
                manifesto_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            manifesto = None
    if criar_manifesto and sqlite_integro and manifesto is None:
        agora = agora or datetime.now()
        manifesto = {
            "arquivo": caminho.name,
            "tipo": "pre_migracao",
            "criado_em": agora.replace(microsecond=0).isoformat(),
            "tamanho_bytes": caminho.stat().st_size,
            "sha256": checksum,
            "integridade_sqlite": "ok",
            "violacoes_chaves_estrangeiras": violacoes,
        }
        temporario = manifesto_path.with_suffix(".json.tmp")
        temporario.write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporario.replace(manifesto_path)
    checksum_confere = bool(
        manifesto
        and manifesto.get("tipo") == "pre_migracao"
        and checksum
        and manifesto.get("sha256") == checksum
    )
    if not sqlite_integro:
        motivo = "integridade_sqlite_falhou"
    elif manifesto is None:
        motivo = "manifesto_ausente"
    elif manifesto.get("tipo") != "pre_migracao":
        motivo = "tipo_manifesto_invalido"
    elif not checksum_confere:
        motivo = "checksum_divergente"
    else:
        motivo = None
    return {
        "valido": motivo is None,
        "motivo": motivo,
        "integridade_sqlite": sqlite_integro,
        "mensagens_integridade": integridade,
        "violacoes_chaves_estrangeiras": violacoes,
        "checksum_sha256": checksum,
        "checksum_confere": checksum_confere,
        "manifesto": str(manifesto_path) if manifesto else None,
    }


def _auditar_modelos_sombra_backup(conexao):
    """Valida somente envelopes persistidos; não monta dataset nem treina."""
    inconsistentes = {
        "temporais": [],
        "contextuais": [],
        "ancoras_longas": [],
        "modelos_longos": [],
    }
    for mercado in MERCADOS_CALIBRADOS:
        regra_versao = versao_regra_para_mercado(mercado)
        temporal = carregar_modelo_pontuacao_sombra(
            conexao, mercado, regra_versao
        )
        if temporal is not None and not temporal.get("integro"):
            inconsistentes["temporais"].append(mercado)
        contextual = carregar_modelo_pontuacao_contexto_sombra(
            conexao, mercado, regra_versao
        )
        if contextual is not None and not contextual.get("integro"):
            inconsistentes["contextuais"].append(mercado)
        ancora_longa = carregar_ancora_pontuacao_longa(
            conexao, mercado, regra_versao
        )
        if ancora_longa is not None and not ancora_longa.get("integro"):
            inconsistentes["ancoras_longas"].append(mercado)
        modelo_longo = carregar_modelo_pontuacao_longa(
            conexao, mercado, regra_versao
        )
        if modelo_longo is not None and not modelo_longo.get("integro"):
            inconsistentes["modelos_longos"].append(mercado)
    integro = not any(inconsistentes.values())
    return {
        "integro": integro,
        "estado": "integro" if integro else "inconsistente",
        "inconsistentes": inconsistentes,
    }


def _integridade_sqlite(caminho):
    try:
        uri = Path(caminho).resolve().as_uri() + "?mode=ro&immutable=1"
        conexao = sqlite3.connect(uri, uri=True)
        try:
            linhas = conexao.execute("PRAGMA integrity_check").fetchall()
            compatibilidade = auditar_compatibilidade(conexao)
            modelos_sombra = (
                _auditar_modelos_sombra_backup(conexao)
                if compatibilidade["compativel"]
                else {
                    "integro": False,
                    "estado": "nao_avaliado",
                    "inconsistentes": {},
                }
            )
        finally:
            conexao.close()
        mensagens = [str(item[0]) for item in linhas]
        return (
            mensagens == ["ok"], mensagens,
            compatibilidade, modelos_sombra,
        )
    except (sqlite3.DatabaseError, OSError, TypeError, ValueError) as erro:
        return False, [str(erro)], {
            "compativel": False,
            "tabelas": 0,
            "tabelas_ausentes": [],
            "colunas_ausentes": {},
            "violacoes_chaves_estrangeiras": 0,
        }, {
            "integro": False,
            "estado": "indisponivel",
            "inconsistentes": {},
        }


def verificar_backup_legado(caminho, manifesto_esperado=None):
    """Valida um ponto histórico sem exigir o esquema do runtime atual."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {"valido": False, "motivo": "arquivo_ausente"}
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro&immutable=1"
        conexao = sqlite3.connect(uri, uri=True)
        try:
            mensagens = [
                str(item[0])
                for item in conexao.execute("PRAGMA integrity_check")
            ]
            violacoes = len(
                conexao.execute("PRAGMA foreign_key_check").fetchall()
            )
        finally:
            conexao.close()
        tamanho = caminho.stat().st_size
        checksum = calcular_sha256(caminho)
    except (sqlite3.DatabaseError, OSError, TypeError, ValueError) as erro:
        return {
            "valido": False,
            "motivo": "integridade_sqlite_falhou",
            "erro": type(erro).__name__,
        }
    manifesto = manifesto_esperado
    if manifesto is None:
        try:
            manifesto = json.loads(
                caminho_manifesto(caminho).read_text(encoding="utf-8")
            )
        except (OSError, TypeError, json.JSONDecodeError):
            manifesto = None
    sqlite_integro = mensagens == ["ok"] and violacoes == 0
    checksum_confere = bool(
        isinstance(manifesto, dict)
        and manifesto.get("sha256") == checksum
    )
    tamanho_confere = bool(
        isinstance(manifesto, dict)
        and int(manifesto.get("tamanho_bytes") or -1) == tamanho
    )
    if not sqlite_integro:
        motivo = "integridade_sqlite_falhou"
    elif manifesto is None:
        motivo = "manifesto_ausente"
    elif not checksum_confere:
        motivo = "checksum_divergente"
    elif not tamanho_confere:
        motivo = "tamanho_divergente"
    else:
        motivo = None
    return {
        "valido": motivo is None,
        "motivo": motivo,
        "modo_verificacao": "integridade_legada",
        "integridade_sqlite": sqlite_integro,
        "mensagens_integridade": mensagens,
        "violacoes_chaves_estrangeiras": violacoes,
        "checksum_sha256": checksum,
        "checksum_confere": checksum_confere,
        "tamanho_bytes": tamanho,
        "tamanho_confere": tamanho_confere,
        "esquema_compativel": None,
    }


def verificar_backup(caminho, criar_manifesto=False, agora=None):
    caminho = Path(caminho)
    if not caminho.exists():
        return {"valido": False, "motivo": "arquivo_ausente"}
    integridade, mensagens, compatibilidade, modelos_sombra = (
        _integridade_sqlite(caminho)
    )
    tabelas = compatibilidade["tabelas"]
    checksum = calcular_sha256(caminho) if integridade else None
    manifesto_path = caminho_manifesto(caminho)
    manifesto = None
    if manifesto_path.exists():
        try:
            manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifesto = None
    if (
        criar_manifesto
        and integridade
        and compatibilidade["compativel"]
        and modelos_sombra["integro"]
        and manifesto is None
    ):
        agora = agora or datetime.now()
        manifesto = {
            "arquivo": caminho.name,
            "criado_em": agora.replace(microsecond=0).isoformat(),
            "tamanho_bytes": caminho.stat().st_size,
            "sha256": checksum,
            "integridade_sqlite": "ok",
            "tabelas": tabelas,
            "esquema_compativel": compatibilidade["compativel"],
            "violacoes_chaves_estrangeiras": compatibilidade[
                "violacoes_chaves_estrangeiras"
            ],
            "modelos_sombra_integros": True,
        }
        temporario = manifesto_path.with_suffix(".json.tmp")
        temporario.write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporario.replace(manifesto_path)
    checksum_confere = bool(
        manifesto and checksum and manifesto.get("sha256") == checksum
    )
    if not integridade:
        motivo = "integridade_sqlite_falhou"
    elif not compatibilidade["compativel"]:
        motivo = "esquema_ou_relacoes_incompativeis"
    elif not modelos_sombra["integro"]:
        motivo = "modelos_sombra_incompativeis"
    elif manifesto is None:
        motivo = "manifesto_ausente"
    elif not checksum_confere:
        motivo = "checksum_divergente"
    else:
        motivo = None
    return {
        "valido": motivo is None,
        "motivo": motivo,
        "integridade_sqlite": integridade,
        "mensagens_integridade": mensagens,
        "checksum_sha256": checksum,
        "checksum_confere": checksum_confere,
        "manifesto": str(manifesto_path) if manifesto is not None else None,
        "tamanho_bytes": caminho.stat().st_size,
        "tabelas": tabelas,
        "esquema_compativel": compatibilidade["compativel"],
        "tabelas_ausentes": compatibilidade["tabelas_ausentes"],
        "colunas_ausentes": compatibilidade["colunas_ausentes"],
        "violacoes_chaves_estrangeiras": compatibilidade[
            "violacoes_chaves_estrangeiras"
        ],
        "modelos_sombra_integros": modelos_sombra["integro"],
        "modelos_sombra_estado": modelos_sombra["estado"],
        "modelos_sombra_inconsistentes": modelos_sombra[
            "inconsistentes"
        ],
    }


def verificar_arquivo_backup(caminho, criar_manifesto=False, agora=None):
    """Valida de forma uniforme o legado ``.db`` e o novo ``.db.gz``."""
    caminho = Path(caminho)
    if caminho.name.endswith(".db.gz"):
        from backup_compactado import verificar_backup_compactado

        compactado = verificar_backup_compactado(caminho)
        sqlite = compactado.get("integridade_sqlite") or {}
        return {
            **sqlite,
            "valido": bool(compactado.get("saudavel")),
            "motivo": compactado.get("motivo"),
            "checksum_sha256": compactado.get("checksum_sqlite"),
            "checksum_compactado": compactado.get(
                "checksum_compactado"
            ),
            "manifesto": str(caminho_manifesto(caminho)),
            "tamanho_bytes": compactado.get(
                "tamanho_compactado_bytes", 0
            ),
            "tamanho_sqlite_bytes": compactado.get(
                "tamanho_sqlite_bytes", 0
            ),
            "formato": "sqlite-gzip-verificado-v1",
        }
    return verificar_backup(
        caminho, criar_manifesto=criar_manifesto, agora=agora
    )


def selecionar_backup_restauravel(pasta_backups):
    """Seleciona o ponto compatível mais recente sem modificar arquivos."""
    pasta_backups = Path(pasta_backups)
    candidatos = []
    vistos = set()
    for padrao in (
        "monitor_????????.db",
        "periodico_*.db",
        "pre_reinicio_*.db",
    ):
        for caminho in BackupBanco._glob_formatos(pasta_backups, padrao):
            resolvido = caminho.resolve()
            if resolvido not in vistos:
                vistos.add(resolvido)
                candidatos.append(caminho)
    ordenados = list(reversed(
        BackupBanco._ordenar_por_antiguidade(candidatos)
    ))
    avaliados = []
    for caminho in ordenados:
        verificacao = verificar_arquivo_backup(caminho)
        avaliados.append({
            "arquivo": caminho.name,
            "valido": bool(verificacao["valido"]),
            "motivo": verificacao.get("motivo"),
        })
        if verificacao["valido"]:
            return {
                "encontrado": True,
                "caminho": caminho,
                "verificacao": verificacao,
                "avaliados": avaliados,
            }
    return {
        "encontrado": False,
        "caminho": None,
        "verificacao": None,
        "avaliados": avaliados,
    }


def _gravar_json_atomico(caminho, dados):
    caminho = Path(caminho)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(caminho)


def restaurar_banco_de_backup(
    caminho_banco, pasta_backups, agora=None, motivo="corrupcao_comprovada"
):
    """Restaura atomicamente um banco parado e preserva a cópia danificada.

    A função não decide se a recuperação é necessária. O chamador precisa
    comprovar corrupção ou ausência do banco e garantir que nenhum processo
    esteja usando os arquivos.
    """
    caminho_banco = Path(caminho_banco)
    pasta_backups = Path(pasta_backups)
    agora = agora or datetime.now()
    pasta_backups.mkdir(parents=True, exist_ok=True)
    selecao = selecionar_backup_restauravel(pasta_backups)
    if not selecao["encontrado"]:
        return {
            "saudavel": False,
            "estado": "sem_backup_restauravel",
            "motivo": motivo,
            "avaliados": selecao["avaliados"],
        }

    origem = Path(selecao["caminho"])
    verificacao_origem = selecao["verificacao"]
    sufixo = agora.strftime("%Y%m%d_%H%M%S_%f")
    temporario = caminho_banco.parent / (
        f".{caminho_banco.stem}.recuperacao_{sufixo}.tmp"
    )
    quarentena = pasta_backups / (
        f"quarentena_corrompido_{caminho_banco.stem}_{sufixo}.db"
    )
    estado_path = caminho_banco.parent / "recuperacao_banco_estado.json"
    movidos = []
    restaurado_instalado = False
    temporario.unlink(missing_ok=True)
    try:
        if origem.name.endswith(".db.gz"):
            from backup_compactado import restaurar_backup_compactado

            extracao = restaurar_backup_compactado(origem, temporario)
            if not extracao.get("saudavel"):
                raise RuntimeError(
                    "extracao_backup_compactado_falhou:"
                    f"{extracao.get('estado')}:{extracao.get('motivo')}"
                )
        else:
            shutil.copy2(origem, temporario)
        with temporario.open("rb+") as arquivo:
            os.fsync(arquivo.fileno())
        checksum_temporario = calcular_sha256(temporario)
        if checksum_temporario != verificacao_origem["checksum_sha256"]:
            raise RuntimeError("checksum_copia_restauracao_divergente")
        integridade, mensagens, compatibilidade, modelos_sombra = (
            _integridade_sqlite(temporario)
        )
        if not (
            integridade
            and compatibilidade["compativel"]
            and modelos_sombra["integro"]
        ):
            raise RuntimeError(
                "copia_restauracao_invalida:"
                + ";".join(mensagens[:3])
            )

        if caminho_banco.exists():
            caminho_banco.replace(quarentena)
            movidos.append((quarentena, caminho_banco))
        for terminacao in ("-wal", "-shm"):
            atual = Path(f"{caminho_banco}{terminacao}")
            if atual.exists():
                preservado = Path(f"{quarentena}{terminacao}")
                atual.replace(preservado)
                movidos.append((preservado, atual))
        temporario.replace(caminho_banco)
        restaurado_instalado = True
        integridade_final, mensagens_finais, compatibilidade_final, modelos_final = (
            _integridade_sqlite(caminho_banco)
        )
        if not (
            integridade_final
            and compatibilidade_final["compativel"]
            and modelos_final["integro"]
        ):
            raise RuntimeError(
                "restauracao_final_invalida:"
                + ";".join(mensagens_finais[:3])
            )
    except Exception as erro:
        temporario.unlink(missing_ok=True)
        if restaurado_instalado:
            falho = pasta_backups / (
                f"restauracao_falhou_{caminho_banco.stem}_{sufixo}.db"
            )
            caminho_banco.replace(falho)
        for preservado, original in reversed(movidos):
            if preservado.exists() and not original.exists():
                preservado.replace(original)
        return {
            "saudavel": False,
            "estado": "restauracao_falhou",
            "motivo": motivo,
            "erro": type(erro).__name__,
            "detalhe": str(erro)[:300],
            "backup": origem.name,
        }

    registro = {
        "saudavel": True,
        "estado": "banco_restaurado",
        "motivo": motivo,
        "restaurado_em": agora.replace(microsecond=0).isoformat(),
        "backup": origem.name,
        "checksum_sha256": verificacao_origem["checksum_sha256"],
        "quarentena": quarentena.name if quarentena.exists() else None,
        "manifesto_backup": verificacao_origem.get("manifesto"),
        "backups_avaliados": selecao["avaliados"],
    }
    try:
        _gravar_json_atomico(estado_path, registro)
        registro["registro_persistido"] = True
    except OSError as erro:
        registro["registro_persistido"] = False
        registro["erro_registro"] = type(erro).__name__
    return registro
