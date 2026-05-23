"""
Orquestrador principal — executa Fases 1 a 4 em sequência.
Uso: python run.py [--csv CAMINHO_CSV] [--fase 1|2|3|4]
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
    parser = argparse.ArgumentParser(description="SmallRadar — pipeline de small caps BR")
    parser.add_argument("--csv", type=Path, default=config.STATUS_INVEST_CSV_DEFAULT,
                        help="Caminho para o CSV do Status Invest")
    parser.add_argument("--fase", type=int, choices=[1, 2, 3, 4], default=None,
                        help="Executar apenas uma fase específica")
    parser.add_argument("--reconstruir-universo", action="store_true",
                        help="Força reexecução da Fase 1 mesmo se universo_atual.json existir")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("SmallRadar — iniciando pipeline")
    log.info("=" * 60)

    rodar_todas = args.fase is None

    # -----------------------------------------------------------------------
    # Fase 1 — Universo
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 1:
        if args.reconstruir_universo or not config.UNIVERSO_ATUAL_PATH.exists():
            from src.build_universe import run as fase1
            fase1(args.csv)
        else:
            log.info("Fase 1: universo_atual.json já existe, pulando (use --reconstruir-universo pra forçar)")

    if not config.UNIVERSO_ATUAL_PATH.exists():
        log.error("universo_atual.json não encontrado. Execute a Fase 1 primeiro.")
        sys.exit(1)

    with open(config.UNIVERSO_ATUAL_PATH, encoding="utf-8") as f:
        universo_json = json.load(f)
    universo = universo_json["tickers"]
    universo_versao = universo_json["metadata"].get("data_geracao", "")[:7]

    # -----------------------------------------------------------------------
    # Fase 2 — Coleta de preços
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 2:
        from src.fetch_prices import run as fase2
        fase2()

    if not config.PRECOS_PARQUET_PATH.exists():
        log.error("precos.parquet não encontrado. Execute a Fase 2 primeiro.")
        sys.exit(1)

    from src import storage
    df_precos = storage.ler_precos()
    log.info(f"Preços carregados: {len(df_precos):,} linhas, "
             f"{df_precos['ticker'].nunique()} tickers")

    # -----------------------------------------------------------------------
    # Fase 3 — Scoring e Carteira
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 3:
        from src.portfolio import run as fase3
        fase3(df_precos, universo, universo_versao)

    # -----------------------------------------------------------------------
    # Fase 4 — Backtest
    # -----------------------------------------------------------------------
    if rodar_todas or args.fase == 4:
        from src.backtest import run as fase4
        fase4(df_precos, universo)

    log.info("=" * 60)
    log.info("Pipeline concluído com sucesso")
    log.info("=" * 60)

    # Resumo final
    if config.LAST_RUN_SUMMARY_PATH.exists():
        with open(config.LAST_RUN_SUMMARY_PATH, encoding="utf-8") as f:
            summary = json.load(f)
        log.info(f"Status Fase 2: {summary.get('status')}")

    if config.CARTEIRA_ATUAL_PATH.exists():
        with open(config.CARTEIRA_ATUAL_PATH, encoding="utf-8") as f:
            carteira = json.load(f)
        n = carteira["metadata"].get("n_posicoes", 0)
        ret = carteira.get("retorno_acumulado_total", 0)
        bootstrap = carteira["metadata"].get("bootstrap_retroativo", False)
        log.info(f"Carteira atual: {n} posições, retorno={ret:.2%}, bootstrap={bootstrap}")

    if config.BACKTEST_RESULTADO_PATH.exists():
        with open(config.BACKTEST_RESULTADO_PATH, encoding="utf-8") as f:
            bt = json.load(f)
        n_sem = bt["metadata"].get("n_semanas_simuladas", 0)
        ret_total = bt.get("metricas_estrategia", {}).get("retorno_total", 0)
        log.info(f"Backtest: {n_sem} semanas, retorno_total={ret_total:.2%}")


if __name__ == "__main__":
    main()
