"""
Módulo 6 — Variantes de Tendência e Momentum.

Testa T0/T1/T2/T3 (tendência) e M0/M1/M2/M3 (momentum) por IC sobre excess return.
DIAGNOSTIC_SPEC §7.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.benchmarks import retorno_benchmark_periodo
from src.diagnostic_modules.ic import _computar_excess_returns


# ---------------------------------------------------------------------------
# Variantes de tendência
# ---------------------------------------------------------------------------

def calcular_tendencia_variante(df_ticker: pd.DataFrame, variante: str) -> float:
    """
    Recalcula score de tendência com a variante especificada.
    df_ticker deve estar filtrado até data_corte (anti-look-ahead).
    Retorna valor 0-100.
    """
    close = df_ticker["adj_close"].dropna()

    if variante == "T0":
        # MMA50/200 — baseline V1
        if len(close) < 200:
            return float("nan")
        mma50 = float(close.tail(50).mean())
        mma200 = float(close.tail(200).mean())
        preco = float(close.iloc[-1])
        bruto = (1 if preco > mma50 else 0) + (1 if preco > mma200 else 0) + (1 if mma50 > mma200 else 0)
        return (bruto / 3) * 100

    elif variante == "T1":
        # MMA20/50 — baseline V2
        if len(close) < 50:
            return float("nan")
        mma20 = float(close.tail(20).mean())
        mma50 = float(close.tail(50).mean())
        preco = float(close.iloc[-1])
        bruto = (1 if preco > mma20 else 0) + (1 if preco > mma50 else 0) + (1 if mma20 > mma50 else 0)
        return (bruto / 3) * 100

    elif variante == "T2":
        # EMA20/50
        if len(close) < 50:
            return float("nan")
        ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        preco = float(close.iloc[-1])
        bruto = (1 if preco > ema20 else 0) + (1 if preco > ema50 else 0) + (1 if ema20 > ema50 else 0)
        return (bruto / 3) * 100

    elif variante == "T3":
        # Pesos assimétricos: (P>MMA20)×2 + (P>MMA50)×1 + (MMA20>MMA50)×1 → escala 0-4
        if len(close) < 50:
            return float("nan")
        mma20 = float(close.tail(20).mean())
        mma50 = float(close.tail(50).mean())
        preco = float(close.iloc[-1])
        bruto = (2 if preco > mma20 else 0) + (1 if preco > mma50 else 0) + (1 if mma20 > mma50 else 0)
        return (bruto / 4) * 100

    raise ValueError(f"Variante desconhecida: {variante}")


# ---------------------------------------------------------------------------
# Variantes de momentum
# ---------------------------------------------------------------------------

def calcular_momentum_variante(df_ticker: pd.DataFrame, variante: str) -> float:
    """
    Recalcula momentum bruto com a variante especificada.
    df_ticker deve estar filtrado até data_corte (anti-look-ahead).
    Retorna valor bruto (será normalizado por percentil depois).
    """
    close = df_ticker["adj_close"].dropna()
    n = len(close)

    # Mínimo absoluto para calcular qualquer variante
    if n < 22:
        return float("nan")

    preco_atual = float(close.iloc[-1])
    ret_1m = preco_atual / float(close.iloc[-22]) - 1

    if variante == "M1":
        return ret_1m

    if n < 64:
        return float("nan")

    ret_3m = preco_atual / float(close.iloc[-64]) - 1

    if variante == "M3":
        return (ret_1m + ret_3m) / 2

    if n < 127:
        return float("nan")

    ret_6m = preco_atual / float(close.iloc[-127]) - 1

    if variante == "M0":
        return (ret_1m + ret_3m + ret_6m) / 3

    if variante == "M2":
        return (ret_1m * 3 + ret_3m * 2 + ret_6m * 1) / 6

    raise ValueError(f"Variante desconhecida: {variante}")


# ---------------------------------------------------------------------------
# IC por variante
# ---------------------------------------------------------------------------

def calcular_ic_variantes(
    backtest_carteiras: dict,
    df_precos: pd.DataFrame,
    universo: list[dict],
    bench_df: pd.DataFrame,
    variantes_tend: list[str],
    variantes_mom: list[str],
) -> tuple[dict, dict]:
    """
    Para cada variante de tendência e momentum: IC sobre excess return vs SMLL.
    Mesmo método do Módulo 3 — garante comparabilidade.
    """
    todos_tickers = [t["ticker_b3"] for t in universo]
    ic_tend: dict[str, list[dict]] = {v: [] for v in variantes_tend}
    ic_mom: dict[str, list[dict]] = {v: [] for v in variantes_mom}

    # Agrupa preços por ticker para evitar filtro repetido no loop interno
    grupos_ticker: dict[str, pd.DataFrame] = {
        t: df_precos[df_precos["ticker"] == t].sort_values("date")
        for t in todos_tickers
    }

    for semana in backtest_carteiras["carteiras"]:
        data_corte = date.fromisoformat(semana["data_corte_dados"])
        data_inicio = date.fromisoformat(semana["data_formacao"])
        data_fim = date.fromisoformat(semana["data_vigencia_fim"])

        # Excess returns vs SMLL
        excess, _ = _computar_excess_returns(
            semana, df_precos, bench_df, todos_tickers
        )
        if len(excess) < 20:
            continue

        # Preços filtrados até data_corte por ticker
        df_filtrados: dict[str, pd.DataFrame] = {
            ticker: g[g["date"].dt.date <= data_corte]
            for ticker, g in grupos_ticker.items()
        }

        # --- Variantes de tendência ---
        for variante in variantes_tend:
            scores_v, retornos = [], []
            for ticker in todos_tickers:
                if ticker not in excess:
                    continue
                df_f = df_filtrados[ticker]
                sc = calcular_tendencia_variante(df_f, variante)
                if np.isnan(sc):
                    continue
                scores_v.append(sc)
                retornos.append(excess[ticker])
            if len(scores_v) >= 10:
                ic, _ = spearmanr(scores_v, retornos)
                ic_tend[variante].append({
                    "semana": semana["semana"],
                    "ic": float(ic) if not np.isnan(ic) else 0.0,
                })

        # --- Variantes de momentum (normalização percentil por semana) ---
        for variante in variantes_mom:
            mom_brutos: dict[str, float] = {}
            for ticker in todos_tickers:
                if ticker not in excess:
                    continue
                df_f = df_filtrados[ticker]
                mb = calcular_momentum_variante(df_f, variante)
                if not np.isnan(mb):
                    mom_brutos[ticker] = mb

            if len(mom_brutos) < 10:
                continue

            # Normalização percentil dentro da semana
            serie = pd.Series(mom_brutos)
            norm = serie.rank(pct=True) * 100

            scores_v = [float(norm[t]) for t in mom_brutos]
            retornos = [excess[t] for t in mom_brutos]

            ic, _ = spearmanr(scores_v, retornos)
            ic_mom[variante].append({
                "semana": semana["semana"],
                "ic": float(ic) if not np.isnan(ic) else 0.0,
            })

    def sumarizar(ic_dict: dict) -> dict:
        resumo: dict[str, dict] = {}
        for variante, series in ic_dict.items():
            ics = [x["ic"] for x in series]
            if not ics:
                resumo[variante] = {
                    "ic_medio": 0.0, "ic_positivo_pct": 0.0,
                    "ir": 0.0, "n_semanas": 0,
                }
                continue
            ic_mean = float(np.mean(ics))
            ic_std = float(np.std(ics))
            resumo[variante] = {
                "ic_medio": round(ic_mean, 6),
                "ic_positivo_pct": round(
                    sum(1 for x in ics if x > 0) / len(ics), 4
                ),
                "ir": round(ic_mean / ic_std, 4) if ic_std > 0 else 0.0,
                "n_semanas": len(ics),
            }
        return resumo

    return sumarizar(ic_tend), sumarizar(ic_mom)


def identificar_vencedora(resumo: dict, baseline_key: str) -> dict:
    """
    Identifica variante com maior IC médio.
    Só recomenda mudança se ganho vs baseline > 20%.
    """
    if not resumo:
        return {
            "variante_vencedora": baseline_key,
            "ic_vencedora": 0.0,
            "ic_baseline": 0.0,
            "ganho_relativo": 0.0,
            "recomenda_mudanca": False,
            "motivo": "Sem dados suficientes",
        }

    baseline_ic = resumo.get(baseline_key, {}).get("ic_medio", 0.0)
    melhor = max(resumo, key=lambda v: resumo[v]["ic_medio"])
    melhor_ic = resumo[melhor]["ic_medio"]

    ganho = (
        (melhor_ic - baseline_ic) / abs(baseline_ic)
        if baseline_ic != 0 else 0.0
    )

    return {
        "variante_vencedora": melhor,
        "ic_vencedora": round(melhor_ic, 6),
        "ic_baseline": round(baseline_ic, 6),
        "ganho_relativo": round(ganho, 4),
        "recomenda_mudanca": ganho > 0.20,
        "motivo": (
            f"Variante {melhor} tem IC {ganho:.0%} acima do baseline "
            f"({melhor_ic:.4f} vs {baseline_ic:.4f}) — "
            + ("recomendada para V2." if ganho > 0.20 else "ganho < 20% — manter baseline.")
        ),
    }
