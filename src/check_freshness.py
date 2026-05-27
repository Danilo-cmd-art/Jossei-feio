"""
Fase 6 — Idempotência do pipeline.

Verifica se o último run já foi executado com sucesso nas últimas N horas.
Se sim, seta output 'skip=true' para o GitHub Actions evitar execução duplicada.
Usado para que o run das 20h BRT não refaça o trabalho do run das 19h BRT.

Uso:
  python src/check_freshness.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import config

JANELA = timedelta(hours=config.JANELA_FRESCOR_HORAS)


def verificar_frescor() -> bool:
    """Retorna True se os dados estão frescos (skip=true)."""
    summary_path = config.LAST_RUN_SUMMARY_PATH
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("last_run_summary.json não encontrado ou inválido — executar pipeline.")
        return False

    if summary.get("status") != "success":
        print(f"Último run não foi success (status={summary.get('status')}) — executar pipeline.")
        return False

    ts_str = summary.get("timestamp", "")
    if not ts_str:
        print("Sem timestamp — executar pipeline.")
        return False

    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        agora = datetime.now(timezone.utc)

        if (agora - ts) < JANELA:
            print(
                f"Dados frescos (último run: {ts_str}, janela={config.JANELA_FRESCOR_HORAS}h) "
                "— pulando pipeline."
            )
            return True
        else:
            print(f"Dados desatualizados (último run: {ts_str}) — executar pipeline.")
            return False
    except ValueError as e:
        print(f"Erro ao parsear timestamp '{ts_str}': {e} — executar pipeline.")
        return False


if __name__ == "__main__":
    # NUNCA falha — em caso de qualquer erro, retorna skip=false (executa o
    # pipeline) e exit 0. Step de idempotência NÃO pode bloquear o pipeline.
    try:
        skip = verificar_frescor()
    except Exception as e:
        print(f"Erro inesperado em check_freshness: {e!r} — assumindo skip=false.")
        skip = False

    valor = "true" if skip else "false"
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        try:
            with open(github_output, "a") as f:
                f.write(f"skip={valor}\n")
        except Exception as e:
            print(f"Falha ao escrever GITHUB_OUTPUT: {e!r} — pipeline seguira.")
    print(f"skip={valor}")
