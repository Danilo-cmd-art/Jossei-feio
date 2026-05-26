"""Aba Live — performance real do sistema vivo (desde 18/05/2026).

Reusa o componente de gráfico cumulativo do Backtest (mesma lógica, mesma
identidade visual), apenas construindo o equity_curve a partir das semanas
REAIS gravadas em historico/carteira_*.json.

Fontes de dados (todas atualizadas automaticamente pelo workflow intraday):
  • historico/carteira_<semana>.json — retorno semanal real da carteira
  • data/benchmarks.parquet          — retornos diários de IBOV/SMAL11/CDI

Como o intraday roda hourly de 10h a 18h BRT, esta aba também atualiza
hourly — o último ponto da curva (semana em curso) evolui em tempo real.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

import config
from components.backtest import _render_retorno_acumulado
from components.footer import render_footer
from components.theme import COLORS
from utils.formatters import fmt_data_br, fmt_pct, fmt_reais


# ---------------------------------------------------------------------------
# Carregamento (reusa lógica da Carteira mas isolada para clareza)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _carregar_historicos_v3c() -> list[dict]:
    """
    Lê todos os arquivos historico/carteira_<semana>.json (V3c) com
    performance_diaria não vazia. Ordenado cronologicamente.
    Exclui carteira_v2_*.json.
    """
    hist_dir = config.HISTORICO_DIR
    if not hist_dir.exists():
        return []
    arquivos = [
        p for p in hist_dir.glob("carteira_*.json")
        if not p.name.startswith("carteira_v2_")
    ]
    semana_data: dict[str, dict] = {}
    for path in arquivos:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if not d.get("performance_diaria"):
                continue
            if d.get("metadata", {}).get("versao_formula") != "v3c":
                continue
            chave = d["metadata"].get("data_vigencia_inicio") or path.stem
            existente = semana_data.get(chave)
            if (existente is None or
                len(d["performance_diaria"]) > len(existente["performance_diaria"])):
                semana_data[chave] = d
        except Exception:
            continue
    return sorted(
        semana_data.values(),
        key=lambda x: x["metadata"].get("data_vigencia_inicio", ""),
    )


@st.cache_data(ttl=60)
def _carregar_benchmarks_df() -> pd.DataFrame | None:
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Equity curve real — mesmo formato do backtest, alimenta o gráfico
# ---------------------------------------------------------------------------

def _construir_equity_curve_real(
    historicos: list[dict],
    bench_df: pd.DataFrame | None,
) -> list[dict]:
    """
    Constrói uma equity_curve no MESMO formato consumido por
    _render_retorno_acumulado() do backtest:

        [{ data, valor_estrategia, valor_ibov, valor_smll, valor_cdi }, ...]

    Lógica:
      • Ponto inicial (baseline 100): data_corte_dados da primeira semana
        — representa "0% acumulado" e ancora o gráfico.
      • Para cada semana real: compõe retorno semanal da carteira sobre o
        valor cumulativo anterior. Benchmarks são calculados como retorno
        cumulativo total do parquet desde o data_corte inicial até o último
        pregão de cada semana (mais preciso que encadear retornos semanais).
    """
    if not historicos or bench_df is None:
        return []

    meta_primeira = historicos[0]["metadata"]
    data_corte_inicial_str = meta_primeira.get("data_corte_dados") \
                          or meta_primeira.get("data_vigencia_inicio")
    if not data_corte_inicial_str:
        return []
    dt_corte_inicial = date.fromisoformat(data_corte_inicial_str[:10])

    # Ponto inicial: 100 = baseline (0% acumulado)
    curva: list[dict] = [{
        "data":             data_corte_inicial_str[:10],
        "valor_estrategia": 100.0,
        "valor_ibov":       100.0,
        "valor_smll":       100.0,
        "valor_cdi":        100.0,
    }]

    val_strat = 100.0
    for h in historicos:
        ret_semana = h.get("retorno_acumulado_total") or 0.0
        val_strat = val_strat * (1.0 + ret_semana)

        perf = h.get("performance_diaria", [])
        data_x = perf[-1]["data"][:10] if perf \
                 else h["metadata"].get("data_vigencia_fim", "")[:10]
        dt_x = date.fromisoformat(data_x)

        # Benchmarks: cumulativo total do parquet (dt_corte_inicial → dt_x]
        def _val_acum(col: str) -> float:
            if col not in bench_df.columns:
                return 100.0
            janela = bench_df[
                (bench_df["date"].dt.date > dt_corte_inicial) &
                (bench_df["date"].dt.date <= dt_x)
            ][col].dropna()
            ret = float((1 + janela).prod() - 1) if not janela.empty else 0.0
            return 100.0 * (1 + ret)

        curva.append({
            "data":             data_x,
            "valor_estrategia": val_strat,
            "valor_ibov":       _val_acum("ibov"),
            "valor_smll":       _val_acum("smll"),
            "valor_cdi":        _val_acum("cdi"),
        })

    return curva


# ---------------------------------------------------------------------------
# Cabeçalho com período e contagem de semanas
# ---------------------------------------------------------------------------

def _render_cabecalho(historicos: list[dict]) -> None:
    if not historicos:
        return
    primeira = historicos[0]["metadata"]
    ultima   = historicos[-1]["metadata"]

    n_total = len(historicos)
    n_fechadas = sum(
        1 for h in historicos
        if (h.get("metadata", {}).get("data_vigencia_fim") or "") < date.today().isoformat()
    )
    n_em_curso = n_total - n_fechadas

    detalhe = (f"{n_fechadas} fechada{'s' if n_fechadas != 1 else ''}"
               + (f", {n_em_curso} em curso" if n_em_curso else ""))

    st.markdown(
        f"""
        <div style='display:flex; gap:24px; flex-wrap:wrap;
                    padding:14px 0 22px 0;
                    border-bottom:1px solid {COLORS["border"]};
                    margin-bottom:28px;'>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:{COLORS["muted"]};
                        font-weight:500;'>
              Período (operação real)
            </div>
            <div style='font-size:0.95rem; color:{COLORS["ink"]};
                        font-weight:500; margin-top:2px;'>
              {fmt_data_br(primeira.get("data_vigencia_inicio"))}
              → hoje
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:{COLORS["muted"]};
                        font-weight:500;'>
              Semanas registradas
            </div>
            <div style='font-size:0.95rem; color:{COLORS["ink"]};
                        font-weight:500; margin-top:2px;'>
              {n_total} <span style='color:{COLORS["muted"]}; font-weight:400;'>
              ({detalhe})</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Card único: retorno acumulado real
# ---------------------------------------------------------------------------

def _render_card_retorno(curva: list[dict]) -> None:
    if len(curva) < 2:
        st.info("Aguardando primeira semana fechar pra calcular retorno acumulado.")
        return

    ret_acum = curva[-1]["valor_estrategia"] / 100.0 - 1.0
    cor = COLORS["pos"] if ret_acum >= 0 else COLORS["neg"]

    st.markdown(
        f"""
        <div style='background:{COLORS["surface"]};
                    border:1px solid {COLORS["border"]};
                    border-radius:2px; padding:24px 28px;
                    max-width:520px;'>
          <div style='font-size:0.74rem; text-transform:uppercase;
                      letter-spacing:0.9px; color:{COLORS["muted"]};
                      font-weight:500;'>
            Retorno acumulado real
          </div>
          <div style='font-family:"Source Serif Pro",Georgia,serif;
                      font-size:2.6rem; font-weight:600; color:{cor};
                      line-height:1.1; margin-top:6px;
                      font-feature-settings:"tnum" 1;'>
            {fmt_pct(ret_acum, sinal=True)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tabela: histórico semanal completo (todas as semanas reais)
# ---------------------------------------------------------------------------

VALOR_INICIAL_CARTEIRA = 10_000.0


def _render_tabela_historico(
    historicos: list[dict],
    bench_df: pd.DataFrame | None,
) -> None:
    if not historicos:
        return

    rows = []
    valor_acum = VALOR_INICIAL_CARTEIRA
    for h in historicos:
        meta = h["metadata"]
        vig_ini = meta.get("data_vigencia_inicio", "")
        vig_fim = meta.get("data_vigencia_fim", "")
        ret_semana = h.get("retorno_acumulado_total") or 0.0
        valor_acum = valor_acum * (1.0 + ret_semana)
        n_stops = len(h.get("stops_semana") or [])

        # Benchmarks da semana (entre data_corte e fim de vigência ou último pregão)
        data_corte = meta.get("data_corte_dados", "")
        perf = h.get("performance_diaria", [])
        data_chart = perf[-1]["data"][:10] if perf else vig_fim
        vs_ibov = vs_smll = vs_cdi = None
        if bench_df is not None and data_corte and data_chart:
            try:
                dt_c = date.fromisoformat(data_corte[:10])
                dt_x = date.fromisoformat(data_chart[:10])
                for col, alvo in [("ibov", "vs_ibov"), ("smll", "vs_smll"), ("cdi", "vs_cdi")]:
                    if col in bench_df.columns:
                        j = bench_df[
                            (bench_df["date"].dt.date > dt_c) &
                            (bench_df["date"].dt.date <= dt_x)
                        ][col].dropna()
                        if not j.empty:
                            ret_bench = float((1 + j).prod() - 1)
                            spread = ret_semana - ret_bench
                            if alvo == "vs_ibov": vs_ibov = spread
                            elif alvo == "vs_smll": vs_smll = spread
                            elif alvo == "vs_cdi": vs_cdi = spread
            except Exception:
                pass

        rows.append({
            "Vigência":     f"{fmt_data_br(vig_ini)} → {fmt_data_br(vig_fim)}",
            "Retorno (%)":  ret_semana * 100,
            "vs IBOV (%)":  vs_ibov * 100 if vs_ibov is not None else None,
            "vs SMAL11 (%)": vs_smll * 100 if vs_smll is not None else None,
            "vs CDI (%)":   vs_cdi * 100 if vs_cdi is not None else None,
            "Stops":        n_stops,
            "Carteira (R$)": valor_acum,
        })

    df = pd.DataFrame(rows[::-1])  # mais recente em cima

    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Vigência":      st.column_config.TextColumn(width="medium"),
            "Retorno (%)":   st.column_config.NumberColumn("Retorno", format="%+.2f%%"),
            "vs IBOV (%)":   st.column_config.NumberColumn("vs IBOV", format="%+.2f%%"),
            "vs SMAL11 (%)": st.column_config.NumberColumn("vs SMAL11", format="%+.2f%%"),
            "vs CDI (%)":    st.column_config.NumberColumn("vs CDI", format="%+.2f%%"),
            "Stops":         st.column_config.NumberColumn(
                format="%d",
                help="Número de stop loss acionados na semana.",
            ),
            "Carteira (R$)": st.column_config.NumberColumn(
                format="R$ %.2f",
                help=f"Carteira teórica iniciada com R$ {VALOR_INICIAL_CARTEIRA:.0f}.",
            ),
        },
    )


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_live() -> None:
    historicos = _carregar_historicos_v3c()
    bench_df   = _carregar_benchmarks_df()

    if not historicos:
        st.warning(
            "Nenhuma semana real registrada ainda. "
            "Esta aba popula conforme o sistema vivo gera histórico."
        )
        render_footer()
        return

    _render_cabecalho(historicos)
    _render_card_retorno(_construir_equity_curve_real(historicos, bench_df))

    # Gráfico (reusa lógica do backtest)
    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown("### Retorno acumulado por semana")
    curva = _construir_equity_curve_real(historicos, bench_df)
    if len(curva) >= 2:
        # Passa periodo='2a' (não filtra com nossas 2-3 entradas)
        _render_retorno_acumulado(curva, periodo="2a")
    else:
        st.info("Aguardando primeira semana fechar para plotar.")

    # Tabela detalhada
    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown("### Histórico semanal completo")
    _render_tabela_historico(historicos, bench_df)

    render_footer()
