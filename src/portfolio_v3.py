"""
portfolio_v3.py — Simulação semanal com STOP LOSS intraweek.

Regras de negócio (STOPLOSS_V3_SPEC §3-4):
  • Stop loss FIXO de -5% vs preço de entrada (adj_close da sexta anterior)
  • Verificado no FECHAMENTO de cada dia (adj_close)
  • Posição stopada → vira CAIXA (retorno 0%) pelo resto da semana
  • SEM redistribuição — pesos das demais não mudam
  • Garantia anti-look-ahead: obter_adj_close_anterior usa date < data (estrito)

Este módulo NÃO altera nenhum arquivo da V2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


# ---------------------------------------------------------------------------
# Estado da posição (STOPLOSS_V3_SPEC §4.1)
# ---------------------------------------------------------------------------

@dataclass
class Posicao:
    ticker:        str
    preco_entrada: float
    peso:          float                  # peso original (20% se 5 posições)
    ativo:         bool             = True
    preco_stop:    float | None     = None
    data_stop:     str   | None     = None
    ret_no_stop:   float | None     = None


# ---------------------------------------------------------------------------
# Funções auxiliares (STOPLOSS_V3_SPEC §4.3)
# ---------------------------------------------------------------------------

def obter_adj_close(
    ticker: str,
    data,
    df_precos: pd.DataFrame,
) -> float | None:
    """
    Retorna adj_close de um ticker numa data EXATA (fechamento do dia).
    None se não disponível (feriado, ticker sem dado, etc).
    """
    df_t = df_precos[
        (df_precos["ticker"] == ticker) &
        (df_precos["date"]   == pd.Timestamp(data))
    ]
    return float(df_t["adj_close"].iloc[0]) if not df_t.empty else None


def obter_adj_close_anterior(
    ticker: str,
    data,
    df_precos: pd.DataFrame,
) -> float | None:
    """
    Retorna adj_close do pregão IMEDIATAMENTE ANTERIOR a `data`.
    Garantia anti-look-ahead: usa date < data (estrito, jamais <=).
    """
    df_t = df_precos[
        (df_precos["ticker"] == ticker) &
        (df_precos["date"]   <  pd.Timestamp(data))
    ].sort_values("date")
    return float(df_t["adj_close"].iloc[-1]) if not df_t.empty else None


def obter_pregoes_entre(
    data_inicio,
    data_fim,
    df_precos: pd.DataFrame,
) -> list:
    """
    Retorna lista de pregões reais da B3 entre data_inicio e data_fim (inclusive).
    Usa df_precos como calendário (qualquer ticker com pregão naquela data conta).
    """
    datas = df_precos[
        (df_precos["date"] >= pd.Timestamp(data_inicio)) &
        (df_precos["date"] <= pd.Timestamp(data_fim))
    ]["date"].drop_duplicates().sort_values().tolist()
    return datas


# ---------------------------------------------------------------------------
# Loop semanal com stop loss (STOPLOSS_V3_SPEC §4.2)
# ---------------------------------------------------------------------------

STOP_LOSS_LIMITE = -0.05


def simular_semana_v3(
    tickers_entrada: list[str],
    preco_entrada:   dict[str, float],
    pregoes_semana:  list,
    df_precos:       pd.DataFrame,
) -> tuple[float, list[dict], dict[str, Posicao]]:
    """
    Simula uma semana com stop loss fixo de -5%.
    Capital de posição stopada vira caixa (retorno 0%) — sem redistribuição.

    Returns:
        retorno_semana   (float):     retorno acumulado da carteira na semana
        log_eventos      (list[dict]): eventos de stop disparados
        posicoes_finais  (dict):       estado final de cada posição (Posicao)
    """
    n_inicial = len(tickers_entrada)
    if n_inicial == 0:
        return 0.0, [], {}

    peso_unitario = 1 / n_inicial

    posicoes: dict[str, Posicao] = {
        ticker: Posicao(
            ticker        = ticker,
            preco_entrada = preco_entrada[ticker],
            peso          = peso_unitario,
            ativo         = True,
        )
        for ticker in tickers_entrada
    }

    log_eventos:   list[dict] = []
    valor_carteira             = 1.0  # base 1.0

    for data in pregoes_semana:
        retorno_dia_carteira = 0.0

        for ticker, pos in posicoes.items():

            if not pos.ativo:
                # Posição stopada → caixa → contribuição 0%
                continue

            preco_hoje = obter_adj_close(ticker, data, df_precos)
            if preco_hoje is None:
                # Stale data — contribuição 0% neste dia
                continue

            # Verificar stop ANTES de computar retorno do dia
            ret_acumulado = preco_hoje / pos.preco_entrada - 1

            if ret_acumulado <= STOP_LOSS_LIMITE:
                # ─── STOP ATINGIDO ────────────────────────────────────
                pos.ativo       = False
                pos.preco_stop  = preco_hoje
                pos.data_stop   = str(data)
                pos.ret_no_stop = ret_acumulado

                log_eventos.append({
                    "data":          str(data),
                    "evento":        "STOP_LOSS",
                    "ticker":        ticker,
                    "ret_acumulado": ret_acumulado,
                    "preco_entrada": pos.preco_entrada,
                    "preco_stop":    preco_hoje,
                    "peso":          pos.peso,
                })

                # Contribuição do dia do stop:
                # retorno desde ontem até o fechamento de hoje (que atingiu o stop)
                preco_ontem = obter_adj_close_anterior(ticker, data, df_precos)
                if preco_ontem is not None:
                    ret_dia = preco_hoje / preco_ontem - 1
                    retorno_dia_carteira += ret_dia * pos.peso

                # A partir de amanhã: peso desta posição contribui 0% (caixa)
                continue

            # ─── Posição ativa e SEM stop — retorno normal do dia ────
            preco_ontem = obter_adj_close_anterior(ticker, data, df_precos)
            if preco_ontem is None:
                continue
            ret_dia = preco_hoje / preco_ontem - 1
            retorno_dia_carteira += ret_dia * pos.peso

        valor_carteira *= (1 + retorno_dia_carteira)

    retorno_semana = valor_carteira - 1
    return retorno_semana, log_eventos, posicoes
