"""Aba Backtest V2 — versão editorial limpa."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from components.theme import CHART_PALETTE, COLORS
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


def _filtrar_equity(equity_curve: list[dict], periodo: str) -> list[dict]:
    n = {"3m": 13, "6m": 26, "1a": 52, "2a": 104}.get(periodo, 104)
    return equity_curve[-n:] if len(equity_curve) >= n else equity_curve


# ---------------------------------------------------------------------------
# Gráfico de retorno acumulado semanal (Carteira vs Benchmarks)
# ---------------------------------------------------------------------------

def _render_retorno_acumulado(equity_curve: list[dict], periodo: str) -> None:
    dados = _filtrar_equity(equity_curve, periodo)
    if not dados:
        st.info("Sem dados de equity curve.")
        return

    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"])

    # Renormaliza para a janela escolhida em RETORNO ACUMULADO (%)
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
    base   = alt.Chart(df_long)

    linhas = base.mark_line().encode(
        x=alt.X("data:T", title="", axis=alt.Axis(format="%b/%y", labelColor=COLORS["muted"])),
        y=alt.Y(
            "retorno:Q",
            title="",
            axis=alt.Axis(format=".0%", labelColor=COLORS["muted"]),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
            legend=alt.Legend(title="", labelColor=COLORS["ink"], labelFontSize=12),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V2",
            alt.value(2.5),
            alt.value(1.2),
        ),
        tooltip=[
            alt.Tooltip("data:T",     title="Semana", format="%d/%m/%Y"),
            alt.Tooltip("serie:N",    title=""),
            alt.Tooltip("retorno:Q",  format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=400)

    # Labels finais sem sobreposição: stagger vertical baseado em retorno
    df_last = (
        df_long.sort_values("data")
        .groupby("serie", as_index=False)
        .tail(1)
        .copy()
    )
    df_last["rank"] = df_last["retorno"].rank(method="first", ascending=False)
    # dy = -8 para o de cima, escala 14 px por rank pra evitar overlap
    df_last["dy"]   = (df_last["rank"] - 1) * 14 - 4

    labels_list = []
    for _, row in df_last.iterrows():
        labels_list.append(
            alt.Chart(pd.DataFrame([row])).mark_text(
                align="left",
                baseline="middle",
                dx=8,
                dy=float(row["dy"]),
                fontSize=11,
                fontWeight="bold",
                font="Inter",
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
        )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color=COLORS["muted_2"], opacity=0.6
    ).encode(y="y:Q")

    chart = linhas + baseline
    for lbl in labels_list:
        chart = chart + lbl

    st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_backtest(periodo: str = "2a") -> None:
    bt = _carregar_backtest()

    if bt is None:
        st.warning("Backtest V2 ainda não gerado.")
        render_footer()
        return

    meta         = bt["metadata"]
    metricas     = bt.get("metricas_estrategia", {})
    bench        = bt.get("metricas_benchmarks", {})
    alphas       = bt.get("alphas", {})
    equity_curve = bt.get("equity_curve", [])

    # Período em estilo editorial
    st.markdown(
        f"""
        <div style='display:flex; gap:24px; flex-wrap:wrap;
                    padding:14px 0 22px 0;
                    border-bottom:1px solid #DDD8CE;
                    margin-bottom:28px;'>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Período do backtest
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {fmt_data_br(meta.get('janela_inicio'))} → {fmt_data_br(meta.get('janela_fim'))}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Semanas
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {meta.get('n_semanas_simuladas', '—')}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Fórmula · Universo
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {meta.get('versao_formula', 'v2').upper()} · {meta.get('universo_versao', '—')}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Métricas principais — 2 cards grandes
    m1, m2 = st.columns(2)
    m1.metric(
        "Retorno acumulado",
        fmt_pct(metricas.get("retorno_total"), sinal=True),
        help="Retorno total da estratégia no período do backtest.",
    )
    m2.metric(
        "Retorno anualizado",
        fmt_pct(metricas.get("retorno_anualizado"), sinal=True),
        help="Retorno anualizado equivalente (CAGR).",
    )

    # Comparação com benchmarks
    st.markdown("### Comparação com benchmarks")
    col1, col2, col3, col4, col5 = st.columns(5)

    def _ret_bench(nome: str) -> str:
        v = bench.get(nome, {}).get("retorno_anualizado")
        return fmt_pct(v) if v is not None else "n/d"

    col1.metric("IBOV a.a.",       _ret_bench("ibov"))
    col2.metric("SMAL11 a.a.",     _ret_bench("smll"))
    col3.metric("CDI a.a.",        _ret_bench("cdi"))
    col4.metric("Alpha vs IBOV",   fmt_pct(alphas.get("vs_ibov"),  sinal=True))
    col5.metric("Alpha vs SMAL11", fmt_pct(alphas.get("vs_smll"), sinal=True))

    # Gráfico único
    st.markdown("### Retorno acumulado por semana")
    _render_retorno_acumulado(equity_curve, periodo)

    render_footer()
