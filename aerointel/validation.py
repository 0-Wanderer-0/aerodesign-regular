"""Validação dos dados extraídos ANTES de entrar na base oficial.

Regras verificadas a partir dos próprios PDFs (não presumidas):
- Total Geral = max(0, Melhor bateria + Confiabilidade + Notas + Vídeo + Penalidades)
  (confere em 2022, 2023, 2024 e 2026 com erro de arredondamento ≤ 0,02).
- Melhor bateria ≈ Voo + Acurácia + Pouso + Tempo carga (+ Motor) + Penalidades da bateria
  (diferenças pequenas existem em 2026 e são registradas como inconsistência, não corrigidas).
- 'Pontos carga/EE' = 12,5 × CP (2022–2024) ou 50 × CP/PV (2026) — o regime é
  detectado aritmeticamente e registrado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import schema
from .extraction import ExtractionResult, Issue

TOL_TOTAL = 0.06
TOL_BATTERY = 0.5


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(0.0, index=df.index)


def detect_points_regime(df: pd.DataFrame) -> str:
    d = df[(_num(df, "carga_paga") > 0) & (_num(df, "peso_vazio") > 0)]
    if d.empty:
        return "indeterminado"
    cp, pv, p = _num(d, "carga_paga"), _num(d, "peso_vazio"), _num(d, "pontos_carga_ee")
    err_cp = (p - 12.5 * cp).abs().median()
    err_ee = (p - 50 * cp / pv).abs().median()
    if min(err_cp, err_ee) > 1.0:
        return "indeterminado"
    return "12.5xCP" if err_cp < err_ee else "50xEE"


def validate(res: ExtractionResult) -> list[Issue]:
    df = res.rows
    issues: list[Issue] = []
    if df.empty:
        return [Issue("erro", "Nenhuma linha extraída.")]

    # 1. total geral
    comp = sum(_num(df, c).fillna(0) for c in schema.TOTAL_COMPONENTS)
    expected = np.maximum(comp, 0)
    diff = (_num(df, "total_geral") - expected).abs()
    for i in df.index[diff > TOL_TOTAL]:
        issues.append(Issue("aviso", f"Total geral {df.at[i,'total_geral']} ≠ soma dos blocos "
                                     f"{expected[i]:.2f} (Δ={diff[i]:.2f}).", int(df.at[i, 'row_index']), "total_geral"))

    # 2. bateria
    bat = sum(_num(df, c).fillna(0) for c in schema.BATTERY_COMPONENTS if c in df)
    tb = _num(df, "total_melhor_bateria")
    mask = tb > 0
    bdiff = (tb - bat).abs()
    for i in df.index[mask & (bdiff > TOL_BATTERY)]:
        issues.append(Issue("info", f"Melhor bateria {tb[i]:.2f} ≠ soma dos componentes {bat[i]:.2f} "
                                    f"(Δ={bdiff[i]:.2f}). Mantido o valor oficial.",
                            int(df.at[i, 'row_index']), "total_melhor_bateria"))
    clamp = (tb == 0) & (bat < 0)
    for i in df.index[clamp]:
        issues.append(Issue("info", f"Bateria zerada: componentes somam {bat[i]:.2f} (penalidades > pontos).",
                            int(df.at[i, 'row_index']), "total_melhor_bateria"))

    # 3. ordenação / posições
    pos = _num(df, "pos")
    if not pos.is_monotonic_increasing:
        issues.append(Issue("aviso", "Posições não estão em ordem crescente."))
    tot = _num(df, "total_geral")
    order_bad = (tot.diff() > 0.011) & (pos.diff() > 0)
    for i in df.index[order_bad]:
        issues.append(Issue("aviso", "Total maior que o da posição anterior (verificar desempate).",
                            int(df.at[i, 'row_index']), "pos"))
    dups = df[pos.duplicated(keep=False)]
    if not dups.empty:
        issues.append(Issue("info", f"Posições empatadas: {sorted(set(dups['pos'].tolist()))}."))

    # 4. nomes duplicados
    dk = df[df["team_key"].duplicated(keep=False)]
    for k in sorted(set(dk["team_key"])):
        issues.append(Issue("aviso", f"Chave de equipe repetida na mesma edição: '{k}'."))

    # 5. regime de pontos de carga
    regime = detect_points_regime(df)
    issues.append(Issue("info", f"Coluna 'Pontos carga/EE' segue o regime {regime}."))
    return issues
