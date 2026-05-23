# PHASE 5 SPEC — Frontend (Streamlit App)

> **Versão:** 1.0
> **Data:** 22/05/2026
> **Status:** Fase 5 fechada. Pronto para implementação.
> **Depende de:** `PROJECT_SPEC.md`, `PHASE1_SPEC.md`, `PHASE2_SPEC.md`, `PHASE3_SPEC.md`, `PHASE4_SPEC.md`

---

## 1. Objetivo da fase

Construir a interface visual do sistema: um app Streamlit com 3 abas que consome os artefatos JSON/Parquet gerados pelas fases anteriores e os apresenta de forma clara, honesta e funcional.

**Em uma frase:** transformar os dados calculados pelo backend em uma interface navegável que mostra a carteira da semana, o ranking das 50 ações e o histórico de backtest.

---

## 2. Stack e decisões estruturantes

| Decisão | Escolha |
|---|---|
| Stack | **Streamlit** (Python puro, sem JS/HTML separado) |
| Estrutura | **3 abas:** Carteira \| Ranking \| Backtest |
| Gráficos | **Altair** (declarativo, integrado nativo no Streamlit) |
| Responsividade | **Desktop-first** (Streamlit default, sem esforço extra de responsividade) |
| Sidebar | **Presente** — filtro de período no backtest (3m / 6m / 1a / 2a) |
| Disclaimer | **Rodapé fixo** — visível em todas as abas |
| Tabela histórica backtest | **Não exibida** — só equity curve + métricas agregadas |
| Ranking | **Tabela com breakdown expansível** por linha (fatores A/B/C/D) |

### 2.1 Trade-off honesto (Streamlit)
- ✅ Deploy simples, tudo Python, sem JSON rendering manual
- ✅ Altair já integrado (`st.altair_chart`)
- ❌ Não é uma página estática — precisa de servidor rodando (impacta Fase 6)
- ❌ Visual limitado comparado a React/Next.js
- ❌ Streamlit tem opiniões fortes sobre layout (workarounds com `st.columns`, `st.expander`)

---

## 3. Estrutura geral do app

```
app.py
│
├── Header global
│   ├── Título: "Small Cap Momentum Tracker"
│   └── Badge de status da última atualização (last_run_summary.json)
│
├── Sidebar
│   └── Filtro de período do backtest: [3m | 6m | 1a | 2a]
│       (visível em todas as abas, só tem efeito na aba Backtest)
│
├── Aba 1 — Carteira
├── Aba 2 — Ranking
├── Aba 3 — Backtest
│
└── Rodapé fixo (disclaimer)
```

---

## 4. Header global

### 4.1 Título e subtítulo
```
Small Cap Momentum Tracker
Universo: 50 small caps brasileiras | Carteira teórica semanal Top 5
```

### 4.2 Badge de status
- Lê `data/last_run_summary.json`
- Se `status == "success"`: `✅ Atualizado em 22/05/2026 às 18:00`
- Se `status == "degraded"`: `⚠️ Atualização parcial — 22/05/2026 às 18:00`
- Se `status == "failed"`: `🔴 Falha na última atualização — verificar logs`
- Se arquivo não existe: `⚪ Dados ainda não carregados`

### 4.3 Implementação
```python
import streamlit as st
import json

def render_header():
    st.title("Small Cap Momentum Tracker")
    st.caption("Universo: 50 small caps brasileiras | Carteira teórica semanal Top 5")
    
    try:
        with open("data/last_run_summary.json") as f:
            summary = json.load(f)
        status = summary.get("status", "unknown")
        ts = summary.get("timestamp", "")[:16].replace("T", " às ")
        
        if status == "success":
            st.success(f"✅ Atualizado em {ts}")
        elif status == "degraded":
            st.warning(f"⚠️ Atualização parcial — {ts}")
        elif status == "failed":
            st.error(f"🔴 Falha na última atualização — {ts}")
    except FileNotFoundError:
        st.info("⚪ Dados ainda não carregados")
```

---

## 5. Aba 1 — Carteira

### 5.1 Fonte de dados
- `data/carteira_atual.json` (Fase 3)

### 5.2 Layout da aba

```
[Badge bootstrap, se aplicável]
[Alerta de carteira incompleta, se aplicável]

━━ Carteira da semana ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Formada em: 19/05/2026 | Vigência: 19/05 → 23/05/2026
Posições: 5 | Peso por posição: 20%

┌─────────────────────────────────────────────────┐
│ Tabela: Ticker | Score | Retorno acumulado | STALE │
└─────────────────────────────────────────────────┘

━━ Performance acumulada da semana ━━━━━━━━━━━━━━━━
[Gráfico de linha: Carteira vs IBOV vs SMLL vs CDI]

━━ Performance numérica ━━━━━━━━━━━━━━━━━━━━━━━━━━
[4 métricas: retorno carteira | vs IBOV | vs SMLL | vs CDI]
```

### 5.3 Badges e alertas condicionais

**Badge bootstrap** (quando `bootstrap_retroativo == true`):
```python
st.info("🔄 Carteira retroativa de bootstrap — formada com dados anteriores a [data_corte]. "
        "Próxima carteira oficial: [proxima_segunda].")
```

**Alerta carteira incompleta** (quando `n_posicoes < 5`):
```python
st.warning(f"⚠️ Apenas {n} ações passaram no filtro de tendência esta semana. "
           f"Peso por posição: {100/n:.1f}%")
```

**Alerta carteira vazia** (quando `n_posicoes == 0`):
```python
st.error("🚫 Nenhuma ação atendeu ao filtro de tendência esta semana. Sem recomendação.")
```

### 5.4 Tabela de posições

Colunas: `Ticker` | `Score` | `Retorno Acumulado` | `Status`

- `Retorno Acumulado`: formatado como `+3,6%` (verde) ou `-1,2%` (vermelho)
- `Status`: `✅ Ativo` ou `⚠️ Stale` (quando `is_stale == true`)
- Ordenada por `rank_na_formacao`

```python
import pandas as pd

def render_tabela_carteira(tickers):
    rows = []
    for t in tickers:
        ret = t["retorno_acumulado"]
        ret_str = f"+{ret*100:.1f}%" if ret >= 0 else f"{ret*100:.1f}%"
        status = "⚠️ Stale" if t.get("is_stale") else "✅ Ativo"
        rows.append({
            "Ticker": t["ticker"],
            "Score": f"{t['score_na_formacao']:.1f}",
            "Retorno Acumulado": ret_str,
            "Status": status
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
```

### 5.5 Gráfico de performance acumulada

- **Tipo:** linha (Altair `mark_line`)
- **X:** data do pregão
- **Y:** retorno acumulado (eixo em %)
- **Séries:** Carteira (destaque) + IBOV + SMLL + CDI
- **Tooltip:** hover mostra data + retorno de cada série
- **Linha de base:** 0% tracejada

```python
import altair as alt

def render_grafico_performance(performance_diaria):
    # Montar DataFrame long-format
    # Colunas: data, serie, retorno_acumulado
    chart = alt.Chart(df).mark_line().encode(
        x=alt.X("data:T", title="Data"),
        y=alt.Y("retorno_acumulado:Q", title="Retorno acumulado (%)",
                axis=alt.Axis(format=".1%")),
        color=alt.Color("serie:N", 
                        scale=alt.Scale(
                            domain=["Carteira", "IBOV", "SMLL", "CDI"],
                            range=["#2563eb", "#6b7280", "#9ca3af", "#d1d5db"]
                        )),
        strokeWidth=alt.condition(
            alt.datum.serie == "Carteira",
            alt.value(3), alt.value(1.5)
        ),
        tooltip=["data:T", "serie:N", 
                 alt.Tooltip("retorno_acumulado:Q", format=".2%")]
    ).properties(height=300)
    
    baseline = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        strokeDash=[4, 4], color="gray", opacity=0.5
    ).encode(y="y:Q")
    
    st.altair_chart(chart + baseline, use_container_width=True)
```

### 5.6 Métricas numéricas

4 `st.metric` lado a lado (usando `st.columns(4)`):
- **Carteira:** retorno acumulado da semana
- **vs IBOV:** diferença vs IBOV (delta colorido)
- **vs SMLL:** diferença vs SMLL
- **vs CDI:** diferença vs CDI

```python
col1, col2, col3, col4 = st.columns(4)
col1.metric("Carteira", f"{ret_carteira*100:.2f}%")
col2.metric("vs IBOV", f"{ret_carteira*100:.2f}%", 
            delta=f"{(ret_carteira - ret_ibov)*100:.2f}%")
# etc.
```

---

## 6. Aba 2 — Ranking

### 6.1 Fonte de dados
- `data/scores_atual.json` (Fase 3)

### 6.2 Layout da aba

```
Data de referência: 22/05/2026

[Tabela principal: Rank | Ticker | Score | Tendência | Na Carteira]

[Expansor por linha: fatores A/B/C/D com valores brutos e normalizados]
```

### 6.3 Tabela principal

Colunas:
- `Rank` — posição 1-50
- `Ticker` — ticker B3
- `Score Final` — 0-100 com 1 casa decimal
- `Tendência` — `🟢🟢🟢` / `🟢🟢⬜` / `🟢⬜⬜` / `⬜⬜⬜` (3 bolinhas representando os 3 critérios MMA)
- `Na Carteira` — `⭐` se está nas Top 5 da carteira atual, vazio caso contrário
- `Passou Filtro` — `✅` se `passou_filtro_tendencia == true`, `❌` se não

```python
def render_tendencia(fatores):
    tend = fatores["tendencia"]
    p1 = "🟢" if tend["preco_acima_mma50"] else "⬜"
    p2 = "🟢" if tend["preco_acima_mma200"] else "⬜"
    p3 = "🟢" if tend["mma50_acima_mma200"] else "⬜"
    return f"{p1}{p2}{p3}"
```

### 6.4 Breakdown expansível por ação

Implementado com `st.expander` por linha — ou, mais praticamente, com uma tabela selecionável + `st.expander` abaixo mostrando o breakdown da linha selecionada.

**Abordagem recomendada (Streamlit-friendly):**

```python
# Tabela principal com st.dataframe (selecionável)
event = st.dataframe(df_ranking, on_select="rerun", selection_mode="single-row")

# Breakdown da linha selecionada
if event.selection.rows:
    idx = event.selection.rows[0]
    ticker_selecionado = scores[idx]
    
    with st.expander(f"📊 Breakdown — {ticker_selecionado['ticker']}", expanded=True):
        render_breakdown(ticker_selecionado)
```

**Conteúdo do breakdown:**

```
┌─────────────────────────────────────────────────────────────────┐
│ CEAB3 — Score: 87.3                                             │
│                                                                 │
│ A) Momentum (peso 35%)      Bruto: +16,5%   Norm: 92.0   → 32.2│
│    ret 1m: +8,2%  ret 3m: +12,5%  ret 6m: +28,9%              │
│                                                                 │
│ B) Tendência (peso 30%)     Bruto: 3/3       Norm: 100.0  → 30.0│
│    P>MMA50: ✅  P>MMA200: ✅  MMA50>MMA200: ✅                  │
│    Preço: R$12,85 | MMA50: R$11,42 | MMA200: R$9,87            │
│                                                                 │
│ C) ROIC (peso 20%)          Bruto: 16,9%    Norm: 78.0   → 15.6│
│                                                                 │
│ D) CAGR Receita 5a (peso 15%) Bruto: 14,3%  Norm: 63.5  → 9.5 │
└─────────────────────────────────────────────────────────────────┘
```

```python
def render_breakdown(ticker_data):
    fat = ticker_data["fatores"]
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("**A) Momentum (35%)**")
        mom = fat["momentum"]
        st.write(f"ret 1m: {mom['ret_1m']*100:.1f}% | "
                 f"ret 3m: {mom['ret_3m']*100:.1f}% | "
                 f"ret 6m: {mom['ret_6m']*100:.1f}%")
        st.write(f"Bruto: {mom['bruto']*100:.1f}% → "
                 f"Norm: {mom['normalizado']:.0f} → "
                 f"Contribuição: {mom['contribuicao_score']:.1f}")
        
        st.markdown("**C) ROIC (20%)**")
        roic = fat["roic"]
        missing_str = " *(missing — usando mediana)*" if roic["is_missing"] else ""
        st.write(f"Bruto: {roic['bruto']:.1f}%{missing_str} → "
                 f"Norm: {roic['normalizado']:.0f} → "
                 f"Contribuição: {roic['contribuicao_score']:.1f}")
    
    with col_b:
        st.markdown("**B) Tendência (30%)**")
        tend = fat["tendencia"]
        p1 = "✅" if tend["preco_acima_mma50"] else "❌"
        p2 = "✅" if tend["preco_acima_mma200"] else "❌"
        p3 = "✅" if tend["mma50_acima_mma200"] else "❌"
        st.write(f"P>MMA50: {p1}  P>MMA200: {p2}  MMA50>MMA200: {p3}")
        st.write(f"Preço: R${tend['preco_atual']:.2f} | "
                 f"MMA50: R${tend['mma_50']:.2f} | "
                 f"MMA200: R${tend['mma_200']:.2f}")
        st.write(f"Bruto: {tend['bruto']}/3 → "
                 f"Norm: {tend['normalizado']:.0f} → "
                 f"Contribuição: {tend['contribuicao_score']:.1f}")
        
        st.markdown("**D) CAGR Receita 5a (15%)**")
        cagr = fat["cagr_receita"]
        missing_str = " *(missing — usando mediana)*" if cagr["is_missing"] else ""
        st.write(f"Bruto: {cagr['bruto']:.1f}%{missing_str} → "
                 f"Norm: {cagr['normalizado']:.0f} → "
                 f"Contribuição: {cagr['contribuicao_score']:.1f}")
```

---

## 7. Aba 3 — Backtest

### 7.1 Fonte de dados
- `data/backtest_resultado.json` (Fase 4)
- Filtro de período: sidebar (`periodo_backtest` = `3m` / `6m` / `1a` / `2a`)

### 7.2 Layout da aba

```
Período selecionado: Últimos 2 anos (104 semanas)

━━ Métricas principais ━━━━━━━━━━━━━━━━━━━━━━━━━━━
[6 cards: retorno anual | vol | Sharpe | max DD | win rate | hit vs SMLL]

━━ Comparação com benchmarks ━━━━━━━━━━━━━━━━━━━━━
[3 cards: Alpha vs IBOV | Alpha vs SMLL | Alpha vs CDI]

━━ Equity curve ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Gráfico de linha: Estratégia vs IBOV vs SMLL vs CDI]

━━ Drawdown ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Gráfico de área: drawdown da estratégia ao longo do tempo]

[⚠️ Aviso de limitações (inline, colapsável)]
```

### 7.3 Sidebar — filtro de período

```python
with st.sidebar:
    st.header("Configurações")
    periodo = st.radio(
        "Período do backtest",
        options=["3m", "6m", "1a", "2a"],
        index=3,  # default: 2a
        format_func=lambda x: {
            "3m": "Últimos 3 meses",
            "6m": "Últimos 6 meses", 
            "1a": "Último ano",
            "2a": "2 anos completos"
        }[x]
    )
```

Filtro aplicado sobre `equity_curve[]` — corta a lista pelo número de semanas correspondente ao período selecionado.

### 7.4 Cards de métricas

**Linha 1 — Risco/retorno (6 colunas):**

| Card | Valor | Delta |
|---|---|---|
| Retorno anualizado | 20,5% | — |
| Volatilidade anual | 28,1% | — |
| Sharpe Ratio | 0,65 | — |
| Max Drawdown | -18,3% | — |
| Win Rate semanal | 57% | — |
| Hit Rate vs SMLL | 54% | — |

**Linha 2 — Alphas (3 colunas):**

| Card | Valor |
|---|---|
| Alpha vs IBOV | +11,7% a.a. |
| Alpha vs SMLL | +8,2% a.a. |
| Alpha vs CDI | +9,5% a.a. |

```python
def render_metricas(metricas, metricas_bench, alphas):
    cols = st.columns(6)
    cols[0].metric("Retorno a.a.", f"{metricas['retorno_anualizado']*100:.1f}%")
    cols[1].metric("Volatilidade a.a.", f"{metricas['volatilidade_anualizada']*100:.1f}%")
    cols[2].metric("Sharpe", f"{metricas['sharpe_ratio']:.2f}")
    cols[3].metric("Max Drawdown", f"{metricas['max_drawdown']*100:.1f}%")
    cols[4].metric("Win Rate", f"{metricas['win_rate_semanal']*100:.0f}%")
    cols[5].metric("Hit vs SMLL", f"{metricas['hit_rate_vs_smll']*100:.0f}%")
    
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("Alpha vs IBOV", f"+{alphas['vs_ibov']*100:.1f}%")
    col2.metric("Alpha vs SMLL", f"+{alphas['vs_smll']*100:.1f}%")
    col3.metric("Alpha vs CDI", f"+{alphas['vs_cdi']*100:.1f}%")
```

### 7.5 Equity curve

- **Tipo:** linha (Altair `mark_line`)
- **X:** semana (data)
- **Y:** valor base 100 (começa em 100, reflete crescimento acumulado)
- **Séries:** Estratégia (destaque) + IBOV + SMLL + CDI
- **Filtrado** pelo período selecionado na sidebar

```python
def render_equity_curve(equity_curve, periodo):
    df = pd.DataFrame(equity_curve)
    df["data"] = pd.to_datetime(df["data"])
    
    # Filtrar por período
    n_semanas = {"3m": 13, "6m": 26, "1a": 52, "2a": 104}[periodo]
    df = df.tail(n_semanas).copy()
    
    # Long format
    df_long = df.melt(
        id_vars="data",
        value_vars=["valor_estrategia", "valor_ibov", "valor_smll", "valor_cdi"],
        var_name="serie", value_name="valor"
    )
    label_map = {
        "valor_estrategia": "Estratégia",
        "valor_ibov": "IBOV",
        "valor_smll": "SMLL",
        "valor_cdi": "CDI"
    }
    df_long["serie"] = df_long["serie"].map(label_map)
    
    chart = alt.Chart(df_long).mark_line().encode(
        x=alt.X("data:T", title=""),
        y=alt.Y("valor:Q", title="Valor (base 100)"),
        color=alt.Color("serie:N",
                        scale=alt.Scale(
                            domain=["Estratégia", "IBOV", "SMLL", "CDI"],
                            range=["#2563eb", "#6b7280", "#9ca3af", "#d1d5db"]
                        )),
        strokeWidth=alt.condition(
            alt.datum.serie == "Estratégia",
            alt.value(3), alt.value(1.5)
        ),
        tooltip=["data:T", "serie:N",
                 alt.Tooltip("valor:Q", format=".1f")]
    ).properties(height=350, title="Equity Curve — Base 100")
    
    st.altair_chart(chart, use_container_width=True)
```

### 7.6 Gráfico de drawdown

- **Tipo:** área (Altair `mark_area`) com cor vermelha semitransparente
- **X:** semana
- **Y:** drawdown da estratégia (negativo, 0 = sem drawdown)
- **Filtrado** pelo mesmo período

```python
def render_drawdown(equity_curve, periodo):
    df = pd.DataFrame(equity_curve)
    df["data"] = pd.to_datetime(df["data"])
    n_semanas = {"3m": 13, "6m": 26, "1a": 52, "2a": 104}[periodo]
    df = df.tail(n_semanas).copy()
    
    # Calcular drawdown da estratégia
    rolling_max = df["valor_estrategia"].cummax()
    df["drawdown"] = df["valor_estrategia"] / rolling_max - 1
    
    chart = alt.Chart(df).mark_area(
        color="#ef4444", opacity=0.4, line={"color": "#ef4444"}
    ).encode(
        x=alt.X("data:T", title=""),
        y=alt.Y("drawdown:Q", title="Drawdown", axis=alt.Axis(format=".0%")),
        tooltip=["data:T", alt.Tooltip("drawdown:Q", format=".1%")]
    ).properties(height=180, title="Drawdown da Estratégia")
    
    st.altair_chart(chart, use_container_width=True)
```

### 7.7 Aviso de limitações (inline, colapsável)

```python
with st.expander("⚠️ Limitações do backtest (importante ler)", expanded=False):
    st.markdown("""
    **Este backtest possui vieses conhecidos que podem inflar os resultados:**
    
    - **Survivorship bias:** o universo usa os 50 tickers *atuais*. Ações que 
      foram deslistadas ou entraram em recuperação judicial no período histórico 
      não aparecem — o que tende a inflar os retornos.
    
    - **Zero custos:** sem corretagem, sem slippage, sem impostos. 
      Estimativa de impacto: ~1,35%/ano no retorno bruto.
    
    - **Universo fixo:** o mesmo universo de maio/2026 é usado para todas as 
      ~104 semanas. O universo real variaria ao longo do tempo.
    
    - **Janela curta:** 2 anos têm significância estatística limitada.
    
    **Backtest não é garantia de retorno futuro.**
    """)
```

---

## 8. Rodapé fixo (disclaimer)

```python
def render_footer():
    st.divider()
    st.caption(
        "⚠️ **Disclaimer:** Este sistema é uma ferramenta de estudo pessoal. "
        "**Não constitui recomendação de investimento.** "
        "Os scores e carteiras são modelos quantitativos experimentais, "
        "sem garantia de retorno. Backtest possui survivorship bias e assume "
        "zero custos de transação. Invista com responsabilidade."
    )
```

Posicionado após o conteúdo de cada aba (Streamlit não suporta rodapé global nativo — replicar em cada aba ou usar hack de `st.empty()` com CSS).

---

## 9. Tratamento de estados de erro e ausência de dados

| Situação | Comportamento |
|---|---|
| `carteira_atual.json` não existe | `st.error("Carteira ainda não gerada. Execute o pipeline.")` |
| `scores_atual.json` não existe | `st.error("Scores ainda não calculados. Execute o pipeline.")` |
| `backtest_resultado.json` não existe | `st.warning("Backtest ainda não gerado. Execute scoring + backtest.")` |
| `carteira_atual.json` com `n_posicoes == 0` | Alerta vermelho, sem tabela de posições |
| Ticker STALE na carteira | Badge `⚠️ Stale` na coluna Status da tabela |
| Backtest com período selecionado > dados disponíveis | Usa todos os dados disponíveis + aviso |

---

## 10. Estrutura de arquivos da Fase 5

```
projeto/
├── app.py                          ← app Streamlit principal
├── components/
│   ├── header.py                   ← render_header()
│   ├── carteira.py                 ← render_aba_carteira()
│   ├── ranking.py                  ← render_aba_ranking(), render_breakdown()
│   ├── backtest.py                 ← render_aba_backtest()
│   └── footer.py                   ← render_footer()
├── utils/
│   └── formatters.py               ← helpers de formatação (%, R$, datas)
├── data/                           ← artefatos gerados pelas Fases 1-4
│   ├── scores_atual.json
│   ├── carteira_atual.json
│   ├── backtest_resultado.json
│   └── last_run_summary.json
└── requirements.txt                ← streamlit, altair, pandas
```

---

## 11. Dependências

```
# requirements.txt (acréscimos da Fase 5)
streamlit>=1.35.0
altair>=5.3.0
pandas>=2.0.0
```

---

## 12. Entregáveis da Fase 5 (a implementar)

1. **`app.py`** — entrada do app, monta abas e chama componentes
2. **`components/header.py`** — badge de status + título
3. **`components/carteira.py`** — aba Carteira completa
4. **`components/ranking.py`** — aba Ranking completa (tabela + breakdown)
5. **`components/backtest.py`** — aba Backtest (métricas + gráficos)
6. **`components/footer.py`** — disclaimer fixo
7. **`utils/formatters.py`** — funções utilitárias de formatação

---

## 13. Decisões da Fase 5 (registro histórico)

| Decisão | Escolha | Alternativas consideradas |
|---|---|---|
| Stack | S2 — Streamlit | S1 HTML/JS puro; S3 Next.js/React |
| Estrutura | P2 — 3 abas (Carteira \| Ranking \| Backtest) | P1 single-page scroll; P3 páginas separadas |
| Gráficos | G2 — Altair | G1 Plotly; G3 Matplotlib |
| Responsividade | M1 — Desktop-first | M2 responsive básico |
| Ranking | R2 — Tabela com breakdown expansível | R1 tabela simples; R3 colunas fixas |
| Disclaimer | D1 — Rodapé fixo | D2 colapsável no topo; D3 só na aba Backtest |
| Tabela histórica backtest | B3 — Não exibir | B1 paginada; B2 scroll |
| Sidebar | A1 — Filtro de período no backtest | A2 sem sidebar |

---

## 14. Interface com outras fases

### 14.1 O que a Fase 5 consome
- `data/scores_atual.json` (Fase 3)
- `data/carteira_atual.json` (Fase 3)
- `data/backtest_resultado.json` (Fase 4)
- `data/last_run_summary.json` (Fase 2)

### 14.2 O que a Fase 5 precisa da Fase 6
- Servidor onde o app Streamlit roda continuamente
- Trigger que re-executa o pipeline e o Streamlit vê os dados atualizados automaticamente (Streamlit faz polling/auto-reload dos arquivos JSON)

---

## 15. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| `st.dataframe` com seleção de linha não disponível em versão antiga do Streamlit | Média | Médio | Usar `st.dataframe(on_select=...)` — requer Streamlit ≥ 1.35; fixar versão no requirements |
| Altair sem suporte a `strokeWidth` condicional em versão antiga | Baixa | Baixo | Usar `alt.condition` — disponível desde Altair 4.x |
| Rodapé fixo no Streamlit | Alta (limitação nativa) | Baixo | Replicar `render_footer()` no final de cada aba |
| Dados desatualizados não refletem no app sem restart | Média | Médio | Streamlit recarrega arquivos JSON a cada interação do usuário por padrão; usar `@st.cache_data(ttl=300)` com TTL de 5 min |
| Breakdown expansível lento com 50 linhas | Baixa | Baixo | Carregar breakdown só quando linha selecionada |

---

## 16. Itens em aberto (para Fase 6)

- **Fase 6:** onde o app Streamlit é hospedado (Streamlit Community Cloud, VPS, Render.com)
- **Fase 6:** como o pipeline backend (Fases 1-4) é agendado e aciona atualização dos JSONs
- **Fase 6:** autenticação (app público ou protegido por senha no Streamlit)
- **Fase 7:** aba ou seção adicional de monitoramento contínuo (performance real acumulada histórica)
