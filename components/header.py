"""Header global — título editorial + status strip discreto + próxima execução."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import streamlit as st

import config


# ---------------------------------------------------------------------------
# Próxima execução do pipeline (cron: Seg-Sex às 19h BRT)
# ---------------------------------------------------------------------------

def _proxima_execucao_pipeline() -> str:
    """Calcula próxima execução do pipeline (Seg–Sex 19:00 BRT)."""
    agora = datetime.now()
    # Pipeline roda dias úteis às 19:00 (BRT)
    candidato = agora.replace(hour=19, minute=0, second=0, microsecond=0)

    # Se já passou das 19h hoje, vai pra próximo dia útil
    if agora >= candidato:
        candidato += timedelta(days=1)

    # Pula sábado (5) e domingo (6)
    while candidato.weekday() >= 5:
        candidato += timedelta(days=1)

    dias_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    return f"{dias_pt[candidato.weekday()]} {candidato.strftime('%d/%m · %H:%M')}"


# ---------------------------------------------------------------------------
# Status strip (linha fina abaixo do título)
# ---------------------------------------------------------------------------

def _render_status_strip() -> None:
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
        cor, rotulo = cores.get(status, ("#7A7A7A", "Estado desconhecido"))
    except FileNotFoundError:
        cor, rotulo = "#7A7A7A", "Aguardando primeira execução"
        ts = "—"

    proxima = _proxima_execucao_pipeline()

    st.markdown(
        f"""
        <div style='display:flex; align-items:center; gap:24px;
                    padding:12px 0; border-bottom:1px solid #DDD8CE;
                    margin-bottom:28px; flex-wrap:wrap;'>
          <div style='display:flex; align-items:center; gap:10px;'>
            <span style='width:8px; height:8px; border-radius:50%;
                         background:{cor}; display:inline-block;'></span>
            <span style='font-size:0.76rem; text-transform:uppercase;
                         letter-spacing:0.8px; color:{cor}; font-weight:600;'>
              {rotulo}
            </span>
          </div>
          <div style='display:flex; align-items:center; gap:6px;
                      font-size:0.76rem; color:#7A7A7A;
                      letter-spacing:0.4px;'>
            <span style='text-transform:uppercase; font-weight:500;
                         letter-spacing:0.8px;'>Última execução</span>
            <span style='color:#4A4A4A;'>{ts}</span>
          </div>
          <div style='display:flex; align-items:center; gap:6px;
                      font-size:0.76rem; color:#7A7A7A;
                      letter-spacing:0.4px;'>
            <span style='text-transform:uppercase; font-weight:500;
                         letter-spacing:0.8px;'>Próxima</span>
            <span style='color:#4A4A4A;'>{proxima}</span>
          </div>
          <div style='margin-left:auto; font-size:0.7rem;
                      letter-spacing:0.9px; text-transform:uppercase;
                      color:#A8A8A8; font-weight:500;'>
            v2.1
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header principal
# ---------------------------------------------------------------------------

def render_header() -> None:
    st.markdown(
        """
        <div style='padding-bottom:8px;'>
          <div style='font-size:0.72rem; text-transform:uppercase;
                      letter-spacing:1.4px; color:#A89968; font-weight:600;
                      margin-bottom:8px;'>
            Small Cap Equity · Brazil
          </div>
          <h1 style='margin:0 0 6px 0;'>Small Cap Momentum Tracker</h1>
          <p style='margin:0; color:#4A4A4A; font-size:1.0rem;
                    font-weight:400; line-height:1.5; max-width:780px;'>
            Estratégia quantitativa semanal sobre o universo de small caps
            brasileiras. Carteira teórica Top 5 reponderada toda segunda-feira.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_status_strip()
