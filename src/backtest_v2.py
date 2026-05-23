"""
Backtest V2 — usa scoring_v2 e universo_v2.json.

Diferenças vs backtest.py:
  - Importa calcular_scores_v2 (filtros F1/F2, fórmula nova)
  - Lê universo_v2.json
  - Garante preços para novos tickers V2 (precos_v2.parquet)
  - Output: backtest_resultado_v2.json + backtest_carteiras_v2.json
  - Não modifica nenhum arquivo da V1

V2_CLAUDE_CODE_PROMPT.md §4.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from statistics import mean, stdev

import pandas as pd
import yfinance as yf

import config
from src.scoring_v2 import calcular_scores_v2
from src import benchmarks
from src.logger import get_logger
from src.portfolio import (
    obter_pregoes,
    ultimo_pregao_antes,
    ultimo_pregao_da_semana,
    formar_carteira,
    calcular_performance_diaria,
)
# Reutiliza funções de métricas do backtest original (sem modificar)
from src.backtest import (
    segundas_no_periodo,
    _preco_em,
    calcular_metricas,
    calcular_metricas_benchmark,
    gerar_equity_curve,
)

log = get_logger()


# ---------------------------------------------------------------------------
# Garantia de preços para tickers V2 não presentes no precos.parquet da V1
# ---------------------------------------------------------------------------

def _garantir_precos_v2(universo_v2: list[dict]) -> pd.DataFrame:
    """
    Carrega precos.parquet (V1) e baixa preços de tickers novos da V2.
    Salva resultado consolidado em precos_v2.parquet.
    Retorna DataFrame completo.
    """
    tickers_v2 = {t["ticker_b3"] for t in universo_v2}

    # Carrega preços V1 existentes
    df_v1: pd.DataFrame | None = None
    if config.PRECOS_PARQUET_PATH.exists():
        df_v1 = pd.read_parquet(config.PRECOS_PARQUET_PATH, engine="pyarrow")
        df_v1["date"] = pd.to_datetime(df_v1["date"])

    tickers_existentes = set(df_v1["ticker"].unique()) if df_v1 is not None else set()
    tickers_novos = tickers_v2 - tickers_existentes

    if tickers_novos:
        log.info(f"Tickers novos V2 sem precos: {sorted(tickers_novos)} — baixando...")
        novos_dfs: list[pd.DataFrame] = []
        periodo_dias = config.DIAS_HISTORICO_BACKTEST  # 756 pregões ~ 3 anos

        for ticker_b3 in sorted(tickers_novos):
            ticker_yf = f"{ticker_b3}.SA"
            try:
                df_dl = yf.download(
                    ticker_yf,
                    period="3y",
                    auto_adjust=True,
                    progress=False,
                )
                if df_dl is None or df_dl.empty:
                    log.warning(f"  {ticker_b3}: sem dados no Yahoo")
                    continue

                # Normaliza colunas (MultiIndex pode aparecer com 1 ticker)
                if isinstance(df_dl.columns, pd.MultiIndex):
                    df_dl.columns = df_dl.columns.get_level_values(0)

                close_col = "Close" if "Close" in df_dl.columns else df_dl.columns[0]
                df_t = pd.DataFrame({
                    "date": pd.to_datetime(df_dl.index).tz_localize(None),
                    "ticker": ticker_b3,
                    "adj_close": df_dl[close_col].values,
                    "volume": df_dl["Volume"].values if "Volume" in df_dl.columns else 0,
                }).dropna(subset=["adj_close"])
                novos_dfs.append(df_t)
                log.info(f"  {ticker_b3}: {len(df_t)} pregões baixados")
            except Exception as e:
                log.warning(f"  {ticker_b3}: erro — {e}")

        if novos_dfs:
            df_novos = pd.concat(novos_dfs, ignore_index=True)
            partes = [df_v1, df_novos] if df_v1 is not None else [df_novos]
            df_completo = pd.concat(partes, ignore_index=True)
            df_completo = df_completo.drop_duplicates(subset=["date", "ticker"])
            df_completo = df_completo.sort_values(["ticker", "date"]).reset_index(drop=True)
        else:
            df_completo = df_v1 if df_v1 is not None else pd.DataFrame()
    else:
        log.info("Todos os tickers V2 já têm preços em precos.parquet — reutilizando.")
        df_completo = df_v1 if df_v1 is not None else pd.DataFrame()

    # Salva precos_v2.parquet
    if not df_completo.empty:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        df_completo.to_parquet(
            config.PRECOS_V2_PARQUET_PATH,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        n_tickers = df_completo["ticker"].nunique()
        log.info(f"precos_v2.parquet salvo: {len(df_completo):,} linhas, {n_tickers} tickers")

    return df_completo


# ---------------------------------------------------------------------------
# Simulação de uma semana (V2)
# ---------------------------------------------------------------------------

def simular_semana_v2(
    data_segunda: date,
    df_precos: pd.DataFrame,
    universo: list[dict],
    pregoes: list[date],
) -> dict | None:
    """
    Reconstrói scores V2 e carteira para uma semana específica.
    GARANTIA ANTI-LOOK-AHEAD: data_corte é a sexta antes de data_segunda.
    """
    data_corte = ultimo_pregao_antes(data_segunda, pregoes)
    if data_corte is None:
        log.warning(f"  Sem pregão antes de {data_segunda}, pulando")
        return None

    data_vigencia_fim = ultimo_pregao_da_semana(data_segunda, pregoes)
    if data_vigencia_fim is None:
        return None

    try:
        scores = calcular_scores_v2(df_precos, universo, data_corte)
    except AssertionError as e:
        log.error(f"  LOOK-AHEAD BIAS em {data_segunda}: {e}")
        raise

    tickers_carteira = formar_carteira(scores, data_corte, df_precos)
    if not tickers_carteira:
        log.info(f"  {data_segunda}: carteira vazia (sem ações nos filtros F1/F2)")
        return None

    n = len(tickers_carteira)
    pregoes_semana = [d for d in pregoes if data_segunda <= d <= data_vigencia_fim]
    performance = calcular_performance_diaria(
        tickers_carteira, data_corte, df_precos, pregoes_semana
    )
    retorno_carteira = performance[-1]["retorno_acumulado"] if performance else 0.0

    semana_iso = data_segunda.strftime("%Y-W%V")

    return {
        "semana": semana_iso,
        "data_formacao": data_segunda.isoformat(),
        "data_corte_dados": data_corte.isoformat(),
        "data_vigencia_fim": data_vigencia_fim.isoformat(),
        "tickers": [
            {
                "ticker": t["ticker"],
                "score": t["score_na_formacao"],
                "preco_entrada": t["preco_entrada"],
                "preco_saida": _preco_em(t["ticker"], data_vigencia_fim, df_precos),
                "retorno_semana": round(
                    (_preco_em(t["ticker"], data_vigencia_fim, df_precos) or t["preco_entrada"] or 1)
                    / (t["preco_entrada"] or 1) - 1, 6
                ) if t["preco_entrada"] else 0.0,
            }
            for t in tickers_carteira
        ],
        "n_posicoes": n,
        "retorno_carteira": round(retorno_carteira, 6),
    }


# ---------------------------------------------------------------------------
# Entrypoint Backtest V2
# ---------------------------------------------------------------------------

def run(df_precos_v1: pd.DataFrame, universo_v1: list[dict]) -> dict:
    """
    Executa backtest V2 completo.
    Ignora df_precos_v1 e universo_v1 (mantido por compatibilidade com run.py).
    Carrega universo_v2.json e precos_v2.parquet internamente.
    """
    log.info("=== BACKTEST V2 ===")

    # Carrega universo V2
    if not config.UNIVERSO_V2_PATH.exists():
        log.error("universo_v2.json nao encontrado. Execute build_universe_v2 primeiro.")
        return {}

    with open(config.UNIVERSO_V2_PATH, encoding="utf-8") as f:
        universo_json = json.load(f)
    universo_v2 = universo_json["tickers"]
    log.info(f"Universo V2: {len(universo_v2)} tickers")

    # Garante preços
    df_precos = _garantir_precos_v2(universo_v2)
    if df_precos.empty:
        log.error("Sem precos disponíveis para V2.")
        return {}

    hoje = date.today()
    pregoes = obter_pregoes(df_precos)

    # Detecta modo
    resultado_existente = None
    if config.BACKTEST_V2_RESULTADO_PATH.exists():
        with open(config.BACKTEST_V2_RESULTADO_PATH, encoding="utf-8") as f:
            resultado_existente = json.load(f)

    if resultado_existente is not None:
        janela_fim_str = resultado_existente["metadata"].get("janela_fim", "")
        if janela_fim_str and date.fromisoformat(janela_fim_str) < hoje:
            modo = "incremental"
        else:
            log.info("Backtest V2 já atualizado para hoje")
            return resultado_existente
    else:
        modo = "full"

    log.info(f"Modo backtest V2: {modo}")

    janela_fim = hoje
    janela_inicio = hoje - timedelta(days=int(config.BACKTEST_JANELA_ANOS * 365.25))
    semanas = segundas_no_periodo(janela_inicio, janela_fim, pregoes)
    log.info(f"Semanas a simular V2: {len(semanas)}")

    carteiras_existentes: list[dict] = []
    semanas_existentes: set[str] = set()
    if modo == "incremental" and resultado_existente:
        if config.BACKTEST_V2_CARTEIRAS_PATH.exists():
            with open(config.BACKTEST_V2_CARTEIRAS_PATH, encoding="utf-8") as f:
                bc = json.load(f)
                carteiras_existentes = bc.get("carteiras", [])
                semanas_existentes = {c["semana"] for c in carteiras_existentes}

    novas_carteiras: list[dict] = []
    for i, data_segunda in enumerate(semanas):
        semana_iso = data_segunda.strftime("%Y-W%V")
        if semana_iso in semanas_existentes:
            continue
        log.info(f"  [{i+1}/{len(semanas)}] Semana {semana_iso} ({data_segunda})")
        resultado_semana = simular_semana_v2(data_segunda, df_precos, universo_v2, pregoes)
        if resultado_semana:
            novas_carteiras.append(resultado_semana)

    todas_carteiras = carteiras_existentes + novas_carteiras
    todas_carteiras.sort(key=lambda c: c["data_formacao"])

    # Benchmarks — garante janela completa
    log.info("Baixando benchmarks para janela completa do backtest V2...")
    bench_df_completo = benchmarks.carregar_benchmarks(janela_inicio, janela_fim)
    if not bench_df_completo.empty:
        benchmarks.salvar_benchmarks(bench_df_completo)
        bench_df = bench_df_completo
    else:
        bench_df = benchmarks.ler_benchmarks()

    cdi_anualizado = config.BACKTEST_CDI_ANUALIZADO_FALLBACK
    if bench_df is not None and "cdi" in bench_df.columns:
        cdi_daily = bench_df["cdi"].dropna()
        if not cdi_daily.empty:
            cdi_anualizado = float((1 + cdi_daily.mean()) ** 252 - 1)

    metricas = calcular_metricas(todas_carteiras, bench_df, cdi_anualizado)
    metricas_ibov = calcular_metricas_benchmark(bench_df, "ibov", todas_carteiras, cdi_anualizado)
    metricas_smll = calcular_metricas_benchmark(bench_df, "smll", todas_carteiras, cdi_anualizado)
    metricas_cdi  = calcular_metricas_benchmark(bench_df, "cdi",  todas_carteiras, cdi_anualizado)

    alphas = {}
    for nome, m in [("vs_ibov", metricas_ibov), ("vs_smll", metricas_smll), ("vs_cdi", metricas_cdi)]:
        ret_bench = m.get("retorno_anualizado", 0.0)
        alphas[nome] = round(metricas.get("retorno_anualizado", 0.0) - ret_bench, 6)

    equity_curve = gerar_equity_curve(todas_carteiras, bench_df)

    resultado = {
        "metadata": {
            "data_geracao": hoje.isoformat(),
            "janela_inicio": janela_inicio.isoformat(),
            "janela_fim": janela_fim.isoformat(),
            "n_semanas_simuladas": len(todas_carteiras),
            "universo_versao": "v2-" + date.today().strftime("%Y-%m"),
            "modo": modo,
            "versao_formula": "v2",
            "limitacoes_declaradas": [
                "survivorship_bias: universo congelado em 2026-05",
                "zero_custos: sem corretagem nem slippage",
            ],
        },
        "metricas_estrategia": metricas,
        "metricas_benchmarks": {
            "ibov": metricas_ibov,
            "smll": metricas_smll,
            "cdi": metricas_cdi,
        },
        "alphas": alphas,
        "equity_curve": equity_curve,
    }

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.BACKTEST_V2_RESULTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)

    carteiras_json = {
        "metadata": {"n_carteiras": len(todas_carteiras), "versao_formula": "v2"},
        "carteiras": todas_carteiras,
    }
    with open(config.BACKTEST_V2_CARTEIRAS_PATH, "w", encoding="utf-8") as f:
        json.dump(carteiras_json, f, ensure_ascii=False, indent=2, default=str)

    log.info(
        f"=== BACKTEST V2 CONCLUIDO: {len(todas_carteiras)} semanas, "
        f"retorno_total={metricas.get('retorno_total', 0):.2%} ==="
    )
    return resultado
