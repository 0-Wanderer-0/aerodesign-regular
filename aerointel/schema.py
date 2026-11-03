"""Esquema canônico dos resultados da Classe Regular.

Cada coluna do PDF oficial é mapeada para um nome canônico. As colunas mudam
entre edições (ex.: 'Bonus Motor Elétrico' só existe em 2023; 'Maior EE' e
'Voos Válidos' só em 2026), por isso a ordem de colunas de cada edição é
montada dinamicamente em `extraction.build_tail_columns` e validada.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str              # "score" (entra na pontuação), "indicator" (não entra), "meta"
    group: str             # bloco do dashboard
    higher_is_better: bool = True
    dtype: str = "float"   # float | int | bool | str
    note: str = ""


# Campos de pontuação e indicadores, na ordem em que aparecem no PDF.
FIELDS: dict[str, Field] = {f.key: f for f in [
    Field("carga_paga", "Carga paga total (kg)", "indicator", "Desempenho de voo"),
    Field("peso_vazio", "Peso vazio (kg)", "indicator", "Desempenho de voo", higher_is_better=False),
    Field("alt_dens", "Altitude-densidade (m)", "indicator", "Condição de voo", dtype="int",
          note="Condição ambiental; não é mérito da equipe."),
    Field("fpv", "FPV (fator previsão de peso vazio)", "indicator", "Previsão e acurácia"),
    Field("pontos_carga_ee", "Pontos de carga / EE", "indicator", "Desempenho de voo",
          note="2022–2024: 12,5×CP; 2026: 50×EE (detectado aritmeticamente). Não comparar entre esses regimes."),
    Field("pontos_acurac", "Pontos de acuracidade de carga", "score", "Previsão e acurácia"),
    Field("pontos_voo", "Pontos de voo", "score", "Desempenho de voo"),
    Field("pouso_100m", "Pouso < 100 m", "indicator", "Operação de pista", dtype="bool"),
    Field("bonus_pouso", "Bônus de pouso", "score", "Operação de pista"),
    Field("tempo_carga", "Tempo de retirada da carga (s)", "indicator", "Operação de pista",
          higher_is_better=False, note="999 = sem registro."),
    Field("bonus_tempo_carga", "Bônus tempo de carga", "score", "Operação de pista"),
    Field("bonus_motor", "Bônus motor elétrico", "score", "Operação de pista",
          note="Só existe na edição 2023."),
    Field("pen_dim_pot", "Penalidade dimensional e potência", "score", "Penalidades e conformidade"),
    Field("pen_validacao", "Penalidade de validação", "score", "Penalidades e conformidade"),
    Field("bateria_melhor", "Nº da melhor bateria", "indicator", "Confiabilidade", dtype="int"),
    Field("bateria_segunda", "Nº da 2ª melhor bateria", "indicator", "Confiabilidade", dtype="int"),
    Field("maior_ee", "Maior EE", "indicator", "Desempenho de voo", note="Só 2026."),
    Field("voos_validos", "Voos válidos", "indicator", "Confiabilidade", dtype="int", note="Só 2026."),
    Field("total_melhor_bateria", "Total da melhor bateria", "score", "Competição de voo"),
    Field("total_2a_bateria", "Total da 2ª melhor bateria", "indicator", "Confiabilidade"),
    Field("pontos_confiab", "Pontos de confiabilidade", "score", "Confiabilidade"),
    Field("notas_rel_apres", "Notas de relatório + apresentação", "score", "Competição de projeto"),
    Field("total_video", "Vídeo", "score", "Vídeo"),
    Field("pen_competicao", "Penalidades da competição", "score", "Penalidades e conformidade"),
    Field("total_geral", "Total geral", "score", "Total"),
    Field("desempate", "Desempate", "meta", "Total", dtype="str"),
]}

# Ordem-base das colunas numéricas (cauda da linha) — as opcionais entram
# conforme o cabeçalho da edição.
TAIL_BASE = [
    "carga_paga", "peso_vazio", "alt_dens", "fpv", "pontos_carga_ee", "pontos_acurac",
    "pontos_voo", "pouso_100m", "bonus_pouso", "tempo_carga", "bonus_tempo_carga",
    "bonus_motor",          # opcional
    "pen_dim_pot", "pen_validacao", "bateria_melhor", "bateria_segunda",
    "maior_ee", "voos_validos",  # opcionais
    "total_melhor_bateria", "total_2a_bateria", "pontos_confiab", "notas_rel_apres",
    "total_video", "pen_competicao", "total_geral",
    "desempate",            # opcional
]
OPTIONAL_TAIL = {
    "bonus_motor": ("Motor",),
    "maior_ee": ("Maior",),
    "voos_validos": ("Voos", "Validos", "Válidos"),
    "desempate": ("Desemp",),
}

# Blocos que somam o Total Geral (Total = bateria + confiab + notas + vídeo + penalidades).
TOTAL_COMPONENTS = ["total_melhor_bateria", "pontos_confiab", "notas_rel_apres",
                    "total_video", "pen_competicao"]

# Componentes da melhor bateria.
BATTERY_COMPONENTS = ["pontos_voo", "pontos_acurac", "bonus_pouso", "bonus_tempo_carga",
                      "bonus_motor", "pen_dim_pot", "pen_validacao"]

# Critérios exibidos como blocos no dashboard (todos são pontuação observada).
DASHBOARD_CRITERIA = [
    "notas_rel_apres", "pontos_voo", "pontos_acurac", "bonus_pouso",
    "bonus_tempo_carga", "bonus_motor", "pontos_confiab", "total_video",
    "pen_dim_pot", "pen_validacao", "pen_competicao", "total_melhor_bateria",
]

PENALTY_FIELDS = {"pen_dim_pot", "pen_validacao", "pen_competicao"}

# Indicadores derivados (calculados aqui, não constam do PDF).
DERIVED = {
    "ee_calc": "EE calculada = CP / PV  [derivado]",
    "fator_residual": "P_voo / (FPV × pontos carga/EE)  [derivado]",
    "queda_2a_bateria": "Queda da 2ª bateria = 1 − T2/T1  [derivado]",
}

# Colunas de metadados de cada linha
META_COLUMNS = ["year", "pos", "numero", "team_name", "school", "uf", "team_key",
                "source_file", "page", "row_index"]


def label(key: str) -> str:
    if key in FIELDS:
        return FIELDS[key].label
    return DERIVED.get(key, key)
