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

# Imports dos componentes
from components.header import render_header
from components.carteira import render_aba_carteira
from components.ranking import render_aba_ranking
from components.backtest import render_aba_backtest
from components.historico import render_aba_historico

# ---------------------------------------------------------------------------
# Sidebar — filtro de período do backtest
# ---------------------------------------------------------------------------
with st.sidebar:
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
    st.caption(
        "**SmallRadar V2**\n\n"
        "Fórmula: F1 (MMA20/50) + F2 (ROIC>0%) → "
        "50% Momentum + 30% ROE + 20% CAGR5a\n\n"
        "Universo: MCAP R$500M–15B"
    )

# ---------------------------------------------------------------------------
# Header global
# ---------------------------------------------------------------------------
render_header()

# ---------------------------------------------------------------------------
# Abas principais
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 Carteira", "🏆 Ranking", "📈 Backtest", "📊 Histórico"]
)

with tab1:
    render_aba_carteira()

with tab2:
    render_aba_ranking()

with tab3:
    render_aba_backtest(periodo=periodo)

with tab4:
    render_aba_historico()
