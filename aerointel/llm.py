"""Síntese interpretativa opcional via API da Anthropic.

Só é usada se a variável de ambiente ANTHROPIC_API_KEY existir e o pacote
`anthropic` estiver instalado. O modelo recebe SOMENTE as evidências
estruturadas do diagnóstico e é instruído a não inventar dados. Sem chave, o
relatório usa apenas o motor determinístico (diagnosis.py).
"""
from __future__ import annotations

import json
import os

MODEL = os.environ.get("AEROINTEL_MODEL", "claude-sonnet-5-5")

SYSTEM = (
    "Você é engenheiro aeronáutico sênior avaliando resultados da SAE BRASIL AeroDesign, Classe Regular. "
    "Use EXCLUSIVAMENTE os dados do JSON fornecido. Não invente notas, causas ou fórmulas. "
    "Diferencie dados observados, grandezas derivadas e hipóteses. Não confunda correlação com causa. "
    "Quando a causa não puder ser determinada pelos resultados, diga isso explicitamente. "
    "Escreva em português do Brasil, em tom técnico e crítico, com no máximo 350 palavras, "
    "citando os critérios e valores do JSON."
)


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def narrative(evidence: dict) -> str:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL, max_tokens=1200, system=SYSTEM,
        messages=[{"role": "user", "content": "Evidências:\n```json\n" + json.dumps(evidence, ensure_ascii=False, default=str)
                   + "\n```\nProduza a síntese: (1) principais perdas, (2) o que limita a classificação, "
                     "(3) três prioridades com metas numéricas tiradas do JSON."}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
