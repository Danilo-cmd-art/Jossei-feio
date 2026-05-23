# PHASE 7 SPEC — Monitoramento Contínuo

> **Versão:** 1.0
> **Data:** 22/05/2026
> **Status:** Fase 7 fechada. Pronto para implementação.
> **Depende de:** todas as fases anteriores

---

## 1. Objetivo da fase

Acompanhar a performance **real** da estratégia semana a semana desde o início da operação — separada e honestamente distinta do backtest histórico — e garantir que o sistema avise quando parar de funcionar.

**Em uma frase:** transformar o sistema de "ferramenta de análise" em "ferramenta de acompanhamento contínuo", com registro permanente do que realmente aconteceu.

---

## 2. Decisões da Fase 7

| Decisão | Escolha |
|---|---|
| Onde exibir | **M1 — 4ª aba no Streamlit ("Histórico")** |
| Janela monitorada | **R2 — Rolling 3 meses** (janela deslizante) |
| Alerta de falha | **A1 — GitHub Issue automático** (2+ dias consecutivos de falha) |
| Conteúdo da aba | **C2 — Retorno acumulado + tabela de carteiras passadas** |
| Distinção backtest vs real | **D1 — Seções separadas com labels explícitos** |

---

## 3. Distinção fundamental: backtest vs performance real

Esta é a distinção mais importante da Fase 7 e deve ser visível em toda a interface.

| | Backtest (Fase 4) | Performance Real (Fase 7) |
|---|---|---|
| **Natureza** | Simulação histórica | Operação ao vivo |
| **Universo** | Congelado em mai/2026 | Universo vigente em cada semana |
| **Custos** | Zero (declarado) | Zero (idem — ferramenta teórica) |
| **Survivorship bias** | Presente (declarado) | Não se aplica (universo real do momento) |
| **Fonte** | `data/backtest_resultado.json` | `data/historico_real.json` (novo) |
| **Label na UI** | 🔬 Backtest histórico (simulação) | 📊 Performance real (ao vivo) |
| **Onde aparece** | Aba Backtest | Aba Histórico |

**Regra de ouro:** nunca concatenar as duas séries num único gráfico contínuo. O backtest termina onde a operação real começa.

---

## 4. Novo artefato: `data/historico_real.json`

Arquivo acumulado semana a semana desde a primeira carteira real (não-bootstrap).

### 4.1 Schema

```json
{
  "metadata": {
    "data_inicio_operacao": "2026-05-25",
    "total_semanas_reais": 12,
    "ultima_atualizacao": "2026-08-15"
  },
  "semanas": [
    {
      "semana": "2026-W22",
      "data_formacao": "2026-05-25",
      "data_corte_dados": "2026-05-22",
      "data_vigencia_fim": "2026-05-29",
      "bootstrap": false,
      "tickers": [
        {
          "ticker": "CEAB3",
          "rank_na_formacao": 1,
          "score_na_formacao": 87.32,
          "preco_entrada": 12.40,
          "preco_saida": 12.85,
          "retorno_semana": 0.0363
        }
      ],
      "n_posicoes": 5,
      "retorno_carteira": 0.0145,
      "retorno_ibov": 0.0072,
      "retorno_smll": 0.0089,
      "retorno_cdi": 0.0024,
      "alpha_vs_ibov": 0.0073,
      "alpha_vs_smll": 0.0056,
      "carteira_venceu_ibov": true,
      "carteira_venceu_smll": true
    }
  ],
  "acumulado": {
    "retorno_total": 0.087,
    "retorno_ibov_total": 0.041,
    "retorno_smll_total": 0.053,
    "retorno_cdi_total": 0.028,
    "win_rate_vs_ibov": 0.67,
    "win_rate_vs_smll": 0.58,
    "n_semanas_positivas": 8,
    "n_semanas_negativas": 4
  }
}
```

### 4.2 Política de acumulação

- Uma entrada por semana, adicionada na sexta (pós-fechamento)
- `retorno_carteira` = retorno equal-weight da semana (sexta / entrada na segunda - 1)
- `preco_saida` = `adj_close` da sexta da semana
- Semana de bootstrap (`bootstrap: true`) **é incluída** com label visual distinto
- Arquivo **nunca sobrescrito** — só append semanal
- Seção `acumulado` recalculada a cada append

### 4.3 Janela rolling 3 meses

- A aba Histórico exibe apenas as **últimas 13 semanas** (~3 meses)
- `historico_real.json` acumula **tudo** (histórico completo preservado)
- A janela rolling é aplicada **apenas na exibição** — não no armazenamento
- Razão: 3 meses é suficiente para avaliar tendência recente sem poluir a UI com dezenas de semanas

---

## 5. Pipeline — atualização semanal do histórico real

### 5.1 Novo script: `src/update_historico_real.py`

Rodado pelo GitHub Actions **toda sexta** (após o pipeline normal), como step adicional no `pipeline.yml`.

```python
"""
Atualiza historico_real.json com o resultado da semana encerrada.
Roda toda sexta após o fechamento.
Idempotente: não duplica se já existe entrada para a semana corrente.
"""
import json
import pandas as pd
from datetime import date, timedelta
from pathlib import Path

def get_semana_iso(data: date) -> str:
    return f"{data.isocalendar().year}-W{data.isocalendar().week:02d}"

def calcular_retorno_semana(carteira_json, df_precos):
    """Calcula retorno real da semana usando preços de entrada e saída."""
    retornos = []
    for t in carteira_json["tickers"]:
        ticker = t["ticker"]
        preco_entrada = t["preco_entrada"]
        
        data_fim = pd.Timestamp(carteira_json["metadata"]["data_vigencia_fim"])
        df_ticker = df_precos[df_precos["ticker"] == ticker]
        
        # Último pregão disponível até data_vigencia_fim
        df_semana = df_ticker[df_ticker["date"] <= data_fim]
        if df_semana.empty:
            continue
        
        preco_saida = df_semana["adj_close"].iloc[-1]
        retornos.append({
            "ticker": ticker,
            "rank_na_formacao": t["rank_na_formacao"],
            "score_na_formacao": t["score_na_formacao"],
            "preco_entrada": preco_entrada,
            "preco_saida": round(preco_saida, 2),
            "retorno_semana": round(preco_saida / preco_entrada - 1, 6)
        })
    
    return retornos

def append_semana(carteira_json, df_precos, benchmarks_json):
    hist_path = Path("data/historico_real.json")
    
    if hist_path.exists():
        with open(hist_path) as f:
            historico = json.load(f)
    else:
        historico = {
            "metadata": {
                "data_inicio_operacao": carteira_json["metadata"]["data_formacao"],
                "total_semanas_reais": 0,
                "ultima_atualizacao": str(date.today())
            },
            "semanas": [],
            "acumulado": {}
        }
    
    semana_id = get_semana_iso(
        date.fromisoformat(carteira_json["metadata"]["data_formacao"])
    )
    
    # Idempotência: não duplica se semana já existe
    semanas_existentes = {s["semana"] for s in historico["semanas"]}
    if semana_id in semanas_existentes:
        print(f"Semana {semana_id} já registrada — pulando.")
        return
    
    tickers_com_retorno = calcular_retorno_semana(carteira_json, df_precos)
    retorno_carteira = sum(t["retorno_semana"] for t in tickers_com_retorno) / len(tickers_com_retorno)
    
    # Benchmarks da semana
    data_inicio = carteira_json["metadata"]["data_vigencia_inicio"]
    data_fim = carteira_json["metadata"]["data_vigencia_fim"]
    ret_ibov = calcular_retorno_benchmark(benchmarks_json, "ibov", data_inicio, data_fim)
    ret_smll = calcular_retorno_benchmark(benchmarks_json, "smll", data_inicio, data_fim)
    ret_cdi  = calcular_retorno_benchmark(benchmarks_json, "cdi",  data_inicio, data_fim)
    
    entrada = {
        "semana": semana_id,
        "data_formacao": carteira_json["metadata"]["data_formacao"],
        "data_corte_dados": carteira_json["metadata"]["data_corte_dados"],
        "data_vigencia_fim": carteira_json["metadata"]["data_vigencia_fim"],
        "bootstrap": carteira_json["metadata"].get("bootstrap_retroativo", False),
        "tickers": tickers_com_retorno,
        "n_posicoes": carteira_json["metadata"]["n_posicoes"],
        "retorno_carteira": round(retorno_carteira, 6),
        "retorno_ibov": round(ret_ibov, 6),
        "retorno_smll": round(ret_smll, 6),
        "retorno_cdi": round(ret_cdi, 6),
        "alpha_vs_ibov": round(retorno_carteira - ret_ibov, 6),
        "alpha_vs_smll": round(retorno_carteira - ret_smll, 6),
        "carteira_venceu_ibov": retorno_carteira > ret_ibov,
        "carteira_venceu_smll": retorno_carteira > ret_smll
    }
    
    historico["semanas"].append(entrada)
    historico["acumulado"] = recalcular_acumulado(historico["semanas"])
    historico["metadata"]["total_semanas_reais"] = len(historico["semanas"])
    historico["metadata"]["ultima_atualizacao"] = str(date.today())
    
    with open(hist_path, "w") as f:
        json.dump(historico, f, indent=2, ensure_ascii=False)
    
    print(f"Semana {semana_id} registrada. Total: {len(historico['semanas'])} semanas.")
```

### 5.2 Integração no `pipeline.yml`

```yaml
      - name: Atualizar histórico real (sextas-feiras)
        if: steps.check_fresh.outputs.skip != 'true'
        run: |
          python -c "
          import datetime
          hoje = datetime.date.today()
          # 4 = sexta-feira
          if hoje.weekday() == 4:
              import subprocess
              subprocess.run(['python', 'src/update_historico_real.py'], check=True)
          else:
              print('Não é sexta — histórico real não atualizado hoje.')
          "
```

---

## 6. Aba Histórico — layout e componentes

### 6.1 Estrutura da aba

```
━━ 📊 Performance Real (ao vivo) ━━━━━━━━━━━━━━━━━━
Operação iniciada em: 25/05/2026 | Semanas registradas: 12
Janela exibida: últimas 13 semanas (~3 meses)

[4 métricas: retorno acumulado | win rate vs IBOV | win rate vs SMLL | semanas positivas]

[Gráfico de linha: Carteira vs IBOV vs SMLL vs CDI — base 100, rolling 3m]

[Tabela: semanas passadas com tickers, scores e retornos]

━━ 🔬 Backtest histórico (simulação) ━━━━━━━━━━━━━━
[Link/botão para a aba Backtest]
[Nota explicando a diferença]
```

### 6.2 Métricas do período rolling

4 `st.metric` em linha:

| Card | Valor exemplo |
|---|---|
| Retorno acumulado (3m) | +8,7% |
| Win rate vs IBOV | 67% das semanas |
| Win rate vs SMLL | 58% das semanas |
| Semanas positivas | 8 de 12 |

```python
def render_metricas_real(acumulado, semanas_rolling):
    n = len(semanas_rolling)
    win_ibov = sum(1 for s in semanas_rolling if s["carteira_venceu_ibov"]) / n
    win_smll = sum(1 for s in semanas_rolling if s["carteira_venceu_smll"]) / n
    pos = sum(1 for s in semanas_rolling if s["retorno_carteira"] > 0)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Retorno acumulado (3m)",
                f"{acumulado['retorno_total']*100:.1f}%")
    col2.metric("Win rate vs IBOV", f"{win_ibov*100:.0f}%",
                help="% de semanas em que a carteira superou o IBOV")
    col3.metric("Win rate vs SMLL", f"{win_smll*100:.0f}%",
                help="% de semanas em que a carteira superou o SMLL")
    col4.metric("Semanas positivas", f"{pos} de {n}")
```

### 6.3 Gráfico de performance real (rolling 3m)

- **Tipo:** linha Altair, base 100
- **Séries:** Carteira | IBOV | SMLL | CDI
- **X:** semana (data de vigência fim)
- **Y:** valor acumulado desde início da janela rolling (base 100)
- **Carteira em destaque** (linha mais grossa, azul)
- Semanas bootstrap marcadas com ponto diferenciado (◇ em vez de ●)

```python
def render_grafico_real(semanas_rolling):
    # Construir equity curve base 100 a partir das semanas rolling
    datas, cart, ibov, smll, cdi = [], [100.0], [100.0], [100.0], [100.0]
    
    for s in semanas_rolling:
        datas.append(s["data_vigencia_fim"])
        cart.append(cart[-1] * (1 + s["retorno_carteira"]))
        ibov.append(ibov[-1] * (1 + s["retorno_ibov"]))
        smll.append(smll[-1] * (1 + s["retorno_smll"]))
        cdi.append(cdi[-1]  * (1 + s["retorno_cdi"]))
    
    # Monta DataFrame long e renderiza com Altair
    # (padrão idêntico ao gráfico da aba Backtest — ver Fase 5 §7.5)
    # Diferença: título = "Performance Real — Base 100 (últimas 13 semanas)"
```

### 6.4 Tabela de carteiras passadas

Colunas visíveis na tabela principal:

| Semana | Carteira | Retorno | vs IBOV | vs SMLL | Ganhou IBOV? |
|---|---|---|---|---|---|
| 2026-W22 | CEAB3, TEND3, … | +1,45% | +0,73% | +0,56% | ✅ |
| 2026-W23 | SOMA3, PRIO3, … | -0,82% | -0,31% | -0,15% | ❌ |

- Semanas bootstrap marcadas com `🔄` na coluna Semana
- Ordenada da mais recente para a mais antiga
- Retorno positivo em verde, negativo em vermelho (via `st.dataframe` com styling)
- Ao selecionar uma linha: expande os 5 tickers com score e retorno individual

```python
def render_tabela_historico(semanas_rolling):
    rows = []
    for s in semanas_rolling:
        tickers_str = ", ".join(t["ticker"] for t in s["tickers"])
        label_semana = f"🔄 {s['semana']}" if s.get("bootstrap") else s["semana"]
        rows.append({
            "Semana": label_semana,
            "Tickers": tickers_str,
            "Retorno": f"{s['retorno_carteira']*100:+.2f}%",
            "vs IBOV": f"{s['alpha_vs_ibov']*100:+.2f}%",
            "vs SMLL": f"{s['alpha_vs_smll']*100:+.2f}%",
            "Ganhou IBOV": "✅" if s["carteira_venceu_ibov"] else "❌"
        })
    
    df = pd.DataFrame(rows)
    event = st.dataframe(df, hide_index=True, use_container_width=True,
                         on_select="rerun", selection_mode="single-row")
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        semana_sel = semanas_rolling[-(idx+1)]  # mais recente primeiro
        with st.expander(f"Detalhes — {semana_sel['semana']}", expanded=True):
            render_detalhes_semana(semana_sel)

def render_detalhes_semana(semana):
    rows = [{
        "Ticker": t["ticker"],
        "Score": f"{t['score_na_formacao']:.1f}",
        "Entrada": f"R${t['preco_entrada']:.2f}",
        "Saída": f"R${t['preco_saida']:.2f}",
        "Retorno": f"{t['retorno_semana']*100:+.2f}%"
    } for t in semana["tickers"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
```

### 6.5 Separador visual backtest vs real

No final da seção de performance real:

```python
st.divider()
st.markdown("### 🔬 Backtest histórico (simulação)")
st.info(
    "O backtest histórico (simulação retroativa de 2 anos) está disponível "
    "na aba **Backtest**. São dados diferentes: o backtest usa universo congelado "
    "e zero custos. A performance real acima é o que aconteceu de fato semana a semana."
)
if st.button("→ Ver aba Backtest"):
    # Streamlit não suporta navegação entre abas via código nativamente.
    # Alternativa: instruir o usuário visualmente.
    st.caption("Clique na aba 'Backtest' no topo da página.")
```

---

## 7. Alerta de falha do pipeline — GitHub Issue automático

### 7.1 Lógica

Se o pipeline falhar por **2 ou mais dias úteis consecutivos**, o workflow abre um GitHub Issue automaticamente.

### 7.2 Novo script: `src/check_pipeline_health.py`

```python
"""
Verifica saúde do pipeline consultando last_run_summary.json.
Se falha consecutiva >= 2 dias úteis, abre GitHub Issue via API.
"""
import json
import os
import requests
from datetime import date, timedelta
from pathlib import Path

LIMITE_DIAS_FALHA = 2

def contar_dias_uteis_desde(data_str: str) -> int:
    """Conta dias úteis entre data_str e hoje."""
    inicio = date.fromisoformat(data_str[:10])
    hoje = date.today()
    dias = 0
    atual = inicio + timedelta(days=1)
    while atual <= hoje:
        if atual.weekday() < 5:  # segunda a sexta
            dias += 1
        atual += timedelta(days=1)
    return dias

def abrir_issue(titulo: str, corpo: str):
    token = os.environ.get("GITHUB_TOKEN")
    repo  = os.environ.get("GITHUB_REPOSITORY")  # "usuario/repo"
    
    if not token or not repo:
        print("GITHUB_TOKEN ou GITHUB_REPOSITORY não definidos — pulando issue.")
        return
    
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github.v3+json"}
    payload = {"title": titulo, "body": corpo,
                "labels": ["pipeline-failure"]}
    
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 201:
        print(f"Issue criado: {resp.json()['html_url']}")
    else:
        print(f"Falha ao criar issue: {resp.status_code} {resp.text}")

def verificar_e_alertar():
    try:
        with open("data/last_run_summary.json") as f:
            summary = json.load(f)
    except FileNotFoundError:
        print("last_run_summary.json não encontrado — pipeline nunca rodou.")
        return
    
    status = summary.get("status", "unknown")
    if status == "success":
        print("Pipeline saudável.")
        return
    
    ts = summary.get("timestamp", "")
    dias_falha = contar_dias_uteis_desde(ts)
    
    if dias_falha >= LIMITE_DIAS_FALHA:
        titulo = f"🚨 Pipeline falhou por {dias_falha} dias úteis consecutivos"
        corpo = (
            f"**Status:** `{status}`\n"
            f"**Último run:** {ts}\n"
            f"**Dias úteis sem sucesso:** {dias_falha}\n\n"
            f"Verificar a aba [Actions]"
            f"(https://github.com/{os.environ.get('GITHUB_REPOSITORY')}/actions) "
            f"para detalhes do erro.\n\n"
            f"---\n*Issue gerado automaticamente pelo pipeline.*"
        )
        abrir_issue(titulo, corpo)
    else:
        print(f"Falha recente ({dias_falha} dia(s)) — abaixo do limite de {LIMITE_DIAS_FALHA}.")

if __name__ == "__main__":
    verificar_e_alertar()
```

### 7.3 Integração no `pipeline.yml`

```yaml
      - name: Verificar saúde do pipeline e alertar se necessário
        if: always()   # roda mesmo se steps anteriores falharam
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}  # token automático do Actions
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python src/check_pipeline_health.py
```

**Nota:** `secrets.GITHUB_TOKEN` é provido automaticamente pelo GitHub Actions — não precisa configurar nada.

### 7.4 Comportamento

- Issue é aberto **uma vez** (não duplica a cada run)
- Para evitar duplicatas: antes de abrir, verifica se já existe issue aberto com o label `pipeline-failure`
- Quando pipeline voltar a funcionar: issue é fechado automaticamente

```python
def issue_ja_aberto(repo: str, token: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github.v3+json"}
    params = {"labels": "pipeline-failure", "state": "open"}
    resp = requests.get(url, headers=headers, params=params)
    return len(resp.json()) > 0

def fechar_issues_pipeline(repo: str, token: str):
    """Fecha issues de falha quando pipeline volta ao normal."""
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github.v3+json"}
    params = {"labels": "pipeline-failure", "state": "open"}
    issues = requests.get(url, headers=headers, params=params).json()
    for issue in issues:
        patch_url = f"https://api.github.com/repos/{repo}/issues/{issue['number']}"
        requests.patch(patch_url, json={"state": "closed"}, headers=headers)
        print(f"Issue #{issue['number']} fechado (pipeline recuperado).")
```

---

## 8. Estrutura de arquivos da Fase 7

```
projeto/
├── .github/
│   └── workflows/
│       └── pipeline.yml            ← atualizado (step de sexta + health check)
├── src/
│   ├── update_historico_real.py    ← novo (Fase 7)
│   └── check_pipeline_health.py   ← novo (Fase 7)
├── components/
│   └── historico.py                ← novo (Fase 7, aba Histórico)
├── data/
│   └── historico_real.json         ← novo (Fase 7, acumula semanas reais)
└── app.py                          ← atualizado (adiciona 4ª aba)
```

---

## 9. Atualização do `app.py` (4ª aba)

```python
# app.py — versão Fase 7
tab1, tab2, tab3, tab4 = st.tabs(["Carteira", "Ranking", "Backtest", "Histórico"])

with tab1:
    from components.carteira import render_aba_carteira
    render_aba_carteira()

with tab2:
    from components.ranking import render_aba_ranking
    render_aba_ranking()

with tab3:
    from components.backtest import render_aba_backtest
    render_aba_backtest()

with tab4:
    from components.historico import render_aba_historico
    render_aba_historico()
```

---

## 10. Decisões da Fase 7 (registro histórico)

| Decisão | Escolha | Alternativas consideradas |
|---|---|---|
| Onde exibir | M1 — 4ª aba "Histórico" | M2 seções na aba Backtest; M3 página separada |
| Janela exibida | R2 — Rolling 3 meses (13 semanas) | R1 desde o início; filtro configurável |
| Armazenamento | Acumulado completo em `historico_real.json` | Só janela rolling; banco de dados |
| Conteúdo | C2 — Gráfico acumulado + tabela de semanas | C1 só gráfico; C3 + métricas rolling |
| Distinção backtest/real | D1 — Seções separadas, labels explícitos | D2 equity curve única concatenada |
| Alerta de falha | A1 — GitHub Issue automático (2+ dias) | A2 e-mail; A3 monitoramento manual |
| Idempotência do append | Verificação por `semana_id` antes de inserir | Sem controle (risco de duplicata) |
| Fechamento de issue | Automático quando pipeline volta ao normal | Manual |

---

## 11. Entregáveis da Fase 7 (a implementar)

1. **`src/update_historico_real.py`** — append semanal de sextas ao histórico real
2. **`src/check_pipeline_health.py`** — abre/fecha GitHub Issues de falha
3. **`components/historico.py`** — aba Histórico completa
4. **`data/historico_real.json`** — criado na primeira sexta de operação real
5. **`.github/workflows/pipeline.yml`** — atualizado com 2 novos steps

---

## 12. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| `historico_real.json` corrompido por append mal formado | Baixa | Alto | Escrever em arquivo temp e renomear (escrita atômica) |
| Issue duplicado aberto a cada run com falha | Média | Baixo | `issue_ja_aberto()` verifica antes de criar |
| `GITHUB_TOKEN` sem permissão para criar issues | Baixa | Médio | Token automático do Actions tem permissão por padrão; verificar `Settings → Actions → Workflow permissions` |
| Semana bootstrap aparece como performance real sem aviso | Baixa | Médio | Label `🔄` explícito na tabela + campo `bootstrap: true` no JSON |
| Rolling 3m com menos de 13 semanas no início | Certa (início de operação) | Baixo | Exibir todas as semanas disponíveis + caption "X semanas registradas (operação iniciada em DD/MM)" |

---

## 13. Estado final do projeto (todas as fases)

```
✅ Fase 0 — Definições estratégicas (PROJECT_SPEC.md v1.1)
✅ Fase 1 — Universo operacional (PHASE1_SPEC.md v1.0)
✅ Fase 2 — Pipeline de preços + Bootstrap (PHASE2_SPEC.md v1.1)
✅ Fase 3 — Motor de Scoring + Carteira (PHASE3_SPEC.md v1.0)
✅ Fase 4 — Backtest histórico (PHASE4_SPEC.md v1.0)
✅ Fase 5 — Frontend Streamlit (PHASE5_SPEC.md v1.0)
✅ Fase 6 — Automação e Deploy (PHASE6_SPEC.md v1.0)
✅ Fase 7 — Monitoramento Contínuo (PHASE7_SPEC.md v1.0)
```

**Stack final consolidado:**
- Backend: Python (yfinance, pandas, pyarrow)
- Frontend: Streamlit + Altair
- Storage: Parquet (preços) + JSON (artefatos e histórico)
- Agendamento: GitHub Actions (cron diário 19h + 20h BRT)
- Hospedagem: Streamlit Community Cloud
- Custo operacional: R$ 0
