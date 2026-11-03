"""Gera o site estático (open source) a partir da base histórica.

    python scripts/build_site.py            # → site/dist/index.html (arquivo único) + site/dist/data.json

O site não tem servidor: os dados vão embutidos no HTML e todos os cálculos de
comparação rodam no navegador (site/src/engine.js, porte de aerointel/analysis.py
e aerointel/diagnosis.py — a paridade é verificada em tests/test_site_parity.py).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aerointel import analysis, db, diagnosis, rules, schema  # noqa: E402

SRC = ROOT / "site" / "src"
DIST = ROOT / "site" / "dist"

EXPORT_COLS = (["year", "pos", "numero", "team_name", "team_key", "school", "uf", "source_file", "page", "row_index"]
               + [k for k in schema.FIELDS] + ["ee_calc", "fator_residual", "queda_2a_bateria", "voou", "n_equipes",
                                               "pct_campeao", "percentil_total"])


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return round(v, 6)
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def build_data() -> dict:
    df = analysis.add_derived(db.load_results())
    docs = db.read_table("documents").query("status == 'validado'")
    cols = [c for c in EXPORT_COLS if c in df]
    rows = [[_clean(v) for v in r] for r in df[cols].itertuples(index=False, name=None)]
    regs = {}
    for y, reg in rules.REGULATIONS.items():
        regs[str(y)] = {"file": reg["file"], "revision": reg["revision"],
                        "max": {k: [v[0], str(v[1])] for k, v in reg["max"].items()},
                        "refs": {k: str(v) for k, v in reg["refs"].items()}}
    return {
        "generated": date.today().isoformat(),
        "columns": cols,
        "rows": rows,
        "fields": {k: {"label": f.label, "kind": f.kind, "group": f.group, "hib": f.higher_is_better,
                       "dtype": f.dtype, "note": f.note} for k, f in schema.FIELDS.items()},
        "derived": schema.DERIVED,
        "dashboard": schema.DASHBOARD_CRITERIA,
        "score_criteria": diagnosis.SCORE_CRITERIA,
        "total_components": schema.TOTAL_COMPONENTS,
        "battery_components": schema.BATTERY_COMPONENTS,
        "penalties": sorted(schema.PENALTY_FIELDS),
        "effort": diagnosis.DEFAULT_EFFORT,
        "regulations": regs,
        "editions": [{"year": int(r.year), "edition_no": int(r.edition_no), "file": r.filename,
                      "title": r.title, "regime": r.points_regime} for r in docs.sort_values("year").itertuples()],
    }


def build(out_dir: Path = DIST) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out_dir / "data.json").write_text(payload, encoding="utf-8")
    html = (SRC / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__STYLE__*/", (SRC / "style.css").read_text(encoding="utf-8"))
    html = html.replace("/*__ENGINE__*/", (SRC / "engine.js").read_text(encoding="utf-8"))
    html = html.replace("/*__APP__*/", (SRC / "app.js").read_text(encoding="utf-8"))
    html = html.replace("/*__DATA__*/null", payload.replace("</", "<\\/"))
    out = out_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"site gerado: {out} ({out.stat().st_size / 1024:.0f} KiB, {len(data['rows'])} linhas)")
    return out


if __name__ == "__main__":
    build()
