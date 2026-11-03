"""Componentes compartilhados da interface (sem lógica de cálculo)."""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aerointel import analysis, db, diagnosis, schema  # noqa: E402
from aerointel.fmt import num, pct  # noqa: E402
from aerointel.teams import suggest_matches  # noqa: E402

# Paleta (referência dataviz): papéis fixos por entidade, nunca por rank.
C_TEAM = "#2a78d6"      # equipe selecionada (slot 1)
C_TOP5 = "#eb6834"      # mediana top-5 (slot 2)
C_CHAMP = "#1baf7a"     # campeão (slot 3)
C_FIELD = "#898781"     # mediana geral / contexto (muted)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
STATUS = {"forte": ("#0ca30c", "✔", "Forte"), "atenção": ("#fab219", "▲", "Atenção"),
          "crítico": ("#d03b3b", "✖", "Crítico")}

CSS = """
<style>
.block-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin:6px 0 18px}
.card{background:var(--card-bg,#fcfcfb);border:1px solid rgba(11,11,11,.10);border-radius:10px;padding:14px 16px;
      box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card h4{margin:0 0 2px;font-size:.92rem;font-weight:600;color:#0b0b0b}
.card .val{font-size:1.65rem;font-weight:650;color:#0b0b0b;line-height:1.2}
.card .sub{font-size:.78rem;color:#52514e}
.badge{display:inline-block;font-size:.72rem;font-weight:600;padding:1px 8px;border-radius:999px;color:#0b0b0b;margin-left:6px}
.bullet{position:relative;height:30px;margin:10px 0 4px}
.bullet .track{position:absolute;top:13px;left:0;right:0;height:4px;background:#e1e0d9;border-radius:2px}
.bullet .mk{position:absolute;top:5px;width:3px;height:20px;border-radius:2px;transform:translateX(-1px)}
.bullet .me{position:absolute;top:7px;width:16px;height:16px;border-radius:50%;transform:translateX(-8px);
            border:2px solid #fcfcfb;box-shadow:0 0 0 1px rgba(0,0,0,.15)}
.legend{font-size:.7rem;color:#52514e;display:flex;gap:10px;flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.tip{font-size:.8rem;color:#1d2433;background:#f1f4f9;border-radius:6px;padding:6px 8px;margin-top:8px}
.impact{font-size:.78rem;color:#52514e;margin-top:6px}
.kpi{background:#fcfcfb;border:1px solid rgba(11,11,11,.10);border-radius:10px;padding:12px 14px}
.kpi .l{font-size:.75rem;color:#52514e}.kpi .v{font-size:1.5rem;font-weight:650;color:#0b0b0b}.kpi .s{font-size:.75rem;color:#898781}
.idtable td,.idtable th{padding:4px 10px;font-size:.85rem;border-bottom:1px solid #e1e0d9;text-align:left}
</style>
"""


@st.cache_data(show_spinner=False)
def _load(db_mtime: float) -> pd.DataFrame:
    df = db.load_results()
    return analysis.add_derived(df) if not df.empty else df


def load_data() -> pd.DataFrame:
    p = db.DEFAULT_DB
    return _load(p.stat().st_mtime if p.exists() else 0.0)


def refresh():
    _load.clear()


def team_options(df: pd.DataFrame) -> pd.DataFrame:
    last = df.sort_values("year").groupby("team_key").tail(1)
    hist = df.groupby("team_key").agg(anos=("year", lambda s: ", ".join(map(str, sorted(s)))),
                                      melhor=("pos", "min"))
    o = last.set_index("team_key")[["team_name", "school", "uf"]].join(hist)
    o["label"] = o["team_name"] + " — " + o["school"].str.slice(0, 55) + " (" + o["uf"].fillna("") + ")"
    return o.sort_values("team_name", key=lambda s: s.str.lower())


def sidebar_selector(df: pd.DataFrame) -> tuple[str | None, int | None]:
    st.markdown(CSS, unsafe_allow_html=True)
    if df.empty:
        st.sidebar.warning("Base vazia. Importe PDFs na página 06.")
        return None, None
    opts = team_options(df)
    keys = list(opts.index)
    if "team_key" not in st.session_state or st.session_state.team_key not in keys:
        st.session_state.team_key = "megazord" if "megazord" in keys else keys[0]

    st.sidebar.markdown("### Equipe analisada")
    q = st.sidebar.text_input("Buscar por nome ou universidade", placeholder="ex.: Megazord, UFMG, Keep Flying")
    if q:
        hits = suggest_matches(q, keys, n=8)
        uni = [k for k in keys if q.lower() in str(opts.at[k, "school"]).lower()]
        hits = list(dict.fromkeys(hits + uni))[:10]
        if hits:
            st.sidebar.caption(f"{len(hits)} equipe(s) encontrada(s)")
            if st.session_state.team_key not in hits:
                st.session_state.team_key = hits[0]
            keys_view = hits
        else:
            st.sidebar.caption("Nenhuma equipe encontrada; mostrando todas.")
            keys_view = keys
    else:
        keys_view = keys
    key = st.sidebar.selectbox("Equipe", keys_view, key="team_key",
                               format_func=lambda k: opts.at[k, "label"])
    years = sorted(df[df["team_key"] == key]["year"].unique())
    if st.session_state.get("_year_team") != key:
        st.session_state.year = years[-1]
        st.session_state._year_team = key
    year = st.sidebar.selectbox("Edição de referência", years, key="year")

    ident = analysis.team_identity(df, key)
    rows = "".join(f"<tr><td>{r.year}</td><td>{int(r.pos)}º/{int(r.n_equipes)}</td><td>{num(r.total_geral)}</td></tr>"
                   for r in ident.itertuples())
    st.sidebar.markdown(
        f"**{html.escape(opts.at[key, 'team_name'])}**  \n{html.escape(str(opts.at[key, 'school']))} · {opts.at[key, 'uf']}"
        f"<table class='idtable'><tr><th>Ano</th><th>Ranking</th><th>Total</th></tr>{rows}</table>",
        unsafe_allow_html=True)
    st.sidebar.caption("Classe Regular · dados oficiais SAE BRASIL")
    return key, int(year)


def status_badge(status: str) -> str:
    color, icon, label = STATUS[status]
    ink = "#0b0b0b" if status == "atenção" else "#ffffff"
    return f"<span class='badge' style='background:{color};color:{ink}'>{icon} {label}</span>"


def kpi(label: str, value: str, sub: str = "") -> str:
    return f"<div class='kpi'><div class='l'>{label}</div><div class='v'>{value}</div><div class='s'>{sub}</div></div>"


def bullet_html(df: pd.DataFrame, year: int, b: analysis.CriterionBench) -> str:
    y = df[df["year"] == year][b.field].dropna()
    lo, hi = min(y.min(), b.team), max(y.max(), b.team)
    if hi - lo < 1e-9:
        hi = lo + 1
    pos = lambda v: 100 * (v - lo) / (hi - lo)  # noqa: E731
    marks = [(b.flyers_median, C_FIELD, "Mediana (equipes com voo)"),
             (b.top5_median, C_TOP5, "Mediana top-5"), (b.champion, C_CHAMP, f"Campeão: {b.champion_name}")]
    m = "".join(f"<div class='mk' title='{html.escape(t)}: {num(v)}' style='left:{pos(v):.1f}%;background:{c}'></div>"
                for v, c, t in marks)
    me = f"<div class='me' title='Equipe: {num(b.team)}' style='left:{pos(b.team):.1f}%;background:{C_TEAM}'></div>"
    return (f"<div class='bullet'><div class='track'></div>{m}{me}</div>"
            f"<div class='sub' style='display:flex;justify-content:space-between'><span>{num(lo)}</span><span>{num(hi)}</span></div>")


LEGEND = (f"<div class='legend'><span><i style='background:{C_TEAM};border-radius:50%'></i>Equipe</span>"
          f"<span><i style='background:{C_TOP5}'></i>Mediana top-5</span><span><i style='background:{C_CHAMP}'></i>Campeão</span>"
          f"<span><i style='background:{C_FIELD}'></i>Mediana das equipes com voo</span></div>")


def block_card(df, year, d: diagnosis.Diagnosis, b: analysis.CriterionBench) -> str:
    imp = ("" if d.impacto_pts <= 0.01 else
           f"<div class='impact'>Atingindo a meta: <b>+{num(d.impacto_pts)} pts</b> · "
           f"{d.impacto_posicoes:+d} posições (→ {d.pos_simulada}º)</div>")
    return (f"<div class='card'><h4>{html.escape(b.label)}{status_badge(d.status)}</h4>"
            f"<div class='val'>{num(b.team)}</div>"
            f"<div class='sub'>{b.rank}º de {b.n} no critério · top-5 {num(b.top5_median)} · campeão {num(b.champion)}</div>"
            f"{bullet_html(df, year, b)}{imp}"
            f"<div class='tip'><b>Como melhorar:</b> {html.escape(d.dica)}</div></div>")


def plotly_layout(fig, height=360, y_title=None, x_title=None):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=60), plot_bgcolor="#fcfcfb",
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family="system-ui, Segoe UI, sans-serif", color="#0b0b0b"),
                      legend=dict(orientation="h", yanchor="top", y=-0.18, x=0), hovermode="x unified")
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", title=x_title)
    fig.update_yaxes(gridcolor="#e1e0d9", zeroline=False, title=y_title)
    return fig


def need_team(key):
    if key is None:
        st.info("Importe resultados na página **06 — Documentos e dados** para começar.")
        st.stop()
