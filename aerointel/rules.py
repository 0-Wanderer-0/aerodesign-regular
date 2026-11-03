"""Regras de pontuação por edição (fonte: regulamentos oficiais).

Só o regulamento 2026 (Rev. 01) está disponível no projeto. As fórmulas de
2022–2024 NÃO são presumidas: para essas edições o sistema usa apenas valores
observados e tetos observados. Quando o regulamento de outra edição for
adicionado, registre-o em REGULATIONS com as referências de página.

Todas as referências abaixo vêm de `Base_Normativa_Regular_2026.md`, que cita
§, equação e página do PDF do regulamento.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

REG_2026_FILE = "Regulamento_SAE_BRASIL_AeroDesign_2026_Rev01_PT.pdf"


@dataclass(frozen=True)
class Ref:
    doc: str
    section: str
    page: str

    def __str__(self):
        return f"{self.doc}, {self.section}, p. {self.page}"


R26 = lambda sec, pg: Ref(REG_2026_FILE, sec, pg)  # noqa: E731

REGULATIONS = {
    2026: {
        "file": REG_2026_FILE,
        "revision": "Rev. 01 (01/03/2026)",
        "total": ("Total = Projeto + Voo + Bônus − Penalidades", R26("§10.5, Eq. 10.1", "108–109")),
        # Máximos regulamentares (só onde o regulamento fixa um teto)
        "max": {
            "notas_rel_apres": (225.0, R26("§11.1 (185 relatórios + 40 apresentação)", "110–111")),
            "pontos_acurac": (30.0, R26("§7.7.5, Eq. 7.6", "58–59")),
            "bonus_tempo_carga": (20.0, R26("§7.7.7, Eq. 7.8", "59")),
            "pontos_confiab": (20.0, R26("§7.7.8, Eq. 7.9", "60")),
            "total_video": (30.0, R26("§6.23", "45–48")),
            "pen_dim_pot": (0.0, R26("NC[7.2.0.1]", "50")),
            "pen_validacao": (0.0, R26("§10.1.10", "100–102")),
            "pen_competicao": (0.0, R26("Apêndice 6", "139–143")),
        },
        "refs": {
            "pontos_voo": R26("§7.7.4, Eq. 7.5 (P_VOO = FPV·FPR·P_EE·f(N)·1,15^-b)", "58"),
            "pontos_carga_ee": R26("§7.7.1, Eq. 7.2 (P_EE = 50·EE)", "57"),
            "fpv": R26("§7.7.2, Eq. 7.3", "57"),
            "pontos_acurac": R26("§7.7.5, Eq. 7.6", "58–59"),
            "bonus_pouso": R26("§7.7.6, Eq. 7.7 (B_PO = 2·EE)", "59"),
            "bonus_tempo_carga": R26("§7.7.7, Eq. 7.8", "59"),
            "pontos_confiab": R26("§7.7.8, Eq. 7.9", "60"),
            "pen_dim_pot": R26("NC[7.2.0.1] (PD = 100·ΔSd; PP = 0,5·ΔSp)", "50"),
            "pen_validacao": R26("§10.1.10 (componentes não primários −20; rodas −20/−30)", "100–102"),
            "notas_rel_apres": R26("§11.1 e Eq. 7.4 (FPR)", "58, 110–111"),
            "total_video": R26("§6.23", "45–48"),
            "pen_competicao": R26("Apêndice 6", "139–143"),
            "classificacao_baterias": R26("Tabela 10.1", "105"),
            "desempate": R26("§4.8.4 / Tab. 4.2 (≤1,0 pt → maior EE)", "13–16"),
        },
    },
}


def regulation_for(year: int) -> dict | None:
    return REGULATIONS.get(year)


# ---------------------------------------------------------------------------
# Fórmulas 2026 e inversas (usadas para INFERIR causas — sempre rotuladas como
# derivadas; nunca substituem o dado oficial)
# ---------------------------------------------------------------------------
def fpv_2026(err_frac: float) -> float:
    return max(0.80, 1.10 - 15 * err_frac ** 2)


def pv_error_from_fpv_2026(fpv: float) -> float | None:
    """|erro relativo de previsão de PV|. None se FPV no piso (erro ≥ 14,1% ou PV não lançado)."""
    if fpv is None or fpv <= 0.8001:
        return None
    return math.sqrt(max(0.0, (1.10 - fpv) / 15))


def pac_2026(err_frac: float) -> float:
    return max(0.0, 30 - 830 * abs(err_frac) ** 1.75)


def cp_error_from_pac_2026(pac: float) -> float | None:
    if pac is None or pac <= 0:
        return None
    return ((30 - pac) / 830) ** (1 / 1.75)


def brc_2026(t: float) -> float:
    return 20.0 if t <= 20 else max(0.0, 20 - 6.324 * math.sqrt(t - 20))


def bcf_2026(p1: float, p2: float) -> float:
    if not p1:
        return 0.0
    return max(0.0, 20 * (1 - 5 * ((p1 - p2) / p1) ** 2))


def fpr_2026(nr: float) -> float:
    return min(1.0, 0.5 + 0.75 * nr / 185)


def config_factor_2026(n: int) -> float:
    n = min(int(n), 3)
    return 0.185 * n ** 2 - 0.775 * n + 1.81


def span_factor_2026(b: float) -> float:
    return 1.15 ** (-b)


def penalty_dim_pot_hypotheses_2026(pen: float) -> list[str]:
    """Explica uma penalidade dimensional/potência observada (valor negativo)."""
    p = abs(pen or 0)
    if p < 0.01:
        return []
    out = [f"Potência: excesso de ≈{p / 0.5:.0f} W acima de 600 W (PP = 0,5·ΔSp)"]
    if p <= 5.0:
        out.append(f"Envergadura: excesso de ≈{p:.1f} cm acima de 4,0 m (PD = 100·ΔSd, sem o adicional de 20)")
    elif p >= 25.0:
        out.append(f"Envergadura: excesso de ≈{p - 20:.1f} cm (>5 cm, inclui adicional de 20 pts)")
    return out
