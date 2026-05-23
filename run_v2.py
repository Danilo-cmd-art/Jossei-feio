"""
Orquestrador V2 — executa pipeline completo sobre a fórmula V2.

Fases:
  2 → fetch_prices.py    (atualiza precos.parquet — V1 tickers)
  3 → portfolio_v2.py    (precos_v2 incremental + scoring + carteira V2)
  4 → backtest_v2.py     (backtest incremental V2)

Uso:
  python run_v2.py              # todas as fases
  python run_v2.py --fase 3     # só scoring/carteira V2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
from src.logger import get_logger

log = get_logger()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SmallRadar V2 — pipeline de small caps BR"
    )
    parser.add_argument(
        "--fase", type=int, choices=[2, 3, 4], default=None,
        help="Executar apenas uma fase específica (2=preços, 3=scoring, 4=backtest)"
    )
    args = parser.parse_args()

    rodar_todas = args.fase is None

    log.info("=" * 60)
    log.info("SmallRadar V2 — iniciando pipeline")
    log.info("=" * 60)

    # -----------------------------------------------------------------------
    # Fase 2 — Coleta de preços V1 (base para precos_v2)
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 2:
        log.info("--- Fase 2: preços V1 ---")
        from src.fetch_prices import run as fase2
        fase2()

    if not config.PRECOS_PARQUET_PATH.exists():
        log.error("precos.parquet não encontrado. Execute --fase 2 primeiro.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Fase 3 — Scoring V2 e Carteira V2
    # (portfolio_v2.run() faz a atualização incremental do precos_v2.parquet)
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 3:
        log.info("--- Fase 3 V2: scoring e carteira ---")
        from src.portfolio_v2 import run as fase3_v2
        fase3_v2()

    # -----------------------------------------------------------------------
    # Fase 4 — Backtest incremental V2
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 4:
        log.info("--- Fase 4 V2: backtest incremental ---")
        from src.backtest_v2 import run as fase4_v2
        fase4_v2(None, None)

    log.info("=" * 60)
    log.info("Pipeline V2 concluído")
    log.info("=" * 60)

    # Resumo final
    if config.CARTEIRA_V2_ATUAL_PATH.exists():
        with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
            carteira = json.load(f)
        n = carteira["metadata"].get("n_posicoes", 0)
        ret = carteira.get("retorno_acumulado_total", 0)
        bootstrap = carteira["metadata"].get("bootstrap_retroativo", False)
        log.info(
            f"Carteira V2 atual: {n} posições, "
            f"retorno={ret:.2%}, bootstrap={bootstrap}"
        )

    if config.BACKTEST_V2_RESULTADO_PATH.exists():
        with open(config.BACKTEST_V2_RESULTADO_PATH, encoding="utf-8") as f:
            bt = json.load(f)
        n_sem = bt["metadata"].get("n_semanas_simuladas", 0)
        ret_total = bt.get("metricas_estrategia", {}).get("retorno_total", 0)
        log.info(f"Backtest V2: {n_sem} semanas, retorno_total={ret_total:.2%}")

    if config.LAST_RUN_SUMMARY_PATH.exists():
        with open(config.LAST_RUN_SUMMARY_PATH, encoding="utf-8") as f:
            summary = json.load(f)
        log.info(f"Status Fase 2: {summary.get('status')}")


if __name__ == "__main__":
    main()
