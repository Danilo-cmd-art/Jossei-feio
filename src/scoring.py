"""
Fase 3 — Motor de Scoring.

Cálculo dos 4 fatores, normalização percentil e score final.
PHASE3_SPEC §3-5.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

import config


def calcular_momentum(df_ticker: pd.DataFrame, data_corte: date) -> float | None:
    """
    Momentum bruto: média de ret_1m, ret_3m, ret_6m.
    df_ticker deve estar filtrado até data_corte (anti-look-ahead).
    """
    closes = df_ticker["adj_close"].dropna()
    n = len(closes)

    janela_max = config.JANELA_MOMENTUM_6M + 1  # 127 posições necessárias
    if n < janela_max:
        return None

    preco_atual = closes.iloc[-1]
    preco_1m = closes.iloc[-(config.JANELA_MOMENTUM_1M + 1)]
    preco_3m = closes.iloc[-(config.JANELA_MOMENTUM_3M + 1)]
    preco_6m = closes.iloc[-(config.JANELA_MOMENTUM_6M + 1)]

    ret_1m = preco_atual / preco_1m - 1
    ret_3m = preco_atual / preco_3m - 1
    ret_6m = preco_atual / preco_6m - 1

    return (ret_1m + ret_3m + ret_6m) / 3


def calcular_tendencia(df_ticker: pd.DataFrame, data_corte: date) -> int:
    """
    Score de tendência 0-3 baseado em MMA50 e MMA200.
    df_ticker deve estar filtrado até data_corte (anti-look-ahead).
    """
    closes = df_ticker["adj_close"].dropna()
    if len(closes) < config.JANELA_MMA_LONGA:
        return 0

    preco_atual = float(closes.iloc[-1])
    mma_50 = float(closes.tail(config.JANELA_MMA_CURTA).mean())
    mma_200 = float(closes.tail(config.JANELA_MMA_LONGA).mean())

    ponto_1 = 1 if preco_atual > mma_50 else 0
    ponto_2 = 1 if preco_atual > mma_200 else 0
    ponto_3 = 1 if mma_50 > mma_200 else 0

    return ponto_1 + ponto_2 + ponto_3


def normalizar_percentil(serie: pd.Series, missing_fill: float = config.PERCENTIL_MISSING_DEFAULT) -> pd.Series:
    """
    Ranking percentil 0-100.
    Maior valor = 100, menor = 0, NaN = missing_fill (50).
    """
    rank = serie.rank(pct=True) * 100
    return rank.fillna(missing_fill)


def calcular_scores(
    df_precos: pd.DataFrame,
    universo: list[dict],
    data_corte: date,
) -> list[dict]:
    """
    Calcula scores para todos os tickers do universo.

    GARANTIA ANTI-LOOK-AHEAD: só usa dados até data_corte inclusive.
    Levanta AssertionError se dados posteriores forem detectados.
    """
    df_filtrado = df_precos[df_precos["date"].dt.date <= data_corte].copy()

    if not df_filtrado.empty:
        max_data = df_filtrado["date"].dt.date.max()
        assert max_data <= data_corte, (
            f"Look-ahead bias detectado: dados até {max_data} mas corte é {data_corte}"
        )

    # Mapa ticker → fundamentos
    fundamentos = {t["ticker_b3"]: t for t in universo}
    tickers = [t["ticker_b3"] for t in universo]

    # Coleta brutas
    mom_bruto: dict[str, float | None] = {}
    tend_bruto: dict[str, int] = {}
    roic_bruto: dict[str, float | None] = {}
    cagr_bruto: dict[str, float | None] = {}
    detalhes: dict[str, dict] = {}

    for ticker in tickers:
        df_t = df_filtrado[df_filtrado["ticker"] == ticker].sort_values("date")
        fund = fundamentos[ticker]

        mom = calcular_momentum(df_t, data_corte)
        tend = calcular_tendencia(df_t, data_corte)

        mom_bruto[ticker] = mom
        tend_bruto[ticker] = tend
        roic_bruto[ticker] = fund.get("roic")
        cagr_bruto[ticker] = fund.get("cagr_receita_5a")

        if df_t.empty:
            detalhes[ticker] = {"preco_atual": None, "mma_50": None, "mma_200": None}
            continue

        closes = df_t["adj_close"].dropna()
        detalhes[ticker] = {
            "preco_atual": float(closes.iloc[-1]) if len(closes) > 0 else None,
            "mma_50": float(closes.tail(config.JANELA_MMA_CURTA).mean()) if len(closes) >= config.JANELA_MMA_CURTA else None,
            "mma_200": float(closes.tail(config.JANELA_MMA_LONGA).mean()) if len(closes) >= config.JANELA_MMA_LONGA else None,
        }

    # Normalização
    mom_serie = pd.Series(mom_bruto)
    tend_serie = pd.Series({t: (v / 3) * 100 for t, v in tend_bruto.items()})
    roic_serie = pd.Series(roic_bruto)
    cagr_serie = pd.Series(cagr_bruto)

    mom_norm = normalizar_percentil(mom_serie)
    tend_norm = tend_serie.fillna(0.0)
    roic_norm = normalizar_percentil(roic_serie)
    cagr_norm = normalizar_percentil(cagr_serie)

    # Scores finais
    resultados = []
    for ticker in tickers:
        mn = float(mom_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))
        tn = float(tend_norm.get(ticker, 0.0))
        rn = float(roic_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))
        cn = float(cagr_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))

        score = (
            config.PESO_MOMENTUM * mn +
            config.PESO_TENDENCIA * tn +
            config.PESO_ROIC * rn +
            config.PESO_CAGR * cn
        )

        tb = tend_bruto.get(ticker, 0)
        passou_filtro = tb >= config.FILTRO_TENDENCIA_MINIMO
        mb = mom_bruto.get(ticker)

        d = detalhes.get(ticker, {})
        resultados.append({
            "ticker": ticker,
            "score_final": round(score, 4),
            "passou_filtro_tendencia": passou_filtro,
            "momentum_bruto": mb,
            "fatores": {
                "momentum": {
                    "bruto": mb,
                    "normalizado": round(mn, 2),
                    "contribuicao_score": round(config.PESO_MOMENTUM * mn, 4),
                },
                "tendencia": {
                    "preco_atual": d.get("preco_atual"),
                    "mma_50": d.get("mma_50"),
                    "mma_200": d.get("mma_200"),
                    "preco_acima_mma50": (d.get("preco_atual") or 0) > (d.get("mma_50") or 0),
                    "preco_acima_mma200": (d.get("preco_atual") or 0) > (d.get("mma_200") or 0),
                    "mma50_acima_mma200": (d.get("mma_50") or 0) > (d.get("mma_200") or 0),
                    "bruto": tb,
                    "normalizado": round(tn, 2),
                    "contribuicao_score": round(config.PESO_TENDENCIA * tn, 4),
                },
                "roic": {
                    "bruto": roic_bruto.get(ticker),
                    "normalizado": round(rn, 2),
                    "contribuicao_score": round(config.PESO_ROIC * rn, 4),
                    "is_missing": roic_bruto.get(ticker) is None,
                },
                "cagr_receita": {
                    "bruto": cagr_bruto.get(ticker),
                    "normalizado": round(cn, 2),
                    "contribuicao_score": round(config.PESO_CAGR * cn, 4),
                    "is_missing": cagr_bruto.get(ticker) is None,
                },
            },
        })

    # Rankear por score
    resultados.sort(key=lambda x: (-x["score_final"], -(x["momentum_bruto"] or -999)))
    for i, r in enumerate(resultados):
        r["rank"] = i + 1

    return resultados
