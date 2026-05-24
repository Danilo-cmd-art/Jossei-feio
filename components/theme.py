"""
Tema visual estilo Goldman Sachs — paleta sóbria + tipografia serifada + cards refinados.
Injeta CSS global. Deve ser chamado uma vez logo após st.set_page_config().
"""
from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Paleta de cores (exportada para uso em gráficos Altair)
# ---------------------------------------------------------------------------
COLORS = {
    "primary":     "#1B365D",   # Navy principal (Carteira / Estratégia)
    "primary_alt": "#2A4D7A",   # Navy claro (hover/links)
    "accent":      "#A89968",   # Dourado (destaques sutis)
    "ink":         "#1A1A1A",   # Texto principal
    "ink_soft":    "#555555",   # Texto secundário
    "muted":       "#888888",   # Cinza neutro 1
    "muted_2":     "#B5B5B5",   # Cinza neutro 2
    "muted_3":     "#D8D8D8",   # Cinza neutro 3 (mais claro)
    "surface":     "#FFFFFF",   # Fundo cards
    "canvas":      "#FAFAF8",   # Fundo página alternativo
    "border":      "#E5E5E5",   # Bordas sutis
    "success":     "#1F7A4B",   # Verde sóbrio
    "danger":      "#A02C2C",   # Vermelho sóbrio
}

# Paleta dos gráficos (Carteira vs benchmarks)
CHART_PALETTE = {
    "Carteira V2":   COLORS["primary"],
    "Estratégia V2": COLORS["primary"],
    "IBOV":          COLORS["ink_soft"],
    "SMAL11":        COLORS["muted"],
    "CDI":           COLORS["muted_3"],
}


# ---------------------------------------------------------------------------
# CSS global (injetado uma única vez por sessão)
# ---------------------------------------------------------------------------
def aplicar_tema() -> None:
    st.markdown(
        """
        <style>
        /* === Tipografia ============================================== */
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+Pro:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');

        html, body, [class*="css"], .stMarkdown, .stCaption {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            color: #1A1A1A;
            font-feature-settings: 'kern' 1, 'liga' 1;
        }

        h1, h2, h3, h4, h5, h6,
        [data-testid="stHeader"] h1,
        .stApp h1, .stApp h2, .stApp h3 {
            font-family: 'Source Serif Pro', Georgia, 'Times New Roman', serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.015em;
            color: #1B365D !important;
        }

        h1 { font-size: 2.4rem  !important; line-height: 1.15 !important; }
        h2 { font-size: 1.7rem  !important; line-height: 1.25 !important; }
        h3 { font-size: 1.3rem  !important; line-height: 1.3  !important; }

        /* === Linhas e seções ========================================= */
        hr, [data-testid="stMarkdownContainer"] hr {
            border: none;
            border-top: 1px solid #E5E5E5;
            margin: 28px 0 !important;
        }

        /* Subheaders (st.subheader) — barra dourada lateral discreta */
        h3 + div, .stMarkdown h3 {
            border-left: 3px solid #A89968;
            padding-left: 14px;
        }

        /* === Cards de métrica ======================================== */
        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E5E5E5;
            border-radius: 2px;
            padding: 18px 22px;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        [data-testid="stMetric"]:hover {
            border-color: #1B365D;
            box-shadow: 0 2px 12px rgba(27, 54, 93, 0.06);
        }

        [data-testid="stMetricLabel"] {
            color: #555 !important;
            font-size: 0.78rem !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.6px;
        }

        [data-testid="stMetricValue"] {
            color: #1A1A1A !important;
            font-family: 'Source Serif Pro', Georgia, serif !important;
            font-weight: 600 !important;
            font-size: 1.9rem !important;
            line-height: 1.1 !important;
        }

        [data-testid="stMetricDelta"] {
            font-weight: 500 !important;
            font-size: 0.88rem !important;
        }

        /* === Tabs ==================================================== */
        [data-baseweb="tab-list"] {
            gap: 4px !important;
            border-bottom: 1px solid #E5E5E5 !important;
            padding-bottom: 0 !important;
        }

        [data-baseweb="tab"] {
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.4px !important;
            font-size: 0.95rem !important;
            color: #555 !important;
            padding: 12px 24px !important;
            border-bottom: 2px solid transparent !important;
        }

        [data-baseweb="tab"][aria-selected="true"] {
            color: #1B365D !important;
            border-bottom-color: #1B365D !important;
        }

        /* === Sidebar ================================================= */
        [data-testid="stSidebar"] {
            background: #F4F4F2 !important;
            border-right: 1px solid #E5E5E5;
        }

        [data-testid="stSidebar"] h2 {
            font-size: 1.05rem !important;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #1B365D !important;
            border-left: none;
            padding-left: 0;
        }

        [data-testid="stSidebar"] .stRadio label {
            font-size: 0.92rem !important;
        }

        /* === DataFrames ============================================== */
        [data-testid="stDataFrame"] {
            border: 1px solid #E5E5E5 !important;
            border-radius: 2px !important;
        }

        [data-testid="stDataFrame"] thead {
            background: #FAFAF8 !important;
            font-family: 'Inter', sans-serif !important;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            font-size: 0.78rem !important;
            color: #555 !important;
        }

        /* === Alerts (success/info/warning/error) ===================== */
        [data-testid="stAlert"] {
            border-radius: 2px !important;
            border-left-width: 3px !important;
            border-top: none !important;
            border-right: none !important;
            border-bottom: none !important;
            padding: 14px 18px !important;
        }

        /* === Expanders =============================================== */
        [data-testid="stExpander"] {
            border: 1px solid #E5E5E5 !important;
            border-radius: 2px !important;
        }

        /* === Buttons ================================================= */
        .stButton > button, .stDownloadButton > button {
            background: #1B365D !important;
            color: #FFFFFF !important;
            border: 1px solid #1B365D !important;
            border-radius: 2px !important;
            padding: 8px 24px !important;
            font-weight: 500 !important;
            letter-spacing: 0.6px !important;
            text-transform: uppercase !important;
            font-size: 0.82rem !important;
            transition: background 0.2s ease;
        }

        .stButton > button:hover, .stDownloadButton > button:hover {
            background: #2A4D7A !important;
            border-color: #2A4D7A !important;
        }

        /* === Reduzir padding superior da página ===================== */
        .main .block-container {
            padding-top: 2.4rem !important;
            max-width: 1320px;
        }

        /* === Captions / disclaimer =================================== */
        [data-testid="stCaptionContainer"] {
            color: #666 !important;
            font-size: 0.85rem !important;
            line-height: 1.5 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
