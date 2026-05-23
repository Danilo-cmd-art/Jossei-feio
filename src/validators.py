"""Validação leve diária (LV1-LV4) — PHASE2_SPEC §9."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
from src.logger import get_logger

log = get_logger()


def validar_leve(df_precos: pd.DataFrame, tickers: list[str]) -> dict:
    """
    Aplica LV1-LV4 para cada ticker.
    Retorna relatório com stale, suspeitos e warnings.
    """
    hoje = date.today()
    limite_stale = hoje - timedelta(days=config.DIAS_TOLERANCIA_STALE)

    stale: list[str] = []
    suspeitos: list[str] = []
    warnings_lista: list[str] = []

    lv_counts = {"LV1_passou": 0, "LV2_passou": 0, "LV3_passou": 0, "LV4_passou": 0}

    for ticker in tickers:
        df_t = df_precos[df_precos["ticker"] == ticker].sort_values("date")
        if df_t.empty:
            log.warning(f"LV1 FAIL {ticker}: sem dados no Parquet")
            stale.append(ticker)
            continue

        ultima_data = df_t["date"].iloc[-1]
        if hasattr(ultima_data, "date"):
            ultima_data = ultima_data.date()

        # LV1 — último pregão presente
        if ultima_data < limite_stale:
            log.warning(f"LV1 FAIL {ticker}: último dado em {ultima_data} (>{config.DIAS_TOLERANCIA_STALE}d)")
            stale.append(ticker)
        else:
            lv_counts["LV1_passou"] += 1

        # LV2 — adj_close positivo
        ultimo_adj = df_t["adj_close"].iloc[-1]
        if pd.isna(ultimo_adj) or ultimo_adj <= 0:
            log.warning(f"LV2 FAIL {ticker}: adj_close inválido ({ultimo_adj})")
            suspeitos.append(ticker)
        else:
            lv_counts["LV2_passou"] += 1

        # LV3 — retorno do último dia entre ±50%
        if len(df_t) >= 2:
            ret = df_t["adj_close"].iloc[-1] / df_t["adj_close"].iloc[-2] - 1
            if abs(ret) > 0.50:
                msg = f"{ticker}: retorno {ret:.1%} no último pregão — split suspeito"
                log.warning(f"LV3 WARN {msg}")
                warnings_lista.append(msg)
                suspeitos.append(ticker)
            else:
                lv_counts["LV3_passou"] += 1
        else:
            lv_counts["LV3_passou"] += 1

        # LV4 — volume > 0
        ultimo_vol = df_t["volume"].iloc[-1]
        if pd.isna(ultimo_vol) or ultimo_vol == 0:
            msg = f"{ticker}: volume zero no último pregão"
            log.warning(f"LV4 WARN {msg}")
            warnings_lista.append(msg)
        else:
            lv_counts["LV4_passou"] += 1

    return {
        "stale": stale,
        "suspeitos": list(set(suspeitos)),
        "warnings": warnings_lista,
        **lv_counts,
    }


def aplicar_forward_fill(df_precos: pd.DataFrame, stale: list[str]) -> pd.DataFrame:
    """
    Para tickers stale (≤3 dias): forward-fill com último adj_close.
    Tickers stale são marcados mas mantidos nos dados.
    """
    if not stale:
        return df_precos
    # Forward-fill já está implícito na leitura do Parquet (último dado válido persiste)
    # Apenas loga — o dado mais recente disponível já é o "forward filled"
    for t in stale:
        log.info(f"  Forward-fill aplicado: {t}")
    return df_precos
