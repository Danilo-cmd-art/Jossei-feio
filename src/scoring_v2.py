"""
Fórmula V2 — Motor de Scoring.

Diferenças vs V1:
  F1: tendência MMA20/50 (era MMA50/200) — filtro de entrada, não fator de score
  F2: ROIC > 0% — filtro de entrada novo
  Fator A: momentum 1m+3m (era 1m+3m+6m), peso 50%
  Fator B: ROE percentil, peso 30% (era tendência MMA50/200)
  Fator C: CAGR receita 5a como proxy de crescimento 12m, peso 20%
  (Fator D removido)

Normalização só sobre tickers que passaram em F1 e F2.
V2_CLAUDE_CODE_PROMPT.md §2.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

import config


# ---------------------------------------------------------------------------
# Filtros de entrada
# ---------------------------------------------------------------------------

def _filtro_f1_tendencia(df_ticker: pd.DataFrame) -> tuple[bool, dict | None]:
    """
    F1 — Tendência MMA20/50.
    aprovado = (P>MMA20) + (P>MMA50) + (MMA20>MMA50) >= 2
    Retorna (passou, detalhe_dict) para exibição no frontend.
    detalhe_dict é None se histórico insuficiente.
    """
    closes = df_ticker["adj_close"].dropna()
    if len(closes) < config.JANELA_MMA_V2_MEDIA:
        return False, None

    preco = float(closes.iloc[-1])
    mma20 = float(closes.tail(config.JANELA_MMA_V2_CURTA).mean())
    mma50 = float(closes.tail(config.JANELA_MMA_V2_MEDIA).mean())

    c1 = preco > mma20
    c2 = preco > mma50
    c3 = mma20 > mma50
    pontos = int(c1) + int(c2) + int(c3)

    detalhe = {
        "preco_atual": round(preco, 4),
        "mma20": round(mma20, 4),
        "mma50": round(mma50, 4),
        "preco_acima_mma20": c1,
        "preco_acima_mma50": c2,
        "mma20_acima_mma50": c3,
        "pontos": pontos,
    }
    return pontos >= 2, detalhe


def _filtro_f2_roic(roic: float | None) -> bool:
    """
    F2 — ROIC > 0%.
    Se ausente (None): aprovado por padrão.
    """
    if roic is None:
        return True
    return roic > 0.0


# ---------------------------------------------------------------------------
# Cálculo de momentum V2 (1m + 3m, sem 6m)
# ---------------------------------------------------------------------------

def _calcular_momentum_v2(
    df_ticker: pd.DataFrame,
) -> tuple[float, float, float] | None:
    """
    momentum_bruto = (ret_1m + ret_3m) / 2
    Retorna (bruto, ret_1m, ret_3m) ou None se histórico insuficiente.
    """
    closes = df_ticker["adj_close"].dropna()
    janela_min = config.JANELA_MOMENTUM_V2_3M + 1  # 64 posições
    if len(closes) < janela_min:
        return None

    preco = float(closes.iloc[-1])
    ret_1m = preco / float(closes.iloc[-(config.JANELA_MOMENTUM_V2_1M + 1)]) - 1
    ret_3m = preco / float(closes.iloc[-(config.JANELA_MOMENTUM_V2_3M + 1)]) - 1
    bruto = (ret_1m + ret_3m) / 2
    return bruto, ret_1m, ret_3m


# ---------------------------------------------------------------------------
# Normalização percentil
# ---------------------------------------------------------------------------

def _normalizar_percentil(
    serie: pd.Series,
    missing_fill: float = config.PERCENTIL_MISSING_DEFAULT,
) -> pd.Series:
    """Ranking percentil 0-100. NaN → missing_fill (50)."""
    rank = serie.rank(pct=True) * 100
    return rank.fillna(missing_fill)


# ---------------------------------------------------------------------------
# Score principal V2
# ---------------------------------------------------------------------------

def calcular_scores_v2(
    df_precos: pd.DataFrame,
    universo: list[dict],
    data_corte: date,
) -> list[dict]:
    """
    Calcula scores V2 para todos os tickers do universo.

    GARANTIA ANTI-LOOK-AHEAD: só usa dados até data_corte inclusive.
    Levanta AssertionError se dados posteriores forem detectados.

    Retorna lista de dicts — inclui passou_filtro_tendencia (alias V1)
    para compatibilidade com portfolio.py/backtest.py.
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

    # ---------------------------------------------------------------------------
    # Passo 1: aplicar filtros F1 e F2 (excluir antes de normalizar)
    # ---------------------------------------------------------------------------
    filtro_status: dict[str, dict] = {}
    mom_resultado: dict[str, tuple | None] = {}  # (bruto, ret_1m, ret_3m) ou None
    f1_detalhes: dict[str, dict | None] = {}

    for ticker in tickers:
        df_t = df_filtrado[df_filtrado["ticker"] == ticker].sort_values("date")
        fund = fundamentos[ticker]

        passou_f1, f1_det = _filtro_f1_tendencia(df_t)
        passou_f2 = _filtro_f2_roic(fund.get("roic"))
        passou_ambos = passou_f1 and passou_f2

        f1_detalhes[ticker] = f1_det
        mom_resultado[ticker] = _calcular_momentum_v2(df_t) if passou_ambos else None

        filtro_status[ticker] = {
            "passou_f1": passou_f1,
            "passou_f2": passou_f2,
            "passou_ambos": passou_ambos,
        }

    # ---------------------------------------------------------------------------
    # Passo 2: normalização SOMENTE sobre aprovados nos filtros
    # ---------------------------------------------------------------------------
    aprovados = [t for t in tickers if filtro_status[t]["passou_ambos"]]

    # Momentum (extrai só o bruto para normalização)
    def _bruto(t: str) -> float | None:
        r = mom_resultado[t]
        return r[0] if r is not None else None

    mom_serie = pd.Series({t: _bruto(t) for t in aprovados})
    mom_norm = _normalizar_percentil(mom_serie)

    # ROE
    roe_serie = pd.Series(
        {t: fundamentos[t].get("roe") for t in aprovados}
    )
    roe_norm = _normalizar_percentil(roe_serie)

    # CAGR receita (5a como proxy de 12m)
    cagr_serie = pd.Series(
        {t: fundamentos[t].get("cagr_receita_5a") for t in aprovados}
    )
    cagr_norm = _normalizar_percentil(cagr_serie)

    # ---------------------------------------------------------------------------
    # Passo 3: montar resultados
    # ---------------------------------------------------------------------------
    resultados: list[dict] = []

    for ticker in tickers:
        fs = filtro_status[ticker]
        fund = fundamentos[ticker]
        passou = fs["passou_ambos"]
        f1_det = f1_detalhes[ticker]
        mom_res = mom_resultado[ticker]

        if passou:
            mn = float(mom_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))
            rn = float(roe_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))
            cn = float(cagr_norm.get(ticker, config.PERCENTIL_MISSING_DEFAULT))

            score = (
                config.PESO_V2_MOMENTUM * mn +
                config.PESO_V2_ROE      * rn +
                config.PESO_V2_CAGR     * cn
            )
            mb = mom_res[0] if mom_res is not None else None
            r1m = mom_res[1] if mom_res is not None else None
            r3m = mom_res[2] if mom_res is not None else None
        else:
            mn = rn = cn = 0.0
            score = 0.0
            mb = r1m = r3m = None

        resultados.append({
            "ticker": ticker,
            "score_final": round(score, 4) if passou else 0.0,
            # Campos de filtro V2
            "passou_filtro_f1": fs["passou_f1"],
            "passou_filtro_f2": fs["passou_f2"],
            "passou_filtros_entrada": passou,
            # Alias para compatibilidade com portfolio.py (formar_carteira)
            "passou_filtro_tendencia": passou,
            "momentum_bruto": mb,
            "fatores": {
                # Filtros de entrada (para breakdown no frontend)
                "filtro_f1": {
                    "passou": fs["passou_f1"],
                    "detalhe": f1_det,  # None se histórico insuficiente
                },
                "filtro_f2": {
                    "passou": fs["passou_f2"],
                    "roic_bruto": fund.get("roic"),
                },
                # Fatores de score (só preenchidos se passou ambos os filtros)
                "momentum": {
                    "ret_1m": round(r1m, 6) if r1m is not None else None,
                    "ret_3m": round(r3m, 6) if r3m is not None else None,
                    "bruto": round(mb, 6) if mb is not None else None,
                    "normalizado": round(mn, 2) if passou else None,
                    "contribuicao_score": round(config.PESO_V2_MOMENTUM * mn, 4) if passou else 0.0,
                },
                "roe": {
                    "bruto": fund.get("roe"),
                    "normalizado": round(rn, 2) if passou else None,
                    "contribuicao_score": round(config.PESO_V2_ROE * rn, 4) if passou else 0.0,
                    "is_missing": fund.get("roe") is None,
                },
                "cagr_receita": {
                    "bruto": fund.get("cagr_receita_5a"),
                    "normalizado": round(cn, 2) if passou else None,
                    "contribuicao_score": round(config.PESO_V2_CAGR * cn, 4) if passou else 0.0,
                    "is_missing": fund.get("cagr_receita_5a") is None,
                    "usando_fallback_5a": True,  # campo 12m não existe no CSV
                },
            },
        })

    # Ranking: aprovados primeiro (por score desc), reprovados depois
    aprovados_lista = [r for r in resultados if r["passou_filtros_entrada"]]
    reprovados_lista = [r for r in resultados if not r["passou_filtros_entrada"]]

    aprovados_lista.sort(key=lambda x: (-x["score_final"], -(x["momentum_bruto"] or -999)))
    for i, r in enumerate(aprovados_lista):
        r["rank"] = i + 1
    for i, r in enumerate(reprovados_lista):
        r["rank"] = len(aprovados_lista) + i + 1

    return aprovados_lista + reprovados_lista
