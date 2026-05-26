"""Aba Backtest V2 — versão editorial limpa."""
from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from components.theme import CHART_PALETTE, COLORS
from utils.formatters import fmt_data_br, fmt_pct


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_backtest() -> dict | None:
    if not config.BACKTEST_V3C_RESULTADO_PATH.exists():
        return None
    with open(config.BACKTEST_V3C_RESULTADO_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=60)
def _carregar_benchmarks_df_live() -> "pd.DataFrame | None":
    """Le data/benchmarks.parquet (fonte canonica) - cache curto para refletir
    cada update intraday."""
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=60)
def _carregar_live_atual() -> dict | None:
    """
    Lê o JSON da semana V3c LIVE mais recente em historico/.
    Usado para sobrescrever o último ponto do equity_curve com o retorno
    real apurado pelo sistema vivo (em vez do retorno simulado do backtest).
    """
    hist_dir = config.HISTORICO_DIR
    if not hist_dir.exists():
        return None
    candidatos = sorted(
        (p for p in hist_dir.glob("carteira_*.json")
         if not p.name.startswith("carteira_v2_")),
        key=lambda p: p.name,
        reverse=True,
    )
    for path in candidatos:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("metadata", {}).get("versao_formula") == "v3c":
                return d
        except Exception:
            continue
    return None


def _injetar_live_no_equity_curve(
    equity_curve: list[dict],
    live: dict | None,
    bench_df: "pd.DataFrame | None" = None,
) -> list[dict]:
    """
    Substitui o último ponto do equity_curve (W atual SIMULADA pelo backtest)
    pelos valores REAIS LIVE — para TODAS as séries (estrategia + benchmarks),
    garantindo total consistência com a aba Carteira (mesma fonte: parquet).

    Mudanças no último ponto:
      • valor_estrategia: penúltimo × (1 + retorno_acumulado_total live)
      • valor_ibov:       penúltimo × (1 + IBOV cumulado no parquet da semana)
      • valor_smll:       penúltimo × (1 + SMAL11 cumulado no parquet da semana)
      • valor_cdi:        penúltimo × (1 + CDI cumulado no parquet da semana)

    Se a semana live não bate com o último ponto do backtest, NÃO altera nada
    (segurança — evita reescrever histórico errado).
    """
    if not equity_curve or live is None or len(equity_curve) < 2:
        return equity_curve

    ret_live_pct = live.get("retorno_acumulado_total")
    if ret_live_pct is None:
        return equity_curve

    meta = live.get("metadata", {})
    vig_ini_live   = (meta.get("data_vigencia_inicio") or "")[:10]
    ultima_data_bt = str(equity_curve[-1].get("data", ""))[:10]
    if not vig_ini_live or not ultima_data_bt or vig_ini_live != ultima_data_bt:
        return equity_curve

    valor_estrategia_anterior = equity_curve[-2].get("valor_estrategia")
    if valor_estrategia_anterior is None:
        return equity_curve

    novo_ponto = dict(equity_curve[-1])
    novo_ponto["valor_estrategia"] = valor_estrategia_anterior * (1.0 + ret_live_pct)
    novo_ponto["_live"] = True

    # Atualiza TAMBÉM os benchmarks do último ponto a partir do parquet
    # (centraliza fonte: mesmo cálculo dos cards e tabela da Carteira).
    if bench_df is not None and not bench_df.empty:
        from datetime import date
        data_corte_str = meta.get("data_corte_dados", "")[:10]
        perf = live.get("performance_diaria", [])
        data_x_str = (perf[-1]["data"][:10] if perf
                      else meta.get("data_vigencia_fim", "")[:10])
        if data_corte_str and data_x_str:
            try:
                dt_corte = date.fromisoformat(data_corte_str)
                dt_x     = date.fromisoformat(data_x_str)
                for col, key in [("ibov", "valor_ibov"),
                                 ("smll", "valor_smll"),
                                 ("cdi",  "valor_cdi")]:
                    if col in bench_df.columns:
                        janela = bench_df[
                            (bench_df["date"].dt.date > dt_corte) &
                            (bench_df["date"].dt.date <= dt_x)
                        ][col].dropna()
                        prev_val = equity_curve[-2].get(key)
                        if not janela.empty and prev_val is not None:
                            ret_bench = float((1 + janela).prod() - 1)
                            novo_ponto[key] = prev_val * (1 + ret_bench)
            except Exception:
                pass  # mantém valores do backtest se algo der errado

    return list(equity_curve[:-1]) + [novo_ponto]


def _filtrar_equity(equity_curve: list[dict], periodo: str) -> list[dict]:
    n = {"3m": 13, "6m": 26, "1a": 52, "2a": 104}.get(periodo, 104)
    return equity_curve[-n:] if len(equity_curve) >= n else equity_curve


# ---------------------------------------------------------------------------
# Gráfico de retorno acumulado semanal (Carteira vs Benchmarks)
# ---------------------------------------------------------------------------

def _render_retorno_acumulado(equity_curve: list[dict], periodo: str) -> None:
    dados = _filtrar_equity(equity_curve, periodo)
    if not dados:
        st.info("Sem dados de equity curve.")
        return

    df = pd.DataFrame(dados)
    df["data"] = pd.to_datetime(df["data"])

    # Base canônica do backtest = 100. Quando o usuário filtra para uma janela
    # parcial (3m/6m/1a), renormalizamos para o primeiro ponto da janela para
    # que o gráfico exiba o retorno DENTRO da janela escolhida.
    # Para período "2a" (full), usamos 100 — assim o final do gráfico bate
    # exatamente com o card 'Retorno acumulado'.
    janela_completa = len(dados) >= len(equity_curve)
    if janela_completa:
        base_est = base_ibov = base_smll = base_cdi = 100.0
    else:
        base_est  = df["valor_estrategia"].iloc[0]
        base_ibov = df["valor_ibov"].iloc[0]
        base_smll = df["valor_smll"].iloc[0]
        base_cdi  = df["valor_cdi"].iloc[0]

    df["Carteira V3c"] = df["valor_estrategia"] / base_est  - 1
    df["IBOV"]         = df["valor_ibov"]       / base_ibov - 1
    df["SMAL11"]       = df["valor_smll"]       / base_smll - 1
    df["CDI"]          = df["valor_cdi"]        / base_cdi  - 1

    df_long = df.melt(
        id_vars="data",
        value_vars=["Carteira V3c", "IBOV", "SMAL11", "CDI"],
        var_name="serie",
        value_name="retorno",
    )

    colors = {k: CHART_PALETTE[k] for k in ("Carteira V3c", "IBOV", "SMAL11", "CDI")}
    base   = alt.Chart(df_long)

    linhas = base.mark_line().encode(
        x=alt.X("data:T", title="", axis=alt.Axis(format="%b/%y", labelColor=COLORS["muted"])),
        y=alt.Y(
            "retorno:Q",
            title="",
            axis=alt.Axis(format=".0%", labelColor=COLORS["muted"]),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
            legend=alt.Legend(title="", labelColor=COLORS["ink"], labelFontSize=12),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V3c",
            alt.value(2.5),
            alt.value(1.2),
        ),
        tooltip=[
            alt.Tooltip("data:T",     title="Semana", format="%d/%m/%Y"),
            alt.Tooltip("serie:N",    title=""),
            alt.Tooltip("retorno:Q",  format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=400)

    # Labels finais sem sobreposição: stagger vertical baseado em retorno
    df_last = (
        df_long.sort_values("data")
        .groupby("serie", as_index=False)
        .tail(1)
        .copy()
    )
    df_last["rank"] = df_last["retorno"].rank(method="first", ascending=False)
    # dy = -8 para o de cima, escala 14 px por rank pra evitar overlap
    df_last["dy"]   = (df_last["rank"] - 1) * 14 - 4

    labels_list = []
    for _, row in df_last.iterrows():
        labels_list.append(
            alt.Chart(pd.DataFrame([row])).mark_text(
                align="left",
                baseline="middle",
                dx=8,
                dy=float(row["dy"]),
                fontSize=11,
                fontWeight="bold",
                font="Inter",
            ).encode(
                x=alt.X("data:T"),
                y=alt.Y("retorno:Q"),
                text=alt.Text("retorno:Q", format="+.1%"),
                color=alt.Color(
                    "serie:N",
                    scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
                    legend=None,
                ),
            )
        )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color=COLORS["muted_2"], opacity=0.6
    ).encode(y="y:Q")

    chart = linhas + baseline
    for lbl in labels_list:
        chart = chart + lbl

    st.altair_chart(chart, use_container_width=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_backtest(periodo: str = "2a") -> None:
    bt = _carregar_backtest()

    if bt is None:
        st.warning("Backtest V3c ainda não gerado.")
        render_footer()
        return

    meta         = bt["metadata"]
    metricas     = bt.get("metricas_estrategia", {})
    bench        = bt.get("metricas_benchmarks", {})
    alphas       = bt.get("alphas", {})
    equity_curve = bt.get("equity_curve", [])

    # Substitui o último ponto do equity_curve (W simulada da semana corrente)
    # pelos valores REAIS LIVE (estrategia + benchmarks). Garante que o
    # gráfico, os cards de spread e a tabela da Carteira/Backtest todos
    # usem a MESMA fonte canônica (parquet de benchmarks atualizado a cada
    # intraday). Sem isso, o último ponto da curva benchmark ficava congelado
    # no valor simulado do backtest, divergindo dos cards da Carteira.
    live = _carregar_live_atual()
    bench_df_live = _carregar_benchmarks_df_live()
    equity_curve = _injetar_live_no_equity_curve(equity_curve, live, bench_df_live)

    # Período em estilo editorial
    st.markdown(
        f"""
        <div style='display:flex; gap:24px; flex-wrap:wrap;
                    padding:14px 0 22px 0;
                    border-bottom:1px solid #DDD8CE;
                    margin-bottom:28px;'>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Período do backtest
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {fmt_data_br(meta.get('janela_inicio'))} → {fmt_data_br(meta.get('janela_fim'))}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Semanas
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {meta.get('n_semanas_simuladas', '—')}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Fórmula · Universo
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {meta.get('versao_formula', 'v2').upper()} · {meta.get('universo_versao', '—')}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Métricas principais — 2 cards grandes
    m1, m2 = st.columns(2)
    m1.metric(
        "Retorno acumulado",
        fmt_pct(metricas.get("retorno_total"), sinal=True),
        help="Retorno total da estratégia no período do backtest.",
    )
    m2.metric(
        "Retorno anualizado",
        fmt_pct(metricas.get("retorno_anualizado"), sinal=True),
        help="Retorno anualizado equivalente (CAGR).",
    )

    # Comparação com benchmarks
    st.markdown("### Comparação com benchmarks")
    col1, col2, col3, col4, col5 = st.columns(5)

    def _ret_bench(nome: str) -> str:
        v = bench.get(nome, {}).get("retorno_anualizado")
        return fmt_pct(v) if v is not None else "n/d"

    col1.metric("IBOV a.a.",       _ret_bench("ibov"))
    col2.metric("SMAL11 a.a.",     _ret_bench("smll"))
    col3.metric("CDI a.a.",        _ret_bench("cdi"))
    col4.metric("Alpha vs IBOV",   fmt_pct(alphas.get("vs_ibov"),  sinal=True))
    col5.metric("Alpha vs SMAL11", fmt_pct(alphas.get("vs_smll"), sinal=True))

    # Gráfico único
    st.markdown("### Retorno acumulado por semana")
    _render_retorno_acumulado(equity_curve, periodo)

    render_footer()
