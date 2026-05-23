"""
Módulo 5 — Concentração por Ação.

Identifica ações que apareceram repetidamente e destruíram ou geraram valor.
DIAGNOSTIC_SPEC §6.
"""
from __future__ import annotations

import numpy as np


def analisar_contribuicao_por_acao(backtest_carteiras: dict) -> list[dict]:
    """
    Por ação: nº de aparições, retorno médio, contribuição ponderada total e win rate.
    Retorna lista ordenada da pior para melhor contribuição.
    """
    contrib: dict[str, dict] = {}

    for semana in backtest_carteiras["carteiras"]:
        n = len(semana["tickers"])
        peso = 1.0 / n if n > 0 else 0.0

        for t in semana["tickers"]:
            ticker = t["ticker"]
            if ticker not in contrib:
                contrib[ticker] = {
                    "aparicoes": 0,
                    "retornos": [],
                    "contribuicoes": [],
                }
            contrib[ticker]["aparicoes"] += 1
            contrib[ticker]["retornos"].append(t["retorno_semana"])
            contrib[ticker]["contribuicoes"].append(t["retorno_semana"] * peso)

    resultado = []
    for ticker, dados in contrib.items():
        retornos = dados["retornos"]
        resultado.append({
            "ticker": ticker,
            "aparicoes": dados["aparicoes"],
            "retorno_medio": round(float(np.mean(retornos)), 6),
            "retorno_melhor": round(float(max(retornos)), 6),
            "retorno_pior": round(float(min(retornos)), 6),
            "contribuicao_total": round(sum(dados["contribuicoes"]), 6),
            "win_rate": round(
                sum(1 for r in retornos if r > 0) / len(retornos), 4
            ),
        })

    # Piores primeiro (menor contribuição total)
    return sorted(resultado, key=lambda x: x["contribuicao_total"])
