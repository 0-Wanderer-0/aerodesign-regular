"""O motor JS do site (site/src/engine.js) reproduz os números do Python para TODAS as equipes."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from aerointel import analysis, db, diagnosis  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node não instalado")


@pytest.fixture(scope="module")
def js_results(tmp_path_factory):
    import build_site
    p = tmp_path_factory.mktemp("site") / "data.json"
    p.write_text(json.dumps(build_site.build_data(), ensure_ascii=False))
    out = subprocess.run(["node", str(ROOT / "site" / "tests" / "parity.js"), str(p)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_parity_all_teams(js_results):
    df = analysis.add_derived(db.load_results())
    assert len(js_results) == len(df)
    mismatches = []
    for item in js_results:
        y, k = item["year"], item["key"]
        py = diagnosis.diagnose(df, y, k)
        pyd = [[d.criterio, d.status, analysis.bench_criterion(df, y, k, d.criterio).rank, round(d.meta_valor, 6),
                round(d.impacto_pts, 4), d.impacto_posicoes, d.confianca] for d in py]
        for a, b in zip(pyd, item["d"]):
            if a[:3] != b[:3] or abs(a[3] - b[3]) > 1e-4 or abs(a[4] - b[4]) > 1e-3 or a[5] != b[5] or a[6] != b[6]:
                mismatches.append((y, k, a, b))
        pod = analysis.podium_gap(df, y, k)["pontos_para_podio"]
        if abs(pod - item["podium"]) > 1e-3:
            mismatches.append((y, k, "podium", pod, item["podium"]))
        pp = diagnosis.priority_matrix(df, y, k)
        if (list(pp["critério"]) if not pp.empty else []) != item["p"]:
            mismatches.append((y, k, "prio", list(pp["critério"]) if not pp.empty else [], item["p"]))
    assert not mismatches, mismatches[:5]
