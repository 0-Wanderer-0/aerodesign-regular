"""Pipeline: PDF → extração → validação → (aprovação) → base histórica."""
from __future__ import annotations

from pathlib import Path

from . import db
from .extraction import ExtractionResult, Issue, extract_results_pdf
from .validation import detect_points_regime, validate


def stage(path: str | Path) -> tuple[ExtractionResult, list[Issue], str]:
    """Extrai e valida sem gravar (área de validação)."""
    res = extract_results_pdf(path)
    issues = res.issues + validate(res)
    regime = detect_points_regime(res.rows) if not res.rows.empty else "indeterminado"
    return res, issues, regime


def commit(res: ExtractionResult, issues: list[Issue], regime: str, db_path=db.DEFAULT_DB) -> int:
    if any(i.level == "erro" for i in issues):
        raise ValueError("Extração com erros — corrija antes de incorporar.")
    return db.store_extraction(res, issues, regime, db_path=db_path)


def ingest_folder(folder: str | Path, db_path=db.DEFAULT_DB, verbose: bool = True) -> list[dict]:
    out = []
    for pdf in sorted(Path(folder).glob("*.pdf")):
        res, issues, regime = stage(pdf)
        errors = [i for i in issues if i.level == "erro"]
        status = "rejeitado" if errors else "incorporado"
        if not errors:
            commit(res, issues, regime, db_path=db_path)
        out.append({"arquivo": pdf.name, "ano": res.year, "classe": res.competition_class,
                    "linhas": len(res.rows), "status": status, "erros": len(errors),
                    "avisos": sum(i.level == "aviso" for i in issues), "regime": regime})
        if verbose:
            print(f"{pdf.name}: {status} — {len(res.rows)} equipes, ano {res.year}, regime {regime}")
            for e in errors:
                print("   ERRO:", e.message)
    return out
