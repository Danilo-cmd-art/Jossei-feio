"""
Fase 3 V2 — Scoring e Carteira.

Usa calcular_scores_v2, universo_v2.json e precos_v2.parquet.
Salva em scores_atual_v2.json e carteira_atual_v2.json.
Não modifica nenhum arquivo V1.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

import config
from src.scoring_v2 import calcular_scores_v2
from src.portfolio import (
    obter_pregoes,
    ultimo_pregao_antes,
    ultimo_pregao_da_semana,
    formar_carteira,
    calcular_performance_diaria,
    atualizar_carteira,
    deve_formar_nova_carteira,
)
from src import benchmarks
from src.logger import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Persistência V2
# ---------------------------------------------------------------------------

def salvar_scores_v2(
    scores: list[dict],
    data_ref: date,
    data_corte: date,
    universo_versao: str,
) -> None:
    """Salva scores_atual_v2.json e histórico diário."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": {
            "data_referencia": data_ref.isoformat(),
            "data_corte_dados": data_corte.isoformat(),
            "total_tickers": len(scores),
            "universo_versao": universo_versao,
            "versao_formula": "v2",
        },
        "scores": scores,
    }

    with open(config.SCORES_V2_ATUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    hist_path = config.HISTORICO_DIR / f"scores_v2_{data_ref.isoformat()}.json"
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Scores V2 salvos: {config.SCORES_V2_ATUAL_PATH}")


def salvar_carteira_v2(carteira: dict) -> None:
    """Salva carteira_atual_v2.json e histórico semanal."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    with open(config.CARTEIRA_V2_ATUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(carteira, f, ensure_ascii=False, indent=2, default=str)

    data_formacao = date.fromisoformat(carteira["metadata"]["data_formacao"])
    semana = data_formacao.strftime("%Y-W%V")
    hist_path = config.HISTORICO_DIR / f"carteira_v2_{semana}.json"
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(carteira, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"Carteira V2 salva: {config.CARTEIRA_V2_ATUAL_PATH}")


# ---------------------------------------------------------------------------
# Atualização incremental de preços V2
# ---------------------------------------------------------------------------

def _atualizar_precos_v2(universo_v2: list[dict]) -> pd.DataFrame:
    """
    Atualização incremental do precos_v2.parquet.
    Baixa apenas dados novos desde a última data registrada.
    """
    from src.fetch_prices import download_precos
    from src.storage import merge_incremental

    tickers_v2 = [t["ticker_b3"] for t in universo_v2]

    # Carrega existente
    df_existente: pd.DataFrame | None = None
    if config.PRECOS_V2_PARQUET_PATH.exists():
        df_existente = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")
        df_existente["date"] = pd.to_datetime(df_existente["date"])

    hoje = date.today()

    if df_existente is not None and not df_existente.empty:
        df_v2 = df_existente[df_existente["ticker"].isin(tickers_v2)]
        if not df_v2.empty:
            ultima = df_v2["date"].max()
            if hasattr(ultima, "date"):
                ultima = ultima.date()
            start = ultima + timedelta(days=1)
        else:
            start = hoje - timedelta(days=1100)
    else:
        start = hoje - timedelta(days=1100)

    if start >= hoje:
        log.info("precos_v2.parquet já atualizado para hoje.")
        return df_existente if df_existente is not None else pd.DataFrame()

    log.info(
        f"Baixando preços V2 ({len(tickers_v2)} tickers, {start} → {hoje})..."
    )
    df_novo, falharam = download_precos(tickers_v2, start, hoje)

    if falharam:
        log.warning(f"  {len(falharam)} ticker(s) falharam: {falharam[:10]}")

    if df_novo.empty:
        log.warning("Sem novos dados V2 — usando parquet existente.")
        return df_existente if df_existente is not None else pd.DataFrame()

    # Merge e salva
    if df_existente is not None and not df_existente.empty:
        df_final = merge_incremental(df_existente, df_novo)
    else:
        df_final = df_novo

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df_final.to_parquet(
        config.PRECOS_V2_PARQUET_PATH,
        engine="pyarrow",
        compression="snappy",
        index=False,
    )
    log.info(
        f"precos_v2.parquet atualizado: {len(df_final):,} linhas, "
        f"{df_final['ticker'].nunique()} tickers"
    )
    return df_final


# ---------------------------------------------------------------------------
# Bootstrap V2
# ---------------------------------------------------------------------------

def executar_bootstrap_v2(
    df_precos: pd.DataFrame,
    universo: list[dict],
    hoje: date,
) -> dict:
    """
    Bootstrap V2: carteira retroativa da semana corrente usando scoring_v2.
    GARANTIA: assertion anti-look-ahead em calcular_scores_v2.
    """
    pregoes = obter_pregoes(df_precos)
    segunda_semana = hoje - timedelta(days=hoje.weekday())
    data_corte = ultimo_pregao_antes(segunda_semana, pregoes)

    if data_corte is None:
        raise RuntimeError("Não foi possível determinar data_corte para bootstrap V2")

    log.info(
        f"Bootstrap V2: segunda={segunda_semana}, "
        f"data_corte={data_corte}, hoje={hoje}"
    )

    scores = calcular_scores_v2(df_precos, universo, data_corte)
    tickers_carteira = formar_carteira(scores, data_corte, df_precos)
    performance = calcular_performance_diaria(
        tickers_carteira, data_corte, df_precos, pregoes
    )

    ret_total = performance[-1]["retorno_acumulado"] if performance else 0.0

    for t in tickers_carteira:
        ticker = t["ticker"]
        df_t = df_precos[
            (df_precos["ticker"] == ticker) &
            (df_precos["date"].dt.date <= hoje)
        ].sort_values("date")
        if not df_t.empty:
            preco_atual = float(df_t["adj_close"].iloc[-1])
            base = t.get("preco_entrada") or 0
            t["preco_atual"] = preco_atual
            t["retorno_acumulado"] = round(preco_atual / base - 1, 6) if base else 0.0

    data_vigencia_fim = ultimo_pregao_da_semana(hoje, pregoes) or hoje
    n = len(tickers_carteira)

    return {
        "metadata": {
            "data_formacao": segunda_semana.isoformat(),
            "data_corte_dados": data_corte.isoformat(),
            "data_vigencia_inicio": segunda_semana.isoformat(),
            "data_vigencia_fim": data_vigencia_fim.isoformat(),
            "bootstrap_retroativo": True,
            "n_posicoes": n,
            "peso_por_posicao": round(1 / n, 6) if n > 0 else 0.0,
            "proxima_carteira_oficial": (
                segunda_semana + timedelta(weeks=1)
            ).isoformat(),
            "versao_formula": "v2",
        },
        "tickers": tickers_carteira,
        "performance_diaria": performance,
        "retorno_acumulado_total": round(ret_total, 6),
    }


# ---------------------------------------------------------------------------
# Entrypoint Fase 3 V2
# ---------------------------------------------------------------------------

def run(df_precos_v1=None, universo_v1=None) -> dict:
    """
    Executa Fase 3 V2 completa.
    Parâmetros ignorados — mantidos por compatibilidade de assinatura.
    """
    log.info("=== FASE 3 V2: Scoring e Carteira ===")

    # Carrega universo V2
    if not config.UNIVERSO_V2_PATH.exists():
        log.error("universo_v2.json não encontrado. Execute build_universe_v2 primeiro.")
        return {}
    with open(config.UNIVERSO_V2_PATH, encoding="utf-8") as f:
        universo_json = json.load(f)
    universo_v2 = universo_json["tickers"]
    universo_versao = "v2-" + universo_json["metadata"].get("data_geracao", "")[:7]
    log.info(f"Universo V2: {len(universo_v2)} tickers ({universo_versao})")

    # Atualiza preços V2
    df_precos = _atualizar_precos_v2(universo_v2)
    if df_precos.empty:
        log.error("Sem preços disponíveis para V2.")
        return {}

    hoje = date.today()
    pregoes = obter_pregoes(df_precos)

    # Carrega carteira existente
    carteira_existente: dict | None = None
    if config.CARTEIRA_V2_ATUAL_PATH.exists():
        with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
            carteira_existente = json.load(f)

    # Benchmarks
    bench_df = benchmarks.ler_benchmarks()

    eh_bootstrap = carteira_existente is None

    if eh_bootstrap:
        log.info("Bootstrap V2: formando carteira retroativa")
        carteira = executar_bootstrap_v2(df_precos, universo_v2, hoje)
        data_corte = date.fromisoformat(carteira["metadata"]["data_corte_dados"])
        scores = calcular_scores_v2(df_precos, universo_v2, data_corte)
        salvar_scores_v2(scores, hoje, data_corte, universo_versao)
        salvar_carteira_v2(carteira)

    elif deve_formar_nova_carteira(carteira_existente, hoje):
        log.info("Formando nova carteira V2 (segunda-feira)")
        data_corte = ultimo_pregao_antes(hoje, pregoes)
        scores = calcular_scores_v2(df_precos, universo_v2, data_corte)
        tickers_carteira = formar_carteira(scores, data_corte, df_precos)
        data_vigencia_fim = ultimo_pregao_da_semana(hoje, pregoes) or hoje
        n = len(tickers_carteira)

        carteira = {
            "metadata": {
                "data_formacao": hoje.isoformat(),
                "data_corte_dados": data_corte.isoformat(),
                "data_vigencia_inicio": hoje.isoformat(),
                "data_vigencia_fim": data_vigencia_fim.isoformat(),
                "bootstrap_retroativo": False,
                "n_posicoes": n,
                "peso_por_posicao": round(1 / n, 6) if n > 0 else 0.0,
                "versao_formula": "v2",
            },
            "tickers": tickers_carteira,
            "performance_diaria": [],
            "retorno_acumulado_total": 0.0,
        }
        salvar_scores_v2(scores, hoje, data_corte, universo_versao)
        salvar_carteira_v2(carteira)

    else:
        log.info("Atualizando performance da carteira V2 ativa")
        data_corte = date.fromisoformat(
            carteira_existente["metadata"]["data_corte_dados"]
        )
        scores = calcular_scores_v2(df_precos, universo_v2, data_corte)
        salvar_scores_v2(scores, hoje, data_corte, universo_versao)
        carteira = atualizar_carteira(
            carteira_existente, df_precos, pregoes, hoje, bench_df
        )
        salvar_carteira_v2(carteira)

    log.info("=== FASE 3 V2 CONCLUÍDA ===")
    return carteira
