# DIAGNOSTIC SPEC — Análise de Atribuição de Performance

> **Versão:** 3.0
> **Data:** 22/05/2026
> **Status:** Fechado. Pronto para implementação.
> **Depende de:** `PHASE3_SPEC.md`, `PHASE4_SPEC.md`
> **Não altera:** nenhum artefato existente — somente leitura dos dados já gerados
>
> **Changelog v3.0:**
> - Módulo 2 (atribuição por fator) removido — IC é a métrica mais confiável e o substitui
> - Módulo 4 (regime de mercado) removido
> - Módulo 5 reduzido a concentração por ação — turnover removido (carteira sem custos)
> - Módulo 6: T4 removido (MMA200 descartado da V2); T1 vira novo baseline V2; T0 mantido só como referência histórica
> - IC calculado sobre excess return vs SMLL (não retorno bruto)
> - IC rolling 26 semanas adicionado ao Módulo 3
> - Correlação momentum-tendência adicionada ao Módulo 3
> - Variantes de momentum adicionadas ao Módulo 6

---

## 1. Objetivo

**Etapa 1 deste diagnóstico:** entender o que está puxando a fórmula V1 para baixo e gerar um relatório com evidências.

**Etapa 2 (spec separado):** a partir do relatório, gerar instruções completas da fórmula V2.

O diagnóstico responde a quatro perguntas sobre a V1:

1. **O problema é o universo ou a fórmula?** Small caps 2023-2025 vs seleção dentro delas
2. **Quais fatores têm poder preditivo real de gerar alpha?** IC por fator sobre excess return
3. **Momentum e tendência são redundantes?** Correlação entre os dois fatores
4. **As janelas de momentum e tendência estão calibradas para o horizonte semanal?** Variantes mais reativas geram mais alpha?

**Princípio central:** nenhuma mudança de fórmula é recomendada sem que este diagnóstico seja concluído primeiro. Mudar sem diagnosticar é overfitting.

---

## 2. Fontes de dados

Todos os dados necessários já existem — o diagnóstico é 100% leitura:

| Arquivo | O que fornece |
|---|---|
| `data/backtest_resultado.json` | Equity curve semanal, métricas agregadas, retornos por semana |
| `data/backtest_carteiras.json` | Composição e retorno de cada uma das ~104 carteiras |
| `historico/scores_YYYY-MM-DD.json` | Score e breakdown de fatores (A/B/C/D) de cada ação em cada dia |
| `data/precos.parquet` | Série histórica de preços — recalcula variantes no Módulo 6 |
| `data/benchmarks.parquet` | Séries do IBOV, SMLL e CDI |

---

## 3. Pipeline do diagnóstico

```
[Leitura dos artefatos existentes]
        │
        ▼
[Módulo 1] Diagnóstico macro
        — Estratégia vs SMLL vs IBOV por subperíodo
        — O problema é o universo ou a seleção?
        │
        ▼
[Módulo 3] IC com excess return + rolling + correlação fatores
        — IC de cada fator sobre retorno em excesso vs SMLL
        — IC rolling 26 semanas (poder preditivo está aumentando ou degradando?)
        — Correlação momentum × tendência (são redundantes?)
        │
        ▼
[Módulo 5] Concentração por ação
        — Quais ações específicas destruíram mais valor?
        │
        ▼
[Módulo 6] Variantes de tendência e momentum
        — Janelas mais curtas geram mais alpha?
        — Variantes de tendência: T0 (ref. V1), T1 (baseline V2), T2, T3
        — Variantes de momentum: M0 (ref. V1), M1, M2, M3
        │
        ▼
[Geração do relatório]
        — diagnostic_report.json
        — diagnostic_report.md (achados + hipóteses para Etapa 2)
```

---

## 4. Módulo 1 — Diagnóstico macro

### 4.1 Objetivo
Separar "a estratégia foi ruim" de "small caps foram ruins no período". Se o SMLL também perdeu pro IBOV consistentemente, parte do underperformance é estrutural do universo — não da fórmula.

### 4.2 Cálculos

**Retorno acumulado por subperíodo:**
```python
def calcular_retornos_por_periodo(equity_curve):
    """
    Divide a equity curve em 4 subperíodos iguais.
    Permite ver se o underperformance foi constante ou concentrado num período.
    """
    n = len(equity_curve)
    periodos = {
        "Q1 (primeiros 6 meses)": equity_curve[:n//4],
        "Q2 (6-12 meses)":        equity_curve[n//4:n//2],
        "Q3 (12-18 meses)":       equity_curve[n//2:3*n//4],
        "Q4 (últimos 6 meses)":   equity_curve[3*n//4:]
    }
    resultado = {}
    for nome, trecho in periodos.items():
        if len(trecho) < 2:
            continue
        ret_estrategia = trecho[-1]["valor_estrategia"] / trecho[0]["valor_estrategia"] - 1
        ret_ibov       = trecho[-1]["valor_ibov"]       / trecho[0]["valor_ibov"]       - 1
        ret_smll       = trecho[-1]["valor_smll"]       / trecho[0]["valor_smll"]       - 1
        resultado[nome] = {
            "estrategia":    ret_estrategia,
            "ibov":          ret_ibov,
            "smll":          ret_smll,
            "alpha_vs_ibov": ret_estrategia - ret_ibov,
            "alpha_vs_smll": ret_estrategia - ret_smll
        }
    return resultado
```

**Hit rate vs SMLL por semestre:**
```python
def diagnostico_vs_smll(backtest_carteiras):
    """
    Calcula hit rate por semestre para ver se a estratégia
    foi consistentemente ruim vs SMLL ou degradou com o tempo.
    """
    semanas = backtest_carteiras["carteiras"]
    por_semestre = {}

    for s in semanas:
        data = pd.Timestamp(s["data_formacao"])
        semestre = f"{data.year}-S{'1' if data.month <= 6 else '2'}"
        if semestre not in por_semestre:
            por_semestre[semestre] = {"ganhou": 0, "perdeu": 0}
        if s["retorno_carteira"] > s["retorno_smll_semana"]:
            por_semestre[semestre]["ganhou"] += 1
        else:
            por_semestre[semestre]["perdeu"] += 1

    for sem, dados in por_semestre.items():
        total = dados["ganhou"] + dados["perdeu"]
        dados["hit_rate"] = dados["ganhou"] / total

    return por_semestre
```

### 4.3 Interpretação

| Resultado | Diagnóstico | Implicação para V2 |
|---|---|---|
| SMLL também perdeu pro IBOV no mesmo período | Problema estrutural do universo no período | Expandir universo para R$500M-15B antes de mexer na fórmula |
| SMLL bateu IBOV mas estratégia perdeu pro SMLL | Problema de seleção dentro do universo | Fórmula precisa melhorar — foco no Módulo 3 |
| Underperformance concentrado em 1-2 semestres | Evento pontual | Investigar o período antes de concluir sobre a fórmula |
| Underperformance constante todos os semestres | Problema estrutural da fórmula | Mudança de fórmula necessária — foco no Módulo 3 |

---

## 5. Módulo 3 — IC com excess return, rolling e correlação entre fatores

### 5.1 Por que excess return e não retorno bruto

IC calculado sobre retorno bruto mede "score alto previu retorno absoluto alto". O que importa é "score alto previu retorno **acima do SMLL**". Uma semana em que o SMLL sobe 3% e todas as ações sobem 2% gera IC positivo no bruto — mas a carteira perdeu pro benchmark. Usando excess return, o IC mede exatamente o poder de gerar alpha.

```python
# ERRADO para o propósito
retornos_reais[ticker] = saida / entrada - 1

# CORRETO — excess return vs SMLL
retorno_bruto = saida / entrada - 1
retornos_reais[ticker] = retorno_bruto - retorno_smll_semana
```

### 5.2 Cálculo do IC por fator

```python
from scipy.stats import spearmanr
import numpy as np

def calcular_ic_por_fator(backtest_carteiras, df_precos, df_benchmarks):
    """
    Para cada semana: correlação de Spearman entre score normalizado
    de cada fator e excess return real da ação vs SMLL.
    """
    fatores = ["momentum", "tendencia", "roic", "cagr", "score_final"]
    ic_series = {f: [] for f in fatores}

    for semana in backtest_carteiras["carteiras"]:
        data_corte  = semana["data_corte_dados"]
        data_inicio = semana["data_formacao"]
        data_fim    = semana["data_vigencia_fim"]

        scores_path = f"historico/scores_{data_corte}.json"
        if not os.path.exists(scores_path):
            continue

        with open(scores_path) as f:
            scores_dia = json.load(f)["scores"]

        # Retorno do SMLL na semana (benchmark)
        df_smll = df_benchmarks[df_benchmarks["ticker"] == "SMLL11"]
        smll_entrada = df_smll[df_smll["date"] <= pd.Timestamp(data_inicio)]["adj_close"]
        smll_saida   = df_smll[df_smll["date"] <= pd.Timestamp(data_fim)]["adj_close"]
        if smll_entrada.empty or smll_saida.empty:
            continue
        ret_smll_semana = smll_saida.iloc[-1] / smll_entrada.iloc[-1] - 1

        # Excess return de cada ação vs SMLL
        retornos_reais = {}
        for s in scores_dia:
            ticker = s["ticker"]
            df_t = df_precos[df_precos["ticker"] == ticker]
            entrada = df_t[df_t["date"] <= pd.Timestamp(data_inicio)]["adj_close"]
            saida   = df_t[df_t["date"] <= pd.Timestamp(data_fim)]["adj_close"]
            if not entrada.empty and not saida.empty:
                ret_bruto = saida.iloc[-1] / entrada.iloc[-1] - 1
                retornos_reais[ticker] = ret_bruto - ret_smll_semana  # excess return

        if len(retornos_reais) < 20:
            continue

        for fator in fatores:
            scores_fator, retornos = [], []
            for s in scores_dia:
                ticker = s["ticker"]
                if ticker not in retornos_reais:
                    continue
                score_val = (s["score_final"] if fator == "score_final"
                             else s["fatores"][fator]["normalizado"])
                scores_fator.append(score_val)
                retornos.append(retornos_reais[ticker])

            if len(scores_fator) < 10:
                continue

            ic, _ = spearmanr(scores_fator, retornos)
            ic_series[fator].append({
                "semana": semana["semana"],
                "ic": ic if not np.isnan(ic) else 0.0
            })

    resumo = {}
    for fator, series in ic_series.items():
        ics = [x["ic"] for x in series]
        resumo[fator] = {
            "ic_medio":        np.mean(ics),
            "ic_mediano":      np.median(ics),
            "ic_positivo_pct": sum(1 for x in ics if x > 0) / len(ics),
            "ic_std":          np.std(ics),
            "ir":              np.mean(ics) / np.std(ics) if np.std(ics) > 0 else 0,
            "series":          series
        }

    return resumo
```

### 5.3 IC rolling 26 semanas

```python
def calcular_ic_rolling(resumo_ic, janela=26):
    """
    Para cada fator: IC médio rolling de 26 semanas.
    Detecta se o poder preditivo está aumentando ou degradando ao longo do tempo.
    IC rolling caindo nos últimos 6 meses = fator perdendo relevância.
    """
    resultado = {}
    for fator, dados in resumo_ic.items():
        series = dados["series"]
        ics    = [x["ic"] for x in series]
        datas  = [x["semana"] for x in series]
        rolling = []
        for i in range(janela, len(ics)):
            rolling.append({
                "semana":     datas[i],
                "ic_rolling": np.mean(ics[i-janela:i])
            })
        # Tendência dos últimos 13 períodos rolling (3 meses)
        if len(rolling) >= 13:
            ic_recente  = np.mean([r["ic_rolling"] for r in rolling[-13:]])
            ic_anterior = np.mean([r["ic_rolling"] for r in rolling[-26:-13]])
            tendencia   = "subindo" if ic_recente > ic_anterior else "caindo"
        else:
            tendencia = "insuficiente"

        resultado[fator] = {
            "rolling": rolling,
            "tendencia_recente": tendencia
        }
    return resultado
```

### 5.4 Correlação entre momentum e tendência

```python
def calcular_correlacao_momentum_tendencia(scores_historico_paths):
    """
    Para cada semana: correlação de Spearman entre score normalizado
    de momentum e score normalizado de tendência, para as 50 ações.
    Correlação > 0.65 = fatores redundantes.
    """
    correlacoes = []

    for path in scores_historico_paths:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            scores_dia = json.load(f)["scores"]

        mom  = [s["fatores"]["momentum"]["normalizado"] for s in scores_dia]
        tend = [s["fatores"]["tendencia"]["normalizado"] for s in scores_dia]

        if len(mom) < 10:
            continue

        corr, _ = spearmanr(mom, tend)
        correlacoes.append(corr if not np.isnan(corr) else 0.0)

    return {
        "correlacao_media":   np.mean(correlacoes),
        "correlacao_mediana": np.median(correlacoes),
        "pct_acima_065":      sum(1 for c in correlacoes if c > 0.65) / len(correlacoes),
        "interpretacao": (
            "REDUNDANTES — momentum e tendência medem essencialmente o mesmo sinal"
            if np.mean(correlacoes) > 0.65
            else "COMPLEMENTARES — momentum e tendência adicionam informação distinta"
        )
    }
```

### 5.5 Interpretação do IC

| IC médio (excess return) | Semáforo | Diagnóstico |
|---|---|---|
| > 0,05 | 🟢 | Fator gera alpha consistente |
| 0,02 – 0,05 | 🟡 | Sinal fraco mas presente |
| 0 – 0,02 | 🔴 | Ruído — não gera alpha |
| < 0 | 🔴🔴 | Fator invertido — prejudica a carteira |

### 5.6 Interpretação da correlação momentum-tendência

| Correlação média | Diagnóstico | Implicação para V2 |
|---|---|---|
| > 0,65 | Redundantes | Tendência vira filtro de entrada (já decidido na V2). Score usa só momentum + fundamentos |
| 0,40 – 0,65 | Parcialmente redundantes | Manter ambos mas reduzir peso de tendência no score |
| < 0,40 | Complementares | Ambos contribuem com informação distinta — manter estrutura |

---

## 6. Módulo 5 — Concentração por ação

### 6.1 Objetivo
Identificar se há ações específicas que apareceram repetidamente na carteira e destruíram valor de forma desproporcional. Permite decisão de blacklist manual antes da V2.

### 6.2 Cálculo

```python
def analisar_contribuicao_por_acao(backtest_carteiras):
    contrib = {}

    for semana in backtest_carteiras["carteiras"]:
        n    = len(semana["tickers"])
        peso = 1 / n if n > 0 else 0

        for t in semana["tickers"]:
            ticker = t["ticker"]
            if ticker not in contrib:
                contrib[ticker] = {"aparicoes": 0, "retornos": [], "contribuicoes": []}
            contrib[ticker]["aparicoes"] += 1
            contrib[ticker]["retornos"].append(t["retorno_semana"])
            contrib[ticker]["contribuicoes"].append(t["retorno_semana"] * peso)

    resultado = []
    for ticker, dados in contrib.items():
        resultado.append({
            "ticker":             ticker,
            "aparicoes":          dados["aparicoes"],
            "retorno_medio":      np.mean(dados["retornos"]),
            "contribuicao_total": sum(dados["contribuicoes"]),
            "win_rate":           sum(1 for r in dados["retornos"] if r > 0) / len(dados["retornos"])
        })

    # Piores primeiro
    return sorted(resultado, key=lambda x: x["contribuicao_total"])
```

### 6.3 Interpretação

| Situação | Ação |
|---|---|
| 1-3 ações respondem por > 50% do prejuízo total | Candidatas a blacklist manual — verificar se há problema fundamentalista não capturado pelo ROIC |
| Prejuízo distribuído entre muitas ações | Problema sistêmico de sinal — não é concentração, foco no Módulo 3 |
| Ações problemáticas têm ROIC positivo mas resultados ruins | Filtro F2 (ROIC > 0%) da V2 não as eliminaria — considerar threshold mais alto |

---

## 7. Módulo 6 — Variantes de tendência e momentum

### 7.1 Contexto e decisões já tomadas

A fórmula V2 já adotou MMA20/50 no **filtro de entrada** (decisão R2 — não depende do diagnóstico). O Módulo 6 testa variantes para o **fator de score de tendência** e para o **fator de momentum**, ambos dentro do universo que passa pelo filtro.

**T4 foi removido:** MMA200 foi descartado da V2 — reintroduzi-lo via T4 seria inconsistente.

### 7.2 Variantes de tendência (fator de score)

| Código | Configuração | Status |
|---|---|---|
| **T0** | MMA50/200 simples — baseline V1 | Referência histórica apenas |
| **T1** | MMA20/50 simples — baseline V2 | **Novo baseline** (alinhado com filtro de entrada) |
| **T2** | EMA20/50 — peso exponencial nos recentes | Mais reativo dentro da mesma janela |
| **T3** | Pesos assimétricos: (P>MMA20)×2 + (P>MMA50)×1 + (MMA20>MMA50)×1 | Curto prazo vale o dobro |

### 7.3 Variantes de momentum

A mesma hipótese de "janelas longas demais" aplica-se ao momentum. O retorno de 6m captura o mesmo sinal que a MMA200 já capturava no filtro da V1 — que foi descartado. Testar variantes mais reativas:

| Código | Configuração | Lógica |
|---|---|---|
| **M0** | (ret_1m + ret_3m + ret_6m) / 3 — baseline V1 | Referência histórica |
| **M1** | ret_1m apenas (21 pregões) | Curto prazo puro — máxima reatividade |
| **M2** | (ret_1m × 3 + ret_3m × 2 + ret_6m × 1) / 6 | Pesos crescentes para o recente |
| **M3** | (ret_1m + ret_3m) / 2 — sem 6m | Remove o sinal mais lento |

**M3 é o baseline da fórmula V2 proposta.** O diagnóstico confirma ou refuta essa escolha.

### 7.4 Cálculo das variantes de tendência

```python
def calcular_tendencia_variante(df_ticker, variante: str) -> float:
    """
    Recalcula score de tendência com a variante especificada.
    Retorna valor normalizado 0-100.
    df_ticker filtrado até data_corte (anti-look-ahead garantido).
    """
    close = df_ticker["adj_close"]

    if variante == "T0":
        mma50  = close.tail(50).mean()
        mma200 = close.tail(200).mean()
        preco  = close.iloc[-1]
        bruto  = (1 if preco > mma50 else 0) + (1 if preco > mma200 else 0) + (1 if mma50 > mma200 else 0)
        return (bruto / 3) * 100

    elif variante == "T1":
        mma20 = close.tail(20).mean()
        mma50 = close.tail(50).mean()
        preco = close.iloc[-1]
        bruto = (1 if preco > mma20 else 0) + (1 if preco > mma50 else 0) + (1 if mma20 > mma50 else 0)
        return (bruto / 3) * 100

    elif variante == "T2":
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        preco = close.iloc[-1]
        bruto = (1 if preco > ema20 else 0) + (1 if preco > ema50 else 0) + (1 if ema20 > ema50 else 0)
        return (bruto / 3) * 100

    elif variante == "T3":
        mma20 = close.tail(20).mean()
        mma50 = close.tail(50).mean()
        preco = close.iloc[-1]
        bruto = (2 if preco > mma20 else 0) + (1 if preco > mma50 else 0) + (1 if mma20 > mma50 else 0)
        return (bruto / 4) * 100

    raise ValueError(f"Variante desconhecida: {variante}")
```

### 7.5 Cálculo das variantes de momentum

```python
def calcular_momentum_variante(df_ticker, variante: str) -> float:
    """
    Recalcula momentum bruto com a variante especificada.
    Retorna valor bruto (será normalizado por percentil depois).
    df_ticker filtrado até data_corte (anti-look-ahead garantido).
    """
    close = df_ticker["adj_close"]

    if len(close) < 127:  # mínimo para M0 (baseline)
        return np.nan

    preco_atual = close.iloc[-1]
    ret_1m = preco_atual / close.iloc[-22]  - 1   # 21 pregões
    ret_3m = preco_atual / close.iloc[-64]  - 1   # 63 pregões
    ret_6m = preco_atual / close.iloc[-127] - 1   # 126 pregões

    if variante == "M0":
        return (ret_1m + ret_3m + ret_6m) / 3

    elif variante == "M1":
        return ret_1m

    elif variante == "M2":
        return (ret_1m * 3 + ret_3m * 2 + ret_6m * 1) / 6

    elif variante == "M3":
        if len(close) < 64:
            return np.nan
        return (ret_1m + ret_3m) / 2

    raise ValueError(f"Variante desconhecida: {variante}")
```

### 7.6 IC por variante (excess return vs SMLL)

```python
def calcular_ic_variantes(backtest_carteiras, df_precos, df_benchmarks,
                           variantes_tend, variantes_mom):
    """
    Para cada variante de tendência e momentum: calcula IC sobre excess return.
    Mesmo método do Módulo 3 — garante comparabilidade.
    """
    ic_tend = {v: [] for v in variantes_tend}
    ic_mom  = {v: [] for v in variantes_mom}

    for semana in backtest_carteiras["carteiras"]:
        data_corte  = semana["data_corte_dados"]
        data_inicio = semana["data_formacao"]
        data_fim    = semana["data_vigencia_fim"]

        scores_path = f"historico/scores_{data_corte}.json"
        if not os.path.exists(scores_path):
            continue

        with open(scores_path) as f:
            tickers_universo = [s["ticker"] for s in json.load(f)["scores"]]

        # Excess return de cada ação vs SMLL
        df_smll = df_benchmarks[df_benchmarks["ticker"] == "SMLL11"]
        smll_ent = df_smll[df_smll["date"] <= pd.Timestamp(data_inicio)]["adj_close"]
        smll_sai = df_smll[df_smll["date"] <= pd.Timestamp(data_fim)]["adj_close"]
        if smll_ent.empty or smll_sai.empty:
            continue
        ret_smll = smll_sai.iloc[-1] / smll_ent.iloc[-1] - 1

        excess_returns = {}
        for ticker in tickers_universo:
            df_t = df_precos[df_precos["ticker"] == ticker]
            ent  = df_t[df_t["date"] <= pd.Timestamp(data_inicio)]["adj_close"]
            sai  = df_t[df_t["date"] <= pd.Timestamp(data_fim)]["adj_close"]
            if not ent.empty and not sai.empty:
                excess_returns[ticker] = (sai.iloc[-1] / ent.iloc[-1] - 1) - ret_smll

        if len(excess_returns) < 20:
            continue

        # IC por variante de tendência
        for variante in variantes_tend:
            scores_v, retornos = [], []
            for ticker in tickers_universo:
                if ticker not in excess_returns:
                    continue
                df_t = df_precos[df_precos["ticker"] == ticker]
                df_f = df_t[df_t["date"] <= pd.Timestamp(data_corte)]
                min_pregoes = 200 if variante == "T0" else 50
                if len(df_f) < min_pregoes:
                    continue
                score = calcular_tendencia_variante(df_f, variante)
                scores_v.append(score)
                retornos.append(excess_returns[ticker])
            if len(scores_v) >= 10:
                ic, _ = spearmanr(scores_v, retornos)
                ic_tend[variante].append({"semana": semana["semana"],
                                          "ic": ic if not np.isnan(ic) else 0.0})

        # IC por variante de momentum
        for variante in variantes_mom:
            scores_v, retornos = [], []
            for ticker in tickers_universo:
                if ticker not in excess_returns:
                    continue
                df_t = df_precos[df_precos["ticker"] == ticker]
                df_f = df_t[df_t["date"] <= pd.Timestamp(data_corte)]
                mom = calcular_momentum_variante(df_f, variante)
                if np.isnan(mom):
                    continue
                scores_v.append(mom)
                retornos.append(excess_returns[ticker])
            if len(scores_v) >= 10:
                ic, _ = spearmanr(scores_v, retornos)
                ic_mom[variante].append({"semana": semana["semana"],
                                         "ic": ic if not np.isnan(ic) else 0.0})

    def sumarizar(ic_dict):
        resumo = {}
        for variante, series in ic_dict.items():
            ics = [x["ic"] for x in series]
            resumo[variante] = {
                "ic_medio":        np.mean(ics),
                "ic_positivo_pct": sum(1 for x in ics if x > 0) / len(ics),
                "ir":              np.mean(ics) / np.std(ics) if np.std(ics) > 0 else 0,
                "n_semanas":       len(series)
            }
        return resumo

    return sumarizar(ic_tend), sumarizar(ic_mom)

def identificar_vencedora(resumo, baseline_key):
    """
    Identifica variante com maior IC médio.
    Só recomenda mudança se ganho vs baseline > 20%.
    """
    baseline_ic = resumo[baseline_key]["ic_medio"]
    melhor = max(resumo, key=lambda v: resumo[v]["ic_medio"])
    melhor_ic = resumo[melhor]["ic_medio"]
    ganho = (melhor_ic - baseline_ic) / abs(baseline_ic) if baseline_ic != 0 else 0

    return {
        "variante_vencedora":  melhor,
        "ic_vencedora":        melhor_ic,
        "ic_baseline":         baseline_ic,
        "ganho_relativo":      ganho,
        "recomenda_mudanca":   ganho > 0.20,
        "motivo": (
            f"Variante {melhor} tem IC {ganho:.0%} acima do baseline "
            f"({melhor_ic:.4f} vs {baseline_ic:.4f}) — "
            + ("recomendada para V2." if ganho > 0.20
               else "ganho < 20% — manter baseline.")
        )
    }
```

### 7.7 Interpretação dos resultados

**Tendência:**

| Variante vencedora | Ação para V2 |
|---|---|
| T0 (baseline V1) | MMA20/50 no score (T1) mas sem vantagem confirmada — manter T1 por consistência com filtro |
| T1 (baseline V2) | MMA20/50 confirmado como melhor — adotar no score |
| T2 (EMA20/50) | Substituir médias simples por EMA no score |
| T3 (pesos assimétricos) | Usar estrutura 0-4 com peso duplo no critério MMA20 |

**Momentum:**

| Variante vencedora | Ação para V2 |
|---|---|
| M0 (baseline V1) | Manter média 1m+3m+6m — janelas longas ainda são úteis |
| M1 (só 1m) | Curto prazo puro — sinal muito reativo, verificar estabilidade |
| M2 (pesos crescentes) | Adotar ponderação 3/2/1 para 1m/3m/6m |
| M3 (1m+3m, sem 6m) | **Confirma proposta da fórmula V2** — remover 6m |

**Regra de adoção:** só muda se ganho relativo > 20% vs baseline. Abaixo disso, manter baseline por parcimônia.

---

## 8. Geração automática de hipóteses para V2

```python
def gerar_hipoteses_v2(m3_ic, m3_correlacao, m3_rolling,
                        m5_contribuicao, m6_tend_vencedora, m6_mom_vencedora):
    hipoteses = []

    # Módulo 3 — IC por fator
    for fator, dados in m3_ic.items():
        if fator == "score_final":
            continue
        if dados["ic_medio"] < 0:
            hipoteses.append({
                "origem":        f"Módulo 3 — IC {fator}",
                "hipotese":      f"Fator {fator} está invertido — prejudica a carteira",
                "evidencia":     f"IC médio = {dados['ic_medio']:.4f} (negativo)",
                "acao_sugerida": f"Remover {fator} da fórmula V2"
            })
        elif dados["ic_medio"] < 0.02:
            hipoteses.append({
                "origem":        f"Módulo 3 — IC {fator}",
                "hipotese":      f"Fator {fator} não gera alpha — é ruído",
                "evidencia":     f"IC médio = {dados['ic_medio']:.4f} (< 0.02)",
                "acao_sugerida": f"Remover ou reduzir peso de {fator} drasticamente na V2"
            })

    # Módulo 3 — IC rolling
    for fator, dados in m3_rolling.items():
        if dados["tendencia_recente"] == "caindo":
            hipoteses.append({
                "origem":        f"Módulo 3 — IC rolling {fator}",
                "hipotese":      f"Fator {fator} está perdendo poder preditivo nos últimos 6 meses",
                "evidencia":     "IC rolling caindo nos últimos 13 períodos",
                "acao_sugerida": f"Reduzir peso de {fator} na V2; monitorar na operação real"
            })

    # Módulo 3 — Correlação momentum-tendência
    if m3_correlacao["correlacao_media"] > 0.65:
        hipoteses.append({
            "origem":        "Módulo 3 — Correlação momentum × tendência",
            "hipotese":      "Momentum e tendência são redundantes",
            "evidencia":     f"Correlação média = {m3_correlacao['correlacao_media']:.2f} (> 0.65)",
            "acao_sugerida": "Manter tendência só como filtro de entrada (já decidido na V2) — confirma a decisão"
        })

    # Módulo 5 — Concentração
    top_destruidores = [a for a in m5_contribuicao if a["contribuicao_total"] < -0.02]
    if len(top_destruidores) <= 3 and sum(a["contribuicao_total"] for a in top_destruidores) < -0.05:
        tickers = [a["ticker"] for a in top_destruidores]
        hipoteses.append({
            "origem":        "Módulo 5 — Concentração",
            "hipotese":      f"Ações {tickers} concentram prejuízo desproporcional",
            "evidencia":     f"Contribuição total: {sum(a['contribuicao_total'] for a in top_destruidores):.3f}",
            "acao_sugerida": "Avaliar adição à blacklist.json antes de rodar V2"
        })

    # Módulo 6 — Variantes de tendência
    if m6_tend_vencedora["recomenda_mudanca"] and m6_tend_vencedora["variante_vencedora"] != "T1":
        hipoteses.append({
            "origem":        "Módulo 6 — Variante tendência",
            "hipotese":      f"Variante {m6_tend_vencedora['variante_vencedora']} gera mais alpha que MMA20/50 simples",
            "evidencia":     m6_tend_vencedora["motivo"],
            "acao_sugerida": f"Adotar {m6_tend_vencedora['variante_vencedora']} no score de tendência da V2"
        })

    # Módulo 6 — Variantes de momentum
    if m6_mom_vencedora["recomenda_mudanca"]:
        hipoteses.append({
            "origem":        "Módulo 6 — Variante momentum",
            "hipotese":      f"Variante {m6_mom_vencedora['variante_vencedora']} gera mais alpha",
            "evidencia":     m6_mom_vencedora["motivo"],
            "acao_sugerida": f"Adotar {m6_mom_vencedora['variante_vencedora']} no cálculo de momentum da V2"
        })

    return hipoteses
```

---

## 9. Script principal

### 9.1 `src/diagnostic.py`

```python
"""
Diagnóstico de performance da fórmula V1 — v3.0
Módulos ativos: 1 (macro), 3 (IC + rolling + correlação), 5 (concentração), 6 (variantes)
Módulos removidos: 2 (atribuição), 4 (regime de mercado)
Output: data/diagnostic_report.json + data/diagnostic_report.md
"""
import json
import os
import pandas as pd
import numpy as np
from pathlib import Path
from glob import glob

from diagnostic_modules.macro       import calcular_retornos_por_periodo, diagnostico_vs_smll
from diagnostic_modules.ic          import (calcular_ic_por_fator, calcular_ic_rolling,
                                             calcular_correlacao_momentum_tendencia)
from diagnostic_modules.concentracao import analisar_contribuicao_por_acao
from diagnostic_modules.tendencia   import (calcular_ic_variantes, identificar_vencedora)
from diagnostic_modules.relatorio   import gerar_markdown, gerar_hipoteses_v2

VARIANTES_TEND = ["T0", "T1", "T2", "T3"]
VARIANTES_MOM  = ["M0", "M1", "M2", "M3"]

def main():
    print("=== Diagnóstico de Performance V1 — spec v3.0 ===")

    print("Carregando artefatos...")
    with open("data/backtest_resultado.json") as f:
        backtest_resultado = json.load(f)
    with open("data/backtest_carteiras.json") as f:
        backtest_carteiras = json.load(f)

    df_precos     = pd.read_parquet("data/precos.parquet")
    df_benchmarks = pd.read_parquet("data/benchmarks.parquet")
    scores_paths  = sorted(glob("historico/scores_*.json"))

    print("Módulo 1: Diagnóstico macro...")
    m1 = {
        "retorno_por_subperiodo":       calcular_retornos_por_periodo(
                                            backtest_resultado["equity_curve"]),
        "hit_rate_vs_smll_por_semestre":diagnostico_vs_smll(backtest_carteiras)
    }

    print("Módulo 3: IC, rolling e correlação fatores...")
    m3_ic         = calcular_ic_por_fator(backtest_carteiras, df_precos, df_benchmarks)
    m3_rolling    = calcular_ic_rolling(m3_ic)
    m3_correlacao = calcular_correlacao_momentum_tendencia(scores_paths)

    print("Módulo 5: Concentração por ação...")
    m5 = analisar_contribuicao_por_acao(backtest_carteiras)

    print("Módulo 6: Variantes de tendência e momentum (2-5 min)...")
    ic_tend, ic_mom = calcular_ic_variantes(
        backtest_carteiras, df_precos, df_benchmarks,
        VARIANTES_TEND, VARIANTES_MOM
    )
    m6_tend_vencedora = identificar_vencedora(ic_tend, baseline_key="T1")
    m6_mom_vencedora  = identificar_vencedora(ic_mom,  baseline_key="M3")

    hipoteses = gerar_hipoteses_v2(
        m3_ic, m3_correlacao, m3_rolling,
        m5, m6_tend_vencedora, m6_mom_vencedora
    )

    relatorio = {
        "metadata": {
            "data_geracao":         str(pd.Timestamp.today().date()),
            "n_semanas_analisadas": len(backtest_carteiras["carteiras"]),
            "periodo":              (f"{backtest_resultado['metadata']['janela_inicio']}"
                                     f" a {backtest_resultado['metadata']['janela_fim']}"),
            "versao_spec":          "3.0"
        },
        "modulo_1_macro": m1,
        "modulo_3_ic": {
            "por_fator":             m3_ic,
            "rolling_26s":           m3_rolling,
            "correlacao_mom_tend":   m3_correlacao
        },
        "modulo_5_concentracao":     m5,
        "modulo_6_variantes": {
            "tendencia":             ic_tend,
            "momentum":              ic_mom,
            "tend_vencedora":        m6_tend_vencedora,
            "mom_vencedora":         m6_mom_vencedora
        },
        "hipoteses_v2": hipoteses
    }

    Path("data").mkdir(exist_ok=True)
    with open("data/diagnostic_report.json", "w") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)
    with open("data/diagnostic_report.md", "w") as f:
        f.write(gerar_markdown(relatorio))

    print("\n✅ Diagnóstico concluído.")
    print("   → data/diagnostic_report.json")
    print("   → data/diagnostic_report.md")

    print("\n=== HIPÓTESES PARA V2 ===")
    for i, h in enumerate(hipoteses, 1):
        print(f"\n{i}. [{h['origem']}] {h['hipotese']}")
        print(f"   Evidência: {h['evidencia']}")
        print(f"   Ação: {h['acao_sugerida']}")

if __name__ == "__main__":
    main()
```

---

## 10. Estrutura de arquivos

```
projeto/
├── src/
│   ├── diagnostic.py                     ← orquestrador principal
│   └── diagnostic_modules/
│       ├── __init__.py
│       ├── macro.py                       ← Módulo 1
│       ├── ic.py                          ← Módulo 3 (IC + rolling + correlação)
│       ├── concentracao.py                ← Módulo 5
│       ├── tendencia.py                   ← Módulo 6 (variantes tend. + mom.)
│       └── relatorio.py                   ← gerador de MD e hipóteses automáticas
└── data/
    ├── diagnostic_report.json             ← gerado
    └── diagnostic_report.md              ← gerado (entregável principal)
```

---

## 11. Dependências

```
# requirements.txt (acréscimo)
scipy>=1.11.0    # spearmanr para IC
```

---

## 12. Como rodar

```bash
# Pré-requisito: pipeline das Fases 1-4 já executado
python src/diagnostic.py
```

Tempo estimado: **3–7 minutos** (Módulo 6 é o mais pesado — recalcula variantes para 50 tickers × 104 semanas × 8 configurações).

---

## 13. Entregáveis

1. **`src/diagnostic.py`** — orquestrador
2. **`src/diagnostic_modules/macro.py`** — Módulo 1
3. **`src/diagnostic_modules/ic.py`** — Módulo 3 (IC + rolling + correlação)
4. **`src/diagnostic_modules/concentracao.py`** — Módulo 5
5. **`src/diagnostic_modules/tendencia.py`** — Módulo 6
6. **`src/diagnostic_modules/relatorio.py`** — gerador de relatório e hipóteses
7. **`data/diagnostic_report.json`** — dados estruturados
8. **`data/diagnostic_report.md`** — **entregável principal da Etapa 1**

---

## 14. O que fazer com o relatório (Etapa 2)

```
1. Ler diagnostic_report.md
   → Seção de hipóteses geradas automaticamente

2. Decidir quais hipóteses aceitar
   → Cada hipótese tem origem, evidência e ação sugerida

3. Abrir nova conversa com Claude:
   "Aqui está o diagnostic_report.md.
    Aceito as hipóteses X, Y e Z.
    Gere o spec V2 de PHASE3_SPEC e PROJECT_SPEC."

4. Specs V2 gerados com base em evidência real
   → Não em especulação
```

---

## 15. Riscos

| Risco | Probabilidade | Mitigação |
|---|---|---|
| `historico/scores_YYYY-MM-DD.json` faltando para algumas semanas | Média | Pular semana; logar gaps |
| IC com < 20 ações em alguma semana | Baixa | Filtro mínimo de 20 observações |
| Módulo 6 muito lento (> 10 min) | Baixa | Paralelizar com `concurrent.futures` se necessário |
| Variante T0 exige 200 pregões — menos semanas válidas que T1/T2/T3 | Média | Reportar `n_semanas` por variante; comparar só nas semanas comuns |
| Overfitting: V2 escolhida para maximizar período analisado | Alta (estrutural) | Documentar viés de seleção nos specs V2 |
