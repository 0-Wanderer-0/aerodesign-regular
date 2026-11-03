"""Formatação numérica pt-BR."""
import math


def num(x, nd=2, signed=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    s = f"{x:+,.{nd}f}" if signed else f"{x:,.{nd}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, nd=1, signed=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return num(100 * x, nd, signed) + "%"
