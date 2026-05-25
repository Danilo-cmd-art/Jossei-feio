"""
backtest_v3c_redistribuicao_positivos.py — Variante V3c.

Regras de redistribuição (combinadas):
  1. Quando uma posição é stopada, o peso liberado só é redistribuído
     para posições ATIVAS com retorno acumulado > 0 (desde a entrada).
  2. Nenhuma posição pode ultrapassar 2× o peso original (peso_maximo).
     O excedente acima do cap fica como CAIXA OCIOSO pelo resto da semana.
  3. Se NÃO houver nenhuma posição positiva no momento do stop,
     o peso liberado vira caixa ocioso (igual ao V3 oficial).

Exemplo (5 posições, 20% cada, peso_maximo = 40%):
  • 1 stopada, 3 positivas, 1 negativa → redistribui pro-rata às 3 positivas
  • 2 stopadas, 1 positiva → a positiva recebe até 40%; excesso vai a caixa
  • 1 stopada, 0 positivas → tudo vira caixa

INPUTS  (READ-ONLY): mesmos do V3 oficial
OUTPUTS:
    data/backtest_resultado_v3c.json
    data/backtest_carteiras_v3c.json

NÃO modifica V2, V3 nem V3b.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src import benchmarks
from src.logger import get_logger
from src.portfolio_v3 import obter_adj_close, obter_adj_close_anterior, obter_pregoes_entre
from src.backtest import calcular_metricas, calcular_metricas_benchmark, gerar_equity_curve
from src.backtest_v3 import calcular_metricas_stop

log = get_logger()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKTEST_V3C_RESULTADO_PATH = config.DATA_DIR / "backtest_resultado_v3c.json"
BACKTEST_V3C_CARTEIRAS_PATH = config.DATA_DIR / "backtest_carteiras_v3c.json"

STOP_LOSS_LIMITE  = -0.05
CAP_MULTIPLICADOR = 2.0   # peso maximo = CAP_MULTIPLICADOR * peso_unitario


# ---------------------------------------------------------------------------
# Posicao (peso mutavel durante a semana)
# ---------------------------------------------------------------------------

@dataclass
class PosicaoV3c:
    ticker:        str
    preco_entrada: float
    peso:          float
    ativo:         bool   = True
    preco_stop:    float | None = None
    data_stop:     str   | None = None
    ret_no_stop:   float | None = None


# ---------------------------------------------------------------------------
# Helper: redistribuir com filtro de positividade + cap de peso
# ---------------------------------------------------------------------------

def _redistribuir(
    peso_a_redistribuir: float,
    posicoes: dict[str, PosicaoV3c],
    data,
    df_precos: pd.DataFrame,
    peso_maximo: float,
) -> float:
    """
    Redistribui peso_a_redistribuir pro-rata entre posicoes ativas e positivas.

    Regras:
      - Apenas posicoes com ret_acumulado > 0 recebem alocacao.
      - Nenhuma posicao pode ultrapassar peso_maximo.
      - Excedente acima do cap retorna como caixa ocioso.

    Retorna: peso nao redistribuido (caixa ocioso).
    """
    # Identifica candidatas: ativas + retorno acumulado positivo no dia atual
    candidatas: list[PosicaoV3c] = []
    for p in posicoes.values():
        if not p.ativo:
            continue
        preco_atual = obter_adj_close(p.ticker, data, df_precos)
        if preco_atual is None:
            continue
        ret_acum = preco_atual / p.preco_entrada - 1
        if ret_acum > 0:
            candidatas.append(p)

    if not candidatas:
        # Nenhuma posicao positiva — todo peso vira caixa ocioso
        return peso_a_redistribuir

    soma_pesos = sum(p.peso for p in candidatas)
    if soma_pesos <= 0:
        return peso_a_redistribuir

    caixa_sobra = 0.0
    for p in candidatas:
        share    = p.peso / soma_pesos
        adicao   = peso_a_redistribuir * share
        espaco   = peso_maximo - p.peso
        if espaco <= 0:
            # Ja esta no limite — esse ganho vai para caixa
            caixa_sobra += adicao
        elif adicao > espaco:
            p.peso    += espaco
            caixa_sobra += adicao - espaco
        else:
            p.peso += adicao

    return caixa_sobra


# ---------------------------------------------------------------------------
# Loop semanal V3c
# ---------------------------------------------------------------------------

def simular_semana_v3c(
    tickers_entrada: list[str],
    preco_entrada:   dict[str, float],
    pregoes_semana:  list,
    df_precos:       pd.DataFrame,
) -> tuple[float, list[dict], dict[str, PosicaoV3c]]:
    """
    Simula uma semana com stop loss -5% e redistribuicao seletiva:
      - Freed weight vai apenas para posicoes positivas (ret_acum > 0).
      - Cap de 2x o peso original por posicao; excesso fica como caixa ocioso.
      - Se nao ha positivas: freed weight vira caixa ocioso (igual ao V3).
    """
    n_inicial = len(tickers_entrada)
    if n_inicial == 0:
        return 0.0, [], {}

    peso_unitario = 1.0 / n_inicial
    peso_maximo   = CAP_MULTIPLICADOR * peso_unitario   # ex: 40% para 5 posicoes

    posicoes: dict[str, PosicaoV3c] = {
        ticker: PosicaoV3c(
            ticker        = ticker,
            preco_entrada = preco_entrada[ticker],
            peso          = peso_unitario,
        )
        for ticker in tickers_entrada
    }

    log_eventos:   list[dict] = []
    valor_carteira             = 1.0
    # Peso em caixa ocioso acumulado (nao contribui para retorno)
    caixa_ocioso               = 0.0

    for data in pregoes_semana:
        retorno_dia_carteira = 0.0

        for ticker in tickers_entrada:
            pos = posicoes[ticker]

            if not pos.ativo:
                continue

            preco_hoje = obter_adj_close(ticker, data, df_precos)
            if preco_hoje is None:
                continue

            ret_acumulado = preco_hoje / pos.preco_entrada - 1

            if ret_acumulado <= STOP_LOSS_LIMITE:
                # ─── STOP ATINGIDO ──────────────────────────────────────
                pos.ativo       = False
                pos.preco_stop  = preco_hoje
                pos.data_stop   = str(data)
                pos.ret_no_stop = ret_acumulado

                peso_liberado = pos.peso

                # Contribuicao do dia do stop (peso ANTES de zerar)
                preco_ontem = obter_adj_close_anterior(ticker, data, df_precos)
                if preco_ontem is not None:
                    ret_dia = preco_hoje / preco_ontem - 1
                    retorno_dia_carteira += ret_dia * peso_liberado

                # Zera e redistribui seletivamente
                pos.peso = 0.0
                sobra = _redistribuir(
                    peso_liberado, posicoes, data, df_precos, peso_maximo
                )
                caixa_ocioso += sobra

                log_eventos.append({
                    "data":               str(data),
                    "evento":             "STOP_LOSS",
                    "ticker":             ticker,
                    "ret_acumulado":      ret_acumulado,
                    "preco_entrada":      pos.preco_entrada,
                    "preco_stop":         preco_hoje,
                    "peso_no_stop":       peso_liberado,
                    "peso_redistribuido": peso_liberado - sobra,
                    "peso_caixa":         sobra,
                })
                continue

            # ─── Posicao ativa sem stop — retorno normal ─────────────────
            preco_ontem = obter_adj_close_anterior(ticker, data, df_precos)
            if preco_ontem is None:
                continue
            ret_dia = preco_hoje / preco_ontem - 1
            retorno_dia_carteira += ret_dia * pos.peso

        valor_carteira *= (1 + retorno_dia_carteira)

    return valor_carteira - 1, log_eventos, posicoes


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== BACKTEST V3c --- Redistribuicao Seletiva (positivas + cap 2x) ===")

    with open(config.BACKTEST_V2_CARTEIRAS_PATH, encoding="utf-8") as f:
        carteiras_v2 = json.load(f)
    with open(config.BACKTEST_V2_RESULTADO_PATH, encoding="utf-8") as f:
        resultado_v2 = json.load(f)

    v3_path  = config.DATA_DIR / "backtest_resultado_v3.json"
    v3b_path = config.DATA_DIR / "backtest_resultado_v3b.json"
    resultado_v3  = json.load(open(v3_path,  encoding="utf-8")) if v3_path.exists()  else None
    resultado_v3b = json.load(open(v3b_path, encoding="utf-8")) if v3b_path.exists() else None

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

        assert pd.Timestamp(data_formacao) > pd.Timestamp(data_corte), (
            f"Look-ahead bias: {data_formacao} <= {data_corte}"
        )

        pregoes = obter_pregoes_entre(data_formacao, data_vigencia_fim, df_precos)
        retorno_carteira, log_eventos, posicoes_semana = simular_semana_v3c(
            tickers_entrada, preco_entrada, pregoes, df_precos
        )

        # Enriquece cada ticker com preco_saida e retorno_semana (para frontend)
        score_map = {t["ticker"]: t.get("score") for t in semana["tickers"]}
        dt_vigencia_fim_date = date.fromisoformat(data_vigencia_fim)
        tickers_enriquecidos = []
        for ticker in tickers_entrada:
            pos = posicoes_semana[ticker]
            ent = pos.preco_entrada
            score = score_map.get(ticker)
            if not pos.ativo:
                # Posição stopada: preço de saída é o preço no dia do stop
                sai = pos.preco_stop
                ret = pos.ret_no_stop
            else:
                # Posição ativa até o fim da semana: preço de fechamento de sexta
                sai = obter_adj_close(ticker, dt_vigencia_fim_date, df_precos)
                ret = (sai / ent - 1) if (sai is not None and ent) else None
            tickers_enriquecidos.append({
                "ticker":         ticker,
                "score":          score,
                "preco_entrada":  round(ent, 4) if ent is not None else None,
                "preco_saida":    round(sai, 4) if sai is not None else None,
                "retorno_semana": round(ret, 6) if ret is not None else None,
            })

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
            "tickers":             tickers_enriquecidos,
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

    resultado = {
        "metadata": {
            "data_geracao":        date.today().isoformat(),
            "janela_inicio":       resultados[0]["data_formacao"],
            "janela_fim":          resultados[-1]["data_vigencia_fim"],
            "n_semanas_simuladas": len(resultados),
            "versao_formula":      "v3c",
            "versao_scoring":      "v2",
            "stop_loss_pct":       -0.05,
            "stop_referencia":     "preco_entrada_fixo",
            "stop_execucao":       "fechamento_dia",
            "capital_apos_stop":   "redistribuicao_seletiva_positivas",
            "redistribuicao":      "pro_rata_apenas_positivas_cap_2x",
            "cap_multiplicador":   CAP_MULTIPLICADOR,
        },
        "metricas_estrategia":  metricas,
        "metricas_stop":        metricas_stop,
        "metricas_benchmarks":  {"ibov": metricas_ibov, "smll": metricas_smll, "cdi": metricas_cdi},
        "alphas":               alphas,
        "equity_curve":         equity_curve,
    }

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BACKTEST_V3C_RESULTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
    with open(BACKTEST_V3C_CARTEIRAS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"metadata": {"n_carteiras": len(resultados), "versao_formula": "v3c"},
             "carteiras": resultados},
            f, ensure_ascii=False, indent=2, default=str,
        )

    log.info(f"  -> {BACKTEST_V3C_RESULTADO_PATH}")
    log.info(f"  -> {BACKTEST_V3C_CARTEIRAS_PATH}")

    # -----------------------------------------------------------------------
    # Comparativo 4-way: V2 / V3 / V3b / V3c
    # -----------------------------------------------------------------------
    mv2  = resultado_v2["metricas_estrategia"]
    mv3  = resultado_v3["metricas_estrategia"]  if resultado_v3  else {}
    mv3b = resultado_v3b["metricas_estrategia"] if resultado_v3b else {}
    mv3c = metricas

    print()
    print("=" * 80)
    print("  COMPARATIVO V2 / V3 (caixa) / V3b (redistrib. total) / V3c (positivas+cap)")
    print("=" * 80)
    print(f"{'Metrica':<30}{'V2':>10}{'V3':>10}{'V3b':>10}{'V3c':>10}{'V3c-V3':>9}")
    print("-" * 80)

    linhas = [
        ("Retorno total",           "retorno_total",           "pct"),
        ("Retorno anualizado",      "retorno_anualizado",      "pct"),
        ("Volatilidade anualizada", "volatilidade_anualizada", "pct"),
        ("Sharpe ratio",            "sharpe_ratio",            "num"),
        ("Max drawdown",            "max_drawdown",            "pct"),
        ("Win rate semanal",        "win_rate_semanal",        "pct"),
        ("Hit rate vs SMLL",        "hit_rate_vs_smll",        "pct"),
    ]
    for label, key, fmt in linhas:
        v2v  = mv2.get(key, 0)
        v3v  = mv3.get(key, 0)
        v3bv = mv3b.get(key, 0)
        v3cv = mv3c.get(key, 0)
        delta = v3cv - v3v
        if fmt == "pct":
            print(f"{label:<30}{v2v*100:>9.2f}%{v3v*100:>9.2f}%{v3bv*100:>9.2f}%{v3cv*100:>9.2f}%{delta*100:>+8.2f}%")
        else:
            print(f"{label:<30}{v2v:>10.4f}{v3v:>10.4f}{v3bv:>10.4f}{v3cv:>10.4f}{delta:>+9.4f}")

    print()
    print(f"Alphas V3c: vs IBOV={alphas['vs_ibov']*100:+.2f}%  "
          f"vs SMLL={alphas['vs_smll']*100:+.2f}%  vs CDI={alphas['vs_cdi']*100:+.2f}%")
    print()
    print(f"Stops V3c: {metricas_stop['n_stops_total']} total / "
          f"{metricas_stop['n_semanas_com_stop']} semanas ({metricas_stop['pct_semanas_com_stop']*100:.1f}%)")
    print(f"Retorno medio pos stopada: {metricas_stop['retorno_medio_pos_stopada']*100:.2f}%")
    print(f"Semanas zeradas: {metricas_stop['semanas_com_carteira_zerada']}")

    ds = mv3c.get("sharpe_ratio", 0) - mv3.get("sharpe_ratio", 0)
    dr = mv3c.get("retorno_anualizado", 0) - mv3.get("retorno_anualizado", 0)
    print()
    print("=" * 80)
    if ds > 0 and dr > 0:
        print("VEREDICTO: V3c MELHOR que V3 -- redistribuicao seletiva AJUDA")
    elif ds < 0 and dr < 0:
        print("VEREDICTO: V3c PIOR que V3  -- manter caixa ocioso (V3 oficial)")
    else:
        print(f"VEREDICTO: INCONCLUSIVO (dSharpe={ds:+.4f}, dRet={dr*100:+.2f}%)")
    print("=" * 80)


if __name__ == "__main__":
    main()
