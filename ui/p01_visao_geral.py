import plotly.graph_objects as go
import streamlit as st

from ui.common import (C_CHAMP, C_FIELD, C_TEAM, C_TOP5, LEGEND, analysis, block_card, diagnosis, kpi,
                       load_data, need_team, num, plotly_layout, sidebar_selector)

df = load_data()
key, year = sidebar_selector(df)
need_team(key)

me = df[(df.year == year) & (df.team_key == key)].iloc[0]
hist = analysis.team_history(df, key)
pod = analysis.podium_gap(df, year, key)

st.title(f"{me.team_name}")
st.caption(f"{me.school} · {me.uf} · Edição de referência {year} · fonte: {me.source_file}, p. {int(me.page)}")

c = st.columns(5)
c[0].markdown(kpi("Posição", f"{int(me.pos)}º", f"de {int(me.n_equipes)} equipes"), unsafe_allow_html=True)
c[1].markdown(kpi("Pontuação total", num(me.total_geral), f"{num(100 * me.pct_campeao, 0)}% do campeão"), unsafe_allow_html=True)
c[2].markdown(kpi("Para o pódio", f"+{num(pod['pontos_para_podio'])}", f"3º: {pod['terceiro']} ({num(pod['terceiro_total'])})"), unsafe_allow_html=True)
best = hist.loc[hist.pos.idxmin()]
c[3].markdown(kpi("Melhor classificação", f"{int(best.pos)}º", f"em {int(best.year)}"), unsafe_allow_html=True)
c[4].markdown(kpi("Temporadas analisadas", str(len(hist)), ", ".join(map(str, hist.year))), unsafe_allow_html=True)

st.subheader(f"Blocos por categoria — {year}")
st.markdown("Cada bloco compara a equipe **apenas com outras equipes da mesma edição**. A meta é a mediana do top-5 "
            "(ou o melhor valor observado, se a equipe já estiver acima dela).")
st.markdown(LEGEND, unsafe_allow_html=True)
diags = {d.criterio: d for d in diagnosis.diagnose(df, year, key)}
order = sorted(diags.values(), key=lambda d: ({"crítico": 0, "atenção": 1, "forte": 2}[d.status], -d.impacto_pts))
cards = []
for d in order:
    b = analysis.bench_criterion(df, year, key, d.criterio)
    cards.append(block_card(df, year, d, b))
st.markdown("<div class='block-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
st.caption("Ganho simulado supõe as demais equipes inalteradas. Detalhes, evidências e referências na página 04.")

st.subheader("Evolução do desempenho")
summ = analysis.edition_summary(df).set_index("year")
col1, col2 = st.columns(2)
with col1:
    f = go.Figure()
    f.add_scatter(x=hist.year, y=hist.total_geral, name=me.team_name, mode="lines+markers", line=dict(color=C_TEAM, width=2), marker=dict(size=9))
    f.add_scatter(x=summ.index, y=summ["total_campeão"], name="Campeão", mode="lines+markers", line=dict(color=C_CHAMP, width=2), marker=dict(size=8))
    f.add_scatter(x=summ.index, y=summ["mediana_top5"], name="Mediana top-5", mode="lines+markers", line=dict(color=C_TOP5, width=2), marker=dict(size=8))
    f.add_scatter(x=summ.index, y=summ["média_geral"], name="Média geral", mode="lines+markers", line=dict(color=C_FIELD, width=2, dash="dot"), marker=dict(size=8))
    plotly_layout(f, y_title="Pontuação total", x_title="Edição").update_xaxes(dtick=1)
    f.update_layout(title="Pontuação total")
    st.plotly_chart(f, width="stretch")
with col2:
    f = go.Figure()
    f.add_scatter(x=hist.year, y=hist.pos, mode="lines+markers+text", text=[f"{int(p)}º" for p in hist.pos],
                  textposition="top center", line=dict(color=C_TEAM, width=2), marker=dict(size=9), name="Posição")
    plotly_layout(f, y_title="Posição", x_title="Edição").update_yaxes(autorange="reversed").update_xaxes(dtick=1)
    f.update_layout(title="Classificação", showlegend=False)
    st.plotly_chart(f, width="stretch")
st.caption("Pontos totais não são estritamente comparáveis entre edições (fórmulas mudam); observe a distância relativa às referências.")
