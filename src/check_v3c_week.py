"""
check_v3c_week.py — Determina se a próxima segunda-feira já tem carteira V3c
formada no `data/carteira_v3c_estado.json`.

Imprime:
  "yes"  → nova-semana DEVE rodar (estado ausente ou de semana anterior)
  "no"   → semana alvo já inicializada, nova-semana deve ser pulada

Uso típico (em workflow YAML):

  SHOULD_INIT=$(python src/check_v3c_week.py)
  if [ "$SHOULD_INIT" = "yes" ]; then
    python run_v3c.py --mode nova-semana
  fi

Lógica:
  - Calcula a próxima segunda-feira (se hoje é segunda, é hoje mesmo).
  - Lê `semana` do estado V3c. Se igual à semana ISO da próxima segunda → "no".
  - Caso contrário (estado ausente, corrompido ou de semana anterior) → "yes".
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import config


def segunda_relevante(hoje: datetime.date) -> datetime.date:
    """
    Retorna a segunda-feira da semana de pregão correspondente a `hoje`.

      - Segunda-Sexta : a segunda-feira da própria semana (esta semana).
      - Sábado-Domingo: a próxima segunda-feira.

    Lógica garante que durante a semana (ter-sex) o helper NÃO sinalize
    re-inicialização da semana que já está em curso.
    """
    wd = hoje.weekday()  # 0=Seg ... 6=Dom
    if wd <= 4:  # Seg-Sex → segunda desta semana
        return hoje - datetime.timedelta(days=wd)
    # Sáb/Dom → próxima segunda
    return hoje + datetime.timedelta(days=(7 - wd))


def main() -> None:
    hoje = datetime.date.today()
    alvo = segunda_relevante(hoje)
    semana_alvo = alvo.strftime("%G-W%V")

    estado_path = config.CARTEIRA_V3C_ESTADO_PATH
    if not estado_path.exists():
        print("yes")
        return

    try:
        with open(estado_path, encoding="utf-8") as f:
            estado = json.load(f)
    except Exception:
        print("yes")
        return

    semana_estado = estado.get("semana", "")
    print("no" if semana_estado == semana_alvo else "yes")


if __name__ == "__main__":
    main()
