"""Header global — título tipográfico + linha de status sóbria."""
from __future__ import annotations

import json

import streamlit as st

import config


def _render_status_strip() -> None:
    """Linha fina abaixo do título com o estado da última execução."""
    summary_path = config.LAST_RUN_SUMMARY_PATH
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        status = summary.get("status", "unknown")
        ts_raw = summary.get("timestamp", "")
        ts     = ts_raw[:16].replace("T", " · ") if ts_raw else "—"

        cores = {
            "success":  ("#1F7A4B", "Operacional"),
            "degraded": ("#A86A1F", "Atualização parcial"),
            "failed":   ("#A02C2C", "Falha na execução"),
        }
        cor, rotulo = cores.get(status, ("#888", "Estado desconhecido"))

        st.markdown(
            f"""
            <div style='display:flex; align-items:center; gap:14px;
                        padding:10px 0; border-bottom:1px solid #E5E5E5;
                        margin-bottom:28px;'>
              <span style='width:8px; height:8px; border-radius:50%;
                           background:{cor}; display:inline-block;'></span>
              <span style='font-size:0.78rem; text-transform:uppercase;
                           letter-spacing:0.8px; color:{cor}; font-weight:600;'>
                {rotulo}
              </span>
              <span style='font-size:0.78rem; color:#888;
                           letter-spacing:0.4px;'>
                Última execução · {ts}
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except FileNotFoundError:
        st.markdown(
            """
            <div style='display:flex; align-items:center; gap:14px;
                        padding:10px 0; border-bottom:1px solid #E5E5E5;
                        margin-bottom:28px;'>
              <span style='width:8px; height:8px; border-radius:50%;
                           background:#888; display:inline-block;'></span>
              <span style='font-size:0.78rem; text-transform:uppercase;
                           letter-spacing:0.8px; color:#888; font-weight:600;'>
                Aguardando primeira execução
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_header() -> None:
    """Header em layout editorial: título serifado + subtítulo + status."""
    st.markdown(
        """
        <div style='padding-bottom:8px;'>
          <div style='font-size:0.72rem; text-transform:uppercase;
                      letter-spacing:1.4px; color:#A89968; font-weight:600;
                      margin-bottom:8px;'>
            Small Cap Equity · Brazil
          </div>
          <h1 style='margin:0 0 6px 0;'>Small Cap Momentum Tracker</h1>
          <p style='margin:0; color:#555; font-size:1.0rem;
                    font-weight:400; line-height:1.5; max-width:780px;'>
            Estratégia quantitativa semanal sobre o universo de small caps
            brasileiras. Carteira teórica Top 5 reponderada toda segunda-feira.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_status_strip()
