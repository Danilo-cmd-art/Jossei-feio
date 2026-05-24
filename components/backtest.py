"""Aba 3 — Backtest V2 (versão simplificada: retorno + benchmarks + 1 gráfico)."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from components.theme import CHART_PALETTE
from utils.formatters import fmt_data_br, fmt_pct


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
# Gráfico: retorno acumulado semanal (Carteira vs Benchmarks)
# ---------------------------------------------------------------------------

def _render_retorno_acumulado(equity_curve: list[dict], periodo: str) -> None:
    dados = _filtrar_equity(equity_curve, periodo)
    if not dados:
        st.info("Sem dados de equity curve.")
        return

    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"])

    # Renormaliza para a janela escolhida e converte em RETORNO ACUMULADO (%)
    base_est  = df["valor_estrategia"].iloc[0]
    base_ibov = df["valor_ibov"].iloc[0]
    base_smll = df["valor_smll"].iloc[0]
    base_cdi  = df["valor_cdi"].iloc[0]

    df["Carteira V2"] = df["valor_estrategia"] / base_est  - 1
    df["IBOV"]        = df["valor_ibov"]       / base_ibov - 1
    df["SMAL11"]      = df["valor_smll"]       / base_smll - 1
    df["CDI"]         = df["valor_cdi"]        / base_cdi  - 1

    df_long = df.melt(
        id_vars="data",
        value_vars=["Carteira V2", "IBOV", "SMAL11", "CDI"],
        var_name="serie",
        value_name="retorno",
    )

    colors = {k: CHART_PALETTE[k] for k in ("Carteira V2", "IBOV", "SMAL11", "CDI")}

    base = alt.Chart(df_long)

    linhas = base.mark_line().encode(
        x=alt.X("data:T", title="", axis=alt.Axis(format="%b/%y")),
        y=alt.Y(
            "retorno:Q",
            title="Retorno acumulado",
            axis=alt.Axis(format=".0%"),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
            legend=alt.Legend(title=""),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V2",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=[
            alt.Tooltip("data:T",     title="Semana", format="%d/%m/%Y"),
            alt.Tooltip("serie:N",    title=""),
            alt.Tooltip("retorno:Q",  format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=380)

    # Label do retorno acumulado FINAL ABAIXO do último ponto de cada série
    df_last = df_long.sort_values("data").groupby("serie").tail(1)
    labels = alt.Chart(df_last).mark_text(
        align="center",
        baseline="top",   # texto fica abaixo do ponto
        dy=10,
        fontSize=12,
        fontWeight="bold",
    ).encode(
        x=alt.X("data:T"),
        y=alt.Y("retorno:Q"),
        text=alt.Text("retorno:Q", format="+.1%"),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
            legend=None,
        ),
    )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color="gray", opacity=0.5
    ).encode(y="y:Q")

    st.altair_chart(linhas + baseline + labels, use_container_width=True)


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

    meta         = bt["metadata"]
    metricas     = bt.get("metricas_estrategia", {})
    bench        = bt.get("metricas_benchmarks", {})
    alphas       = bt.get("alphas", {})
    equity_curve = bt.get("equity_curve", [])

    st.markdown(
        f"**Período:** {fmt_data_br(meta.get('janela_inicio'))} → "
        f"{fmt_data_br(meta.get('janela_fim'))} | "
        f"**Semanas:** {meta.get('n_semanas_simuladas')} | "
        f"**Fórmula:** {meta.get('versao_formula', 'v2').upper()} | "
        f"**Universo:** {meta.get('universo_versao', '—')}"
    )

    # ----------------------------------------------------------------------
    # Métricas principais — apenas Retorno Acumulado e Retorno a.a.
    # ----------------------------------------------------------------------
    st.subheader("Métricas principais")
    m1, m2 = st.columns(2)
    m1.metric(
        "Retorno Acumulado",
        fmt_pct(metricas.get("retorno_total"), sinal=True),
        help="Retorno total da estratégia no período do backtest.",
    )
    m2.metric(
        "Retorno a.a.",
        fmt_pct(metricas.get("retorno_anualizado"), sinal=True),
        help="Retorno anualizado equivalente (CAGR).",
    )

    # ----------------------------------------------------------------------
    # Comparação com benchmarks
    # ----------------------------------------------------------------------
    st.subheader("Comparação com benchmarks")
    col1, col2, col3, col4, col5 = st.columns(5)

    def _ret_bench(nome: str) -> str:
        v = bench.get(nome, {}).get("retorno_anualizado")
        return fmt_pct(v) if v is not None else "n/d"

    col1.metric("IBOV a.a.",        _ret_bench("ibov"))
    col2.metric("SMAL11 a.a.",      _ret_bench("smll"))
    col3.metric("CDI a.a.",         _ret_bench("cdi"))
    col4.metric("Alpha vs IBOV",    fmt_pct(alphas.get("vs_ibov"),  sinal=True))
    col5.metric("Alpha vs SMAL11",  fmt_pct(alphas.get("vs_smll"), sinal=True))

    # ----------------------------------------------------------------------
    # Gráfico único — Retorno acumulado semanal vs benchmarks
    # ----------------------------------------------------------------------
    st.subheader("Retorno acumulado por semana")
    _render_retorno_acumulado(equity_curve, periodo)

    # ----------------------------------------------------------------------
    # Limitações
    # ----------------------------------------------------------------------
    with st.expander("⚠️ Limitações do backtest (importante ler)", expanded=False):
        st.markdown("""
**Este backtest possui vieses conhecidos que podem inflar os resultados:**

- **Survivorship bias:** o universo usa os tickers *atuais* (mai/2026). Ações
  deslistadas ou em recuperação judicial no período histórico não aparecem — isso
  tende a inflar os retornos.

- **Zero custos:** sem corretagem, sem slippage, sem impostos.
  Estimativa de impacto: ~1,35%/ano sobre o retorno bruto.

- **Universo fixo:** o mesmo universo de mai/2026 é usado para todas as semanas.
  O universo real variaria ao longo do tempo.

- **Janela curta:** 2 anos têm significância estatística limitada para avaliar uma
  estratégia quantitativa.

**Backtest não é garantia de retorno futuro.**
        """)

    render_footer()
