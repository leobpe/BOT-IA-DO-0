"""Fingerprint reproduzível da população de gols antecipados."""

import hashlib
import inspect
import json
from pathlib import Path

from configuracao import odd_elegivel, obter_limites_risco


ARQUIVOS_LOGICA_GOLS_ANTECIPADOS = (
    "gols_antecipados.py",
    "contexto_pre_jogo.py",
    "qualidade_dados.py",
)


def calcular_linhagem_gols_antecipados(pasta=None):
    pasta = Path(pasta or Path(__file__).parent)
    limites = obter_limites_risco()
    componentes = {
        "esquema_linhagem": "gols-antecipados-semantica-v2",
        "arquivos": {
            nome: hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
            for nome in ARQUIVOS_LOGICA_GOLS_ANTECIPADOS
        },
        # O arquivo de configuração também contém integrações auxiliares que
        # não alteram a população de gols. Vinculamos somente as funções que
        # efetivamente decidem a faixa de odds, evitando invalidar a coorte por
        # uma flag independente (Scanner, TheStats etc.).
        "configuracao_relevante": {
            "odd_elegivel": hashlib.sha256(
                inspect.getsource(odd_elegivel).encode("utf-8")
            ).hexdigest(),
            "obter_limites_risco": hashlib.sha256(
                inspect.getsource(obter_limites_risco).encode("utf-8")
            ).hexdigest(),
        },
        "faixa_odd_operacional": {
            "minima": float(limites.odd_minima),
            "maxima": float(limites.odd_maxima),
        },
    }
    canonico = json.dumps(
        componentes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "fingerprint": hashlib.sha256(canonico.encode("utf-8")).hexdigest(),
        "componentes": componentes,
    }
