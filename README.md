# SmallRadar V2 — Small Cap Momentum Tracker

Rastreador quantitativo de small caps brasileiras com fórmula V2.

![Pipeline](https://github.com/SEU-USUARIO/smallcap-tracker/actions/workflows/pipeline.yml/badge.svg)

---

## Fórmula V2

| Componente | Detalhe |
|---|---|
| Universo | 50 small caps, MCAP R$500M–15B |
| Filtro F1 | Tendência MMA20/50 ≥ 2/3 critérios |
| Filtro F2 | ROIC > 0% (ou ausente) |
| Fator A | Momentum 1m+3m — peso 50% |
| Fator B | ROE percentil — peso 30% |
| Fator C | CAGR receita 5a — peso 20% |
| Carteira | Top 5 equal-weight, rebalanceamento semanal |

---

## Estrutura do projeto

```
├── app.py                    # Streamlit (Fase 5)
├── run_v2.py                 # Orquestrador V2
├── config.py                 # Constantes
├── src/
│   ├── build_universe_v2.py  # Fase 1 V2 (manual mensal)
│   ├── fetch_prices.py       # Fase 2 (preços V1)
│   ├── scoring_v2.py         # Motor de scoring V2
│   ├── portfolio_v2.py       # Fase 3 V2
│   ├── backtest_v2.py        # Fase 4 V2
│   ├── check_freshness.py    # Fase 6 — idempotência
│   ├── update_historico_real.py  # Fase 7 — histórico ao vivo
│   └── check_pipeline_health.py  # Fase 7 — alertas
├── components/               # Fase 5 — UI Streamlit
│   ├── carteira.py           # Aba Carteira
│   ├── ranking.py            # Aba Ranking
│   ├── backtest.py           # Aba Backtest
│   └── historico.py          # Aba Histórico (Fase 7)
├── utils/
│   └── formatters.py
├── data/                     # Artefatos gerados (versionados)
│   ├── scores_atual_v2.json
│   ├── carteira_atual_v2.json
│   ├── backtest_resultado_v2.json
│   ├── precos_v2.parquet
│   ├── benchmarks.parquet
│   └── last_run_summary.json
├── historico/                # Histórico semanal/mensal
└── .github/workflows/
    └── pipeline.yml          # GitHub Actions (cron diário 19h+20h BRT)
```

---

## Execução local

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar pipeline completo V2 (Fases 2-4)
python run_v2.py

# Apenas scoring + carteira (Fase 3)
python run_v2.py --fase 3

# Atualizar universo V2 (mensal, manual — requer CSV do Status Invest)
python src/build_universe_v2.py

# Rodar app Streamlit
streamlit run app.py
```

---

## Deploy (Streamlit Community Cloud)

1. Faça push do repositório para o GitHub (branch `main`)
2. Acesse [share.streamlit.io](https://share.streamlit.io) com sua conta GitHub
3. "New app" → selecione o repositório → `Main file path: app.py`
4. Deploy — URL pública gerada automaticamente

O app é atualizado automaticamente a cada commit no `main`
(incluindo commits automáticos do GitHub Actions).

---

## Automação (GitHub Actions)

Pipeline roda automaticamente **segunda a sexta, 19h e 20h BRT**:

- **19h**: pipeline principal (Fases 2–4)
- **20h**: fallback se 19h falhou (verifica idempotência — não repete se dados frescos)
- **Sextas**: também atualiza `historico_real.json` (performance ao vivo)
- **Sempre**: verifica saúde do pipeline — abre GitHub Issue se falhar 2+ dias úteis

Para rodar manualmente: `GitHub → Actions → Pipeline Diário V2 → Run workflow`.

---

## Atualização mensal do universo (manual)

```bash
# 1. Exportar CSV do Status Invest (busca avançada, filtro MCAP R$500M–15B)
# 2. Salvar como statusinvest-busca-avancada.csv na raiz do projeto
# 3. Rodar:
python src/build_universe_v2.py

# 4. Commit:
git add universo_v2.json historico/universo_v2_YYYY-MM.json
git commit -m "chore: universo V2 atualizado YYYY-MM"
git push
```

---

## Disclaimer

Este sistema é uma ferramenta de estudo pessoal.
**Não constitui recomendação de investimento.**
Backtest possui survivorship bias e assume zero custos de transação.
