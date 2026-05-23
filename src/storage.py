"""Leitura e escrita do Parquet de preços — PHASE2_SPEC §4."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

import config
from src.logger import get_logger

log = get_logger()

SCHEMA_COLS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]


def ler_precos() -> pd.DataFrame | None:
    """Lê precos.parquet. Retorna None se não existir."""
    if not config.PRECOS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.PRECOS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


def salvar_precos(df: pd.DataFrame) -> None:
    """Escrita atômica: grava em temp e renomeia — evita corrupção parcial."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.DATA_DIR / "_precos_tmp.parquet"
    df.to_parquet(tmp, engine="pyarrow", compression="snappy", index=False)
    tmp.replace(config.PRECOS_PARQUET_PATH)
    log.info(f"precos.parquet salvo: {len(df):,} linhas")


def merge_incremental(df_existente: pd.DataFrame, df_novo: pd.DataFrame) -> pd.DataFrame:
    """
    Combina dados existentes com novos.
    Para cada (date, ticker) que já existe, mantém o dado existente (não sobrescreve),
    mas adiciona linhas novas.
    """
    if df_existente is None or df_existente.empty:
        return df_novo
    if df_novo is None or df_novo.empty:
        return df_existente

    df_novo["date"] = pd.to_datetime(df_novo["date"])
    df_existente["date"] = pd.to_datetime(df_existente["date"])

    combinado = pd.concat([df_existente, df_novo], ignore_index=True)
    combinado = combinado.drop_duplicates(subset=["date", "ticker"], keep="last")
    combinado = combinado.sort_values(["ticker", "date"]).reset_index(drop=True)
    return combinado


def ultima_data_por_ticker(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Retorna {ticker: ultima_data} para download incremental."""
    if df is None or df.empty:
        return {}
    return df.groupby("ticker")["date"].max().to_dict()
