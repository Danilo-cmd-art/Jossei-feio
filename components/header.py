"""Header global — hero band azul navy com título editorial + status strip."""
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
    candidato = agora.replace(hour=19, minute=0, second=0, microsecond=0)

    if agora >= candidato:
        candidato += timedelta(days=1)

    while candidato.weekday() >= 5:
        candidato += timedelta(days=1)

    dias_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    return f"{dias_pt[candidato.weekday()]} {candidato.strftime('%d/%m · %H:%M')}"


# ---------------------------------------------------------------------------
# Status strip (linha fina abaixo do título — sobre fundo navy)
# ---------------------------------------------------------------------------

def _render_status_strip() -> None:
    summary_path = config.LAST_RUN_SUMMARY_PATH
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        status = summary.get("status", "unknown")
        ts_raw = summary.get("timestamp", "")
        ts     = ts_raw[:16].replace("T", " · ") if ts_raw else "—"

        # Cores semânticas adaptadas para fundo navy escuro (versões luminosas)
        cores = {
            "success":  ("#4ADE80", "Operacional"),
            "degraded": ("#F2B65A", "Atualização parcial"),
            "failed":   ("#F47171", "Falha na execução"),
        }
        cor, rotulo = cores.get(status, ("#8A9AB0", "Estado desconhecido"))
    except FileNotFoundError:
        cor, rotulo = "#8A9AB0", "Aguardando primeira execução"
        ts = "—"

    proxima = _proxima_execucao_pipeline()

    st.markdown(
        f"""
        <div class='hero-status-strip'>
          <div class='hero-status-pill'>
            <span class='hero-status-dot' style='background:{cor};
                  box-shadow:0 0 0 3px {cor}22;'></span>
            <span style='font-size:0.74rem; text-transform:uppercase;
                         letter-spacing:0.9px; color:{cor}; font-weight:600;'>
              {rotulo}
            </span>
          </div>

          <div style='display:flex; align-items:baseline; gap:8px;'>
            <span class='hero-status-label'>Última execução</span>
            <span class='hero-status-value'>{ts}</span>
          </div>

          <div style='display:flex; align-items:baseline; gap:8px;'>
            <span class='hero-status-label'>Próxima</span>
            <span class='hero-status-value'>{proxima}</span>
          </div>

          <div class='hero-version-badge'>v3c</div>
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
        <div style='padding-bottom:4px;'>
          <div class='hero-kicker'>Small Cap Equity · Brazil</div>
          <h1 class='hero-title'>Small Cap Momentum Tracker</h1>
          <p class='hero-subtitle'>
            Estratégia quantitativa semanal sobre o universo de small caps
            brasileiras. Carteira teórica Top 5 reponderada toda segunda-feira.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_status_strip()
