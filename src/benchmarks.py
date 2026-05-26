"""Coleta e cálculo de benchmarks — PHASE3_SPEC §8.4."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests
import yfinance as yf

import config
from src.logger import get_logger

log = get_logger()


def _baixar_yf_serie(ticker: str, start: date, end: date) -> pd.Series | None:
    """Baixa série de adj_close para um ticker do Yahoo Finance."""
    try:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return None
        col = "Close" if "Close" in df.columns else df.columns[0]
        if isinstance(df.columns, pd.MultiIndex):
            col = df.columns[0]
            serie = df[col].squeeze()
        else:
            serie = df[col].squeeze()
        serie.index = pd.to_datetime(serie.index).tz_localize(None)
        return serie
    except Exception as e:
        log.warning(f"Erro baixando {ticker}: {e}")
        return None


def _baixar_cdi_bcb(start: date, end: date) -> pd.Series | None:
    """
    Baixa taxa CDI diária da API SGS do Banco Central.
    Código 12 = CDI Over.
    """
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{config.CODIGO_CDI_BCB}/dados"
        f"?formato=json&dataInicial={start.strftime('%d/%m/%Y')}"
        f"&dataFinal={end.strftime('%d/%m/%Y')}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
        if not dados:
            return None
        datas = pd.to_datetime([d["data"] for d in dados], format="%d/%m/%Y")
        valores = [float(d["valor"].replace(",", ".")) / 100 for d in dados]
        return pd.Series(valores, index=datas)
    except Exception as e:
        log.warning(f"CDI BCB falhou: {e}. Usando fallback.")
        return None


def carregar_benchmarks(start: date, end: date) -> pd.DataFrame:
    """
    Retorna DataFrame com colunas: date, ibov, smll, cdi (retornos diários).
    """
    log.info("Carregando benchmarks (IBOV, SMLL, CDI)...")

    ibov = _baixar_yf_serie(config.TICKER_IBOV, start, end)
    smll = _baixar_yf_serie(config.TICKER_SMLL, start, end)
    cdi = _baixar_cdi_bcb(start, end)

    dfs = []
    for nome, serie in [("ibov", ibov), ("smll", smll), ("cdi", cdi)]:
        if serie is not None and not serie.empty:
            df = serie.to_frame(name=nome)
            df.index.name = "date"
            if nome != "cdi":
                df[nome] = df[nome].pct_change()
            dfs.append(df)
        else:
            log.warning(f"Benchmark {nome} indisponível")

    if not dfs:
        return pd.DataFrame(columns=["date", "ibov", "smll", "cdi"])

    resultado = dfs[0]
    for df in dfs[1:]:
        resultado = resultado.join(df, how="outer")

    resultado = resultado.reset_index()
    resultado["date"] = pd.to_datetime(resultado["date"])
    return resultado


def retorno_benchmark_periodo(
    benchmarks_df: pd.DataFrame,
    nome: str,
    data_inicio: date,
    data_fim: date,
) -> float:
    """
    Retorno acumulado de um benchmark entre data_inicio e data_fim.
    Usa produto de (1 + retorno_diario).
    """
    if benchmarks_df.empty or nome not in benchmarks_df.columns:
        return 0.0
    mask = (
        (benchmarks_df["date"].dt.date >= data_inicio) &
        (benchmarks_df["date"].dt.date <= data_fim)
    )
    serie = benchmarks_df.loc[mask, nome].dropna()
    if serie.empty:
        return 0.0
    return float((1 + serie).prod() - 1)


def salvar_benchmarks(df: pd.DataFrame) -> None:
    """
    Salva benchmarks.parquet fazendo MERGE com o existente (linhas novas
    sobrescrevem antigas para a mesma data; histórico anterior é preservado).

    Comportamento anterior (sobrescrita) causava perda do histórico longo
    sempre que um intraday baixava só a janela curta da semana corrente.
    """
    import config
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    existente = ler_benchmarks()
    if existente is not None and not existente.empty and not df.empty:
        # Garantir colunas iguais antes de concatenar
        df["date"] = pd.to_datetime(df["date"])
        existente["date"] = pd.to_datetime(existente["date"])
        combinado = pd.concat([existente, df], ignore_index=True)
        # Para cada data, mantém a última ocorrência (= dados novos)
        combinado = (combinado
                     .sort_values("date")
                     .drop_duplicates(subset="date", keep="last")
                     .reset_index(drop=True))
    else:
        combinado = df

    combinado.to_parquet(
        config.BENCHMARKS_PARQUET_PATH, engine="pyarrow", index=False,
    )
    log.info(f"benchmarks.parquet salvo: {len(combinado)} linhas "
             f"(+{len(df) if existente is None else max(0, len(combinado) - len(existente))} novas)")


def ler_benchmarks() -> pd.DataFrame | None:
    """Lê benchmarks.parquet se existir."""
    import config
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df
