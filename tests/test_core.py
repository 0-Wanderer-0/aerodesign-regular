"""Testes dos cálculos de extração, validação, comparação e simulação.

Valores esperados conferidos manualmente nos PDFs oficiais (data/raw).
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aerointel import analysis, db, diagnosis, rules, schema  # noqa: E402
from aerointel.extraction import TITLE_RE, extract_results_pdf, parse_number  # noqa: E402
from aerointel.ingest import ingest_folder  # noqa: E402
from aerointel.teams import team_key  # noqa: E402
from aerointel.validation import detect_points_regime, validate  # noqa: E402

RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def extractions():
    return {r.year: r for r in (extract_results_pdf(p) for p in sorted(RAW.glob("*.pdf")))}


@pytest.fixture(scope="session")
def df(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "t.db"
    ingest_folder(RAW, db_path=path, verbose=False)
    return analysis.add_derived(db.load_results(path))


# ------------------------------------------------------------- extração
def test_row_counts(extractions):
    assert {y: len(r.rows) for y, r in extractions.items()} == {2022: 56, 2023: 56, 2024: 57, 2026: 61}


def test_edition_columns(extractions):
    assert "bonus_motor" in extractions[2023].tail_columns
    assert "bonus_motor" not in extractions[2024].tail_columns
    assert {"maior_ee", "voos_validos"} <= set(extractions[2026].tail_columns)
    assert "desempate" in extractions[2023].tail_columns and "desempate" not in extractions[2026].tail_columns


def test_megazord_2026_values(extractions):
    r = extractions[2026].rows.set_index("team_key").loc["megazord"]
    assert (r.pos, r.numero) == (14, 13)
    assert r.carga_paga == pytest.approx(8.51)
    assert r.peso_vazio == pytest.approx(2.35)
    assert r.pontos_voo == pytest.approx(108.36)
    assert r.pen_dim_pot == pytest.approx(-16.5)
    assert r.notas_rel_apres == pytest.approx(108.77)
    assert r.total_geral == pytest.approx(277.38)


def test_comma_decimal_2022(extractions):
    r = extractions[2022].rows.iloc[0]
    assert r.team_name == "AXÉ FLY" and r.carga_paga == pytest.approx(12.63) and r.total_geral == pytest.approx(461.99)


def test_overlapping_cells_2023(extractions):
    r = extractions[2023].rows.iloc[1]
    assert r.team_name == "AeroFEG"
    assert r.school.startswith("Faculdade de Engenharia de Guaratinguetá")
    assert r.uf == "SP"


def test_glued_name_school_2024(extractions):
    r = extractions[2024].rows.set_index("pos").loc[30]
    assert r.team_name == "PegAzuls AeroDesign"
    assert r.school.startswith("Universidade Federal Rural do Semi-Árido")


def test_parse_number():
    assert parse_number("1,0995") == pytest.approx(1.0995)
    assert parse_number("1.0995") == pytest.approx(1.0995)
    assert parse_number("-16,50") == pytest.approx(-16.5)
    assert parse_number("999") == 999 and isinstance(parse_number("999"), int)
    assert parse_number("Sim") is True and parse_number("Não") is False


def test_title_detects_class():
    m = TITLE_RE.search("28ª Competição SAE BRASIL de Aerodesign - 2026 - CLASSIFICAÇÃO CLASSE ADVANCED - Final")
    assert m and m.group(3).lower() == "advanced"


# ------------------------------------------------------------- validação
@pytest.mark.parametrize("year", [2022, 2023, 2024, 2026])
def test_total_identity(extractions, year):
    """Total = max(0, bateria + confiab + notas + vídeo + penalidades) em todas as edições."""
    issues = validate(extractions[year])
    assert not [i for i in issues if "Total geral" in i.message]


def test_points_regime(extractions):
    assert detect_points_regime(extractions[2024].rows) == "12.5xCP"
    assert detect_points_regime(extractions[2026].rows) == "50xEE"


# ------------------------------------------------------------- identidade
def test_team_key_normalization():
    assert team_key("AXÉ FLY") == team_key("Axé Fly") == "axe fly"
    assert team_key("MEGAZORD AERODESIGN") == team_key("Megazord AeroDesign") == "megazord"
    assert team_key("UFRGS PAMPA AERODESIGN") == team_key("Pampa AeroDesign")


def test_megazord_history(df):
    h = analysis.team_identity(df, "megazord")
    assert h["year"].tolist() == [2022, 2023, 2024, 2026]
    assert h["pos"].tolist() == [39, 18, 20, 14]


# ------------------------------------------------------------- análise
def test_bench_and_gaps(df):
    b = analysis.bench_criterion(df, 2026, "megazord", "notas_rel_apres")
    top5 = df[df.year == 2026].nsmallest(5, "pos")["notas_rel_apres"]
    assert b.top5_median == pytest.approx(top5.median())
    assert b.gap_top5 == pytest.approx(top5.median() - 108.77)
    assert b.champion == pytest.approx(196.71)


def test_podium_gap(df):
    p = analysis.podium_gap(df, 2026, "megazord")
    assert p["terceiro_total"] == pytest.approx(501.99)
    assert p["pontos_para_podio"] == pytest.approx(501.99 - 277.38 + 0.01)
    assert p["decomposicao"]["Δ vs 3º"].sum() == pytest.approx(501.99 - 277.38, abs=0.05)


def test_simulate_no_change_keeps_position(df):
    s = analysis.simulate(df, 2026, "megazord", {})
    assert s["pos_simulada"] == 14 and s["ganho"] == pytest.approx(0, abs=0.02)


def test_simulate_notes(df):
    s = analysis.simulate(df, 2026, "megazord", {"notas_rel_apres": 108.77 + 100})
    assert s["ganho"] == pytest.approx(100, abs=0.02)
    others = df[(df.year == 2026) & (df.team_key != "megazord")]["total_geral"]
    assert s["pos_simulada"] == int((others > 377.38).sum() + 1)


def test_simulate_unclamps_zeroed_battery(df):
    """2022: penalidade −88,6 zerou a bateria; removê-la recupera a soma real dos componentes."""
    s = analysis.simulate(df, 2022, "megazord", {"pen_dim_pot": 0.0})
    assert s["ganho"] == pytest.approx(-17.38 + 88.60, abs=0.05)


def test_derived_ee(df):
    r = df[(df.year == 2026) & (df.team_key == "megazord")].iloc[0]
    assert r.ee_calc == pytest.approx(8.51 / 2.35)
    assert r.fator_residual == pytest.approx(108.36 / (1.046 * 181.06), rel=1e-4)


# ------------------------------------------------------------- regulamento 2026
def test_formula_inverses():
    for e in (0.0, 0.03, 0.08, 0.12):
        assert rules.pv_error_from_fpv_2026(rules.fpv_2026(e)) == pytest.approx(e, abs=1e-9) or e == 0
        if rules.pac_2026(e) > 0:
            assert rules.cp_error_from_pac_2026(rules.pac_2026(e)) == pytest.approx(e, abs=1e-9)
    assert rules.config_factor_2026(1) == pytest.approx(1.22)
    assert rules.config_factor_2026(2) == pytest.approx(1.00)
    assert rules.config_factor_2026(3) == pytest.approx(1.15)
    assert rules.brc_2026(20) == 20 and rules.brc_2026(20.5) == pytest.approx(20 - 6.324 * math.sqrt(0.5))
    assert rules.bcf_2026(100, 80) == pytest.approx(16.0)
    assert rules.fpr_2026(123.33) == pytest.approx(1.0, abs=1e-3)


def test_regulation_only_where_available():
    assert rules.regulation_for(2026) is not None
    assert rules.regulation_for(2022) is None


# ------------------------------------------------------------- diagnóstico
def test_diagnosis_targets_come_from_other_teams(df):
    for d in diagnosis.diagnose(df, 2026, "megazord"):
        y = df[df.year == 2026]
        observed = set(round(v, 6) for v in y[d.criterio].dropna()) | {round(y.nsmallest(5, "pos")[d.criterio].median(), 6)}
        assert round(d.meta_valor, 6) in observed
        assert d.confianca in {"Alta", "Média", "Baixa"}
        assert d.referencias[0].startswith("AD2026_Pontuacao_Final_Regular.pdf")


def test_no_causal_formula_without_regulation(df):
    d = {x.criterio: x for x in diagnosis.diagnose(df, 2022, "megazord")}
    assert "não disponível" in d["pontos_voo"].interpretacao
    assert "Eq." not in d["pontos_acurac"].interpretacao


def test_priority_matrix(df):
    m = diagnosis.priority_matrix(df, 2026, "megazord")
    assert list(m["prioridade"]) == list(range(1, len(m) + 1))
    assert m["score"].is_monotonic_decreasing
    assert "bonus_motor" not in set(m["critério"])  # critério inexistente na edição vigente
