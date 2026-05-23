"""
Módulo 3 — Information Coefficient (IC) com excess return vs SMLL.

Calcula IC por fator, IC rolling 26 semanas e correlação momentum × tendência.
DIAGNOSTIC_SPEC §5.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src import scoring
from src.benchmarks import retorno_benchmark_periodo

# Fatores presentes na estrutura de scoring.py
# Nota: spec usa "cagr", código real usa "cagr_receita"
_FATORES = ["momentum", "tendencia", "roic", "cagr_receita", "score_final"]


def _get_score_normalizado(entrada: dict, fator: str) -> float | None:
    """Extrai valor normalizado de um fator do dict de scores."""
    if fator == "score_final":
        return entrada.get("score_final")
    fatores = entrada.get("fatores", {})
    bloco = fatores.get(fator, {})
    return bloco.get("normalizado")


def _computar_excess_returns(
    semana: dict,
    df_precos: pd.DataFrame,
    bench_df: pd.DataFrame,
    todos_tickers: list[str],
) -> tuple[dict[str, float], float]:
    """
    Retorna (excess_returns_dict, ret_smll_semana).
    excess_returns[ticker] = retorno_bruto_ticker - ret_smll
    """
    data_inicio = date.fromisoformat(semana["data_formacao"])
    data_fim = date.fromisoformat(semana["data_vigencia_fim"])

    ret_smll = retorno_benchmark_periodo(bench_df, "smll", data_inicio, data_fim)

    # Pré-filtra por faixa de datas (evita pandas filter por ticker 50x)
    mask = (
        (df_precos["date"].dt.date >= data_inicio) &
        (df_precos["date"].dt.date <= data_fim)
    )
    df_janela = df_precos[mask]

    # Também precisamos do preço no data_inicio (último pregão ≤ data_formacao)
    mask_antes = df_precos["date"].dt.date <= data_inicio
    df_antes = df_precos[mask_antes]

    excess: dict[str, float] = {}
    for ticker in todos_tickers:
        ent = df_antes[df_antes["ticker"] == ticker]["adj_close"]
        sai = df_janela[df_janela["ticker"] == ticker]["adj_close"]
        if ent.empty or sai.empty:
            continue
        ret_bruto = float(sai.iloc[-1]) / float(ent.iloc[-1]) - 1
        excess[ticker] = ret_bruto - ret_smll

    return excess, ret_smll


def calcular_ic_por_fator(
    backtest_carteiras: dict,
    df_precos: pd.DataFrame,
    universo: list[dict],
    bench_df: pd.DataFrame,
) -> dict[str, dict]:
    """
    Para cada semana: correlação de Spearman entre score normalizado
    de cada fator e excess return vs SMLL.

    Recomputa scores históricos via scoring.calcular_scores()
    (não depende de arquivos historico/scores_*.json).
    """
    todos_tickers = [t["ticker_b3"] for t in universo]
    ic_series: dict[str, list[dict]] = {f: [] for f in _FATORES}

    for semana in backtest_carteiras["carteiras"]:
        data_corte = date.fromisoformat(semana["data_corte_dados"])

        # Recalcula scores com anti-look-ahead garantido
        try:
            scores_semana = scoring.calcular_scores(df_precos, universo, data_corte)
        except AssertionError:
            continue

        # Excess returns de todas as 50 ações vs SMLL
        excess, _ = _computar_excess_returns(semana, df_precos, bench_df, todos_tickers)

        if len(excess) < 20:
            continue

        # Score dict para lookup rápido
        score_map = {s["ticker"]: s for s in scores_semana}

        for fator in _FATORES:
            scores_v, retornos = [], []
            for ticker, exc_ret in excess.items():
                entrada = score_map.get(ticker)
                if entrada is None:
                    continue
                val = _get_score_normalizado(entrada, fator)
                if val is None:
                    continue
                scores_v.append(val)
                retornos.append(exc_ret)

            if len(scores_v) < 10:
                continue

            ic, _ = spearmanr(scores_v, retornos)
            ic_series[fator].append({
                "semana": semana["semana"],
                "ic": float(ic) if not np.isnan(ic) else 0.0,
            })

    resumo: dict[str, dict] = {}
    for fator, series in ic_series.items():
        ics = [x["ic"] for x in series]
        if not ics:
            resumo[fator] = {"ic_medio": 0.0, "ic_mediano": 0.0,
                             "ic_positivo_pct": 0.0, "ic_std": 0.0,
                             "ir": 0.0, "n_semanas": 0, "series": []}
            continue
        ic_mean = float(np.mean(ics))
        ic_std = float(np.std(ics))
        resumo[fator] = {
            "ic_medio": round(ic_mean, 6),
            "ic_mediano": round(float(np.median(ics)), 6),
            "ic_positivo_pct": round(sum(1 for x in ics if x > 0) / len(ics), 4),
            "ic_std": round(ic_std, 6),
            "ir": round(ic_mean / ic_std, 4) if ic_std > 0 else 0.0,
            "n_semanas": len(ics),
            "series": series,
        }

    return resumo


def calcular_ic_rolling(
    resumo_ic: dict[str, dict],
    janela: int = 26,
) -> dict[str, dict]:
    """
    IC médio rolling de `janela` semanas por fator.
    Detecta se poder preditivo está subindo ou caindo.
    """
    resultado: dict[str, dict] = {}

    for fator, dados in resumo_ic.items():
        series = dados.get("series", [])
        ics = [x["ic"] for x in series]
        datas = [x["semana"] for x in series]

        if len(ics) < janela:
            resultado[fator] = {
                "rolling": [],
                "tendencia_recente": "insuficiente",
            }
            continue

        rolling = [
            {
                "semana": datas[i],
                "ic_rolling": round(float(np.mean(ics[i - janela: i])), 6),
            }
            for i in range(janela, len(ics))
        ]

        # Tendência: últimos 13 períodos rolling vs os 13 anteriores
        if len(rolling) >= 13:
            ic_recente = float(np.mean([r["ic_rolling"] for r in rolling[-13:]]))
            ic_anterior = float(np.mean([r["ic_rolling"] for r in rolling[-26:-13]])) if len(rolling) >= 26 else ic_recente
            tendencia = "subindo" if ic_recente > ic_anterior else "caindo"
        else:
            tendencia = "insuficiente"

        resultado[fator] = {
            "rolling": rolling,
            "tendencia_recente": tendencia,
        }

    return resultado


def calcular_correlacao_momentum_tendencia(
    backtest_carteiras: dict,
    df_precos: pd.DataFrame,
    universo: list[dict],
) -> dict[str, Any]:
    """
    Correlação de Spearman entre score normalizado de momentum e tendência
    para as 50 ações por semana. Média sobre todas as semanas.

    Adapta spec: recalcula scores em vez de ler arquivos históricos.
    """
    correlacoes: list[float] = []

    for semana in backtest_carteiras["carteiras"]:
        data_corte = date.fromisoformat(semana["data_corte_dados"])

        try:
            scores_semana = scoring.calcular_scores(df_precos, universo, data_corte)
        except AssertionError:
            continue

        mom = [
            s["fatores"]["momentum"]["normalizado"]
            for s in scores_semana
            if s["fatores"]["momentum"]["normalizado"] is not None
        ]
        tend = [
            s["fatores"]["tendencia"]["normalizado"]
            for s in scores_semana
            if s["fatores"]["tendencia"]["normalizado"] is not None
        ]

        # Alinhar por ticker
        mom_map = {
            s["ticker"]: s["fatores"]["momentum"]["normalizado"]
            for s in scores_semana
        }
        tend_map = {
            s["ticker"]: s["fatores"]["tendencia"]["normalizado"]
            for s in scores_semana
        }
        tickers_com_ambos = [
            t for t in mom_map
            if mom_map[t] is not None and tend_map.get(t) is not None
        ]

        if len(tickers_com_ambos) < 10:
            continue

        mom_vals = [mom_map[t] for t in tickers_com_ambos]
        tend_vals = [tend_map[t] for t in tickers_com_ambos]

        corr, _ = spearmanr(mom_vals, tend_vals)
        if not np.isnan(corr):
            correlacoes.append(float(corr))

    if not correlacoes:
        return {
            "correlacao_media": 0.0,
            "correlacao_mediana": 0.0,
            "pct_acima_065": 0.0,
            "interpretacao": "Sem dados suficientes",
        }

    media = float(np.mean(correlacoes))
    return {
        "correlacao_media": round(media, 4),
        "correlacao_mediana": round(float(np.median(correlacoes)), 4),
        "pct_acima_065": round(
            sum(1 for c in correlacoes if c > 0.65) / len(correlacoes), 4
        ),
        "n_semanas": len(correlacoes),
        "interpretacao": (
            "REDUNDANTES — momentum e tendencia medem essencialmente o mesmo sinal"
            if media > 0.65
            else "COMPLEMENTARES — momentum e tendencia adicionam informacao distinta"
        ),
    }
