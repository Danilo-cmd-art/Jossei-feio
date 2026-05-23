"""Aba 1 — Carteira da semana (V2)."""
from __future__ import annotations

import json
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from utils.formatters import fmt_data_br, fmt_pct, fmt_pct_delta, fmt_reais


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_carteira() -> dict | None:
    if not config.CARTEIRA_V2_ATUAL_PATH.exists():
        return None
    with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def _carregar_benchmarks() -> pd.DataFrame | None:
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Gráfico de performance acumulada
# ---------------------------------------------------------------------------

def _render_grafico(performance: list[dict], bench_df: pd.DataFrame | None, data_corte: str) -> None:
    if not performance:
        st.info("Nenhum pregão de performance disponível ainda.")
        return

    rows = []
    for p in performance:
        rows.append({"data": p["data"], "serie": "Carteira V2", "retorno": p["retorno_acumulado"]})
        # Benchmarks embutidos na performance_diaria (se disponíveis)
        if "benchmarks" in p:
            b = p["benchmarks"]
            for nome, key in [("IBOV", "ibov"), ("SMAL11", "smll"), ("CDI", "cdi")]:
                v = b.get(key)
                if v is not None:
                    rows.append({"data": p["data"], "serie": nome, "retorno": v})

    if len(rows) <= len(performance):
        # Sem benchmarks embutidos — tenta calcular do parquet
        if bench_df is not None:
            dt_corte = date.fromisoformat(data_corte)
            for p in performance:
                dt = date.fromisoformat(p["data"][:10])
                for nome, col in [("IBOV", "ibov"), ("SMAL11", "smll"), ("CDI", "cdi")]:
                    if col in bench_df.columns:
                        janela = bench_df[
                            (bench_df["date"].dt.date > dt_corte) &
                            (bench_df["date"].dt.date <= dt)
                        ][col].dropna()
                        ret_acum = float(((1 + janela).prod() - 1)) if not janela.empty else 0.0
                        rows.append({"data": p["data"], "serie": nome, "retorno": ret_acum})

    df = pd.DataFrame(rows)
    if df.empty:
        return

    # Trunca para data (sem hora) e mantém apenas o último valor de cada dia por série
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    df = df.groupby(["data", "serie"], as_index=False).last()

    colors = {
        "Carteira V2": "#2563eb",
        "IBOV": "#6b7280",
        "SMAL11": "#9ca3af",
        "CDI": "#d1d5db",
    }
    domain = list(colors.keys())
    range_c = list(colors.values())

    base = alt.Chart(df)

    # Linhas com pontos marcados em cada dia
    linhas = base.mark_line(point=alt.OverlayMarkDef(filled=True, size=55)).encode(
        x=alt.X(
            "data:T",
            title="",
            axis=alt.Axis(format="%a %d/%m", labelAngle=0, tickCount="day"),
        ),
        y=alt.Y(
            "retorno:Q",
            title="Retorno acumulado",
            axis=alt.Axis(format=".1%"),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=domain, range=range_c),
            legend=alt.Legend(title=""),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V2",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=[
            alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
            alt.Tooltip("serie:N", title=""),
            alt.Tooltip("retorno:Q", format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=320)

    # Labels de % acumulado nos pontos da Carteira V2
    df_label = df[df["serie"] == "Carteira V2"].copy()
    labels = alt.Chart(df_label).mark_text(
        align="center",
        baseline="bottom",
        dy=-10,
        fontSize=11,
        fontWeight="bold",
        color="#2563eb",
    ).encode(
        x=alt.X("data:T"),
        y=alt.Y("retorno:Q"),
        text=alt.Text("retorno:Q", format="+.2%"),
    )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color="gray", opacity=0.5
    ).encode(y="y:Q")

    st.altair_chart(linhas + baseline + labels, use_container_width=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_carteira() -> None:
    carteira = _carregar_carteira()

    if carteira is None:
        st.error(
            "Carteira V2 ainda não gerada. "
            "Execute `python run_v2.py --fase 3` primeiro."
        )
        render_footer()
        return

    meta = carteira["metadata"]
    tickers = carteira.get("tickers", [])
    performance = carteira.get("performance_diaria", [])
    n = meta.get("n_posicoes", 0)
    ret_total = carteira.get("retorno_acumulado_total", 0.0)
    bootstrap = meta.get("bootstrap_retroativo", False)
    data_corte = meta.get("data_corte_dados", "")

    # Badges e alertas
    if bootstrap:
        st.info(
            f"🔄 **Carteira retroativa de bootstrap** — formada com dados até "
            f"{fmt_data_br(data_corte)}. "
            f"Próxima carteira oficial: "
            f"{fmt_data_br(meta.get('proxima_carteira_oficial'))}."
        )

    if n == 0:
        st.error("🚫 Nenhuma ação atendeu aos filtros F1+F2 esta semana. Sem recomendação.")
        render_footer()
        return
    elif n < 5:
        st.warning(
            f"⚠️ Apenas {n} ações passaram nos filtros esta semana. "
            f"Peso por posição: {100/n:.1f}%"
        )

    # ---------------------------------------------------------------------------
    # Cabeçalho da carteira + retorno em destaque
    # ---------------------------------------------------------------------------
    st.subheader("Carteira da semana")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    c1.markdown(f"**Formada em:** {fmt_data_br(meta.get('data_formacao'))}")
    c2.markdown(
        f"**Vigência:** {fmt_data_br(meta.get('data_vigencia_inicio'))} → "
        f"{fmt_data_br(meta.get('data_vigencia_fim'))}"
    )
    c3.markdown(f"**Posições:** {n} | Peso: {100/n:.0f}%")
    c4.metric("Retorno", fmt_pct(ret_total, sinal=True))

    # ---------------------------------------------------------------------------
    # Tabela de posições individuais
    # ---------------------------------------------------------------------------
    rows = []
    for t in tickers:
        ret = t.get("retorno_acumulado", 0.0)
        ret_str = fmt_pct(ret, sinal=True)
        status = "⚠️ Stale" if t.get("is_stale") else "✅ Ativo"
        rows.append({
            "Ticker": t["ticker"],
            "Score (formação)": fmt_score_val(t.get("score_na_formacao")),
            "Entrada": fmt_reais(t.get("preco_entrada")),
            "Atual": fmt_reais(t.get("preco_atual")),
            "Retorno Acum.": ret_str,
            "Status": status,
        })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
    )

    # ---------------------------------------------------------------------------
    # Performance da semana
    # ---------------------------------------------------------------------------
    if performance:
        st.subheader("Performance da semana")
        bench_df = _carregar_benchmarks()

        # Calcula retornos dos benchmarks no período da carteira
        ret_ibov = ret_smll = ret_cdi = None
        if bench_df is not None:
            dt_corte = date.fromisoformat(data_corte)
            dt_fim = date.fromisoformat(performance[-1]["data"][:10])
            for nome_col, nome_var in [("ibov", "ibov"), ("smll", "smll"), ("cdi", "cdi")]:
                if nome_col in bench_df.columns:
                    janela = bench_df[
                        (bench_df["date"].dt.date > dt_corte) &
                        (bench_df["date"].dt.date <= dt_fim)
                    ][nome_col].dropna()
                    v = float(((1 + janela).prod() - 1)) if not janela.empty else None
                    if nome_var == "ibov":
                        ret_ibov = v
                    elif nome_var == "smll":
                        ret_smll = v
                    elif nome_var == "cdi":
                        ret_cdi = v

        # Cards: carteira vs benchmarks (cada card mostra o retorno do próprio índice)
        # Delta = carteira − benchmark (positivo = outperformou, negativo = underperformou)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📊 Carteira V2", fmt_pct(ret_total, sinal=True))
        col2.metric(
            "IBOV",
            fmt_pct(ret_ibov, sinal=True) if ret_ibov is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_ibov) if ret_ibov is not None else None,
            help="Delta = Carteira − IBOV (positivo: superou o índice)",
        )
        col3.metric(
            "SMAL11",
            fmt_pct(ret_smll, sinal=True) if ret_smll is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_smll) if ret_smll is not None else None,
            help="Delta = Carteira − SMAL11",
        )
        col4.metric(
            "CDI",
            fmt_pct(ret_cdi, sinal=True) if ret_cdi is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_cdi) if ret_cdi is not None else None,
            help="Delta = Carteira − CDI",
        )

        # Gráfico acumulado por dia (com labels nos pontos da carteira)
        _render_grafico(performance, bench_df, data_corte)
    else:
        st.info("Performance ainda não disponível (primeiro dia ou fora do pregão).")

    render_footer()


def fmt_score_val(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):.1f}"
