"""
Fase 7 — Alerta de saúde do pipeline.

Abre um GitHub Issue se o pipeline falhar por 2+ dias úteis consecutivos.
Fecha issues de falha abertos quando o pipeline volta ao normal.

Executado sempre pelo GitHub Actions (mesmo se steps anteriores falharam).

Uso:
  python src/check_pipeline_health.py
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import config
from src.logger import get_logger

log = get_logger()

LIMITE_DIAS_FALHA = 2


# ---------------------------------------------------------------------------
# Contagem de dias úteis
# ---------------------------------------------------------------------------

def _dias_uteis_desde(data_str: str) -> int:
    """Dias úteis (seg–sex) entre data_str e hoje."""
    try:
        inicio = date.fromisoformat(data_str[:10])
    except ValueError:
        return 0

    hoje = date.today()
    dias = 0
    atual = inicio + timedelta(days=1)
    while atual <= hoje:
        if atual.weekday() < 5:
            dias += 1
        atual += timedelta(days=1)
    return dias


# ---------------------------------------------------------------------------
# GitHub Issues API
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _issue_ja_aberto(repo: str, token: str) -> bool:
    try:
        import requests
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/issues",
            headers=_headers(token),
            params={"labels": "pipeline-failure", "state": "open"},
            timeout=15,
        )
        return len(resp.json()) > 0
    except Exception as e:
        log.warning(f"Erro ao verificar issues abertos: {e}")
        return False


def _abrir_issue(repo: str, token: str, titulo: str, corpo: str) -> None:
    if _issue_ja_aberto(repo, token):
        log.info("Issue de falha já aberto — não duplica.")
        return
    try:
        import requests
        resp = requests.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers=_headers(token),
            json={"title": titulo, "body": corpo, "labels": ["pipeline-failure"]},
            timeout=15,
        )
        if resp.status_code == 201:
            log.info(f"Issue criado: {resp.json()['html_url']}")
        else:
            log.warning(f"Falha ao criar issue: {resp.status_code}")
    except Exception as e:
        log.warning(f"Erro ao abrir issue: {e}")


def _fechar_issues_pipeline(repo: str, token: str) -> None:
    try:
        import requests
        resp = requests.get(
            f"https://api.github.com/repos/{repo}/issues",
            headers=_headers(token),
            params={"labels": "pipeline-failure", "state": "open"},
            timeout=15,
        )
        for issue in resp.json():
            num = issue["number"]
            requests.patch(
                f"https://api.github.com/repos/{repo}/issues/{num}",
                headers=_headers(token),
                json={"state": "closed"},
                timeout=15,
            )
            log.info(f"Issue #{num} fechado (pipeline recuperado).")
    except Exception as e:
        log.warning(f"Erro ao fechar issues: {e}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def verificar_e_alertar() -> None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    summary_path = config.LAST_RUN_SUMMARY_PATH
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
    except FileNotFoundError:
        log.warning("last_run_summary.json não encontrado — pipeline nunca rodou.")
        return

    status = summary.get("status", "unknown")

    if status == "success":
        log.info("Pipeline saudável.")
        if token and repo:
            _fechar_issues_pipeline(repo, token)
        return

    ts = summary.get("timestamp", "")
    dias_falha = _dias_uteis_desde(ts)

    log.warning(
        f"Pipeline em falha (status={status}) há {dias_falha} dia(s) útil(eis). "
        f"Limite: {LIMITE_DIAS_FALHA}."
    )

    if dias_falha >= LIMITE_DIAS_FALHA:
        if not token or not repo:
            log.warning(
                "GITHUB_TOKEN ou GITHUB_REPOSITORY não definidos — "
                "não é possível abrir Issue."
            )
            return

        titulo = f"🚨 Pipeline falhou por {dias_falha} dias úteis consecutivos"
        corpo = (
            f"**Status:** `{status}`\n"
            f"**Último run:** {ts}\n"
            f"**Dias úteis sem sucesso:** {dias_falha}\n\n"
            f"Verificar a aba "
            f"[Actions](https://github.com/{repo}/actions) para detalhes.\n\n"
            f"---\n*Issue gerado automaticamente pelo pipeline SmallRadar V2.*"
        )
        _abrir_issue(repo, token, titulo, corpo)
    else:
        log.info(f"Falha recente ({dias_falha} dia(s)) — abaixo do limite de {LIMITE_DIAS_FALHA}.")


if __name__ == "__main__":
    verificar_e_alertar()
