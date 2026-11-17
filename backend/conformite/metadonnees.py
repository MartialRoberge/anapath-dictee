"""Garde-fou « aucune donnee medicale » : seules des metadonnees techniques sont acceptees.

Une valeur est admise si c'est un booleen, un entier borne, ou une chaine courte SANS espace composee de
[A-Za-z0-9_.:+/-] (identifiant, enum, version, empreinte hexadecimale). Tout le reste est rejete.
"""
from __future__ import annotations

import re
from typing import Any

IDENT = re.compile(r"^[A-Za-z0-9_.:+/-]{1,80}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_INT = 10**9


class MetadonneeInvalide(ValueError):
    pass


def valider_valeur(v: Any, chemin: str = "") -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        if abs(v) > MAX_INT:
            raise MetadonneeInvalide(f"{chemin}: entier hors bornes")
        return v
    if isinstance(v, str):
        if v != "" and not IDENT.fullmatch(v):
            raise MetadonneeInvalide(f"{chemin}: chaîne non conforme (texte libre refusé)")
        return v
    if isinstance(v, (list, tuple)):
        if len(v) > 50:
            raise MetadonneeInvalide(f"{chemin}: liste trop longue")
        return [valider_valeur(x, chemin) for x in v]
    if isinstance(v, dict):
        return valider_payload(v, chemin)
    raise MetadonneeInvalide(f"{chemin}: type non autorisé")


def valider_payload(d: dict[str, Any], chemin: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        if not isinstance(k, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", k):
            raise MetadonneeInvalide(f"{chemin}: clé non conforme")
        out[k] = valider_valeur(v, f"{chemin}.{k}")
    return out
