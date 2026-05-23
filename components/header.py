"""Header global — título + badge de status da última atualização."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

import config


def render_header() -> None:
    st.title("Small Cap Momentum Tracker")
    st.caption(
        "Universo: 50 small caps brasileiras (R$500M–15B) | "
        "Carteira teórica semanal Top 5 | Fórmula V2"
    )

    summary_path = config.LAST_RUN_SUMMARY_PATH
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        status = summary.get("status", "unknown")
        ts_raw = summary.get("timestamp", "")
        ts = ts_raw[:16].replace("T", " às ") if ts_raw else ""

        if status == "success":
            st.success(f"✅ Atualizado em {ts}")
        elif status == "degraded":
            st.warning(f"⚠️ Atualização parcial — {ts}")
        elif status == "failed":
            st.error(f"🔴 Falha na última atualização — {ts}")
        else:
            st.info(f"⚪ Status desconhecido — {ts or 'sem timestamp'}")
    except FileNotFoundError:
        st.info("⚪ Dados ainda não carregados — execute o pipeline primeiro.")
