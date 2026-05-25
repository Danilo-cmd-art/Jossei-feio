"""
run_v3c.py — Orquestrador do sistema V3c ao vivo.

MODO AUTO (padrão): detectado automaticamente pelo horário UTC
  - Segunda 12:00-12:59 UTC (09:00-09:59 BRT): nova-semana
  - Seg-Sex 21:30-22:00 UTC (18:30-19:00 BRT): close
  - Seg-Sex 13:00-21:29 UTC (10:00-18:29 BRT): intraday

MODOS MANUAIS (sobrescreve o auto):
  python run_v3c.py --mode nova-semana
  python run_v3c.py --mode close
  python run_v3c.py --mode intraday
  python run_v3c.py --mode close --data 2026-05-23   # reprocessar data específica

DEPENDÊNCIAS:
  - universo_v2.json    (métricas fundamentalistas — atualizar mensalmente)
  - data/precos_v2.parquet  (histórico de preços — deve estar atualizado até D-1)

OUTPUTS:
  - data/carteira_v3c_estado.json    (estado interno da semana corrente)
  - historico/carteira_YYYY-WWW.json (consumido pelo frontend)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import config
from src.logger import get_logger
from src.portfolio_v3c_live import (
    carregar_estado,
    estado_expirado,
    nova_semana,
    processar_fechamento,
    atualizar_intraday,
    gerar_carteira_json,
    salvar_carteira_historico,
)

log = get_logger()

# ---------------------------------------------------------------------------
# Detecção automática de modo pelo horário UTC
# ---------------------------------------------------------------------------

def detectar_modo(now_utc: datetime) -> str:
    """
    Determina o modo de operação com base no horário atual (UTC).

    Horário de Brasília (BRT) = UTC-3 (Brasil não adota horário de verão desde 2019).

    Schedules:
      nova-semana : Segunda, 12:00-12:59 UTC (09:00-09:59 BRT)
      close       : Seg-Sex, 21:30-22:00 UTC (18:30-19:00 BRT)
      intraday    : Seg-Sex, 13:00-21:29 UTC (10:00-18:29 BRT)
    """
    weekday = now_utc.weekday()   # 0=seg, 4=sex
    hour    = now_utc.hour
    minute  = now_utc.minute

    is_weekday = 0 <= weekday <= 4

    if weekday == 0 and hour == 12:
        return "nova-semana"
    if is_weekday and hour == 21 and minute >= 30:
        return "close"
    if is_weekday and (13 <= hour <= 21):
        return "intraday"

    return "intraday"   # fallback seguro (atualiza preços sem aplicar stop)


# ---------------------------------------------------------------------------
# Refresh de preços do parquet (necessário para nova-semana scoring)
# ---------------------------------------------------------------------------

def _refresh_precos_parquet(universo: list[dict]) -> pd.DataFrame:
    """
    Garante que precos_v2.parquet esteja atualizado para os tickers do universo.
    Baixa apenas os últimos 10 dias para cada ticker (incremental rápido).
    Reutiliza preços já existentes no parquet.
    """
    import yfinance as yf
    from src.backtest_v2 import _garantir_precos_v2

    log.info("Atualizando precos_v2.parquet antes da formação da semana...")
    df = _garantir_precos_v2(universo)
    return df


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="V3c Live Portfolio Runner")
    parser.add_argument(
        "--mode",
        choices=["nova-semana", "close", "intraday", "auto"],
        default="auto",
        help="Modo de operação (padrão: auto-detectado por horário UTC)",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Data para processar fechamento (YYYY-MM-DD). Só para --mode close.",
    )
    args = parser.parse_args()

    hoje = date.today()
    now_utc = datetime.utcnow()

    # Determinar modo
    if args.mode == "auto":
        modo = detectar_modo(now_utc)
        log.info(f"Modo auto-detectado: '{modo}' (UTC {now_utc.strftime('%H:%M')})")
    else:
        modo = args.mode
        log.info(f"Modo manual: '{modo}'")

    # -----------------------------------------------------------------------
    # Carregar dados comuns
    # -----------------------------------------------------------------------
    if not config.UNIVERSO_V2_PATH.exists():
        log.error("universo_v2.json não encontrado. Rode build_universe_v2 primeiro.")
        sys.exit(1)
    with open(config.UNIVERSO_V2_PATH, encoding="utf-8") as f:
        universo_json = json.load(f)
    universo = universo_json["tickers"]

    # Benchmarks (para enriquecer performance_diaria com ibov/smll/cdi)
    bench_df: pd.DataFrame | None = None
    try:
        from src import benchmarks as bm
        bench_df = bm.ler_benchmarks()
    except Exception as e:
        log.warning(f"Benchmarks indisponíveis: {e}")

    # -----------------------------------------------------------------------
    # MODO: nova-semana
    # -----------------------------------------------------------------------
    if modo == "nova-semana":
        log.info("=== V3c: NOVA SEMANA ===")

        # Atualizar preços antes de calcular scores
        try:
            df_precos = _refresh_precos_parquet(universo)
        except Exception as e:
            log.warning(f"Refresh de preços falhou, usando parquet existente: {e}")
            df_precos = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")

        df_precos["date"] = pd.to_datetime(df_precos["date"])

        # Verificar frescor do parquet (deve ter dados até pelo menos D-5)
        ultima_data_parquet = df_precos["date"].max().date()
        dias_atraso = (hoje - ultima_data_parquet).days
        if dias_atraso > 7:
            log.warning(
                f"Parquet está {dias_atraso} dias desatualizado ({ultima_data_parquet}). "
                "Scores podem estar desatualizados."
            )

        estado = nova_semana(df_precos, universo, hoje)

        # Gerar e salvar carteira para o frontend (sem performance ainda)
        carteira = gerar_carteira_json(estado, bench_df)
        semana_iso = estado["semana"]
        salvar_carteira_historico(carteira, semana_iso)
        log.info(f"Semana {semana_iso} iniciada. Tickers: "
                 f"{[p['ticker'] for p in estado['posicoes']]}")

    # -----------------------------------------------------------------------
    # MODO: close
    # -----------------------------------------------------------------------
    elif modo == "close":
        log.info("=== V3c: FECHAMENTO DO DIA ===")

        data_close = date.fromisoformat(args.data) if args.data else hoje

        estado = carregar_estado()
        if estado is None or estado_expirado(estado, data_close):
            log.error("Estado V3c não encontrado ou expirado. Rode --mode nova-semana.")
            sys.exit(1)

        estado = processar_fechamento(estado, data_close)

        # Atualizar benchmarks (baixa dados frescos)
        try:
            from src import benchmarks as bm
            from datetime import timedelta
            bench_df = bm.carregar_benchmarks(
                date.fromisoformat(estado["data_corte_dados"]) - timedelta(days=5),
                data_close,
            )
            if not bench_df.empty:
                bm.salvar_benchmarks(bench_df)
        except Exception as e:
            log.warning(f"Falha ao atualizar benchmarks: {e}")

        carteira = gerar_carteira_json(estado, bench_df)
        salvar_carteira_historico(carteira, estado["semana"])
        log.info("Fechamento processado e carteira atualizada no frontend.")

    # -----------------------------------------------------------------------
    # MODO: intraday
    # -----------------------------------------------------------------------
    elif modo == "intraday":
        log.info("=== V3c: ATUALIZAÇÃO INTRADAY ===")

        estado = carregar_estado()
        if estado is None or estado_expirado(estado, hoje):
            # Se for segunda-feira sem estado: forma nova semana automaticamente
            if hoje.weekday() == 0 and (estado is None or estado_expirado(estado, hoje)):
                log.info("Segunda-feira sem estado V3c. Formando nova semana...")
                if not config.PRECOS_V2_PARQUET_PATH.exists():
                    log.error("precos_v2.parquet não encontrado.")
                    sys.exit(1)
                df_precos = pd.read_parquet(config.PRECOS_V2_PARQUET_PATH, engine="pyarrow")
                df_precos["date"] = pd.to_datetime(df_precos["date"])
                estado = nova_semana(df_precos, universo, hoje)
            else:
                log.error("Estado V3c não encontrado ou expirado. Rode --mode nova-semana.")
                sys.exit(1)

        estado = atualizar_intraday(estado)

        carteira = gerar_carteira_json(estado, bench_df)
        salvar_carteira_historico(carteira, estado["semana"])
        log.info("Frontend atualizado com preços intraday.")

    log.info("run_v3c.py concluído.")


if __name__ == "__main__":
    main()
