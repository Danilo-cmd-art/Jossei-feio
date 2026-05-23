"""Rodapé fixo com disclaimer."""
import streamlit as st


def render_footer() -> None:
    st.divider()
    st.caption(
        "⚠️ **Disclaimer:** Este sistema é uma ferramenta de estudo pessoal. "
        "**Não constitui recomendação de investimento.** "
        "Os scores e carteiras são modelos quantitativos experimentais, "
        "sem garantia de retorno. Backtest possui survivorship bias e assume "
        "zero custos de transação. Fórmula V2: filtros F1 (MMA20/50) + F2 (ROIC>0%), "
        "fatores momentum (50%) + ROE (30%) + CAGR5a (20%). "
        "Invista com responsabilidade."
    )
