"""
Fase 7 — Atualização semanal do histórico real.

Executado toda sexta-feira pelo GitHub Actions (após o pipeline normal).
Append idempotente: não duplica se semana já existe.

Uso:
  python src/update_historico_real.py
"""
from __future__ import annotations

import json
import tempfile
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

import config
from src.logger import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _semana_iso(d: date) -> str:
    cal = d.isocalendar()
    return f"{cal.year}-W{cal.week:02d}"


def _retorno_benchmark(bench_df: pd.DataFrame, col: str, dt_inicio: date, dt_fim: date) -> float:
    """Retorno acumulado do benchmark entre dt_inicio e dt_fim."""
    if col not in bench_df.columns:
        return 0.0
    janela = bench_df[
        (bench_df["date"].dt.date > dt_inicio) &
        (bench_df["date"].dt.date <= dt_fim)
    ][col].dropna()
    if janela.empty:
        return 0.0
    return float((1 + janela).prod() - 1)


def _recalcular_acumulado(semanas: list[dict]) -> dict:
    if not semanas:
        return {}

    ret_cart = [(1 + s.get("retorno_carteira", 0)) for s in semanas]
    ret_ibov = [(1 + s.get("retorno_ibov", 0)) for s in semanas]
    ret_smll = [(1 + s.get("retorno_smll", 0)) for s in semanas]
    ret_cdi  = [(1 + s.get("retorno_cdi", 0)) for s in semanas]

    from math import prod
    n = len(semanas)
    win_ibov = sum(1 for s in semanas if s.get("carteira_venceu_ibov"))
    win_smll = sum(1 for s in semanas if s.get("carteira_venceu_smll"))
    pos = sum(1 for s in semanas if s.get("retorno_carteira", 0) > 0)

    return {
        "retorno_total": round(prod(ret_cart) - 1, 6),
        "retorno_ibov_total": round(prod(ret_ibov) - 1, 6),
        "retorno_smll_total": round(prod(ret_smll) - 1, 6),
        "retorno_cdi_total": round(prod(ret_cdi) - 1, 6),
        "win_rate_vs_ibov": round(win_ibov / n, 4),
        "win_rate_vs_smll": round(win_smll / n, 4),
        "n_semanas_positivas": pos,
        "n_semanas_negativas": n - pos,
    }


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

def _calcular_retorno_carteira(carteira_json: dict, df_precos: pd.DataFrame) -> list[dict]:
    """Calcula retorno real de cada posição da carteira na semana."""
    data_fim_str = carteira_json["metadata"].get("data_vigencia_fim")
    if not data_fim_str:
        return []

    dt_fim = pd.Timestamp(data_fim_str)
    resultados = []

    for t in carteira_json.get("tickers", []):
        ticker = t["ticker"]
        preco_entrada = t.get("preco_entrada")
        if not preco_entrada:
            continue

        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"] <= dt_fim)
        ].sort_values("date")

        if df_t.empty:
            continue

        preco_saida = float(df_t["adj_close"].iloc[-1])
        resultados.append({
            "ticker": ticker,
            "rank_na_formacao": t.get("rank_na_formacao"),
            "score_na_formacao": t.get("score_na_formacao"),
            "preco_entrada": round(preco_entrada, 4),
            "preco_saida": round(preco_saida, 4),
            "retorno_semana": round(preco_saida / preco_entrada - 1, 6),
        })

    return resultados


def append_semana() -> None:
    """Appenda a semana encerrada ao historico_real.json."""
    # Carrega carteira V2 atual
    if not config.CARTEIRA_V2_ATUAL_PATH.exists():
        log.warning("carteira_atual_v2.json não encontrado — pulando update histórico real.")
        return

    with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
        carteira_json = json.load(f)

    meta = carteira_json.get("metadata", {})
    data_formacao_str = meta.get("data_formacao")
    data_vigencia_fim_str = meta.get("data_vigencia_fim")
    data_vigencia_inicio_str = meta.get("data_vigencia_inicio", data_formacao_str)

    if not data_formacao_str or not data_vigencia_fim_str:
        log.warning("Carteira V2 sem data_formacao ou data_vigencia_fim — pulando.")
        return

    dt_formacao = date.fromisoformat(data_formacao_str)
    dt_vigencia_fim = date.fromisoformat(data_vigencia_fim_str)

    # Só appenda se a semana já encerrou
    if date.today() < dt_vigencia_fim:
        log.info(
            f"Semana {_semana_iso(dt_formacao)} ainda não encerrou "
            f"(vigência até {dt_vigencia_fim}) — pulando."
        )
        return

    semana_id = _semana_iso(dt_formacao)

    # Carrega histórico existente ou inicializa
    hist_path = config.HISTORICO_REAL_PATH
    if hist_path.exists():
        with open(hist_path, encoding="utf-8") as f:
            historico = json.load(f)
    else:
        historico = {
            "metadata": {
                "data_inicio_operacao": data_formacao_str,
                "total_semanas_reais": 0,
                "ultima_atualizacao": date.today().isoformat(),
            },
            "semanas": [],
            "acumulado": {},
        }

    # Idempotência
    semanas_existentes = {s["semana"] for s in historico["semanas"]}
    if semana_id in semanas_existentes:
        log.info(f"Semana {semana_id} já registrada — pulando.")
        return

    # Preços V2
    if not config.PRECOS_V2_PARQUET_PATH.exists():
        log.warning("precos_v2.parquet não encontrado — pulando update histórico real.")
        return

    df_precos = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")
    df_precos["date"] = pd.to_datetime(df_precos["date"])

    # Retornos das posições
    tickers_com_retorno = _calcular_retorno_carteira(carteira_json, df_precos)
    if not tickers_com_retorno:
        log.warning(f"Sem retornos calculados para a semana {semana_id} — pulando.")
        return

    retorno_carteira = sum(t["retorno_semana"] for t in tickers_com_retorno) / len(tickers_com_retorno)

    # Benchmarks
    bench_df: pd.DataFrame | None = None
    if config.BENCHMARKS_PARQUET_PATH.exists():
        bench_df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
        bench_df["date"] = pd.to_datetime(bench_df["date"])

    dt_inicio = date.fromisoformat(data_vigencia_inicio_str) - __import__("datetime").timedelta(days=1)

    ret_ibov = _retorno_benchmark(bench_df, "ibov", dt_inicio, dt_vigencia_fim) if bench_df is not None else 0.0
    ret_smll = _retorno_benchmark(bench_df, "smll", dt_inicio, dt_vigencia_fim) if bench_df is not None else 0.0
    ret_cdi  = _retorno_benchmark(bench_df, "cdi",  dt_inicio, dt_vigencia_fim) if bench_df is not None else 0.0

    entrada = {
        "semana": semana_id,
        "data_formacao": data_formacao_str,
        "data_corte_dados": meta.get("data_corte_dados", ""),
        "data_vigencia_fim": data_vigencia_fim_str,
        "bootstrap": meta.get("bootstrap_retroativo", False),
        "tickers": tickers_com_retorno,
        "n_posicoes": meta.get("n_posicoes", len(tickers_com_retorno)),
        "retorno_carteira": round(retorno_carteira, 6),
        "retorno_ibov": round(ret_ibov, 6),
        "retorno_smll": round(ret_smll, 6),
        "retorno_cdi": round(ret_cdi, 6),
        "alpha_vs_ibov": round(retorno_carteira - ret_ibov, 6),
        "alpha_vs_smll": round(retorno_carteira - ret_smll, 6),
        "carteira_venceu_ibov": retorno_carteira > ret_ibov,
        "carteira_venceu_smll": retorno_carteira > ret_smll,
    }

    historico["semanas"].append(entrada)
    historico["acumulado"] = _recalcular_acumulado(historico["semanas"])
    historico["metadata"]["total_semanas_reais"] = len(historico["semanas"])
    historico["metadata"]["ultima_atualizacao"] = date.today().isoformat()

    # Escrita atômica: escreve em temp e renomeia
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = hist_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2, default=str)
    shutil.move(str(tmp), str(hist_path))

    log.info(
        f"Semana {semana_id} registrada no histórico real. "
        f"Total: {len(historico['semanas'])} semanas. "
        f"Retorno: {retorno_carteira:.2%}"
    )


if __name__ == "__main__":
    append_semana()
