import plotly.graph_objects as go
import streamlit as st

from ui.common import (C_CHAMP, C_FIELD, C_TEAM, C_TOP5, analysis, load_data, need_team, num, plotly_layout,
                       schema, sidebar_selector)

df = load_data()
key, year = sidebar_selector(df)
need_team(key)
hist = analysis.team_history(df, key)
st.title("02 — Análise histórica")
st.caption(f"{hist.iloc[-1].team_name} · edições {', '.join(map(str, hist.year))}")

st.subheader("Desempenho relativo por critério (equipe ÷ mediana do top-5 da edição)")
st.markdown("Esta é a forma comparável entre anos: cada valor é dividido pela referência da **própria edição**. "
            "100% = igual à mediana do top-5.")
crit = [c for c in schema.DASHBOARD_CRITERIA if c not in schema.PENALTY_FIELDS]
rows = []
for c in crit:
    rs = analysis.relative_series(df, key, c)
    for _, r in rs.iterrows():
        rows.append({"critério": schema.label(c), "ano": int(r.year), "rel": r["relativo ao top-5"],
                     "txt": f"{num(r.equipe)} / {num(r['mediana top-5'])}"})
import pandas as pd  # noqa: E402
m = pd.DataFrame(rows)
if not m.empty:
    pv = m.pivot(index="critério", columns="ano", values="rel")
    tx = m.pivot(index="critério", columns="ano", values="txt")
    z = pv.clip(upper=1.5).values
    lab = pv.map(lambda v: "" if pd.isna(v) else f"{v * 100:.0f}%")
    hov = lab + "  (" + tx.fillna("") + ")"
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(c) for c in pv.columns], y=pv.index, text=lab.values, texttemplate="%{text}",
        customdata=hov.values, zmin=0, zmax=1.5,
        colorscale=[[0, "#d03b3b"], [0.6667, "#f0efec"], [1, "#2a78d6"]], xgap=2, ygap=2,
        hovertemplate="%{y} · %{x}<br>%{customdata} da mediana top-5<extra></extra>",
        colorbar=dict(title="÷ top-5", tickformat=".0%")))
    fig.update_xaxes(type="category")
    plotly_layout(fig, height=420)
    fig.update_layout(hovermode="closest")
    st.plotly_chart(fig, width="stretch")
    st.caption("Vermelho = abaixo da referência; azul = acima. Mediana top-5 = 0 gera célula vazia (divisão indefinida).")

st.subheader("Critério ao longo das edições")
c = st.selectbox("Critério", schema.DASHBOARD_CRITERIA + ["carga_paga", "peso_vazio", "ee_calc", "fpv", "fator_residual"],
                 format_func=schema.label)
rs = analysis.relative_series(df, key, c) if c in schema.FIELDS and schema.FIELDS[c].kind == "score" else None
if rs is None or rs.empty:
    # indicadores: calcula referências diretamente
    out = []
    for y in sorted(df.year.unique()):
        e = df[df.year == y]
        me = e[e.team_key == key]
        if me.empty:
            continue
        out.append({"year": y, "equipe": me.iloc[0][c], "mediana top-5": e.nsmallest(5, "pos")[c].median(),
                    "campeão": e.nsmallest(1, "pos")[c].iloc[0], "mediana (com voo)": e[e.voou][c].median()})
    rs = pd.DataFrame(out)
f = go.Figure()
for col, color, dash in [("equipe", C_TEAM, None), ("mediana top-5", C_TOP5, None), ("campeão", C_CHAMP, None),
                         ("mediana (com voo)", C_FIELD, "dot")]:
    f.add_scatter(x=rs.year, y=rs[col], name=col.capitalize(), mode="lines+markers",
                  line=dict(color=color, width=2, dash=dash), marker=dict(size=8))
plotly_layout(f, y_title=schema.label(c), x_title="Edição").update_xaxes(dtick=1)
st.plotly_chart(f, width="stretch")
if c == "pontos_carga_ee":
    st.warning("2022–2024: 12,5 × CP · 2026: 50 × EE. Valores de regimes diferentes não são comparáveis.")
elif c in ("pontos_voo", "total_melhor_bateria"):
    st.info("A fórmula de pontos de voo mudou (carga → EE em 2026). Compare a distância para as referências, não o valor absoluto.")
st.dataframe(rs.round(3), hide_index=True, width="stretch")

st.subheader("Panorama das edições")
st.dataframe(analysis.edition_summary(df).round(2), hide_index=True, width="stretch")

st.subheader(f"Variabilidade dos critérios — {year} (equipes com voo)")
st.markdown("Critérios com maior amplitude são onde a classificação mais se decide.")
st.dataframe(analysis.criterion_variability(df, year).round(2), hide_index=True, width="stretch")
