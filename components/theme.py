"""
Tema visual estilo Goldman Sachs — paleta sóbria + tipografia serifada + cards refinados.
Injetar CSS global. Deve ser chamado uma vez logo após st.set_page_config().
"""
from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Paleta de cores (exportada para uso em gráficos Altair e helpers)
# ---------------------------------------------------------------------------
COLORS = {
    # Navy / dourado
    "primary":      "#1B365D",   # Navy principal
    "primary_alt":  "#2A4D7A",   # Navy claro (hover / links)
    "accent":       "#A89968",   # Dourado quente
    "accent_deep":  "#7A6F4D",   # Dourado profundo (detalhes)
    # Textos
    "ink":          "#1A1A1A",
    "ink_soft":     "#4A4A4A",
    "muted":        "#7A7A7A",
    "muted_2":      "#A8A8A8",
    "muted_3":      "#D2CCC0",
    # Superfícies
    "surface":      "#FFFFFF",
    "canvas":       "#FAFAF7",
    "canvas_warm":  "#F4EFE5",   # bege claro (banner sutil)
    "border":       "#DDD8CE",
    # Semânticos (positivo / negativo) — tons sóbrios
    "pos":          "#1F7A4B",
    "pos_bg":       "#E8F1EC",
    "neg":          "#A02C2C",
    "neg_bg":       "#F4E6E6",
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
            font-feature-settings: 'kern' 1, 'liga' 1, 'tnum' 1;
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

        /* === App background ========================================== */
        .stApp { background: #FAFAF7 !important; }

        /* === Linhas e seções ========================================= */
        hr, [data-testid="stMarkdownContainer"] hr {
            border: none;
            border-top: 1px solid #DDD8CE;
            margin: 28px 0 !important;
        }

        /* Subheaders (st.subheader) — barra dourada lateral discreta */
        .stMarkdown h3 {
            border-left: 3px solid #A89968;
            padding-left: 14px;
        }

        /* === Cards de métrica ======================================== */
        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #DDD8CE;
            border-radius: 2px;
            padding: 18px 22px;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        [data-testid="stMetric"]:hover {
            border-color: #1B365D;
            box-shadow: 0 2px 14px rgba(27, 54, 93, 0.06);
        }

        [data-testid="stMetricLabel"] {
            color: #4A4A4A !important;
            font-size: 0.76rem !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.7px;
        }

        [data-testid="stMetricValue"] {
            color: #1A1A1A !important;
            font-family: 'Source Serif Pro', Georgia, serif !important;
            font-weight: 600 !important;
            font-size: 1.95rem !important;
            line-height: 1.1 !important;
            font-feature-settings: 'tnum' 1;
        }

        [data-testid="stMetricDelta"] {
            font-weight: 500 !important;
            font-size: 0.85rem !important;
        }

        /* === Tabs ==================================================== */
        [data-baseweb="tab-list"] {
            gap: 4px !important;
            border-bottom: 1px solid #DDD8CE !important;
            padding-bottom: 0 !important;
            background: transparent !important;
        }

        [data-baseweb="tab"] {
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.4px !important;
            font-size: 0.95rem !important;
            color: #4A4A4A !important;
            padding: 12px 24px !important;
            border-bottom: 2px solid transparent !important;
            background: transparent !important;
        }

        [data-baseweb="tab"][aria-selected="true"] {
            color: #1B365D !important;
            border-bottom-color: #1B365D !important;
        }

        /* === Sidebar ================================================= */
        [data-testid="stSidebar"] {
            background: #EFEAE0 !important;
            border-right: 1px solid #DDD8CE;
        }

        [data-testid="stSidebar"] h2 {
            font-size: 1.0rem !important;
            text-transform: uppercase;
            letter-spacing: 0.9px;
            color: #1B365D !important;
            border-left: none;
            padding-left: 0;
        }

        [data-testid="stSidebar"] .stRadio label {
            font-size: 0.92rem !important;
            color: #1A1A1A !important;
        }

        /* === DataFrames ============================================== */
        [data-testid="stDataFrame"] {
            border: 1px solid #DDD8CE !important;
            border-radius: 2px !important;
        }

        [data-testid="stDataFrame"] thead {
            background: #F4EFE5 !important;
            font-family: 'Inter', sans-serif !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 0.75rem !important;
            color: #4A4A4A !important;
        }

        /* === Alerts: nosso próprio banner via div, escondemos st.info */
        /* Mantém alerts mas com visual sóbrio caso usados */
        [data-testid="stAlert"] {
            border-radius: 2px !important;
            border-left-width: 3px !important;
            border-top: none !important;
            border-right: none !important;
            border-bottom: none !important;
            padding: 14px 18px !important;
            background: #F4EFE5 !important;
            color: #4A4A4A !important;
        }

        [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
            color: #4A4A4A !important;
        }

        /* === Expanders =============================================== */
        [data-testid="stExpander"] {
            border: 1px solid #DDD8CE !important;
            border-radius: 2px !important;
            background: #FFFFFF;
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

        /* === Container principal ==================================== */
        .main .block-container {
            padding-top: 2.4rem !important;
            padding-bottom: 4rem !important;
            max-width: 1320px;
        }

        /* === Captions ================================================ */
        [data-testid="stCaptionContainer"] {
            color: #7A7A7A !important;
            font-size: 0.82rem !important;
            line-height: 1.5 !important;
        }

        /* === Banner editorial customizado =========================== */
        .editorial-banner {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #F4EFE5;
            border-left: 3px solid #A89968;
            padding: 12px 18px;
            margin: 16px 0 24px 0;
            font-size: 0.88rem;
            color: #4A4A4A;
        }

        /* Tag inline (próxima reponderação, etc.) */
        .tag-inline {
            display: inline-block;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 600;
            color: #7A6F4D;
            background: #F4EFE5;
            border: 1px solid #DDD8CE;
            padding: 4px 10px;
            border-radius: 2px;
        }

        /* Footer minimalista */
        .footer-min {
            border-top: 1px solid #DDD8CE;
            margin-top: 48px;
            padding-top: 16px;
            text-align: center;
            font-size: 0.74rem;
            color: #A8A8A8;
            letter-spacing: 0.3px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
