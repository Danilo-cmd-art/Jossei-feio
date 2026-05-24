# Planejamento estratégico — Histórico da carteira (semana a semana)

## 1. Problema

Hoje o usuário só vê:
- **Carteira**: a semana corrente (ou a anterior via bootstrap) + 1 linha resumo no "Histórico semanal" (sem composição).
- **Backtest**: métricas agregadas + curva de retorno acumulado.

**Falta**: a capacidade de **explorar a composição da carteira semana a semana** —
quais 5 ações foram escolhidas em cada semana das 104 simuladas, com seus
scores, preços de entrada/saída e retorno individual.

---

## 2. Decisão de UX: aba separada vs. embutir no Backtest

### Critérios

| Critério | Embutir no Backtest | Aba separada "Histórico" |
|---|---|---|
| Coerência conceitual | Backtest é macro (curva/métricas). Misturar 104 carteiras × 5 tickers polui. | Aba dedicada deixa Backtest enxuto e dá espaço pra exploração detalhada. |
| Tempo de carregamento | Backtest ficaria pesado (520 linhas + drill-down). | Lazy: só carrega quando o usuário abre a aba. |
| Intenção de uso | "Como está performando?" | "O que a estratégia comprou em X data?" |
| Padrão de mercado (Goldman, BlackRock, etc.) | Reports de fundos sempre separam **holdings history** de **performance** | ✓ |
| Espaço para crescer | Limitado. | Permite adicionar filtros, exports, análises agregadas. |

### **Decisão**: **NOVA aba "Histórico"** (terceira aba, depois de Carteira e Backtest).

---

## 3. Fontes de dados

| Arquivo | Conteúdo | Uso |
|---|---|---|
| `data/backtest_carteiras_v2.json` | 104 semanas simuladas (`semana`, `data_formacao`, `data_vigencia_fim`, `tickers[]` com `ticker`, `score`, `preco_entrada`, `preco_saida`, `retorno_semana`) | Fonte primária — dados completos das 104 semanas |
| `historico/carteira*.json` | Carteiras "reais" do sistema vivo (1 por semana após go-live) | Mostrar marcador "real" vs "simulado" |
| `data/backtest_resultado_v2.json` | Retorno agregado por semana (para totalizadores) | Cruzar `retorno_total_semana` da estratégia |

---

## 4. Estrutura da aba "Histórico"

### 4.1 Cabeçalho editorial (3 blocos label/valor)

```
PERÍODO DO HISTÓRICO          SEMANAS REGISTRADAS     TICKERS ÚNICOS
27/05/2024 → 22/05/2026       104                     ~58
```

### 4.2 Estatísticas agregadas (cards)

```
+--------------+--------------+--------------+--------------+
| Semanas      | % semanas    | Tickers      | Top ticker   |
| positivas    | positivas    | únicos       | (frequência) |
| 57           | 54.8%        | 58           | INTB3 · 12x  |
+--------------+--------------+--------------+--------------+
```

### 4.3 Ranking de tickers mais frequentes (top 10)

```
### Tickers mais frequentes na carteira
┌────────┬───────────┬────────────┬──────────────┐
│ Ticker │ Aparições │ Retorno    │ Hit rate     │
│        │           │ médio/sem. │ (+ semanas)  │
├────────┼───────────┼────────────┼──────────────┤
│ INTB3  │ 12        │ +1.42%     │ 58%          │
│ DESK3  │ 11        │ +0.87%     │ 55%          │
│ ...
```

### 4.4 Linha do tempo — composição semanal (tabela master)

Tabela com **1 linha por semana** (104 semanas, ordem mais recente primeiro):

| Semana | Vigência | Retorno | Melhor | Pior | Composição |
|---|---|---|---|---|---|
| 2026-W21 | 18/05 → 22/05 | −1.57% | EUCA4 (+2.8%) | OFSA3 (−5.1%) | `OFSA3 · INTB3 · EUCA4 · TTEN3 · BMGB4` |
| 2026-W20 | 11/05 → 15/05 | … | … | … | … |

**Comportamento**: ao **selecionar uma linha**, expande um painel abaixo com:

```
### Composição da semana 2026-W21 (18/05 → 22/05)

┌────────┬───────┬──────────┬──────────┬──────────┬───────────┐
│ Ticker │ Score │ Entrada  │ Saída    │ Δ (R$)   │ Retorno   │
│ OFSA3  │ 81.6  │ R$ 32,26 │ R$ 30,63 │ -R$ 1,63 │ −5.05%    │
│ INTB3  │ 74.6  │ R$ 14,65 │ R$ 13,95 │ -R$ 0,70 │ −4.78%    │
│ EUCA4  │ 70.8  │ R$ 26,41 │ R$ 27,15 │ +R$ 0,74 │ +2.80%    │
│ TTEN3  │ 69.9  │ R$ 16,66 │ R$ 15,XX │ ...      │ ...       │
│ BMGB4  │ 67.X  │ R$ 5,15  │ R$ 5,17  │ +R$ 0,02 │ +0.39%    │
└────────┴───────┴──────────┴──────────┴──────────┴───────────┘

[Retorno ponderado da semana: -1.57%]
```

### 4.5 Filtros (sidebar ou inline)

- **Buscar ticker**: input texto → filtra semanas onde o ticker aparece
- **Período**: dropdown (últimos 3m, 6m, 1a, tudo)
- **Apenas semanas positivas / negativas**: checkbox/toggle

---

## 5. Componentes técnicos

### 5.1 Novo arquivo: `components/historico_carteira.py`

Funções:

- `_carregar_carteiras_backtest() -> list[dict]` (cached)
- `_estatisticas_agregadas(carteiras) -> dict` (n_pos, %pos, tickers únicos)
- `_frequencia_tickers(carteiras) -> pd.DataFrame` (top tickers + métricas)
- `_render_cabecalho_editorial(...)` (label/valor 3 blocos)
- `_render_estatisticas(...)`
- `_render_top_tickers(...)`
- `_render_timeline(carteiras, filtros)` — tabela master + selectbox drill-down
- `render_aba_historico_carteira()` — função principal

### 5.2 Mudanças em `app.py`

Adicionar terceira aba:
```python
tab_carteira, tab_backtest, tab_historico = st.tabs(
    ["Carteira", "Backtest", "Histórico"]
)
```

### 5.3 Reuso de utilitários

- `fmt_pct`, `fmt_reais`, `fmt_data_br` — já existem
- `COLORS`, `CHART_PALETTE` — já existem
- Padrão de header editorial (3 blocos label/valor) — extrair pra `theme.py`?
  Não nessa rodada — copiar do backtest pra evitar refactor maior.

---

## 6. Detalhes de implementação

### 6.1 Performance

- 104 semanas × 5 tickers = 520 linhas no total
- DataFrame de Composição: **lazy** — só gera ao selecionar
- Stats agregadas: cached com `@st.cache_data(ttl=300)`
- A tabela master mostra **resumo curto** (ex: `OFSA3 · INTB3 · EUCA4 · TTEN3 · BMGB4`) — não impactar performance

### 6.2 Drill-down via `st.dataframe(on_select="rerun")`

Streamlit suporta seleção de linha nativa:
```python
event = st.dataframe(df, on_select="rerun", selection_mode="single-row")
if event.selection.rows:
    idx = event.selection.rows[0]
    _render_composicao(carteiras[idx])
```

### 6.3 Tratamento de dados ausentes

- Algumas semanas podem ter `preco_saida = None` (semana sem fechamento ainda)
- `retorno_semana = None` → mostrar "—"
- `score = None` → mostrar "—"

### 6.4 Coluna "Composição" da tabela master

String formatada: `"OFSA3 · INTB3 · EUCA4 · TTEN3 · BMGB4"` (ordem decrescente de score).
Máximo 5 tickers (sempre é 5 nas carteiras V2).

### 6.5 Cores semânticas

- Retorno positivo → cor `COLORS["pos"]` (verde sóbrio)
- Retorno negativo → cor `COLORS["neg"]` (vermelho sóbrio)
- Aplicado via column_config NumberColumn (não suporta cor nativa) → **deixar sem cor por enquanto**, formatação simples

---

## 7. O que NÃO entra nessa rodada (escopo intencional)

- Exportação CSV/Excel da composição (próxima iteração)
- Gráficos de overlap entre semanas (Sankey, etc.) — over-engineering
- Análise de turnover (% de tickers que mudam semana a semana) — fica como
  feature do roadmap se houver demanda
- Comparação histórica de scores (curva do score médio) — fora do escopo

---

## 8. Ordem de execução

1. ✅ Documentar o plano (este arquivo)
2. Criar `components/historico_carteira.py` com:
   - Loaders + helpers
   - Cabeçalho editorial + estatísticas + top tickers + timeline + drill-down
3. Adicionar terceira aba em `app.py`
4. Validar sintaxe
5. Commit + push

---

*Documento gerado em 2026-05-23.*
