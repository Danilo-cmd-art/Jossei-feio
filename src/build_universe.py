"""
Fase 1 — Universo Operacional.

Pipeline: CSV Status Invest → filtro mcap → ranking liquidez →
          validação Yahoo Finance → blacklist → universo_atual.json
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

# Adiciona raiz ao path para imports de config
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.logger import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# 1. Leitura e saneamento do CSV
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float | None:
    """Converte valor (str BR ou numérico) para float. Retorna None se inválido."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    # Formato BR: "1.234,56" → remove ponto de milhar, troca vírgula por ponto
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# Alias usado em pontos do código que ainda recebem strings BR cruas
_parse_br_float = _to_float


def carregar_csv(csv_path: Path) -> pd.DataFrame:
    """
    Lê CSV do Status Invest.
    Usa decimal=',' e thousands='.' para parsear números brasileiros nativamente,
    evitando o Arrow string backend do pandas 3.0.
    """
    log.info(f"Lendo CSV: {csv_path}")
    df = pd.read_csv(
        csv_path,
        sep=";",
        encoding="utf-8",
        decimal=",",
        thousands=".",
    )
    df.columns = [c.strip() for c in df.columns]

    # Garante que TICKER permanece string limpa
    df["TICKER"] = df["TICKER"].astype(str).str.strip()

    log.info(f"CSV carregado: {len(df)} linhas")
    return df


def filtrar_candidatos(df: pd.DataFrame) -> pd.DataFrame:
    """Saneamento bruto + filtro small cap + ranking por liquidez."""
    # Saneamento bruto
    df = df.dropna(subset=["VALOR DE MERCADO", "LIQUIDEZ MEDIA DIARIA"])
    df = df[df["VALOR DE MERCADO"] > 0]
    df = df[df["LIQUIDEZ MEDIA DIARIA"] > 0]

    # Filtro small cap
    df = df[
        (df["VALOR DE MERCADO"] >= config.MCAP_MIN) &
        (df["VALOR DE MERCADO"] <= config.MCAP_MAX)
    ]

    df = df.sort_values("LIQUIDEZ MEDIA DIARIA", ascending=False).reset_index(drop=True)
    log.info(f"Candidatos após filtros: {len(df)}")
    return df


# ---------------------------------------------------------------------------
# 2. Validação de qualidade no Yahoo Finance
# ---------------------------------------------------------------------------

def _baixar_historico(ticker_yf: str, anos: int = 3) -> pd.DataFrame | None:
    """Baixa histórico via yfinance. Retorna None em falha."""
    try:
        t = yf.Ticker(ticker_yf)
        df = t.history(period=f"{anos}y", auto_adjust=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        log.debug(f"{ticker_yf}: erro no download — {e}")
        return None


def _validar_qualidade(df: pd.DataFrame, ticker: str) -> dict:
    """Aplica critérios Q1-Q5. Retorna dict com resultado de cada critério."""
    today = date.today()
    resultados = {}

    # Q1 — histórico mínimo
    resultados["q1_historico"] = bool(len(df) >= config.Q1_HISTORICO_MINIMO)

    # Q2 — retornos absurdos
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    retornos = df[close_col].pct_change().abs()
    n_absurdos = int((retornos > 0.50).sum())
    resultados["q2_retornos_absurdos"] = bool(n_absurdos <= config.Q2_RETORNOS_ABSURDOS_MAX)

    # Q3 — volume zerado
    vol_zero_pct = float((df["Volume"] == 0).mean()) if "Volume" in df.columns else 0.0
    resultados["q3_volume_zerado"] = bool(vol_zero_pct < config.Q3_VOLUME_ZERO_MAX_PCT)

    # Q4 — integridade do Close
    nan_pct = float(df[close_col].isna().mean())
    resultados["q4_close_integro"] = bool(nan_pct < config.Q4_CLOSE_NAN_MAX_PCT)

    # Q5 — atividade recente
    ultima_data = df.index[-1]
    if hasattr(ultima_data, "date"):
        ultima_data = ultima_data.date()
    dias_atraso = (today - ultima_data).days
    resultados["q5_recente"] = bool(dias_atraso <= config.Q5_RECENTE_MAX_DIAS)

    resultados["criterios_atendidos"] = sum(
        1 for k, v in resultados.items() if k != "criterios_atendidos" and v is True
    )
    return resultados


def _aplicar_filtros_exclusao(df: pd.DataFrame, ticker: str) -> tuple[bool, str]:
    """
    Filtros F1-F5 (Fase 1 §5). Retorna (excluir, motivo).
    Qualquer flag acionada → excluir.
    """
    close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
    closes = df[close_col].dropna()

    if len(closes) < 60:
        return False, ""

    # F1 — drawdown 60d
    preco_atual = closes.iloc[-1]
    preco_max_60d = closes.tail(60).max()
    if preco_max_60d > 0:
        drawdown = preco_atual / preco_max_60d - 1
        if drawdown < config.F1_DRAWDOWN_LIMITE:
            return True, f"F1_DRAWDOWN: {drawdown:.1%}"

    # F2 — volatilidade absurda
    retornos = closes.pct_change().tail(60).dropna()
    if len(retornos) >= 20:
        vol = retornos.std() * math.sqrt(252)
        if vol > config.F2_VOL_ANUALIZADA_LIMITE:
            return True, f"F2_VOL_ALTA: {vol:.1%}"

    # F3 — volume colapsado
    if "Volume" in df.columns:
        vol_20d = df["Volume"].tail(20).mean()
        vol_252d = df["Volume"].tail(252).mean()
        if vol_252d > 0 and vol_20d < config.F3_VOLUME_COLAPSADO_RATIO * vol_252d:
            return True, f"F3_VOL_COLAPSADO: {vol_20d/vol_252d:.1%} do histórico"

    # F4 — preço travado
    ultimos_20 = closes.tail(20)
    media_20 = ultimos_20.mean()
    if media_20 > 0:
        variacao = (ultimos_20.max() - ultimos_20.min()) / media_20
        if variacao < config.F4_PRECO_TRAVADO_VARIACAO:
            return True, f"F4_PRECO_TRAVADO: variacao={variacao:.2%}"

    # F5 — gaps de pregão (comparação com referência PETR4)
    # Implementação simplificada: gap > 5 dias consecutivos no próprio índice
    datas = pd.Series(df.index)
    if len(datas) >= 2:
        datas_dt = pd.to_datetime(datas)
        gaps = datas_dt.diff().dt.days.dropna()
        max_gap = gaps.max()
        if max_gap > config.F5_GAPS_PREGAO_MAX:
            return True, f"F5_GAP_PREGAO: {int(max_gap)} dias consecutivos"

    return False, ""


# ---------------------------------------------------------------------------
# 3. Blacklist manual
# ---------------------------------------------------------------------------

def _carregar_blacklist() -> set[str]:
    """Lê blacklist.json e retorna conjunto de tickers bloqueados."""
    path = config.BLACKLIST_PATH
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tickers = {item["ticker"].upper() for item in data.get("blacklist", [])}

    # Aviso sobre entradas vencidas
    hoje = date.today().isoformat()
    for item in data.get("blacklist", []):
        if item.get("revisar_em", "9999-99-99") < hoje:
            log.warning(
                f"Blacklist: {item['ticker']} tem revisar_em={item['revisar_em']} no passado"
            )
    return tickers


# ---------------------------------------------------------------------------
# 4. Loop principal de validação
# ---------------------------------------------------------------------------

def construir_universo(csv_path: Path) -> dict:
    """
    Executa pipeline completo da Fase 1.
    Retorna dict compatível com schema de universo_atual.json.
    """
    df_csv = carregar_csv(csv_path)
    candidatos = filtrar_candidatos(df_csv)
    blacklist = _carregar_blacklist()

    aprovados: list[dict] = []
    excluidos: list[dict] = []
    tentativas_totais = 0

    log.info(f"Iniciando validação de {len(candidatos)} candidatos no Yahoo Finance...")

    for idx, row in candidatos.iterrows():
        if len(aprovados) >= config.UNIVERSO_ALVO:
            break

        ticker_b3 = str(row["TICKER"]).strip().upper()
        ticker_yf = f"{ticker_b3}.SA"
        rank_liq = int(idx) + 1
        tentativas_totais += 1

        # Blacklist
        if ticker_b3 in blacklist:
            log.info(f"  [{rank_liq}] {ticker_b3}: BLACKLIST_MANUAL")
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": "BLACKLIST_MANUAL",
                "detalhe": "Presente em blacklist.json",
            })
            continue

        # Download
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

        # Critérios de qualidade
        qualidade = _validar_qualidade(df_hist, ticker_b3)
        if qualidade["criterios_atendidos"] < config.CRITERIOS_APROVACAO_MINIMO:
            motivo = "FAIL_QUALIDADE_" + "_".join(
                k.upper() for k, v in qualidade.items()
                if k != "criterios_atendidos" and v is False
            )
            log.warning(
                f"  [{rank_liq}] {ticker_b3}: {motivo} "
                f"({qualidade['criterios_atendidos']}/5 critérios)"
            )
            excluidos.append({
                "ticker_b3": ticker_b3,
                "rank_liquidez_original": rank_liq,
                "motivo": motivo,
                "detalhe": f"{qualidade['criterios_atendidos']}/5 critérios de qualidade",
            })
            continue

        # Filtros de exclusão
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

        # Aprovado
        roic = _parse_br_float(row.get("ROIC"))
        cagr = _parse_br_float(row.get("CAGR RECEITAS 5 ANOS"))

        aprovados.append({
            "rank_liquidez": len(aprovados) + 1,
            "ticker_b3": ticker_b3,
            "ticker_yf": ticker_yf,
            "mcap": row.get("VALOR DE MERCADO"),
            "liquidez_diaria": row.get("LIQUIDEZ MEDIA DIARIA"),
            "roic": roic,
            "cagr_receita_5a": cagr,
            "qualidade_dados": qualidade,
        })
        log.info(
            f"  [{rank_liq}] {ticker_b3}: APROVADO "
            f"(#{len(aprovados)}/{config.UNIVERSO_ALVO})"
        )

    # Verificar mínimo
    n = len(aprovados)
    if n < config.UNIVERSO_MINIMO:
        raise RuntimeError(
            f"Universo insuficiente: apenas {n} tickers válidos "
            f"(mínimo: {config.UNIVERSO_MINIMO}). Revisão manual necessária."
        )
    if n < config.UNIVERSO_ALVO:
        log.warning(f"Universo menor que o alvo: {n}/{config.UNIVERSO_ALVO} tickers")

    ano_mes = date.today().strftime("%Y-%m")
    universo = {
        "metadata": {
            "data_geracao": date.today().isoformat(),
            "vigencia_ate": (date.today().replace(day=1) +
                             timedelta(days=32)).replace(day=1).isoformat(),
            "fonte_csv": str(csv_path.name),
            "total_candidatos_brutos": len(df_csv),
            "total_apos_filtros": len(candidatos),
            "total_aprovados": n,
            "total_excluidos": len(excluidos),
        },
        "tickers": aprovados,
        "excluidos": excluidos,
    }

    return universo


# ---------------------------------------------------------------------------
# 5. Persistência
# ---------------------------------------------------------------------------

def salvar_universo(universo: dict) -> None:
    """Salva universo_atual.json e cópia histórica."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)

    with open(config.UNIVERSO_ATUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(universo, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"Salvo: {config.UNIVERSO_ATUAL_PATH}")

    ano_mes = date.today().strftime("%Y-%m")
    hist_path = config.HISTORICO_DIR / f"universo_{ano_mes}.json"
    shutil.copy(config.UNIVERSO_ATUAL_PATH, hist_path)
    log.info(f"Histórico: {hist_path}")


def gerar_validation_report(universo: dict) -> None:
    """Salva validation_report.csv com resultado ticker-a-ticker."""
    rows = []
    for t in universo["tickers"]:
        q = t["qualidade_dados"]
        rows.append({
            "ticker": t["ticker_b3"],
            "status": "APROVADO",
            "rank_liquidez": t["rank_liquidez"],
            **{k: v for k, v in q.items()},
        })
    for e in universo["excluidos"]:
        rows.append({
            "ticker": e["ticker_b3"],
            "status": e["motivo"],
            "rank_liquidez": e["rank_liquidez_original"],
            "detalhe": e.get("detalhe", ""),
        })

    df = pd.DataFrame(rows)
    report_path = config.DATA_DIR / "validation_report.csv"
    df.to_csv(report_path, index=False)
    log.info(f"Validation report: {report_path}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run(csv_path: Path | None = None) -> dict:
    """Executa Fase 1 completa. Retorna universo gerado."""
    if csv_path is None:
        csv_path = config.STATUS_INVEST_CSV_DEFAULT

    log.info("=== FASE 1: Construção do universo ===")
    universo = construir_universo(csv_path)
    salvar_universo(universo)
    gerar_validation_report(universo)

    n = universo["metadata"]["total_aprovados"]
    log.info(f"=== FASE 1 CONCLUÍDA: {n} tickers aprovados ===")
    return universo


if __name__ == "__main__":
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    run(csv)
