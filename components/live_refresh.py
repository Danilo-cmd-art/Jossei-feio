"""
Live refresh — polling client-side via Streamlit.

Inclui também detecção de JSONs corrompidos (markers de conflict git
deixados por git stash pop com conflito). Se detectado, mostra erro
VISÍVEL no site em vez de cair em fallback silencioso (W21 ao invés W22).

Como funciona:
  • st_autorefresh() força um rerun completo da página a cada N segundos.
  • A cada rerun, _trigger_intraday_se_stale() verifica a idade dos dados.
  • Se a última atualização for mais antiga que LIMITE_STALE_SEGUNDOS,
    executa `python run_v3c.py --mode intraday` em subprocess.
  • Após o intraday, os caches @st.cache_data (ttl=60s) ficam stale e os
    componentes recarregam dados frescos automaticamente.

Independente do cron do GitHub Actions:
  • Funciona enquanto alguém tiver o site aberto no browser.
  • Sem cron, o navegador é o "trigger".
  • Cada visitante ativo atualiza os dados; outros visitantes pegam o
    estado mais fresco no próximo rerun.

Idempotência:
  • run_v3c.py --mode intraday é seguro de rodar várias vezes seguidas.
  • Atualiza apenas state + parquet + historico (não muda carteira).
  • Múltiplos visitantes simultâneos podem disparar simultaneamente —
    último escrito ganha (não há corrida destrutiva).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st

import config


# ---------------------------------------------------------------------------
# Detecção defensiva de JSONs corrompidos (markers de conflict)
# ---------------------------------------------------------------------------

_CONFLICT_MARKER_PATTERN = re.compile(
    r"^(<{7}|={7}|>{7})", flags=re.MULTILINE
)


def _arquivos_corrompidos() -> list[tuple[str, str]]:
    """
    Retorna lista de (caminho, motivo) de arquivos JSON críticos que
    estão corrompidos por:
      • markers de conflict git (<<<<<<< / ======= / >>>>>>>)
      • JSON parse inválido
    """
    paths_criticos = [
        config.CARTEIRA_V3C_ESTADO_PATH,
        *config.HISTORICO_DIR.glob("carteira_2026-W*.json"),
    ]
    problemas: list[tuple[str, str]] = []
    for p in paths_criticos:
        path = Path(p)
        if not path.exists() or path.name.startswith("carteira_v2_"):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            problemas.append((str(path), f"Erro leitura: {e!r}"))
            continue
        if _CONFLICT_MARKER_PATTERN.search(content):
            problemas.append((str(path), "Markers de merge conflict (<<<<<<< / =======)"))
            continue
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            problemas.append((str(path), f"JSON invalido: {e!s}"))
    return problemas


def verificar_integridade_dados() -> None:
    """
    Bloqueia a renderização do site se houver JSONs corrompidos —
    mostra mensagem clara em vez do fallback silencioso.
    Chamar uma vez no app.py logo após configurar_polling().
    """
    problemas = _arquivos_corrompidos()
    if not problemas:
        return

    st.error("**⚠ Detectado problema de integridade nos dados**", icon=None)
    for caminho, motivo in problemas:
        st.markdown(f"• `{caminho}` — {motivo}")
    st.markdown(
        """
        **Causa típica:** git stash pop com conflito deixou markers
        (`<<<<<<<` / `=======` / `>>>>>>>`) ou JSON malformado.

        **Como resolver localmente:**
        ```
        python -c "import re,pathlib; p=pathlib.Path('arquivo.json');
                  p.write_text(re.sub(r'<<<<<<< Updated upstream\\n(.*?)\\n=======\\n(.*?)\\n>>>>>>> Stashed changes\\n',
                                       r'\\2\\n', p.read_text(), flags=re.DOTALL))"
        rm historico/carteira_<semana>.json
        python run_v3c.py --mode intraday
        ```
        Depois `git commit` + `git push`.
        """
    )
    st.stop()


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

INTERVALO_AUTOREFRESH_SEGUNDOS = 300   # rerun da página a cada 5 min
LIMITE_STALE_SEGUNDOS          = 300   # dispara intraday se dados > 5 min

# Caminhos checados para determinar "idade" dos dados
_PATHS_FRESCOR = [
    config.CARTEIRA_V3C_ESTADO_PATH,
    config.BENCHMARKS_PARQUET_PATH,
]


# ---------------------------------------------------------------------------
# Idade dos dados
# ---------------------------------------------------------------------------

def _idade_dados_segundos() -> int | None:
    """
    Retorna idade (segundos) do arquivo mais RECENTEMENTE modificado entre
    os de frescor monitorados. None se nenhum arquivo existir.
    """
    timestamps = []
    for p in _PATHS_FRESCOR:
        path = Path(p)
        if path.exists():
            timestamps.append(path.stat().st_mtime)
    if not timestamps:
        return None
    mais_recente = max(timestamps)
    return int(time.time() - mais_recente)


def _idade_humano(segundos: int) -> str:
    """Formata segundos como '2 min', '1h 03min', '34s'."""
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60} min"
    h = segundos // 3600
    m = (segundos % 3600) // 60
    return f"{h}h {m:02d}min"


# ---------------------------------------------------------------------------
# Trigger do intraday (subprocess)
# ---------------------------------------------------------------------------

def _trigger_intraday() -> tuple[bool, str]:
    """
    Executa `python run_v3c.py --mode intraday` em subprocess.
    Retorna (sucesso, mensagem). Timeout 90s.
    """
    try:
        repo_root = Path(__file__).parent.parent
        resultado = subprocess.run(
            [sys.executable, "run_v3c.py", "--mode", "intraday"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=90,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        ok = resultado.returncode == 0
        msg_tail = (resultado.stdout or resultado.stderr or "").strip().split("\n")[-1][:120]
        return ok, msg_tail
    except subprocess.TimeoutExpired:
        return False, "Timeout (90s)"
    except Exception as e:
        return False, f"Erro: {e!r}"


def _trigger_intraday_se_stale() -> dict:
    """
    Se idade dos dados > LIMITE_STALE_SEGUNDOS, dispara intraday.
    Retorna info dict com 'idade_segundos', 'acao', 'mensagem'.
    """
    idade = _idade_dados_segundos()
    if idade is None:
        return {"idade_segundos": None, "acao": "sem_dados",
                "mensagem": "Nenhum arquivo de dados encontrado."}

    if idade <= LIMITE_STALE_SEGUNDOS:
        return {"idade_segundos": idade, "acao": "fresco",
                "mensagem": f"Dados frescos ({_idade_humano(idade)})."}

    # Stale — dispara intraday
    # Usa session_state para evitar múltiplos triggers no mesmo rerun
    chave = "intraday_em_execucao"
    if st.session_state.get(chave):
        return {"idade_segundos": idade, "acao": "ja_em_execucao",
                "mensagem": "Intraday em execução por outro rerun."}

    st.session_state[chave] = True
    try:
        ok, msg = _trigger_intraday()
    finally:
        st.session_state[chave] = False

    # Limpar caches do Streamlit para recarregar dados frescos
    st.cache_data.clear()

    return {
        "idade_segundos": idade,
        "acao": "atualizado" if ok else "falhou",
        "mensagem": f"Intraday {'OK' if ok else 'FALHOU'}: {msg}",
    }


# ---------------------------------------------------------------------------
# Entry point — chamar de app.py
# ---------------------------------------------------------------------------

def configurar_polling() -> dict:
    """
    Ativa o polling client-side (auto-rerun da página + intraday on-stale).
    Chamar UMA VEZ no início do app.py, após set_page_config.

    Returns: dict com info sobre o último ciclo de refresh.
    """
    # 1. Auto-rerun da página a cada INTERVALO_AUTOREFRESH_SEGUNDOS
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(
            interval=INTERVALO_AUTOREFRESH_SEGUNDOS * 1000,  # ms
            key="live_refresh_tick",
        )
    except ImportError:
        # streamlit-autorefresh não instalado — segue sem auto-rerun
        pass

    # 2. Se dados stale, dispara intraday on-the-fly
    return _trigger_intraday_se_stale()


# ---------------------------------------------------------------------------
# Render do banner de status (chamar logo após header)
# ---------------------------------------------------------------------------

def render_banner_atualizacao(info: dict) -> None:
    """
    Mostra um banner discreto com:
      • Tempo desde a última atualização dos dados
      • Botão "Atualizar agora" para forçar refresh manual
    """
    idade = info.get("idade_segundos")
    acao  = info.get("acao", "")

    # Cor + ícone conforme acao
    if acao == "atualizado":
        cor, label = "#1F7A4B", "ATUALIZADO AGORA"
    elif acao == "falhou":
        cor, label = "#A02C2C", "FALHA NA ATUALIZAÇÃO"
    elif acao == "fresco":
        cor, label = "#7A7A7A", "DADOS FRESCOS"
    elif acao == "ja_em_execucao":
        cor, label = "#A86A1F", "ATUALIZANDO…"
    else:
        cor, label = "#7A7A7A", "—"

    idade_txt = _idade_humano(idade) if idade is not None else "—"

    col_msg, col_botao = st.columns([5, 1])
    with col_msg:
        st.markdown(
            f"""
            <div style='display:flex; align-items:center; gap:14px;
                        padding:8px 14px;
                        background:rgba(255,255,255,0.05);
                        border:1px solid rgba(255,255,255,0.08);
                        border-radius:6px;
                        margin-bottom:18px; font-size:0.78rem;'>
              <span style='color:{cor}; font-weight:600;
                           letter-spacing:0.6px;'>{label}</span>
              <span style='color:#C8D3E2;'>
                Última atualização:
                <b style='color:#FFFFFF;'>{idade_txt} atrás</b>
                · Próximo auto-refresh em até {INTERVALO_AUTOREFRESH_SEGUNDOS // 60} min
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_botao:
        if st.button("Atualizar agora", use_container_width=True,
                     key="btn_atualizar_manual"):
            with st.spinner("Buscando preços frescos do Yahoo Finance…"):
                ok, msg = _trigger_intraday()
                st.cache_data.clear()
            if ok:
                st.success(f"Atualizado: {msg}", icon=None)
            else:
                st.error(f"Falhou: {msg}", icon=None)
            st.rerun()
