"""Diagnóstico crítico e priorização.

Regras de raciocínio
1. Toda meta é tirada de DADOS DE OUTRAS EQUIPES da mesma edição (mediana do
   top-5, campeão, melhor valor observado). Nada é comparado com pontuações
   inventadas.
2. Interpretações causais só usam fórmulas do regulamento DA MESMA EDIÇÃO.
   Hoje só existe o de 2026; para 2022–2024 o texto diz explicitamente que a
   causa não pode ser determinada pelos resultados.
3. Cada item traz grau de confiança:
   - Alta  : valor oficial lido do PDF + comparação direta;
   - Média : grandeza derivada por fórmula do regulamento da edição;
   - Baixa : hipótese sobre causa (configuração, processo) que precisa ser
             confirmada com dados internos da equipe.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import analysis, rules, schema
from .fmt import num, pct

SCORE_CRITERIA = ["notas_rel_apres", "pontos_voo", "pontos_acurac", "bonus_pouso",
                  "bonus_tempo_carga", "bonus_motor", "pontos_confiab", "total_video",
                  "pen_dim_pot", "pen_validacao", "pen_competicao"]

# Estimativas de esforço/custo/risco (1 = baixo, 5 = alto). NÃO vêm dos dados:
# são hipóteses de engenharia, editáveis na página 05.
DEFAULT_EFFORT = {
    "notas_rel_apres": dict(esforco=3, custo=1, risco=1, prazo="3–6 meses (ciclo de relatório)",
                            disciplinas="Todas as disciplinas de relatório + apresentação"),
    "pontos_voo": dict(esforco=5, custo=4, risco=4, prazo="ciclo completo de projeto",
                       disciplinas="Conceitual, Aerodinâmica, Estruturas, Desempenho"),
    "pontos_acurac": dict(esforco=2, custo=1, risco=1, prazo="1–2 meses (ensaios em voo)",
                          disciplinas="Desempenho, Ensaios em voo"),
    "bonus_pouso": dict(esforco=3, custo=2, risco=3, prazo="2–3 meses",
                        disciplinas="Desempenho, Trem de pouso, Pilotagem"),
    "bonus_tempo_carga": dict(esforco=2, custo=1, risco=1, prazo="< 1 mês (treino)",
                              disciplinas="Estruturas (compartimento), Operação"),
    "bonus_motor": dict(esforco=2, custo=2, risco=2, prazo="—", disciplinas="Elétrica"),
    "pontos_confiab": dict(esforco=4, custo=3, risco=3, prazo="ciclo de construção + ensaios",
                           disciplinas="Estruturas, Manufatura, Operação, Safety"),
    "total_video": dict(esforco=2, custo=2, risco=2, prazo="até a data do vídeo",
                        disciplinas="Ensaios em voo, Gestão"),
    "pen_dim_pot": dict(esforco=1, custo=1, risco=1, prazo="< 1 mês (checagem)",
                        disciplinas="Elétrica (wattímetro/hélice), Manufatura (envergadura)"),
    "pen_validacao": dict(esforco=2, custo=2, risco=2, prazo="1–2 meses",
                          disciplinas="Estruturas, Trem de pouso"),
    "pen_competicao": dict(esforco=1, custo=1, risco=1, prazo="contínuo",
                           disciplinas="Gestão de prazos e documentos"),
}


@dataclass
class Diagnosis:
    criterio: str
    rotulo: str
    ano: int
    status: str                  # crítico | atenção | forte
    problema: str
    evidencia: str
    comparacao_historica: str
    comparacao_competitiva: str
    referencias: list[str]
    interpretacao: str
    recomendacao: str
    impacto_pts: float
    impacto_posicoes: int
    pos_simulada: int | None
    meta_valor: float
    meta_fonte: str
    confianca: str
    confianca_motivo: str
    hipoteses: list[str] = field(default_factory=list)
    dica: str = ""

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
def _row(df, year, key):
    r = df[(df["year"] == year) & (df["team_key"] == key)]
    return None if r.empty else r.iloc[0]


def _top5(df, year):
    return df[df["year"] == year].nsmallest(5, "pos")


def _src(row, col):
    return (f"{row['source_file']}, p. {int(row['page'])}, linha Pos {int(row['pos'])} "
            f"('{row['team_name']}'), coluna '{schema.label(col)}'")


def _history_text(df, key, field, year) -> str:
    rs = analysis.relative_series(df, key, field)
    if rs.empty or len(rs) < 2:
        return "Sem outras edições da equipe para comparar."
    parts = []
    for _, r in rs.iterrows():
        rel = "—" if pd.isna(r["relativo ao top-5"]) else pct(r["relativo ao top-5"], 0)
        parts.append(f"{int(r['year'])}: {num(r['equipe'])} (rank {int(r['rank'])}/{int(r['n'])}; {rel} da mediana top-5)")
    return "; ".join(parts) + ". Comparação entre anos feita só por posição relativa (regras mudam)."


def _competitive_text(b: analysis.CriterionBench) -> str:
    s = (f"Mediana top-5 {num(b.top5_median)} (faixa {num(b.top5_min)}–{num(b.top5_max)}); "
         f"campeão ({b.champion_name}) {num(b.champion)}; melhor observado {num(b.best_observed)} ({b.best_team}); "
         f"mediana das equipes com voo {num(b.flyers_median)}.")
    if b.neighbor_name:
        s += f" Equipe imediatamente acima no ranking geral ({b.neighbor_name}): {num(b.neighbor_above)}."
    return s


def _target(b: analysis.CriterionBench) -> tuple[float, str]:
    if b.team < b.top5_median - 1e-9:
        return b.top5_median, "mediana do top-5 da edição"
    if b.team < b.best_observed - 1e-9:
        return b.best_observed, f"melhor valor observado ({b.best_team})"
    return b.team, "já no melhor nível observado"


# ---------------------------------------------------------------------------
# Interpretações específicas por critério
# ---------------------------------------------------------------------------
def _interp_notas(df, year, me, b, reg):
    hyps, txt = [], []
    txt.append("O resultado publicado soma relatório e apresentação; o PDF de resultados não separa as "
               "parcelas, então não é possível dizer qual disciplina perdeu pontos.")
    conf = "Alta"
    if reg:
        nota = float(me["notas_rel_apres"])
        if nota < 123.3:
            fpr_max = rules.fpr_2026(nota)
            pv = float(me["pontos_voo"] or 0)
            ganho_min = pv / fpr_max - pv if pv > 0 else 0
            txt.append(f"Pelo regulamento {year}, o FPR multiplica o voo e só satura em NR ≥ 123,3/185. Como a nota "
                       f"total ({num(nota)}) já é < 123,3, o NR também é, logo FPR ≤ {num(fpr_max, 3)} — o voo foi "
                       f"reduzido em pelo menos {pct(1 - fpr_max)}. Levar NR a ≥123,3 renderia ≥ {num(ganho_min)} pts "
                       f"extras em P_voo além dos pontos diretos.")
            hyps.append("FPR < 1 penalizou P_voo (derivado, Eq. 7.4).")
            conf = "Média"
        else:
            txt.append("A nota total já permite FPR = 1 se a parcela de relatório for ≥123,3; acima disso cada ponto vale só 1 ponto.")
    return " ".join(txt), hyps, conf


def _voo_decomposition(df, year, me):
    """P_voo = pontos_carga_ee × FPV × fator_residual (identidade). Compara com a mediana do top-5."""
    t5 = analysis.add_derived(df) if "fator_residual" not in df else df
    t5 = _top5(t5, year)
    ref = {k: float(t5[k].median()) for k in ["pontos_carga_ee", "fpv", "fator_residual", "pontos_voo"]}
    mine = {k: float(me[k]) if pd.notna(me[k]) else np.nan for k in ref}
    if not all(np.isfinite(list(mine.values()))) or mine["pontos_voo"] <= 0:
        return None
    logs = {k: np.log(mine[k] / ref[k]) for k in ["pontos_carga_ee", "fpv", "fator_residual"]}
    total_log = sum(logs.values())
    return {"ref": ref, "mine": mine, "logs": logs, "total_log": total_log}


def _interp_voo(df, year, me, b, reg):
    hyps, txt = [], []
    t5 = _top5(df, year)
    cp, pv, ee = me["carga_paga"], me["peso_vazio"], me["ee_calc"]
    txt.append(f"Perfil da equipe: CP {num(cp, 3)} kg, PV {num(pv, 3)} kg, EE {num(ee, 2)}, FPV {num(me['fpv'], 4)}. "
               f"Top-5 (mediana): CP {num(t5['carga_paga'].median(), 3)} kg, PV {num(t5['peso_vazio'].median(), 3)} kg, "
               f"EE {num(t5['ee_calc'].median(), 2)}, FPV {num(t5['fpv'].median(), 4)}.")
    dec = _voo_decomposition(df, year, me)
    conf = "Alta"
    if dec:
        names = {"pontos_carga_ee": "carga/EE", "fpv": "FPV", "fator_residual": "fator residual"}
        shares = []
        for k, v in sorted(dec["logs"].items(), key=lambda kv: kv[1]):
            if dec["total_log"] < 0 and v < 0:
                shares.append(f"{names[k]} explica {pct(v / dec['total_log'], 0)} da diferença")
        txt.append("Decomposição multiplicativa observada (P_voo = pontos carga/EE × FPV × fator residual): "
                   f"fator residual da equipe {num(dec['mine']['fator_residual'], 3)} vs {num(dec['ref']['fator_residual'], 3)} "
                   f"no top-5. " + ("; ".join(shares) + "." if shares else ""))
    if reg and dec:
        res = dec["mine"]["fator_residual"]
        nota = float(me["notas_rel_apres"])
        fpr_hi = rules.fpr_2026(nota)
        cands = []
        for n in (1, 2, 3):
            for fpr in sorted({fpr_hi, 1.0}):
                x = res / (fpr * rules.config_factor_2026(n))
                if 0 < x <= 1:
                    bspan = -np.log(x) / np.log(1.15)
                    if 0.5 <= bspan <= 4.0:
                        cands.append(f"N={n}, b≈{num(bspan, 2)} m (FPR={num(fpr, 3)})")
        if cands:
            txt.append(f"Pelo regulamento {year} o fator residual = FPR × f(N) × 1,15^(−b). Combinações coerentes com "
                       f"{num(res, 3)}: " + "; ".join(cands) + ".")
            hyps.append("Configuração (N) e envergadura (b) inferidas do fator residual — confirmar com o projeto real.")
        t5res = t5["fator_residual"].median()
        txt.append(f"Mediana do top-5 = {num(t5res, 3)}; exemplos que geram esse fator com FPR=1: "
                   f"N=3 com b≈{num(-np.log(t5res / 1.15) / np.log(1.15), 2)} m, ou N=1 com b≈{num(-np.log(t5res / 1.22) / np.log(1.15), 2)} m.")
        err = rules.pv_error_from_fpv_2026(float(me["fpv"]))
        if err is not None:
            errs = [rules.pv_error_from_fpv_2026(float(x)) for x in t5["fpv"]]
            errs = [e for e in errs if e is not None]
            txt.append(f"FPV {num(me['fpv'], 4)} ⇒ erro de previsão do PV ≈ {pct(err)} (Eq. 7.3 invertida); "
                       f"top-5: mediana {pct(np.median(errs)) if errs else '—'}.")
        target = b.top5_median
        need_ee = target / (50 * float(me["fpv"]) * res) if res > 0 else np.nan
        txt.append(f"Mantendo FPV e fator residual atuais, alcançar P_voo {num(target)} exigiria EE ≈ {num(need_ee, 2)} "
                   f"(a maior EE observada na edição foi {num(df[df['year']==year]['ee_calc'].max(), 2)}). "
                   + ("Isso indica que só aumentar carga não basta: é preciso mexer no fator de configuração/relatório."
                      if need_ee > df[df['year'] == year]['ee_calc'].max() else ""))
        conf = "Média"
    elif dec:
        txt.append(f"Regulamento {year} não disponível no projeto: a decomposição é uma identidade aritmética, "
                   "mas o significado do fator residual nessa edição não pode ser determinado.")
    return " ".join(txt), hyps, conf


def _interp_acurac(df, year, me, b, reg):
    if not reg:
        return ("Sem o regulamento da edição não é possível converter pontos em erro de previsão.", [], "Alta")
    err = rules.cp_error_from_pac_2026(float(me["pontos_acurac"]))
    t5 = _top5(df, year)
    errs = [rules.cp_error_from_pac_2026(float(x)) for x in t5["pontos_acurac"]]
    errs = [e for e in errs if e is not None]
    if err is None:
        return ("Pontuação zero: erro de previsão de carga ≥ ~15%, coeficientes da reta não lançados no aeroct, "
                "ou bateria sem acuracidade — o resultado não permite distinguir.", ["Causa da acuracidade zero indeterminada."], "Média")
    return (f"P_AC {num(me['pontos_acurac'])} ⇒ erro de previsão de carga ≈ {pct(err)} (Eq. 7.6 invertida). "
            f"Equipes do top-5 que pontuaram: erro mediano ≈ {pct(np.median(errs)) if errs else '—'}. "
            f"Cada ponto aqui depende de previsão (reta a·Hρ + b), não de desempenho bruto.", [], "Média")


def _interp_pouso(df, year, me, b, reg):
    y = df[df["year"] == year]
    share = (y[y["voou"]]["pouso_100m"].astype(str) == "Sim").mean()
    s = f"Pouso < 100 m da equipe: {me['pouso_100m']}. {pct(share, 0)} das equipes com voo pararam em 100 m."
    if reg:
        bmax = 2 * float(me['ee_calc'] or 0)
        s += f" Em {year} B_PO = 2×EE: o bônus máximo da equipe com a EE atual seria {num(bmax)}."
        if bmax < b.top5_median:
            s += " A meta do top-5 só é alcançável aumentando a EE — o pouso já não é o gargalo."
        return s, [], "Média"
    return s, [], "Alta"


def _interp_tempo(df, year, me, b, reg):
    t = me["tempo_carga"]
    y = df[(df["year"] == year) & (df["tempo_carga"] < 999)]
    s = f"Tempo de retirada {num(t, 1)} s; mediana das equipes com registro {num(y['tempo_carga'].median(), 1)} s; top-5 {num(_top5(df, year)['tempo_carga'].replace(999, np.nan).median(), 1)} s."
    if reg:
        s += " Em 2026 o bônus cai de 20 para 15,5 pts com 0,5 s acima de 20 s (Eq. 7.8)."
    return s, [], "Alta"


def _interp_confiab(df, year, me, b, reg):
    q = me["queda_2a_bateria"]
    t5 = _top5(df, year)
    s = (f"2ª melhor bateria {num(me['total_2a_bateria'])} vs melhor {num(me['total_melhor_bateria'])} "
         f"(queda {pct(q) if pd.notna(q) else '—'}). Top-5: queda mediana {pct(t5['queda_2a_bateria'].median())}.")
    if "voos_validos" in me and pd.notna(me.get("voos_validos")):
        s += f" Voos válidos: {int(me['voos_validos'])} (top-5 mediana {num(t5['voos_validos'].median(), 0)})."
    if reg:
        s += " Pelo regulamento 2026 a bonificação zera com queda ≥ 44,7% e vale 16 pts com queda de 20% (Eq. 7.9)."
        return s, [], "Média"
    return s, [], "Alta"


def _interp_pen_dim(df, year, me, b, reg):
    v = float(me["pen_dim_pot"] or 0)
    if v >= 0:
        return "Sem penalidade.", [], "Alta"
    s = f"Penalidade de {num(v)} pts na melhor bateria."
    tb_sum = sum(float(me.get(c, 0) or 0) for c in schema.BATTERY_COMPONENTS if c in me)
    if float(me["total_melhor_bateria"]) == 0 and tb_sum < 0:
        s += " Ela foi suficiente para ZERAR a bateria (soma dos componentes negativa)."
    if reg:
        h = rules.penalty_dim_pot_hypotheses_2026(v)
        if len(h) == 1:
            s += " Única hipótese compatível com o valor pelo regulamento: " + h[0] + "."
        else:
            s += " Hipóteses pelo regulamento: " + "; ".join(h) + ". O PDF não informa qual ocorreu."
        return s, h, "Baixa"
    return s + " Sem o regulamento da edição não é possível separar dimensão de potência.", [], "Alta"


def _interp_generic(df, year, me, b, reg):
    return "", [], "Alta"


INTERP = {
    "notas_rel_apres": _interp_notas, "pontos_voo": _interp_voo, "pontos_acurac": _interp_acurac,
    "bonus_pouso": _interp_pouso, "bonus_tempo_carga": _interp_tempo, "pontos_confiab": _interp_confiab,
    "pen_dim_pot": _interp_pen_dim,
}


def _recommendation(field, b, me, df, year, meta, fonte):
    top = _top5(df, year)
    who = ", ".join(f"{r.team_name} ({num(getattr(r, field))})" for r in top.itertuples())
    base = f"Meta baseada em dados: {num(meta)} ({fonte}). Referências da edição: {who}."
    specific = {
        "notas_rel_apres": "Usar como benchmark os relatórios das equipes do top-5 (quando públicos) e revisar cada disciplina com banca interna antes da entrega.",
        "pontos_voo": "Atacar o termo com maior participação na decomposição: se for o fator residual, rever configuração/envergadura e o FPR; se for carga/EE, reduzir PV e aumentar CP; se for FPV, melhorar a previsão de peso vazio.",
        "pontos_acurac": "Refazer a curva de carga vs. altitude-densidade com ensaios em voo e margem estatística; comparar a previsão com a carga real em cada bateria.",
        "bonus_pouso": "Treinar e projetar para parada dentro da zona de 100 m (freio, trem, rampa de aproximação).",
        "bonus_tempo_carga": "Cronometrar a retirada de carga em treinos com 2 pessoas; manter margem abaixo do limite do bônus.",
        "pontos_confiab": "Garantir pelo menos duas baterias válidas e próximas: plano de manutenção entre baterias e inspeção pós-voo.",
        "total_video": "Cumprir integralmente os requisitos do vídeo de voo no prazo.",
        "pen_dim_pot": "Checagem dimensional e de potência (wattímetro de pico, hélice escolhida por ensaio) antes de cada bateria.",
        "pen_validacao": "Reforçar componentes não primários e rodas; inspeção após cada pouso.",
        "pen_competicao": "Checklist de prazos e requisitos documentais.",
    }.get(field, "")
    return f"{base} {specific}".strip()


def short_tip(field, df, year, me, b, meta, fonte) -> str:
    """Dica curta para o card do dashboard — só com números de outras equipes."""
    t5 = _top5(df, year)
    if meta == b.team:
        return f"No nível de referência da edição (melhor observado {num(b.best_observed)})."
    head = f"Meta {num(meta)} ({fonte})."
    if field == "pontos_voo":
        return (f"{head} Top-5: EE {num(t5['ee_calc'].median(), 2)} × sua {num(me['ee_calc'], 2)}; "
                f"PV {num(t5['peso_vazio'].median(), 2)} × {num(me['peso_vazio'], 2)} kg; "
                f"fator residual {num(t5['fator_residual'].median(), 3)} × {num(me['fator_residual'], 3)}.")
    if field == "notas_rel_apres":
        return f"{head} Top-5 entre {num(b.top5_min)} e {num(b.top5_max)}; melhor nota: {b.best_team} ({num(b.best_observed)})."
    if field == "pontos_acurac" and rules.regulation_for(year):
        e = rules.cp_error_from_pac_2026(float(me["pontos_acurac"]))
        return f"{head} Seu erro de previsão de carga ≈ {pct(e) if e is not None else '≥15%'}; a meta equivale a ≈ {pct(rules.cp_error_from_pac_2026(meta) or 0)}."
    if field == "pontos_confiab":
        return (f"{head} Sua 2ª bateria caiu {pct(me['queda_2a_bateria']) if pd.notna(me['queda_2a_bateria']) else '100%'}; "
                f"no top-5 a queda mediana foi {pct(t5['queda_2a_bateria'].median())}.")
    if field == "bonus_pouso":
        share = (t5["pouso_100m"].astype(str) == "Sim").sum()
        return f"{head} {share} de 5 do top-5 pararam em 100 m; o bônus escala com a carga/EE."
    if field == "bonus_tempo_carga":
        return f"{head} Seu tempo: {num(me['tempo_carga'], 1)} s; top-5: {num(t5['tempo_carga'].replace(999, np.nan).median(), 1)} s."
    if field in schema.PENALTY_FIELDS:
        clean = (df[df['year'] == year][field] == 0).mean()
        return f"{head} {pct(clean, 0)} das equipes da edição não sofreram essa penalidade."
    return f"{head} Melhor observado: {b.best_team} ({num(b.best_observed)})."


def diagnose(df: pd.DataFrame, year: int, team_key: str) -> list[Diagnosis]:
    df = df if "ee_calc" in df else analysis.add_derived(df)
    me = _row(df, year, team_key)
    if me is None:
        return []
    reg = rules.regulation_for(year)
    out = []
    for f in SCORE_CRITERIA:
        b = analysis.bench_criterion(df, year, team_key, f)
        if b is None:
            continue
        meta, fonte = _target(b)
        sim = analysis.simulate(df, year, team_key, {f: meta}) if meta != b.team else {
            "ganho": 0.0, "posicoes_ganhas": 0, "pos_simulada": int(me["pos"])}
        interp, hyps, conf = INTERP.get(f, _interp_generic)(df, year, me, b, reg)
        refs = [_src(me, f)]
        if reg and (f in reg["refs"] or f in reg["max"]):
            refs.append(str(reg["refs"].get(f) or reg["max"][f][1]))
        elif not reg:
            refs.append(f"Regulamento {year}: não disponível no projeto — fórmula da edição não verificada.")
        if b.status == "forte" or meta == b.team:
            problema = f"{b.label}: nível de referência (rank {b.rank}/{b.n})."
        else:
            problema = (f"{b.label}: {num(b.team)} pts, {num(meta - b.team)} abaixo da meta "
                        f"({fonte}; rank {b.rank}/{b.n}).")
        conf_motivo = {"Alta": "valor oficial e comparação direta com outras equipes da mesma edição",
                       "Média": f"inclui grandezas derivadas das fórmulas do regulamento {year}",
                       "Baixa": "a causa é hipótese; o PDF de resultados não a registra"}[conf]
        out.append(Diagnosis(
            criterio=f, rotulo=b.label, ano=year, status=b.status, problema=problema,
            evidencia=f"Equipe: {num(b.team)} (rank {b.rank}/{b.n}). Diferença para a mediana do top-5: "
                      f"{num(b.gap_top5, signed=True)} pts; para o campeão: {num(b.gap_champion, signed=True)} pts "
                      f"(positivo = pontos a ganhar).",
            comparacao_historica=_history_text(df, team_key, f, year),
            comparacao_competitiva=_competitive_text(b),
            referencias=refs, interpretacao=interp,
            recomendacao=_recommendation(f, b, me, df, year, meta, fonte),
            impacto_pts=float(sim["ganho"]), impacto_posicoes=int(sim["posicoes_ganhas"]),
            pos_simulada=sim.get("pos_simulada"), meta_valor=meta, meta_fonte=fonte,
            confianca=conf, confianca_motivo=conf_motivo, hipoteses=hyps,
            dica=short_tip(f, df, year, me, b, meta, fonte),
        ))
    return out


# ---------------------------------------------------------------------------
# Priorização
# ---------------------------------------------------------------------------
def priority_matrix(df: pd.DataFrame, year: int, team_key: str,
                    effort: dict | None = None, weights: dict | None = None,
                    only_current_criteria: bool = True) -> pd.DataFrame:
    effort = {**DEFAULT_EFFORT, **(effort or {})}
    w = {"potencial": 0.35, "posicoes": 0.25, "recorrencia": 0.15, "facilidade": 0.25, **(weights or {})}
    diags = [d for d in diagnose(df, year, team_key) if d.impacto_pts > 0.01]
    latest = max(df["year"])
    rec = analysis.recurrence(df if "ee_calc" in df else analysis.add_derived(df), team_key)
    rec = rec.set_index("critério")["recorrência"].to_dict() if not rec.empty else {}
    rows = []
    for d in diags:
        if only_current_criteria and d.criterio not in analysis.fields_in_year(df, latest):
            continue
        e = effort.get(d.criterio, dict(esforco=3, custo=3, risco=3, prazo="—", disciplinas="—"))
        rows.append({"critério": d.criterio, "rótulo": d.rotulo, "status": d.status,
                     "ganho potencial (pts)": d.impacto_pts, "posições ganhas": d.impacto_posicoes,
                     "posição simulada": d.pos_simulada, "recorrência": rec.get(d.criterio, 0.0),
                     "esforço": e["esforco"], "custo": e["custo"], "risco": e["risco"],
                     "prazo": e["prazo"], "disciplinas": e["disciplinas"], "confiança": d.confianca,
                     "meta": d.meta_valor, "fonte da meta": d.meta_fonte})
    m = pd.DataFrame(rows)
    if m.empty:
        return m
    norm = lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0 + 1  # noqa: E731
    m["facilidade"] = (15 - m["esforço"] - m["custo"] - m["risco"]) / 12
    m["score"] = (w["potencial"] * norm(m["ganho potencial (pts)"]) + w["posicoes"] * norm(m["posições ganhas"].astype(float))
                  + w["recorrencia"] * m["recorrência"] + w["facilidade"] * m["facilidade"])
    m = m.sort_values("score", ascending=False).reset_index(drop=True)
    m.insert(0, "prioridade", range(1, len(m) + 1))
    return m


def strengths(diags: list[Diagnosis]) -> list[Diagnosis]:
    return [d for d in diags if d.status == "forte"]


def limiting_criteria(diags: list[Diagnosis], n: int = 3) -> list[Diagnosis]:
    return sorted([d for d in diags if d.impacto_pts > 0], key=lambda d: (-d.impacto_posicoes, -d.impacto_pts))[:n]
