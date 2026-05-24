"""Aba 1 — Carteira da semana (V2)."""
from __future__ import annotations

import json
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from utils.formatters import fmt_data_br, fmt_pct, fmt_pct_delta, fmt_reais

# Nomes dos dias em PT-BR (independente do locale do browser)
_DIAS_PT = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_carteira() -> dict | None:
    if not config.CARTEIRA_V2_ATUAL_PATH.exists():
        return None
    with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=60)          # TTL curto para pegar atualizações da semana
def _carregar_historico_com_performance() -> dict | None:
    """
    Varre historico/ e retorna o arquivo mais recente que tenha
    performance_diaria não-vazia. Aceita carteira*.json (qualquer prefixo).
    """
    hist_dir = config.HISTORICO_DIR
    if not hist_dir.exists():
        return None

    # Ordena por nome decrescente — nomes ISO-week garantem ordem cronológica
    candidatos = sorted(hist_dir.glob("carteira*.json"), key=lambda p: p.name, reverse=True)

    for path in candidatos:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("performance_diaria"):   # lista não-vazia = há pregões
                return data
        except Exception:
            continue
    return None


@st.cache_data(ttl=300)
def _carregar_benchmarks() -> pd.DataFrame | None:
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Gráfico de performance acumulada
# ---------------------------------------------------------------------------

def _render_grafico(performance: list[dict], bench_df: pd.DataFrame | None, data_corte: str) -> None:
    """
    Gráfico de linha com:
    - Eixo X: dias da semana em PT-BR (Seg 18/05 …)
    - Labels de % acumulado ABAIXO de cada ponto da Carteira V2
    - Linha de base em 0 %
    - Benchmarks (IBOV, SMAL11, CDI) quando disponíveis
    """
    if not performance:
        st.info("Nenhum pregão de performance disponível ainda.")
        return

    rows = []
    for p in performance:
        rows.append({
            "data": p["data"],
            "serie": "Carteira V2",
            "retorno": p["retorno_acumulado"],
        })
        if "benchmarks" in p:
            b = p["benchmarks"]
            for nome, key in [("IBOV", "ibov"), ("SMAL11", "smll"), ("CDI", "cdi")]:
                v = b.get(key)
                if v is not None:
                    rows.append({"data": p["data"], "serie": nome, "retorno": v})

    # Se não havia benchmarks embutidos, calcula do parquet
    if len(rows) <= len(performance) and bench_df is not None:
        dt_corte = date.fromisoformat(data_corte)
        for p in performance:
            dt = date.fromisoformat(p["data"][:10])
            for nome, col in [("IBOV", "ibov"), ("SMAL11", "smll"), ("CDI", "cdi")]:
                if col in bench_df.columns:
                    janela = bench_df[
                        (bench_df["date"].dt.date > dt_corte) &
                        (bench_df["date"].dt.date <= dt)
                    ][col].dropna()
                    ret_acum = float(((1 + janela).prod() - 1)) if not janela.empty else 0.0
                    rows.append({"data": p["data"], "serie": nome, "retorno": ret_acum})

    df = pd.DataFrame(rows)
    if df.empty:
        return

    # Normaliza para data e mantém apenas o último valor por (dia, série)
    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    df = df.groupby(["data", "serie"], as_index=False).last()

    # Rótulo do eixo X: "Seg 18/05" — forçado em PT-BR
    df["dia"] = df["data"].apply(
        lambda d: f"{_DIAS_PT.get(d.dayofweek, '')} {d.strftime('%d/%m')}"
    )
    # Ordem explícita dos dias (preserva sequência cronológica)
    ordem_dias = (
        df[["data", "dia"]].drop_duplicates().sort_values("data")["dia"].tolist()
    )

    colors = {
        "Carteira V2": "#2563eb",
        "IBOV":        "#6b7280",
        "SMAL11":      "#9ca3af",
        "CDI":         "#d1d5db",
    }
    domain    = list(colors.keys())
    range_c   = list(colors.values())

    base = alt.Chart(df)

    linhas = base.mark_line(point=alt.OverlayMarkDef(filled=True, size=60)).encode(
        x=alt.X(
            "dia:O",
            sort=ordem_dias,
            title="",
            axis=alt.Axis(labelAngle=0),
        ),
        y=alt.Y(
            "retorno:Q",
            title="Retorno acumulado",
            axis=alt.Axis(format=".1%"),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=domain, range=range_c),
            legend=alt.Legend(title=""),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V2",
            alt.value(3),
            alt.value(1.5),
        ),
        tooltip=[
            alt.Tooltip("dia:O",      title="Dia"),
            alt.Tooltip("serie:N",    title=""),
            alt.Tooltip("retorno:Q",  format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=320)

    # Labels ABAIXO de cada ponto da Carteira V2
    df_label = df[df["serie"] == "Carteira V2"].copy()
    labels = alt.Chart(df_label).mark_text(
        align="center",
        baseline="top",     # topo do texto alinhado ao ponto → texto fica abaixo
        dy=8,               # desloca 8px para baixo
        fontSize=11,
        fontWeight="bold",
        color="#2563eb",
    ).encode(
        x=alt.X("dia:O", sort=ordem_dias),
        y=alt.Y("retorno:Q"),
        text=alt.Text("retorno:Q", format="+.2%"),
    )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color="gray", opacity=0.5
    ).encode(y="y:Q")

    st.altair_chart(linhas + baseline + labels, use_container_width=True)


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_carteira() -> None:
    carteira = _carregar_carteira()

    if carteira is None:
        st.error(
            "Carteira V2 ainda não gerada. "
            "Execute `python run_v2.py --fase 3` primeiro."
        )
        render_footer()
        return

    meta        = carteira["metadata"]
    tickers     = carteira.get("tickers", [])
    performance = carteira.get("performance_diaria", [])
    n           = meta.get("n_posicoes", 0)
    ret_total   = carteira.get("retorno_acumulado_total", 0.0)
    bootstrap   = meta.get("bootstrap_retroativo", False)
    data_corte  = meta.get("data_corte_dados", "")

    # -----------------------------------------------------------------------
    # Bootstrap: quando a semana atual ainda não tem pregões, mostra a última
    # semana completa do historico (com banner informativo)
    # -----------------------------------------------------------------------
    historico: dict | None = None
    usando_historico = False

    if not performance:
        historico = _carregar_historico_com_performance()
        if historico:
            st.info(
                "🔄 **Exibindo a última semana com pregões registrados** — "
                "a carteira atual ainda não tem dados de performance disponíveis."
            )
            usando_historico = True
            # Usa dados históricos para performance e tabela
            performance = historico["performance_diaria"]
            ret_total   = historico.get("retorno_acumulado_total", 0.0)
            data_corte  = historico["metadata"].get("data_corte_dados", data_corte)
            tickers     = historico.get("tickers", tickers)
        else:
            st.info(
                "🕐 **Performance ainda não disponível** — "
                "aguardando o primeiro pregão da semana."
            )

    # Badge de bootstrap retroativo (carteira gerada retroativamente)
    if bootstrap:
        st.info(
            f"🔄 **Carteira retroativa de bootstrap** — formada com dados até "
            f"{fmt_data_br(data_corte)}. "
            f"Próxima carteira oficial: "
            f"{fmt_data_br(meta.get('proxima_carteira_oficial'))}."
        )

    if n == 0:
        st.error("🚫 Nenhuma ação atendeu aos filtros F1+F2 esta semana. Sem recomendação.")
        render_footer()
        return
    elif n < 5:
        st.warning(
            f"⚠️ Apenas {n} ações passaram nos filtros esta semana. "
            f"Peso por posição: {100/n:.1f}%"
        )

    # -----------------------------------------------------------------------
    # Cabeçalho
    # -----------------------------------------------------------------------
    if usando_historico and historico:
        h_meta     = historico["metadata"]
        n_display  = h_meta.get("n_posicoes", n)
        st.subheader("Carteira da semana anterior")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Formada em:** {fmt_data_br(h_meta.get('data_formacao'))}")
        c2.markdown(
            f"**Vigência:** {fmt_data_br(h_meta.get('data_vigencia_inicio'))} → "
            f"{fmt_data_br(h_meta.get('data_vigencia_fim'))}"
        )
        c3.markdown(f"**Posições:** {n_display} | Peso: {100/n_display:.0f}%")
    else:
        st.subheader("Carteira da semana")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Formada em:** {fmt_data_br(meta.get('data_formacao'))}")
        c2.markdown(
            f"**Vigência:** {fmt_data_br(meta.get('data_vigencia_inicio'))} → "
            f"{fmt_data_br(meta.get('data_vigencia_fim'))}"
        )
        c3.markdown(f"**Posições:** {n} | Peso: {100/n:.0f}%")

    # -----------------------------------------------------------------------
    # Tabela de posições individuais
    # -----------------------------------------------------------------------
    rows = []
    for t in tickers:
        ret    = t.get("retorno_acumulado", 0.0)
        status = "⚠️ Stale" if t.get("is_stale") else "✅ Ativo"
        rows.append({
            "Ticker":            t["ticker"],
            "Score (formação)":  fmt_score_val(t.get("score_na_formacao")),
            "Entrada":           fmt_reais(t.get("preco_entrada")),
            "Atual":             fmt_reais(t.get("preco_atual")),
            "Retorno Acum.":     fmt_pct(ret, sinal=True),
            "Status":            status,
        })

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # -----------------------------------------------------------------------
    # Performance da semana (gráfico + métricas numéricas)
    # -----------------------------------------------------------------------
    if performance:
        bench_df = _carregar_benchmarks()

        # — Gráfico acumulado por dia —
        st.subheader("Performance acumulada da semana")
        _render_grafico(performance, bench_df, data_corte)

        # — Métricas numéricas —
        st.subheader("Performance numérica")
        ret_ibov = ret_smll = ret_cdi = None
        if bench_df is not None:
            dt_corte = date.fromisoformat(data_corte)
            dt_fim   = date.fromisoformat(performance[-1]["data"][:10])
            for nome_col, nome_var in [("ibov", "ibov"), ("smll", "smll"), ("cdi", "cdi")]:
                if nome_col in bench_df.columns:
                    janela = bench_df[
                        (bench_df["date"].dt.date > dt_corte) &
                        (bench_df["date"].dt.date <= dt_fim)
                    ][nome_col].dropna()
                    v = float(((1 + janela).prod() - 1)) if not janela.empty else None
                    if nome_var == "ibov":
                        ret_ibov = v
                    elif nome_var == "smll":
                        ret_smll = v
                    elif nome_var == "cdi":
                        ret_cdi = v

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Carteira V2", fmt_pct(ret_total, sinal=True))
        col2.metric(
            "vs IBOV",
            fmt_pct(ret_ibov, sinal=True) if ret_ibov is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_ibov) if ret_ibov is not None else None,
            help="Delta = Carteira − IBOV (positivo: superou o índice)",
        )
        col3.metric(
            "vs SMAL11",
            fmt_pct(ret_smll, sinal=True) if ret_smll is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_smll) if ret_smll is not None else None,
            help="Delta = Carteira − SMAL11",
        )
        col4.metric(
            "vs CDI",
            fmt_pct(ret_cdi, sinal=True) if ret_cdi is not None else "—",
            delta=fmt_pct_delta(ret_total - ret_cdi) if ret_cdi is not None else None,
            help="Delta = Carteira − CDI",
        )

    render_footer()


def fmt_score_val(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):.1f}"
