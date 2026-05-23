"""
Diagnostico de Performance da Formula V1 — v3.0.

Modulos ativos: 1 (macro), 3 (IC + rolling + correlacao), 5 (concentracao), 6 (variantes).
Output: data/diagnostic_report.json + data/diagnostic_report.md

DIAGNOSTIC_SPEC §9.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Garante que o root do projeto está no sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import config
from src.benchmarks import ler_benchmarks
from src.logger import get_logger
from src.diagnostic_modules.macro import (
    calcular_retornos_por_periodo,
    diagnostico_vs_smll,
)
from src.diagnostic_modules.ic import (
    calcular_ic_por_fator,
    calcular_ic_rolling,
    calcular_correlacao_momentum_tendencia,
)
from src.diagnostic_modules.concentracao import analisar_contribuicao_por_acao
from src.diagnostic_modules.tendencia import (
    calcular_ic_variantes,
    identificar_vencedora,
)
from src.diagnostic_modules.relatorio import gerar_markdown, gerar_hipoteses_v2

log = get_logger()

VARIANTES_TEND = ["T0", "T1", "T2", "T3"]
VARIANTES_MOM  = ["M0", "M1", "M2", "M3"]


def main() -> None:
    log.info("=" * 60)
    log.info("Diagnostico de Performance V1 — DIAGNOSTIC_SPEC v3.0")
    log.info("=" * 60)

    # ------------------------------------------------------------------
    # Carregar artefatos
    # ------------------------------------------------------------------
    log.info("Carregando artefatos...")

    if not config.BACKTEST_RESULTADO_PATH.exists():
        log.error("backtest_resultado.json nao encontrado. Execute a Fase 4 primeiro.")
        sys.exit(1)
    if not config.BACKTEST_CARTEIRAS_PATH.exists():
        log.error("backtest_carteiras.json nao encontrado. Execute a Fase 4 primeiro.")
        sys.exit(1)
    if not config.PRECOS_PARQUET_PATH.exists():
        log.error("precos.parquet nao encontrado. Execute a Fase 2 primeiro.")
        sys.exit(1)
    if not config.UNIVERSO_ATUAL_PATH.exists():
        log.error("universo_atual.json nao encontrado. Execute a Fase 1 primeiro.")
        sys.exit(1)

    with open(config.BACKTEST_RESULTADO_PATH, encoding="utf-8") as f:
        backtest_resultado = json.load(f)
    with open(config.BACKTEST_CARTEIRAS_PATH, encoding="utf-8") as f:
        backtest_carteiras = json.load(f)
    with open(config.UNIVERSO_ATUAL_PATH, encoding="utf-8") as f:
        universo_json = json.load(f)
    universo: list[dict] = universo_json["tickers"]

    df_precos = pd.read_parquet(config.PRECOS_PARQUET_PATH, engine="pyarrow")
    df_precos["date"] = pd.to_datetime(df_precos["date"])

    bench_df = ler_benchmarks()
    if bench_df is None:
        log.error("benchmarks.parquet nao encontrado. Execute a Fase 4 primeiro.")
        sys.exit(1)

    n_semanas = len(backtest_carteiras["carteiras"])
    log.info(f"Artefatos carregados: {n_semanas} semanas de backtest, {len(universo)} tickers")

    # ------------------------------------------------------------------
    # Módulo 1 — Diagnóstico macro
    # ------------------------------------------------------------------
    log.info("Modulo 1: Diagnostico macro...")
    m1_subperiodo = calcular_retornos_por_periodo(backtest_resultado["equity_curve"])
    m1_hitrate   = diagnostico_vs_smll(backtest_carteiras, bench_df)
    m1 = {
        "retorno_por_subperiodo":        m1_subperiodo,
        "hit_rate_vs_smll_por_semestre": m1_hitrate,
    }
    log.info(f"  Subperiodos calculados: {list(m1_subperiodo.keys())}")

    # ------------------------------------------------------------------
    # Módulo 3 — IC, rolling, correlação
    # ------------------------------------------------------------------
    log.info("Modulo 3: IC por fator (recomputa scores de 104 semanas, ~2 min)...")
    m3_ic = calcular_ic_por_fator(backtest_carteiras, df_precos, universo, bench_df)

    for fator, dados in m3_ic.items():
        log.info(
            f"  {fator:<14} IC={dados['ic_medio']:+.4f} "
            f"pct_pos={dados['ic_positivo_pct']:.1%} "
            f"IR={dados['ir']:+.3f} "
            f"({dados['n_semanas']}s)"
        )

    log.info("Modulo 3: IC rolling 26 semanas...")
    m3_rolling = calcular_ic_rolling(m3_ic)
    for fator, dados in m3_rolling.items():
        log.info(f"  {fator:<14} tendencia={dados['tendencia_recente']}")

    log.info("Modulo 3: Correlacao momentum x tendencia...")
    m3_correlacao = calcular_correlacao_momentum_tendencia(
        backtest_carteiras, df_precos, universo
    )
    log.info(
        f"  correlacao_media={m3_correlacao['correlacao_media']:.3f} — "
        f"{m3_correlacao['interpretacao']}"
    )

    # ------------------------------------------------------------------
    # Módulo 5 — Concentração por ação
    # ------------------------------------------------------------------
    log.info("Modulo 5: Concentracao por acao...")
    m5 = analisar_contribuicao_por_acao(backtest_carteiras)
    log.info(f"  {len(m5)} acoes analisadas")
    log.info("  Top 3 destruidores:")
    for a in m5[:3]:
        log.info(
            f"    {a['ticker']}: contrib={a['contribuicao_total']:+.4f} "
            f"aparicoes={a['aparicoes']} win={a['win_rate']:.1%}"
        )

    # ------------------------------------------------------------------
    # Módulo 6 — Variantes de tendência e momentum
    # ------------------------------------------------------------------
    log.info(f"Modulo 6: Variantes {VARIANTES_TEND} x {VARIANTES_MOM} (~3-5 min)...")
    ic_tend, ic_mom = calcular_ic_variantes(
        backtest_carteiras, df_precos, universo, bench_df,
        VARIANTES_TEND, VARIANTES_MOM,
    )

    log.info("  Tendencia:")
    for v, d in ic_tend.items():
        log.info(f"    {v}: IC={d['ic_medio']:+.4f} IR={d['ir']:+.3f} ({d['n_semanas']}s)")

    log.info("  Momentum:")
    for v, d in ic_mom.items():
        log.info(f"    {v}: IC={d['ic_medio']:+.4f} IR={d['ir']:+.3f} ({d['n_semanas']}s)")

    m6_tend_vencedora = identificar_vencedora(ic_tend, baseline_key="T1")
    m6_mom_vencedora  = identificar_vencedora(ic_mom,  baseline_key="M3")
    log.info(f"  Tendencia vencedora: {m6_tend_vencedora['variante_vencedora']} — {m6_tend_vencedora['motivo']}")
    log.info(f"  Momentum vencedora:  {m6_mom_vencedora['variante_vencedora']} — {m6_mom_vencedora['motivo']}")

    # ------------------------------------------------------------------
    # Hipóteses V2
    # ------------------------------------------------------------------
    hipoteses = gerar_hipoteses_v2(
        m3_ic, m3_correlacao, m3_rolling,
        m5, m6_tend_vencedora, m6_mom_vencedora,
    )

    # ------------------------------------------------------------------
    # Montar relatório
    # ------------------------------------------------------------------
    relatorio = {
        "metadata": {
            "data_geracao":         str(pd.Timestamp.today().date()),
            "n_semanas_analisadas": n_semanas,
            "periodo": (
                f"{backtest_resultado['metadata']['janela_inicio']}"
                f" a {backtest_resultado['metadata']['janela_fim']}"
            ),
            "versao_spec": "3.0",
        },
        "modulo_1_macro": m1,
        "modulo_3_ic": {
            "por_fator":           m3_ic,
            "rolling_26s":         m3_rolling,
            "correlacao_mom_tend": m3_correlacao,
        },
        "modulo_5_concentracao": m5,
        "modulo_6_variantes": {
            "tendencia":     ic_tend,
            "momentum":      ic_mom,
            "tend_vencedora": m6_tend_vencedora,
            "mom_vencedora":  m6_mom_vencedora,
        },
        "hipoteses_v2": hipoteses,
    }

    # ------------------------------------------------------------------
    # Salvar
    # ------------------------------------------------------------------
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    report_json = config.DATA_DIR / "diagnostic_report.json"
    report_md   = config.DATA_DIR / "diagnostic_report.md"

    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False, default=str)

    with open(report_md, "w", encoding="utf-8") as f:
        f.write(gerar_markdown(relatorio))

    log.info("=" * 60)
    log.info("Diagnostico concluido.")
    log.info(f"  -> {report_json}")
    log.info(f"  -> {report_md}")

    log.info(f"\n=== HIPOTESES PARA V2 ({len(hipoteses)} encontradas) ===")
    for i, h in enumerate(hipoteses, 1):
        log.info(f"\n{i}. [{h['origem']}] {h['hipotese']}")
        log.info(f"   Evidencia: {h['evidencia']}")
        log.info(f"   Acao: {h['acao_sugerida']}")


if __name__ == "__main__":
    main()
