import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from aerointel import llm, report
from ui.common import (C_TEAM, analysis, diagnosis, load_data, need_team, num, plotly_layout, sidebar_selector)

df = load_data()
key, year = sidebar_selector(df)
need_team(key)
me = df[(df.year == year) & (df.team_key == key)].iloc[0]
st.title("05 — Relatório estratégico")
st.caption(f"{me.team_name} · base {year}")

st.subheader("Matriz de priorização")
st.markdown("Ganho potencial, posições e recorrência vêm dos resultados. **Esforço, custo e risco são estimativas** "
            "(1 = baixo, 5 = alto) — edite conforme a realidade da equipe.")
ed_key = f"effort_{key}"
if ed_key not in st.session_state:
    st.session_state[ed_key] = {}
w = st.columns(4)
weights = {"potencial": w[0].slider("Peso: ganho", 0.0, 1.0, 0.35, 0.05),
           "posicoes": w[1].slider("Peso: posições", 0.0, 1.0, 0.25, 0.05),
           "recorrencia": w[2].slider("Peso: recorrência", 0.0, 1.0, 0.15, 0.05),
           "facilidade": w[3].slider("Peso: facilidade", 0.0, 1.0, 0.25, 0.05)}
prio = diagnosis.priority_matrix(df, year, key, effort=st.session_state[ed_key], weights=weights)
if prio.empty:
    st.success("Nenhum critério abaixo da referência nesta edição.")
    st.stop()
edit = st.data_editor(
    prio[["prioridade", "rótulo", "ganho potencial (pts)", "posições ganhas", "recorrência", "esforço", "custo", "risco",
          "prazo", "confiança", "meta", "fonte da meta", "score", "critério"]],
    disabled=["prioridade", "rótulo", "ganho potencial (pts)", "posições ganhas", "recorrência", "confiança", "meta",
              "fonte da meta", "score", "critério"],
    column_config={"esforço": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
                   "custo": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
                   "risco": st.column_config.NumberColumn(min_value=1, max_value=5, step=1),
                   "recorrência": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
                   "score": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                   "ganho potencial (pts)": st.column_config.NumberColumn(format="%.1f"),
                   "meta": st.column_config.NumberColumn(format="%.2f")},
    hide_index=True, width="stretch", key=f"editor_{key}_{year}")
new_effort = {r["critério"]: dict(esforco=int(r["esforço"]), custo=int(r["custo"]), risco=int(r["risco"]),
                                  prazo=r["prazo"], disciplinas=diagnosis.DEFAULT_EFFORT.get(r["critério"], {}).get("disciplinas", "—"))
              for _, r in edit.iterrows()}
if st.button("Recalcular prioridades com as estimativas editadas"):
    st.session_state[ed_key] = new_effort
    st.rerun()

fig = go.Figure(go.Scatter(
    x=prio["facilidade"], y=prio["ganho potencial (pts)"], mode="markers+text", text=prio["rótulo"],
    textposition=["top center" if i % 2 == 0 else "bottom center" for i in range(len(prio))], marker=dict(size=12 + 4 * prio["posições ganhas"].clip(lower=0), color=C_TEAM,
                                           line=dict(color="#fcfcfb", width=2)),
    customdata=prio[["posições ganhas", "esforço", "custo", "risco"]].values,
    hovertemplate="%{text}<br>Ganho %{y:.1f} pts · %{customdata[0]} posições<br>Esforço %{customdata[1]} · "
                  "Custo %{customdata[2]} · Risco %{customdata[3]}<extra></extra>"))
plotly_layout(fig, height=420, x_title="Facilidade (estimativa: 1 − esforço/custo/risco normalizados)", y_title="Ganho potencial (pts)")
fig.update_layout(title="Retorno × facilidade (tamanho = posições ganhas)", hovermode="closest")
fig.update_xaxes(range=[-0.05, 1.15])
st.plotly_chart(fig, width="stretch")

st.subheader("Metas quantitativas por disciplina")
targ = prio[["rótulo", "meta", "fonte da meta", "ganho potencial (pts)"]].copy()
targ["valor atual"] = [float(me[c]) for c in prio["critério"]]
targ["disciplinas responsáveis"] = [diagnosis.DEFAULT_EFFORT.get(c, {}).get("disciplinas", "—") for c in prio["critério"]]
st.dataframe(targ[["rótulo", "valor atual", "meta", "fonte da meta", "ganho potencial (pts)", "disciplinas responsáveis"]].round(2),
             hide_index=True, width="stretch")
all_in = analysis.simulate(df, year, key, {c: m for c, m in zip(prio["critério"], prio["meta"])})
st.info(f"Se todas as metas fossem atingidas (demais equipes fixas): {num(all_in['total_simulado'])} pts → "
        f"{all_in['pos_simulada']}º lugar. Isso é um teto de cenário, não uma previsão.")

st.subheader("Síntese por IA")
narr_key = f"narr_{key}_{year}"
if llm.available():
    if st.button("Gerar síntese interpretativa"):
        ev = {"equipe": me.team_name, "ano": year, "posicao": int(me.pos), "total": float(me.total_geral),
              "podio": {k: v for k, v in analysis.podium_gap(df, year, key).items() if k != "decomposicao"},
              "diagnosticos": [d.as_dict() for d in diagnosis.diagnose(df, year, key)],
              "prioridades": prio.drop(columns=["score"]).to_dict("records")}
        with st.spinner("Consultando o modelo…"):
            try:
                st.session_state[narr_key] = llm.narrative(ev)
            except Exception as e:  # noqa: BLE001
                st.error(f"Falha na API: {e}")
    if narr_key in st.session_state:
        st.markdown(st.session_state[narr_key])
else:
    st.caption("Defina ANTHROPIC_API_KEY e instale `anthropic` para ativar a síntese por IA. "
               "O diagnóstico abaixo é determinístico e totalmente rastreável.")

st.subheader("Exportar relatório")
md = report.build_markdown(df, year, key, narrative=st.session_state.get(narr_key), effort=st.session_state[ed_key])
fn = f"relatorio_{key.replace(' ', '_')}_{year}"
c1, c2 = st.columns(2)
c1.download_button("Baixar Markdown", md, file_name=f"{fn}.md", mime="text/markdown")
c2.download_button("Baixar HTML (imprimir em PDF pelo navegador)", report.markdown_to_html(md, f"Relatório {me.team_name} {year}"),
                   file_name=f"{fn}.html", mime="text/html")
with st.expander("Pré-visualizar relatório", expanded=False):
    st.markdown(md)
