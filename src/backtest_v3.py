"""
backtest_v3.py — Backtest com STOP LOSS intraweek.

Reutiliza as carteiras formadas pelo backtest V2 (não recalcula scoring) e
aplica simulação dia-a-dia com stop loss fixo de -5%.

INPUTS  (READ-ONLY — não modifica):
    data/backtest_carteiras_v2.json     carteiras simuladas pela V2
    data/precos_v2.parquet              calendário de pregões + adj_close
    data/benchmarks.parquet             IBOV/SMLL/CDI

OUTPUTS:
    data/backtest_resultado_v3.json     métricas + metadata + equity curve
    data/backtest_carteiras_v3.json     uma entrada por semana com log_eventos

Uso:
    python src/backtest_v3.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# Garante que rodar `python src/backtest_v3.py` funciona
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src import benchmarks
from src.logger import get_logger
from src.portfolio_v3 import (
    simular_semana_v3,
    obter_pregoes_entre,
)
# Reusa métricas e equity curve já implementadas (sem modificar)
from src.backtest import (
    calcular_metricas,
    calcular_metricas_benchmark,
    gerar_equity_curve,
)

log = get_logger()


# ---------------------------------------------------------------------------
# Paths V3 (definidos aqui para não modificar config.py)
# ---------------------------------------------------------------------------

BACKTEST_V3_RESULTADO_PATH = config.DATA_DIR / "backtest_resultado_v3.json"
BACKTEST_V3_CARTEIRAS_PATH = config.DATA_DIR / "backtest_carteiras_v3.json"


# ---------------------------------------------------------------------------
# Métricas exclusivas de stop loss (STOPLOSS_V3_SPEC §6)
# ---------------------------------------------------------------------------

def calcular_metricas_stop(resultados: list[dict]) -> dict:
    todos_stops = [
        e for r in resultados
        for e in r["log_eventos"] if e["evento"] == "STOP_LOSS"
    ]
    semanas_com_stop = [r for r in resultados if r["n_stops_semana"] > 0]
    semanas_zeradas  = [
        r for r in resultados
        if r["n_stops_semana"] == r["n_posicoes_inicial"]
        and r["n_posicoes_inicial"] > 0
    ]
    n = len(resultados) or 1

    return {
        "n_stops_total":               len(todos_stops),
        "n_semanas_com_stop":          len(semanas_com_stop),
        "pct_semanas_com_stop":        round(len(semanas_com_stop) / n, 4),
        "retorno_medio_pos_stopada":   round(
            float(np.mean([e["ret_acumulado"] for e in todos_stops])), 6
        ) if todos_stops else 0.0,
        "n_stops_por_semana_medio":    round(len(todos_stops) / n, 4),
        "semanas_com_carteira_zerada": len(semanas_zeradas),
    }


# ---------------------------------------------------------------------------
# Comparativo V2 vs V3 (output no terminal — STOPLOSS_V3_SPEC §7.2)
# ---------------------------------------------------------------------------

def imprimir_comparativo(v2: dict, v3: dict, metricas_stop: dict) -> str:
    """Imprime a tabela comparativa e retorna o veredicto."""
    mv2 = v2["metricas_estrategia"]
    mv3 = v3["metricas_estrategia"]

    def _d(k):
        return mv3.get(k, 0) - mv2.get(k, 0)

    print()
    print("=" * 60)
    print(" COMPARATIVO V2 vs V3 (Stop Loss -5% intraweek)")
    print("=" * 60)
    print(f"{'Métrica':<28} {'V2':>10} {'V3':>10} {'Delta':>10}")
    print("-" * 60)
    linhas = [
        ("Retorno total",            "retorno_total",            "pct"),
        ("Retorno anualizado",       "retorno_anualizado",       "pct"),
        ("Volatilidade anualizada",  "volatilidade_anualizada",  "pct"),
        ("Sharpe ratio",             "sharpe_ratio",             "num"),
        ("Max drawdown",             "max_drawdown",             "pct"),
        ("Win rate semanal",         "win_rate_semanal",         "pct"),
        ("Hit rate vs SMLL",         "hit_rate_vs_smll",         "pct"),
    ]
    for label, key, fmt in linhas:
        v2_val = mv2.get(key, 0)
        v3_val = mv3.get(key, 0)
        delta  = v3_val - v2_val
        if fmt == "pct":
            print(f"{label:<28} {v2_val*100:>9.2f}% {v3_val*100:>9.2f}% {delta*100:>+9.2f}%")
        else:
            print(f"{label:<28} {v2_val:>10.4f} {v3_val:>10.4f} {delta:>+10.4f}")

    print()
    print("--- Métricas exclusivas V3 (stop loss) ---")
    print(f"{'Stops acionados (total)':<32}             {metricas_stop['n_stops_total']:>5}")
    print(f"{'Semanas com pelo menos 1 stop':<32}             {metricas_stop['n_semanas_com_stop']:>5}"
          f"  ({metricas_stop['pct_semanas_com_stop']*100:.1f}%)")
    print(f"{'Stops por semana (média)':<32}            {metricas_stop['n_stops_por_semana_medio']:>6.2f}")
    print(f"{'Retorno médio pos stopada':<32}          {metricas_stop['retorno_medio_pos_stopada']*100:>6.2f}%")
    print(f"{'Semanas com carteira 100% zerada':<32}             {metricas_stop['semanas_com_carteira_zerada']:>5}")

    # Veredicto: melhor em Sharpe E retorno anualizado?
    delta_sharpe = mv3.get("sharpe_ratio", 0)        - mv2.get("sharpe_ratio", 0)
    delta_ret    = mv3.get("retorno_anualizado", 0)  - mv2.get("retorno_anualizado", 0)

    if delta_sharpe > 0 and delta_ret > 0:
        veredicto = "V3 MELHOR — implementar stop loss"
    elif delta_sharpe < 0 and delta_ret < 0:
        veredicto = "V3 PIOR — manter V2 como está"
    else:
        veredicto = (
            "INCONCLUSIVO — V3 melhor em uma métrica, pior em outra "
            "(trade-off entre Sharpe e retorno)"
        )

    print()
    print("=" * 60)
    print(f" VEREDICTO: {veredicto}")
    print("=" * 60)
    return veredicto


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== BACKTEST V3 — Stop Loss Intraweek ===")

    # 1) Inputs (READ-ONLY)
    if not config.BACKTEST_V2_CARTEIRAS_PATH.exists():
        log.error("backtest_carteiras_v2.json não encontrado. Rode o backtest V2 primeiro.")
        sys.exit(1)
    if not config.PRECOS_V2_PARQUET_PATH.exists():
        log.error("precos_v2.parquet não encontrado.")
        sys.exit(1)
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        log.error("benchmarks.parquet não encontrado.")
        sys.exit(1)
    if not config.BACKTEST_V2_RESULTADO_PATH.exists():
        log.error("backtest_resultado_v2.json não encontrado (necessário para comparativo).")
        sys.exit(1)

    with open(config.BACKTEST_V2_CARTEIRAS_PATH, encoding="utf-8") as f:
        carteiras_v2 = json.load(f)
    with open(config.BACKTEST_V2_RESULTADO_PATH, encoding="utf-8") as f:
        resultado_v2 = json.load(f)

    df_precos     = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")
    df_precos["date"] = pd.to_datetime(df_precos["date"])
    df_benchmarks = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df_benchmarks["date"] = pd.to_datetime(df_benchmarks["date"])

    n_total = len(carteiras_v2["carteiras"])
    log.info(f"Simulando {n_total} semanas...")

    resultados: list[dict] = []

    for i, semana in enumerate(carteiras_v2["carteiras"], 1):
        tickers_entrada = [t["ticker"] for t in semana["tickers"]]
        preco_entrada   = {t["ticker"]: t["preco_entrada"] for t in semana["tickers"]}

        data_formacao     = semana["data_formacao"]
        data_corte        = semana["data_corte_dados"]
        data_vigencia_fim = semana["data_vigencia_fim"]

        # Garantia anti-look-ahead (STOPLOSS_V3_SPEC §4.4)
        assert pd.Timestamp(data_formacao) > pd.Timestamp(data_corte), (
            f"Look-ahead bias: data_formacao {data_formacao} <= data_corte {data_corte}"
        )

        pregoes = obter_pregoes_entre(data_formacao, data_vigencia_fim, df_precos)

        retorno_carteira, log_eventos, _ = simular_semana_v3(
            tickers_entrada, preco_entrada, pregoes, df_precos
        )

        # Retornos dos benchmarks na mesma janela (data_corte exclusivo, data_vigencia_fim inclusivo)
        dt_corte = date.fromisoformat(data_corte)
        dt_fim   = date.fromisoformat(data_vigencia_fim)
        ret_ibov = benchmarks.retorno_benchmark_periodo(df_benchmarks, "ibov", dt_corte, dt_fim)
        ret_smll = benchmarks.retorno_benchmark_periodo(df_benchmarks, "smll", dt_corte, dt_fim)
        ret_cdi  = benchmarks.retorno_benchmark_periodo(df_benchmarks, "cdi",  dt_corte, dt_fim)

        n_stops = sum(1 for e in log_eventos if e["evento"] == "STOP_LOSS")

        resultados.append({
            "semana":              semana["semana"],
            "data_formacao":       data_formacao,
            "data_corte_dados":    data_corte,
            "data_vigencia_fim":   data_vigencia_fim,
            "tickers_iniciais":    tickers_entrada,
            "n_posicoes_inicial":  len(tickers_entrada),
            "n_stops_semana":      n_stops,
            "tickers_stopados":    [e["ticker"] for e in log_eventos],
            "retorno_carteira":    round(retorno_carteira, 6),
            "retorno_ibov_semana": round(ret_ibov, 6) if ret_ibov is not None else 0.0,
            "retorno_smll_semana": round(ret_smll, 6) if ret_smll is not None else 0.0,
            "retorno_cdi_semana":  round(ret_cdi, 6)  if ret_cdi  is not None else 0.0,
            "alpha_vs_ibov":       round(retorno_carteira - (ret_ibov or 0), 6),
            "alpha_vs_smll":       round(retorno_carteira - (ret_smll or 0), 6),
            "log_eventos":         log_eventos,
        })

        if i % 20 == 0 or i == n_total:
            log.info(f"  {i}/{n_total} semanas processadas")

    # 2) Métricas agregadas
    cdi_anualizado = config.BACKTEST_CDI_ANUALIZADO_FALLBACK
    if "cdi" in df_benchmarks.columns:
        cdi_daily = df_benchmarks["cdi"].dropna()
        if not cdi_daily.empty:
            cdi_anualizado = float((1 + cdi_daily.mean()) ** 252 - 1)

    metricas      = calcular_metricas(resultados, df_benchmarks, cdi_anualizado)
    metricas_ibov = calcular_metricas_benchmark(df_benchmarks, "ibov", resultados, cdi_anualizado)
    metricas_smll = calcular_metricas_benchmark(df_benchmarks, "smll", resultados, cdi_anualizado)
    metricas_cdi  = calcular_metricas_benchmark(df_benchmarks, "cdi",  resultados, cdi_anualizado)

    alphas = {
        "vs_ibov": round(metricas.get("retorno_anualizado", 0) - metricas_ibov.get("retorno_anualizado", 0), 6),
        "vs_smll": round(metricas.get("retorno_anualizado", 0) - metricas_smll.get("retorno_anualizado", 0), 6),
        "vs_cdi":  round(metricas.get("retorno_anualizado", 0) - metricas_cdi.get("retorno_anualizado",  0), 6),
    }

    equity_curve  = gerar_equity_curve(resultados, df_benchmarks)
    metricas_stop = calcular_metricas_stop(resultados)

    # 3) Persistência
    metadata = {
        "data_geracao":            date.today().isoformat(),
        "janela_inicio":           resultados[0]["data_formacao"],
        "janela_fim":              resultados[-1]["data_vigencia_fim"],
        "n_semanas_simuladas":     len(resultados),
        "versao_formula":          "v3",
        "versao_scoring":          "v2",
        "stop_loss_pct":           -0.05,
        "stop_referencia":         "preco_entrada_fixo",
        "stop_execucao":           "fechamento_dia",
        "capital_apos_stop":       "caixa_ocioso",
        "redistribuicao":          "nenhuma",
        "limitacoes_declaradas": [
            "survivorship_bias: universo congelado",
            "zero_custos: sem corretagem nem slippage",
            "stop_no_fechamento: stop real seria intraday — resultado real ligeiramente pior",
            "caixa_sem_rendimento: capital stopado rende 0% pelo restante da semana",
        ],
    }

    resultado = {
        "metadata":             metadata,
        "metricas_estrategia":  metricas,
        "metricas_stop":        metricas_stop,
        "metricas_benchmarks": {
            "ibov": metricas_ibov,
            "smll": metricas_smll,
            "cdi":  metricas_cdi,
        },
        "alphas":               alphas,
        "equity_curve":         equity_curve,
    }

    carteiras_v3 = {
        "metadata":  {"n_carteiras": len(resultados), "versao_formula": "v3"},
        "carteiras": resultados,
    }

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BACKTEST_V3_RESULTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
    with open(BACKTEST_V3_CARTEIRAS_PATH, "w", encoding="utf-8") as f:
        json.dump(carteiras_v3, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"  -> {BACKTEST_V3_RESULTADO_PATH}")
    log.info(f"  -> {BACKTEST_V3_CARTEIRAS_PATH}")

    # 4) Comparativo
    imprimir_comparativo(resultado_v2, resultado, metricas_stop)

    print()
    print("Backtest V3 concluído.")


if __name__ == "__main__":
    main()
