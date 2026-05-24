"""Rodapé com disclaimer em bloco editorial."""
import streamlit as st


def render_footer() -> None:
    st.markdown(
        """
        <div style='
            background:#FAFAF8;
            border-left:3px solid #A89968;
            padding:16px 20px;
            margin-top:32px;
            font-size:0.82rem;
            line-height:1.6;
            color:#555;
        '>
          <div style='font-size:0.72rem; text-transform:uppercase;
                      letter-spacing:1.2px; color:#A89968; font-weight:600;
                      margin-bottom:6px;'>
            Aviso Legal
          </div>
          <strong style='color:#1A1A1A;'>Não constitui recomendação de investimento.</strong>
          Ferramenta de estudo pessoal. Os scores e carteiras são modelos
          quantitativos experimentais, sem garantia de retorno. O backtest possui
          <em>survivorship bias</em> e assume zero custos de transação.
          Fórmula V2: filtros F1 (MMA 20/50) + F2 (ROIC > 0%); fatores Momentum
          50% + ROE 30% + CAGR 5a 20%. Invista com responsabilidade.
        </div>
        """,
        unsafe_allow_html=True,
    )
