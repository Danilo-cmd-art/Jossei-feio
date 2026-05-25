"""
Tema visual SmallRadar V3c — paleta editorial sóbria.

Estrutura:
  • Header (hero band): fundo azul navy escuro #0F2240 com texto branco/dourado
  • Tabs navigation: continua na hero band azul, sublinhada em dourado
  • Conteúdo das tabs: superfície branca elevada, contraste claro com a hero

Paleta restrita a quatro cores: branco, preto, azul navy e dourado.
Verde/vermelho semânticos são usados APENAS em retornos (pos/neg) — ínfima
área da UI, justificável para legibilidade financeira.

Build: 2026-05-25T13:00 — redeploy forçado para invalidar cache do Streamlit Cloud.
"""
from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Paleta de cores (exportada para uso em gráficos Altair e helpers)
# ---------------------------------------------------------------------------
COLORS = {
    # Navy / dourado (paleta principal)
    "primary":        "#1B365D",   # Navy clássico (gráficos, accent)
    "primary_alt":    "#2A4D7A",   # Navy claro (hover / links)
    "hero":           "#0F2240",   # Navy escuro (hero band background)
    "hero_alt":       "#15304F",   # Navy intermediário (status strip)
    "accent":         "#C9A961",   # Dourado luminoso (tags sobre azul)
    "accent_warm":    "#A89968",   # Dourado clássico (gráficos e detalhes)
    "accent_deep":    "#7A6F4D",   # Dourado profundo (detalhes sutis)
    # Textos
    "ink":            "#0F1419",   # Preto suave (texto principal sobre branco)
    "ink_soft":       "#3A4654",
    "muted":          "#6B7785",
    "muted_2":        "#A5AEBC",
    "muted_3":        "#D8DEE5",
    # Textos sobre fundo azul (hero band)
    "on_hero":        "#FFFFFF",
    "on_hero_soft":   "#C8D3E2",   # Azul-cinza claro (descrição sobre azul)
    "on_hero_muted":  "#8A9AB0",   # Azul cinza médio (labels sobre azul)
    # Superfícies
    "surface":        "#FFFFFF",   # Branco puro (cards)
    "canvas":         "#F7F5F0",   # Bege papel (fundo das tabs)
    "canvas_warm":    "#F4EFE5",   # Bege quente (banners)
    "border":         "#E2DED4",
    "border_soft":    "#EEEAE0",
    # Semânticos (positivo / negativo)
    "pos":            "#1F7A4B",
    "pos_bg":         "#E8F1EC",
    "neg":            "#A02C2C",
    "neg_bg":         "#F4E6E6",
}

# Paleta dos gráficos (Carteira vs benchmarks) — paleta restrita
CHART_PALETTE = {
    "Carteira V2":   COLORS["primary"],
    "Carteira V3c":  COLORS["primary"],
    "Estratégia V2": COLORS["primary"],
    "IBOV":          COLORS["accent_warm"],
    "SMAL11":        COLORS["muted"],
    "CDI":           COLORS["muted_2"],
}


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------
def aplicar_tema() -> None:
    st.markdown(
        f"""
        <style>
        /* === Tipografia ============================================== */
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+Pro:wght@400;600;700&family=Inter:wght@300;400;500;600;700&display=swap');

        html, body, [class*="css"], .stMarkdown, .stCaption {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            color: {COLORS["ink"]};
            font-feature-settings: 'kern' 1, 'liga' 1, 'tnum' 1;
        }}

        /* Headings serifados — mas SOMENTE no conteúdo das tabs (não no header global) */
        [data-baseweb="tab-panel"] h1,
        [data-baseweb="tab-panel"] h2,
        [data-baseweb="tab-panel"] h3,
        [data-baseweb="tab-panel"] h4 {{
            font-family: 'Source Serif Pro', Georgia, 'Times New Roman', serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.015em;
            color: {COLORS["primary"]} !important;
        }}

        [data-baseweb="tab-panel"] h1 {{ font-size: 2.0rem  !important; line-height: 1.15 !important; }}
        [data-baseweb="tab-panel"] h2 {{ font-size: 1.5rem  !important; line-height: 1.25 !important; }}
        [data-baseweb="tab-panel"] h3 {{ font-size: 1.2rem  !important; line-height: 1.3  !important;
                                          border-left: 3px solid {COLORS["accent_warm"]};
                                          padding-left: 14px; }}

        /* === HERO BAND: fundo azul navy estende full-width ============ */
        .stApp {{
            background: {COLORS["hero"]} !important;
        }}

        /* Block container vira "vidro" — fundo da hero sangra através */
        .main .block-container {{
            padding-top: 2.2rem !important;
            padding-bottom: 4rem !important;
            max-width: 1320px;
            background: transparent !important;
        }}

        /* === TAB NAVIGATION: claras sobre fundo navy ================== */
        [data-baseweb="tab-list"] {{
            gap: 4px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.12) !important;
            padding-bottom: 0 !important;
            background: transparent !important;
            margin-top: 8px;
        }}

        [data-baseweb="tab"] {{
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            letter-spacing: 0.5px !important;
            font-size: 0.92rem !important;
            color: {COLORS["on_hero_soft"]} !important;
            padding: 14px 26px !important;
            border-bottom: 2px solid transparent !important;
            background: transparent !important;
            text-transform: uppercase;
            transition: color 0.18s ease, border-bottom-color 0.18s ease;
        }}

        [data-baseweb="tab"]:hover {{
            color: {COLORS["on_hero"]} !important;
        }}

        [data-baseweb="tab"][aria-selected="true"] {{
            color: {COLORS["accent"]} !important;
            border-bottom-color: {COLORS["accent"]} !important;
            font-weight: 600 !important;
        }}

        /* === TAB PANEL: card branco elevado =========================== */
        [data-baseweb="tab-panel"] {{
            background: {COLORS["canvas"]} !important;
            padding: 36px 44px 44px 44px !important;
            margin-top: 0 !important;
            border-radius: 0 0 4px 4px;
            box-shadow:
                0 2px 0 rgba(15, 34, 64, 0.4),
                0 8px 28px rgba(15, 34, 64, 0.18);
            min-height: 600px;
        }}

        /* === Cards de métrica (dentro do tab panel) =================== */
        [data-testid="stMetric"] {{
            background: {COLORS["surface"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 2px;
            padding: 20px 24px;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }}

        [data-testid="stMetric"]:hover {{
            border-color: {COLORS["primary"]};
            box-shadow: 0 2px 14px rgba(27, 54, 93, 0.08);
        }}

        [data-testid="stMetricLabel"] {{
            color: {COLORS["muted"]} !important;
            font-size: 0.74rem !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.9px;
        }}

        [data-testid="stMetricValue"] {{
            color: {COLORS["ink"]} !important;
            font-family: 'Source Serif Pro', Georgia, serif !important;
            font-weight: 600 !important;
            font-size: 1.95rem !important;
            line-height: 1.1 !important;
            font-feature-settings: 'tnum' 1;
        }}

        [data-testid="stMetricDelta"] {{
            font-weight: 500 !important;
            font-size: 0.85rem !important;
        }}

        /* === Sidebar (mantém clara) =================================== */
        [data-testid="stSidebar"] {{
            background: {COLORS["canvas_warm"]} !important;
            border-right: 1px solid {COLORS["border"]};
        }}

        [data-testid="stSidebar"] h2 {{
            font-size: 1.0rem !important;
            text-transform: uppercase;
            letter-spacing: 0.9px;
            color: {COLORS["primary"]} !important;
            border-left: none;
            padding-left: 0;
            font-family: 'Inter', sans-serif !important;
        }}

        [data-testid="stSidebar"] .stRadio label {{
            font-size: 0.92rem !important;
            color: {COLORS["ink"]} !important;
        }}

        /* Botão de colapso do sidebar (>>) — visível sobre fundo navy */
        [data-testid="collapsedControl"] {{
            color: {COLORS["on_hero"]} !important;
        }}

        /* === DataFrames =============================================== */
        [data-testid="stDataFrame"] {{
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 2px !important;
        }}

        [data-testid="stDataFrame"] thead {{
            background: {COLORS["canvas_warm"]} !important;
            font-family: 'Inter', sans-serif !important;
            text-transform: uppercase;
            letter-spacing: 0.55px;
            font-size: 0.73rem !important;
            color: {COLORS["ink_soft"]} !important;
        }}

        /* === Alerts (st.info / st.warning) ============================ */
        [data-testid="stAlert"] {{
            border-radius: 2px !important;
            border-left-width: 3px !important;
            border-top: none !important;
            border-right: none !important;
            border-bottom: none !important;
            padding: 14px 18px !important;
            background: {COLORS["canvas_warm"]} !important;
            color: {COLORS["ink_soft"]} !important;
        }}

        [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {{
            color: {COLORS["ink_soft"]} !important;
        }}

        /* === Expanders ================================================ */
        [data-testid="stExpander"] {{
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 2px !important;
            background: {COLORS["surface"]};
        }}

        /* === Buttons ================================================== */
        .stButton > button, .stDownloadButton > button {{
            background: {COLORS["primary"]} !important;
            color: {COLORS["on_hero"]} !important;
            border: 1px solid {COLORS["primary"]} !important;
            border-radius: 2px !important;
            padding: 9px 26px !important;
            font-weight: 500 !important;
            letter-spacing: 0.7px !important;
            text-transform: uppercase !important;
            font-size: 0.8rem !important;
            transition: background 0.2s ease;
        }}

        .stButton > button:hover, .stDownloadButton > button:hover {{
            background: {COLORS["primary_alt"]} !important;
            border-color: {COLORS["primary_alt"]} !important;
        }}

        /* === Inputs (text/select) ===================================== */
        [data-baseweb="input"] input,
        [data-baseweb="select"] > div {{
            background: {COLORS["surface"]} !important;
            border: 1px solid {COLORS["border"]} !important;
            border-radius: 2px !important;
        }}

        /* === Captions ================================================= */
        [data-testid="stCaptionContainer"] {{
            color: {COLORS["muted"]} !important;
            font-size: 0.82rem !important;
            line-height: 1.5 !important;
        }}

        /* === Banner editorial customizado ============================= */
        .editorial-banner {{
            display: flex;
            align-items: center;
            gap: 12px;
            background: {COLORS["canvas_warm"]};
            border-left: 3px solid {COLORS["accent_warm"]};
            padding: 12px 18px;
            margin: 16px 0 24px 0;
            font-size: 0.88rem;
            color: {COLORS["ink_soft"]};
        }}

        /* Tag inline (próxima reponderação, etc.) */
        .tag-inline {{
            display: inline-block;
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.9px;
            font-weight: 600;
            color: {COLORS["accent_deep"]};
            background: {COLORS["canvas_warm"]};
            border: 1px solid {COLORS["border"]};
            padding: 4px 11px;
            border-radius: 2px;
        }}

        /* Footer minimalista (dentro do tab panel) */
        .footer-min {{
            border-top: 1px solid {COLORS["border"]};
            margin-top: 48px;
            padding-top: 16px;
            text-align: center;
            font-size: 0.72rem;
            color: {COLORS["muted"]};
            letter-spacing: 0.4px;
        }}

        /* === HEADER global (hero) — classes utilitárias =============== */
        .hero-kicker {{
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 1.6px;
            color: {COLORS["accent"]};
            font-weight: 600;
            margin-bottom: 10px;
        }}

        .hero-title {{
            font-family: 'Source Serif Pro', Georgia, serif !important;
            font-size: 2.6rem !important;
            line-height: 1.1 !important;
            font-weight: 600 !important;
            color: {COLORS["on_hero"]} !important;
            margin: 0 0 12px 0 !important;
            letter-spacing: -0.02em;
        }}

        .hero-subtitle {{
            font-size: 1.0rem;
            color: {COLORS["on_hero_soft"]};
            font-weight: 300;
            line-height: 1.55;
            max-width: 780px;
            margin: 0;
        }}

        .hero-status-strip {{
            display: flex;
            align-items: center;
            gap: 28px;
            padding: 16px 0 18px 0;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            margin-top: 28px;
            flex-wrap: wrap;
        }}

        .hero-status-label {{
            font-size: 0.7rem;
            text-transform: uppercase;
            font-weight: 600;
            letter-spacing: 1px;
            color: {COLORS["on_hero_muted"]};
        }}

        .hero-status-value {{
            font-size: 0.86rem;
            color: {COLORS["on_hero"]};
            font-weight: 500;
            font-feature-settings: 'tnum' 1;
        }}

        .hero-status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 12px;
            border-radius: 11px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }}

        .hero-status-dot {{
            width: 7px; height: 7px;
            border-radius: 50%;
            display: inline-block;
        }}

        .hero-version-badge {{
            margin-left: auto;
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 1.4px;
            color: {COLORS["accent"]};
            text-transform: uppercase;
            border: 1px solid {COLORS["accent"]};
            padding: 4px 12px;
            border-radius: 11px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
