"""SAE AeroDesign Intelligence V0 — Classe Regular.

Executar:  streamlit run app.py
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="SAE AeroDesign Intelligence", page_icon="✈️", layout="wide")

from aerointel import db  # noqa: E402
from aerointel.ingest import ingest_folder  # noqa: E402

# Primeira execução: popula a base com os PDFs de data/raw
if not db.DEFAULT_DB.exists() or db.read_table("results").empty:
    with st.spinner("Importando PDFs de data/raw…"):
        ingest_folder(ROOT / "data" / "raw", verbose=False)

pages = [
    st.Page("ui/p01_visao_geral.py", title="01 — Visão geral", icon="🧭", default=True),
    st.Page("ui/p02_historico.py", title="02 — Análise histórica", icon="📈"),
    st.Page("ui/p03_benchmarking.py", title="03 — Benchmarking", icon="🏁"),
    st.Page("ui/p04_diagnostico.py", title="04 — Diagnóstico", icon="🩺"),
    st.Page("ui/p05_relatorio.py", title="05 — Relatório estratégico", icon="📄"),
    st.Page("ui/p06_documentos.py", title="06 — Documentos e dados", icon="🗂️"),
]
st.navigation(pages).run()
