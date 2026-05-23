"""Aba 3 — Backtest V2 (métricas + equity curve + drawdown)."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from utils.formatters import fmt_data_br, fmt_pct, fmt_pct_delta


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_backtest() -> dict | None:
    if not config.BACKTEST_V2_RESULTADO_PATH.exists():
        return None
    with open(config.BACKTEST_V2_RESULTADO_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Filtro de período
# ---------------------------------------------------------------------------

def _filtrar_equity(equity_curve: list[dict], periodo: str) -> list[dict]:
    n = {"3m": 13, "6m": 26, "1a": 52, "2a": 104}.get(periodo, 104)
    return equity_curve[-n:] if len(equity_curve) >= n else equity_curve


# ---------------------------------------------------------------------------
# Gráfico equity curve
# ---------------------------------------------------------------------------

def _render_equity_curve(equity_curve: list[dict], periodo: str) -> None:
    dados = _filtrar_equity(equity_curve, periodo)
    if not dados:
        st.info("Sem dados de equity curve.")
        return

    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"])

    # Renormaliza para base 100 na janela selecionada
    base_est = df["valor_estrategia"].iloc[0]
    base_ibov = df["valor_ibov"].iloc[0]
    base_smll = df["valor_smll"].iloc[0]
    base_cdi = df["valor_cdi"].iloc[0]

    df["Estratégia V2"] = df["valor_estrategia"] / base_est * 100
    df["IBOV"] = df["valor_ibov"] / base_ibov * 100
    df["SMAL11"] = df["valor_smll"] / base_smll * 100
    df["CDI"] = df["valor_cdi"] / base_cdi * 100

    df_long = df.melt(
        id_vars="data",
        value_vars=["Estratégia V2", "IBOV", "SMAL11", "CDI"],
        var_name="serie",
        value_name="valor",
    )

    colors = {
        "Estratégia V2": "#2563eb",
        "IBOV": "#6b7280",
        "SMAL11": "#9ca3af",
        "CDI": "#d1d5db",
    }

    chart = alt.Chart(df_long).mark_line().encode(
        x=alt.X("data:T", title=""),
        y=alt.Y("valor:Q", title="Valor (base 100)"),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(
                domain=list(colors.keys()),
                range=list(colors.values()),
            ),
            legend=alt.Legend(title=""),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Estratégia V2",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=[
            alt.Tooltip("data:T", title="Data"),
            alt.Tooltip("serie:N", title=""),
            alt.Tooltip("valor:Q", format=".1f", title="Base 100"),
        ],
    ).properties(height=350, title="Equity Curve — Base 100")

    st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------------------
# Gráfico drawdown
# ---------------------------------------------------------------------------

def _render_drawdown(equity_curve: list[dict], periodo: str) -> None:
    dados = _filtrar_equity(equity_curve, periodo)
    if not dados:
        return

    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"])

    rolling_max = df["valor_estrategia"].cummax()
    df["drawdown"] = df["valor_estrategia"] / rolling_max - 1

    chart = alt.Chart(df).mark_area(
        color="#ef4444", opacity=0.4, line={"color": "#ef4444"}
    ).encode(
        x=alt.X("data:T", title=""),
        y=alt.Y(
            "drawdown:Q",
            title="Drawdown",
            axis=alt.Axis(format=".0%"),
        ),
        tooltip=[
            alt.Tooltip("data:T", title="Data"),
            alt.Tooltip("drawdown:Q", format=".1%", title="Drawdown"),
        ],
    ).properties(height=180, title="Drawdown da Estratégia V2")

    st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_backtest(periodo: str = "2a") -> None:
    bt = _carregar_backtest()

    if bt is None:
        st.warning(
            "Backtest V2 ainda não gerado. "
            "Execute `python run_v2.py --fase 4` primeiro."
        )
        render_footer()
        return

    meta = bt["metadata"]
    metricas = bt.get("metricas_estrategia", {})
    bench = bt.get("metricas_benchmarks", {})
    alphas = bt.get("alphas", {})
    equity_curve = bt.get("equity_curve", [])

    st.markdown(
        f"**Período:** {fmt_data_br(meta.get('janela_inicio'))} → "
        f"{fmt_data_br(meta.get('janela_fim'))} | "
        f"**Semanas:** {meta.get('n_semanas_simuladas')} | "
        f"**Fórmula:** {meta.get('versao_formula', 'v2').upper()} | "
        f"**Universo:** {meta.get('universo_versao', '—')}"
    )

    # --- Métricas de risco/retorno ---
    st.subheader("Métricas principais")
    cols = st.columns(6)
    cols[0].metric(
        "Retorno a.a.",
        fmt_pct(metricas.get("retorno_anualizado")),
    )
    cols[1].metric(
        "Volatilidade a.a.",
        fmt_pct(metricas.get("volatilidade_anualizada")),
    )
    cols[2].metric("Sharpe", f"{metricas.get('sharpe_ratio', 0):.2f}")
    cols[3].metric(
        "Max Drawdown",
        fmt_pct(metricas.get("max_drawdown")),
    )
    cols[4].metric(
        "Win Rate",
        fmt_pct(metricas.get("win_rate_semanal")),
    )
    cols[5].metric(
        "Hit vs SMAL11",
        fmt_pct(metricas.get("hit_rate_vs_smll")),
    )

    # --- Alphas ---
    st.subheader("Comparação com benchmarks")
    col1, col2, col3, col4, col5 = st.columns(5)

    def _ret_bench(nome: str) -> str:
        v = bench.get(nome, {}).get("retorno_anualizado")
        return fmt_pct(v) if v is not None else "n/d"

    col1.metric("IBOV a.a.", _ret_bench("ibov"))
    col2.metric("SMAL11 a.a.", _ret_bench("smll"))
    col3.metric("CDI a.a.", _ret_bench("cdi"))
    col4.metric(
        "Alpha vs IBOV",
        fmt_pct(alphas.get("vs_ibov"), sinal=True),
    )
    col5.metric(
        "Alpha vs SMAL11",
        fmt_pct(alphas.get("vs_smll"), sinal=True),
    )

    # --- Equity curve ---
    _render_equity_curve(equity_curve, periodo)

    # --- Drawdown ---
    st.subheader("Drawdown")
    _render_drawdown(equity_curve, periodo)

    # --- Limitações ---
    with st.expander("⚠️ Limitações do backtest (importante ler)", expanded=False):
        st.markdown("""
**Este backtest possui vieses conhecidos que podem inflar os resultados:**

- **Survivorship bias:** o universo usa os 50 tickers *atuais* (mai/2026). Ações
  deslistadas ou em recuperação judicial no período histórico não aparecem — isso
  tende a inflar os retornos.

- **Zero custos:** sem corretagem, sem slippage, sem impostos.
  Estimativa de impacto: ~1,35%/ano sobre o retorno bruto.

- **Universo fixo:** o mesmo universo de mai/2026 é usado para todas as ~104 semanas.
  O universo real variaria ao longo do tempo.

- **Janela curta:** 2 anos têm significância estatística limitada para avaliar uma
  estratégia quantitativa.

**Backtest não é garantia de retorno futuro.**
        """)

    render_footer()
