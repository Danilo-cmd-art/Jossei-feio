"""
Módulo 1 — Diagnóstico Macro.

Compara estratégia vs IBOV vs SMLL por subperíodo e semestre.
DIAGNOSTIC_SPEC §4.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.benchmarks import retorno_benchmark_periodo


def calcular_retornos_por_periodo(equity_curve: list[dict]) -> dict:
    """
    Divide equity_curve em 4 subperíodos iguais (Q1-Q4).
    Cada Q tem ~26 semanas (~6 meses).
    """
    n = len(equity_curve)
    if n < 4:
        return {}

    # Índices de divisão: Q1=[0..n//4), Q2=[n//4..n//2), ...
    cortes = [0, n // 4, n // 2, 3 * n // 4, n]
    nomes = [
        "Q1 (primeiros 6 meses)",
        "Q2 (6-12 meses)",
        "Q3 (12-18 meses)",
        "Q4 (ultimos 6 meses)",
    ]

    resultado: dict[str, dict] = {}
    for nome, i_ini, i_fim in zip(nomes, cortes, cortes[1:]):
        trecho = equity_curve[i_ini:i_fim]
        if len(trecho) < 2:
            continue

        # Ponto de referência do início do trecho é o valor do ponto anterior
        # (equity_curve[i_ini-1] se existir) para medir retorno intra-período
        ponto_inicio = equity_curve[i_ini - 1] if i_ini > 0 else trecho[0]
        ponto_fim = trecho[-1]

        def ret(key: str) -> float:
            v_ini = ponto_inicio[key]
            v_fim = ponto_fim[key]
            return (v_fim / v_ini - 1) if v_ini else 0.0

        re = ret("valor_estrategia")
        ri = ret("valor_ibov")
        rs = ret("valor_smll")

        resultado[nome] = {
            "periodo": f"{ponto_inicio['data']} -> {ponto_fim['data']}",
            "n_semanas": len(trecho),
            "estrategia": round(re, 6),
            "ibov": round(ri, 6),
            "smll": round(rs, 6),
            "alpha_vs_ibov": round(re - ri, 6),
            "alpha_vs_smll": round(re - rs, 6),
        }

    return resultado


def diagnostico_vs_smll(
    backtest_carteiras: dict,
    bench_df: pd.DataFrame,
) -> dict:
    """
    Hit rate vs SMLL por semestre (S1/S2 de cada ano).
    Computa retorno SMLL semanal a partir de benchmarks.parquet.
    """
    por_semestre: dict[str, dict] = {}

    for s in backtest_carteiras["carteiras"]:
        data_formacao = pd.Timestamp(s["data_formacao"])
        semestre = f"{data_formacao.year}-S{'1' if data_formacao.month <= 6 else '2'}"

        if semestre not in por_semestre:
            por_semestre[semestre] = {"ganhou": 0, "perdeu": 0, "empate": 0}

        # Retorno SMLL na semana
        inicio = date.fromisoformat(s["data_corte_dados"])
        fim = date.fromisoformat(s["data_vigencia_fim"])
        ret_smll = retorno_benchmark_periodo(bench_df, "smll", inicio, fim)

        ret_cart = s["retorno_carteira"]
        if ret_cart > ret_smll:
            por_semestre[semestre]["ganhou"] += 1
        elif ret_cart < ret_smll:
            por_semestre[semestre]["perdeu"] += 1
        else:
            por_semestre[semestre]["empate"] += 1

    for sem, dados in por_semestre.items():
        total = dados["ganhou"] + dados["perdeu"] + dados["empate"]
        dados["total"] = total
        dados["hit_rate"] = round(dados["ganhou"] / total, 4) if total else 0.0

    return dict(sorted(por_semestre.items()))
