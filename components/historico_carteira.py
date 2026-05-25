"""Aba Histórico — composição da carteira semana a semana.

Fonte de dados: mescla de
  1. data/backtest_carteiras_v2.json    (104 semanas SIMULADAS)
  2. historico/carteira*.json           (carteiras REAIS do sistema vivo)

Para semanas onde existem AMBAS, a versão REAL tem prioridade — é o que o
sistema vivo de fato formou e onde os retornos são apurados em produção.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date

import pandas as pd
import streamlit as st

import config
from components.footer import render_footer
from components.theme import COLORS
from utils.formatters import fmt_data_br, fmt_pct, fmt_reais


# ---------------------------------------------------------------------------
# Helpers de normalização
# ---------------------------------------------------------------------------

def _iso_week_de_data(data_iso: str) -> str:
    """'2026-05-18' -> '2026-W21'"""
    try:
        d   = date.fromisoformat(data_iso[:10])
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        return ""


def _normalizar_carteira_real(d: dict) -> dict | None:
    """
    Converte o formato de historico/carteira*.json para a estrutura usada
    pelo módulo (mesma do backtest_carteiras_v2.json).

    Retorna None se faltar performance_diaria (carteira ainda sem fechamento).
    """
    if not d.get("performance_diaria"):
        return None
    meta = d.get("metadata", {})
    inicio = meta.get("data_vigencia_inicio") or meta.get("data_formacao")
    if not inicio:
        return None

    return {
        "semana":             _iso_week_de_data(inicio),
        "data_formacao":      meta.get("data_formacao"),
        "data_corte_dados":   meta.get("data_corte_dados"),
        "data_vigencia_fim":  meta.get("data_vigencia_fim"),
        "is_real":            True,                      # marcador
        "retorno_total":      d.get("retorno_acumulado_total"),
        "tickers": [
            {
                "ticker":         t["ticker"],
                "score":          t.get("score_na_formacao"),
                "preco_entrada":  t.get("preco_entrada"),
                "preco_saida":    t.get("preco_atual"),
                "retorno_semana": t.get("retorno_acumulado"),
            }
            for t in d.get("tickers", [])
        ],
    }


# ---------------------------------------------------------------------------
# Carregamento (mesclado: real tem prioridade sobre simulado)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _carregar_carteiras_combinadas() -> dict | None:
    if not config.BACKTEST_V3C_CARTEIRAS_PATH.exists():
        return None
    with open(config.BACKTEST_V3C_CARTEIRAS_PATH, encoding="utf-8") as f:
        bt = json.load(f)

    # Indexa carteiras simuladas por chave 'semana' (ex: '2026-W21')
    carteiras_por_semana: dict[str, dict] = {}
    for c in bt.get("carteiras", []):
        sem = c.get("semana") or _iso_week_de_data(c.get("data_formacao", ""))
        c["is_real"] = False                              # marcador padrão
        if sem:
            carteiras_por_semana[sem] = c

    # Sobrescreve com REAIS (do diretório historico/)
    hist_dir = config.HISTORICO_DIR
    if hist_dir.exists():
        for path in hist_dir.glob("carteira*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                normalizada = _normalizar_carteira_real(raw)
                if normalizada and normalizada["semana"]:
                    carteiras_por_semana[normalizada["semana"]] = normalizada
            except Exception:
                continue

    # Reordena cronologicamente
    carteiras_ordenadas = sorted(
        carteiras_por_semana.values(),
        key=lambda c: c.get("data_formacao") or "",
    )

    return {
        "metadata":  bt.get("metadata", {}),
        "carteiras": carteiras_ordenadas,
    }


# ---------------------------------------------------------------------------
# Estatísticas agregadas
# ---------------------------------------------------------------------------

def _retorno_carteira(c: dict) -> float | None:
    """
    Retorno da semana. Para carteiras REAIS usa o 'retorno_total' já calculado
    pelo sistema (com base na evolução diária da carteira composta).
    Para SIMULADAS, calcula a média equal-weighted dos retornos individuais.
    """
    if c.get("is_real") and c.get("retorno_total") is not None:
        return c["retorno_total"]
    rets = [t.get("retorno_semana") for t in c.get("tickers", [])]
    rets = [r for r in rets if r is not None]
    return sum(rets) / len(rets) if rets else None


def _estatisticas_agregadas(carteiras: list[dict]) -> dict:
    total = len(carteiras)
    rets_sem: list[float] = []
    tickers_set: set[str] = set()

    for c in carteiras:
        r = _retorno_carteira(c)
        if r is not None:
            rets_sem.append(r)
        for t in c.get("tickers", []):
            tickers_set.add(t["ticker"])

    n_pos = sum(1 for r in rets_sem if r >= 0)
    n_neg = sum(1 for r in rets_sem if r < 0)

    return {
        "n_semanas":     total,
        "n_positivas":   n_pos,
        "n_negativas":   n_neg,
        "pct_positivas": n_pos / total if total else 0,
        "tickers_unicos": len(tickers_set),
    }


def _frequencia_tickers(carteiras: list[dict], top_n: int = 10) -> pd.DataFrame:
    """Ranking dos tickers mais frequentes na carteira, com hit rate e retorno médio."""
    contagem: Counter[str]               = Counter()
    rets_por_ticker: dict[str, list[float]] = defaultdict(list)

    for c in carteiras:
        for t in c.get("tickers", []):
            tk = t["ticker"]
            contagem[tk] += 1
            r = t.get("retorno_semana")
            if r is not None:
                rets_por_ticker[tk].append(r)

    rows = []
    for tk, n in contagem.most_common(top_n):
        rets = rets_por_ticker.get(tk, [])
        ret_medio = sum(rets) / len(rets) if rets else None
        hit_rate  = (sum(1 for r in rets if r >= 0) / len(rets)) if rets else None
        rows.append({
            "Ticker":      tk,
            "Aparições":   n,
            "Retorno médio (%)":  ret_medio * 100 if ret_medio is not None else None,
            "Hit rate (%)":       hit_rate  * 100 if hit_rate  is not None else None,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers de rendering
# ---------------------------------------------------------------------------

def _render_cabecalho_editorial(meta: dict, stats: dict) -> None:
    st.markdown(
        f"""
        <div style='display:flex; gap:24px; flex-wrap:wrap;
                    padding:14px 0 22px 0;
                    border-bottom:1px solid #DDD8CE;
                    margin-bottom:28px;'>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Período do histórico
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {fmt_data_br(meta.get("janela_inicio"))}
              → {fmt_data_br(meta.get("janela_fim"))}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Semanas registradas
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {stats["n_semanas"]}
            </div>
          </div>
          <div>
            <div style='font-size:0.7rem; text-transform:uppercase;
                        letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
              Tickers únicos
            </div>
            <div style='font-size:0.95rem; color:#1A1A1A; font-weight:500;
                        margin-top:2px;'>
              {stats["tickers_unicos"]}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_estatisticas(stats: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Semanas positivas",  stats["n_positivas"])
    c2.metric(
        "% semanas positivas",
        fmt_pct(stats["pct_positivas"]),
        help="Fração de semanas em que a carteira fechou no positivo.",
    )
    c3.metric("Semanas negativas", stats["n_negativas"])


def _render_top_tickers(df_freq: pd.DataFrame) -> None:
    if df_freq.empty:
        return
    st.markdown("### Tickers mais frequentes")
    st.dataframe(
        df_freq,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ticker":            st.column_config.TextColumn(width="small"),
            "Aparições":         st.column_config.NumberColumn(
                format="%d",
                help="Número de semanas em que o ticker entrou no Top 5.",
            ),
            "Retorno médio (%)": st.column_config.NumberColumn(
                "Retorno médio",
                format="%+.2f%%",
                help="Retorno médio do ticker considerando todas as semanas em que esteve na carteira.",
            ),
            "Hit rate (%)": st.column_config.NumberColumn(
                "Hit rate",
                format="%.1f%%",
                help="Percentual de semanas em que o ticker fechou positivo.",
            ),
        },
    )


def _construir_tabela_master(carteiras: list[dict]) -> pd.DataFrame:
    """Tabela mestra: 1 linha por semana, ordem mais recente primeiro."""
    rows = []
    for c in carteiras:
        tickers = c.get("tickers", [])
        ret_semana = _retorno_carteira(c)

        rets = [(t["ticker"], t.get("retorno_semana")) for t in tickers]
        rets_validos = [(tk, r) for tk, r in rets if r is not None]
        if rets_validos:
            tk_best, ret_best   = max(rets_validos, key=lambda x: x[1])
            tk_worst, ret_worst = min(rets_validos, key=lambda x: x[1])
        else:
            tk_best = tk_worst = "—"
            ret_best = ret_worst = None

        composicao = " · ".join(t["ticker"] for t in tickers)

        rows.append({
            "Semana":     c.get("semana", "—"),
            "Origem":     "Real" if c.get("is_real") else "Simulada",
            "Vigência":   f"{fmt_data_br(c.get('data_formacao'))} → {fmt_data_br(c.get('data_vigencia_fim'))}",
            "Retorno (%)":   ret_semana * 100 if ret_semana is not None else None,
            "Melhor":     f"{tk_best} ({ret_best*100:+.2f}%)" if ret_best is not None else "—",
            "Pior":       f"{tk_worst} ({ret_worst*100:+.2f}%)" if ret_worst is not None else "—",
            "Composição": composicao,
        })

    df = pd.DataFrame(rows)
    # mais recente primeiro
    return df.iloc[::-1].reset_index(drop=True)


def _render_composicao_detalhada(carteira: dict) -> None:
    """Drill-down: detalhe da semana selecionada com tickers, preços e retornos."""
    sem    = carteira.get("semana", "—")
    vig    = f"{fmt_data_br(carteira.get('data_formacao'))} → {fmt_data_br(carteira.get('data_vigencia_fim'))}"
    tickers = carteira.get("tickers", [])
    ret_semana = _retorno_carteira(carteira)
    origem = "Carteira real do sistema vivo" if carteira.get("is_real") else "Simulação do backtest"

    cor_ret = COLORS["pos"] if (ret_semana or 0) >= 0 else COLORS["neg"]

    st.markdown(
        f"""
        <div style='background:#FFFFFF; border:1px solid #DDD8CE;
                    border-radius:2px; padding:22px 26px;
                    margin-top:18px;'>
          <div style='display:flex; justify-content:space-between;
                      align-items:flex-end; flex-wrap:wrap; gap:12px;
                      margin-bottom:18px;'>
            <div>
              <div style='font-size:0.72rem; text-transform:uppercase;
                          letter-spacing:1px; color:#A89968; font-weight:600;'>
                Semana {sem} · {origem}
              </div>
              <div style='font-family:"Source Serif Pro",Georgia,serif;
                          font-size:1.4rem; font-weight:600; color:#1B365D;
                          margin-top:2px; line-height:1.1;'>
                Composição detalhada
              </div>
              <div style='font-size:0.88rem; color:#4A4A4A; margin-top:6px;'>
                Vigência {vig}
              </div>
            </div>
            <div style='text-align:right;'>
              <div style='font-size:0.7rem; text-transform:uppercase;
                          letter-spacing:0.9px; color:#7A7A7A; font-weight:500;'>
                Retorno da semana
              </div>
              <div style='font-family:"Source Serif Pro",Georgia,serif;
                          font-size:1.55rem; font-weight:600; color:{cor_ret};
                          margin-top:2px; line-height:1.1;
                          font-feature-settings:"tnum" 1;'>
                {fmt_pct(ret_semana, sinal=True) if ret_semana is not None else "—"}
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tabela detalhada de tickers
    rows = []
    for t in tickers:
        ent = t.get("preco_entrada")
        sai = t.get("preco_saida")
        delta_rs = (sai - ent) if (ent is not None and sai is not None) else None
        rows.append({
            "Ticker":      t["ticker"],
            "Score":       t.get("score"),
            "Entrada (R$)": ent,
            "Saída (R$)":   sai,
            "Δ (R$)":       delta_rs,
            "Retorno (%)":  t["retorno_semana"] * 100 if t.get("retorno_semana") is not None else None,
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Ticker":       st.column_config.TextColumn(width="small"),
            "Score":        st.column_config.NumberColumn(format="%.1f"),
            "Entrada (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Saída (R$)":   st.column_config.NumberColumn(format="R$ %.2f"),
            "Δ (R$)":       st.column_config.NumberColumn(format="R$ %+.2f"),
            "Retorno (%)":  st.column_config.NumberColumn(
                "Retorno",
                format="%+.2f%%",
            ),
        },
    )


# ---------------------------------------------------------------------------
# Render principal
# ---------------------------------------------------------------------------

def render_aba_historico_carteira() -> None:
    bt = _carregar_carteiras_combinadas()

    if bt is None or not bt.get("carteiras"):
        st.warning(
            "Histórico de carteiras ainda não gerado. "
            "Execute `python run_v2.py --fase 4` primeiro."
        )
        render_footer()
        return

    meta      = bt.get("metadata", {})
    carteiras = bt["carteiras"]
    stats     = _estatisticas_agregadas(carteiras)

    # Cabeçalho + estatísticas
    _render_cabecalho_editorial(meta, stats)
    _render_estatisticas(stats)

    # Top tickers (10 mais frequentes)
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    df_freq = _frequencia_tickers(carteiras, top_n=10)
    _render_top_tickers(df_freq)

    # Filtros (inline acima da tabela)
    st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)
    st.markdown("### Composição semana a semana")

    fc1, fc2, fc3 = st.columns([2, 2, 1])
    busca = fc1.text_input(
        "Buscar ticker",
        placeholder="ex: INTB3",
        help="Filtra semanas em que o ticker apareceu na carteira.",
    ).strip().upper()
    filtro_periodo = fc2.selectbox(
        "Período",
        options=["Tudo", "Últimos 3 meses", "Últimos 6 meses", "Último ano"],
        index=0,
    )
    apenas_pos = fc3.toggle("Só positivas", value=False)

    # Aplica filtros
    carteiras_filtradas = list(carteiras)
    if busca:
        carteiras_filtradas = [
            c for c in carteiras_filtradas
            if any(t["ticker"].upper() == busca for t in c.get("tickers", []))
        ]
    if filtro_periodo != "Tudo":
        n_map = {"Últimos 3 meses": 13, "Últimos 6 meses": 26, "Último ano": 52}
        carteiras_filtradas = carteiras_filtradas[-n_map[filtro_periodo]:]
    if apenas_pos:
        carteiras_filtradas = [
            c for c in carteiras_filtradas
            if (_retorno_carteira(c) or 0) >= 0
        ]

    if not carteiras_filtradas:
        st.info("Nenhuma semana encontrada com os filtros aplicados.")
        render_footer()
        return

    # Tabela master com drill-down nativo do Streamlit
    df_master = _construir_tabela_master(carteiras_filtradas)

    event = st.dataframe(
        df_master,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Semana":     st.column_config.TextColumn(width="small"),
            "Origem":     st.column_config.TextColumn(
                width="small",
                help="'Real' = carteira formada pelo sistema vivo "
                     "(prioritária quando existe). "
                     "'Simulada' = carteira reconstruída pelo backtest.",
            ),
            "Vigência":   st.column_config.TextColumn(width="medium"),
            "Retorno (%)": st.column_config.NumberColumn(
                "Retorno",
                format="%+.2f%%",
                help="Retorno da carteira na semana. Para carteiras reais usa "
                     "o retorno apurado pelo sistema; para simuladas, média "
                     "equal-weighted dos 5 ativos.",
            ),
            "Melhor":     st.column_config.TextColumn(),
            "Pior":       st.column_config.TextColumn(),
            "Composição": st.column_config.TextColumn(
                "Tickers da semana",
                width="large",
                help="Lista dos 5 tickers da semana (ordem por score).",
            ),
        },
    )

    # Drill-down
    if event and event.selection.rows:
        idx_filtrado = event.selection.rows[0]
        # df_master está em ordem invertida (mais recente em cima)
        # carteiras_filtradas está em ordem cronológica
        carteira_sel = carteiras_filtradas[::-1][idx_filtrado]
        _render_composicao_detalhada(carteira_sel)
    else:
        st.markdown(
            "<div style='font-size:0.85rem; color:#7A7A7A; margin-top:14px;'>"
            "Selecione uma linha na tabela acima para ver a composição detalhada."
            "</div>",
            unsafe_allow_html=True,
        )

    render_footer()
