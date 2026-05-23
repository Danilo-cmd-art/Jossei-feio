"""
Gerador de relatório — Markdown e hipóteses automáticas para V2.
DIAGNOSTIC_SPEC §8-9.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Semáforo IC
# ---------------------------------------------------------------------------

def _semaforo_ic(ic_medio: float) -> str:
    if ic_medio > 0.05:
        return "VERDE (alpha consistente)"
    elif ic_medio > 0.02:
        return "AMARELO (sinal fraco)"
    elif ic_medio >= 0:
        return "VERMELHO (ruido)"
    else:
        return "VERMELHO DUPLO (fator invertido)"


# ---------------------------------------------------------------------------
# Hipóteses automáticas para V2
# ---------------------------------------------------------------------------

def gerar_hipoteses_v2(
    m3_ic: dict,
    m3_correlacao: dict,
    m3_rolling: dict,
    m5_contribuicao: list[dict],
    m6_tend_vencedora: dict,
    m6_mom_vencedora: dict,
) -> list[dict]:
    hipoteses: list[dict] = []

    # --- Módulo 3: IC por fator ---
    for fator, dados in m3_ic.items():
        if fator == "score_final":
            continue
        ic = dados.get("ic_medio", 0.0)
        if ic < 0:
            hipoteses.append({
                "origem": f"Modulo 3 — IC {fator}",
                "hipotese": f"Fator {fator} esta invertido — prejudica a carteira",
                "evidencia": f"IC medio = {ic:.4f} (negativo)",
                "acao_sugerida": f"Remover {fator} da formula V2",
            })
        elif ic < 0.02:
            hipoteses.append({
                "origem": f"Modulo 3 — IC {fator}",
                "hipotese": f"Fator {fator} nao gera alpha — e ruido",
                "evidencia": f"IC medio = {ic:.4f} (< 0.02)",
                "acao_sugerida": f"Remover ou reduzir peso de {fator} drasticamente na V2",
            })

    # --- Módulo 3: IC rolling ---
    for fator, dados in m3_rolling.items():
        if dados.get("tendencia_recente") == "caindo":
            hipoteses.append({
                "origem": f"Modulo 3 — IC rolling {fator}",
                "hipotese": f"Fator {fator} esta perdendo poder preditivo nos ultimos 6 meses",
                "evidencia": "IC rolling caindo nos ultimos 13 periodos",
                "acao_sugerida": f"Reduzir peso de {fator} na V2; monitorar na operacao real",
            })

    # --- Módulo 3: Correlação momentum-tendência ---
    corr = m3_correlacao.get("correlacao_media", 0.0)
    if corr > 0.65:
        hipoteses.append({
            "origem": "Modulo 3 — Correlacao momentum x tendencia",
            "hipotese": "Momentum e tendencia sao redundantes",
            "evidencia": f"Correlacao media = {corr:.2f} (> 0.65)",
            "acao_sugerida": (
                "Manter tendencia so como filtro de entrada (ja decidido na V2) — confirma a decisao"
            ),
        })

    # --- Módulo 5: Concentração ---
    destruidores = [a for a in m5_contribuicao if a["contribuicao_total"] < -0.02]
    if len(destruidores) <= 3 and sum(a["contribuicao_total"] for a in destruidores) < -0.05:
        tickers = [a["ticker"] for a in destruidores]
        hipoteses.append({
            "origem": "Modulo 5 — Concentracao",
            "hipotese": f"Acoes {tickers} concentram prejuizo desproporcional",
            "evidencia": f"Contribuicao total: {sum(a['contribuicao_total'] for a in destruidores):.3f}",
            "acao_sugerida": "Avaliar adicao a blacklist.json antes de rodar V2",
        })

    # --- Módulo 6: Variante de tendência ---
    if (m6_tend_vencedora.get("recomenda_mudanca")
            and m6_tend_vencedora.get("variante_vencedora") != "T1"):
        hipoteses.append({
            "origem": "Modulo 6 — Variante tendencia",
            "hipotese": (
                f"Variante {m6_tend_vencedora['variante_vencedora']} "
                "gera mais alpha que MMA20/50 simples"
            ),
            "evidencia": m6_tend_vencedora.get("motivo", ""),
            "acao_sugerida": (
                f"Adotar {m6_tend_vencedora['variante_vencedora']} "
                "no score de tendencia da V2"
            ),
        })

    # --- Módulo 6: Variante de momentum ---
    if m6_mom_vencedora.get("recomenda_mudanca"):
        hipoteses.append({
            "origem": "Modulo 6 — Variante momentum",
            "hipotese": (
                f"Variante {m6_mom_vencedora['variante_vencedora']} gera mais alpha"
            ),
            "evidencia": m6_mom_vencedora.get("motivo", ""),
            "acao_sugerida": (
                f"Adotar {m6_mom_vencedora['variante_vencedora']} "
                "no calculo de momentum da V2"
            ),
        })

    return hipoteses


# ---------------------------------------------------------------------------
# Gerador de Markdown
# ---------------------------------------------------------------------------

def gerar_markdown(relatorio: dict[str, Any]) -> str:
    meta = relatorio["metadata"]
    m1 = relatorio["modulo_1_macro"]
    m3 = relatorio["modulo_3_ic"]
    m5 = relatorio["modulo_5_concentracao"]
    m6 = relatorio["modulo_6_variantes"]
    hips = relatorio.get("hipoteses_v2", [])

    linhas: list[str] = []

    # Cabeçalho
    linhas += [
        f"# Diagnostico de Performance V1 — {meta['data_geracao']}",
        f"",
        f"> **Periodo analisado:** {meta['periodo']}",
        f"> **Semanas:** {meta['n_semanas_analisadas']}",
        f"> **Spec versao:** {meta['versao_spec']}",
        f"",
        f"---",
        f"",
    ]

    # Módulo 1
    linhas += [
        "## Modulo 1 — Diagnostico Macro",
        "",
        "### Retorno por subperiodo",
        "",
        "| Periodo | Estrategia | IBOV | SMLL | Alpha vs IBOV | Alpha vs SMLL |",
        "|---|---|---|---|---|---|",
    ]
    for nome, dados in m1.get("retorno_por_subperiodo", {}).items():
        linhas.append(
            f"| {nome} "
            f"| {dados['estrategia']:.2%} "
            f"| {dados['ibov']:.2%} "
            f"| {dados['smll']:.2%} "
            f"| {dados['alpha_vs_ibov']:+.2%} "
            f"| {dados['alpha_vs_smll']:+.2%} |"
        )

    linhas += [
        "",
        "### Hit rate vs SMLL por semestre",
        "",
        "| Semestre | Ganhou | Perdeu | Hit Rate |",
        "|---|---|---|---|",
    ]
    for sem, dados in m1.get("hit_rate_vs_smll_por_semestre", {}).items():
        linhas.append(
            f"| {sem} | {dados['ganhou']} | {dados['perdeu']} | {dados['hit_rate']:.1%} |"
        )

    linhas += ["", "---", ""]

    # Módulo 3 — IC
    linhas += [
        "## Modulo 3 — Information Coefficient (IC)",
        "",
        "> IC calculado sobre excess return vs SMLL (nao retorno bruto).",
        "",
        "### IC por fator",
        "",
        "| Fator | IC Medio | IC Mediano | % Positivo | IR | Semaforo |",
        "|---|---|---|---|---|---|",
    ]
    for fator, dados in m3.get("por_fator", {}).items():
        linhas.append(
            f"| {fator} "
            f"| {dados['ic_medio']:.4f} "
            f"| {dados['ic_mediano']:.4f} "
            f"| {dados['ic_positivo_pct']:.1%} "
            f"| {dados['ir']:.3f} "
            f"| {_semaforo_ic(dados['ic_medio'])} |"
        )

    linhas += [
        "",
        "### IC Rolling 26 semanas — tendencia recente",
        "",
        "| Fator | Tendencia (ultimos 6 meses) |",
        "|---|---|",
    ]
    for fator, dados in m3.get("rolling_26s", {}).items():
        seta = "↑" if dados["tendencia_recente"] == "subindo" else ("↓" if dados["tendencia_recente"] == "caindo" else "—")
        linhas.append(f"| {fator} | {seta} {dados['tendencia_recente']} |")

    corr = m3.get("correlacao_mom_tend", {})
    linhas += [
        "",
        "### Correlacao Momentum x Tendencia",
        "",
        f"- **Correlacao media:** {corr.get('correlacao_media', 0):.3f}",
        f"- **Correlacao mediana:** {corr.get('correlacao_mediana', 0):.3f}",
        f"- **% semanas acima de 0.65:** {corr.get('pct_acima_065', 0):.1%}",
        f"- **Interpretacao:** {corr.get('interpretacao', '')}",
        "",
        "---",
        "",
    ]

    # Módulo 5
    linhas += [
        "## Modulo 5 — Concentracao por Acao",
        "",
        "### 10 maiores destruidores de valor",
        "",
        "| Ticker | Aparicoes | Contrib. Total | Retorno Medio | Win Rate |",
        "|---|---|---|---|---|",
    ]
    for acao in m5[:10]:
        linhas.append(
            f"| {acao['ticker']} "
            f"| {acao['aparicoes']} "
            f"| {acao['contribuicao_total']:+.4f} "
            f"| {acao['retorno_medio']:+.2%} "
            f"| {acao['win_rate']:.1%} |"
        )

    linhas += [
        "",
        "### 5 maiores geradores de valor",
        "",
        "| Ticker | Aparicoes | Contrib. Total | Retorno Medio | Win Rate |",
        "|---|---|---|---|---|",
    ]
    for acao in sorted(m5, key=lambda x: x["contribuicao_total"], reverse=True)[:5]:
        linhas.append(
            f"| {acao['ticker']} "
            f"| {acao['aparicoes']} "
            f"| {acao['contribuicao_total']:+.4f} "
            f"| {acao['retorno_medio']:+.2%} "
            f"| {acao['win_rate']:.1%} |"
        )

    linhas += ["", "---", ""]

    # Módulo 6
    linhas += [
        "## Modulo 6 — Variantes de Tendencia e Momentum",
        "",
        "### Tendencia (baseline V2 = T1)",
        "",
        "| Variante | IC Medio | % Positivo | IR | N Semanas |",
        "|---|---|---|---|---|",
    ]
    for v, dados in m6.get("tendencia", {}).items():
        linhas.append(
            f"| {v} "
            f"| {dados['ic_medio']:.4f} "
            f"| {dados['ic_positivo_pct']:.1%} "
            f"| {dados['ir']:.3f} "
            f"| {dados['n_semanas']} |"
        )

    tv = m6.get("tend_vencedora", {})
    linhas += [
        "",
        f"**Vencedora:** {tv.get('variante_vencedora', '?')} | "
        f"Ganho vs baseline: {tv.get('ganho_relativo', 0):.1%} | "
        f"Recomenda mudanca: {'SIM' if tv.get('recomenda_mudanca') else 'NAO'}",
        f"> {tv.get('motivo', '')}",
        "",
        "### Momentum (baseline V2 = M3)",
        "",
        "| Variante | IC Medio | % Positivo | IR | N Semanas |",
        "|---|---|---|---|---|",
    ]
    for v, dados in m6.get("momentum", {}).items():
        linhas.append(
            f"| {v} "
            f"| {dados['ic_medio']:.4f} "
            f"| {dados['ic_positivo_pct']:.1%} "
            f"| {dados['ir']:.3f} "
            f"| {dados['n_semanas']} |"
        )

    mv = m6.get("mom_vencedora", {})
    linhas += [
        "",
        f"**Vencedora:** {mv.get('variante_vencedora', '?')} | "
        f"Ganho vs baseline: {mv.get('ganho_relativo', 0):.1%} | "
        f"Recomenda mudanca: {'SIM' if mv.get('recomenda_mudanca') else 'NAO'}",
        f"> {mv.get('motivo', '')}",
        "",
        "---",
        "",
    ]

    # Hipóteses V2
    linhas += [
        "## Hipoteses para V2",
        "",
        f"> {len(hips)} hipotese(s) gerada(s) automaticamente.",
        "",
    ]
    if not hips:
        linhas.append("Nenhuma hipotese gerada — formula V1 parece adequada para os dados analisados.")
    else:
        for i, h in enumerate(hips, 1):
            linhas += [
                f"### {i}. {h['hipotese']}",
                f"",
                f"- **Origem:** {h['origem']}",
                f"- **Evidencia:** {h['evidencia']}",
                f"- **Acao sugerida:** {h['acao_sugerida']}",
                f"",
            ]

    linhas += [
        "---",
        "",
        "> **AVISO:** Este diagnostico usa os mesmos dados do backtest.",
        "> Qualquer ajuste de formula baseado nestes resultados carrega risco de overfitting.",
        "> A formula V2 deve ser validada em dados futuros (out-of-sample).",
    ]

    return "\n".join(linhas)
