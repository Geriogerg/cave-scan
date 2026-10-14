"""Accords de texte partagés par les écrans et les messages des services (T4-D14)."""

from __future__ import annotations


def accord(nombre: int, singulier: str, pluriel: str) -> str:
    """« 1 bouteille », « 3 bouteilles » : jamais « bouteille(s) ». Zéro s'accorde
    au singulier."""
    return f"{nombre} {pluriel if nombre > 1 else singulier}"
