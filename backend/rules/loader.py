"""Chargement des regles metier YAML en objets OrganRules typed.

Les fichiers ``rules/data/*.yaml`` sont parses une fois au demarrage et
caches en memoire. ``get_rules(organe)`` retourne le ruleset associe ou
le ruleset ``generic`` si l'organe n'est pas connu.

Convention : une fonction = une action. Zero logique metier dans ce
module, uniquement de la lecture de fichiers et de la conversion en
Pydantic.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from schemas import ChampObligatoire, Organe, OrganRules, SousTypeRules


RULES_DATA_DIR: Path = Path(__file__).resolve().parent / "data"


_CACHE: dict[Organe, OrganRules] = {}
_GENERIC_FALLBACK: OrganRules | None = None


# ---------------------------------------------------------------------------
# Conversion YAML brut -> objets typed
# ---------------------------------------------------------------------------


def _parse_champ(raw: dict[str, object]) -> ChampObligatoire:
    """Convertit une entree ``champs_obligatoires`` YAML en ChampObligatoire."""
    return ChampObligatoire(
        nom=cast(str, raw.get("nom", "")),
        section=cast(
            "ChampObligatoire.model_fields['section'].annotation",  # type: ignore[valid-type]
            raw.get("section", "microscopie"),
        ),
        conditions=cast(list[str], raw.get("conditions", []) or []),
        description=cast(str, raw.get("description", "") or ""),
    )


def _parse_sous_type(name: str, raw: dict[str, object]) -> SousTypeRules:
    """Convertit une entree ``sous_types.<name>`` en SousTypeRules."""
    champs_raw = cast(list[dict[str, object]], raw.get("champs_obligatoires", []) or [])
    return SousTypeRules(
        nom=cast(str, raw.get("nom", name)),
        mots_cles_detection=cast(list[str], raw.get("mots_cles_detection", []) or []),
        champs_obligatoires=[_parse_champ(c) for c in champs_raw],
        marqueurs_ihc_attendus=cast(
            list[str], raw.get("marqueurs_ihc_attendus", []) or []
        ),
        template_macroscopie=cast(str, raw.get("template_macroscopie", "") or ""),
        notes=cast(str, raw.get("notes", "") or ""),
    )


def _parse_organ_rules(raw: dict[str, object]) -> OrganRules:
    """Convertit un fichier YAML complet en OrganRules typed."""
    sous_types_raw = cast(dict[str, dict[str, object]], raw.get("sous_types", {}) or {})
    sous_types: dict[str, SousTypeRules] = {
        name: _parse_sous_type(name, data) for name, data in sous_types_raw.items()
    }
    return OrganRules(
        organe=cast(Organe, raw.get("organe", "generic")),
        nom_affichage=cast(str, raw.get("nom_affichage", "") or ""),
        sous_types=sous_types,
        systeme_staging=cast(str, raw.get("systeme_staging", "") or ""),
        description=cast(str, raw.get("description", "") or ""),
    )


# ---------------------------------------------------------------------------
# Chargement initial (eager) et cache
# ---------------------------------------------------------------------------


def _load_yaml_file(path: Path) -> OrganRules:
    """Lit un fichier YAML et le convertit en OrganRules."""
    content: str = path.read_text(encoding="utf-8")
    raw = cast(dict[str, object], yaml.safe_load(content))
    return _parse_organ_rules(raw)


def _load_all_rules() -> dict[Organe, OrganRules]:
    """Charge tous les fichiers .yaml du dossier rules/data/ en memoire."""
    loaded: dict[Organe, OrganRules] = {}
    for path in sorted(RULES_DATA_DIR.glob("*.yaml")):
        rules: OrganRules = _load_yaml_file(path)
        loaded[rules.organe] = rules
    return loaded


def reload_rules() -> None:
    """Recharge tous les YAML (utilise en developpement pour hot-reload)."""
    global _GENERIC_FALLBACK
    _CACHE.clear()
    _CACHE.update(_load_all_rules())
    _GENERIC_FALLBACK = _CACHE.get("generic")


def _ensure_loaded() -> None:
    """Charge les regles a la premiere utilisation."""
    if not _CACHE:
        reload_rules()


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def get_rules(organe: Organe) -> OrganRules:
    """Retourne les regles pour un organe donne, fallback generique sinon.

    Garantit toujours un retour non-None : si l'organe n'est pas couvert,
    retourne le ruleset ``generic`` charge depuis ``generic.yaml``.
    """
    _ensure_loaded()
    rules: OrganRules | None = _CACHE.get(organe)
    if rules is not None:
        return rules
    if _GENERIC_FALLBACK is None:
        raise RuntimeError(
            "Le ruleset generique n'est pas charge. Verifier rules/data/generic.yaml"
        )
    return _GENERIC_FALLBACK


def list_supported_organes() -> list[Organe]:
    """Liste les organes couverts par un fichier YAML specifique."""
    _ensure_loaded()
    return sorted(_CACHE.keys())
