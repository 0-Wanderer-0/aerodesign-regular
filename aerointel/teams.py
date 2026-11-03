"""Identidade de equipes entre edições.

Os nomes variam de grafia entre PDFs ("AXÉ FLY" × "Axé Fly", "UFRGS PAMPA
AERODESIGN" × "Pampa AeroDesign"). A chave canônica remove acentos, caixa,
pontuação e palavras genéricas. Casos que a normalização não resolve vão para
a tabela de apelidos (editável na página 06) — nunca são fundidos às cegas.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

GENERIC_WORDS = {"aerodesign", "aero", "design", "equipe", "regular", "team", "de", "do", "da"}

# Apelidos verificados manualmente nos PDFs (grafias diferentes da mesma equipe).
DEFAULT_ALIASES = {
    "ufrgs pampa": "pampa",
    "aerocauria pucpr": "aerocaria pucpr",
    "aracua": "aracua",
    "avoante aeromec": "avoante aeromec",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def team_key(name: str) -> str:
    s = strip_accents(str(name or "")).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in GENERIC_WORDS]
    key = " ".join(words) or s.strip()
    return DEFAULT_ALIASES.get(key, key)


def suggest_matches(name: str, known_keys: list[str], n: int = 5, cutoff: float = 0.55) -> list[str]:
    """Sugere chaves parecidas (para busca e para o painel de apelidos)."""
    k = team_key(name)
    hits = [x for x in known_keys if k and (k in x or x in k)]
    hits += [x for x in difflib.get_close_matches(k, known_keys, n=n, cutoff=cutoff) if x not in hits]
    return hits[:n]
