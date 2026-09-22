"""Persistência isolada das hipóteses pré-live prospectivas."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path


def _json(valor):
    return json.dumps(
        valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def identidade_bilhete(bilhete, data_alvo):
    pernas = sorted(
        (
            int(item.get("fixture_id") or 0),
            str(item.get("bookmaker_id") or ""),
            str(item.get("mercado") or ""),
            str(item.get("selecao") or ""),
            float(item.get("odd") or 0),
        )
        for item in bilhete.get("pernas") or []
    )
    bruto = _json({
        "data": data_alvo,
        "linhagem_sha256": str(bilhete.get("linhagem_sha256") or ""),
        "pernas": [item[:-1] for item in pernas],
    })
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


TABELAS_OBRIGATORIAS = {
    "execucoes_pre_live", "bilhetes_pre_live",
}


def verificar_banco_pre_live(caminho, exigir_esquema=True):
    caminho = Path(caminho)
    if not caminho.is_file() or caminho.stat().st_size <= 0:
        return {"valido": False, "motivo": "banco_ausente"}
    conexao = None
    try:
        uri = caminho.resolve().as_uri() + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True, timeout=10)
        integridade = [
            item[0] for item in conexao.execute("PRAGMA quick_check")
        ]
        tabelas = {
            item[0] for item in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    except (OSError, sqlite3.Error) as erro:
        return {
            "valido": False, "motivo": type(erro).__name__,
            "integridade": [], "tabelas_ausentes": sorted(TABELAS_OBRIGATORIAS),
        }
    finally:
        if conexao is not None:
            conexao.close()
    ausentes = sorted(TABELAS_OBRIGATORIAS - tabelas) if exigir_esquema else []
    return {
        "valido": integridade == ["ok"] and not ausentes,
        "motivo": (
            None if integridade == ["ok"] and not ausentes
            else "quick_check_falhou" if integridade != ["ok"]
            else "esquema_incompleto"
        ),
        "integridade": integridade,
        "tabelas_ausentes": ausentes,
    }


def verificar_backup_pre_live(caminho):
    """Confirma SQLite e manifesto criptográfico do backup pré-live."""
    caminho = Path(caminho)
    banco = verificar_banco_pre_live(caminho)
    manifesto_caminho = caminho.with_suffix(".db.manifest.json")
    try:
        manifesto = json.loads(
            manifesto_caminho.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, TypeError):
        manifesto = {}
    sha256 = (
        hashlib.sha256(caminho.read_bytes()).hexdigest()
        if caminho.is_file() else None
    )
    manifesto_valido = bool(
        manifesto.get("versao") == "backup-pre-live-v1"
        and manifesto.get("arquivo") == caminho.name
        and manifesto.get("tamanho") == (
            caminho.stat().st_size if caminho.is_file() else None
        )
        and manifesto.get("sha256") == sha256
        and manifesto.get("quick_check") == ["ok"]
    )
    return {
        "saudavel": bool(banco.get("valido") and manifesto_valido),
        "arquivo": caminho.name,
        "banco": banco,
        "manifesto_valido": manifesto_valido,
        "sha256": sha256,
    }


def preparar_banco_pre_live(caminho, pasta_backups):
    """Restaura corrupção comprovada; nunca substitui silenciosamente dados."""
    caminho = Path(caminho)
    pasta_backups = Path(pasta_backups)
    if not caminho.exists():
        return {"estado": "novo", "restaurado": False}
    verificacao = verificar_banco_pre_live(caminho)
    if verificacao["valido"]:
        return {"estado": "saudavel", "restaurado": False}
    candidatos = sorted(
        pasta_backups.glob("pre_live_[0-9]*.db"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    origem = next(
        (item for item in candidatos if verificar_banco_pre_live(item)["valido"]),
        None,
    )
    if origem is None:
        raise RuntimeError(
            "pre_live_corrompido_sem_backup_restauravel:"
            f"{verificacao.get('motivo')}"
        )
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    quarentena = pasta_backups / f"pre_live_corrompido_{carimbo}.db"
    pasta_backups.mkdir(parents=True, exist_ok=True)
    caminho.replace(quarentena)
    for sufixo in ("-wal", "-shm"):
        auxiliar = Path(f"{caminho}{sufixo}")
        if auxiliar.exists():
            auxiliar.replace(Path(f"{quarentena}{sufixo}"))
    temporario = caminho.with_name(f".{caminho.name}.restaurando.tmp")
    origem_conexao = destino_conexao = None
    try:
        origem_conexao = sqlite3.connect(
            origem.resolve().as_uri() + "?mode=ro", uri=True, timeout=10
        )
        destino_conexao = sqlite3.connect(temporario, timeout=10)
        origem_conexao.backup(destino_conexao)
    finally:
        if destino_conexao is not None:
            destino_conexao.close()
        if origem_conexao is not None:
            origem_conexao.close()
    restaurado = verificar_banco_pre_live(temporario)
    if not restaurado["valido"]:
        temporario.unlink(missing_ok=True)
        raise RuntimeError("restauracao_pre_live_nao_passou_integridade")
    temporario.replace(caminho)
    return {
        "estado": "restaurado", "restaurado": True,
        "backup": origem.name, "quarentena": quarentena.name,
    }


class RepositorioPreLive:
    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(self.caminho, timeout=30)
        self.conexao.execute("PRAGMA journal_mode=WAL")
        self.conexao.execute("PRAGMA foreign_keys=ON")
        self._preparar()

    def _preparar(self):
        with self.conexao:
            self.conexao.executescript("""
                CREATE TABLE IF NOT EXISTS execucoes_pre_live (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    iniciado_em TEXT NOT NULL,
                    finalizado_em TEXT,
                    data_alvo TEXT NOT NULL,
                    jogos_calendario INTEGER NOT NULL DEFAULT 0,
                    jogos_analisados INTEGER NOT NULL DEFAULT 0,
                    odds_completas INTEGER NOT NULL DEFAULT 0,
                    bilhetes INTEGER NOT NULL DEFAULT 0,
                    estado TEXT NOT NULL,
                    diagnostico_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bilhetes_pre_live (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identidade TEXT NOT NULL UNIQUE,
                    criado_em TEXT NOT NULL,
                    data_alvo TEXT NOT NULL,
                    fixture_ids_json TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    bookmaker TEXT NOT NULL,
                    odd_total REAL NOT NULL,
                    probabilidade_modelo REAL NOT NULL,
                    edge_modelo REAL NOT NULL,
                    estado TEXT NOT NULL,
                    versao TEXT NOT NULL,
                    linhagem_sha256 TEXT NOT NULL,
                    bilhete_json TEXT NOT NULL,
                    resultado TEXT,
                    retorno_unidades REAL,
                    finalizado_em TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_bilhetes_pre_live_data
                    ON bilhetes_pre_live(data_alvo, estado);
                CREATE TABLE IF NOT EXISTS entregas_pre_live (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bilhete_id INTEGER NOT NULL,
                    canal TEXT NOT NULL,
                    mensagem_id INTEGER,
                    criado_em TEXT NOT NULL,
                    resultado_sha256 TEXT,
                    resultado_editado_em TEXT,
                    UNIQUE(bilhete_id, canal),
                    FOREIGN KEY(bilhete_id) REFERENCES bilhetes_pre_live(id)
                );
                CREATE TABLE IF NOT EXISTS listas_pre_live (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_alvo TEXT NOT NULL,
                    canal TEXT NOT NULL,
                    mensagem_id INTEGER NOT NULL,
                    conteudo_sha256 TEXT NOT NULL,
                    conteudo_texto TEXT,
                    resultado_sha256 TEXT,
                    resultado_editado_em TEXT,
                    criado_em TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    UNIQUE(data_alvo, canal)
                );
                CREATE TABLE IF NOT EXISTS itens_listas_pre_live (
                    lista_id INTEGER NOT NULL,
                    bilhete_id INTEGER NOT NULL,
                    posicao INTEGER NOT NULL,
                    bilhete_json TEXT NOT NULL,
                    PRIMARY KEY(lista_id, posicao),
                    UNIQUE(lista_id, bilhete_id),
                    FOREIGN KEY(lista_id) REFERENCES listas_pre_live(id),
                    FOREIGN KEY(bilhete_id) REFERENCES bilhetes_pre_live(id)
                );
                CREATE TABLE IF NOT EXISTS resultados_pernas_pre_live (
                    bilhete_id INTEGER NOT NULL,
                    posicao INTEGER NOT NULL,
                    fixture_id INTEGER NOT NULL,
                    mercado TEXT NOT NULL,
                    selecao TEXT NOT NULL,
                    odd REAL NOT NULL,
                    resultado TEXT NOT NULL,
                    atualizado_em TEXT NOT NULL,
                    finalizado_em TEXT,
                    PRIMARY KEY(bilhete_id, posicao),
                    FOREIGN KEY(bilhete_id) REFERENCES bilhetes_pre_live(id)
                );
                CREATE INDEX IF NOT EXISTS idx_resultados_pernas_estado
                    ON resultados_pernas_pre_live(resultado, fixture_id);
                CREATE TABLE IF NOT EXISTS metadados_pre_live (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS coorte_pre_live_preciso (
                    definicao_sha256 TEXT NOT NULL,
                    bilhete_id INTEGER NOT NULL,
                    ordem INTEGER NOT NULL,
                    incluido_em TEXT NOT NULL,
                    odd_total REAL NOT NULL,
                    bilhete_json TEXT NOT NULL,
                    PRIMARY KEY(definicao_sha256, bilhete_id),
                    UNIQUE(definicao_sha256, ordem),
                    FOREIGN KEY(bilhete_id) REFERENCES bilhetes_pre_live(id)
                );
            """)
            colunas_entregas = {
                item[1] for item in self.conexao.execute(
                    "PRAGMA table_info(entregas_pre_live)"
                )
            }
            if "resultado_editado_em" not in colunas_entregas:
                self.conexao.execute(
                    "ALTER TABLE entregas_pre_live "
                    "ADD COLUMN resultado_editado_em TEXT"
                )
            if "resultado_sha256" not in colunas_entregas:
                self.conexao.execute(
                    "ALTER TABLE entregas_pre_live "
                    "ADD COLUMN resultado_sha256 TEXT"
                )
            colunas_listas = {
                item[1] for item in self.conexao.execute(
                    "PRAGMA table_info(listas_pre_live)"
                )
            }
            for coluna in (
                "conteudo_texto", "resultado_sha256",
                "resultado_editado_em",
            ):
                if coluna not in colunas_listas:
                    self.conexao.execute(
                        f"ALTER TABLE listas_pre_live ADD COLUMN {coluna} TEXT"
                    )
            self.conexao.execute(
                """
                UPDATE execucoes_pre_live
                SET estado='interrompida', finalizado_em=COALESCE(
                    finalizado_em, iniciado_em
                )
                WHERE estado='executando'
                """
            )

    def iniciar_execucao(self, data_alvo):
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT INTO execucoes_pre_live
                    (iniciado_em, data_alvo, estado, diagnostico_json)
                VALUES (?, ?, 'executando', '{}')
                """,
                (agora, str(data_alvo)),
            )
        return int(cursor.lastrowid)

    def concluir_execucao(self, execucao_id, resumo, estado="concluida"):
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            self.conexao.execute(
                """
                UPDATE execucoes_pre_live
                SET finalizado_em=?, jogos_calendario=?, jogos_analisados=?,
                    odds_completas=?, bilhetes=?, estado=?, diagnostico_json=?
                WHERE id=?
                """,
                (
                    agora,
                    int(resumo.get("jogos_calendario") or 0),
                    int(resumo.get("jogos_analisados") or 0),
                    int(bool(resumo.get("odds_completas"))),
                    int(resumo.get("bilhetes") or 0),
                    str(estado), _json(resumo), int(execucao_id),
                ),
            )

    def registrar_bilhetes(self, bilhetes, data_alvo, detalhar=False):
        agora = datetime.now(timezone.utc).isoformat()
        inseridos = promovidos = 0
        with self.conexao:
            for bilhete in bilhetes or []:
                identidade = identidade_bilhete(bilhete, data_alvo)
                fixture_ids = sorted({
                    int(item.get("fixture_id") or 0)
                    for item in bilhete.get("pernas") or []
                    if item.get("fixture_id")
                })
                cursor = self.conexao.execute(
                    """
                    INSERT OR IGNORE INTO bilhetes_pre_live (
                        identidade, criado_em, data_alvo, fixture_ids_json,
                        tipo, bookmaker, odd_total, probabilidade_modelo,
                        edge_modelo, estado, versao, linhagem_sha256,
                        bilhete_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identidade, agora, str(data_alvo), _json(fixture_ids),
                        bilhete["tipo"], str(bilhete.get("bookmaker") or ""),
                        float(bilhete["odd_total"]),
                        float(bilhete["probabilidade_modelo"]),
                        float(bilhete["edge_modelo"]),
                        str(bilhete["estado"]), str(bilhete["versao"]),
                        str(bilhete["linhagem_sha256"]), _json(bilhete),
                    ),
                )
                inseridos += int(cursor.rowcount > 0)
                estado_novo = str(bilhete.get("estado") or "")
                estados_confirmados = {
                    "apto_sombra_confirmado", "apto_envio_automatico",
                }
                if cursor.rowcount == 0 and estado_novo in estados_confirmados:
                    atualizado = self.conexao.execute(
                        """
                        UPDATE bilhetes_pre_live
                        SET odd_total=?, probabilidade_modelo=?, edge_modelo=?,
                            estado=?, bilhete_json=?
                        WHERE identidade=? AND resultado IS NULL
                          AND (
                            estado='preliminar_aguardando_escalacao'
                            OR (
                              ?='apto_envio_automatico'
                              AND estado='apto_sombra_confirmado'
                            )
                          )
                        """,
                        (
                            float(bilhete["odd_total"]),
                            float(bilhete["probabilidade_modelo"]),
                            float(bilhete["edge_modelo"]),
                            estado_novo, _json(bilhete), identidade,
                            estado_novo,
                        ),
                    )
                    promovidos += int(atualizado.rowcount > 0)
        if detalhar:
            return {"inseridos": inseridos, "confirmados": promovidos}
        return inseridos

    def listar_bilhetes_pendentes(self, limite=200):
        linhas = self.conexao.execute(
            """
            SELECT id, bilhete_json
            FROM bilhetes_pre_live
            WHERE resultado IS NULL
               OR EXISTS (
                    SELECT 1 FROM resultados_pernas_pre_live r
                    WHERE r.bilhete_id=bilhetes_pre_live.id
                      AND r.resultado='pendente'
               )
            ORDER BY criado_em, id
            LIMIT ?
            """,
            (max(int(limite), 1),),
        ).fetchall()
        resultado = []
        for bilhete_id, bruto in linhas:
            try:
                bilhete = json.loads(bruto)
            except (TypeError, json.JSONDecodeError):
                continue
            resultado.append({"id": int(bilhete_id), "bilhete": bilhete})
        return resultado

    def listar_bilhetes_entregues_pendentes(self, limite=50):
        linhas = self.conexao.execute(
            """
            SELECT DISTINCT b.id, b.bilhete_json
            FROM bilhetes_pre_live b
            JOIN entregas_pre_live e ON e.bilhete_id=b.id
            WHERE b.resultado IS NULL
               OR EXISTS (
                    SELECT 1 FROM resultados_pernas_pre_live r
                    WHERE r.bilhete_id=b.id AND r.resultado='pendente'
               )
            ORDER BY b.criado_em, b.id
            LIMIT ?
            """,
            (max(int(limite), 1),),
        ).fetchall()
        resultado = []
        for bilhete_id, bruto in linhas:
            try:
                bilhete = json.loads(bruto)
            except (TypeError, json.JSONDecodeError):
                continue
            resultado.append({"id": int(bilhete_id), "bilhete": bilhete})
        return resultado

    def listar_bilhetes_publicados_pendentes(
        self, limite=200, data_alvo=None, canal=None
    ):
        filtros = [
            """
            (
                b.resultado IS NULL
                OR EXISTS (
                    SELECT 1 FROM resultados_pernas_pre_live r
                    WHERE r.bilhete_id=b.id AND r.resultado='pendente'
                )
            )
            """,
            """
            (
                EXISTS (
                    SELECT 1 FROM entregas_pre_live e
                    WHERE e.bilhete_id=b.id
                      AND (? IS NULL OR e.canal=?)
                )
                OR EXISTS (
                    SELECT 1
                    FROM itens_listas_pre_live i
                    JOIN listas_pre_live l ON l.id=i.lista_id
                    WHERE i.bilhete_id=b.id
                      AND (? IS NULL OR l.canal=?)
                )
            )
            """,
        ]
        parametros = [canal, canal, canal, canal]
        if data_alvo is not None:
            filtros.append("b.data_alvo=?")
            parametros.append(str(data_alvo))
        parametros.append(max(int(limite), 1))
        consulta = f"""
            SELECT DISTINCT b.id, b.bilhete_json
            FROM bilhetes_pre_live b
            WHERE {' AND '.join(filtros)}
            ORDER BY b.criado_em, b.id
            LIMIT ?
        """
        linhas = self.conexao.execute(consulta, parametros).fetchall()
        resultado = []
        for bilhete_id, bruto in linhas:
            try:
                bilhete = json.loads(bruto)
            except (TypeError, json.JSONDecodeError):
                continue
            resultado.append({"id": int(bilhete_id), "bilhete": bilhete})
        return resultado

    def listar_confirmados_para_envio(self, data_alvo, canal, limite=3):
        linhas = self.conexao.execute(
            """
            SELECT b.id, b.bilhete_json
            FROM bilhetes_pre_live b
            LEFT JOIN entregas_pre_live e
              ON e.bilhete_id=b.id AND e.canal=?
            WHERE b.data_alvo=?
              AND b.estado='apto_envio_automatico'
              AND b.resultado IS NULL
              AND e.id IS NULL
            ORDER BY b.edge_modelo DESC, b.probabilidade_modelo DESC, b.id
            LIMIT ?
            """,
            (str(canal), str(data_alvo), max(int(limite), 1)),
        ).fetchall()
        itens = []
        for bilhete_id, bruto in linhas:
            try:
                bilhete = json.loads(bruto)
            except (TypeError, json.JSONDecodeError):
                continue
            itens.append({"id": int(bilhete_id), "bilhete": bilhete})
        return itens

    def total_entregas(self, data_alvo, canal):
        linha = self.conexao.execute(
            """
            SELECT COUNT(*)
            FROM entregas_pre_live e
            JOIN bilhetes_pre_live b ON b.id=e.bilhete_id
            WHERE b.data_alvo=? AND e.canal=?
            """,
            (str(data_alvo), str(canal)),
        ).fetchone()
        return int(linha[0] or 0)

    def obter_lista_preliminar(self, data_alvo, canal):
        linha = self.conexao.execute(
            """
            SELECT mensagem_id, conteudo_sha256, atualizado_em,
                   conteudo_texto, resultado_sha256, resultado_editado_em
            FROM listas_pre_live
            WHERE data_alvo=? AND canal=?
            """,
            (str(data_alvo), str(canal)),
        ).fetchone()
        if linha is None:
            return None
        return {
            "mensagem_id": int(linha[0]),
            "conteudo_sha256": str(linha[1]),
            "atualizado_em": str(linha[2]),
            "conteudo_texto": linha[3],
            "resultado_sha256": linha[4],
            "resultado_editado_em": linha[5],
        }

    def listar_fixture_ids_publicados(self, data_alvo, canal):
        """Lista partidas já exibidas em qualquer lista do canal no dia."""
        linhas = self.conexao.execute(
            """
            SELECT b.fixture_ids_json
            FROM listas_pre_live l
            JOIN itens_listas_pre_live i ON i.lista_id=l.id
            JOIN bilhetes_pre_live b ON b.id=i.bilhete_id
            WHERE l.canal=?
              AND (l.data_alvo=? OR l.data_alvo LIKE ?)
            """,
            (str(canal), str(data_alvo), f"{data_alvo}|%"),
        ).fetchall()
        fixture_ids = set()
        for (bruto,) in linhas:
            try:
                ids = json.loads(bruto or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            for fixture_id in ids:
                try:
                    fixture_ids.add(int(fixture_id))
                except (TypeError, ValueError):
                    continue
        return fixture_ids

    def registrar_lista_preliminar(
        self, data_alvo, canal, mensagem_id, conteudo_sha256,
        conteudo_texto=None, bilhetes=None, data_bilhetes=None,
    ):
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            self.conexao.execute(
                """
                INSERT INTO listas_pre_live (
                    data_alvo, canal, mensagem_id, conteudo_sha256,
                    conteudo_texto, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(data_alvo, canal) DO UPDATE SET
                    mensagem_id=excluded.mensagem_id,
                    conteudo_sha256=excluded.conteudo_sha256,
                    conteudo_texto=excluded.conteudo_texto,
                    atualizado_em=excluded.atualizado_em
                """,
                (
                    str(data_alvo), str(canal), int(mensagem_id),
                    str(conteudo_sha256), conteudo_texto, agora, agora,
                ),
            )
            lista_id = int(self.conexao.execute(
                "SELECT id FROM listas_pre_live WHERE data_alvo=? AND canal=?",
                (str(data_alvo), str(canal)),
            ).fetchone()[0])
            for posicao, bilhete in enumerate(bilhetes or [], 1):
                identidade = identidade_bilhete(
                    bilhete, str(data_bilhetes or str(data_alvo).split("|", 1)[0])
                )
                linha_bilhete = self.conexao.execute(
                    "SELECT id FROM bilhetes_pre_live WHERE identidade=?",
                    (identidade,),
                ).fetchone()
                if linha_bilhete is None:
                    continue
                self.conexao.execute(
                    """
                    INSERT OR IGNORE INTO itens_listas_pre_live (
                        lista_id, bilhete_id, posicao, bilhete_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        lista_id, int(linha_bilhete[0]), int(posicao),
                        _json(bilhete),
                    ),
                )
        return self.obter_lista_preliminar(data_alvo, canal)

    def listar_listas_para_editar(self, limite=20):
        linhas = self.conexao.execute(
            """
            SELECT l.id, l.canal, l.mensagem_id, l.conteudo_texto,
                   l.resultado_sha256
            FROM listas_pre_live l
            WHERE l.conteudo_texto IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM itens_listas_pre_live i
                JOIN bilhetes_pre_live b ON b.id=i.bilhete_id
                WHERE i.lista_id=l.id AND b.resultado IS NOT NULL
              )
            ORDER BY l.id DESC
            LIMIT ?
            """,
            (max(int(limite), 1),),
        ).fetchall()
        listas = []
        for lista_id, canal, mensagem_id, texto, hash_anterior in linhas:
            resultados = []
            for posicao, bilhete_id, resultado in self.conexao.execute(
                    """
                    SELECT i.posicao, b.id, b.resultado
                    FROM itens_listas_pre_live i
                    JOIN bilhetes_pre_live b ON b.id=i.bilhete_id
                    WHERE i.lista_id=?
                    ORDER BY i.posicao
                    """,
                    (int(lista_id),),
                ).fetchall():
                resultados.append({
                    "posicao": int(posicao),
                    "resultado": resultado,
                    "pernas": self._resultados_pernas_resumidos(
                        int(bilhete_id)
                    ),
                })
            assinatura = hashlib.sha256(
                _json(resultados).encode("utf-8")
            ).hexdigest()
            if assinatura == hash_anterior:
                continue
            listas.append({
                "id": int(lista_id),
                "canal": str(canal),
                "mensagem_id": int(mensagem_id),
                "conteudo_texto": str(texto),
                "resultados": resultados,
                "resultado_sha256": assinatura,
            })
        return listas

    def marcar_lista_resultados_editada(self, lista_id, resultado_sha256):
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE listas_pre_live
                SET resultado_sha256=?, resultado_editado_em=?, atualizado_em=?
                WHERE id=?
                """,
                (str(resultado_sha256), agora, agora, int(lista_id)),
            )
        return cursor.rowcount > 0

    def registrar_entrega(self, bilhete_id, canal, mensagem_id):
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            cursor = self.conexao.execute(
                """
                INSERT OR IGNORE INTO entregas_pre_live
                    (bilhete_id, canal, mensagem_id, criado_em)
                VALUES (?, ?, ?, ?)
                """,
                (int(bilhete_id), str(canal), int(mensagem_id), agora),
            )
        return cursor.rowcount > 0

    def listar_entregas_para_editar(self, limite=50):
        linhas = self.conexao.execute(
            """
            SELECT e.id, e.canal, e.mensagem_id, b.id, b.bilhete_json,
                   b.resultado, e.resultado_sha256
            FROM entregas_pre_live e
            JOIN bilhetes_pre_live b ON b.id=e.bilhete_id
            WHERE b.resultado IN ('green', 'red', 'anulada')
              AND e.mensagem_id IS NOT NULL
            ORDER BY b.finalizado_em DESC, e.id DESC
            """
        ).fetchall()
        itens = []
        for (
            entrega_id, canal, mensagem_id, bilhete_id, bruto, resultado,
            hash_anterior,
        ) in linhas:
            try:
                bilhete = json.loads(bruto)
            except (TypeError, json.JSONDecodeError):
                continue
            resultados_pernas = self._resultados_pernas_resumidos(
                int(bilhete_id)
            )
            assinatura = self._assinatura_resultado(
                resultado, resultados_pernas
            )
            if assinatura == hash_anterior:
                continue
            itens.append({
                "id": int(entrega_id),
                "canal": str(canal),
                "mensagem_id": int(mensagem_id),
                "bilhete": bilhete,
                "resultado": str(resultado),
                "resultados_pernas": resultados_pernas,
                "resultado_sha256": assinatura,
            })
            if len(itens) >= max(int(limite), 1):
                break
        return itens

    def _resultados_pernas_resumidos(self, bilhete_id):
        return [
            {
                "posicao": int(posicao),
                "fixture_id": int(fixture_id),
                "mercado": str(mercado),
                "selecao": str(selecao),
                "resultado": str(resultado),
            }
            for (
                posicao, fixture_id, mercado, selecao, resultado
            ) in self.conexao.execute(
                """
                SELECT posicao, fixture_id, mercado, selecao, resultado
                FROM resultados_pernas_pre_live
                WHERE bilhete_id=?
                ORDER BY posicao
                """,
                (int(bilhete_id),),
            ).fetchall()
        ]

    @staticmethod
    def _assinatura_resultado(resultado, resultados_pernas):
        bruto = _json({
            "resultado": resultado,
            "pernas": list(resultados_pernas or []),
        })
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    def marcar_entrega_editada(
        self, entrega_id, resultado_sha256=None
    ):
        agora = datetime.now(timezone.utc).isoformat()
        if resultado_sha256 is None:
            linha = self.conexao.execute(
                """
                SELECT b.id, b.resultado
                FROM entregas_pre_live e
                JOIN bilhetes_pre_live b ON b.id=e.bilhete_id
                WHERE e.id=?
                """,
                (int(entrega_id),),
            ).fetchone()
            if linha is None:
                return False
            resultado_sha256 = self._assinatura_resultado(
                linha[1], self._resultados_pernas_resumidos(int(linha[0]))
            )
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE entregas_pre_live
                SET resultado_sha256=?, resultado_editado_em=?
                WHERE id=? AND (
                    resultado_sha256 IS NULL OR resultado_sha256<>?
                )
                """,
                (
                    str(resultado_sha256), agora, int(entrega_id),
                    str(resultado_sha256),
                ),
            )
        return cursor.rowcount > 0

    def registrar_resultados_pernas(self, bilhete_id, bilhete, resultados):
        """Persiste cada seleção, inclusive as ainda pendentes da múltipla."""
        pernas = list((bilhete or {}).get("pernas") or [])
        resultados = list(resultados or [])
        if len(pernas) != len(resultados):
            return 0
        agora = datetime.now(timezone.utc).isoformat()
        gravados = 0
        with self.conexao:
            for posicao, (perna, resultado) in enumerate(
                zip(pernas, resultados), 1
            ):
                resultado = str(resultado or "pendente")
                finalizado_em = (
                    agora if resultado in {"green", "red", "anulada"}
                    else None
                )
                cursor = self.conexao.execute(
                    """
                    INSERT INTO resultados_pernas_pre_live (
                        bilhete_id, posicao, fixture_id, mercado, selecao,
                        odd, resultado, atualizado_em, finalizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(bilhete_id, posicao) DO UPDATE SET
                        fixture_id=excluded.fixture_id,
                        mercado=excluded.mercado,
                        selecao=excluded.selecao,
                        odd=excluded.odd,
                        resultado=CASE
                            WHEN resultados_pernas_pre_live.resultado
                                 IN ('green', 'red', 'anulada')
                            THEN resultados_pernas_pre_live.resultado
                            ELSE excluded.resultado
                        END,
                        atualizado_em=excluded.atualizado_em,
                        finalizado_em=COALESCE(
                            resultados_pernas_pre_live.finalizado_em,
                            excluded.finalizado_em
                        )
                    """,
                    (
                        int(bilhete_id), int(posicao),
                        int(perna.get("fixture_id") or 0),
                        str(perna.get("mercado") or ""),
                        str(perna.get("selecao") or ""),
                        float(perna.get("odd") or 0.0), resultado,
                        agora, finalizado_em,
                    ),
                )
                gravados += int(cursor.rowcount > 0)
        return gravados

    def listar_resultados_pernas(self, bilhete_id=None):
        parametros = []
        filtro = ""
        if bilhete_id is not None:
            filtro = "WHERE bilhete_id=?"
            parametros.append(int(bilhete_id))
        linhas = self.conexao.execute(
            f"""
            SELECT bilhete_id, posicao, fixture_id, mercado, selecao, odd,
                   resultado, atualizado_em, finalizado_em
            FROM resultados_pernas_pre_live
            {filtro}
            ORDER BY bilhete_id, posicao
            """,
            parametros,
        ).fetchall()
        return [
            {
                "bilhete_id": int(linha[0]),
                "posicao": int(linha[1]),
                "fixture_id": int(linha[2]),
                "mercado": str(linha[3]),
                "selecao": str(linha[4]),
                "odd": float(linha[5]),
                "resultado": str(linha[6]),
                "atualizado_em": str(linha[7]),
                "finalizado_em": linha[8],
            }
            for linha in linhas
        ]

    def finalizar_bilhete(self, bilhete_id, resultado, retorno):
        if resultado not in {"green", "red", "anulada"}:
            return False
        agora = datetime.now(timezone.utc).isoformat()
        with self.conexao:
            cursor = self.conexao.execute(
                """
                UPDATE bilhetes_pre_live
                SET resultado=?, retorno_unidades=?, finalizado_em=?
                WHERE id=? AND resultado IS NULL
                """,
                (str(resultado), float(retorno), agora, int(bilhete_id)),
            )
        return cursor.rowcount > 0

    def resumir_validacao(
        self, linhagem_sha256, estado="apto_sombra_confirmado"
    ):
        linhas = self.conexao.execute(
            """
            SELECT resultado, retorno_unidades
            FROM bilhetes_pre_live
            WHERE linhagem_sha256=? AND estado=?
              AND resultado IN ('green', 'red')
            ORDER BY finalizado_em, id
            """,
            (str(linhagem_sha256), str(estado)),
        ).fetchall()
        retornos = [float(linha[1]) for linha in linhas]
        total = len(retornos)
        greens = sum(linha[0] == "green" for linha in linhas)
        roi = sum(retornos) / total if total else None
        limite_inferior_roi = None
        if total >= 2:
            desvio = statistics.stdev(retornos)
            limite_inferior_roi = roi - 1.96 * desvio / math.sqrt(total)
        taxa = greens / total if total else None
        wilson_inferior = None
        if total:
            z = 1.96
            denominador = 1 + z * z / total
            centro = taxa + z * z / (2 * total)
            margem = z * math.sqrt(
                taxa * (1 - taxa) / total + z * z / (4 * total * total)
            )
            wilson_inferior = (centro - margem) / denominador
        return {
            "linhagem_sha256": str(linhagem_sha256),
            "resultados": total,
            "greens": greens,
            "reds": total - greens,
            "taxa_acerto": round(taxa, 4) if taxa is not None else None,
            "wilson_95_inferior": (
                round(wilson_inferior, 4)
                if wilson_inferior is not None else None
            ),
            "roi": round(roi, 4) if roi is not None else None,
            "roi_95_inferior": (
                round(limite_inferior_roi, 4)
                if limite_inferior_roi is not None else None
            ),
            "amostra_minima": 30,
            "apto_revisao": bool(
                total >= 30 and roi is not None and roi > 0
                and limite_inferior_roi is not None
                and limite_inferior_roi > 0
            ),
            "promocao_automatica": False,
        }

    def criar_backup(self, pasta_backups, agora=None, manter=12):
        agora = agora or datetime.now(timezone.utc)
        pasta_backups = Path(pasta_backups)
        pasta_backups.mkdir(parents=True, exist_ok=True)
        destino = pasta_backups / f"pre_live_{agora:%Y%m%d_%H%M%S}.db"
        temporario = pasta_backups / f".{destino.name}.tmp"
        conexao_destino = sqlite3.connect(temporario, timeout=30)
        try:
            self.conexao.backup(conexao_destino)
        finally:
            conexao_destino.close()
        verificacao = verificar_banco_pre_live(temporario)
        if not verificacao["valido"]:
            temporario.unlink(missing_ok=True)
            raise RuntimeError(
                "backup_pre_live_invalido:"
                f"{verificacao.get('motivo')}"
            )
        temporario.replace(destino)
        resumo = hashlib.sha256(destino.read_bytes()).hexdigest()
        manifesto = {
            "versao": "backup-pre-live-v1",
            "criado_em": agora.isoformat(),
            "arquivo": destino.name,
            "tamanho": destino.stat().st_size,
            "sha256": resumo,
            "quick_check": ["ok"],
        }
        destino.with_suffix(".db.manifest.json").write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        arquivos = sorted(
            pasta_backups.glob("pre_live_[0-9]*.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for antigo in arquivos[max(int(manter), 1):]:
            antigo.unlink(missing_ok=True)
            antigo.with_suffix(".db.manifest.json").unlink(missing_ok=True)
        return {
            "criado": True, "arquivo": destino.name,
            "sha256": resumo, "quick_check": ["ok"],
        }

    def fechar(self):
        self.conexao.close()
