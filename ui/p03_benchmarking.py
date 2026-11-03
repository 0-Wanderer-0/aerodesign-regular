import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.common import (C_TEAM, SERIES, analysis, load_data, need_team, num, plotly_layout, schema,
                       sidebar_selector)

df = load_data()
key, year = sidebar_selector(df)
need_team(key)
st.title("03 — Benchmarking")
y = df[df.year == year].sort_values("pos")
names = y.set_index("team_key")["team_name"].to_dict()

refs = analysis.reference_teams(df, year, key)
c1, c2 = st.columns([1, 2])
group = c1.radio("Grupo de referência", list(refs.keys()), index=2)
sel_default = [k for k in refs[group] if k in names and k != key]
chosen = c2.multiselect("Equipes para comparar (edição selecionada)", [k for k in names if k != key],
                        default=sel_default[:6], format_func=lambda k: names[k])
if group == "campeões históricos":
    st.caption("Campeões históricos: " + ", ".join(df[df.pos == 1].sort_values("year").apply(lambda r: f"{r.year}: {r.team_name}", axis=1)))

teams = [key] + chosen
fields = [f for f in analysis.fields_in_year(df, year) if f != "total_melhor_bateria"]

st.subheader("Desempenho por critério")
tab = analysis.compare_teams(df, year, teams, fields)
tab.columns = ["Posição", "Total"] + [schema.label(f) for f in fields if f != "total_geral"]
st.dataframe(tab.T.style.format(lambda v: num(v) if isinstance(v, float) else v), width="stretch")

st.subheader("Percentil na edição por critério")
st.markdown("Percentil 100 = melhor equipe da edição no critério. Permite comparar critérios de escalas diferentes.")
pct = {}
for f in fields:
    if f == "total_geral":
        continue
    r = analysis.rank_in_criterion(df, year, f)
    pct[f] = 1 - (r - 1) / max(len(y) - 1, 1)
pct = pd.DataFrame(pct)
pct["team_key"] = y["team_key"].values
pct = pct.set_index("team_key")
cats = [schema.label(f) for f in pct.columns]
fig = go.Figure()
for i, k in enumerate(teams[:8]):
    vals = list(pct.loc[k].values * 100)
    fig.add_scatterpolar(r=vals + vals[:1], theta=cats + cats[:1], name=names[k],
                         line=dict(color=SERIES[i % 8], width=3 if k == key else 2), fill="toself" if k == key else None,
                         opacity=1 if k == key else 0.85)
fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], gridcolor="#e1e0d9")), height=520,
                  legend=dict(orientation="h", y=-0.1), margin=dict(l=40, r=40, t=30, b=30))
st.plotly_chart(fig, width="stretch")
if len(teams) > 8:
    st.caption("Radar limitado a 8 equipes para manter cores distinguíveis.")

st.subheader("Onde as equipes de referência são superiores")
rows = []
for k in chosen:
    for f in fields:
        if f == "total_geral":
            continue
        a, b = float(y.set_index("team_key").at[k, f]), float(y.set_index("team_key").at[key, f])
        if a - b > 0.5:
            rows.append({"equipe de referência": names[k], "critério": schema.label(f), "referência": a,
                         "sua equipe": b, "vantagem (pts)": a - b})
if rows:
    v = pd.DataFrame(rows).sort_values("vantagem (pts)", ascending=False)
    agg = v.groupby("critério")["vantagem (pts)"].agg(["count", "median"]).sort_values("median", ascending=False)
    agg.columns = ["nº de referências superiores", "vantagem mediana (pts)"]
    st.dataframe(agg.round(2), width="stretch")
    with st.expander("Detalhe por equipe"):
        st.dataframe(v.round(2), hide_index=True, width="stretch")
else:
    st.info("Selecione equipes de referência.")

st.subheader(f"Ranking completo — {year}")
show = y[["pos", "team_name", "school", "uf", "total_geral", "total_melhor_bateria", "notas_rel_apres",
          "pontos_confiab", "total_video", "pen_competicao", "carga_paga", "peso_vazio", "ee_calc"]].copy()
show.columns = ["Pos", "Equipe", "Escola", "UF", "Total", "Melhor bateria", "Notas", "Confiab.", "Vídeo",
                "Penal. comp.", "CP (kg)", "PV (kg)", "EE [derivado]"]
st.dataframe(show.style.apply(lambda r: [f"background-color:#cde2fb" if r["Equipe"] == names[key] else "" for _ in r], axis=1)
             .format(precision=2), hide_index=True, width="stretch", height=420)
