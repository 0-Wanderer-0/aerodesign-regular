import plotly.graph_objects as go
import streamlit as st

from ui.common import (C_TEAM, C_TOP5, analysis, diagnosis, kpi, load_data, need_team, num, plotly_layout, schema,
                       sidebar_selector, status_badge)

df = load_data()
key, year = sidebar_selector(df)
need_team(key)
me = df[(df.year == year) & (df.team_key == key)].iloc[0]
diags = diagnosis.diagnose(df, year, key)
st.title("04 — Diagnóstico crítico")
st.caption(f"{me.team_name} · {year} · {int(me.pos)}º/{int(me.n_equipes)} · {num(me.total_geral)} pts")

lim = diagnosis.limiting_criteria(diags)
fortes = diagnosis.strengths(diags)
c1, c2 = st.columns(2)
with c1:
    st.subheader("O que limita a classificação")
    for d in lim:
        st.markdown(f"{status_badge(d.status)} **{d.rotulo}** — +{num(d.impacto_pts)} pts · {d.impacto_posicoes:+d} posições "
                    f"(→ {d.pos_simulada}º) · confiança {d.confianca}", unsafe_allow_html=True)
with c2:
    st.subheader("Pontos fortes")
    st.markdown(", ".join(d.rotulo for d in fortes) or "Nenhum critério no nível de referência.")

st.subheader("Quanto falta para o pódio")
pod = analysis.podium_gap(df, year, key)
k = st.columns(3)
k[0].markdown(kpi("Pontos para o pódio", f"+{num(pod['pontos_para_podio'])}", f"3º: {pod['terceiro']}"), unsafe_allow_html=True)
k[1].markdown(kpi("Pontos para o título", f"+{num(pod['pontos_para_titulo'])}", f"Campeão: {pod['campeao']}"), unsafe_allow_html=True)
dec = pod["decomposicao"]
k[2].markdown(kpi("Maior lacuna vs 3º", dec.loc[dec['Δ vs 3º'].idxmax(), 'bloco'], f"+{num(dec['Δ vs 3º'].max())} pts"), unsafe_allow_html=True)
d2 = dec[dec["Δ vs 3º"].abs() > 0.005]
fig = go.Figure(go.Waterfall(
    x=["Equipe"] + d2["bloco"].tolist() + ["3º colocado"],
    measure=["absolute"] + ["relative"] * len(d2) + ["total"],
    y=[pod["equipe_total"]] + d2["Δ vs 3º"].tolist() + [0],
    text=[num(pod["equipe_total"])] + [num(v, signed=True) for v in d2["Δ vs 3º"]] + [num(pod["terceiro_total"])],
    textposition="outside", connector=dict(line=dict(color="#c3c2b7", width=1)),
    increasing=dict(marker=dict(color=C_TOP5)), decreasing=dict(marker=dict(color="#d03b3b")),
    totals=dict(marker=dict(color=C_TEAM))))
plotly_layout(fig, height=380, y_title="Pontos")
fig.update_layout(title=f"Da pontuação da equipe à do 3º colocado ({pod['terceiro']})", hovermode="closest", showlegend=False)
st.plotly_chart(fig, width="stretch")

st.subheader("Simulador de cenários")
st.markdown("Ajuste os blocos e veja a posição resultante (demais equipes fixas). Valores iniciais = oficiais.")
sim_fields = [f for f in ["notas_rel_apres", "pontos_voo", "pontos_acurac", "bonus_pouso", "bonus_tempo_carga",
                          "pontos_confiab", "total_video", "pen_dim_pot", "pen_validacao", "pen_competicao"]
              if f in df and df[df.year == year][f].notna().any()]
cols = st.columns(3)
changes = {}
for i, f in enumerate(sim_fields):
    e = df[df.year == year][f]
    lo, hi = float(min(e.min(), me[f])), float(max(e.max(), me[f]))
    v = cols[i % 3].slider(schema.label(f), lo, hi if hi > lo else lo + 1, float(me[f]), step=0.5, key=f"sim_{f}_{year}_{key}")
    if abs(v - float(me[f])) > 1e-9:
        changes[f] = v
res = analysis.simulate(df, year, key, changes)
st.markdown(f"**Total simulado: {num(res['total_simulado'])}** ({num(res['ganho'], signed=True)}) → "
            f"**{res['pos_simulada']}º** ({res['posicoes_ganhas']:+d} posições)")

st.subheader("Diagnóstico por critério")
for d in sorted(diags, key=lambda d: -d.impacto_pts):
    with st.expander(f"{d.rotulo} — {d.status} · +{num(d.impacto_pts)} pts · confiança {d.confianca}",
                     expanded=d in lim[:1]):
        st.markdown(f"**Problema identificado:** {d.problema}")
        st.markdown(f"**Evidência quantitativa:** {d.evidencia}")
        st.markdown(f"**Comparação histórica:** {d.comparacao_historica}")
        st.markdown(f"**Comparação competitiva:** {d.comparacao_competitiva}")
        if d.interpretacao:
            st.markdown(f"**Interpretação técnica:** {d.interpretacao}")
        st.markdown(f"**Recomendação:** {d.recomendacao}")
        st.markdown(f"**Impacto potencial:** +{num(d.impacto_pts)} pts, {d.impacto_posicoes:+d} posições (→ {d.pos_simulada}º).")
        st.markdown(f"**Grau de confiança:** {d.confianca} — {d.confianca_motivo}.")
        if d.hipoteses:
            st.warning("Hipóteses a confirmar com dados internos: " + "; ".join(d.hipoteses))
        st.caption("Referências: " + " · ".join(d.referencias))

st.subheader("Deficiências recorrentes")
rec = analysis.recurrence(df, key)
if not rec.empty:
    rec["recorrência"] = (rec["recorrência"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(rec, hide_index=True, width="stretch")
    st.caption("Recorrência = fração das edições disputadas em que a equipe ficou abaixo da mediana do top-5 no critério.")
