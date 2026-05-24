# Análise rigorosa do front-end — SmallRadar V2

Documento técnico baseado nas screenshots do site em produção (commit `fac015d`)
e leitura completa do código de `app.py`, `components/carteira.py`,
`components/backtest.py`, `components/header.py`, `components/footer.py`,
`components/theme.py`.

---

## 1. O que **funciona** e deve ser preservado

| # | Item | Por que funciona |
|---|------|------------------|
| 1 | Tipografia Source Serif Pro + Inter | Headlines serifadas dão o tom editorial-financeiro. Body em Inter é legível. |
| 2 | Tagline dourada `SMALL CAP EQUITY · BRAZIL` | Hierarquia clara, sinaliza posicionamento. |
| 3 | Status strip com dot colorido (`● OPERACIONAL`) | Discreto, profissional, substitui caixas coloridas exageradas. |
| 4 | Tabs com underline navy | Limpo, sem caixas, foco no conteúdo. |
| 5 | Cards de métrica com label uppercase tracked + valor em serifa | Boa legibilidade e elegância. |
| 6 | Paleta navy + dourado + escala de cinzas nos gráficos | Sóbrio, profissional, fácil leitura. |
| 7 | Subheaders com barra dourada lateral | Detalhe sutil que organiza visualmente. |
| 8 | Layout 2 abas (Carteira + Backtest) | Foco no essencial. |

---

## 2. O que **não funciona** — diagnóstico

### 2.1 Quebras de elegância (alta prioridade)

| # | Problema | Onde | Impacto |
|---|----------|------|---------|
| A1 | **Emojis nos labels dos cards** (`📊 RETORNO`, `💰 CARTEIRA`, `🏆 PINE4`, `📉 INTB3`) | `carteira.py` linhas 287/292/308/312 | Destoa completamente do tom editorial. |
| A2 | **Banner azul vivo** com `st.info()` (`🔄 Exibindo a última semana…`) | `carteira.py` 220-223 | Fundo `#cce5ff` saturado quebra a paleta sóbria. |
| A3 | **Delta verde com valor negativo** no card Carteira teórica (`↑ R$-156,82`) | `carteira.py` 294 | Streamlit infere "positivo" do sinal `↑`, mas valor é negativo. Visual contraditório. |
| A4 | **Aviso Legal extenso no footer** | `footer.py` | Usuário pediu "sem disclaimers desnecessários". |
| A5 | **Expander "Limitações do backtest"** com emoji `⚠️` e markdown extenso | `backtest.py` 192-210 | Mesmo motivo de A4. |
| A6 | **Fundo branco puro** (#FFFFFF) | `config.toml` | Goldman usa fundos quentes/levemente off-white. |
| A7 | **Coluna "Status" sempre "✅ Ativo"** | `carteira.py` 322 | Informação inútil ocupa espaço. |

### 2.2 Informações críticas faltando

| # | Faltando | Por que é importante |
|---|----------|----------------------|
| B1 | **Histórico semanal** (tabela das últimas semanas com retorno + benchmarks + valor da carteira teórica) | Usuário pediu explicitamente "registros semanais". Permite avaliar consistência. |
| B2 | **Próxima reponderação** (próxima segunda + countdown) | Usuário não sabe quando a carteira muda. |
| B3 | **Carteira teórica acumulada multi-semana** | Hoje só reflete UMA semana. Precisa compor (∏ (1+ret_i)) × R$10.000 ao longo de todas as semanas desde 18/05/2026. |
| B4 | **Variação Δ na tabela de posições** (preço entrada → atual em R$) | Hoje só mostra `Entrada` e `Atual` separados — usuário precisa fazer a conta. |
| B5 | **Tooltip explicando "Score (formação)"** | Termo técnico sem contexto. |

### 2.3 Redundâncias / ruído visual

| # | Redundância | Onde |
|---|-------------|------|
| C1 | Card `Carteira V2 -1.57%` em "Performance numérica" repete o destaque do topo | `carteira.py` 365 |
| C2 | Texto "Retorno acumulado" no eixo Y do gráfico semanal — já é óbvio pelo título | `carteira.py` 145 |
| C3 | Subtítulo "Performance acumulada da semana" + "Performance numérica" — dois subheaders consecutivos para a mesma seção lógica | `carteira.py` 341/345 |
| C4 | Labels finais do backtest se sobrepõem quando séries convergem (`+35.8%`, `+35.8%`, `+30.0%`, `+0.5%`) | `backtest.py` 96-113 |

### 2.4 Quebras menores de UX

| # | Problema |
|---|----------|
| D1 | Gráfico semanal e backtest têm baselines com `color="gray"` — visualmente desconectado da paleta theme. |
| D2 | "Limitações do backtest" usa markdown bold/asterisk dentro de expander — quebra a renderização limpa. |
| D3 | Sidebar sem indicar **versão** do app ou data de deploy. |

---

## 3. Plano de mudanças

### 3.1 Tema visual (`theme.py` + `config.toml`)

- **Background page**: `#FFFFFF` → `#FAFAF7` (off-white quente)
- **Sidebar**: `#F4F4F2` → `#EFEAE0` (marfim mais profundo)
- **Borders**: `#E5E5E5` → `#DDD8CE` (warm grey)
- **Card surface**: branco puro → `#FFFFFF` com borda warm `#DDD8CE`
- Adicionar paleta de **retorno semântico** (verde/vermelho sóbrios)
- Adicionar `--accent-deep`: `#7A6F4D` (dourado profundo para detalhes)

### 3.2 `carteira.py` — refatoração completa

- [A1] Remover **todos os emojis** dos labels. Substituir por:
  - Texto puro nos cards de métrica
  - Símbolos tipográficos (▲ ▼) usados via CSS, não Unicode emoji
- [A2] Banner do bootstrap → **tag discreta** no canto direito do header da seção (`Exibindo semana anterior` em cinza claro)
- [A3] Card Carteira teórica: lógica manual de delta (não passar para Streamlit) ou usar `delta_color="inverse"` quando aplicável
- [A7] Remover coluna **Status** (sempre "Ativo")
- [B1] Adicionar seção `Histórico semanal` (tabela das últimas 8 semanas)
- [B2] Adicionar tag `Próxima reponderação: Seg 25/05` no header
- [B3] Calcular carteira acumulada lendo TODOS os arquivos `historico/carteira*.json` desde 18/05
- [B4] Tabela: nova coluna `Δ` (variação em R$)
- [B5] Tooltip no header "Score" via column_config
- [C1] Consolidar "Performance numérica" — só **deltas vs benchmarks** (sem repetir Carteira V2)
- [C2] Eixo Y do gráfico: remover título "Retorno acumulado", deixar só o formato `.1%`
- [C3] Unificar em uma única seção `Performance da semana` com gráfico + cards de comparação juntos
- Tabela: retornos verde/vermelho sóbrios via column_config + delta_color

### 3.3 `backtest.py`

- Remover "Métricas principais" como subheader — virar apenas os 2 cards no topo
- Header em estilo editorial (período em caption tipográfico, não markdown bold)
- [A5] Remover expander de Limitações
- [C4] Resolver sobreposição de labels finais: stagger via `dy` calculado por ordem do retorno
- [D1] Baseline com cor `COLORS["muted_2"]` em vez de gray

### 3.4 `footer.py`

- [A4] Reduzir para **1 linha cinza claro** no fim da página:
  - `"Ferramenta de estudo. Não constitui recomendação de investimento."`
- Remover bloco com faixa dourada (era exagero)

### 3.5 `header.py`

- Adicionar **próxima execução** ao lado da última (ex: `Próxima · Seg 26/05 às 19:00`)
- Marca discreta `v2.1` no canto direito do header

### 3.6 Novas funções utilitárias

Em `components/carteira.py` (ou novo `components/historico_semanal.py`):

```python
def _carregar_historico_semanas() -> list[dict]:
    """Lê todos os arquivos historico/carteira*.json com performance.
    Retorna ordenado cronologicamente.
    """

def _calcular_carteira_acumulada(historicos: list[dict],
                                  valor_inicial: float = 10_000) -> list[dict]:
    """Chain dos retornos: V(t) = V(t-1) * (1 + ret_t).
    Retorna lista com {data_fim, retorno_semana, valor_carteira} por semana.
    """
```

---

## 4. Ordem de execução

1. **Theme**: atualizar `config.toml` + `theme.py` (paleta + CSS)
2. **Carteira**: refatoração completa (remover emojis, adicionar histórico, consolidar seções)
3. **Backtest**: limpeza + correção dos labels
4. **Footer**: redução drástica
5. **Header**: próxima execução
6. **Commit + push único**

---

*Documento gerado em 2026-05-23 como parte da terceira iteração de UI.*
