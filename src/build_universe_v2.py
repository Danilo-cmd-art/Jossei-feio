"""
Fase 1 V2 — Universo Operacional expandido.

Diferenças vs V1:
  - MCAP_MAX = R$15B (V1 era R$5B)
  - Inclui campo "roe" no JSON de saída
  - Salva em universo_v2.json (não sobrescreve universo_atual.json)

Reutiliza toda a lógica de validação de build_universe.py.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.build_universe import (
    carregar_csv,
    _baixar_historico,
    _validar_qualidade,
    _aplicar_filtros_exclusao,
    _carregar_blacklist,
    _parse_br_float,
    gerar_validation_report,
)
from src.logger import get_logger

log = get_logger()


def _prefixo_empresa(ticker: str) -> str:
    """
    Extrai o prefixo da empresa removendo os dígitos finais.
    Ex: BRSR3 → 'BRSR', BRKM5 → 'BRKM', IGTI11 → 'IGTI'
    Usado para deduplicar múltiplas classes de ações do mesmo emissor.
    """
    return re.sub(r"\d+$", "", ticker.strip().upper())


def _deduplicate_by_company(aprovados: list[dict]) -> list[dict]:
    """
    Remove classes de ações duplicadas do mesmo emissor.
    Mantém apenas o ticker mais líquido por empresa (lista já ordenada por liquidez).
    Ex: se BRSR3 e BRSR6 foram aprovados, exclui BRSR6 e mantém BRSR3.
    """
    seen: dict[str, str] = {}  # prefixo → ticker mantido
    result: list[dict] = []
    excluidos_dedup: list[str] = []

    for t in aprovados:
        prefix = _prefixo_empresa(t["ticker_b3"])
        if prefix not in seen:
            seen[prefix] = t["ticker_b3"]
            result.append(t)
        else:
            excluidos_dedup.append(t["ticker_b3"])
            log.info(
                f"  Dedup empresa: {t['ticker_b3']} removido "
                f"(duplicata de {seen[prefix]} — emissor '{prefix}')"
            )

    if excluidos_dedup:
        log.info(
            f"Deduplicação por empresa: {len(aprovados)} → {len(result)} tickers "
            f"({len(excluidos_dedup)} removidos: {excluidos_dedup})"
        )
    return result


def filtrar_candidatos_v2(df: pd.DataFrame) -> pd.DataFrame:
    """Saneamento + filtro R$500M–15B + liquidez mínima + ranking por liquidez."""
    df = df.dropna(subset=["VALOR DE MERCADO", "LIQUIDEZ MEDIA DIARIA"])
    df = df[df["VALOR DE MERCADO"] > 0]
    df = df[df["LIQUIDEZ MEDIA DIARIA"] > 0]
    df = df[
        (df["VALOR DE MERCADO"] >= config.MCAP_MIN) &
        (df["VALOR DE MERCADO"] <= config.MCAP_MAX_V2)
    ]

    # Filtro de liquidez mínima — exclui tickers ilíquidos onde execução real
    # seria inviável e yfinance frequentemente falha em retornar preço intraday.
    antes_liq = len(df)
    df = df[df["LIQUIDEZ MEDIA DIARIA"] >= config.LIQUIDEZ_MINIMA_DIARIA]
    removidos_por_liquidez = antes_liq - len(df)
    if removidos_por_liquidez > 0:
        log.info(
            f"Filtro liquidez ≥ R$ {config.LIQUIDEZ_MINIMA_DIARIA:,.0f}/dia: "
            f"{removidos_por_liquidez} tickers removidos"
        )

    df = df.sort_values("LIQUIDEZ MEDIA DIARIA", ascending=False).reset_index(drop=True)
    log.info(f"Candidatos V2 após filtros: {len(df)}")
    return df


def construir_universo_v2(csv_path: Path) -> dict:
    """
    Executa pipeline completo para o universo V2.
    Output: universo_v2.json (inclui campo 'roe').
    """
    df_csv = carregar_csv(csv_path)
    candidatos = filtrar_candidatos_v2(df_csv)
    blacklist = _carregar_blacklist()

    aprovados: list[dict] = []
    excluidos: list[dict] = []

    log.info(f"Iniciando validação de {len(candidatos)} candidatos V2 no Yahoo Finance...")

    for idx, row in candidatos.iterrows():
        if len(aprovados) >= config.UNIVERSO_ALVO_V2:
            break

        ticker_b3 = str(row["TICKER"]).strip().upper()
        ticker_yf = f"{ticker_b3}.SA"
        rank_liq = int(idx) + 1

        if ticker_b3 in blacklist:
            log.info(f"  [{rank_liq}] {ticker_b3}: BLACKLIST_MANUAL")
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": "BLACKLIST_MANUAL",
                "detalhe": "Presente em blacklist.json",
            })
            continue

        log.info(f"  [{rank_liq}] {ticker_b3}: baixando histórico...")
        df_hist = _baixar_historico(ticker_yf)

        if df_hist is None or df_hist.empty:
            log.warning(f"  [{rank_liq}] {ticker_b3}: FAIL_NO_DATA")
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": "FAIL_NO_DATA",
                "detalhe": "yfinance retornou DataFrame vazio",
            })
            continue

        qualidade = _validar_qualidade(df_hist, ticker_b3)
        if qualidade["criterios_atendidos"] < config.CRITERIOS_APROVACAO_MINIMO:
            motivo = "FAIL_QUALIDADE_" + "_".join(
                k.upper() for k, v in qualidade.items()
                if k != "criterios_atendidos" and v is False
            )
            log.warning(f"  [{rank_liq}] {ticker_b3}: {motivo} ({qualidade['criterios_atendidos']}/5)")
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": motivo,
                "detalhe": f"{qualidade['criterios_atendidos']}/5 critérios de qualidade",
            })
            continue

        excluir, motivo_filtro = _aplicar_filtros_exclusao(df_hist, ticker_b3)
        if excluir:
            log.warning(f"  [{rank_liq}] {ticker_b3}: EXCLUIDO — {motivo_filtro}")
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": "FAIL_FILTRO_AUTO",
                "detalhe": motivo_filtro,
            })
            continue

        # Aprovado — inclui ROE além dos campos V1
        roic = _parse_br_float(row.get("ROIC"))
        roe  = _parse_br_float(row.get("ROE"))
        cagr = _parse_br_float(row.get("CAGR RECEITAS 5 ANOS"))

        aprovados.append({
            "rank_liquidez": len(aprovados) + 1,
            "ticker_b3": ticker_b3,
            "ticker_yf": ticker_yf,
            "mcap": row.get("VALOR DE MERCADO"),
            "liquidez_diaria": row.get("LIQUIDEZ MEDIA DIARIA"),
            "roic": roic,
            "roe": roe,
            "cagr_receita_5a": cagr,
            "qualidade_dados": qualidade,
        })
        log.info(f"  [{rank_liq}] {ticker_b3}: APROVADO (#{len(aprovados)}/{config.UNIVERSO_ALVO_V2})")

    # Remove múltiplas classes do mesmo emissor — mantém o mais líquido por empresa
    aprovados = _deduplicate_by_company(aprovados)

    # Reordena ranks após deduplicação
    for i, t in enumerate(aprovados):
        t["rank_liquidez"] = i + 1

    n = len(aprovados)
    if n < config.UNIVERSO_MINIMO:
        raise RuntimeError(
            f"Universo V2 insuficiente: apenas {n} tickers válidos "
            f"(mínimo: {config.UNIVERSO_MINIMO}). Revisão manual necessária."
        )
    if n < 50:
        log.warning(f"Universo V2 com poucos tickers: apenas {n} aprovados")

    universo = {
        "metadata": {
            "data_geracao": date.today().isoformat(),
            "vigencia_ate": (
                (date.today().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
            ),
            "fonte_csv": str(csv_path.name),
            "versao": "v2",
            "mcap_min": config.MCAP_MIN,
            "mcap_max": config.MCAP_MAX_V2,
            "total_candidatos_brutos": len(df_csv),
            "total_apos_filtros": len(candidatos),
            "total_aprovados": n,
            "total_excluidos": len(excluidos),
        },
        "tickers": aprovados,
        "excluidos": excluidos,
    }
    return universo


def salvar_universo_v2(universo: dict) -> None:
    """Salva universo_v2.json. Não sobrescreve universo_atual.json."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    with open(config.UNIVERSO_V2_PATH, "w", encoding="utf-8") as f:
        json.dump(universo, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"Salvo: {config.UNIVERSO_V2_PATH}")

    ano_mes = date.today().strftime("%Y-%m")
    hist_path = config.HISTORICO_DIR / f"universo_v2_{ano_mes}.json"
    shutil.copy(config.UNIVERSO_V2_PATH, hist_path)
    log.info(f"Histórico V2: {hist_path}")


def run(csv_path: Path | None = None) -> dict:
    """Executa pipeline V2 completo."""
    if csv_path is None:
        csv_path = config.STATUS_INVEST_CSV_DEFAULT

    log.info("=== BUILD UNIVERSO V2 (R$500M-15B) ===")
    universo = construir_universo_v2(csv_path)
    salvar_universo_v2(universo)
    gerar_validation_report(universo)

    n = universo["metadata"]["total_aprovados"]
    tickers = [t["ticker_b3"] for t in universo["tickers"]]
    log.info(f"=== UNIVERSO V2 CONCLUIDO: {n} tickers aprovados ===")
    log.info(f"Tickers: {tickers}")
    return universo


if __name__ == "__main__":
    import sys
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run(csv)
