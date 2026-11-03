"""Relatório técnico (Markdown/HTML) com referências documentais."""
from __future__ import annotations

import html
from datetime import date

import pandas as pd

from . import analysis, diagnosis, rules
from .fmt import num, pct


def build_markdown(df: pd.DataFrame, year: int, team_key: str, narrative: str | None = None,
                   effort: dict | None = None) -> str:
    df = df if "ee_calc" in df else analysis.add_derived(df)
    me = df[(df["year"] == year) & (df["team_key"] == team_key)]
    if me.empty:
        return "Equipe não participou da edição selecionada."
    me = me.iloc[0]
    diags = diagnosis.diagnose(df, year, team_key)
    pod = analysis.podium_gap(df, year, team_key)
    prio = diagnosis.priority_matrix(df, year, team_key, effort=effort)
    ident = analysis.team_identity(df, team_key)
    reg = rules.regulation_for(year)

    L = [f"# Relatório estratégico — {me['team_name']} ({year})", "",
         f"*Gerado em {date.today():%d/%m/%Y} pelo SAE AeroDesign Intelligence V0. Classe Regular apenas.*", "",
         "## Identificação", "",
         f"- **Equipe:** {me['team_name']}  ",
         f"- **Instituição:** {me['school']} ({me['uf']})  ",
         f"- **Edição analisada:** {year} — {int(me['pos'])}º de {int(me['n_equipes'])} equipes, {num(me['total_geral'])} pts  ",
         f"- **Fonte:** {me['source_file']}, p. {int(me['page'])}  ",
         f"- **Regulamento da edição:** {reg['file'] + ' ' + reg['revision'] if reg else 'não disponível no projeto (interpretações limitadas a dados observados)'}",
         "", "### Histórico", "", "| Ano | Nome no PDF | Posição | Total | Fonte |", "|---|---|---|---|---|"]
    for _, r in ident.iterrows():
        L.append(f"| {r['year']} | {r['team_name']} | {int(r['pos'])}/{int(r['n_equipes'])} | {num(r['total_geral'])} | {r['source_file']} |")

    L += ["", "## Distância para o pódio e para o título", "",
          f"- 3º colocado: **{pod['terceiro']}** com {num(pod['terceiro_total'])} pts → faltam **{num(pod['pontos_para_podio'])} pts**.",
          f"- Campeão: **{pod['campeao']}** com {num(pod['campeao_total'])} pts → faltam **{num(pod['pontos_para_titulo'])} pts**.",
          "", "| Bloco do total | Equipe | 3º colocado | Δ vs 3º | Mediana top-5 | Δ vs top-5 |", "|---|---|---|---|---|---|"]
    for _, r in pod["decomposicao"].iterrows():
        L.append(f"| {r['bloco']} | {num(r['equipe'])} | {num(r['3º colocado'])} | {num(r['Δ vs 3º'], signed=True)} | "
                 f"{num(r['mediana top-5'])} | {num(r['Δ vs top-5'], signed=True)} |")

    lim = diagnosis.limiting_criteria(diags)
    L += ["", "## Onde a equipe perde pontos", ""]
    if lim:
        L.append("Critérios que mais limitam a classificação (simulação: equipe atinge a meta, demais equipes inalteradas):")
        L.append("")
        for d in lim:
            L.append(f"- **{d.rotulo}** — +{num(d.impacto_pts)} pts, {d.impacto_posicoes:+d} posições (→ {d.pos_simulada}º). Confiança: {d.confianca}.")
    fortes = diagnosis.strengths(diags)
    if fortes:
        L += ["", "**Pontos fortes (no nível do top-5 ou do melhor observado):** " + ", ".join(d.rotulo for d in fortes) + "."]

    if narrative:
        L += ["", "## Síntese interpretativa (IA)", "", narrative.strip(), "",
              "> Texto gerado a partir apenas das evidências estruturadas deste relatório. Verifique antes de usar."]

    L += ["", "## Diagnóstico por critério", ""]
    for d in sorted(diags, key=lambda d: -d.impacto_pts):
        L += [f"### {d.rotulo} — {d.status.upper()}", "",
              f"- **Problema:** {d.problema}",
              f"- **Evidência quantitativa:** {d.evidencia}",
              f"- **Comparação histórica:** {d.comparacao_historica}",
              f"- **Comparação competitiva:** {d.comparacao_competitiva}"]
        if d.interpretacao:
            L.append(f"- **Interpretação técnica:** {d.interpretacao}")
        L += [f"- **Recomendação:** {d.recomendacao}",
              f"- **Impacto potencial:** +{num(d.impacto_pts)} pts; {d.impacto_posicoes:+d} posições (posição simulada {d.pos_simulada}º).",
              f"- **Confiança:** {d.confianca} — {d.confianca_motivo}."]
        if d.hipoteses:
            L.append(f"- **Hipóteses a confirmar:** " + "; ".join(d.hipoteses))
        L.append("- **Referências:** " + " | ".join(d.referencias))
        L.append("")

    if not prio.empty:
        L += ["## Prioridades para a próxima competição", "",
              "| # | Critério | Ganho (pts) | Posições | Recorrência | Esforço | Custo | Risco | Prazo | Meta |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in prio.iterrows():
            L.append(f"| {r['prioridade']} | {r['rótulo']} | {num(r['ganho potencial (pts)'])} | {r['posições ganhas']:+d} | "
                     f"{pct(r['recorrência'], 0)} | {r['esforço']} | {r['custo']} | {r['risco']} | {r['prazo']} | {num(r['meta'])} ({r['fonte da meta']}) |")
        L += ["", "*Esforço, custo e risco (1–5) são estimativas de engenharia editáveis, não dados observados.*"]

    L += ["", "## Limitações", "",
          "- Ganhos simulados supõem as demais equipes constantes; não são previsões.",
          "- Correlação entre critérios não implica causa; hipóteses estão marcadas como tal.",
          "- Notas de relatório e apresentação aparecem somadas no PDF de resultados.",
          "- Comparações entre anos usam posição relativa, pois fórmulas e pesos mudam (ex.: pontos de carga 12,5×CP até 2024 e 50×EE em 2026).",
          "- Regulamentos de 2022–2025 e resultados de 2025 não estão no projeto."]
    return "\n".join(L)


def markdown_to_html(md: str, title: str = "Relatório") -> str:
    """Conversão simples (sem dependências) para exportar/imprimir."""
    out, in_table, in_list = [], False, False
    for line in md.splitlines():
        esc = html.escape(line)
        import re
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", esc)
        if line.startswith("|"):
            cells = [c.strip() for c in esc.strip("|").split("|")]
            if set("".join(cells)) <= set("-"):
                continue
            if not in_table:
                out.append("<table>"); in_table = True
                out.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>"); in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{esc[2:]}</li>"); continue
        if in_list:
            out.append("</ul>"); in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{esc[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{esc[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{esc[2:]}</h1>")
        elif line.startswith("&gt; "):
            out.append(f"<blockquote>{esc[5:]}</blockquote>")
        elif line.strip():
            out.append(f"<p>{esc}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font-family:system-ui,Segoe UI,Arial;max-width:960px;margin:32px auto;color:#1d2433;line-height:1.5}"
           "table{border-collapse:collapse;margin:12px 0;font-size:13px}td,th{border:1px solid #d5dae3;padding:4px 8px;text-align:left}"
           "th{background:#f1f4f9}h1{color:#0b3d91}h2{border-bottom:2px solid #0b3d91;padding-bottom:4px;margin-top:28px}"
           "h3{color:#0b3d91;margin-top:20px}blockquote{color:#555;border-left:3px solid #ccc;margin:0;padding-left:10px}")
    return f"<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body>{''.join(out)}</body></html>"
