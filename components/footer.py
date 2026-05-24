"""Rodapé minimalista — uma linha discreta no fim da página."""
import streamlit as st


def render_footer() -> None:
    st.markdown(
        """
        <div class='footer-min'>
          SmallRadar V2 · Ferramenta de estudo · Não constitui recomendação de investimento
        </div>
        """,
        unsafe_allow_html=True,
    )
