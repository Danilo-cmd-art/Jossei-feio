"""
Fase 3 — Carteira teórica.

Formação, freeze semanal, performance e bootstrap retroativo.
PHASE3_SPEC §6-8, PHASE2_SPEC §18.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd

import config
from src import scoring, benchmarks
from src.logger import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Calendário de pregões (referência PETR4)
# ---------------------------------------------------------------------------

def obter_pregoes(df_precos: pd.DataFrame) -> list[date]:
    """Retorna lista ordenada de datas de pregão a partir dos dados de PETR4 ou qualquer ticker."""
    ref = "PETR4"
    if ref in df_precos["ticker"].values:
        df_ref = df_precos[df_precos["ticker"] == ref]
    else:
        df_ref = df_precos

    datas = sorted(df_ref["date"].dt.date.unique())
    return datas


def ultimo_pregao_antes(data_alvo: date, pregoes: list[date]) -> date | None:
    """Retorna o último pregão estritamente antes de data_alvo."""
    anteriores = [d for d in pregoes if d < data_alvo]
    return anteriores[-1] if anteriores else None


def primeiro_pregao_da_semana(data_ref: date, pregoes: list[date]) -> date | None:
    """Retorna o primeiro pregão da semana ISO de data_ref."""
    segunda = data_ref - timedelta(days=data_ref.weekday())
    sexta = segunda + timedelta(days=4)
    da_semana = [d for d in pregoes if segunda <= d <= sexta]
    return da_semana[0] if da_semana else None


def ultimo_pregao_da_semana(data_ref: date, pregoes: list[date]) -> date | None:
    """Retorna o último pregão da semana ISO de data_ref."""
    segunda = data_ref - timedelta(days=data_ref.weekday())
    sexta = segunda + timedelta(days=4)
    da_semana = [d for d in pregoes if segunda <= d <= sexta]
    return da_semana[-1] if da_semana else None


# ---------------------------------------------------------------------------
# Formação da carteira
# ---------------------------------------------------------------------------

def formar_carteira(
    scores: list[dict],
    data_corte: date,
    df_precos: pd.DataFrame,
) -> list[dict]:
    """
    Seleciona Top-N tickers com filtro de tendência ≥ 2.
    Desempate: maior momentum_bruto, depois ordem alfabética.
    """
    aprovados = [s for s in scores if s["passou_filtro_tendencia"]]

    # Ordenação: score desc, momentum desc, ticker asc
    aprovados.sort(key=lambda s: (
        -s["score_final"],
        -(s.get("momentum_bruto") or -999),
        s["ticker"],
    ))

    selecionados = aprovados[:config.N_POSICOES_CARTEIRA_ALVO]
    n = len(selecionados)
    peso = 1 / n if n > 0 else 0.0

    # Preço de entrada = adj_close na data_corte
    def preco_em(ticker: str, data: date) -> float | None:
        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"].dt.date <= data)
        ].sort_values("date")
        if df_t.empty:
            return None
        return float(df_t["adj_close"].iloc[-1])

    tickers_carteira = []
    for s in selecionados:
        p_entrada = preco_em(s["ticker"], data_corte)
        tickers_carteira.append({
            "ticker": s["ticker"],
            "rank_na_formacao": s["rank"],
            "score_na_formacao": round(s["score_final"], 4),
            "preco_entrada": p_entrada,
            "preco_atual": p_entrada,
            "retorno_acumulado": 0.0,
            "is_stale": False,
            "peso": round(peso, 6),
        })

    return tickers_carteira


def calcular_performance_diaria(
    tickers_carteira: list[dict],
    data_corte: date,
    df_precos: pd.DataFrame,
    pregoes: list[date],
) -> list[dict]:
    """
    Calcula retorno diário e acumulado da carteira desde data_corte.
    Preço base = adj_close em data_corte.
    """
    datas_perf = [d for d in pregoes if d > data_corte]
    if not datas_perf:
        return []

    # Preços base
    precos_base: dict[str, float] = {}
    for t in tickers_carteira:
        ticker = t["ticker"]
        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"].dt.date <= data_corte)
        ].sort_values("date")
        if not df_t.empty:
            precos_base[ticker] = float(df_t["adj_close"].iloc[-1])

    serie: list[dict] = []
    for data in datas_perf:
        retornos_dia: list[float] = []
        for t in tickers_carteira:
            ticker = t["ticker"]
            base = precos_base.get(ticker)
            if base is None or base == 0:
                continue
            df_t = df_precos[
                (df_precos["ticker"] == ticker) &
                (df_precos["date"].dt.date <= data)
            ].sort_values("date")
            if df_t.empty:
                continue
            preco_atual = float(df_t["adj_close"].iloc[-1])
            ret_acum = preco_atual / base - 1
            retornos_dia.append(ret_acum)

        if not retornos_dia:
            continue

        ret_acum_carteira = sum(retornos_dia) / len(retornos_dia)

        # Retorno do dia = variação em relação ao dia anterior
        if serie:
            ret_dia = ret_acum_carteira - serie[-1]["retorno_acumulado"]
        else:
            ret_dia = ret_acum_carteira

        serie.append({
            "data": data.isoformat(),
            "retorno_dia": round(ret_dia, 6),
            "retorno_acumulado": round(ret_acum_carteira, 6),
        })

    return serie


# ---------------------------------------------------------------------------
# Bootstrap retroativo — PHASE2_SPEC §18
# ---------------------------------------------------------------------------

def executar_bootstrap(
    df_precos: pd.DataFrame,
    universo: list[dict],
    hoje: date,
) -> dict:
    """
    Constrói carteira retroativa da semana corrente.
    data_corte = último pregão antes da segunda desta semana.
    GARANTIA: assertion anti-look-ahead em calcular_scores.
    """
    pregoes = obter_pregoes(df_precos)

    segunda_semana = hoje - timedelta(days=hoje.weekday())
    data_corte = ultimo_pregao_antes(segunda_semana, pregoes)

    if data_corte is None:
        raise RuntimeError("Não foi possível determinar data de corte para bootstrap")

    log.info(f"Bootstrap: segunda={segunda_semana}, data_corte={data_corte}, hoje={hoje}")

    # Scores calculados APENAS com dados ≤ data_corte
    scores = scoring.calcular_scores(df_precos, universo, data_corte)
    tickers_carteira = formar_carteira(scores, data_corte, df_precos)

    # Performance desde data_corte até hoje
    performance = calcular_performance_diaria(tickers_carteira, data_corte, df_precos, pregoes)

    # Atualiza preço_atual e retorno_acumulado
    if performance:
        ret_total = performance[-1]["retorno_acumulado"]
    else:
        ret_total = 0.0

    for t in tickers_carteira:
        ticker = t["ticker"]
        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"].dt.date <= hoje)
        ].sort_values("date")
        if not df_t.empty:
            preco_atual = float(df_t["adj_close"].iloc[-1])
            base = t.get("preco_entrada") or 0
            t["preco_atual"] = preco_atual
            t["retorno_acumulado"] = round(preco_atual / base - 1, 6) if base else 0.0

    # Vigência: do início da semana até sexta
    data_vigencia_fim = ultimo_pregao_da_semana(hoje, pregoes) or hoje

    n = len(tickers_carteira)
    carteira = {
        "metadata": {
            "data_formacao": segunda_semana.isoformat(),
            "data_corte_dados": data_corte.isoformat(),
            "data_vigencia_inicio": segunda_semana.isoformat(),
            "data_vigencia_fim": data_vigencia_fim.isoformat(),
            "bootstrap_retroativo": True,
            "n_posicoes": n,
            "peso_por_posicao": round(1 / n, 6) if n > 0 else 0.0,
            "proxima_carteira_oficial": (segunda_semana + timedelta(weeks=1)).isoformat(),
        },
        "tickers": tickers_carteira,
        "performance_diaria": performance,
        "retorno_acumulado_total": round(ret_total, 6),
    }

    return carteira


# ---------------------------------------------------------------------------
# Ciclo regular (segunda-feira)
# ---------------------------------------------------------------------------

def deve_formar_nova_carteira(carteira_json: dict | None, hoje: date) -> bool:
    """Retorna True se devemos formar nova carteira hoje."""
    if carteira_json is None:
        return True
    data_fim_str = carteira_json.get("metadata", {}).get("data_vigencia_fim")
    if not data_fim_str:
        return True
    data_fim = date.fromisoformat(data_fim_str)
    if hoje > data_fim:
        return True
    return False


def atualizar_carteira(
    carteira_json: dict,
    df_precos: pd.DataFrame,
    pregoes: list[date],
    hoje: date,
    benchmarks_df: pd.DataFrame | None,
) -> dict:
    """Atualiza preços e performance da carteira ativa sem reformar."""
    data_corte = date.fromisoformat(carteira_json["metadata"]["data_corte_dados"])
    tickers_carteira = carteira_json["tickers"]

    performance = calcular_performance_diaria(tickers_carteira, data_corte, df_precos, pregoes)

    ret_total = performance[-1]["retorno_acumulado"] if performance else 0.0

    # Adiciona benchmarks à performance diária
    if benchmarks_df is not None and not benchmarks_df.empty:
        for entrada in performance:
            data_d = date.fromisoformat(entrada["data"])
            entrada["benchmarks"] = {
                "ibov": benchmarks.retorno_benchmark_periodo(benchmarks_df, "ibov", data_corte, data_d),
                "smll": benchmarks.retorno_benchmark_periodo(benchmarks_df, "smll", data_corte, data_d),
                "cdi": benchmarks.retorno_benchmark_periodo(benchmarks_df, "cdi", data_corte, data_d),
            }

    for t in tickers_carteira:
        ticker = t["ticker"]
        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"].dt.date <= hoje)
        ].sort_values("date")
        if not df_t.empty:
            preco_atual = float(df_t["adj_close"].iloc[-1])
            base = t.get("preco_entrada") or 0
            t["preco_atual"] = preco_atual
            t["retorno_acumulado"] = round(preco_atual / base - 1, 6) if base else 0.0

    carteira_json["performance_diaria"] = performance
    carteira_json["retorno_acumulado_total"] = round(ret_total, 6)
    return carteira_json


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def salvar_scores(scores: list[dict], data_ref: date, data_corte: date, universo_versao: str) -> None:
    """Salva scores_atual.json e histórico diário."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": {
            "data_referencia": data_ref.isoformat(),
            "data_corte_dados": data_corte.isoformat(),
            "total_tickers": len(scores),
            "universo_versao": universo_versao,
        },
        "scores": scores,
    }

    with open(config.SCORES_ATUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    hist_path = config.HISTORICO_DIR / f"scores_{data_ref.isoformat()}.json"
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Scores salvos: {config.SCORES_ATUAL_PATH}")


def salvar_carteira(carteira: dict) -> None:
    """Salva carteira_atual.json e histórico semanal."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    with open(config.CARTEIRA_ATUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(carteira, f, ensure_ascii=False, indent=2, default=str)

    data_formacao = date.fromisoformat(carteira["metadata"]["data_formacao"])
    semana = data_formacao.strftime("%Y-W%V")
    hist_path = config.HISTORICO_DIR / f"carteira_{semana}.json"
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(carteira, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Carteira salva: {config.CARTEIRA_ATUAL_PATH}")


# ---------------------------------------------------------------------------
# Entrypoint Fase 3
# ---------------------------------------------------------------------------

def run(df_precos: pd.DataFrame, universo: list[dict], universo_versao: str) -> dict:
    """Executa Fase 3 completa."""
    log.info("=== FASE 3: Scoring e Carteira ===")
    hoje = date.today()
    pregoes = obter_pregoes(df_precos)

    # Carrega carteira existente (se houver)
    carteira_existente = None
    if config.CARTEIRA_ATUAL_PATH.exists():
        with open(config.CARTEIRA_ATUAL_PATH, encoding="utf-8") as f:
            carteira_existente = json.load(f)

    # Benchmarks
    inicio_janela = hoje - timedelta(days=400)
    bench_df = benchmarks.ler_benchmarks()
    if bench_df is None:
        bench_df = benchmarks.carregar_benchmarks(inicio_janela, hoje)
        if not bench_df.empty:
            benchmarks.salvar_benchmarks(bench_df)

    # É bootstrap (primeira vez) ou ciclo regular?
    eh_bootstrap = carteira_existente is None

    if eh_bootstrap:
        log.info("Modo Bootstrap: formando carteira retroativa da semana corrente")
        carteira = executar_bootstrap(df_precos, universo, hoje)

        # Scores com data_corte do bootstrap
        data_corte = date.fromisoformat(carteira["metadata"]["data_corte_dados"])
        scores = scoring.calcular_scores(df_precos, universo, data_corte)
        salvar_scores(scores, hoje, data_corte, universo_versao)
        salvar_carteira(carteira)

    elif deve_formar_nova_carteira(carteira_existente, hoje):
        log.info("Formando nova carteira (segunda-feira)")
        data_corte = ultimo_pregao_antes(hoje, pregoes)
        scores = scoring.calcular_scores(df_precos, universo, data_corte)

        tickers_carteira = formar_carteira(scores, data_corte, df_precos)
        data_vigencia_fim = ultimo_pregao_da_semana(hoje, pregoes) or hoje
        n = len(tickers_carteira)

        carteira = {
            "metadata": {
                "data_formacao": hoje.isoformat(),
                "data_corte_dados": data_corte.isoformat(),
                "data_vigencia_inicio": hoje.isoformat(),
                "data_vigencia_fim": data_vigencia_fim.isoformat(),
                "bootstrap_retroativo": False,
                "n_posicoes": n,
                "peso_por_posicao": round(1 / n, 6) if n > 0 else 0.0,
            },
            "tickers": tickers_carteira,
            "performance_diaria": [],
            "retorno_acumulado_total": 0.0,
        }

        salvar_scores(scores, hoje, data_corte, universo_versao)
        salvar_carteira(carteira)

    else:
        log.info("Atualizando performance da carteira ativa")
        data_corte = date.fromisoformat(carteira_existente["metadata"]["data_corte_dados"])
        scores = scoring.calcular_scores(df_precos, universo, data_corte)
        salvar_scores(scores, hoje, data_corte, universo_versao)

        carteira = atualizar_carteira(carteira_existente, df_precos, pregoes, hoje, bench_df)
        salvar_carteira(carteira)

    log.info("=== FASE 3 CONCLUÍDA ===")
    return carteira
