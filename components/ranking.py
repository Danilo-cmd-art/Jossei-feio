"""Aba 2 — Ranking V2 (tabela + breakdown F1/F2/fatores)."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from utils.formatters import fmt_data_br, fmt_pct, fmt_reais


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_scores() -> dict | None:
    if not config.SCORES_V2_ATUAL_PATH.exists():
        return None
    with open(config.SCORES_V2_ATUAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def _carregar_carteira_tickers() -> set[str]:
    if not config.CARTEIRA_V2_ATUAL_PATH.exists():
        return set()
    with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
        c = json.load(f)
    return {t["ticker"] for t in c.get("tickers", [])}


# ---------------------------------------------------------------------------
# Helpers visuais
# ---------------------------------------------------------------------------

def _render_tendencia_f1(score_dict: dict) -> str:
    """
    3 bolinhas representando os critérios do F1 (MMA20/50):
    preco>MMA20 | preco>MMA50 | MMA20>MMA50
    """
    fat = score_dict.get("fatores", {})
    f1 = fat.get("filtro_f1", {})
    det = f1.get("detalhe")

    if det is None:
        # Sem detalhe (histórico insuficiente)
        passou = f1.get("passou", False)
        return "❌ dados insuf." if not passou else "✅"

    c1 = "🟢" if det.get("preco_acima_mma20") else "⬜"
    c2 = "🟢" if det.get("preco_acima_mma50") else "⬜"
    c3 = "🟢" if det.get("mma20_acima_mma50") else "⬜"
    return f"{c1}{c2}{c3}"


# ---------------------------------------------------------------------------
# Breakdown expandido (V2)
# ---------------------------------------------------------------------------

def _render_breakdown_v2(s: dict) -> None:
    """Detalhe completo de um ticker: filtros + fatores de score."""
    fat = s.get("fatores", {})
    passou = s.get("passou_filtros_entrada", False)

    # --- Filtros de entrada ---
    st.markdown("**🔍 Filtros de Entrada**")

    f1 = fat.get("filtro_f1", {})
    f2 = fat.get("filtro_f2", {})
    det_f1 = f1.get("detalhe")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        icone_f1 = "✅" if f1.get("passou") else "❌"
        st.markdown(f"**F1 — Tendência MMA20/50: {icone_f1}**")
        if det_f1:
            c1 = "✅" if det_f1.get("preco_acima_mma20") else "❌"
            c2 = "✅" if det_f1.get("preco_acima_mma50") else "❌"
            c3 = "✅" if det_f1.get("mma20_acima_mma50") else "❌"
            st.write(f"P > MMA20: {c1}  |  P > MMA50: {c2}  |  MMA20 > MMA50: {c3}")
            st.write(
                f"Preço: {fmt_reais(det_f1.get('preco_atual'))} | "
                f"MMA20: {fmt_reais(det_f1.get('mma20'))} | "
                f"MMA50: {fmt_reais(det_f1.get('mma50'))} | "
                f"Pontos: {det_f1.get('pontos', 0)}/3"
            )
        else:
            st.write("Histórico insuficiente para calcular MMA20/50.")

    with col_f2:
        icone_f2 = "✅" if f2.get("passou") else "❌"
        roic = f2.get("roic_bruto")
        roic_str = f"{roic:.1f}%" if roic is not None else "n/d (aprovado por padrão)"
        st.markdown(f"**F2 — ROIC > 0%: {icone_f2}**")
        st.write(f"ROIC: {roic_str}")

    if not passou:
        st.warning("Ação reprovada nos filtros — sem score calculado.")
        return

    st.divider()
    st.markdown("**📊 Fatores de Score**")

    col_a, col_b, col_c = st.columns(3)

    # Fator A — Momentum 50%
    with col_a:
        mom = fat.get("momentum", {})
        st.markdown("**A) Momentum (50%)**")
        r1m = mom.get("ret_1m")
        r3m = mom.get("ret_3m")
        st.write(
            f"ret 1m: {fmt_pct(r1m, sinal=True)}  |  "
            f"ret 3m: {fmt_pct(r3m, sinal=True)}"
        )
        st.write(
            f"Bruto: {fmt_pct(mom.get('bruto'), sinal=True)} → "
            f"Norm: {mom.get('normalizado', '—'):.0f} → "
            f"Contrib: {mom.get('contribuicao_score', 0):.1f}"
        )

    # Fator B — ROE 30%
    with col_b:
        roe = fat.get("roe", {})
        st.markdown("**B) ROE (30%)**")
        missing_str = " *(missing — mediana 50)*" if roe.get("is_missing") else ""
        bruto_roe = roe.get("bruto")
        bruto_str = f"{bruto_roe:.1f}%" if bruto_roe is not None else "n/d"
        st.write(f"Bruto: {bruto_str}{missing_str}")
        st.write(
            f"Norm: {roe.get('normalizado', '—'):.0f} → "
            f"Contrib: {roe.get('contribuicao_score', 0):.1f}"
        )

    # Fator C — CAGR 5a 20%
    with col_c:
        cagr = fat.get("cagr_receita", {})
        st.markdown("**C) CAGR Receita 5a (20%)**")
        missing_str = " *(missing — mediana 50)*" if cagr.get("is_missing") else ""
        fallback_str = " *(proxy 5a)*" if cagr.get("usando_fallback_5a") else ""
        bruto_cagr = cagr.get("bruto")
        bruto_str = f"{bruto_cagr:.1f}%" if bruto_cagr is not None else "n/d"
        st.write(f"Bruto: {bruto_str}{missing_str}{fallback_str}")
        st.write(
            f"Norm: {cagr.get('normalizado', '—'):.0f} → "
            f"Contrib: {cagr.get('contribuicao_score', 0):.1f}"
        )

    st.markdown(
        f"**Score final: `{s.get('score_final', 0):.2f}`** "
        f"(momentum {fat.get('momentum', {}).get('contribuicao_score', 0):.1f} + "
        f"ROE {fat.get('roe', {}).get('contribuicao_score', 0):.1f} + "
        f"CAGR {fat.get('cagr_receita', {}).get('contribuicao_score', 0):.1f})"
    )


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_ranking() -> None:
    dados = _carregar_scores()

    if dados is None:
        st.error(
            "Scores V2 ainda não calculados. "
            "Execute `python run_v2.py --fase 3` primeiro."
        )
        render_footer()
        return

    meta = dados["metadata"]
    scores = dados["scores"]
    carteira_tickers = _carregar_carteira_tickers()

    st.markdown(
        f"**Data de referência:** {fmt_data_br(meta.get('data_referencia'))} | "
        f"**Corte de dados:** {fmt_data_br(meta.get('data_corte_dados'))} | "
        f"**Tickers:** {meta.get('total_tickers')} | "
        f"**Fórmula:** {meta.get('versao_formula', 'v2').upper()}"
    )

    # Monta tabela
    rows = []
    for s in scores:
        rows.append({
            "Rank": s.get("rank", "—"),
            "Ticker": s["ticker"],
            "Score": f"{s['score_final']:.1f}" if s.get("passou_filtros_entrada") else "—",
            "F1 MMA20/50": _render_tendencia_f1(s),
            "F2 ROIC>0%": "✅" if s.get("passou_filtro_f2") else "❌",
            "Passou": "✅" if s.get("passou_filtros_entrada") else "❌",
            "Carteira": "⭐" if s["ticker"] in carteira_tickers else "",
        })

    df_rank = pd.DataFrame(rows)

    event = st.dataframe(
        df_rank,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # Breakdown da linha selecionada
    if event.selection.rows:
        idx = event.selection.rows[0]
        s_sel = scores[idx]
        with st.expander(
            f"📊 Breakdown — {s_sel['ticker']} (rank #{s_sel.get('rank', '?')})",
            expanded=True,
        ):
            _render_breakdown_v2(s_sel)

    render_footer()
