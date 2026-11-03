import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from aerointel import db, ingest, rules
from aerointel.extraction import parse_number
from ui.common import ROOT, load_data, refresh, schema, sidebar_selector

df = load_data()
sidebar_selector(df)
st.title("06 — Documentos e dados")

tabs = st.tabs(["Importar resultados", "Documentos", "Validação e correção", "Apelidos de equipes",
                "Histórico de processamento", "Regulamentos", "Base completa"])

# ---------------------------------------------------------------- importar
with tabs[0]:
    st.markdown("Envie o PDF oficial de **pontuação final da Classe Regular**. O sistema identifica a edição pelo título, "
                "extrai a tabela, valida a aritmética e só incorpora depois da sua aprovação. PDFs da Advanced ou Micro são recusados.")
    up = st.file_uploader("PDF de resultados", type=["pdf"])
    if up is not None:
        raw_dir = ROOT / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp()) / up.name
        tmp.write_bytes(up.getvalue())
        res, issues, regime = ingest.stage(tmp)
        dup = db.document_exists(res.sha256)
        st.markdown(f"**Edição detectada:** {res.year} ({res.edition_no}ª competição) · **Classe:** {res.competition_class} · "
                    f"**Equipes:** {len(res.rows)} · **Regime da coluna de carga:** {regime}")
        if dup:
            st.info(f"Este arquivo já está na base ({dup['filename']}, status {dup['status']}).")
        iss = pd.DataFrame([i.as_dict() for i in issues])
        if not iss.empty:
            st.dataframe(iss, hide_index=True, width="stretch")
        st.markdown("**Pré-visualização (edite células se a extração errou; as edições ficam registradas como correções):**")
        cols = ["pos", "numero", "team_name", "school", "uf"] + [c for c in res.tail_columns]
        edited = st.data_editor(res.rows[cols], width="stretch", height=360, key=f"stage_{res.sha256[:8]}")
        errors = [i for i in issues if i.level == "erro"]
        if errors:
            st.error("Há erros de extração. Corrija o documento ou registre o problema antes de incorporar.")
        elif st.button("Validar e incorporar à base", type="primary"):
            diffs = []
            for c in cols:
                for i in res.rows.index:
                    a, b = res.rows.at[i, c], edited.at[i, c]
                    if str(a) != str(b):
                        diffs.append((i, c, b))
            dest = raw_dir / up.name
            dest.write_bytes(up.getvalue())
            doc_id = ingest.commit(res, issues, regime)
            if diffs:
                ids = db.read_table("results").query("doc_id == @doc_id").set_index("row_index")["id"]
                for i, c, v in diffs:
                    db.add_correction(int(ids[int(res.rows.at[i, "row_index"])]), c, v, "Correção na validação da importação")
            refresh()
            st.success(f"Incorporado (documento #{doc_id}, {len(diffs)} correção(ões) registrada(s)).")

# ---------------------------------------------------------------- documentos
with tabs[1]:
    docs = db.read_table("documents")
    if not docs.empty:
        docs["tail_columns"] = docs["tail_columns"].map(lambda s: len(json.loads(s)) if s else 0)
        docs = docs.rename(columns={"tail_columns": "nº colunas numéricas"})
    st.dataframe(docs.drop(columns=["sha256"], errors="ignore"), hide_index=True, width="stretch")
    years = sorted(df.year.unique()) if not df.empty else []
    exp = list(range(min(years), max(years) + 1)) if years else []
    miss = [y for y in exp if y not in years]
    if miss:
        st.warning(f"Edições ausentes na base: {', '.join(map(str, miss))}.")

# ---------------------------------------------------------------- correção
with tabs[2]:
    st.markdown("Correções manuais nunca apagam o valor original: ficam numa tabela de auditoria e são aplicadas na leitura.")
    if not df.empty:
        y = st.selectbox("Edição", sorted(df.year.unique()), key="corr_year")
        e = df[df.year == y]
        rid = st.selectbox("Linha", e["id"], format_func=lambda i: f"{int(e.set_index('id').at[i, 'pos'])}º — {e.set_index('id').at[i, 'team_name']}")
        fields = ["team_name", "school", "uf", "pos"] + list(schema.FIELDS)
        f = st.selectbox("Campo", fields, format_func=schema.label)
        cur = e.set_index("id").at[rid, f] if f in e else None
        st.caption(f"Valor atual: {cur}")
        newv = st.text_input("Novo valor")
        why = st.text_input("Motivo (obrigatório)")
        if st.button("Registrar correção", disabled=not (newv and why)):
            v = parse_number(newv) if f not in ("team_name", "school", "uf") else newv
            db.add_correction(int(rid), f, v, why)
            refresh()
            st.success("Correção registrada.")
    st.markdown("**Correções registradas**")
    st.dataframe(db.read_table("corrections"), hide_index=True, width="stretch")
    st.markdown("**Inconsistências detectadas na validação**")
    log = db.read_table("processing_log")
    docs = db.read_table("documents")[["id", "filename", "year"]].rename(columns={"id": "doc_id"})
    st.dataframe(log.merge(docs, on="doc_id", how="left").query("level != 'info' or message.str.contains('≠|zerada')", engine="python")
                 [["year", "filename", "level", "row_index", "field", "message"]], hide_index=True, width="stretch")

# ---------------------------------------------------------------- apelidos
with tabs[3]:
    st.markdown("Use quando a mesma equipe aparece com grafias diferentes entre edições. "
                "A unificação é explícita e reversível.")
    if not df.empty:
        keys = sorted(df["original_team_key"].unique())
        names = df.groupby("original_team_key").apply(
            lambda g: f"{g.iloc[-1].team_name} ({', '.join(map(str, sorted(g.year)))})", include_groups=False).to_dict()
        c1, c2 = st.columns(2)
        a = c1.selectbox("Grafia a unificar", keys, format_func=lambda k: names[k])
        b = c2.selectbox("Equipe canônica", keys, format_func=lambda k: names[k])
        if st.button("Unificar", disabled=a == b):
            db.add_alias(a, b, "manual")
            refresh()
            st.rerun()
        al = db.read_table("aliases")
        st.dataframe(al, hide_index=True, width="stretch")
        if not al.empty:
            rm = st.selectbox("Remover apelido", al["alias_key"])
            if st.button("Remover"):
                db.remove_alias(rm)
                refresh()
                st.rerun()
        single = df.groupby("team_key")["year"].nunique()
        st.caption(f"{(single == 1).sum()} equipes aparecem em uma única edição — candidatas a revisão de grafia.")

# ---------------------------------------------------------------- log
with tabs[4]:
    log = db.read_table("processing_log")
    st.dataframe(log.sort_values("id", ascending=False), hide_index=True, width="stretch", height=420)

# ---------------------------------------------------------------- regulamentos
with tabs[5]:
    st.markdown("Fórmulas, pesos e tetos usados nas interpretações. Só edições com regulamento registrado recebem "
                "interpretação causal; as demais ficam restritas a comparações observadas.")
    for yv, reg in rules.REGULATIONS.items():
        st.markdown(f"**{yv}** — `{reg['file']}` {reg['revision']}")
        st.dataframe(pd.DataFrame([{"critério": schema.label(k), "teto": v[0], "referência": str(v[1])} for k, v in reg["max"].items()]),
                     hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"item": schema.label(k), "referência": str(v)} for k, v in reg["refs"].items()]),
                     hide_index=True, width="stretch")
    have = set(rules.REGULATIONS)
    st.warning("Regulamentos ausentes para: " + ", ".join(str(y) for y in sorted(df.year.unique()) if y not in have))
    reg_dir = ROOT / "data" / "regulamentos"
    if reg_dir.exists():
        st.caption("Arquivos em data/regulamentos: " + ", ".join(p.name for p in reg_dir.glob("*.pdf")))

# ---------------------------------------------------------------- base
with tabs[6]:
    st.dataframe(df, hide_index=True, width="stretch", height=420)
    st.download_button("Baixar base (CSV)", df.drop(columns=["corrected_fields"]).to_csv(index=False).encode("utf-8-sig"),
                       "base_historica_regular.csv", "text/csv")
