"""
Fase 2 — Pipeline de coleta de preços.

Download histórico via yfinance → merge com Parquet → validação leve.
PHASE2_SPEC §2-10.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

import config
from src.logger import get_logger
from src import storage, validators

log = get_logger()


# ---------------------------------------------------------------------------
# Download em lotes com retry
# ---------------------------------------------------------------------------

def _baixar_lote(tickers_yf: list[str], start: str, end: str) -> pd.DataFrame | None:
    """Baixa um lote de tickers com retry exponencial (3 tentativas)."""
    for tentativa in range(config.MAX_TENTATIVAS_RETRY):
        try:
            df = yf.download(
                tickers_yf,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                group_by="ticker",
            )
            if df is not None and not df.empty:
                return df
            return None
        except Exception as e:
            if tentativa == config.MAX_TENTATIVAS_RETRY - 1:
                log.error(f"Lote falhou após {config.MAX_TENTATIVAS_RETRY} tentativas: {e}")
                return None
            espera = config.BACKOFF_BASE_SEGUNDOS ** (tentativa + 1)
            log.warning(f"  tentativa {tentativa + 1} falhou ({e}). Retry em {espera}s.")
            time.sleep(espera)
    return None


def _extrair_ticker_df(df_multi: pd.DataFrame, ticker_yf: str) -> pd.DataFrame | None:
    """
    Extrai DataFrame de um ticker específico do resultado multi-ticker do yfinance.
    Lida com MultiIndex de colunas (quando >1 ticker no lote).
    """
    if df_multi is None or df_multi.empty:
        return None

    # yfinance retorna MultiIndex quando múltiplos tickers
    if isinstance(df_multi.columns, pd.MultiIndex):
        # yfinance 1.x: level 0 = ticker, level 1 = campo (Open/Close/...)
        level_tickers = df_multi.columns.get_level_values(0)
        level_fields = df_multi.columns.get_level_values(1)
        if ticker_yf in level_tickers:
            df_t = df_multi.xs(ticker_yf, axis=1, level=0).copy()
        elif ticker_yf in level_fields:
            # estrutura invertida (versões mais antigas)
            df_t = df_multi.xs(ticker_yf, axis=1, level=1).copy()
        else:
            return None
    else:
        # Lote de 1 ticker — colunas simples
        df_t = df_multi.copy()

    if df_t.empty:
        return None

    # Normaliza nomes de colunas
    col_map = {c: c.lower().replace(" ", "_") for c in df_t.columns}
    df_t = df_t.rename(columns=col_map)

    # Garante coluna adj_close
    if "adj_close" not in df_t.columns and "close" in df_t.columns:
        df_t["adj_close"] = df_t["close"]

    return df_t


def _df_para_long(df_t: pd.DataFrame, ticker_b3: str) -> pd.DataFrame:
    """Converte DataFrame de um ticker para formato long."""
    df_t = df_t.copy()
    df_t.index = pd.to_datetime(df_t.index)
    df_t = df_t.reset_index()

    # Nomeia coluna de data
    data_col = df_t.columns[0]
    df_t = df_t.rename(columns={data_col: "date"})

    # Remove timezone
    df_t["date"] = pd.to_datetime(df_t["date"]).dt.tz_localize(None)

    cols_necessarias = ["date", "open", "high", "low", "close", "adj_close", "volume"]
    for col in cols_necessarias:
        if col not in df_t.columns:
            df_t[col] = float("nan")

    df_t["ticker"] = ticker_b3
    df_t["volume"] = pd.to_numeric(df_t["volume"], errors="coerce").fillna(0).astype("int64")

    return df_t[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]]


def download_precos(
    tickers_b3: list[str],
    start: date,
    end: date,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Baixa preços para lista de tickers em lotes de TAMANHO_LOTE_DOWNLOAD.
    Retorna (DataFrame long, lista de tickers que falharam).
    """
    tickers_yf = [f"{t}.SA" for t in tickers_b3]
    start_str = start.isoformat()
    end_str = (end + timedelta(days=1)).isoformat()  # yfinance exclui end

    todos: list[pd.DataFrame] = []
    falharam: list[str] = []
    n_lotes = (len(tickers_yf) + config.TAMANHO_LOTE_DOWNLOAD - 1) // config.TAMANHO_LOTE_DOWNLOAD

    for i in range(0, len(tickers_yf), config.TAMANHO_LOTE_DOWNLOAD):
        lote_yf = tickers_yf[i:i + config.TAMANHO_LOTE_DOWNLOAD]
        lote_b3 = tickers_b3[i:i + config.TAMANHO_LOTE_DOWNLOAD]
        n_lote = i // config.TAMANHO_LOTE_DOWNLOAD + 1
        log.info(f"  Lote {n_lote}/{n_lotes}: baixando {len(lote_yf)} tickers...")

        df_lote = _baixar_lote(lote_yf, start_str, end_str)

        if df_lote is None:
            log.error(f"  Lote {n_lote}: FALHOU completamente")
            falharam.extend(lote_b3)
            continue

        for ticker_yf, ticker_b3 in zip(lote_yf, lote_b3):
            df_t = _extrair_ticker_df(df_lote, ticker_yf)
            if df_t is None or df_t.empty:
                log.warning(f"  {ticker_b3}: sem dados no lote")
                falharam.append(ticker_b3)
                continue
            long_df = _df_para_long(df_t, ticker_b3)
            long_df = long_df.dropna(subset=["adj_close"])
            if long_df.empty:
                falharam.append(ticker_b3)
                continue
            todos.append(long_df)

        log.info(f"  Lote {n_lote}/{n_lotes}: OK")

    if not todos:
        return pd.DataFrame(), falharam

    return pd.concat(todos, ignore_index=True), falharam


# ---------------------------------------------------------------------------
# Orquestrador principal
# ---------------------------------------------------------------------------

def run(modo_forcado: str | None = None) -> dict:
    """
    Executa Fase 2 completa.
    Retorna resumo da execução (compatível com last_run_summary.json).
    """
    inicio = datetime.now()
    log.info("=== FASE 2: Coleta de preços ===")

    # Carregar universo
    universo_path = config.UNIVERSO_ATUAL_PATH
    if not universo_path.exists():
        raise FileNotFoundError(f"universo_atual.json não encontrado: {universo_path}")
    with open(universo_path, encoding="utf-8") as f:
        universo = json.load(f)
    tickers_b3 = [t["ticker_b3"] for t in universo["tickers"]]
    log.info(f"Universo carregado: {len(tickers_b3)} tickers")

    # Detectar modo
    hoje = date.today()
    df_existente = storage.ler_precos()
    eh_primeira_execucao = df_existente is None

    if modo_forcado:
        modo = modo_forcado
    elif eh_primeira_execucao:
        modo = "full_refresh"
        log.info("Primeira execucao detectada -> full_refresh")
    elif hoje.weekday() == config.DIA_FULL_REFRESH:
        modo = "full_refresh"
    else:
        modo = "incremental"

    log.info(f"Modo: {modo}")

    # Definir janela de download
    if modo == "full_refresh":
        # Para backtest: 756 pregões ≈ 3 anos de trading days
        # 756 pregões / 252 por ano ≈ 3 anos calendário com folga
        dias_calendario = int(config.DIAS_HISTORICO_BACKTEST * 365 / 252) + 30
        start = hoje - timedelta(days=dias_calendario)
        end = hoje
        log.info(f"Full refresh: {start} -> {end}")
    else:
        # Incremental: baixar apenas o que falta
        ultimas = storage.ultima_data_por_ticker(df_existente)
        if ultimas:
            start_ts = min(ultimas.values())
            if hasattr(start_ts, "date"):
                start = start_ts.date() + timedelta(days=1)
            else:
                start = start_ts + timedelta(days=1)
        else:
            dias_calendario = int(config.DIAS_HISTORICO_BACKTEST * 365 / 252) + 30
            start = hoje - timedelta(days=dias_calendario)
        end = hoje
        log.info(f"Incremental: {start} -> {end}")

    # Download
    df_novo, falharam = download_precos(tickers_b3, start, end)

    # Merge
    if modo == "full_refresh" or df_existente is None:
        df_final = df_novo
    else:
        df_final = storage.merge_incremental(df_existente, df_novo)

    # Salvar
    if not df_final.empty:
        storage.salvar_precos(df_final)
        ultimo_pregao = df_final["date"].max()
        if hasattr(ultimo_pregao, "date"):
            ultimo_pregao = ultimo_pregao.date()
    else:
        ultimo_pregao = None
        log.error("DataFrame final vazio — nada salvo")

    # Validação leve
    val = validators.validar_leve(df_final, tickers_b3)

    # Status
    pct_falha = len(falharam) / len(tickers_b3)
    if pct_falha >= config.LIMITE_FAILED_PCT:
        status = "failed"
    elif pct_falha >= config.LIMITE_DEGRADED_PCT:
        status = "degraded"
    else:
        status = "success"

    duracao = (datetime.now() - inicio).seconds
    summary = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "modo": modo,
        "ultimo_pregao": str(ultimo_pregao),
        "tickers_baixados": len(tickers_b3) - len(falharam),
        "tickers_falharam": len(falharam),
        "tickers_falharam_lista": falharam,
        "tickers_stale": val["stale"],
        "tickers_suspeitos": val["suspeitos"],
        "duracao_segundos": duracao,
        "validacao_leve": {
            "LV1_passou": val["LV1_passou"],
            "LV2_passou": val["LV2_passou"],
            "LV3_passou": val["LV3_passou"],
            "LV4_passou": val["LV4_passou"],
        },
        "warnings": val["warnings"],
    }

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.LAST_RUN_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    log.info(
        f"=== FASE 2 CONCLUÍDA: status={status}, "
        f"{summary['tickers_baixados']}/{len(tickers_b3)} tickers, "
        f"{duracao}s ==="
    )
    return summary


if __name__ == "__main__":
    run()
