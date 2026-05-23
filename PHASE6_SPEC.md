# PHASE 6 SPEC — Automação e Deploy

> **Versão:** 1.0
> **Data:** 22/05/2026
> **Status:** Fase 6 fechada. Pronto para implementação.
> **Depende de:** todas as fases anteriores

---

## 1. Objetivo da fase

Colocar o sistema em produção de forma totalmente automatizada: pipeline backend rodando diariamente sem intervenção manual, app Streamlit sempre servindo dados atualizados, tudo hospedado gratuitamente no GitHub + Streamlit Community Cloud.

**Em uma frase:** apertar um botão uma vez e o sistema se atualiza sozinho todo dia pra sempre.

---

## 2. Arquitetura de produção

```
┌─────────────────────────────────────────────────────────┐
│                      GitHub                             │
│                                                         │
│  ┌─────────────────────┐    ┌────────────────────────┐  │
│  │   GitHub Actions    │    │    Repositório Git      │  │
│  │                     │    │                         │  │
│  │  cron 19h + 20h BRT │───▶│  data/*.json           │  │
│  │  roda pipeline      │    │  data/precos.parquet    │  │
│  │  commit artefatos   │    │  historico/*.json       │  │
│  └─────────────────────┘    └────────────┬────────────┘  │
└────────────────────────────────────────── │ ─────────────┘
                                            │ push detectado
                                            ▼
                          ┌─────────────────────────────┐
                          │  Streamlit Community Cloud  │
                          │                             │
                          │  app.py lê data/*.json      │
                          │  serve interface atualizada │
                          │  URL pública, acesso livre  │
                          └─────────────────────────────┘
```

---

## 3. Decisões da Fase 6

| Decisão | Escolha |
|---|---|
| Hospedagem | **H1 — Streamlit Community Cloud** (gratuito) |
| Agendamento | **A1 — GitHub Actions** (cron diário) |
| Horário | **19h00 BRT** (principal) + **20h00 BRT** (fallback) |
| Acesso | **P1 — Público** (link direto, sem senha) |
| Idempotência | Segunda execução verifica se dados já estão frescos antes de rodar |

### 3.1 Trade-offs honesto (H1 — Streamlit Community Cloud)
- ✅ Gratuito, zero config de servidor
- ✅ Deploy automático a cada commit no branch main
- ✅ HTTPS nativo, URL pública estável
- ❌ App "dorme" após ~1h sem acesso (~30s para acordar)
- ❌ Limite de recursos (1 CPU, 1GB RAM) — suficiente para este projeto
- ❌ Dados em Git (parquet + JSONs) — ok para <100MB, mas exige atenção ao crescimento

---

## 4. Estrutura do repositório

```
smallcap-tracker/                   ← raiz do repositório
├── .github/
│   └── workflows/
│       └── pipeline.yml            ← workflow do GitHub Actions
├── src/
│   ├── build_universe.py           ← Fase 1
│   ├── fetch_prices.py             ← Fase 2
│   ├── scoring.py                  ← Fase 3
│   ├── portfolio.py                ← Fase 3
│   ├── benchmarks.py               ← Fase 3
│   └── backtest.py                 ← Fase 4
├── components/                     ← Fase 5
│   ├── header.py
│   ├── carteira.py
│   ├── ranking.py
│   ├── backtest.py
│   └── footer.py
├── utils/
│   └── formatters.py
├── data/                           ← artefatos gerados (versionados no Git)
│   ├── scores_atual.json
│   ├── carteira_atual.json
│   ├── backtest_resultado.json
│   ├── last_run_summary.json
│   └── precos.parquet
├── historico/                      ← histórico mensal/semanal (versionado)
│   ├── universo_2026-05.json
│   ├── scores_2026-05-22.json
│   └── carteira_2026-W21.json
├── universo_atual.json             ← atualizado mensalmente pelo usuário
├── blacklist.json                  ← mantido manualmente
├── config.py                       ← todas as constantes
├── app.py                          ← entrada do Streamlit
├── requirements.txt
└── README.md
```

### 4.1 O que vai para o Git (e o que não vai)

| Arquivo | Git? | Razão |
|---|---|---|
| `data/*.json` | ✅ Sim | Streamlit lê direto do repo clonado |
| `data/precos.parquet` | ✅ Sim | Necessário para o app e para o pipeline incremental |
| `historico/*.json` | ✅ Sim | Auditoria, backtest |
| `logs/*.log` | ❌ Não | `.gitignore` — só ruído |
| `statusinvest-busca-avancada.csv` | ❌ Não | Upload manual mensal, não versionar |
| `__pycache__/` | ❌ Não | Padrão |

**Atenção ao tamanho do repo:** `precos.parquet` (~1MB) + `historico/` crescendo ~50KB/semana. Em 2 anos: ~5MB de histórico. Bem dentro dos limites do GitHub.

---

## 5. GitHub Actions — workflow

### 5.1 Arquivo: `.github/workflows/pipeline.yml`

```yaml
name: Pipeline Diário

on:
  schedule:
    # 19h00 BRT = 22h00 UTC (BRT = UTC-3)
    - cron: '0 22 * * 1-5'   # segunda a sexta, 22h UTC
    # 20h00 BRT = 23h00 UTC (fallback)
    - cron: '0 23 * * 1-5'
  workflow_dispatch:          # permite rodar manualmente pelo GitHub UI

jobs:
  pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 15       # aborta se travar

    steps:
      - name: Checkout do repositório
        uses: actions/checkout@v4
        with:
          fetch-depth: 1      # shallow clone, mais rápido

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'        # cache de dependências entre runs

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Verificar idempotência
        id: check_fresh
        run: python src/check_freshness.py
        # Se dados já estão frescos (rodou com sucesso nas últimas 2h):
        # seta output skip=true e o pipeline não roda novamente

      - name: Rodar pipeline (Fase 2 — preços)
        if: steps.check_fresh.outputs.skip != 'true'
        run: python src/fetch_prices.py

      - name: Rodar pipeline (Fase 3 — scoring + carteira)
        if: steps.check_fresh.outputs.skip != 'true'
        run: python src/scoring.py && python src/portfolio.py

      - name: Rodar pipeline (Fase 4 — backtest incremental)
        if: steps.check_fresh.outputs.skip != 'true'
        run: python src/backtest.py

      - name: Commit e push dos artefatos atualizados
        if: steps.check_fresh.outputs.skip != 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ historico/
          git diff --staged --quiet || git commit -m "chore: atualização automática $(date -u '+%Y-%m-%d %H:%M UTC')"
          git push
```

### 5.2 Lógica de idempotência — `src/check_freshness.py`

```python
"""
Verifica se o pipeline já rodou com sucesso recentemente.
Se sim, seta output 'skip=true' para evitar execução duplicada.
Usado para que o run das 20h não refaça trabalho do run das 19h.
"""
import json
import os
from datetime import datetime, timezone, timedelta

JANELA_FRESCOR_HORAS = 2

def check():
    try:
        with open("data/last_run_summary.json") as f:
            summary = json.load(f)
        
        if summary.get("status") != "success":
            print("Último run não foi success — executar pipeline")
            return False
        
        ts_str = summary.get("timestamp", "")
        ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        agora = datetime.now(timezone.utc)
        
        if (agora - ts) < timedelta(hours=JANELA_FRESCOR_HORAS):
            print(f"Dados frescos (último run: {ts_str}) — pulando pipeline")
            return True
        
        return False
    
    except (FileNotFoundError, KeyError, ValueError):
        return False

if __name__ == "__main__":
    skip = check()
    # Seta output para o GitHub Actions
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
        f.write(f"skip={'true' if skip else 'false'}\n")
```

### 5.3 Secrets necessários

O pipeline usa `yfinance` (Yahoo Finance, sem autenticação) e API pública do BCB — **nenhum secret necessário** para o pipeline padrão.

Se no futuro uma API exigir chave:

```yaml
# No workflow, acessar via:
env:
  MINHA_API_KEY: ${{ secrets.MINHA_API_KEY }}
```

Configurar em: `GitHub repo → Settings → Secrets and variables → Actions`.

---

## 6. Deploy no Streamlit Community Cloud

### 6.1 Passo a passo (único, feito uma vez)

1. Acessar [share.streamlit.io](https://share.streamlit.io) com conta GitHub
2. Clicar em "New app"
3. Selecionar:
   - **Repository:** `seu-usuario/smallcap-tracker`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Clicar "Deploy"
5. Em ~2 minutos: app disponível em `https://seu-usuario-smallcap-tracker.streamlit.app`

### 6.2 Auto-deploy

A cada commit no branch `main` (incluindo os commits automáticos do GitHub Actions), o Streamlit Community Cloud detecta a mudança e recarrega o app automaticamente em ~30 segundos.

### 6.3 Comportamento de "sleep"

- App dorme após ~1h sem acesso
- Acorda em ~30 segundos no primeiro acesso
- **Impacto prático:** nenhum para uso pessoal

### 6.4 Requisitos do Streamlit Community Cloud

- Arquivo `requirements.txt` na raiz (já existe)
- Arquivo `app.py` na raiz (já existe)
- Repositório público **ou** conta Streamlit com acesso a repo privado

---

## 7. Atualização mensal do universo (manual)

O CSV do Status Invest e a execução da Fase 1 (`build_universe.py`) são **manuais** — decisão da Fase 1. O fluxo:

```
1. Usuário acessa Status Invest → exporta CSV
2. Coloca o CSV na raiz do projeto (sobrescreve o anterior)
3. Roda localmente: python src/build_universe.py
4. Revisa blacklist.json se necessário
5. Commit e push:
   git add universo_atual.json blacklist.json historico/universo_YYYYMM.json
   git commit -m "chore: universo atualizado YYYY-MM"
   git push
6. GitHub Actions detecta push → pipeline automático já usa novo universo
```

**Lembrete:** o workflow do GitHub Actions **não** roda `build_universe.py` automaticamente — só as Fases 2-4. Universo é responsabilidade do usuário.

---

## 8. Execução manual (trigger on-demand)

Para rodar o pipeline fora do horário agendado (ex: após atualizar o universo):

```
GitHub repo → Actions → Pipeline Diário → Run workflow → Run workflow
```

Ou via CLI com GitHub CLI:
```bash
gh workflow run pipeline.yml
```

---

## 9. Monitoramento do pipeline

### 9.1 Onde ver os logs
- `GitHub repo → Actions → Pipeline Diário → [run específico]`
- Cada step tem output detalhado
- Em caso de falha: GitHub envia e-mail automático para o dono do repo

### 9.2 O que monitorar
- Status do último run (verde/vermelho na aba Actions)
- Badge de status no app (lê `last_run_summary.json` — Fase 5)
- Tamanho do repo crescendo acima de 500MB (improvável, mas monitorar)

### 9.3 Badge no README (opcional mas recomendado)

```markdown
![Pipeline](https://github.com/seu-usuario/smallcap-tracker/actions/workflows/pipeline.yml/badge.svg)
```

---

## 10. Configuração de fuso horário no cron

```yaml
# BRT = UTC-3 (sem horário de verão desde 2019)
# 19h00 BRT = 22h00 UTC → cron '0 22 * * 1-5'
# 20h00 BRT = 23h00 UTC → cron '0 23 * * 1-5'
# Apenas dias úteis (1-5 = segunda a sexta)
```

**Nota:** GitHub Actions usa UTC. O Brasil não adota mais horário de verão desde 2019, então BRT = UTC-3 é fixo o ano todo.

---

## 11. Configurações adicionais em `config.py`

```python
# config.py (acréscimos da Fase 6)

# Controle de idempotência
JANELA_FRESCOR_HORAS = 2    # segunda execução pula se dados < 2h

# Git commit automático
GIT_COMMIT_MESSAGE_TEMPLATE = "chore: atualização automática {timestamp}"

# Streamlit
STREAMLIT_APP_TITLE = "Small Cap Momentum Tracker"
```

---

## 12. Entregáveis da Fase 6 (a implementar)

1. **`.github/workflows/pipeline.yml`** — workflow completo com cron duplo
2. **`src/check_freshness.py`** — lógica de idempotência
3. **`.gitignore`** — logs, cache, CSV do Status Invest, `__pycache__`
4. **`README.md`** — instruções de deploy e uso
5. **Deploy inicial** no Streamlit Community Cloud (feito pelo usuário, 1 vez)

---

## 13. Decisões da Fase 6 (registro histórico)

| Decisão | Escolha | Alternativas consideradas |
|---|---|---|
| Hospedagem | H1 — Streamlit Community Cloud | H2 Render/Railway; H3 VPS |
| Agendamento | A1 — GitHub Actions | A2 cron local; A3 cron no servidor |
| Horário | 19h00 BRT (principal) + 20h00 BRT (fallback) | Único horário às 19h ou 21h |
| Idempotência | `check_freshness.py` — pula se dados < 2h | Sem controle; lock file |
| Acesso | P1 — Público | P2 protegido por senha |
| Universo mensal | Manual (fora do cron) | Automatizar com agendamento mensal |

---

## 14. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| GitHub Actions falha (Yahoo offline) | Baixa | Médio | Retry nativo no yfinance + run das 20h como fallback |
| Conflito de merge no git push automático | Muito baixa | Médio | Pipeline roda sequencialmente; sem edições manuais simultâneas em `data/` |
| Repo cresce além do limite GitHub (1GB) | Muito baixa | Alto | Monitorar; `precos.parquet` é sobrescrito (não acumula) |
| Streamlit Community Cloud muda política gratuita | Baixa | Alto | Migração para Render.com é drop-in (mesmo `app.py`) |
| App dorme e usuário acha que está quebrado | Média | Baixo | Documentar no README; badge de status no app |
| Run das 19h e 20h rodam simultaneamente | Muito baixa | Médio | `check_freshness.py` garante que o segundo pula |

---

## 15. Itens em aberto (para Fase 7)

- **Fase 7:** aba ou seção de monitoramento contínuo — performance real acumulada semana a semana desde o início da operação
- **Fase 7:** comparação rolling entre carteiras passadas e benchmarks
- **Fase 7:** alerta automático (e-mail ou GitHub Issue) se pipeline falha por 2+ dias consecutivos
