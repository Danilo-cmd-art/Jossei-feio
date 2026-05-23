# Prompt para Claude Code — Implementação da Fórmula V2

> **Como usar:** abra o Claude Code na raiz do projeto (onde já estão as Fases 1-4 codadas),
> anexe os documentos listados na seção "Documentos para anexar" e cole o prompt abaixo.

---

## Documentos para anexar

Anexar nesta ordem:

1. `PROJECT_SPEC.md` — visão geral do projeto e fórmula V1
2. `PHASE1_SPEC.md` — universo operacional (filtros de mcap, liquidez)
3. `PHASE2_SPEC.md` — pipeline de preços (precos.parquet, fetch_prices.py)
4. `PHASE3_SPEC.md` — motor de scoring V1 (scoring.py, portfolio.py)
5. `PHASE4_SPEC.md` — backtest histórico (backtest.py)
6. `DIAGNOSTIC_SPEC.md` — diagnóstico de performance (contexto das decisões da V2)

> Os specs das Fases 5-7 (frontend, automação, monitoramento) não são necessários
> para esta implementação — a V2 é exclusivamente backend.

---

## Prompt

Estou implementando a **fórmula V2** de um sistema de small cap tracker brasileiro.
As Fases 1-4 já estão codadas e funcionando. A V2 roda sobre a mesma engenharia
de dados — não reescreve nada do que existe.

**Regra principal:** não modificar nenhum arquivo existente das Fases 1-4.
Toda mudança da V2 vai em arquivos novos ou em parâmetros isolados.

---

## Contexto das decisões da V2

A fórmula V1 foi rodada em backtest e apresentou performance abaixo do benchmark
(IBOV/SMLL). A V2 corrige problemas identificados na V1:

**Problemas da V1:**
- Momentum e tendência eram redundantes (65% do peso no mesmo sinal)
- CAGR de receita de 5 anos desalinhado com horizonte semanal
- Filtro de tendência (MMA50/200) eliminava mais da metade do universo
- ROIC como score relativo era menos útil que como filtro de qualidade mínima

**Decisões da V2 (já fechadas — não reabrir):**

| Componente | V1 | V2 |
|---|---|---|
| Universo mcap | R$500M–5B | R$500M–15B |
| Filtro F1 | Tendência ≥ 2/3 MMA50/200 | Tendência ≥ 2/3 MMA20/50 |
| Filtro F2 | Não existia | ROIC > 0% (novo) |
| Fator A | Momentum 1m+3m+6m, peso 35% | Momentum 1m+3m, peso 50% |
| Fator B | Tendência MMA50/200, peso 30% | ROE percentil, peso 30% |
| Fator C | ROIC percentil, peso 20% | Crescimento receita 12m, peso 20% |
| Fator D | CAGR receita 5a, peso 15% | Removido |

---

## O que implementar

### 1. Ajuste no universo — `build_universe.py`

Localizar a constante de mcap máximo e alterar:

```python
# Trocar
MCAP_MAX = 5_000_000_000
# Por
MCAP_MAX = 15_000_000_000
```

Rodar `build_universe.py` para gerar novo `universo_atual.json`.
Logar quantos candidatos existem no novo range (esperado: ~250 vs ~135 anterior).

---

### 2. Novo arquivo — `src/scoring_v2.py`

Criar do zero. Não modificar `scoring.py`.

Deve implementar:

**Filtros de entrada (aplicados antes do score):**

```
F1 — Tendência MMA20/50:
    mma20 = média dos últimos 20 pregões de adj_close
    mma50 = média dos últimos 50 pregões de adj_close
    critérios = [preco > mma20, preco > mma50, mma20 > mma50]
    aprovado = sum(critérios) >= 2
    Ação se reprovado: ação descartada — não entra no score

F2 — ROIC mínimo:
    roic = campo "roic" do universo_atual.json
    aprovado = roic > 0
    Se roic ausente (None): aprovado por padrão (não elimina por missing)
    Ação se reprovado: ação descartada — não entra no score
```

**Fórmula de score (só para ações que passaram em F1 e F2):**

```
Fator A — Momentum (peso 50%):
    ret_1m = adj_close_hoje / adj_close_21_pregoes_atras - 1
    ret_3m = adj_close_hoje / adj_close_63_pregoes_atras - 1
    momentum_bruto = (ret_1m + ret_3m) / 2
    momentum_norm  = ranking percentil dentro do universo aprovado × 100

Fator B — ROE (peso 30%):
    roe = campo "roe" do universo_atual.json
    roe_norm = ranking percentil dentro do universo aprovado × 100
    Se ausente: percentil 50

Fator C — Crescimento receita 12m (peso 20%):
    cagr_12m = campo correspondente do universo_atual.json
    cagr_12m_norm = ranking percentil dentro do universo aprovado × 100
    Se ausente: percentil 50
    Fallback se campo não existir no CSV: usar cagr_receita_5a como proxy

score_v2 = 0.50 × momentum_norm + 0.30 × roe_norm + 0.20 × cagr_12m_norm
```

**Seleção da carteira:**
```
Top 5 por score_v2 entre as ações que passaram nos filtros F1 e F2
Equal-weight: 20% por posição
Se menos de 5 passarem nos filtros: carteira com N < 5 posições (mesmo comportamento da V1)
```

**Schema do output** (compatível com o que `backtest.py` espera):
```python
{
    "metadata": {
        "data_referencia": "YYYY-MM-DD",
        "data_corte_dados": "YYYY-MM-DD",
        "total_tickers_universo": 50,
        "total_aprovados_filtros": N,
        "universo_versao": "2026-05",
        "versao_formula": "v2"
    },
    "scores": [
        {
            "ticker": "CEAB3",
            "rank": 1,
            "score_final": 87.32,
            "passou_filtro_f1": True,
            "passou_filtro_f2": True,
            "passou_filtros_entrada": True,
            "fatores": {
                "momentum": {
                    "ret_1m": 0.082,
                    "ret_3m": 0.124,
                    "bruto": 0.103,
                    "normalizado": 92.0,
                    "contribuicao_score": 46.0
                },
                "roe": {
                    "bruto": 18.5,
                    "normalizado": 78.0,
                    "contribuicao_score": 23.4,
                    "is_missing": False
                },
                "cagr_receita": {
                    "bruto": 14.3,
                    "normalizado": 63.5,
                    "contribuicao_score": 12.7,
                    "is_missing": False,
                    "usando_fallback_5a": False
                }
            }
        }
    ]
}
```

**Garantia anti-look-ahead (obrigatória):**
```python
def calcular_scores_v2(df_precos, universo, data_corte):
    df_filtrado = df_precos[df_precos["date"] <= pd.Timestamp(data_corte)]
    assert df_filtrado["date"].max() <= pd.Timestamp(data_corte), \
        f"Look-ahead bias detectado: dados após {data_corte}"
    # ... resto do cálculo
```

---

### 3. Verificação dos campos no CSV do Status Invest

Antes de implementar, verificar quais campos estão disponíveis:

```python
import pandas as pd
df = pd.read_csv("statusinvest-busca-avancada.csv", sep=";", decimal=",")
print(df.columns.tolist())
```

Mapear:
- ROE → identificar nome exato da coluna
- Crescimento receita 12m → verificar se existe; se não, usar CAGR 5 anos como fallback
- ROIC → confirmar nome da coluna (já usado na V1)

Reportar o mapeamento encontrado antes de prosseguir com a implementação.

---

### 4. Ajuste no backtest — `backtest.py`

**Não modificar o arquivo original.** Criar `backtest_v2.py` copiando o original
e alterando:

```python
# Trocar import de scoring
from scoring_v2 import calcular_scores_v2 as calcular_scores

# Trocar nomes dos arquivos de output
OUTPUT_RESULTADO  = "data/backtest_resultado_v2.json"
OUTPUT_CARTEIRAS  = "data/backtest_carteiras_v2.json"

# Adicionar campo de versão no metadata
"versao_formula": "v2"
```

Rodar `backtest_v2.py` e confirmar que gera os dois arquivos de output.

---

### 5. Comparação V1 vs V2

Após o backtest V2 concluir, gerar tabela comparativa:

```python
import json

with open("data/backtest_resultado.json") as f:
    v1 = json.load(f)["metricas_estrategia"]
with open("data/backtest_resultado_v2.json") as f:
    v2 = json.load(f)["metricas_estrategia"]

metricas = [
    ("retorno_total",       "Retorno total"),
    ("retorno_anualizado",  "Retorno anualizado"),
    ("volatilidade_anualizada", "Volatilidade"),
    ("sharpe_ratio",        "Sharpe ratio"),
    ("max_drawdown",        "Max drawdown"),
    ("win_rate_semanal",    "Win rate semanal"),
    ("hit_rate_vs_smll",    "Hit rate vs SMLL"),
    ("beta_vs_ibov",        "Beta vs IBOV")
]

print(f"\n{'Métrica':<28} {'V1':>10} {'V2':>10} {'Delta':>10}")
print("-" * 60)
for campo, nome in metricas:
    val_v1 = v1.get(campo, 0)
    val_v2 = v2.get(campo, 0)
    delta  = val_v2 - val_v1
    sinal  = "+" if delta > 0 else ""
    print(f"{nome:<28} {val_v1:>10.3f} {val_v2:>10.3f} {sinal}{delta:>9.3f}")
```

---

## Ordem de execução

```
1. Verificar campos do CSV do Status Invest → reportar mapeamento
2. Ajustar MCAP_MAX em build_universe.py
3. Rodar build_universe.py → confirmar novo universo_atual.json
4. Criar scoring_v2.py → testar com data_corte manual antes de integrar
5. Criar backtest_v2.py → rodar backtest completo
6. Gerar tabela comparativa V1 vs V2
```

---

## Critério de sucesso

A implementação está correta quando:

- [ ] `universo_atual.json` tem tickers com mcap até R$15B
- [ ] `scoring_v2.py` aplica F1 (MMA20/50) e F2 (ROIC > 0%) antes do score
- [ ] Score usa apenas 3 fatores: momentum (1m+3m), ROE, crescimento 12m
- [ ] Assertion anti-look-ahead não dispara em nenhuma semana do backtest
- [ ] `backtest_resultado_v2.json` e `backtest_carteiras_v2.json` gerados
- [ ] Tabela comparativa V1 vs V2 impressa no terminal
- [ ] Arquivos originais da V1 intactos (não modificados)
