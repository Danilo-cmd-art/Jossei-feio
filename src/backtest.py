"""
Fase 4 — Backtest Histórico.

~104 semanas retroativas com garantia anti-look-ahead.
PHASE4_SPEC §2-12.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from statistics import mean, stdev

import pandas as pd

import config
from src import scoring, benchmarks
from src.logger import get_logger
from src.portfolio import (
    obter_pregoes,
    ultimo_pregao_antes,
    ultimo_pregao_da_semana,
    formar_carteira,
    calcular_performance_diaria,
)

log = get_logger()


# ---------------------------------------------------------------------------
# Iterador de segundas-feiras do backtest
# ---------------------------------------------------------------------------

def segundas_no_periodo(inicio: date, fim: date, pregoes: list[date]) -> list[date]:
    """
    Retorna lista do primeiro pregão de cada semana dentro de [inicio, fim].
    Avança cursor para a próxima segunda-feira antes de iterar.
    """
    semanas: list[date] = []
    pregoes_set = set(pregoes)

    # Avança até a próxima segunda-feira
    dias_ate_segunda = (7 - inicio.weekday()) % 7
    cursor = inicio + timedelta(days=dias_ate_segunda)

    while cursor <= fim:
        if cursor in pregoes_set:
            semanas.append(cursor)
        else:
            # Feriado: primeiro pregão da semana
            sexta = cursor + timedelta(days=4)
            da_semana = [d for d in pregoes if cursor <= d <= sexta]
            if da_semana:
                semanas.append(da_semana[0])
        cursor += timedelta(days=7)
    return semanas


# ---------------------------------------------------------------------------
# Simulação de uma semana
# ---------------------------------------------------------------------------

def simular_semana(
    data_segunda: date,
    df_precos: pd.DataFrame,
    universo: list[dict],
    pregoes: list[date],
) -> dict | None:
    """
    Reconstrói scores e carteira para uma semana específica.
    GARANTIA ANTI-LOOK-AHEAD: data_corte é a sexta antes de data_segunda.
    """
    data_corte = ultimo_pregao_antes(data_segunda, pregoes)
    if data_corte is None:
        log.warning(f"  Sem pregão antes de {data_segunda}, pulando")
        return None

    data_vigencia_fim = ultimo_pregao_da_semana(data_segunda, pregoes)
    if data_vigencia_fim is None:
        return None

    # Scores: SÓ dados até data_corte (assertion em calcular_scores)
    try:
        scores = scoring.calcular_scores(df_precos, universo, data_corte)
    except AssertionError as e:
        log.error(f"  LOOK-AHEAD BIAS em {data_segunda}: {e}")
        raise

    tickers_carteira = formar_carteira(scores, data_corte, df_precos)
    if not tickers_carteira:
        log.info(f"  {data_segunda}: carteira vazia (sem ações no filtro de tendência)")
        return None

    n = len(tickers_carteira)

    # Performance da semana: só os 5 pregões da semana (anti-slow-path)
    pregoes_semana = [d for d in pregoes if data_segunda <= d <= data_vigencia_fim]
    performance = calcular_performance_diaria(tickers_carteira, data_corte, df_precos, pregoes_semana)

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


def _preco_em(ticker: str, data: date, df_precos: pd.DataFrame) -> float | None:
    df_t = df_precos[
        (df_precos["ticker"] == ticker) &
        (df_precos["date"].dt.date <= data)
    ].sort_values("date")
    if df_t.empty:
        return None
    return float(df_t["adj_close"].iloc[-1])


# ---------------------------------------------------------------------------
# Métricas agregadas
# ---------------------------------------------------------------------------

def calcular_metricas(
    carteiras: list[dict],
    bench_df: pd.DataFrame | None,
    cdi_anualizado: float,
) -> dict:
    """Calcula métricas completas de retorno, risco e qualidade."""
    retornos = [c["retorno_carteira"] for c in carteiras]
    n = len(retornos)

    if n == 0:
        return {}

    ret_total = float((pd.Series([1 + r for r in retornos])).prod() - 1)
    n_anos = n / 52
    ret_anualizado = float((1 + ret_total) ** (1 / n_anos) - 1) if n_anos > 0 else 0.0
    ret_medio_semanal = mean(retornos)

    vol_semanal = stdev(retornos) if n > 1 else 0.0
    vol_anualizada = vol_semanal * math.sqrt(52)

    # Max drawdown
    equity = [100.0]
    for r in retornos:
        equity.append(equity[-1] * (1 + r))

    peak = equity[0]
    max_dd = 0.0
    max_dd_idx = 0
    for i, v in enumerate(equity[1:], 1):
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
            max_dd_idx = i

    data_max_dd = carteiras[min(max_dd_idx - 1, n - 1)]["data_vigencia_fim"] if carteiras else None

    sharpe = (ret_anualizado - cdi_anualizado) / vol_anualizada if vol_anualizada > 0 else 0.0

    n_positivas = sum(1 for r in retornos if r > 0)
    win_rate = n_positivas / n

    # Hit rate vs SMLL
    hit_smll = 0
    if bench_df is not None and "smll" in bench_df.columns:
        for c in carteiras:
            inicio = date.fromisoformat(c["data_corte_dados"])
            fim = date.fromisoformat(c["data_vigencia_fim"])
            ret_smll = benchmarks.retorno_benchmark_periodo(bench_df, "smll", inicio, fim)
            if c["retorno_carteira"] > ret_smll:
                hit_smll += 1
        hit_rate_smll = hit_smll / n
    else:
        hit_rate_smll = 0.0

    # Beta vs IBOV
    beta_ibov = 0.0
    if bench_df is not None and "ibov" in bench_df.columns:
        rets_ibov = []
        for c in carteiras:
            inicio = date.fromisoformat(c["data_corte_dados"])
            fim = date.fromisoformat(c["data_vigencia_fim"])
            rets_ibov.append(benchmarks.retorno_benchmark_periodo(bench_df, "ibov", inicio, fim))
        if len(rets_ibov) == len(retornos) and stdev(rets_ibov) > 0:
            cov = sum((x - mean(retornos)) * (y - mean(rets_ibov))
                      for x, y in zip(retornos, rets_ibov)) / (n - 1)
            var_ibov = stdev(rets_ibov) ** 2
            beta_ibov = cov / var_ibov

    return {
        "retorno_total": round(ret_total, 6),
        "retorno_anualizado": round(ret_anualizado, 6),
        "retorno_medio_semanal": round(ret_medio_semanal, 6),
        "volatilidade_anualizada": round(vol_anualizada, 6),
        "max_drawdown": round(max_dd, 6),
        "data_max_drawdown": data_max_dd,
        "sharpe_ratio": round(sharpe, 4),
        "win_rate_semanal": round(win_rate, 4),
        "hit_rate_vs_smll": round(hit_rate_smll, 4),
        "beta_vs_ibov": round(beta_ibov, 4),
        "n_semanas_positivas": n_positivas,
        "n_semanas_negativas": n - n_positivas,
    }


def calcular_metricas_benchmark(
    bench_df: pd.DataFrame | None,
    nome: str,
    carteiras: list[dict],
    cdi_anualizado: float,
) -> dict:
    """Métricas de retorno para um benchmark no mesmo período das carteiras."""
    if bench_df is None or nome not in (bench_df.columns if bench_df is not None else []):
        return {}

    retornos = []
    for c in carteiras:
        inicio = date.fromisoformat(c["data_corte_dados"])
        fim = date.fromisoformat(c["data_vigencia_fim"])
        retornos.append(benchmarks.retorno_benchmark_periodo(bench_df, nome, inicio, fim))

    n = len(retornos)
    if n == 0:
        return {}

    ret_total = float((pd.Series([1 + r for r in retornos])).prod() - 1)
    n_anos = n / 52
    ret_anual = float((1 + ret_total) ** (1 / n_anos) - 1) if n_anos > 0 else 0.0
    vol = stdev(retornos) * math.sqrt(52) if n > 1 else 0.0

    # Max drawdown
    equity = [100.0]
    for r in retornos:
        equity.append(equity[-1] * (1 + r))
    peak = equity[0]
    max_dd = 0.0
    for v in equity[1:]:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd

    sharpe = (ret_anual - cdi_anualizado) / vol if vol > 0 else 0.0

    return {
        "retorno_total": round(ret_total, 6),
        "retorno_anualizado": round(ret_anual, 6),
        "volatilidade_anualizada": round(vol, 6),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 6),
    }


# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------

def gerar_equity_curve(
    carteiras: list[dict],
    bench_df: pd.DataFrame | None,
) -> list[dict]:
    curve = []
    val_estrategia = 100.0
    val_ibov = 100.0
    val_smll = 100.0
    val_cdi = 100.0

    for c in carteiras:
        inicio = date.fromisoformat(c["data_corte_dados"])
        fim = date.fromisoformat(c["data_vigencia_fim"])

        val_estrategia *= (1 + c["retorno_carteira"])

        r_ibov = benchmarks.retorno_benchmark_periodo(bench_df, "ibov", inicio, fim) if bench_df is not None else 0.0
        r_smll = benchmarks.retorno_benchmark_periodo(bench_df, "smll", inicio, fim) if bench_df is not None else 0.0
        r_cdi = benchmarks.retorno_benchmark_periodo(bench_df, "cdi", inicio, fim) if bench_df is not None else 0.0

        val_ibov *= (1 + r_ibov)
        val_smll *= (1 + r_smll)
        val_cdi *= (1 + r_cdi)

        curve.append({
            "data": fim,
            "valor_estrategia": round(val_estrategia, 4),
            "valor_ibov": round(val_ibov, 4),
            "valor_smll": round(val_smll, 4),
            "valor_cdi": round(val_cdi, 4),
        })

    return curve


# ---------------------------------------------------------------------------
# Entrypoint Fase 4
# ---------------------------------------------------------------------------

def run(df_precos: pd.DataFrame, universo: list[dict]) -> dict:
    """Executa backtest completo ou incremental."""
    log.info("=== FASE 4: Backtest ===")
    hoje = date.today()
    pregoes = obter_pregoes(df_precos)

    # Detectar modo
    resultado_existente = None
    if config.BACKTEST_RESULTADO_PATH.exists():
        with open(config.BACKTEST_RESULTADO_PATH, encoding="utf-8") as f:
            resultado_existente = json.load(f)

    if resultado_existente is not None:
        janela_fim_str = resultado_existente["metadata"].get("janela_fim", "")
        if janela_fim_str and date.fromisoformat(janela_fim_str) < hoje:
            modo = "incremental"
        else:
            log.info("Backtest já atualizado para hoje")
            return resultado_existente
    else:
        modo = "full"

    log.info(f"Modo backtest: {modo}")

    # Período do backtest
    janela_fim = hoje
    janela_inicio = hoje - timedelta(days=int(config.BACKTEST_JANELA_ANOS * 365.25))
    warmup = timedelta(days=int(config.BACKTEST_DIAS_WARMUP * 365 / 252))

    # Segundas no período
    semanas = segundas_no_periodo(janela_inicio, janela_fim, pregoes)
    log.info(f"Semanas a simular: {len(semanas)} ({janela_inicio} -> {janela_fim})")

    # No modo incremental, pegar apenas semanas novas
    carteiras_existentes: list[dict] = []
    semanas_existentes: set[str] = set()
    if modo == "incremental" and resultado_existente:
        if config.BACKTEST_CARTEIRAS_PATH.exists():
            with open(config.BACKTEST_CARTEIRAS_PATH, encoding="utf-8") as f:
                bc = json.load(f)
                carteiras_existentes = bc.get("carteiras", [])
                semanas_existentes = {c["semana"] for c in carteiras_existentes}

    # Simular semanas
    novas_carteiras: list[dict] = []
    for i, data_segunda in enumerate(semanas):
        semana_iso = data_segunda.strftime("%Y-W%V")
        if semana_iso in semanas_existentes:
            continue
        log.info(f"  [{i+1}/{len(semanas)}] Semana {semana_iso} ({data_segunda})")
        resultado_semana = simular_semana(data_segunda, df_precos, universo, pregoes)
        if resultado_semana:
            novas_carteiras.append(resultado_semana)

    todas_carteiras = carteiras_existentes + novas_carteiras
    todas_carteiras.sort(key=lambda c: c["data_formacao"])

    # Benchmarks — garante janela completa do backtest (2 anos)
    log.info("Baixando benchmarks para janela completa do backtest...")
    bench_df_completo = benchmarks.carregar_benchmarks(janela_inicio, janela_fim)
    if not bench_df_completo.empty:
        benchmarks.salvar_benchmarks(bench_df_completo)
        bench_df = bench_df_completo
    else:
        bench_df = benchmarks.ler_benchmarks()

    # CDI anualizado (fallback se não tiver dados)
    cdi_anualizado = config.BACKTEST_CDI_ANUALIZADO_FALLBACK
    if bench_df is not None and "cdi" in bench_df.columns:
        cdi_daily = bench_df["cdi"].dropna()
        if not cdi_daily.empty:
            cdi_anualizado = float((1 + cdi_daily.mean()) ** 252 - 1)

    metricas = calcular_metricas(todas_carteiras, bench_df, cdi_anualizado)
    metricas_ibov = calcular_metricas_benchmark(bench_df, "ibov", todas_carteiras, cdi_anualizado)
    metricas_smll = calcular_metricas_benchmark(bench_df, "smll", todas_carteiras, cdi_anualizado)
    metricas_cdi = calcular_metricas_benchmark(bench_df, "cdi", todas_carteiras, cdi_anualizado)

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
            "universo_versao": date.today().strftime("%Y-%m"),
            "modo": modo,
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
    with open(config.BACKTEST_RESULTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)

    carteiras_json = {"metadata": {"n_carteiras": len(todas_carteiras)}, "carteiras": todas_carteiras}
    with open(config.BACKTEST_CARTEIRAS_PATH, "w", encoding="utf-8") as f:
        json.dump(carteiras_json, f, ensure_ascii=False, indent=2, default=str)

    log.info(
        f"=== FASE 4 CONCLUÍDA: {len(todas_carteiras)} semanas, "
        f"retorno_total={metricas.get('retorno_total', 0):.2%} ==="
    )
    return resultado
