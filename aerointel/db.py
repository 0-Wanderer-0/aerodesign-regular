"""Base histórica em SQLite.

Tabelas
- documents       : um registro por PDF importado (hash, edição, classe, status)
- results_raw     : células brutas de cada linha, exatamente como lidas do PDF
- results         : linha estruturada (valores originais — nunca sobrescritos)
- corrections     : correções manuais auditáveis (campo, valor antigo/novo, motivo)
- aliases         : unificação manual de grafias de equipes
- processing_log  : histórico de processamento e validação

`load_results()` devolve a visão com correções aplicadas e marca as células corrigidas.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import schema
from .extraction import ExtractionResult, Issue

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "aerointel.db"

RESULT_COLS = ["year", "pos", "numero", "team_name", "team_key", "school", "school_raw", "uf",
               "source_file", "page", "row_index"] + [k for k in schema.FIELDS]

DDL = f"""
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY, filename TEXT, sha256 TEXT UNIQUE, kind TEXT,
    year INTEGER, edition_no INTEGER, class TEXT, title TEXT, pages INTEGER,
    tail_columns TEXT, points_regime TEXT, status TEXT, imported_at TEXT
);
CREATE TABLE IF NOT EXISTS results_raw (
    id INTEGER PRIMARY KEY, doc_id INTEGER, page INTEGER, row_index INTEGER, cells TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY, doc_id INTEGER,
    {", ".join(f"{c} {'TEXT' if c in ('team_name','team_key','school','school_raw','uf','source_file','desempate','pouso_100m') else 'REAL'}" for c in RESULT_COLS)}
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY, result_id INTEGER, field TEXT, old_value TEXT, new_value TEXT,
    reason TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS aliases (alias_key TEXT PRIMARY KEY, team_key TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY, doc_id INTEGER, ts TEXT, level TEXT, message TEXT, row_index INTEGER, field TEXT
);
CREATE TABLE IF NOT EXISTS regulations (
    id INTEGER PRIMARY KEY, filename TEXT, sha256 TEXT UNIQUE, year INTEGER, revision TEXT, imported_at TEXT
);
"""


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(DDL)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def document_exists(sha256: str, db_path=DEFAULT_DB) -> dict | None:
    with connect(db_path) as con:
        row = con.execute("SELECT id, filename, year, status FROM documents WHERE sha256=?", (sha256,)).fetchone()
    return dict(zip(["id", "filename", "year", "status"], row)) if row else None


def store_extraction(res: ExtractionResult, issues: list[Issue], regime: str,
                     db_path=DEFAULT_DB, replace_year: bool = True) -> int:
    """Incorpora uma extração validada. Se já existir documento da mesma edição,
    ele é substituído (ex.: rev01 substitui rev00) e isso fica registrado no log."""
    with connect(db_path) as con:
        cur = con.cursor()
        if replace_year and res.year is not None:
            old = cur.execute("SELECT id, filename FROM documents WHERE year=? AND kind='resultado'",
                              (res.year,)).fetchall()
            for oid, ofn in old:
                cur.execute("DELETE FROM results WHERE doc_id=?", (oid,))
                cur.execute("DELETE FROM results_raw WHERE doc_id=?", (oid,))
                cur.execute("UPDATE documents SET status='substituído' WHERE id=?", (oid,))
                cur.execute("INSERT INTO processing_log(doc_id, ts, level, message) VALUES (?,?,?,?)",
                            (oid, _now(), "info", f"Substituído por {res.source_file}"))
            cur.execute("DELETE FROM documents WHERE sha256=?", (res.sha256,))
        cur.execute(
            "INSERT INTO documents(filename, sha256, kind, year, edition_no, class, title, pages, "
            "tail_columns, points_regime, status, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (res.source_file, res.sha256, "resultado", res.year, res.edition_no, res.competition_class,
             res.title, res.pages, json.dumps(res.tail_columns), regime, "validado", _now()))
        doc_id = cur.lastrowid
        for raw in res.raw_rows:
            cur.execute("INSERT INTO results_raw(doc_id, page, row_index, cells) VALUES (?,?,?,?)",
                        (doc_id, raw.get("page"), raw.get("row_index"), json.dumps(raw["cells"], ensure_ascii=False)))
        df = res.rows.copy()
        for c in RESULT_COLS:
            if c not in df:
                df[c] = None
        if "pouso_100m" in df:
            df["pouso_100m"] = df["pouso_100m"].map(lambda v: None if v is None else ("Sim" if v is True else ("Não" if v is False else str(v))))
        df = df[RESULT_COLS].astype(object).where(pd.notna(df[RESULT_COLS]), None)
        placeholders = ",".join("?" * (len(RESULT_COLS) + 1))
        cur.executemany(f"INSERT INTO results(doc_id, {', '.join(RESULT_COLS)}) VALUES ({placeholders})",
                        [(doc_id, *row) for row in df.itertuples(index=False, name=None)])
        for i in issues:
            cur.execute("INSERT INTO processing_log(doc_id, ts, level, message, row_index, field) VALUES (?,?,?,?,?,?)",
                        (doc_id, _now(), i.level, i.message, i.row_index, i.field))
    return doc_id


def add_correction(result_id: int, field: str, new_value, reason: str, db_path=DEFAULT_DB):
    if field not in RESULT_COLS:
        raise ValueError(f"Campo desconhecido: {field}")
    with connect(db_path) as con:
        old = con.execute(f"SELECT {field} FROM results WHERE id=?", (result_id,)).fetchone()
        if old is None:
            raise ValueError("Linha inexistente")
        con.execute("INSERT INTO corrections(result_id, field, old_value, new_value, reason, created_at) "
                    "VALUES (?,?,?,?,?,?)", (result_id, field, str(old[0]), str(new_value), reason, _now()))


def add_alias(alias_key: str, team_key: str, note: str = "", db_path=DEFAULT_DB):
    with connect(db_path) as con:
        con.execute("INSERT OR REPLACE INTO aliases(alias_key, team_key, note) VALUES (?,?,?)",
                    (alias_key, team_key, note))


def remove_alias(alias_key: str, db_path=DEFAULT_DB):
    with connect(db_path) as con:
        con.execute("DELETE FROM aliases WHERE alias_key=?", (alias_key,))


def read_table(name: str, db_path=DEFAULT_DB) -> pd.DataFrame:
    with connect(db_path) as con:
        return pd.read_sql_query(f"SELECT * FROM {name}", con)


def load_results(db_path=DEFAULT_DB) -> pd.DataFrame:
    """Resultados com correções manuais e apelidos aplicados.

    Colunas extras: `corrected_fields` (lista de campos corrigidos na linha) e
    `original_team_key`.
    """
    with connect(db_path) as con:
        df = pd.read_sql_query("SELECT * FROM results", con)
        corr = pd.read_sql_query("SELECT * FROM corrections ORDER BY id", con)
        aliases = dict(con.execute("SELECT alias_key, team_key FROM aliases").fetchall())
    if df.empty:
        return df
    df["corrected_fields"] = [[] for _ in range(len(df))]
    idx = {rid: i for i, rid in enumerate(df["id"])}
    for _, c in corr.iterrows():
        i = idx.get(c["result_id"])
        if i is None:
            continue
        val = c["new_value"]
        if c["field"] not in ("team_name", "team_key", "school", "uf", "desempate", "pouso_100m"):
            try:
                val = float(val)
            except ValueError:
                pass
        df.at[df.index[i], c["field"]] = val
        df.at[df.index[i], "corrected_fields"] = df.at[df.index[i], "corrected_fields"] + [c["field"]]
    df["original_team_key"] = df["team_key"]
    df["team_key"] = df["team_key"].map(lambda k: aliases.get(k, k))
    for c in schema.FIELDS:
        if c in df and schema.FIELDS[c].dtype in ("float", "int"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["year"] = df["year"].astype(int)
    df["pos"] = pd.to_numeric(df["pos"]).astype(int)
    return df.sort_values(["year", "pos", "row_index"]).reset_index(drop=True)
