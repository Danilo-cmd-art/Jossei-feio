"""Helpers de formatação compartilhados entre componentes."""
from __future__ import annotations

from datetime import date


def fmt_pct(v: float | None, casas: int = 2, sinal: bool = False) -> str:
    """Formata número como porcentagem. Ex: 0.1362 → '+13.62%'"""
    if v is None:
        return "n/d"
    s = f"{v * 100:.{casas}f}%"
    if sinal and v >= 0:
        s = "+" + s
    return s


def fmt_pct_delta(v: float | None) -> str:
    """Formata delta de porcentagem com sinal. Ex: 0.05 → '+5.00%'"""
    return fmt_pct(v, sinal=True)


def fmt_reais(v: float | None) -> str:
    """Formata como R$. Ex: 12.85 → 'R$12,85'"""
    if v is None:
        return "n/d"
    return f"R${v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_score(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}"


def fmt_data_br(iso: str | None) -> str:
    """'2026-05-22' → '22/05/2026'"""
    if not iso:
        return "—"
    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso


def fmt_semana(semana_iso: str) -> str:
    """'2026-W22' → 'Sem. 22/2026'"""
    try:
        ano, w = semana_iso.split("-W")
        return f"Sem. {w}/{ano}"
    except Exception:
        return semana_iso


def cor_retorno(v: float | None) -> str:
    """Retorna 'normal', 'verde' ou 'vermelho' baseado no sinal."""
    if v is None:
        return "normal"
    return "verde" if v >= 0 else "vermelho"
