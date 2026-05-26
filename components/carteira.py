"""Aba Carteira — versão editorial (sem emojis, com histórico semanal e carteira teórica composta)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from components.theme import CHART_PALETTE, COLORS
from utils.formatters import fmt_data_br, fmt_pct, fmt_reais

# Nomes dos dias em PT-BR (independente do locale do browser)
_DIAS_PT = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}

# Simulação de carteira teórica iniciada em 18/05/2026
VALOR_INICIAL_CARTEIRA = 10_000.0
DATA_INICIO_SIMULACAO  = date(2026, 5, 18)


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_carteira() -> dict | None:
    """
    Carrega a carteira da semana corrente.

    Prioridade:
      1. historico/carteira_<semana_corrente>.json se gerado por V3c
         (versao_formula == 'v3c' no metadata).
      2. data/carteira_atual_v2.json (fallback para a versão V2 do pipeline).

    O V3c live sobrescreve historico/ a cada hora durante o pregão; usar essa
    fonte como primária garante que o frontend reflita a lógica V3c assim que
    o pipeline live rodar.
    """
    hist_dir = config.HISTORICO_DIR
    if hist_dir.exists():
        # Coleta arquivos historico/carteira_*.json (exclui prefixos v2_).
        # Ordena pelo NOME do arquivo (carteira_YYYY-WWW.json) — ordem alfabética
        # bate com ordem cronológica e é determinística (independente de mtime,
        # que no Streamlit Cloud pode ser idêntico para vários arquivos após
        # git pull no mesmo segundo).
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

    # Fallback V2
    if not config.CARTEIRA_V2_ATUAL_PATH.exists():
        return None
    with open(config.CARTEIRA_V2_ATUAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=60)
def _carregar_todos_historicos() -> list[dict]:
    """
    Lê todos os arquivos historico/carteira_<semana>.json (V3c) com
    performance_diaria não-vazia. Retorna ordenado cronologicamente
    (mais antigo primeiro) e sem duplicatas de mesma semana ISO.

    Exclui arquivos `carteira_v2_*.json` — são da pipeline V2 antiga
    e colidem na mesma chave de data_vigencia_inicio que o V3c live,
    sobrescrevendo a tabela "Histórico semanal" com vigência errada.
    """
    hist_dir = config.HISTORICO_DIR
    if not hist_dir.exists():
        return []

    # Filtra: só arquivos do V3c (formato `carteira_YYYY-WWW.json`)
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
            # Só V3c (filtro defensivo — também excluído pelo nome)
            if d.get("metadata", {}).get("versao_formula") != "v3c":
                continue
            meta = d.get("metadata", {})
            chave = meta.get("data_vigencia_inicio") or meta.get("data_formacao") or path.stem
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
def _carregar_historico_com_performance() -> dict | None:
    """Retorna o histórico mais recente com performance_diaria não-vazia."""
    historicos = _carregar_todos_historicos()
    return historicos[-1] if historicos else None


@st.cache_data(ttl=300)
def _carregar_benchmarks() -> pd.DataFrame | None:
    if not config.BENCHMARKS_PARQUET_PATH.exists():
        return None
    df = pd.read_parquet(config.BENCHMARKS_PARQUET_PATH, engine="pyarrow")
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Cálculos auxiliares
# ---------------------------------------------------------------------------

def _calcular_retornos_benchmarks(
    bench_df: pd.DataFrame | None,
    data_inicio_iso: str,
    data_fim_iso: str,
) -> dict[str, float | None]:
    """Retorna {ibov, smll, cdi} acumulados na janela ]inicio, fim]."""
    out: dict[str, float | None] = {"ibov": None, "smll": None, "cdi": None}
    if bench_df is None:
        return out
    dt_ini = date.fromisoformat(data_inicio_iso[:10])
    dt_fim = date.fromisoformat(data_fim_iso[:10])
    for col in ("ibov", "smll", "cdi"):
        if col in bench_df.columns:
            janela = bench_df[
                (bench_df["date"].dt.date > dt_ini) &
                (bench_df["date"].dt.date <= dt_fim)
            ][col].dropna()
            out[col] = float((1 + janela).prod() - 1) if not janela.empty else None
    return out


def _historico_semanas_resumido(
    historicos: list[dict],
    bench_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Constrói tabela das últimas semanas + valor cumulativo da carteira teórica.
    Colunas: Semana, Vigência, Retorno, vs IBOV, vs SMAL11, vs CDI, Valor teórico
    """
    if not historicos:
        return pd.DataFrame()

    valor_acumulado = VALOR_INICIAL_CARTEIRA
    rows = []

    for h in historicos:
        meta = h["metadata"]
        ret_sem = h.get("retorno_acumulado_total", 0.0)
        bench   = _calcular_retornos_benchmarks(
            bench_df,
            meta.get("data_corte_dados", ""),
            h["performance_diaria"][-1]["data"],
        )
        valor_acumulado *= (1 + ret_sem)

        rows.append({
            "vig_inicio": meta.get("data_vigencia_inicio"),
            "vig_fim":    meta.get("data_vigencia_fim"),
            "ret":        ret_sem,
            "vs_ibov":    (ret_sem - bench["ibov"]) if bench["ibov"] is not None else None,
            "vs_smll":    (ret_sem - bench["smll"]) if bench["smll"] is not None else None,
            "vs_cdi":     (ret_sem - bench["cdi"])  if bench["cdi"]  is not None else None,
            "valor":      valor_acumulado,
        })

    return pd.DataFrame(rows)


def _proxima_segunda() -> date:
    """Próxima segunda-feira a partir de hoje (exclusive)."""
    hoje = date.today()
    dias = (7 - hoje.weekday()) % 7 or 7
    return hoje + timedelta(days=dias)


# ---------------------------------------------------------------------------
# Gráfico de performance acumulada (semana atual ou histórica)
# ---------------------------------------------------------------------------

def _render_grafico_semana(
    performance: list[dict],
    bench_df: pd.DataFrame | None,
    data_corte: str,
) -> None:
    if not performance:
        return

    rows = []
    for p in performance:
        rows.append({"data": p["data"], "serie": "Carteira V3c", "retorno": p["retorno_acumulado"]})

    # SEMPRE recalcula benchmarks do parquet (fonte canonica, sincronizado com
    # os cards "VS IBOV / VS SMAL11 / VS CDI"). O campo `benchmarks` salvo
    # dentro de `performance_diaria` pode estar com snapshot stale do momento
    # do intraday — divergiria do que os cards exibem.
    if bench_df is not None:
        dt_corte = date.fromisoformat(data_corte)
        for p in performance:
            dt = date.fromisoformat(p["data"][:10])
            for nome, col in [("IBOV", "ibov"), ("SMAL11", "smll"), ("CDI", "cdi")]:
                if col in bench_df.columns:
                    janela = bench_df[
                        (bench_df["date"].dt.date > dt_corte) &
                        (bench_df["date"].dt.date <= dt)
                    ][col].dropna()
                    if not janela.empty:
                        ret_acum = float((1 + janela).prod() - 1)
                        rows.append({"data": p["data"], "serie": nome, "retorno": ret_acum})

    df = pd.DataFrame(rows)
    if df.empty:
        return

    df["data"] = pd.to_datetime(df["data"]).dt.normalize()
    df = df.groupby(["data", "serie"], as_index=False).last()

    df["dia"] = df["data"].apply(
        lambda d: f"{_DIAS_PT.get(d.dayofweek, '')} {d.strftime('%d/%m')}"
    )
    ordem_dias = (
        df[["data", "dia"]].drop_duplicates().sort_values("data")["dia"].tolist()
    )

    colors  = {k: CHART_PALETTE[k] for k in ("Carteira V3c", "IBOV", "SMAL11", "CDI")}
    domain  = list(colors.keys())
    range_c = list(colors.values())

    base = alt.Chart(df)
    linhas = base.mark_line(point=alt.OverlayMarkDef(filled=True, size=55)).encode(
        x=alt.X(
            "dia:O",
            sort=ordem_dias,
            title="",
            axis=alt.Axis(labelAngle=0, labelColor=COLORS["muted"]),
        ),
        y=alt.Y(
            "retorno:Q",
            title="",
            axis=alt.Axis(format=".1%", labelColor=COLORS["muted"]),
        ),
        color=alt.Color(
            "serie:N",
            scale=alt.Scale(domain=domain, range=range_c),
            legend=alt.Legend(title="", labelColor=COLORS["ink"], labelFontSize=12),
        ),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira V3c",
            alt.value(2.5),
            alt.value(1.2),
        ),
        tooltip=[
            alt.Tooltip("dia:O",      title="Dia"),
            alt.Tooltip("serie:N",    title=""),
            alt.Tooltip("retorno:Q",  format="+.2%", title="Retorno acum."),
        ],
    ).properties(height=320)

    df_label = df[df["serie"] == "Carteira V3c"].copy()
    labels = alt.Chart(df_label).mark_text(
        align="center",
        baseline="top",
        dy=12,
        fontSize=11,
        fontWeight="bold",
        color=COLORS["primary"],
        font="Inter",
    ).encode(
        x=alt.X("dia:O", sort=ordem_dias),
        y=alt.Y("retorno:Q"),
        text=alt.Text("retorno:Q", format="+.2%"),
    )

    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color=COLORS["muted_2"], opacity=0.6
    ).encode(y="y:Q")

    st.altair_chart(linhas + baseline + labels, use_container_width=True)


# ---------------------------------------------------------------------------
# Banner editorial (substitui st.info azul)
# ---------------------------------------------------------------------------

def _banner_editorial(texto: str) -> None:
    st.markdown(
        f"<div class='editorial-banner'>{texto}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Eventos da semana (stops + redistribuição) — carteira LIVE
# ---------------------------------------------------------------------------

def _render_eventos_semana_live(carteira: dict) -> None:
    """
    Mostra a timeline de stops da semana atual + texto explicativo em
    linguagem natural. Lê `stops_semana` do JSON do historico (formato live).

    Para cada evento exibe data, ticker, retorno no stop, peso liberado,
    redistribuído (a posições positivas) e enviado para caixa.

    Se nenhum stop ocorreu, mostra um aviso discreto. Caso contrário,
    constrói uma "narrativa do dia" para cada data com stop, descrevendo
    o que aconteceu em linguagem natural (ex: "Terça 26/05 — STOP em
    TTEN3 a -5,40%; peso de 20% redistribuído para PINE4, HAPV3, MLAS3
    em proporção pro-rata").
    """
    eventos = carteira.get("stops_semana") or []
    # Normaliza data (alguns chegam com timestamp completo)
    for e in eventos:
        e["data"] = str(e.get("data", ""))[:10]
    eventos = sorted(eventos, key=lambda x: (x.get("data", ""), x.get("ticker", "")))

    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown("### Eventos da semana")

    if not eventos:
        st.markdown(
            """
            <div style='font-size:0.85rem; color:#7A7A7A;
                        padding:10px 14px; background:#F8F6F0;
                        border:1px solid #DDD8CE; border-radius:2px;'>
              Nenhum stop loss acionado nesta semana — as 5 posições seguem
              ativas com pesos originais (20% cada).
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Narrativa cronológica — agrupa eventos por data
    dias_pt_full = {
        0: "Segunda", 1: "Terça", 2: "Quarta",
        3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo",
    }
    eventos_por_dia: dict[str, list[dict]] = {}
    for e in eventos:
        eventos_por_dia.setdefault(e["data"], []).append(e)

    # Identifica as posições POSITIVAS na semana (para narrar a redistribuição)
    tickers_positivos = [
        t["ticker"] for t in carteira.get("tickers", [])
        if (t.get("retorno_acumulado") or 0) > 0
    ]

    narrativas = []
    for data_iso, eventos_dia in sorted(eventos_por_dia.items()):
        try:
            d = date.fromisoformat(data_iso)
            dia_label = f"{dias_pt_full[d.weekday()]} {d.strftime('%d/%m')}"
        except Exception:
            dia_label = data_iso

        partes = []
        for e in eventos_dia:
            tk     = e.get("ticker", "?")
            ret    = (e.get("ret_acumulado") or 0) * 100
            peso_red = (e.get("peso_redistribuido") or 0) * 100
            peso_cx  = (e.get("peso_caixa") or 0) * 100
            if peso_cx > 0.01 and peso_red < 0.01:
                destino = f"peso integral ({peso_cx:.1f}%) foi para caixa (nenhuma posição positiva no momento)"
            elif peso_cx > 0.01:
                destino = f"{peso_red:.1f}% redistribuído para posições positivas e {peso_cx:.1f}% para caixa (cap 2× atingido)"
            else:
                destino = f"{peso_red:.1f}% redistribuído integralmente para posições positivas"
            partes.append(f"<b>{tk}</b> stopou em {ret:+.2f}% (fechamento R$ {e.get('preco_stop', 0):.2f}); {destino}")

        narrativa = f"<b>{dia_label}</b> · " + " &nbsp;•&nbsp; ".join(partes)
        narrativas.append(narrativa)

    # Renderiza narrativa
    st.markdown(
        f"""
        <div style='font-size:0.88rem; color:#2A2A2A; line-height:1.6;
                    background:#FBF9F4; border-left:3px solid {COLORS["primary"]};
                    padding:14px 18px; border-radius:2px;
                    margin-bottom:14px;'>
          {"<br><br>".join(narrativas)}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tabela detalhada de eventos (mesma estrutura da aba Histórico)
    rows = []
    for e in eventos:
        rows.append({
            "Data":              fmt_data_br(e.get("data", "")),
            "Evento":            e.get("evento", "—").replace("_", " ").title(),
            "Ticker":            e.get("ticker", "—"),
            "Retorno no stop (%)": (e.get("ret_acumulado") or 0) * 100,
            "Entrada (R$)":      e.get("preco_entrada"),
            "Preço stop (R$)":   e.get("preco_stop"),
            "Peso liberado (%)": (e.get("peso_no_stop") or 0) * 100,
            "→ Redistribuído (%)": (e.get("peso_redistribuido") or 0) * 100,
            "→ Caixa (%)":       (e.get("peso_caixa") or 0) * 100,
        })
    df_ev = pd.DataFrame(rows)
    st.dataframe(
        df_ev,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Data":     st.column_config.TextColumn(width="small"),
            "Evento":   st.column_config.TextColumn(width="small"),
            "Ticker":   st.column_config.TextColumn(width="small"),
            "Retorno no stop (%)": st.column_config.NumberColumn(
                "Retorno no stop",
                format="%+.2f%%",
                help="Retorno acumulado quando o stop foi acionado. "
                     "Trigger: ret ≤ -5%; execução no preço de fechamento.",
            ),
            "Entrada (R$)":    st.column_config.NumberColumn(format="R$ %.2f"),
            "Preço stop (R$)": st.column_config.NumberColumn(
                "Preço no stop",
                format="R$ %.2f",
            ),
            "Peso liberado (%)": st.column_config.NumberColumn(
                "Peso liberado",
                format="%.1f%%",
                help="Peso que a posição tinha quando stopou.",
            ),
            "→ Redistribuído (%)": st.column_config.NumberColumn(
                "→ Posições positivas",
                format="%.1f%%",
                help="Fração do peso liberado realocada para posições com retorno > 0 "
                     "(respeitando cap 2× peso original).",
            ),
            "→ Caixa (%)": st.column_config.NumberColumn(
                "→ Caixa",
                format="%.1f%%",
                help="Fração não redistribuída — cap 2× atingido ou nenhuma "
                     "posição positiva. Capital fica rendendo 0% até sexta.",
            ),
        },
    )


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_carteira() -> None:
    carteira = _carregar_carteira()

    if carteira is None:
        st.error("Carteira ainda não gerada.")
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
    # Bootstrap: se a semana atual não tem pregões, usa último histórico
    # -----------------------------------------------------------------------
    historicos = _carregar_todos_historicos()
    historico_atual: dict | None = None
    usando_historico = False

    if not performance:
        historico_atual = historicos[-1] if historicos else None
        if historico_atual:
            usando_historico = True
            performance = historico_atual["performance_diaria"]
            ret_total   = historico_atual.get("retorno_acumulado_total", 0.0)
            data_corte  = historico_atual["metadata"].get("data_corte_dados", data_corte)
            tickers     = historico_atual.get("tickers", tickers)

    if bootstrap:
        _banner_editorial(
            f"Carteira retroativa de bootstrap · dados até {fmt_data_br(data_corte)}. "
            f"Próxima carteira oficial em {fmt_data_br(meta.get('proxima_carteira_oficial'))}."
        )

    if n == 0:
        st.warning("Nenhuma ação atendeu aos filtros F1+F2 esta semana. Sem recomendação.")
        render_footer()
        return

    # -----------------------------------------------------------------------
    # Cabeçalho da semana
    # -----------------------------------------------------------------------
    h_meta_display = historico_atual["metadata"] if usando_historico else meta
    n_display      = h_meta_display.get("n_posicoes", n)
    titulo         = "Carteira da semana" + (" anterior" if usando_historico else "")
    proxima_seg    = _proxima_segunda()

    tag_html = ""
    if usando_historico:
        tag_html = (
            "<span class='tag-inline' style='margin-left:14px;'>"
            "Exibindo semana anterior</span>"
        )

    st.markdown(
        f"""
        <div style='display:flex; align-items:flex-end;
                    justify-content:space-between;
                    border-bottom:1px solid #DDD8CE; padding-bottom:14px;
                    margin-bottom:22px; flex-wrap:wrap; gap:14px;'>
          <div>
            <h3 style='margin:0; border-left:none; padding-left:0;'>
              {titulo}{tag_html}
            </h3>
            <div style='font-size:0.85rem; color:#4A4A4A; margin-top:6px;'>
              Vigência {fmt_data_br(h_meta_display.get('data_vigencia_inicio'))}
              → {fmt_data_br(h_meta_display.get('data_vigencia_fim'))}
              · {n_display} posições · peso {100/n_display:.0f}%
            </div>
          </div>
          <div style='text-align:right;'>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A6F4D; font-weight:600;'>
              Próxima reponderação
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              Seg {proxima_seg.strftime('%d/%m/%Y')}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Métricas de destaque (sem emojis)
    # -----------------------------------------------------------------------
    # Carteira teórica composta multi-semanas (todos os históricos cronológicos)
    valor_atual = VALOR_INICIAL_CARTEIRA
    for h in historicos:
        valor_atual *= (1 + h.get("retorno_acumulado_total", 0.0))
    lucro_total = valor_atual - VALOR_INICIAL_CARTEIRA
    ret_acumulado_geral = lucro_total / VALOR_INICIAL_CARTEIRA if VALOR_INICIAL_CARTEIRA else 0

    rets_individuais = [t.get("retorno_acumulado", 0.0) for t in tickers]
    if rets_individuais:
        idx_best  = max(range(len(tickers)), key=lambda i: rets_individuais[i])
        idx_worst = min(range(len(tickers)), key=lambda i: rets_individuais[i])
    else:
        idx_best = idx_worst = None

    mk1, mk2, mk3, mk4 = st.columns(4)
    mk1.metric(
        "Retorno na semana",
        fmt_pct(ret_total, sinal=True),
        help="Retorno agregado ponderado da carteira na semana exibida.",
    )

    # Card "Carteira teórica" renderizado manualmente
    # (Streamlit não parseia sinal dentro de strings tipo "R$-156,82")
    with mk2:
        cor_delta = COLORS["pos"] if lucro_total >= 0 else COLORS["neg"]
        arrow     = "▲" if lucro_total >= 0 else "▼"
        sinal     = "+" if lucro_total >= 0 else "−"
        valor_abs = fmt_reais(abs(lucro_total))
        st.markdown(
            f"""
            <div style='background:#FFFFFF; border:1px solid #DDD8CE;
                        border-radius:2px; padding:18px 22px;
                        height:100%;'>
              <div style='font-size:0.76rem; color:#4A4A4A;
                          text-transform:uppercase; letter-spacing:0.7px;
                          font-weight:500;'
                   title='Valor de uma carteira teórica iniciada com {fmt_reais(VALOR_INICIAL_CARTEIRA)} em {DATA_INICIO_SIMULACAO.strftime("%d/%m/%Y")}, compondo o retorno de todas as semanas registradas. Acumulado: {fmt_pct(ret_acumulado_geral, sinal=True)}.'>
                Carteira teórica
              </div>
              <div style='font-family:"Source Serif Pro",Georgia,serif;
                          font-size:1.95rem; font-weight:600; color:#1A1A1A;
                          margin-top:6px; line-height:1.1;
                          font-feature-settings:"tnum" 1;'>
                {fmt_reais(valor_atual)}
              </div>
              <div style='font-size:0.85rem; color:{cor_delta};
                          font-weight:500; margin-top:6px;
                          font-feature-settings:"tnum" 1;'>
                {arrow} {sinal}{valor_abs}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if idx_best is not None:
        mk3.metric(
            f"Melhor · {tickers[idx_best]['ticker']}",
            fmt_pct(rets_individuais[idx_best], sinal=True),
        )
    if idx_worst is not None:
        mk4.metric(
            f"Pior · {tickers[idx_worst]['ticker']}",
            fmt_pct(rets_individuais[idx_worst], sinal=True),
        )

    # -----------------------------------------------------------------------
    # Tabela de posições (sem coluna Status; com Δ R$ e cores no retorno)
    # -----------------------------------------------------------------------
    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown("### Posições")

    rows = []
    for t in tickers:
        ret = t.get("retorno_acumulado", 0.0)
        ent = t.get("preco_entrada") or 0
        atu = t.get("preco_atual") or 0
        delta_rs = atu - ent if (ent and atu) else None
        rows.append({
            "Ticker":           t["ticker"],
            "Score":            float(t.get("score_na_formacao") or 0),
            "Entrada (R$)":     ent,
            "Atual (R$)":       atu,
            "Δ (R$)":           delta_rs,
            # Retorno multiplicado por 100 — Streamlit NumberColumn não faz isso sozinho
            "Retorno (%)":      ret * 100,
        })

    df_pos = pd.DataFrame(rows)
    st.dataframe(
        df_pos,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ticker": st.column_config.TextColumn(width="small"),
            "Score": st.column_config.NumberColumn(
                "Score",
                help="Score na formação (0–100). "
                     "Composto por 50% Momentum + 30% ROE + 20% CAGR 5a.",
                format="%.1f",
            ),
            "Entrada (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Atual (R$)":   st.column_config.NumberColumn(format="R$ %.2f"),
            "Δ (R$)":       st.column_config.NumberColumn(
                format="R$ %+.2f",
                help="Variação absoluta do preço desde a entrada.",
            ),
            "Retorno (%)":  st.column_config.NumberColumn(
                "Retorno",
                format="%+.2f%%",
                help="Retorno acumulado da posição na semana.",
            ),
        },
    )

    # Como Streamlit não suporta cores condicionais nativas em columns,
    # convertemos a coluna Retorno em string formatada com sinal/percentual.
    # (Já feita via column_config acima.)

    # -----------------------------------------------------------------------
    # Eventos da semana (stops + redistribuição)
    # -----------------------------------------------------------------------
    _render_eventos_semana_live(carteira)

    # -----------------------------------------------------------------------
    # Performance da semana (gráfico + comparação com benchmarks)
    # -----------------------------------------------------------------------
    if performance:
        st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
        st.markdown("### Performance da semana")

        bench_df = _carregar_benchmarks()
        _render_grafico_semana(performance, bench_df, data_corte)

        # Cards de comparação (deltas) — sem repetir a Carteira V2
        b = _calcular_retornos_benchmarks(
            bench_df,
            data_corte,
            performance[-1]["data"],
        )
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "vs IBOV",
            fmt_pct(b["ibov"], sinal=True) if b["ibov"] is not None else "—",
            delta=fmt_pct(ret_total - b["ibov"], sinal=True) if b["ibov"] is not None else None,
            help="Card mostra o retorno do índice na semana; delta é Carteira − Índice.",
        )
        c2.metric(
            "vs SMAL11",
            fmt_pct(b["smll"], sinal=True) if b["smll"] is not None else "—",
            delta=fmt_pct(ret_total - b["smll"], sinal=True) if b["smll"] is not None else None,
        )
        c3.metric(
            "vs CDI",
            fmt_pct(b["cdi"], sinal=True) if b["cdi"] is not None else "—",
            delta=fmt_pct(ret_total - b["cdi"], sinal=True) if b["cdi"] is not None else None,
        )

    # -----------------------------------------------------------------------
    # Histórico semanal
    # -----------------------------------------------------------------------
    if historicos:
        st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
        st.markdown("### Histórico semanal")
        bench_df = _carregar_benchmarks()
        df_hist  = _historico_semanas_resumido(historicos, bench_df)

        # Mostra mais recentes em cima
        df_hist_display = df_hist.iloc[::-1].copy()
        df_hist_display["Vigência"] = df_hist_display.apply(
            lambda r: f"{fmt_data_br(r['vig_inicio'])} → {fmt_data_br(r['vig_fim'])}",
            axis=1,
        )
        # Multiplica por 100 — NumberColumn não converte decimal → percentual
        for col in ("ret", "vs_ibov", "vs_smll", "vs_cdi"):
            df_hist_display[col] = df_hist_display[col].apply(
                lambda v: v * 100 if v is not None else None
            )

        df_hist_display = df_hist_display[
            ["Vigência", "ret", "vs_ibov", "vs_smll", "vs_cdi", "valor"]
        ].rename(columns={
            "ret":     "Retorno",
            "vs_ibov": "vs IBOV",
            "vs_smll": "vs SMAL11",
            "vs_cdi":  "vs CDI",
            "valor":   "Carteira (R$)",
        })

        st.dataframe(
            df_hist_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Vigência": st.column_config.TextColumn(width="medium"),
                "Retorno": st.column_config.NumberColumn(
                    format="%+.2f%%",
                    help="Retorno da semana.",
                ),
                "vs IBOV":   st.column_config.NumberColumn(
                    format="%+.2f%%",
                    help="Delta vs IBOV na semana (Carteira − IBOV).",
                ),
                "vs SMAL11": st.column_config.NumberColumn(format="%+.2f%%"),
                "vs CDI":    st.column_config.NumberColumn(format="%+.2f%%"),
                "Carteira (R$)": st.column_config.NumberColumn(
                    format="R$ %.2f",
                    help=f"Valor cumulativo de uma carteira teórica iniciada "
                         f"com R$ {VALOR_INICIAL_CARTEIRA:.0f} em "
                         f"{DATA_INICIO_SIMULACAO.strftime('%d/%m/%Y')}.",
                ),
            },
        )

    render_footer()
