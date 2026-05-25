"""
Small Cap Momentum Tracker — App Streamlit (Fases 5, 6, 7).

Fórmula V2: filtros F1 (MMA20/50) + F2 (ROIC>0%), fatores momentum+ROE+CAGR5a.
Universo: 50 small caps brasileiras (R$500M–15B).

Uso:
  streamlit run app.py
"""
import streamlit as st

# Configuração da página (deve vir antes de qualquer st.*)
st.set_page_config(
    page_title="Small Cap Momentum Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Tema visual (aplicar logo após set_page_config)
from components.theme import aplicar_tema
aplicar_tema()

# Imports dos componentes
from components.header import render_header
from components.carteira import render_aba_carteira
from components.backtest import render_aba_backtest
from components.historico_carteira import render_aba_historico_carteira

# Imports preservados (abas ocultas — podem ser reativadas no futuro)
# from components.ranking import render_aba_ranking
# from components.historico import render_aba_historico

# ---------------------------------------------------------------------------
# Sidebar — filtro de período do backtest
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        "<div style='font-family:\"Source Serif Pro\",serif; font-size:1.4rem; "
        "font-weight:600; color:#1B365D; letter-spacing:-0.01em; margin-bottom:2px;'>"
        "SmallRadar</div>"
        "<div style='font-size:0.72rem; color:#A89968; text-transform:uppercase; "
        "letter-spacing:1.4px; font-weight:600; margin-bottom:22px;'>V3c · "
        "Quantitative Strategy</div>",
        unsafe_allow_html=True,
    )

    st.header("Configurações")
    periodo = st.radio(
        "Período do backtest",
        options=["3m", "6m", "1a", "2a"],
        index=3,   # default: 2 anos
        format_func=lambda x: {
            "3m": "Últimos 3 meses",
            "6m": "Últimos 6 meses",
            "1a": "Último ano",
            "2a": "2 anos completos",
        }[x],
    )
    st.divider()
    st.markdown(
        "<div style='font-size:0.82rem; color:#3A4654; line-height:1.65;'>"
        "<strong style='color:#1B365D; font-size:0.78rem; "
        "text-transform:uppercase; letter-spacing:0.9px;'>Metodologia</strong><br>"
        "Scoring V2 · Stop loss −5% · Redistribuição seletiva "
        "(posições positivas, cap 2×).<br><br>"
        "<strong style='color:#1B365D; font-size:0.78rem; "
        "text-transform:uppercase; letter-spacing:0.9px;'>Pesos do score</strong><br>"
        "Momentum 50% · ROE 30% · CAGR 5a 20%<br><br>"
        "<strong style='color:#1B365D; font-size:0.78rem; "
        "text-transform:uppercase; letter-spacing:0.9px;'>Universo</strong><br>"
        "Small caps brasileiras · MCAP R$ 500M–15B · liquidez ≥ R$ 1MM/dia"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Header global
# ---------------------------------------------------------------------------
render_header()

# ---------------------------------------------------------------------------
# Abas principais — Carteira + Backtest (Ranking e Histórico ocultos)
# ---------------------------------------------------------------------------
tab_carteira, tab_backtest, tab_historico = st.tabs(
    ["Carteira", "Backtest", "Histórico"]
)

with tab_carteira:
    render_aba_carteira()

with tab_backtest:
    render_aba_backtest(periodo=periodo)

with tab_historico:
    render_aba_historico_carteira()
