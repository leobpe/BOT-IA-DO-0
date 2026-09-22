"""Entrega compacta das melhores seleções pré-live confirmadas."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from filtro_pre_live_preciso import filtrar_bilhetes_pre_live_precisos
from resumo_forca_sinais import resumo_forca_pre_live


def _transporte_padrao(url, dados):
    requisicao = Request(
        url, data=urlencode(dados).encode("utf-8"), method="POST"
    )
    with urlopen(requisicao, timeout=15) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


ROTULOS_MERCADOS = {
    "resultado": "Resultado",
    "chance_dupla": "Chance dupla",
    "chance_dupla_mais_gols": "Chance dupla + gols",
    "total_gols": "Total de gols",
    "ambas_marcam": "Ambas marcam",
    "resultado_mais_gols": "Resultado + gols",
    "resultado_mais_ambas": "Resultado + ambas marcam",
    "total_gols_mais_ambas": "Total de gols + ambas marcam",
    "multigols": "Multigols",
    "time_marca_gol": "Time marca gol",
    "multigols_time": "Multigols do time",
}


def _texto_selecao(valor):
    texto = str(valor or "-").replace("|", " + ").replace("_", " ")
    substituicoes = {
        "mandante": "casa",
        "visitante": "fora",
        "empate": "empate",
        "ou": "ou",
        "over": "mais de",
        "under": "menos de",
        "sim": "sim",
        "nao": "não",
    }
    return " ".join(substituicoes.get(item, item) for item in texto.split())


def _horario(inicio):
    try:
        return datetime.fromisoformat(str(inicio)).strftime("%H:%M")
    except (TypeError, ValueError):
        return None


def mensagem_bilhete_pre_live(
    bilhete, resultado=None, resultados_pernas=None
):
    pernas = list((bilhete or {}).get("pernas") or [])
    titulos = {
        "green": "✅ GREEN — PRÉ-LIVE",
        "red": "❌ RED — PRÉ-LIVE",
        "anulada": "↩️ ANULADA — PRÉ-LIVE",
    }
    linhas = [
        titulos.get(resultado, "⭐ PRÉ-LIVE — SELEÇÃO CONFIRMADA"), ""
    ]
    resultado_por_posicao = {
        int(item.get("posicao") or 0): item.get("resultado")
        for item in resultados_pernas or []
    }
    icones_pernas = {
        "green": "✅",
        "red": "❌",
        "anulada": "↩️",
        "pendente": "⏳",
    }
    for indice, perna in enumerate(pernas, 1):
        jogo = perna.get("jogo") or {}
        prefixo = f"{indice}. " if len(pernas) > 1 else ""
        resultado_perna = resultado_por_posicao.get(indice)
        icone_resultado = icones_pernas.get(resultado_perna)
        linhas.append(
            f"{(icone_resultado + ' ') if icone_resultado else ''}"
            f"⚽ {prefixo}{jogo.get('mandante') or '-'} x "
            f"{jogo.get('visitante') or '-'}"
        )
        liga = jogo.get("liga")
        horario = _horario(jogo.get("inicio"))
        if liga or horario:
            linhas.append(
                "🏆 " + " | ".join(item for item in (liga, horario) if item)
            )
        mercado = ROTULOS_MERCADOS.get(
            perna.get("mercado"), str(perna.get("mercado") or "Mercado")
        )
        linhas.append(f"🎯 {mercado}: {_texto_selecao(perna.get('selecao'))}")
        linhas.append(
            f"📈 Odd {float(perna.get('odd') or 0):.2f} | "
            f"{perna.get('bookmaker') or bilhete.get('bookmaker') or '-'}"
        )
        linhas.append("")
    linhas.append(f"Odd final: {float(bilhete.get('odd_total') or 0):.2f}")
    linhas.append("✅ Escalações e contexto conferidos.")
    linhas.append(resumo_forca_pre_live(bilhete))
    return "\n".join(linhas)


def _resumo_elencos(bilhetes):
    por_fixture = {}
    for bilhete in bilhetes or []:
        for perna in bilhete.get("pernas") or []:
            fixture_id = perna.get("fixture_id")
            if fixture_id is None or fixture_id in por_fixture:
                continue
            jogadores = ((perna.get("modelo") or {}).get("jogadores") or {})
            lados = [jogadores.get(lado) or {} for lado in (
                "mandante", "visitante"
            )]
            por_fixture[fixture_id] = {
                "confirmada": bool(
                    lados and all(item.get("escalacao_confirmada") for item in lados)
                ),
                "destaques": sum(
                    int(item.get("destaques_titulares") or 0)
                    + int(item.get("destaques_ausentes") or 0)
                    for item in lados
                ),
                "desfalques": sum(
                    int(item.get("desfalques_relevantes") or 0)
                    for item in lados
                ),
            }
    return {
        "jogos": len(por_fixture),
        "escalacoes_confirmadas": sum(
            item["confirmada"] for item in por_fixture.values()
        ),
        "destaques_identificados": sum(
            item["destaques"] for item in por_fixture.values()
        ),
        "desfalques_relevantes": sum(
            item["desfalques"] for item in por_fixture.values()
        ),
    }


def mensagem_lista_preliminar_pre_live(resumo, bilhetes, limite=10):
    """Monta a prévia diária no mesmo formato compacto das entradas oficiais."""
    selecionados = list(bilhetes or [])[:max(int(limite), 0)]
    slot_publicacao = str(resumo.get("slot_publicacao") or "").strip()
    titulo = (
        f"📋 PRÉ-LIVE — LISTA DAS {slot_publicacao}"
        if slot_publicacao else "📋 PRÉ-LIVE — MELHORES DO DIA"
    )
    cobertura = resumo.get("cobertura_analise")
    cobertura_texto = (
        f"{float(cobertura) * 100:.1f}%" if cobertura is not None else "-"
    )
    linhas = [
        titulo,
        "",
        (
            f"📊 {int(resumo.get('jogos_calendario') or 0)} jogos | "
            f"{int(resumo.get('jogos_com_odds_utilizaveis') or 0)} com odds | "
            f"{int(resumo.get('jogos_analisados') or 0)} analisados"
        ),
        (
            f"Candidatos elegíveis: "
            f"{int(resumo.get('candidatos_elegiveis') or 0)} | "
            f"Cobertura: {cobertura_texto} | "
            f"Combinações: {int(resumo.get('bilhetes') or len(bilhetes or []))}"
        ),
        "",
        f"⭐ {len(selecionados)} melhores oportunidades desta análise",
        "",
    ]
    bilhetes_confirmados = 0
    for indice, bilhete in enumerate(selecionados, 1):
        linhas.append(f"{indice}. ⭐ PRÉ-LIVE — CANDIDATA")
        linhas.append("")
        confirmacoes = []
        for perna in bilhete.get("pernas") or []:
            jogo = perna.get("jogo") or {}
            linhas.append(
                f"⚽ {jogo.get('mandante') or '-'} x "
                f"{jogo.get('visitante') or '-'}"
            )
            liga = jogo.get("liga")
            horario = _horario(jogo.get("inicio"))
            if liga or horario:
                linhas.append(
                    "🏆 " + " | ".join(
                        item for item in (liga, horario) if item
                    )
                )
            mercado = ROTULOS_MERCADOS.get(
                perna.get("mercado"), str(perna.get("mercado") or "Mercado")
            )
            linhas.append(
                f"🎯 {mercado}: {_texto_selecao(perna.get('selecao'))}"
            )
            linhas.append(
                f"📈 Odd {float(perna.get('odd') or 0):.2f} | "
                f"{perna.get('bookmaker') or bilhete.get('bookmaker') or '-'}"
            )
            jogadores = ((perna.get("modelo") or {}).get("jogadores") or {})
            lados = [jogadores.get(lado) or {} for lado in (
                "mandante", "visitante"
            )]
            confirmacoes.append(
                bool(lados and all(
                    item.get("escalacao_confirmada") for item in lados
                ))
            )
            linhas.append("")
        linhas.append(f"Odd final: {float(bilhete.get('odd_total') or 0):.2f}")
        if confirmacoes and all(confirmacoes):
            bilhetes_confirmados += 1
            linhas.append("✅ Escalações e contexto conferidos.")
        else:
            linhas.append("🟡 Aguardando escalações e contexto.")
        linhas.append(resumo_forca_pre_live(bilhete, compacto=True))
        linhas.append("")

    elencos = _resumo_elencos(selecionados)
    linhas.extend([
        "👥 RESUMO DAS CONFERÊNCIAS",
        (
            f"Escalações confirmadas: {elencos['escalacoes_confirmadas']}/"
            f"{elencos['jogos']} jogos da lista."
        ),
    ])
    if elencos["destaques_identificados"] or elencos["desfalques_relevantes"]:
        linhas.append(
            f"Destaques identificados: {elencos['destaques_identificados']} | "
            f"Desfalques relevantes: {elencos['desfalques_relevantes']}"
        )
    else:
        linhas.append(
            "Titulares, estrelas e desfalques ainda sem confirmação suficiente."
        )
    linhas.extend([
        "",
        f"✅ Confirmadas agora: {bilhetes_confirmados}/"
        f"{len(selecionados)} entradas da lista.",
        "🟡 As demais permanecem visíveis aguardando confirmação.",
        "⚠️ A lista só será editada para informar GREEN, RED ou anulação.",
    ])
    return "\n".join(linhas)


def publicar_lista_preliminar_pre_live(
    repositorio, resumo, bilhetes, token, canal, limite=10,
    transporte=None, ativo=True,
):
    if not ativo:
        return {"estado": "desativado", "enviados": 0, "editados": 0}
    if not token or not canal:
        return {"estado": "sem_destino", "enviados": 0, "editados": 0}
    bilhetes, ignorados_filtro = filtrar_bilhetes_pre_live_precisos(
        bilhetes,
        caminho_controle=(
            repositorio.caminho.parent / "pre_live_preciso_estado.json"
        ),
    )
    if not bilhetes:
        return {
            "estado": "sem_candidatos_precisos",
            "enviados": 0,
            "editados": 0,
            "ignorados_filtro_preciso": ignorados_filtro,
        }
    transporte = transporte or _transporte_padrao
    data_alvo = str(resumo.get("data_alvo") or "")
    slot_publicacao = str(resumo.get("slot_publicacao") or "").strip()
    if not slot_publicacao:
        iniciado_em = str(resumo.get("iniciado_em") or "")
        try:
            slot_publicacao = datetime.fromisoformat(iniciado_em).strftime(
                "%H:%M"
            )
        except ValueError:
            slot_publicacao = "manual"
    chave_publicacao = f"{data_alvo}|{slot_publicacao}"
    existente = repositorio.obter_lista_preliminar(chave_publicacao, canal)
    if existente:
        return {
            "estado": "ja_enviada_no_horario",
            "enviados": 0,
            "editados": 0,
            "slot_publicacao": slot_publicacao,
        }
    fixtures_publicados = repositorio.listar_fixture_ids_publicados(
        data_alvo, canal
    )
    selecionados = []
    repetidos = 0
    for bilhete in bilhetes or []:
        fixtures = {
            int(perna.get("fixture_id"))
            for perna in bilhete.get("pernas") or []
            if perna.get("fixture_id") is not None
        }
        if fixtures & fixtures_publicados:
            repetidos += 1
            continue
        selecionados.append(bilhete)
        if len(selecionados) >= max(int(limite), 0):
            break
    if not selecionados:
        return {
            "estado": "sem_jogos_novos_no_dia",
            "enviados": 0,
            "editados": 0,
            "ignorados_repetidos": repetidos,
            "slot_publicacao": slot_publicacao,
            "ignorados_filtro_preciso": ignorados_filtro,
        }
    texto = mensagem_lista_preliminar_pre_live(
        resumo, selecionados, limite=len(selecionados)
    )
    conteudo_sha256 = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    resposta = transporte(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {
            "chat_id": canal,
            "text": texto,
            "disable_web_page_preview": "true",
        },
    )
    resultado = (resposta or {}).get("result") or {}
    mensagem_id = resultado.get("message_id")
    chat_id = str((resultado.get("chat") or {}).get("id") or "")
    if not (resposta or {}).get("ok") or mensagem_id is None:
        raise RuntimeError("telegram_lista_sem_confirmacao")
    if chat_id and chat_id != str(canal):
        raise RuntimeError("telegram_lista_canal_divergente")
    repositorio.registrar_lista_preliminar(
        chave_publicacao,
        canal,
        mensagem_id,
        conteudo_sha256,
        conteudo_texto=texto,
        bilhetes=selecionados,
        data_bilhetes=data_alvo,
    )
    return {
        "estado": "enviada",
        "enviados": 1,
        "editados": 0,
        "itens": len(selecionados),
        "ignorados_repetidos": repetidos,
        "ignorados_filtro_preciso": ignorados_filtro,
        "slot_publicacao": slot_publicacao,
    }


def mensagem_lista_preliminar_com_resultados(texto_base, resultados):
    icones = {
        "green": "✅ GREEN",
        "red": "❌ RED",
        "anulada": "↩️ ANULADA",
        None: "⏳ PENDENTE",
    }
    resultados = list(resultados or [])
    greens = sum(item.get("resultado") == "green" for item in resultados)
    reds = sum(item.get("resultado") == "red" for item in resultados)
    anuladas = sum(item.get("resultado") == "anulada" for item in resultados)
    pendentes = sum(item.get("resultado") is None for item in resultados)
    decididas = greens + reds
    acerto = 100.0 * greens / decididas if decididas else None
    resumo = f"✅ {greens} acertos | ❌ {reds} erros"
    if anuladas:
        resumo += f" | ↩️ {anuladas} anulada(s)"
    if pendentes:
        resumo += f" | ⏳ {pendentes} pendente(s)"
    if acerto is not None:
        resumo += f" | 🎯 {acerto:.1f}%"
    linhas = [
        str(texto_base or "").rstrip(),
        "",
        "📊 RESULTADO PRÉ-LIVE",
        resumo,
    ]
    for item in resultados:
        resultado = item.get("resultado")
        linhas.append(
            f"{int(item.get('posicao') or 0)}. "
            f"{icones.get(resultado, '⏳ PENDENTE')}"
        )
        pernas = list(item.get("pernas") or [])
        if pernas:
            icones_compactos = {
                "green": "✅", "red": "❌",
                "anulada": "↩️", "pendente": "⏳",
            }
            linhas.append(
                "   Pernas: " + " ".join(
                    f"{int(perna.get('posicao') or 0)}"
                    f"{icones_compactos.get(perna.get('resultado'), '⏳')}"
                    for perna in pernas
                )
            )
    return "\n".join(linhas)


def editar_resultados_listas_pre_live(
    repositorio, token, transporte=None, limite=20
):
    if not token:
        return {"estado": "desativado", "editados": 0, "falhas": 0}
    transporte = transporte or _transporte_padrao
    itens = repositorio.listar_listas_para_editar(limite=limite)
    editados = falhas = 0
    for item in itens:
        try:
            resposta = transporte(
                f"https://api.telegram.org/bot{token}/editMessageText",
                {
                    "chat_id": item["canal"],
                    "message_id": item["mensagem_id"],
                    "text": mensagem_lista_preliminar_com_resultados(
                        item["conteudo_texto"], item["resultados"]
                    ),
                    "disable_web_page_preview": "true",
                },
            )
            if not (resposta or {}).get("ok"):
                raise RuntimeError("telegram_lista_resultado_sem_confirmacao")
            if repositorio.marcar_lista_resultados_editada(
                item["id"], item["resultado_sha256"]
            ):
                editados += 1
        except Exception:
            falhas += 1
    return {
        "estado": "editado" if editados else "sem_resultados_novos",
        "editados": editados,
        "falhas": falhas,
        "candidatos": len(itens),
    }


def editar_resultados_pre_live(
    repositorio, token, transporte=None, limite=50
):
    if not token:
        return {"estado": "desativado", "editados": 0, "falhas": 0}
    transporte = transporte or _transporte_padrao
    itens = repositorio.listar_entregas_para_editar(limite=limite)
    editados = falhas = 0
    for item in itens:
        try:
            resposta = transporte(
                f"https://api.telegram.org/bot{token}/editMessageText",
                {
                    "chat_id": item["canal"],
                    "message_id": item["mensagem_id"],
                    "text": mensagem_bilhete_pre_live(
                        item["bilhete"], resultado=item["resultado"],
                        resultados_pernas=item["resultados_pernas"],
                    ),
                    "disable_web_page_preview": "true",
                },
            )
            if not (resposta or {}).get("ok"):
                raise RuntimeError("telegram_edicao_sem_confirmacao")
            if repositorio.marcar_entrega_editada(
                item["id"], item["resultado_sha256"]
            ):
                editados += 1
        except Exception:
            falhas += 1
    return {
        "estado": "editado" if editados else "sem_resultados_novos",
        "editados": editados,
        "falhas": falhas,
        "candidatos": len(itens),
    }


def enviar_confirmados_pre_live(
    repositorio, data_alvo, token, canal, maximo_dia=3, transporte=None,
    aplicacao_automatica=True,
):
    if not aplicacao_automatica:
        return {
            "estado": "desativado_modo_sombra",
            "enviados": 0,
            "falhas": 0,
            "candidatos": 0,
            "limite_dia": int(maximo_dia),
        }
    if not token or not canal:
        return {"estado": "desativado", "enviados": 0, "falhas": 0}
    transporte = transporte or _transporte_padrao
    enviados_antes = repositorio.total_entregas(data_alvo, canal)
    restantes = max(int(maximo_dia) - enviados_antes, 0)
    if restantes == 0:
        return {"estado": "limite_diario", "enviados": 0, "falhas": 0}
    candidatos = repositorio.listar_confirmados_para_envio(
        data_alvo, canal, limite=restantes
    )
    bilhetes_filtrados, ignorados_filtro = filtrar_bilhetes_pre_live_precisos(
        [item["bilhete"] for item in candidatos],
        caminho_controle=(
            repositorio.caminho.parent / "pre_live_preciso_estado.json"
        ),
    )
    identidades_aprovadas = {id(bilhete) for bilhete in bilhetes_filtrados}
    candidatos = [
        item for item in candidatos
        if id(item["bilhete"]) in identidades_aprovadas
    ]
    enviados = falhas = 0
    for item in candidatos:
        try:
            resposta = transporte(
                f"https://api.telegram.org/bot{token}/sendMessage",
                {
                    "chat_id": canal,
                    "text": mensagem_bilhete_pre_live(item["bilhete"]),
                    "disable_web_page_preview": "true",
                },
            )
            resultado = (resposta or {}).get("result") or {}
            mensagem_id = resultado.get("message_id")
            chat_id = str((resultado.get("chat") or {}).get("id") or "")
            if not (resposta or {}).get("ok") or mensagem_id is None:
                raise RuntimeError("telegram_sem_confirmacao")
            if chat_id and chat_id != str(canal):
                raise RuntimeError("telegram_canal_divergente")
            if repositorio.registrar_entrega(
                item["id"], canal, mensagem_id
            ):
                enviados += 1
        except Exception:
            falhas += 1
    return {
        "estado": "enviado" if enviados else "sem_confirmados",
        "enviados": enviados,
        "falhas": falhas,
        "candidatos": len(candidatos),
        "ignorados_filtro_preciso": ignorados_filtro,
        "limite_dia": int(maximo_dia),
    }
