import argparse
import hashlib
import json
import math
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PASTA = Path(__file__).parent
ARQUIVO_RELATORIO = PASTA / "lsports_escanteios_2t_diagnostico.json"
VERSAO_DIAGNOSTICO = "lsports-prova-escanteios-2t-v1"
LIMITE_AMOSTRA_BYTES = 25 * 1024 * 1024
STATUS_LIQUIDADO_DOCUMENTADO = "3"
TIPO_MENSAGEM_LIQUIDACAO = "35"
IDADE_MAXIMA_ATUALIZACAO_SEGUNDOS = 15 * 60
TOLERANCIA_FUTURO_SEGUNDOS = 5


def _texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(texto.casefold().split())


def _campo(objeto, nome, padrao=None):
    if not isinstance(objeto, dict):
        return padrao
    nome = str(nome).casefold()
    for chave, valor in objeto.items():
        if str(chave).casefold() == nome:
            return valor
    return padrao


def _identificador(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _numero(valor):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _linha_asiatica_valida(valor):
    linha = _numero(valor)
    if linha is None or not 0 <= linha <= 100:
        return False
    return abs(linha * 4 - round(linha * 4)) < 1e-8


def _instante_iso(valor):
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        instante = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        return None
    return instante.astimezone(timezone.utc)


def _timestamp_iso(valor):
    instante = _instante_iso(valor)
    return instante.isoformat() if instante is not None else None


def _cabecalho(payload):
    if isinstance(payload, dict):
        direto = _campo(payload, "Header")
        if isinstance(direto, dict):
            return direto
        for valor in payload.values():
            encontrado = _cabecalho(valor)
            if encontrado is not None:
                return encontrado
    elif isinstance(payload, list):
        for valor in payload:
            encontrado = _cabecalho(valor)
            if encontrado is not None:
                return encontrado
    return None


def _instante_mensagem(payload):
    cabecalho = _cabecalho(payload) or {}
    servidor = _numero(_campo(cabecalho, "ServerTimestamp"))
    if servidor is not None:
        # A documentação usa Unix epoch em milissegundos. Segundos também são
        # aceitos para não depender do serializador usado na exportação.
        if abs(servidor) >= 100_000_000_000:
            servidor /= 1000.0
        try:
            return datetime.fromtimestamp(servidor, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return _instante_iso(_campo(cabecalho, "CreationDate"))


def _atualizacao_coerente(valor, referencia):
    instante = _instante_iso(valor)
    if instante is None or referencia is None:
        return None, False
    idade = (referencia - instante).total_seconds()
    coerente = (
        -TOLERANCIA_FUTURO_SEGUNDOS
        <= idade
        <= IDADE_MAXIMA_ATUALIZACAO_SEGUNDOS
    )
    return instante.isoformat(), coerente


def _lista_entidades(objeto, plural, singular):
    valor = _campo(objeto, plural)
    if valor is None:
        valor = _campo(objeto, singular)
    if isinstance(valor, list):
        return [item for item in valor if isinstance(item, dict)]
    if isinstance(valor, dict):
        internos = _campo(valor, singular)
        if isinstance(internos, list):
            return [item for item in internos if isinstance(item, dict)]
        if isinstance(internos, dict):
            return [internos]
        return [valor]
    return []


def _eventos(payload):
    encontrados = []
    visitados = set()

    def visitar(valor):
        if isinstance(valor, dict):
            if (
                _identificador(_campo(valor, "FixtureId")) is not None
                and _campo(valor, "Markets") is not None
            ):
                identidade = id(valor)
                if identidade not in visitados:
                    visitados.add(identidade)
                    encontrados.append(valor)
                return
            for item in valor.values():
                visitar(item)
        elif isinstance(valor, list):
            for item in valor:
                visitar(item)

    visitar(payload)
    return encontrados


def _mercado_2t_cantos(nome):
    texto = _texto_normalizado(nome)
    tem_cantos = "corner" in texto or "escanteio" in texto
    tem_2t = any(
        termo in texto
        for termo in (
            "2nd half",
            "second half",
            "2o tempo",
            "2 tempo",
            "segundo tempo",
        )
    )
    tem_over_under = "over" in texto and "under" in texto
    excluido = any(
        termo in texto
        for termo in (
            "exactly",
            "exatamente",
            "race",
            "corrida",
            "handicap",
            "home team",
            "away team",
            "mandante",
            "visitante",
        )
    )
    return tem_cantos and tem_2t and tem_over_under and not excluido


def _contexto_partida(evento):
    erros = []
    partida_id = _identificador(_campo(evento, "FixtureId"))
    if partida_id is None:
        erros.append("fixture_id_ausente")

    fixture = _campo(evento, "Fixture")
    if not isinstance(fixture, dict):
        fixture = {}
        erros.append("fixture_ausente")

    esporte = _campo(fixture, "Sport")
    esporte_nome = str(_campo(esporte, "Name", "") or "").strip()
    if _texto_normalizado(esporte_nome) not in ("football", "soccer", "futebol"):
        erros.append("esporte_futebol_nao_comprovado")

    liga = _campo(fixture, "League")
    liga_id = _identificador(_campo(liga, "Id"))
    liga_nome = str(_campo(liga, "Name", "") or "").strip()
    if liga_id is None or not liga_nome:
        erros.append("liga_incompleta")

    participantes = _lista_entidades(
        fixture, "Participants", "Participant"
    )
    times = []
    posicoes = set()
    for participante in participantes:
        participante_id = _identificador(_campo(participante, "Id"))
        nome = str(_campo(participante, "Name", "") or "").strip()
        posicao = _identificador(_campo(participante, "Position"))
        if participante_id is not None and nome and posicao in ("1", "2"):
            times.append({
                "id": participante_id,
                "nome": nome,
                "posicao": int(posicao),
            })
            posicoes.add(posicao)
    if len(times) != 2 or posicoes != {"1", "2"}:
        erros.append("participantes_incompletos_ou_ambiguos")

    return {
        "fixture_id": partida_id,
        "liga_id": liga_id,
        "liga": liga_nome or None,
        "times": sorted(times, key=lambda item: item["posicao"]),
    }, erros


def _status_contrato(contrato, chave):
    valores = _campo(contrato, chave, [])
    if not isinstance(valores, list):
        return set()
    return {
        str(valor).strip()
        for valor in valores
        if str(valor).strip()
    }


def _contrato_validado(contrato):
    contrato = contrato if isinstance(contrato, dict) else {}
    status_ativos = _status_contrato(contrato, "status_ativos")
    vencedores = _status_contrato(contrato, "settlement_vencedor")
    perdedores = _status_contrato(contrato, "settlement_perdedor")
    reembolsos = _status_contrato(contrato, "settlement_reembolso")
    origem = str(_campo(contrato, "origem_mapeamento", "") or "").strip()
    origem_sha256 = (
        hashlib.sha256(origem.encode("utf-8")).hexdigest()
        if origem else None
    )
    formato = _texto_normalizado(_campo(contrato, "formato_preco"))
    status_liquidado = str(
        _campo(
            contrato,
            "status_liquidado",
            STATUS_LIQUIDADO_DOCUMENTADO,
        )
    ).strip()
    erros = []
    if formato != "decimal":
        erros.append("formato_preco_decimal_nao_comprovado")
    if not status_ativos:
        erros.append("mapeamento_status_ativo_ausente")
    if not origem:
        erros.append("origem_mapeamento_status_ausente")
    if not vencedores or not perdedores:
        erros.append("mapeamento_liquidacao_incompleto")
    if status_liquidado != STATUS_LIQUIDADO_DOCUMENTADO:
        erros.append("status_liquidado_diverge_documentacao")
    return {
        "formato_preco": formato,
        "status_ativos": status_ativos,
        "status_liquidado": status_liquidado,
        "vencedores": vencedores,
        "perdedores": perdedores,
        "reembolsos": reembolsos,
        "origem": origem,
        "origem_sha256": origem_sha256,
    }, erros


def _provedores(mercado):
    provedores = _lista_entidades(mercado, "Providers", "Provider")
    return provedores


def _apostas(objeto):
    return _lista_entidades(objeto, "Bets", "Bet")


def _agrupar_apostas(apostas):
    grupos = {}
    erros = []
    for aposta in apostas:
        nome = _texto_normalizado(_campo(aposta, "Name"))
        if nome not in ("over", "under"):
            erros.append("mercado_contem_opcao_diferente_de_over_under")
            continue
        linha = _numero(_campo(aposta, "Line"))
        base = _numero(_campo(aposta, "BaseLine"))
        if not _linha_asiatica_valida(linha) or base is None:
            erros.append("linha_ou_baseline_invalida")
            continue
        chave = (float(linha), float(base))
        grupo = grupos.setdefault(chave, {})
        if nome in grupo:
            erros.append("selecao_duplicada_ambigua")
            continue
        grupo[nome] = aposta
    return grupos, erros


def _avaliar_ofertas(snapshot, contrato):
    ofertas = []
    motivos = []
    mercados_2t = 0
    instante_snapshot = _instante_mensagem(snapshot)
    if instante_snapshot is None:
        motivos.append("timestamp_mensagem_snapshot_ausente_ou_invalido")
    for evento in _eventos(snapshot):
        contexto, erros_contexto = _contexto_partida(evento)
        mercados = _lista_entidades(evento, "Markets", "Market")
        for mercado in mercados:
            nome_mercado = str(_campo(mercado, "Name", "") or "").strip()
            if not _mercado_2t_cantos(nome_mercado):
                continue
            mercados_2t += 1
            mercado_id = _identificador(_campo(mercado, "Id"))
            if mercado_id is None:
                motivos.append("market_id_ausente")
                continue
            if erros_contexto:
                motivos.extend(erros_contexto)
                continue

            provedores = _provedores(mercado)
            if not provedores:
                motivos.append("provider_ausente")
                continue
            for provedor in provedores:
                provedor_id = _identificador(_campo(provedor, "Id"))
                provedor_nome = str(
                    _campo(provedor, "Name", "") or ""
                ).strip()
                if provedor_id is None or not provedor_nome:
                    motivos.append("provider_incompleto")
                    continue
                provider_atualizado, provider_coerente = (
                    _atualizacao_coerente(
                        _campo(provedor, "LastUpdate"), instante_snapshot
                    )
                )
                if not provider_coerente:
                    motivos.append("provider_last_update_ausente_ou_antigo")
                    continue
                grupos, erros_grupos = _agrupar_apostas(_apostas(provedor))
                if erros_grupos:
                    motivos.extend(erros_grupos)
                    continue
                if not grupos:
                    motivos.append("apostas_over_under_ausentes")
                    continue

                for (linha, base), lados in grupos.items():
                    if set(lados) != {"over", "under"}:
                        motivos.append("par_over_under_incompleto")
                        continue
                    resumo_lados = {}
                    erro_par = False
                    for lado, aposta in lados.items():
                        aposta_id = _identificador(_campo(aposta, "Id"))
                        preco = _numero(_campo(aposta, "Price"))
                        status = _identificador(_campo(aposta, "Status"))
                        atualizado, atualizacao_coerente = (
                            _atualizacao_coerente(
                                _campo(aposta, "LastUpdate"),
                                instante_snapshot,
                            )
                        )
                        if aposta_id is None:
                            motivos.append("bet_id_ausente")
                            erro_par = True
                        if preco is None or not 1 < preco <= 1000:
                            motivos.append("odd_decimal_invalida")
                            erro_par = True
                        if status not in contrato["status_ativos"]:
                            motivos.append("status_aposta_nao_comprovado_ativo")
                            erro_par = True
                        if not atualizacao_coerente:
                            motivos.append(
                                "last_update_invalido_antigo_ou_futuro"
                            )
                            erro_par = True
                        resumo_lados[lado] = {
                            "bet_id": aposta_id,
                            "odd": preco,
                            "status": status,
                            "last_update": atualizado,
                        }
                    if erro_par:
                        continue
                    ofertas.append({
                        **contexto,
                        "market_id": mercado_id,
                        "mercado": nome_mercado,
                        "provider_id": provedor_id,
                        "provider": provedor_nome,
                        "snapshot_em": (
                            instante_snapshot.isoformat()
                            if instante_snapshot is not None else None
                        ),
                        "provider_last_update": provider_atualizado,
                        "linha": linha,
                        "baseline": base,
                        "over": resumo_lados["over"],
                        "under": resumo_lados["under"],
                    })
    if mercados_2t == 0:
        motivos.append("mercado_2t_cantos_over_under_nao_encontrado")
    return ofertas, motivos, mercados_2t


def _avaliar_liquidacao(payload, ofertas, contrato):
    if not isinstance(payload, dict):
        return [], ["liquidacao_ausente"]
    comprovacoes = []
    motivos = []
    cabecalho = _cabecalho(payload) or {}
    tipo_mensagem = _identificador(_campo(cabecalho, "Type"))
    instante_liquidacao = _instante_mensagem(payload)
    if tipo_mensagem != TIPO_MENSAGEM_LIQUIDACAO:
        motivos.append("tipo_mensagem_liquidacao_nao_e_35")
    if instante_liquidacao is None:
        motivos.append("timestamp_mensagem_liquidacao_ausente_ou_invalido")
    if (
        tipo_mensagem != TIPO_MENSAGEM_LIQUIDACAO
        or instante_liquidacao is None
    ):
        return [], motivos
    ofertas_por_chave = {
        (
            oferta["fixture_id"],
            oferta["market_id"],
            oferta["linha"],
            oferta["baseline"],
            oferta["over"]["bet_id"],
            oferta["under"]["bet_id"],
        ): oferta
        for oferta in ofertas
    }
    mercados_2t = 0
    for evento in _eventos(payload):
        fixture_id = _identificador(_campo(evento, "FixtureId"))
        mercados = _lista_entidades(evento, "Markets", "Market")
        for mercado in mercados:
            nome_mercado = str(_campo(mercado, "Name", "") or "").strip()
            if not _mercado_2t_cantos(nome_mercado):
                continue
            mercados_2t += 1
            market_id = _identificador(_campo(mercado, "Id"))
            grupos, erros = _agrupar_apostas(_apostas(mercado))
            if erros:
                motivos.extend(erros)
                continue
            for (linha, base), lados in grupos.items():
                if set(lados) != {"over", "under"}:
                    motivos.append("liquidacao_over_under_incompleta")
                    continue
                over_id = _identificador(_campo(lados["over"], "Id"))
                under_id = _identificador(_campo(lados["under"], "Id"))
                chave = (
                    fixture_id,
                    market_id,
                    linha,
                    base,
                    over_id,
                    under_id,
                )
                if chave not in ofertas_por_chave:
                    motivos.append("liquidacao_nao_corresponde_a_oferta")
                    continue
                oferta = ofertas_por_chave[chave]
                instante_oferta = _instante_iso(oferta.get("snapshot_em"))
                if (
                    instante_oferta is None
                    or instante_liquidacao <= instante_oferta
                ):
                    motivos.append("liquidacao_nao_e_posterior_a_oferta")
                    continue
                status_over = _identificador(
                    _campo(lados["over"], "Status")
                )
                status_under = _identificador(
                    _campo(lados["under"], "Status")
                )
                if not (
                    status_over == contrato["status_liquidado"]
                    and status_under == contrato["status_liquidado"]
                ):
                    motivos.append("status_liquidacao_invalido")
                    continue
                resultado_over = _identificador(
                    _campo(lados["over"], "Settlement")
                )
                resultado_under = _identificador(
                    _campo(lados["under"], "Settlement")
                )
                resultado_normal = (
                    resultado_over in contrato["vencedores"]
                    and resultado_under in contrato["perdedores"]
                ) or (
                    resultado_under in contrato["vencedores"]
                    and resultado_over in contrato["perdedores"]
                )
                resultado_push = bool(contrato["reembolsos"]) and (
                    resultado_over in contrato["reembolsos"]
                    and resultado_under in contrato["reembolsos"]
                )
                if not (resultado_normal or resultado_push):
                    motivos.append("resultado_liquidacao_incompativel")
                    continue
                atualizado_over, coerente_over = _atualizacao_coerente(
                    _campo(lados["over"], "LastUpdate"),
                    instante_liquidacao,
                )
                atualizado_under, coerente_under = _atualizacao_coerente(
                    _campo(lados["under"], "LastUpdate"),
                    instante_liquidacao,
                )
                if not coerente_over or not coerente_under:
                    motivos.append(
                        "last_update_liquidacao_invalido_antigo_ou_futuro"
                    )
                    continue
                comprovacoes.append({
                    "fixture_id": fixture_id,
                    "market_id": market_id,
                    "mercado": nome_mercado,
                    "liquidacao_em": instante_liquidacao.isoformat(),
                    "linha": linha,
                    "baseline": base,
                    "over": {
                        "bet_id": over_id,
                        "settlement": resultado_over,
                        "last_update": atualizado_over,
                    },
                    "under": {
                        "bet_id": under_id,
                        "settlement": resultado_under,
                        "last_update": atualizado_under,
                    },
                    "tipo_resultado": "push" if resultado_push else "win_loss",
                })
    if mercados_2t == 0:
        motivos.append("mercado_2t_ausente_na_liquidacao")
    return comprovacoes, motivos


def gerar_relatorio(
    documento,
    *,
    gerado_em=None,
    entrada_sha256=None,
    entrada_bytes=None,
):
    documento = documento if isinstance(documento, dict) else {}
    snapshot = _campo(documento, "snapshot")
    liquidacao = _campo(documento, "liquidacao")
    contrato_bruto = _campo(documento, "contrato")
    contrato, erros_contrato = _contrato_validado(contrato_bruto)

    motivos = list(erros_contrato)
    ofertas = []
    mercados_encontrados = 0
    if not isinstance(snapshot, dict):
        motivos.append("snapshot_ausente")
    elif erros_contrato:
        # O conteúdo ainda é varrido para diferenciar ausência de mercado de
        # falta de metadados contratuais, mas nunca comprova uma oferta.
        _, motivos_oferta, mercados_encontrados = _avaliar_ofertas(
            snapshot, contrato
        )
        motivos.extend(motivos_oferta)
    else:
        ofertas, motivos_oferta, mercados_encontrados = _avaliar_ofertas(
            snapshot, contrato
        )
        motivos.extend(motivos_oferta)

    liquidacoes = []
    if ofertas:
        liquidacoes, motivos_liquidacao = _avaliar_liquidacao(
            liquidacao, ofertas, contrato
        )
        motivos.extend(motivos_liquidacao)
    elif not isinstance(liquidacao, dict):
        motivos.append("liquidacao_ausente")

    contagem_motivos = Counter(motivos)
    oferta_comprovada = bool(ofertas) and not erros_contrato
    liquidacao_comprovada = bool(liquidacoes) and oferta_comprovada
    gerado_em = gerado_em or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    return {
        "versao": VERSAO_DIAGNOSTICO,
        "gerado_em": gerado_em,
        "fonte_candidata": "LSports OddsService",
        "modo": "offline_somente_leitura",
        "requisicoes_realizadas": 0,
        "evidencia_entrada": {
            "sha256": entrada_sha256,
            "bytes": entrada_bytes,
            "payload_bruto_persistido": False,
        },
        "mercados_2t_estruturais_encontrados": mercados_encontrados,
        "ofertas_validas": len(ofertas),
        "liquidacoes_validas": len(liquidacoes),
        "oferta_real_comprovada": oferta_comprovada,
        "liquidacao_comprovada": liquidacao_comprovada,
        "apto_apenas_integracao_sombra": liquidacao_comprovada,
        "habilita_integracao_automatica": False,
        "mapeamento_status": {
            "origem_informada": bool(contrato["origem"]),
            "origem_sha256": contrato["origem_sha256"],
            "formato_preco": contrato["formato_preco"] or None,
            "status_ativos": sorted(contrato["status_ativos"]),
            "status_liquidado": contrato["status_liquidado"],
            "settlement_vencedor": sorted(contrato["vencedores"]),
            "settlement_perdedor": sorted(contrato["perdedores"]),
            "settlement_reembolso": sorted(contrato["reembolsos"]),
        },
        "ofertas": ofertas[:50],
        "liquidacoes": liquidacoes[:50],
        "motivos_bloqueio": [
            {"motivo": motivo, "ocorrencias": contagem_motivos[motivo]}
            for motivo in sorted(contagem_motivos)
        ],
        "observacao": (
            "O diagnóstico nunca ativa a fonte. Mesmo com oferta e "
            "liquidação comprovadas, o próximo estágio permitido é sombra."
        ),
    }


def carregar_amostra_com_proveniencia(caminho):
    caminho = Path(caminho)
    try:
        conteudo = caminho.read_bytes()
    except OSError as erro:
        raise ValueError("Não foi possível ler a amostra LSports") from erro
    if len(conteudo) > LIMITE_AMOSTRA_BYTES:
        raise ValueError("Amostra excede o limite seguro de 25 MB")
    try:
        documento = json.loads(conteudo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise ValueError("Amostra LSports não é JSON válido") from erro
    if not isinstance(documento, dict):
        raise ValueError("Amostra LSports precisa ser um objeto JSON")
    return documento, {
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "bytes": len(conteudo),
    }


def carregar_amostra(caminho):
    documento, _ = carregar_amostra_com_proveniencia(caminho)
    return documento


def salvar_relatorio(relatorio, caminho=ARQUIVO_RELATORIO):
    caminho = Path(caminho)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(caminho)
    return caminho


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Valida offline uma amostra LSports de escanteios Over/Under 2T."
        )
    )
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, default=ARQUIVO_RELATORIO)
    argumentos = parser.parse_args()
    try:
        documento, proveniencia = carregar_amostra_com_proveniencia(
            argumentos.entrada
        )
        relatorio = gerar_relatorio(
            documento,
            entrada_sha256=proveniencia["sha256"],
            entrada_bytes=proveniencia["bytes"],
        )
        caminho = salvar_relatorio(relatorio, argumentos.saida)
    except (OSError, ValueError) as erro:
        raise SystemExit(str(erro)) from erro
    print(
        "Diagnóstico LSports 2T concluído sem rede. "
        f"Ofertas válidas={relatorio['ofertas_validas']} | "
        f"liquidações válidas={relatorio['liquidacoes_validas']} | "
        f"relatório={caminho}"
    )
    print("A fonte permanece desligada; integração automática=false.")


if __name__ == "__main__":
    main()
