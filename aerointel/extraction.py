"""Extração dos PDFs oficiais de pontuação final (Classe Regular).

Estrutura real verificada nos PDFs 2022, 2023, 2024 e 2026:
- 1 página, tabela sem linhas de grade (pdfplumber não acha bordas);
- cada célula é desenhada como um *run* de texto contínuo; nomes de escola
  longos transbordam e se SOBREPÕEM às colunas vizinhas — por isso a extração
  por palavras (x/y) embaralha caracteres. A solução é ler os caracteres na
  ordem do fluxo de conteúdo e quebrar runs quando o x salta (>0,6 pt) ou
  volta para trás; cada run é uma célula;
- 2022/2023 usam vírgula decimal; 2024/2026 usam ponto;
- a página de 2026 tem /Rotate 90 (pdfplumber já devolve coordenadas giradas);
- as colunas numéricas variam por edição (ver schema.OPTIONAL_TAIL).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pdfplumber

from . import schema
from .teams import team_key

TITLE_RE = re.compile(
    r"(\d+)\s*[ªº°a]?\s*Competi[çc][ãa]o\s+SAE\s+BRASIL\s+de\s+Aerodesign\s*-\s*(\d{4})\s*-\s*"
    r"CLASSIFICA[ÇC][ÃA]O\s+CLASSE\s+(\w+)", re.I)
NUM_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
TAIL_TOKEN_RE = re.compile(r"^(-?\d+(?:[.,]\d+)?|Sim|N[ãa]o|-|[A-Z]{1,3})$")
GAP_SPLIT = 0.6     # pt — dentro de uma célula o gap entre caracteres é ≤ 0,2 pt
LINE_TOL = 1.2      # pt — runs da mesma linha variam ~0,3 pt no topo


@dataclass
class Issue:
    level: str          # "erro" | "aviso" | "info"
    message: str
    row_index: int | None = None
    field: str | None = None

    def as_dict(self):
        return {"nivel": self.level, "mensagem": self.message,
                "linha": self.row_index, "campo": self.field}


@dataclass
class ExtractionResult:
    source_file: str
    sha256: str
    year: int | None
    edition_no: int | None
    competition_class: str | None
    title: str
    tail_columns: list[str]
    rows: pd.DataFrame
    raw_rows: list[dict]
    issues: list[Issue] = field(default_factory=list)
    pages: int = 1

    @property
    def ok(self) -> bool:
        return not any(i.level == "erro" for i in self.issues)


# ----------------------------------------------------------------------------
# Baixo nível: caracteres → runs → linhas
# ----------------------------------------------------------------------------
def _runs_from_chars(chars: list[dict]) -> list[dict]:
    runs, cur, prev = [], None, None
    for c in chars:
        if prev is None:
            new = True
        else:
            gap = c["x0"] - prev["x1"]
            new = abs(c["top"] - prev["top"]) > 0.6 or gap < -0.5 or gap > GAP_SPLIT
        if new:
            cur = {"chars": []}
            runs.append(cur)
        cur["chars"].append(c)
        prev = c
    out = []
    for i, r in enumerate(runs):
        cs = r["chars"]
        text = "".join(ch["text"] for ch in cs).strip()
        if not text:
            continue
        out.append({
            "text": text, "x0": min(ch["x0"] for ch in cs), "x1": max(ch["x1"] for ch in cs),
            "top": sum(ch["top"] for ch in cs) / len(cs), "size": cs[0].get("size", 0),
            "seq": i, "chars": [ch for ch in cs if ch["text"].strip() or True],
        })
    return out


def _group_lines(runs: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for r in sorted(runs, key=lambda r: (r["top"], r["seq"])):
        if lines and abs(lines[-1][0]["top"] - r["top"]) <= LINE_TOL:
            lines[-1].append(r)
        else:
            lines.append([r])
    return [sorted(line, key=lambda r: r["seq"]) for line in lines]


def _split_merged(run: dict, centers: dict, issues: list, row_index: int) -> list[dict]:
    """Separa um run que juntou Nome + Escola sem espaço (ex.: 2024, linha 30
    'PegAzuls AeroDesignUniversidade Federal...').

    O texto de cada célula é centralizado na sua coluna; escolhe-se o ponto de
    corte (início de palavra em maiúscula) que melhor centraliza cada parte.
    """
    cn, cs_ = centers["team_name"], centers["school"]
    rc0 = (run["x0"] + run["x1"]) / 2
    # Um run legítimo é centralizado na própria coluna (escolas longas transbordam
    # simetricamente). Só tenta separar se cobrir as duas colunas E estiver descentrado.
    if not (run["x0"] < cn < run["x1"] and run["x0"] < cs_ < run["x1"]):
        return [run]
    if min(abs(rc0 - cn), abs(rc0 - cs_)) < 4.0:
        return [run]
    chars = run["chars"]
    best = None
    for k in range(1, len(chars)):
        if not chars[k]["text"].isupper():
            continue
        left, right = chars[:k], chars[k:]
        lc = (left[0]["x0"] + left[-1]["x1"]) / 2
        rc = (right[0]["x0"] + right[-1]["x1"]) / 2
        cost = abs(lc - cn) + abs(rc - cs_)
        if best is None or cost < best[0]:
            best = (cost, k)
    if best is None:
        return [run]
    k = best[1]
    mk = lambda part: {**run, "text": "".join(c["text"] for c in part).strip(),
                       "x0": part[0]["x0"], "x1": part[-1]["x1"], "chars": part}
    left, right = mk(chars[:k]), mk(chars[k:])
    issues.append(Issue("info", f"Células Nome/Escola coladas no PDF; separadas por centralização: "
                                f"'{left['text']}' | '{right['text']}'", row_index, "team_name"))
    return [left, right]


def parse_number(tok: str):
    tok = tok.strip()
    if tok in ("Sim",):
        return True
    if tok in ("Não", "Nao"):
        return False
    if not NUM_RE.match(tok):
        return tok
    if "," in tok:
        tok = tok.replace(".", "").replace(",", ".")
    v = float(tok)
    return int(v) if re.match(r"^-?\d+$", tok) else v


def build_tail_columns(header_text: str) -> list[str]:
    cols = []
    for k in schema.TAIL_BASE:
        if k in schema.OPTIONAL_TAIL:
            if any(kw.lower() in header_text.lower() for kw in schema.OPTIONAL_TAIL[k]):
                cols.append(k)
        else:
            cols.append(k)
    return cols


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


# ----------------------------------------------------------------------------
# Extração principal
# ----------------------------------------------------------------------------
def extract_results_pdf(path: str | Path) -> ExtractionResult:
    path = Path(path)
    issues: list[Issue] = []
    all_rows, raw_rows = [], []
    title, year, edition_no, klass = "", None, None, None
    tail_cols: list[str] = []

    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for page_no, page in enumerate(pdf.pages, start=1):
            runs = _runs_from_chars(page.chars)
            lines = _group_lines(runs)

            # título / edição / classe
            for line in lines[:6]:
                txt = " ".join(r["text"] for r in line)
                m = TITLE_RE.search(txt)
                if m:
                    title = txt.strip()
                    edition_no, year, klass = int(m.group(1)), int(m.group(2)), m.group(3).title()
                    break

            # cabeçalho: âncoras de coluna
            header_runs = []
            first_data_idx = None
            for li, line in enumerate(lines):
                if (len(line) >= 15 and NUM_RE.match(line[0]["text"])
                        and sum(1 for r in line if TAIL_TOKEN_RE.match(r["text"])) >= 15):
                    first_data_idx = li
                    break
                header_runs.extend(line)
            if first_data_idx is None:
                issues.append(Issue("erro", f"Página {page_no}: nenhuma linha de dados reconhecida."))
                continue
            header_text = " ".join(r["text"] for r in header_runs)
            if not tail_cols:
                tail_cols = build_tail_columns(header_text)

            def hcenter(word):
                ws = [r for r in header_runs if r["text"].lower().startswith(word.lower())]
                return (ws[0]["x0"] + ws[0]["x1"]) / 2 if ws else None

            centers = {"team_name": hcenter("Nome"), "school": hcenter("Escola"), "uf": hcenter("UF")}
            if None in centers.values():
                issues.append(Issue("erro", "Cabeçalho sem 'Nome', 'Escola' ou 'UF' — formato desconhecido."))
                continue

            n_tail = len(tail_cols)
            for line in lines[first_data_idx:]:
                texts = [r["text"] for r in line]
                if len(line) < n_tail + 3 or not NUM_RE.match(texts[0]):
                    if any(t.strip() for t in texts):
                        raw_rows.append({"page": page_no, "ignored": True, "cells": texts})
                    continue
                row_index = len(all_rows)
                pos, numero = parse_number(texts[0]), parse_number(texts[1])
                tail_runs = line[-n_tail:]
                text_runs = line[2:-n_tail]
                rec = {"pos": pos, "numero": numero, "page": page_no, "row_index": row_index,
                       "team_name": "", "school": "", "uf": ""}
                # células de texto → coluna de cabeçalho mais próxima (texto é centralizado)
                buckets = {"team_name": [], "school": [], "uf": []}
                text_runs = [piece for r in text_runs for piece in _split_merged(r, centers, issues, row_index)]
                for r in text_runs:
                    xc = (r["x0"] + r["x1"]) / 2
                    col = min(centers, key=lambda k: abs(centers[k] - xc))
                    buckets[col].append(r["text"])
                # UF: só aceita token curto; senão devolve ao campo escola
                uf = " ".join(buckets["uf"]).strip()
                if len(uf) > 12:
                    buckets["school"].append(uf)
                    uf = ""
                rec["team_name"] = " ".join(buckets["team_name"]).strip()
                school_raw = " ".join(buckets["school"]).strip()
                rec["school_raw"] = school_raw
                rec["school"] = re.sub(r"\s+", " ", school_raw.replace('"', "")).strip()
                rec["team_name"] = re.sub(r"\s+", " ", rec["team_name"])
                rec["uf"] = uf
                bad = [r["text"] for r in tail_runs if not TAIL_TOKEN_RE.match(r["text"])]
                if bad:
                    issues.append(Issue("erro", f"Tokens inesperados na parte numérica: {bad}", row_index))
                for col, r in zip(tail_cols, tail_runs):
                    rec[col] = parse_number(r["text"])
                if not rec["team_name"]:
                    issues.append(Issue("aviso", "Nome da equipe vazio.", row_index, "team_name"))
                all_rows.append(rec)
                raw_rows.append({"page": page_no, "row_index": row_index, "cells": texts})

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df.insert(0, "year", year)
        df["team_key"] = df["team_name"].map(team_key)
        df["source_file"] = path.name
        if "desempate" in df:
            df["desempate"] = df["desempate"].astype(str)
    if klass and klass.lower() != "regular":
        issues.append(Issue("erro", f"Documento da classe '{klass}'. O sistema aceita só a Classe Regular."))
    if year is None:
        issues.append(Issue("erro", "Edição (ano) não identificada no título."))

    return ExtractionResult(
        source_file=path.name, sha256=sha256_of(path), year=year, edition_no=edition_no,
        competition_class=klass, title=title, tail_columns=tail_cols, rows=df,
        raw_rows=raw_rows, issues=issues, pages=n_pages,
    )
