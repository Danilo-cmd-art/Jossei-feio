"""Aba 4 — Histórico Real (Fase 7): performance ao vivo semana a semana."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from utils.formatters import fmt_data_br, fmt_pct, fmt_pct_delta


JANELA_ROLLING = 13  # ~3 meses


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_historico() -> dict | None:
    if not config.HISTORICO_REAL_PATH.exists():
        return None
    with open(config.HISTORICO_REAL_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Gráfico performance real (base 100, rolling)
# ---------------------------------------------------------------------------

def _render_grafico_real(semanas: list[dict]) -> None:
    if not semanas:
        return

    cart = [100.0]
    ibov = [100.0]
    smll = [100.0]
    cdi_ = [100.0]
    datas = []

    for s in semanas:
        datas.append(s["data_vigencia_fim"])
        cart.append(cart[-1] * (1 + s.get("retorno_carteira", 0)))
        ibov.append(ibov[-1] * (1 + s.get("retorno_ibov", 0)))
        smll.append(smll[-1] * (1 + s.get("retorno_smll", 0)))
        cdi_.append(cdi_[-1] * (1 + s.get("retorno_cdi", 0)))

    # Remove ponto inicial (base)
    df = pd.DataFrame({
        "data": pd.to_datetime(datas),
        "Carteira V3c": cart[1:],
        "IBOV": ibov[1:],
        "SMAL11": smll[1:],
        "CDI": cdi_[1:],
    })

    df_long = df.melt(
        id_vars="data",
        value_vars=["Carteira V3c", "IBOV", "SMAL11", "CDI"],
        var_name="serie",
        value_name="valor",
    )

    # Marca semanas bootstrap com shape diferente
    bootstrap_set = {s["data_vigencia_fim"] for s in semanas if s.get("bootstrap")}

    colors = {
        "Carteira V3c": "#2563eb",
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
            alt.datum.serie == "Carteira V3c",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=[
            alt.Tooltip("data:T", title="Data"),
            alt.Tooltip("serie:N", title=""),
            alt.Tooltip("valor:Q", format=".1f", title="Base 100"),
        ],
    ).properties(
        height=300,
        title="Performance Real — Base 100 (últimas 13 semanas)",
    )

    st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------------------
# Tabela de semanas passadas
# ---------------------------------------------------------------------------

def _render_tabela_historico(semanas: list[dict]) -> None:
    # Mais recente primeiro
    semanas_ord = list(reversed(semanas))

    rows = []
    for s in semanas_ord:
        label = f"🔄 {s['semana']}" if s.get("bootstrap") else s["semana"]
        tickers_str = ", ".join(t["ticker"] for t in s.get("tickers", []))
        ret = s.get("retorno_carteira", 0)
        rows.append({
            "Semana": label,
            "Tickers": tickers_str,
            "Retorno": fmt_pct(ret, sinal=True),
            "vs IBOV": fmt_pct(s.get("alpha_vs_ibov"), sinal=True),
            "vs SMAL11": fmt_pct(s.get("alpha_vs_smll"), sinal=True),
            "Ganhou IBOV": "✅" if s.get("carteira_venceu_ibov") else "❌",
        })

    df = pd.DataFrame(rows)
    event = st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        s_sel = semanas_ord[idx]
        with st.expander(
            f"Detalhes — {s_sel['semana']}", expanded=True
        ):
            _render_detalhes_semana(s_sel)


def _render_detalhes_semana(semana: dict) -> None:
    rows = []
    for t in semana.get("tickers", []):
        rows.append({
            "Ticker": t["ticker"],
            "Score": f"{t.get('score_na_formacao', 0):.1f}",
            "Entrada": f"R${t.get('preco_entrada', 0):.2f}",
            "Saída": f"R${t.get('preco_saida', 0):.2f}" if t.get("preco_saida") else "—",
            "Retorno": fmt_pct(t.get("retorno_semana"), sinal=True),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_historico() -> None:
    historico = _carregar_historico()

    if historico is None:
        st.info(
            "📊 **Histórico real ainda não iniciado.**\n\n"
            "O histórico de performance ao vivo é gerado automaticamente toda sexta, "
            "a partir da primeira semana de operação real (pós-bootstrap).\n\n"
            "O arquivo `data/historico_real.json` será criado quando o pipeline "
            "rodar pela primeira vez numa sexta-feira."
        )
        st.divider()
        st.markdown("### 🔬 Backtest histórico (simulação)")
        st.info(
            "O backtest histórico (simulação de 2 anos) está disponível na aba **Backtest**. "
            "São dados diferentes: o backtest usa universo congelado e zero custos. "
            "Esta aba mostrará o que aconteceu de fato semana a semana ao vivo."
        )
        render_footer()
        return

    meta = historico["metadata"]
    todas_semanas = historico.get("semanas", [])
    acumulado = historico.get("acumulado", {})

    # Rolling: últimas JANELA_ROLLING semanas
    semanas_rolling = todas_semanas[-JANELA_ROLLING:]
    n_disp = len(semanas_rolling)
    n_total = len(todas_semanas)

    st.markdown(
        f"📊 **Performance Real (ao vivo)** | "
        f"Operação iniciada em: {fmt_data_br(meta.get('data_inicio_operacao'))} | "
        f"Semanas registradas: {n_total}"
    )

    if n_disp < JANELA_ROLLING:
        st.caption(
            f"Exibindo todas as {n_disp} semanas disponíveis "
            f"(operação iniciada recentemente, ainda menos de 13 semanas)."
        )
    else:
        st.caption(f"Janela exibida: últimas {JANELA_ROLLING} semanas (~3 meses).")

    # Métricas rolling
    if semanas_rolling:
        n = len(semanas_rolling)
        win_ibov = sum(1 for s in semanas_rolling if s.get("carteira_venceu_ibov")) / n
        win_smll = sum(1 for s in semanas_rolling if s.get("carteira_venceu_smll")) / n
        pos = sum(1 for s in semanas_rolling if s.get("retorno_carteira", 0) > 0)

        ret_acum = acumulado.get("retorno_total", 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            f"Retorno acum. ({n_disp}sem)",
            fmt_pct(ret_acum),
            help="Retorno acumulado desde o início da operação real",
        )
        col2.metric(
            "Win rate vs IBOV",
            f"{win_ibov*100:.0f}%",
            help="% de semanas em que a carteira superou o IBOV",
        )
        col3.metric(
            "Win rate vs SMAL11",
            f"{win_smll*100:.0f}%",
            help="% de semanas em que a carteira superou o SMAL11",
        )
        col4.metric("Semanas positivas", f"{pos} de {n}")

    # Gráfico base 100
    if semanas_rolling:
        _render_grafico_real(semanas_rolling)

    # Tabela de semanas
    st.subheader("Carteiras passadas")
    if semanas_rolling:
        _render_tabela_historico(semanas_rolling)
    else:
        st.info("Nenhuma semana registrada ainda.")

    # Separador backtest vs real
    st.divider()
    st.markdown("### 🔬 Backtest histórico (simulação)")
    st.info(
        "O backtest histórico (simulação retroativa de 2 anos) está disponível "
        "na aba **Backtest**. São dados diferentes: o backtest usa universo congelado "
        "e zero custos. A performance real acima é o que aconteceu de fato semana a semana."
    )

    render_footer()
