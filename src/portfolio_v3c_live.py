"""
portfolio_v3c_live.py — Gerenciamento da carteira semanal V3c ao vivo.

DOIS MODOS DE OPERAÇÃO:
  intraday : atualiza preços atuais para exibição (SEM avaliar stop loss)
  close    : avalia stop loss com preços de fechamento, redistribui seletivamente

Regras da estratégia V3c:
  • Stop loss fixo de -5% acumulado vs. preco_entrada (adj_close da sexta anterior)
  • Redistribuição apenas para posições ATIVAS com ret_acumulado > 0 no fechamento
  • Cap: nenhuma posição ultrapassa 2× o peso original (excesso → caixa ocioso)
  • Se nenhuma posição positiva: peso liberado vira caixa ocioso (igual ao V3)

Estado persistido em:  data/carteira_v3c_estado.json
Output p/ frontend:    historico/carteira_YYYY-WWW.json  (mesmo formato V2 real)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src import benchmarks as bm
from src.portfolio import (
    obter_pregoes,
    ultimo_pregao_antes,
    ultimo_pregao_da_semana,
    formar_carteira,
)
from src.scoring_v2 import calcular_scores_v2
from src.logger import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

STOP_LOSS_LIMITE  = -0.05
CAP_MULTIPLICADOR = 2.0

V3C_ESTADO_PATH = config.DATA_DIR / "carteira_v3c_estado.json"


# ---------------------------------------------------------------------------
# Download de preços via yfinance
# ---------------------------------------------------------------------------

def _baixar_ultimo_preco(ticker_yf: str) -> float | None:
    """
    Retorna o preço mais recente disponível.
    Durante o pregão: último preço negociado (5-min candle).
    Fora do pregão: fechamento do último dia.
    """
    try:
        df = yf.download(
            ticker_yf, period="1d", interval="5m",
            auto_adjust=True, progress=False,
        )
        if df is not None and not df.empty:
            col = "Close" if "Close" in df.columns else df.columns[0]
            return float(df[col].dropna().iloc[-1])
        # Fallback: diário
        df = yf.download(ticker_yf, period="2d", interval="1d",
                         auto_adjust=True, progress=False)
        if df is not None and not df.empty:
            col = "Close" if "Close" in df.columns else df.columns[0]
            return float(df[col].dropna().iloc[-1])
    except Exception as e:
        log.warning(f"{ticker_yf}: yfinance erro — {e}")
    return None


def _baixar_fechamento(ticker_yf: str, data: date) -> float | None:
    """
    Retorna adj_close oficial de fechamento para uma data específica.
    Usa janela de 3 dias para tolerância a feriados.
    """
    try:
        ini = (data - timedelta(days=3)).isoformat()
        fim = (data + timedelta(days=1)).isoformat()
        df = yf.download(
            ticker_yf, start=ini, end=fim,
            interval="1d", auto_adjust=True, progress=False,
        )
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index).normalize()
        ts = pd.Timestamp(data)
        col = "Close" if "Close" in df.columns else df.columns[0]
        if ts in df.index:
            return float(df.loc[ts, col])
        return float(df[col].dropna().iloc[-1])
    except Exception as e:
        log.warning(f"{ticker_yf} ({data}): yfinance erro — {e}")
    return None


# ---------------------------------------------------------------------------
# Estado V3c — persistência
# ---------------------------------------------------------------------------

def carregar_estado() -> dict | None:
    """Carrega estado V3c da semana corrente. Retorna None se inexistente."""
    if not V3C_ESTADO_PATH.exists():
        return None
    with open(V3C_ESTADO_PATH, encoding="utf-8") as f:
        return json.load(f)


def salvar_estado(estado: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(V3C_ESTADO_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"Estado V3c salvo: {V3C_ESTADO_PATH}")


def estado_expirado(estado: dict | None, hoje: date) -> bool:
    """True se não há estado ou se é de uma semana anterior."""
    if estado is None:
        return True
    try:
        data_fim = date.fromisoformat(estado["data_vigencia_fim"])
        return hoje > data_fim
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Formação de nova semana V3c
# ---------------------------------------------------------------------------

def nova_semana(
    df_precos: pd.DataFrame,
    universo: list[dict],
    hoje: date,
) -> dict:
    """
    Forma nova carteira semanal (Segunda-feira):
      1. Scoring V2 com data_corte = último pregão antes de hoje
      2. Seleciona Top-N passando filtros F1+F2
      3. Inicializa estado V3c com pesos iguais

    Retorna o estado inicial salvo.
    """
    pregoes = obter_pregoes(df_precos)
    data_corte = ultimo_pregao_antes(hoje, pregoes)
    if data_corte is None:
        raise RuntimeError(f"Sem pregão antes de {hoje}")

    data_vigencia_fim = ultimo_pregao_da_semana(hoje, pregoes) or hoje
    semana_iso = hoje.strftime("%Y-W%V")

    log.info(f"Nova semana V3c: {semana_iso}  corte={data_corte}  fim={data_vigencia_fim}")

    scores = calcular_scores_v2(df_precos, universo, data_corte)
    selecionados = formar_carteira(scores, data_corte, df_precos)

    if not selecionados:
        raise RuntimeError("V3c: carteira vazia — nenhum ticker passou F1+F2")

    n             = len(selecionados)
    peso_unitario = 1.0 / n
    peso_maximo   = CAP_MULTIPLICADOR * peso_unitario
    scores_map    = {s["ticker"]: s for s in scores}

    posicoes = []
    for t in selecionados:
        ticker = t["ticker"]
        s = scores_map.get(ticker, {})
        posicoes.append({
            "ticker":          ticker,
            "ticker_yf":       ticker + ".SA",
            "rank_formacao":   s.get("rank", 0),
            "score_formacao":  round(float(s.get("score_final", 0)), 4),
            "preco_entrada":   t.get("preco_entrada"),
            # preco_ref_dia = preço usado como referência do início do dia atual
            # Inicializado com preco_entrada; atualizado ao fim de cada pregão (close)
            "preco_ref_dia":   t.get("preco_entrada"),
            "peso_atual":      peso_unitario,
            "ativo":           True,
            "preco_atual":     t.get("preco_entrada"),
            "ret_acumulado":   0.0,
            "preco_stop":      None,
            "data_stop":       None,
            "ret_no_stop":     None,
        })

    estado = {
        "versao":               "v3c",
        "semana":               semana_iso,
        "data_formacao":        hoje.isoformat(),
        "data_corte_dados":     data_corte.isoformat(),
        "data_vigencia_inicio": hoje.isoformat(),
        "data_vigencia_fim":    data_vigencia_fim.isoformat(),
        "n_posicoes_inicial":   n,
        "peso_unitario":        peso_unitario,
        "peso_maximo":          peso_maximo,
        "posicoes":             posicoes,
        "stops_semana":         [],
        "dias_processados":     [],
        "performance_diaria":   [],
        "ultima_atualizacao":   datetime.now().isoformat(timespec="seconds"),
        "modo_ultima_atualizacao": "nova_semana",
    }

    salvar_estado(estado)
    log.info(f"Estado V3c inicializado: {[p['ticker'] for p in posicoes]}")
    return estado


# ---------------------------------------------------------------------------
# Redistribuição V3c (equivalente ao backtest)
# ---------------------------------------------------------------------------

def _redistribuir(
    peso_liberado: float,
    posicoes: list[dict],
    precos: dict[str, float],
    peso_maximo: float,
) -> float:
    """
    Redistribui peso_liberado entre posições ativas com ret_acumulado > 0.
    Retorna o peso não redistribuído (caixa ocioso).
    """
    candidatas = [
        p for p in posicoes
        if p["ativo"]
        and p.get("preco_entrada")
        and precos.get(p["ticker"]) is not None
        and (precos[p["ticker"]] / p["preco_entrada"] - 1) > 0
    ]

    if not candidatas:
        return peso_liberado

    soma_pesos = sum(p["peso_atual"] for p in candidatas)
    if soma_pesos <= 0:
        return peso_liberado

    caixa = 0.0
    for p in candidatas:
        share  = p["peso_atual"] / soma_pesos
        adicao = peso_liberado * share
        espaco = peso_maximo - p["peso_atual"]
        if espaco <= 0:
            caixa += adicao
        elif adicao > espaco:
            p["peso_atual"] += espaco
            caixa += adicao - espaco
        else:
            p["peso_atual"] += adicao
    return caixa


# ---------------------------------------------------------------------------
# Processamento de fechamento (stop loss + redistribuição)
# ---------------------------------------------------------------------------

def processar_fechamento(estado: dict, data: date | None = None) -> dict:
    """
    Avalia stop loss com preços de fechamento oficial (adj_close).
    Aplica redistribuição V3c seletiva.
    Atualiza estado e anexa entrada à performance_diaria com modo='close'.

    Deve ser chamado UMA VEZ por dia, após ~18:30 BRT.
    Idempotente: se o dia já foi processado, retorna sem fazer nada.
    """
    if data is None:
        data = date.today()
    data_str = data.isoformat()

    if data_str in estado.get("dias_processados", []):
        log.info(f"Fechamento {data_str} já processado — ignorando.")
        return estado

    log.info(f"Processando fechamento V3c — {data_str}")

    posicoes    = estado["posicoes"]
    peso_maximo = estado["peso_maximo"]

    # 1. Baixar preços de fechamento para posições ativas
    precos_fechamento: dict[str, float] = {}
    for pos in posicoes:
        if not pos["ativo"]:
            continue
        p = _baixar_fechamento(pos["ticker_yf"], data)
        if p is not None:
            precos_fechamento[pos["ticker"]] = p

    if not precos_fechamento:
        log.warning(f"Sem preços de fechamento para {data_str} — feriado ou erro?")
        return estado

    # 2. Avaliar stop loss e calcular retorno do dia
    retorno_dia = 0.0

    for pos in posicoes:
        if not pos["ativo"]:
            continue
        ticker      = pos["ticker"]
        preco_hoje  = precos_fechamento.get(ticker)
        if preco_hoje is None:
            continue

        preco_entrada = pos["preco_entrada"] or preco_hoje
        ret_acumulado = preco_hoje / preco_entrada - 1

        # Retorno do dia vs. referência anterior (último close ou entrada)
        preco_ref = pos.get("preco_ref_dia") or preco_entrada
        ret_dia_pos = preco_hoje / preco_ref - 1 if preco_ref else 0.0

        if ret_acumulado <= STOP_LOSS_LIMITE:
            # ─── STOP ATINGIDO ─────────────────────────────────────────
            peso_antes = pos["peso_atual"]
            retorno_dia += ret_dia_pos * peso_antes   # contribuição final

            pos.update({
                "ativo":         False,
                "preco_atual":   preco_hoje,
                "ret_acumulado": round(ret_acumulado, 6),
                "preco_stop":    preco_hoje,
                "data_stop":     data_str,
                "ret_no_stop":   round(ret_acumulado, 6),
                "peso_atual":    0.0,
            })

            caixa = _redistribuir(peso_antes, posicoes, precos_fechamento, peso_maximo)

            evento = {
                "data":               data_str,
                "evento":             "STOP_LOSS",
                "ticker":             ticker,
                "ret_acumulado":      round(ret_acumulado, 6),
                "preco_entrada":      preco_entrada,
                "preco_stop":         preco_hoje,
                "peso_no_stop":       round(peso_antes, 6),
                "peso_redistribuido": round(peso_antes - caixa, 6),
                "peso_caixa":         round(caixa, 6),
            }
            estado["stops_semana"].append(evento)
            log.info(f"  STOP {ticker}: ret={ret_acumulado*100:.2f}%  "
                     f"redistrib={( peso_antes-caixa)*100:.1f}%  caixa={caixa*100:.1f}%")
        else:
            # Posição ativa sem stop
            retorno_dia += ret_dia_pos * pos["peso_atual"]
            pos.update({
                "preco_atual":   preco_hoje,
                "ret_acumulado": round(ret_acumulado, 6),
                "preco_ref_dia": preco_hoje,   # próximo dia usará este como referência
            })

    # 3. Retorno acumulado composto
    perf = [p for p in estado.get("performance_diaria", [])
            if not (p["data"] == data_str and p["modo"] == "intraday")]  # remove provisional
    ret_acum_anterior = perf[-1]["retorno_acumulado"] if perf else 0.0
    ret_acum_total    = (1 + ret_acum_anterior) * (1 + retorno_dia) - 1

    perf.append({
        "data":              data_str,
        "retorno_dia":       round(retorno_dia, 6),
        "retorno_acumulado": round(ret_acum_total, 6),
        "modo":              "close",
    })
    estado["performance_diaria"]  = perf
    estado["dias_processados"].append(data_str)
    estado["ultima_atualizacao"]  = datetime.now().isoformat(timespec="seconds")
    estado["modo_ultima_atualizacao"] = "close"

    salvar_estado(estado)
    log.info(f"Fechamento OK: ret_dia={retorno_dia*100:.3f}%  "
             f"acum_semana={ret_acum_total*100:.3f}%")
    return estado


# ---------------------------------------------------------------------------
# Atualização intraday (somente preços, SEM stop loss)
# ---------------------------------------------------------------------------

def atualizar_intraday(estado: dict) -> dict:
    """
    Baixa preços atuais e atualiza a entry provisória de hoje em performance_diaria.
    NÃO avalia stop loss — uso exclusivo durante o pregão.

    A entry intraday tem modo='intraday' e é substituída pelo close ao final do dia.
    """
    log.info("Atualização intraday V3c")
    posicoes     = estado["posicoes"]
    data_hoje    = date.today()
    data_hoje_str = data_hoje.isoformat()

    # Baixar preços atuais
    precos: dict[str, float] = {}
    for pos in posicoes:
        p = _baixar_ultimo_preco(pos["ticker_yf"])
        if p is not None:
            precos[pos["ticker"]] = p

    if not precos:
        log.warning("Sem preços disponíveis no momento — mercado fechado?")
        return estado

    # Atualizar ret_acumulado (vs preco_entrada) de cada posição
    for pos in posicoes:
        ticker = pos["ticker"]
        preco_agora = precos.get(ticker)
        if preco_agora is None:
            continue
        pos["preco_atual"] = preco_agora
        preco_entrada = pos["preco_entrada"] or preco_agora
        pos["ret_acumulado"] = round(preco_agora / preco_entrada - 1, 6)

    # Retorno intraday do dia: vs preco_ref_dia (último close processado, ou entrada)
    ret_dia_intraday = 0.0
    for pos in posicoes:
        if not pos["ativo"]:
            continue
        ticker = pos["ticker"]
        preco_agora = precos.get(ticker)
        if preco_agora is None:
            continue
        preco_ref = pos.get("preco_ref_dia") or pos.get("preco_entrada") or preco_agora
        ret_dia_intraday += (preco_agora / preco_ref - 1) * pos["peso_atual"]

    # Retorno acumulado composto (vs último close processado)
    perf_close = [p for p in estado.get("performance_diaria", []) if p["modo"] == "close"]
    ret_acum_base  = perf_close[-1]["retorno_acumulado"] if perf_close else 0.0
    ret_acum_total = (1 + ret_acum_base) * (1 + ret_dia_intraday) - 1

    # Substituir entry intraday de hoje
    perf = [p for p in estado.get("performance_diaria", [])
            if not (p["data"] == data_hoje_str and p["modo"] == "intraday")]
    perf.append({
        "data":              data_hoje_str,
        "retorno_dia":       round(ret_dia_intraday, 6),
        "retorno_acumulado": round(ret_acum_total, 6),
        "modo":              "intraday",
    })
    estado["performance_diaria"]     = sorted(perf, key=lambda x: x["data"])
    estado["ultima_atualizacao"]     = datetime.now().isoformat(timespec="seconds")
    estado["modo_ultima_atualizacao"] = "intraday"

    salvar_estado(estado)
    log.info(f"Intraday OK: ret_dia={ret_dia_intraday*100:.3f}%  "
             f"acum_semana={ret_acum_total*100:.3f}%")
    return estado


# ---------------------------------------------------------------------------
# Geração do arquivo para o frontend
# ---------------------------------------------------------------------------

def gerar_carteira_json(estado: dict, bench_df: pd.DataFrame | None = None) -> dict:
    """
    Converte o estado V3c para o formato historico/carteira_YYYY-WWW.json.
    Compatível com components/carteira.py e components/historico_carteira.py.
    """
    posicoes = estado["posicoes"]
    perf_raw = estado.get("performance_diaria", [])

    ret_total = perf_raw[-1]["retorno_acumulado"] if perf_raw else 0.0
    data_corte = date.fromisoformat(estado["data_corte_dados"])

    # Adicionar benchmarks à performance (se disponíveis)
    perf_com_bench = []
    for entry in perf_raw:
        bench_vals: dict = {}
        if bench_df is not None and not bench_df.empty:
            d = date.fromisoformat(entry["data"])
            bench_vals = {
                "ibov": bm.retorno_benchmark_periodo(bench_df, "ibov", data_corte, d),
                "smll": bm.retorno_benchmark_periodo(bench_df, "smll", data_corte, d),
                "cdi":  bm.retorno_benchmark_periodo(bench_df, "cdi",  data_corte, d),
            }
        perf_com_bench.append({**entry, "benchmarks": bench_vals})

    # Construir lista de tickers para o frontend
    tickers_frontend = []
    for pos in posicoes:
        tickers_frontend.append({
            "ticker":            pos["ticker"],
            "rank_na_formacao":  pos.get("rank_formacao", 0),
            "score_na_formacao": pos.get("score_formacao", 0.0),
            "preco_entrada":     pos.get("preco_entrada"),
            "preco_atual":       pos.get("preco_atual"),
            "retorno_acumulado": pos.get("ret_acumulado", 0.0),
            "is_stale":          not pos["ativo"],   # stopped = stale no display
            "peso":              round(pos["peso_atual"], 6),
            # Campos extras V3c (ignorados pelo frontend, úteis para auditoria)
            "v3c_ativo":     pos["ativo"],
            "v3c_data_stop": pos.get("data_stop"),
        })

    return {
        "metadata": {
            "data_formacao":        estado["data_formacao"],
            "data_corte_dados":     estado["data_corte_dados"],
            "data_vigencia_inicio": estado["data_vigencia_inicio"],
            "data_vigencia_fim":    estado["data_vigencia_fim"],
            "bootstrap_retroativo": False,
            "n_posicoes":           estado["n_posicoes_inicial"],
            "peso_por_posicao":     round(estado["peso_unitario"], 6),
            "versao_formula":       "v3c",
            "stop_loss_pct":        STOP_LOSS_LIMITE,
            "redistribuicao":       "positivas_cap_2x",
            "ultima_atualizacao":   estado.get("ultima_atualizacao"),
            "modo_atualizacao":     estado.get("modo_ultima_atualizacao"),
        },
        "tickers":                 tickers_frontend,
        "performance_diaria":      perf_com_bench,
        "retorno_acumulado_total": round(ret_total, 6),
        "stops_semana":            estado.get("stops_semana", []),
    }


def salvar_carteira_historico(carteira: dict, semana_iso: str) -> Path:
    """
    Salva carteira em historico/carteira_YYYY-WWW.json.
    Sobrescreve se já existir (idempotente).
    """
    config.HISTORICO_DIR.mkdir(parents=True, exist_ok=True)
    path = config.HISTORICO_DIR / f"carteira_{semana_iso}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(carteira, f, ensure_ascii=False, indent=2, default=str)
    log.info(f"Carteira histórico salva: {path}")
    return path
