"""Importa todos os PDFs de resultados de uma pasta para a base SQLite.

Uso:  python scripts/ingest.py [pasta] [--db caminho.db]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aerointel import db  # noqa: E402
from aerointel.ingest import ingest_folder  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    a = ap.parse_args()
    ingest_folder(a.folder, db_path=a.db)
