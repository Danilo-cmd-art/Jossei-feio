# Diagnostico de Performance V1 — 2026-05-23

> **Periodo analisado:** 2024-05-23 a 2026-05-23
> **Semanas:** 104
> **Spec versao:** 3.0

---

## Modulo 1 — Diagnostico Macro

### Retorno por subperiodo

| Periodo | Estrategia | IBOV | SMLL | Alpha vs IBOV | Alpha vs SMLL |
|---|---|---|---|---|---|
| Q1 (primeiros 6 meses) | -4.64% | 0.29% | -4.33% | -4.92% | -0.31% |
| Q2 (6-12 meses) | 4.39% | 6.96% | 13.66% | -2.57% | -9.26% |
| Q3 (12-18 meses) | 11.91% | 12.61% | 5.90% | -0.70% | +6.01% |
| Q4 (ultimos 6 meses) | -4.25% | 7.60% | -12.75% | -11.85% | +8.50% |

### Hit rate vs SMLL por semestre

| Semestre | Ganhou | Perdeu | Hit Rate |
|---|---|---|---|
| 2024-S1 | 2 | 3 | 40.0% |
| 2024-S2 | 14 | 13 | 51.8% |
| 2025-S1 | 15 | 11 | 57.7% |
| 2025-S2 | 15 | 11 | 57.7% |
| 2026-S1 | 9 | 11 | 45.0% |

---

## Modulo 3 — Information Coefficient (IC)

> IC calculado sobre excess return vs SMLL (nao retorno bruto).

### IC por fator

| Fator | IC Medio | IC Mediano | % Positivo | IR | Semaforo |
|---|---|---|---|---|---|
| momentum | 0.0056 | -0.0015 | 50.0% | 0.029 | VERMELHO (ruido) |
| tendencia | 0.0095 | 0.0263 | 53.8% | 0.057 | VERMELHO (ruido) |
| roic | 0.0650 | 0.0507 | 63.5% | 0.392 | VERDE (alpha consistente) |
| cagr_receita | 0.0248 | 0.0321 | 59.6% | 0.163 | AMARELO (sinal fraco) |
| score_final | 0.0313 | 0.0436 | 58.7% | 0.168 | AMARELO (sinal fraco) |

### IC Rolling 26 semanas — tendencia recente

| Fator | Tendencia (ultimos 6 meses) |
|---|---|
| momentum | ↓ caindo |
| tendencia | ↓ caindo |
| roic | ↓ caindo |
| cagr_receita | ↓ caindo |
| score_final | ↓ caindo |

### Correlacao Momentum x Tendencia

- **Correlacao media:** 0.772
- **Correlacao mediana:** 0.787
- **% semanas acima de 0.65:** 91.3%
- **Interpretacao:** REDUNDANTES — momentum e tendencia medem essencialmente o mesmo sinal

---

## Modulo 5 — Concentracao por Acao

### 10 maiores destruidores de valor

| Ticker | Aparicoes | Contrib. Total | Retorno Medio | Win Rate |
|---|---|---|---|---|
| TEND3 | 24 | -0.0663 | -1.38% | 54.2% |
| ARML3 | 6 | -0.0651 | -5.43% | 33.3% |
| PLPL3 | 15 | -0.0561 | -1.87% | 33.3% |
| CVCB3 | 4 | -0.0387 | -4.84% | 50.0% |
| INTB3 | 9 | -0.0283 | -1.57% | 22.2% |
| CEAB3 | 19 | -0.0279 | -0.73% | 47.4% |
| MOVI3 | 24 | -0.0275 | -0.57% | 41.7% |
| BEEF3 | 2 | -0.0247 | -6.16% | 0.0% |
| VLID3 | 3 | -0.0224 | -3.73% | 33.3% |
| VAMO3 | 2 | -0.0210 | -5.24% | 0.0% |

### 5 maiores geradores de valor

| Ticker | Aparicoes | Contrib. Total | Retorno Medio | Win Rate |
|---|---|---|---|---|
| PINE4 | 37 | +0.1110 | +1.50% | 70.3% |
| MDNE3 | 68 | +0.1060 | +0.78% | 57.4% |
| TFCO4 | 29 | +0.0858 | +1.48% | 69.0% |
| LAVV3 | 55 | +0.0615 | +0.56% | 58.2% |
| DESK3 | 33 | +0.0576 | +0.87% | 51.5% |

---

## Modulo 6 — Variantes de Tendencia e Momentum

### Tendencia (baseline V2 = T1)

| Variante | IC Medio | % Positivo | IR | N Semanas |
|---|---|---|---|---|
| T0 | 0.0058 | 53.8% | 0.035 | 104 |
| T1 | -0.0185 | 43.3% | -0.122 | 104 |
| T2 | -0.0139 | 50.0% | -0.089 | 104 |
| T3 | -0.0165 | 46.2% | -0.110 | 104 |

**Vencedora:** T0 | Ganho vs baseline: 131.4% | Recomenda mudanca: SIM
> Variante T0 tem IC 131% acima do baseline (0.0058 vs -0.0185) — recomendada para V2.

### Momentum (baseline V2 = M3)

| Variante | IC Medio | % Positivo | IR | N Semanas |
|---|---|---|---|---|
| M0 | 0.0054 | 49.0% | 0.028 | 104 |
| M1 | -0.0011 | 53.8% | -0.006 | 104 |
| M2 | 0.0013 | 51.0% | 0.007 | 104 |
| M3 | -0.0003 | 51.9% | -0.001 | 104 |

**Vencedora:** M0 | Ganho vs baseline: 2196.1% | Recomenda mudanca: SIM
> Variante M0 tem IC 2196% acima do baseline (0.0054 vs -0.0003) — recomendada para V2.

---

## Hipoteses para V2

> 10 hipotese(s) gerada(s) automaticamente.

### 1. Fator momentum nao gera alpha — e ruido

- **Origem:** Modulo 3 — IC momentum
- **Evidencia:** IC medio = 0.0056 (< 0.02)
- **Acao sugerida:** Remover ou reduzir peso de momentum drasticamente na V2

### 2. Fator tendencia nao gera alpha — e ruido

- **Origem:** Modulo 3 — IC tendencia
- **Evidencia:** IC medio = 0.0095 (< 0.02)
- **Acao sugerida:** Remover ou reduzir peso de tendencia drasticamente na V2

### 3. Fator momentum esta perdendo poder preditivo nos ultimos 6 meses

- **Origem:** Modulo 3 — IC rolling momentum
- **Evidencia:** IC rolling caindo nos ultimos 13 periodos
- **Acao sugerida:** Reduzir peso de momentum na V2; monitorar na operacao real

### 4. Fator tendencia esta perdendo poder preditivo nos ultimos 6 meses

- **Origem:** Modulo 3 — IC rolling tendencia
- **Evidencia:** IC rolling caindo nos ultimos 13 periodos
- **Acao sugerida:** Reduzir peso de tendencia na V2; monitorar na operacao real

### 5. Fator roic esta perdendo poder preditivo nos ultimos 6 meses

- **Origem:** Modulo 3 — IC rolling roic
- **Evidencia:** IC rolling caindo nos ultimos 13 periodos
- **Acao sugerida:** Reduzir peso de roic na V2; monitorar na operacao real

### 6. Fator cagr_receita esta perdendo poder preditivo nos ultimos 6 meses

- **Origem:** Modulo 3 — IC rolling cagr_receita
- **Evidencia:** IC rolling caindo nos ultimos 13 periodos
- **Acao sugerida:** Reduzir peso de cagr_receita na V2; monitorar na operacao real

### 7. Fator score_final esta perdendo poder preditivo nos ultimos 6 meses

- **Origem:** Modulo 3 — IC rolling score_final
- **Evidencia:** IC rolling caindo nos ultimos 13 periodos
- **Acao sugerida:** Reduzir peso de score_final na V2; monitorar na operacao real

### 8. Momentum e tendencia sao redundantes

- **Origem:** Modulo 3 — Correlacao momentum x tendencia
- **Evidencia:** Correlacao media = 0.77 (> 0.65)
- **Acao sugerida:** Manter tendencia so como filtro de entrada (ja decidido na V2) — confirma a decisao

### 9. Variante T0 gera mais alpha que MMA20/50 simples

- **Origem:** Modulo 6 — Variante tendencia
- **Evidencia:** Variante T0 tem IC 131% acima do baseline (0.0058 vs -0.0185) — recomendada para V2.
- **Acao sugerida:** Adotar T0 no score de tendencia da V2

### 10. Variante M0 gera mais alpha

- **Origem:** Modulo 6 — Variante momentum
- **Evidencia:** Variante M0 tem IC 2196% acima do baseline (0.0054 vs -0.0003) — recomendada para V2.
- **Acao sugerida:** Adotar M0 no calculo de momentum da V2

---

> **AVISO:** Este diagnostico usa os mesmos dados do backtest.
> Qualquer ajuste de formula baseado nestes resultados carrega risco de overfitting.
> A formula V2 deve ser validada em dados futuros (out-of-sample).