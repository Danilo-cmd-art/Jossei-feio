"""Constantes centralizadas do projeto SmallRadar."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
HISTORICO_DIR = ROOT_DIR / "historico"
LOGS_DIR = ROOT_DIR / "logs"
SRC_DIR = ROOT_DIR / "src"

UNIVERSO_ATUAL_PATH = ROOT_DIR / "universo_atual.json"
BLACKLIST_PATH = ROOT_DIR / "blacklist.json"
PRECOS_PARQUET_PATH = DATA_DIR / "precos.parquet"
SCORES_ATUAL_PATH = DATA_DIR / "scores_atual.json"
CARTEIRA_ATUAL_PATH = DATA_DIR / "carteira_atual.json"
BENCHMARKS_PARQUET_PATH = DATA_DIR / "benchmarks.parquet"
LAST_RUN_SUMMARY_PATH = DATA_DIR / "last_run_summary.json"
BACKTEST_RESULTADO_PATH = DATA_DIR / "backtest_resultado.json"
BACKTEST_CARTEIRAS_PATH = DATA_DIR / "backtest_carteiras.json"

# CSV do Status Invest — caminho padrão (usuário pode sobrescrever via argumento)
STATUS_INVEST_CSV_DEFAULT = ROOT_DIR / "statusinvest-busca-avancada.csv"

# ---------------------------------------------------------------------------
# Fase 1 — Universo
# ---------------------------------------------------------------------------
MCAP_MIN = 500_000_000       # R$ 500M
MCAP_MAX = 5_000_000_000     # R$ 5B
UNIVERSO_ALVO = 50           # tickers no universo
UNIVERSO_MINIMO = 30         # mínimo aceitável antes de abortar

# Critérios de qualidade (Fase 1 §4)
Q1_HISTORICO_MINIMO = 504    # pregões (~2 anos)
Q2_RETORNOS_ABSURDOS_MAX = 2 # ocorrências de |retorno| > 50%
Q3_VOLUME_ZERO_MAX_PCT = 0.10
Q4_CLOSE_NAN_MAX_PCT = 0.01
Q5_RECENTE_MAX_DIAS = 7
CRITERIOS_APROVACAO_MINIMO = 4  # de 5

# Filtros automáticos de exclusão (Fase 1 §5)
F1_DRAWDOWN_LIMITE = -0.50
F2_VOL_ANUALIZADA_LIMITE = 1.00
F3_VOLUME_COLAPSADO_RATIO = 0.30
F4_PRECO_TRAVADO_VARIACAO = 0.02
F5_GAPS_PREGAO_MAX = 5

# ---------------------------------------------------------------------------
# Fase 2 — Coleta de preços
# ---------------------------------------------------------------------------
DIAS_HISTORICO_INICIAL = 504     # pregões (operação normal)
DIAS_HISTORICO_BACKTEST = 756    # pregões (para backtest — ~3 anos)
TAMANHO_LOTE_DOWNLOAD = 10
MAX_TENTATIVAS_RETRY = 3
BACKOFF_BASE_SEGUNDOS = 2
DIA_FULL_REFRESH = 6             # domingo (weekday())
DIAS_TOLERANCIA_STALE = 3
LIMITE_DEGRADED_PCT = 0.20
LIMITE_FAILED_PCT = 0.50

# ---------------------------------------------------------------------------
# Fase 3 — Scoring
# ---------------------------------------------------------------------------
JANELA_MOMENTUM_1M = 21
JANELA_MOMENTUM_3M = 63
JANELA_MOMENTUM_6M = 126
JANELA_MMA_CURTA = 50
JANELA_MMA_LONGA = 200

PESO_MOMENTUM = 0.35
PESO_TENDENCIA = 0.30
PESO_ROIC = 0.20
PESO_CAGR = 0.15

FILTRO_TENDENCIA_MINIMO = 2
PERCENTIL_MISSING_DEFAULT = 50.0
N_POSICOES_CARTEIRA_ALVO = 5

TICKER_REFERENCIA_CALENDARIO = "PETR4.SA"
TICKER_IBOV = "^BVSP"
TICKER_SMLL = "SMAL11.SA"  # ticker correto no Yahoo Finance (SMLL11 estava deslistado)
CODIGO_CDI_BCB = 12

# ---------------------------------------------------------------------------
# Fase 4 — Backtest
# ---------------------------------------------------------------------------
BACKTEST_JANELA_ANOS = 2
BACKTEST_DIAS_WARMUP = 252
BACKTEST_CUSTO_POR_TRADE = 0.0
BACKTEST_CDI_ANUALIZADO_FALLBACK = 0.105  # fallback se API BCB falhar

# ---------------------------------------------------------------------------
# Fórmula V2
# ---------------------------------------------------------------------------
MCAP_MAX_V2 = 15_000_000_000   # R$ 15B (expandido vs R$5B da V1)
UNIVERSO_ALVO_V2 = 300         # cap alto o suficiente para incluir todos os candidatos válidos

# Janelas de tendência V2
JANELA_MMA_V2_CURTA = 20       # MMA20 (vs MMA50 da V1)
JANELA_MMA_V2_MEDIA = 50       # MMA50 (vs MMA200 da V1)

# Janelas de momentum V2 (1m+3m, sem 6m)
JANELA_MOMENTUM_V2_1M = 21
JANELA_MOMENTUM_V2_3M = 63

# Pesos V2
PESO_V2_MOMENTUM = 0.50
PESO_V2_ROE      = 0.30
PESO_V2_CAGR     = 0.20

# Caminhos V2
UNIVERSO_V2_PATH          = ROOT_DIR / "universo_v2.json"
PRECOS_V2_PARQUET_PATH    = DATA_DIR / "precos_v2.parquet"
BACKTEST_V2_RESULTADO_PATH = DATA_DIR / "backtest_resultado_v2.json"
BACKTEST_V2_CARTEIRAS_PATH = DATA_DIR / "backtest_carteiras_v2.json"
SCORES_V2_ATUAL_PATH       = DATA_DIR / "scores_atual_v2.json"
CARTEIRA_V2_ATUAL_PATH     = DATA_DIR / "carteira_atual_v2.json"
HISTORICO_REAL_PATH        = DATA_DIR / "historico_real.json"

# Caminhos V3c
BACKTEST_V3C_RESULTADO_PATH = DATA_DIR / "backtest_resultado_v3c.json"
BACKTEST_V3C_CARTEIRAS_PATH = DATA_DIR / "backtest_carteiras_v3c.json"
CARTEIRA_V3C_ESTADO_PATH    = DATA_DIR / "carteira_v3c_estado.json"

# Automação (Fase 6)
JANELA_FRESCOR_HORAS = 2
