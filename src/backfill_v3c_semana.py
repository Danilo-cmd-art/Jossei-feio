"""
backfill_v3c_semana.py — Reconstrói retroativamente o estado V3c live de uma
semana específica usando preços do parquet (sem yfinance).

Uso:
    python src/backfill_v3c_semana.py --formacao 2026-05-18

O que faz:
  1. Calcula scores V2 com data_corte = último pregão antes da data de formação
  2. Forma carteira Top-N (5 posições)
  3. Para cada pregão da semana (formacao..vigencia_fim):
       - Baixa adj_close de cada posição do parquet
       - Aplica regra de stop loss -5% acumulado vs preco_entrada
       - Redistribui peso entre posições positivas (cap 2x); excesso → caixa
       - Calcula retorno_dia e ret_acumulado da carteira
  4. Salva estado em data/carteira_v3c_estado.json
  5. Gera arquivo frontend em historico/carteira_YYYY-WWW.json

NÃO usa yfinance — todos os preços vêm de data/precos_v2.parquet.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import config
from src import benchmarks as bm
from src.logger import get_logger
from src.portfolio import (
    obter_pregoes,
    ultimo_pregao_antes,
    ultimo_pregao_da_semana,
    formar_carteira,
)
from src.portfolio_v3c_live import (
    STOP_LOSS_LIMITE,
    CAP_MULTIPLICADOR,
    _redistribuir,
    salvar_estado,
    gerar_carteira_json,
    salvar_carteira_historico,
)
from src.scoring_v2 import calcular_scores_v2

log = get_logger()


def _obter_preco_close(
    df_precos: pd.DataFrame,
    ticker: str,
    data: date,
) -> float | None:
    """Adj close para ticker na data. None se não houver pregão."""
    sub = df_precos[
        (df_precos["ticker"] == ticker) &
        (df_precos["date"].dt.date == data)
    ]
    if sub.empty:
        return None
    val = sub.iloc[0]["adj_close"]
    return float(val) if pd.notna(val) else None


def backfill(formacao: date) -> None:
    log.info(f"=== BACKFILL V3c — semana iniciada em {formacao} ===")

    # -------------------------------------------------------------------
    # 1. Carregar universo + parquet
    # -------------------------------------------------------------------
    with open(config.UNIVERSO_V2_PATH, encoding="utf-8") as f:
        universo = json.load(f)["tickers"]

    df_precos = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")
    df_precos["date"] = pd.to_datetime(df_precos["date"])

    bench_df: pd.DataFrame | None = None
    try:
        bench_df = bm.ler_benchmarks()
    except Exception as e:
        log.warning(f"Benchmarks indisponíveis: {e}")

    # -------------------------------------------------------------------
    # 2. Determinar datas
    # -------------------------------------------------------------------
    pregoes_idx = obter_pregoes(df_precos)
    data_corte  = ultimo_pregao_antes(formacao, pregoes_idx)
    if data_corte is None:
        raise RuntimeError(f"Sem pregão antes de {formacao}")

    data_fim = ultimo_pregao_da_semana(formacao, pregoes_idx) or formacao
    semana_iso = formacao.strftime("%Y-W%V")

    log.info(f"Semana {semana_iso}  corte={data_corte}  fim={data_fim}")

    # -------------------------------------------------------------------
    # 3. Scoring V2 + formar carteira
    # -------------------------------------------------------------------
    scores = calcular_scores_v2(df_precos, universo, data_corte)
    selecionados = formar_carteira(scores, data_corte, df_precos)

    if not selecionados:
        raise RuntimeError("Carteira vazia — nenhum ticker passou F1+F2")

    n             = len(selecionados)
    peso_unitario = 1.0 / n
    peso_maximo   = CAP_MULTIPLICADOR * peso_unitario
    scores_map    = {s["ticker"]: s for s in scores}

    posicoes = []
    for t in selecionados:
        ticker = t["ticker"]
        s      = scores_map.get(ticker, {})
        posicoes.append({
            "ticker":          ticker,
            "ticker_yf":       ticker + ".SA",
            "rank_formacao":   s.get("rank", 0),
            "score_formacao":  round(float(s.get("score_final", 0)), 4),
            "preco_entrada":   t.get("preco_entrada"),
            "preco_ref_dia":   t.get("preco_entrada"),
            "peso_atual":      peso_unitario,
            "ativo":           True,
            "preco_atual":     t.get("preco_entrada"),
            "ret_acumulado":   0.0,
            "preco_stop":      None,
            "data_stop":       None,
            "ret_no_stop":     None,
        })

    log.info(f"Tickers formados: {[p['ticker'] for p in posicoes]}")

    estado = {
        "versao":               "v3c",
        "semana":               semana_iso,
        "data_formacao":        formacao.isoformat(),
        "data_corte_dados":     data_corte.isoformat(),
        "data_vigencia_inicio": formacao.isoformat(),
        "data_vigencia_fim":    data_fim.isoformat(),
        "n_posicoes_inicial":   n,
        "peso_unitario":        peso_unitario,
        "peso_maximo":          peso_maximo,
        "posicoes":             posicoes,
        "stops_semana":         [],
        "dias_processados":     [],
        "performance_diaria":   [],
        "ultima_atualizacao":   datetime.now().isoformat(timespec="seconds"),
        "modo_ultima_atualizacao": "nova_semana_backfill",
    }

    # -------------------------------------------------------------------
    # 4. Loop dia a dia: aplicar stop loss + redistribuição
    # -------------------------------------------------------------------
    pregoes_semana = sorted(
        d for d in df_precos["date"].dt.date.unique()
        if formacao <= d <= data_fim
    )
    log.info(f"Processando {len(pregoes_semana)} pregões: {pregoes_semana}")

    for d in pregoes_semana:
        d_str = d.isoformat()

        # Baixar precos do dia para posicoes ATIVAS
        precos_hoje: dict[str, float] = {}
        for pos in posicoes:
            if not pos["ativo"]:
                continue
            p = _obter_preco_close(df_precos, pos["ticker"], d)
            if p is not None:
                precos_hoje[pos["ticker"]] = p

        if not precos_hoje:
            log.warning(f"  {d_str}: sem preços, ignorando")
            continue

        retorno_dia = 0.0

        for pos in posicoes:
            if not pos["ativo"]:
                continue
            ticker     = pos["ticker"]
            preco_hoje = precos_hoje.get(ticker)
            if preco_hoje is None:
                continue

            preco_entrada = pos["preco_entrada"] or preco_hoje
            ret_acum      = preco_hoje / preco_entrada - 1

            preco_ref   = pos.get("preco_ref_dia") or preco_entrada
            ret_dia_pos = preco_hoje / preco_ref - 1 if preco_ref else 0.0

            if ret_acum <= STOP_LOSS_LIMITE:
                # STOP ATINGIDO
                peso_antes = pos["peso_atual"]
                retorno_dia += ret_dia_pos * peso_antes

                pos.update({
                    "ativo":         False,
                    "preco_atual":   preco_hoje,
                    "ret_acumulado": round(ret_acum, 6),
                    "preco_stop":    preco_hoje,
                    "data_stop":     d_str,
                    "ret_no_stop":   round(ret_acum, 6),
                    "peso_atual":    0.0,
                })

                caixa = _redistribuir(peso_antes, posicoes, precos_hoje, peso_maximo)
                estado["stops_semana"].append({
                    "data":               d_str,
                    "evento":             "STOP_LOSS",
                    "ticker":             ticker,
                    "ret_acumulado":      round(ret_acum, 6),
                    "preco_entrada":      preco_entrada,
                    "preco_stop":         preco_hoje,
                    "peso_no_stop":       round(peso_antes, 6),
                    "peso_redistribuido": round(peso_antes - caixa, 6),
                    "peso_caixa":         round(caixa, 6),
                })
                log.info(f"  {d_str} STOP {ticker}: ret={ret_acum*100:.2f}% "
                         f"redistrib={(peso_antes-caixa)*100:.1f}% caixa={caixa*100:.1f}%")
            else:
                retorno_dia += ret_dia_pos * pos["peso_atual"]
                pos.update({
                    "preco_atual":   preco_hoje,
                    "ret_acumulado": round(ret_acum, 6),
                    "preco_ref_dia": preco_hoje,
                })

        # Compor retorno acumulado
        perf = estado["performance_diaria"]
        ret_acum_anterior = perf[-1]["retorno_acumulado"] if perf else 0.0
        ret_acum_total    = (1 + ret_acum_anterior) * (1 + retorno_dia) - 1

        perf.append({
            "data":              d_str,
            "retorno_dia":       round(retorno_dia, 6),
            "retorno_acumulado": round(ret_acum_total, 6),
            "modo":              "close",
        })
        estado["dias_processados"].append(d_str)
        log.info(f"  {d_str} ret_dia={retorno_dia*100:+.3f}% "
                 f"acum={ret_acum_total*100:+.3f}%")

    estado["ultima_atualizacao"]      = datetime.now().isoformat(timespec="seconds")
    estado["modo_ultima_atualizacao"] = "close_backfill"

    # -------------------------------------------------------------------
    # 5. Salvar estado + frontend JSON
    # -------------------------------------------------------------------
    salvar_estado(estado)

    carteira = gerar_carteira_json(estado, bench_df)
    salvar_carteira_historico(carteira, semana_iso)

    log.info("=== BACKFILL CONCLUÍDO ===")
    log.info(f"Retorno final V3c: {estado['performance_diaria'][-1]['retorno_acumulado']*100:+.2f}%")
    log.info(f"Stops aplicados:   {len(estado['stops_semana'])}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--formacao", required=True,
                   help="Data de formação da semana (YYYY-MM-DD, segunda-feira)")
    args = p.parse_args()
    backfill(date.fromisoformat(args.formacao))


if __name__ == "__main__":
    main()
