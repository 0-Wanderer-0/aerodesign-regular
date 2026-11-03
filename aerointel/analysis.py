"""Motor de análise estatística e benchmarking.

Princípio: toda comparação é feita DENTRO da mesma edição (mesmo regulamento).
Entre edições comparam-se apenas posições relativas (percentil, % do campeão,
lacuna para o top-5), nunca pontos brutos de critérios cujo cálculo mudou.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import rules, schema


# ---------------------------------------------------------------------------
# Derivados
# ---------------------------------------------------------------------------
def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    cp, pv = d.get("carga_paga"), d.get("peso_vazio")
    d["ee_calc"] = np.where((pv > 0) & (cp > 0), cp / pv.replace(0, np.nan), np.nan)
    base = d["fpv"] * d["pontos_carga_ee"]
    d["fator_residual"] = np.where((base > 0) & (d["pontos_voo"] > 0), d["pontos_voo"] / base, np.nan)
    t1, t2 = d["total_melhor_bateria"], d["total_2a_bateria"]
    d["queda_2a_bateria"] = np.where(t1 > 0, 1 - t2 / t1, np.nan)
    d["voou"] = (d["carga_paga"].fillna(0) > 0) | (t1.fillna(0) > 0)
    d["n_equipes"] = d.groupby("year")["pos"].transform("size")
    d["percentil_total"] = d.groupby("year")["total_geral"].rank(pct=True, method="average")
    champ = d.groupby("year")["total_geral"].transform("max")
    d["pct_campeao"] = d["total_geral"] / champ
    return d


def fields_in_year(df: pd.DataFrame, year: int, candidates=None) -> list[str]:
    candidates = candidates or schema.DASHBOARD_CRITERIA
    y = df[df["year"] == year]
    return [c for c in candidates if c in y and y[c].notna().any()]


# ---------------------------------------------------------------------------
# Estatísticas por edição
# ---------------------------------------------------------------------------
def edition_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("year")
    out = pd.DataFrame({
        "equipes": g.size(),
        "equipes_com_voo": g["voou"].sum(),
        "campeão": g.apply(lambda x: x.loc[x["total_geral"].idxmax(), "team_name"], include_groups=False),
        "total_campeão": g["total_geral"].max(),
        "total_3º": g.apply(lambda x: x.nsmallest(3, "pos")["total_geral"].min(), include_groups=False),
        "mediana_top5": g.apply(lambda x: x.nsmallest(5, "pos")["total_geral"].median(), include_groups=False),
        "média_geral": g["total_geral"].mean(),
        "mediana_geral": g["total_geral"].median(),
        "desvio_padrão": g["total_geral"].std(),
    })
    return out.reset_index()


def criterion_variability(df: pd.DataFrame, year: int, only_flyers: bool = True) -> pd.DataFrame:
    y = df[df["year"] == year]
    if only_flyers:
        y = y[y["voou"]]
    rows = []
    for f in fields_in_year(df, year):
        s = y[f].dropna()
        if s.empty:
            continue
        mean = s.mean()
        rows.append({"critério": f, "rótulo": schema.label(f), "média": mean, "desvio": s.std(),
                     "CV": (s.std() / abs(mean)) if abs(mean) > 1e-9 else np.nan,
                     "mín": s.min(), "máx": s.max(), "amplitude": s.max() - s.min()})
    return pd.DataFrame(rows).sort_values("amplitude", ascending=False)


def rank_in_criterion(df: pd.DataFrame, year: int, field: str) -> pd.Series:
    y = df[df["year"] == year]
    hib = schema.FIELDS[field].higher_is_better if field in schema.FIELDS else True
    return y[field].rank(ascending=not hib, method="min")


# ---------------------------------------------------------------------------
# Benchmarking
# ---------------------------------------------------------------------------
@dataclass
class CriterionBench:
    field: str
    label: str
    year: int
    team: float
    rank: int
    n: int
    champion: float
    champion_name: str
    top3_median: float
    top5_median: float
    top5_min: float
    top5_max: float
    field_median: float
    flyers_median: float
    best_observed: float
    best_team: str
    neighbor_above: float | None
    neighbor_name: str | None
    reg_max: float | None
    reg_ref: str | None

    @property
    def gap_top5(self) -> float:
        return self.top5_median - self.team

    @property
    def gap_best(self) -> float:
        return self.best_observed - self.team

    @property
    def gap_champion(self) -> float:
        return self.champion - self.team

    @property
    def status(self) -> str:
        near_best = self.gap_best <= max(0.10 * abs(self.best_observed), 0.5)
        if self.team >= self.top5_median - 1e-9 and (near_best or self.top5_median > 0):
            return "forte"
        if self.team >= self.flyers_median - 1e-9:
            return "atenção"
        return "crítico"


def bench_criterion(df: pd.DataFrame, year: int, team_key: str, field: str) -> CriterionBench | None:
    y = df[df["year"] == year].sort_values("pos")
    me = y[y["team_key"] == team_key]
    if me.empty or field not in y or y[field].isna().all():
        return None
    me = me.iloc[0]
    others = y[y["team_key"] != team_key]
    top3, top5 = y.nsmallest(3, "pos"), y.nsmallest(5, "pos")
    champ = y.iloc[0]
    hib = schema.FIELDS[field].higher_is_better if field in schema.FIELDS else True
    best_idx = others[field].idxmax() if hib else others[field].idxmin()
    above = y[y["pos"] < me["pos"]]
    neighbor = above.iloc[-1] if not above.empty else None
    reg = rules.regulation_for(year)
    reg_max, reg_ref = (None, None)
    if reg and field in reg["max"]:
        reg_max, ref = reg["max"][field]
        reg_ref = str(ref)
    elif reg and field in reg["refs"]:
        reg_ref = str(reg["refs"][field])
    ranks = rank_in_criterion(df, year, field)
    return CriterionBench(
        field=field, label=schema.label(field), year=year, team=float(me[field]),
        rank=int(ranks.loc[me.name]), n=len(y),
        champion=float(champ[field]), champion_name=champ["team_name"],
        top3_median=float(top3[field].median()), top5_median=float(top5[field].median()),
        top5_min=float(top5[field].min()), top5_max=float(top5[field].max()),
        field_median=float(y[field].median()), flyers_median=float(y[y["voou"]][field].median()),
        best_observed=float(others.loc[best_idx, field]), best_team=others.loc[best_idx, "team_name"],
        neighbor_above=None if neighbor is None else float(neighbor[field]),
        neighbor_name=None if neighbor is None else neighbor["team_name"],
        reg_max=reg_max, reg_ref=reg_ref,
    )


def benchmark_table(df: pd.DataFrame, year: int, team_key: str, fields=None) -> pd.DataFrame:
    rows = []
    for f in fields or fields_in_year(df, year):
        b = bench_criterion(df, year, team_key, f)
        if b is None:
            continue
        rows.append({"critério": f, "rótulo": b.label, "equipe": b.team, "rank": f"{b.rank}/{b.n}",
                     "campeão": b.champion, "mediana top-3": b.top3_median, "mediana top-5": b.top5_median,
                     "mediana (com voo)": b.flyers_median, "melhor observado": b.best_observed,
                     "Δ top-5": b.gap_top5, "Δ campeão": b.gap_champion, "status": b.status})
    return pd.DataFrame(rows)


def compare_teams(df: pd.DataFrame, year: int, team_keys: list[str], fields=None) -> pd.DataFrame:
    y = df[(df["year"] == year) & (df["team_key"].isin(team_keys))]
    fields = fields or fields_in_year(df, year)
    return y.set_index("team_name")[["pos", "total_geral"] + [f for f in fields if f != "total_geral"]]


def reference_teams(df: pd.DataFrame, year: int, team_key: str) -> dict[str, list[str]]:
    """Sugestões de benchmarking baseadas só em resultados."""
    y = df[df["year"] == year].sort_values("pos")
    me = y[y["team_key"] == team_key]
    out = {"campeão": y.head(1)["team_key"].tolist(), "top-3": y.head(3)["team_key"].tolist(),
           "top-5": y.head(5)["team_key"].tolist()}
    if not me.empty:
        p = int(me.iloc[0]["pos"])
        out["concorrentes diretas (±3 posições)"] = y[(y["pos"].between(p - 3, p + 3)) & (y["team_key"] != team_key)]["team_key"].tolist()
    # Evolução expressiva: maior ganho de percentil entre a edição anterior disponível e esta
    years = sorted(df["year"].unique())
    if year in years and years.index(year) > 0:
        prev = years[years.index(year) - 1]
        a = df[df["year"] == prev].set_index("team_key")["percentil_total"]
        b = y.set_index("team_key")["percentil_total"]
        delta = (b - a).dropna().sort_values(ascending=False)
        out[f"maior evolução ({prev}→{year})"] = delta.head(5).index.tolist()
    # Campeões históricos
    out["campeões históricos"] = df[df["pos"] == 1]["team_key"].unique().tolist()
    return out


# ---------------------------------------------------------------------------
# Simulação de impacto e lacuna para o pódio
# ---------------------------------------------------------------------------
def recompute_total(row: pd.Series) -> float:
    return max(0.0, sum(float(row.get(c, 0) or 0) for c in schema.TOTAL_COMPONENTS))


def simulate(df: pd.DataFrame, year: int, team_key: str, changes: dict[str, float]) -> dict:
    """Simula a posição se a equipe atingisse novos valores em blocos do Total.

    `changes` aceita componentes do Total (TOTAL_COMPONENTS) ou componentes da
    bateria (BATTERY_COMPONENTS); estes alteram a melhor bateria pelo mesmo Δ
    (aproximação — a bateria nunca fica < 0). Os demais times ficam constantes.
    """
    y = df[df["year"] == year].copy()
    i = y.index[y["team_key"] == team_key]
    if len(i) == 0:
        return {}
    i = i[0]
    row = y.loc[i].copy()
    comp_sum = sum(float(row.get(c, 0) or 0) for c in schema.BATTERY_COMPONENTS if c in row and pd.notna(row.get(c)))
    battery_base = float(row["total_melhor_bateria"] or 0)
    if battery_base <= 0 and comp_sum < 0:
        battery_base = comp_sum          # bateria zerada por penalidade: parte da soma real
    for f, v in changes.items():
        if f in schema.BATTERY_COMPONENTS:
            battery_base += v - float(row.get(f, 0) or 0)
            row["total_melhor_bateria"] = max(0.0, battery_base)
        row[f] = v
    new_total = recompute_total(row)
    others = y.drop(index=i)["total_geral"]
    new_pos = int((others > new_total + 1e-9).sum() + 1)
    return {"total_original": float(y.loc[i, "total_geral"]), "total_simulado": new_total,
            "ganho": new_total - float(y.loc[i, "total_geral"]),
            "pos_original": int(y.loc[i, "pos"]), "pos_simulada": new_pos,
            "posicoes_ganhas": int(y.loc[i, "pos"]) - new_pos}


def podium_gap(df: pd.DataFrame, year: int, team_key: str) -> dict:
    y = df[df["year"] == year].sort_values("pos")
    me = y[y["team_key"] == team_key]
    if me.empty:
        return {}
    me = me.iloc[0]
    third = y.nsmallest(3, "pos").iloc[-1]
    champ = y.iloc[0]
    top5 = y.nsmallest(5, "pos")
    rows = []
    for c in schema.TOTAL_COMPONENTS:
        rows.append({"bloco": schema.label(c), "campo": c, "equipe": me[c], "3º colocado": third[c],
                     "Δ vs 3º": third[c] - me[c], "mediana top-5": top5[c].median(),
                     "Δ vs top-5": top5[c].median() - me[c], "campeão": champ[c], "Δ vs campeão": champ[c] - me[c]})
    return {
        "equipe_total": float(me["total_geral"]), "pos": int(me["pos"]),
        "terceiro": third["team_name"], "terceiro_total": float(third["total_geral"]),
        "pontos_para_podio": max(0.0, float(third["total_geral"]) - float(me["total_geral"]) + 0.01),
        "campeao": champ["team_name"], "campeao_total": float(champ["total_geral"]),
        "pontos_para_titulo": max(0.0, float(champ["total_geral"]) - float(me["total_geral"]) + 0.01),
        "decomposicao": pd.DataFrame(rows),
    }


# ---------------------------------------------------------------------------
# Histórico da equipe
# ---------------------------------------------------------------------------
def team_history(df: pd.DataFrame, team_key: str) -> pd.DataFrame:
    h = df[df["team_key"] == team_key].sort_values("year")
    return h


def team_identity(df: pd.DataFrame, team_key: str) -> pd.DataFrame:
    h = team_history(df, team_key)
    return h[["year", "team_name", "school", "uf", "pos", "n_equipes", "total_geral", "source_file"]]


def recurrence(df: pd.DataFrame, team_key: str, fields=None) -> pd.DataFrame:
    """Em quantas edições a equipe ficou abaixo da mediana (com voo) e do top-5 em cada critério."""
    rows = []
    h = team_history(df, team_key)
    for f in fields or schema.DASHBOARD_CRITERIA:
        below_med = below_top5 = n = 0
        years = []
        for y in h["year"]:
            b = bench_criterion(df, y, team_key, f)
            if b is None:
                continue
            n += 1
            below_med += b.team < b.flyers_median - 1e-9
            below_top5 += b.team < b.top5_median - 1e-9
            if b.team < b.top5_median - 1e-9:
                years.append(int(y))
        if n:
            rows.append({"critério": f, "rótulo": schema.label(f), "edições": n,
                         "abaixo da mediana": below_med, "abaixo do top-5": below_top5,
                         "recorrência": below_top5 / n, "anos abaixo do top-5": years})
    return pd.DataFrame(rows)


def relative_series(df: pd.DataFrame, team_key: str, field: str) -> pd.DataFrame:
    """Série comparável entre edições: valor da equipe / mediana do top-5 da edição."""
    out = []
    for y in sorted(df["year"].unique()):
        b = bench_criterion(df, y, team_key, field)
        if b is None:
            continue
        rel = b.team / b.top5_median if abs(b.top5_median) > 1e-9 else np.nan
        out.append({"year": y, "equipe": b.team, "mediana top-5": b.top5_median, "campeão": b.champion,
                    "mediana (com voo)": b.flyers_median, "relativo ao top-5": rel, "rank": b.rank, "n": b.n})
    return pd.DataFrame(out)
