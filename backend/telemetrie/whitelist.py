"""Whitelist stricte des evenements de telemetrie MARC v3.

Principe : un evenement n'est accepte que si son type est connu ET si chacun de ses
champs est declare ci-dessous avec une forme fermee (nombre borne, booleen, enum,
identifiant technique [a-z0-9_]). Toute autre cle, toute chaine libre, tout type
inattendu fait rejeter l'evenement entier. Il n'existe aucun champ de texte libre :
ni dictee, ni compte rendu, ni nom de patient ne peut donc traverser ce filtre.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

ID_RE = re.compile(r"^[a-z0-9_]{1,48}$")
PROJET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LISTE = 20


@dataclass(frozen=True)
class Num:
    lo: float
    hi: float


@dataclass(frozen=True)
class Enum:
    valeurs: frozenset[str]


@dataclass(frozen=True)
class Bool:
    pass


@dataclass(frozen=True)
class Ident:
    """Identifiant technique de champ/organe kb : [a-z0-9_], 48 car. max."""


@dataclass(frozen=True)
class Idents:
    """Liste d'identifiants techniques (organes), 20 max."""


Spec = Num | Enum | Bool | Ident | Idents


def _e(*v: str) -> Enum:
    return Enum(frozenset(v))


NIVEAU_SERVICE = _e("N0", "N1", "N2", "N3")
DELAI = Num(0, 3_600_000)
ELEMENT_TYPE = _e("phrase", "trou", "titre", "liste")
STATUT = _e("dicte", "reformule", "normalise", "a_completer")
NIVEAU = _e("haute", "moyenne", "basse")
ALERTE_TYPE = _e("incoherence", "unite", "manquant", "phonetique", "securite", "codage")
GRAVITE = _e("bloquant", "attention", "info")
SYSTEME = _e("ADICAP", "SNOMED_CT", "CIM_O3")
STATUT_CODE = _e("certain", "partiel", "suggestion")
MOTIFS = ("omission", "invention", "mauvaise_unite", "code_errone", "trop_lent", "mise_en_forme", "autre")

# Champs de chaque type d'evenement (tous optionnels, aucun autre accepte).
SCHEMAS: dict[str, dict[str, Spec]] = {
    "projet_genere": {
        "duree_ms": Num(0, 600_000),
        "niveau_service": NIVEAU_SERVICE,
        "organes": Idents(),
        "contexte_lesionnel": _e("benin", "precancereux", "malin", "indetermine"),
        "prelevement": Ident(),
        "nb_elements": Num(0, 2000),
        "nb_trous": Num(0, 500),
        "nb_alertes": Num(0, 500),
        "nb_corrections": Num(0, 500),
        "confiance_moyenne": Num(0, 1),
    },
    "projet_itere": {"duree_ms": Num(0, 600_000), "nb_tours": Num(0, 100)},
    "element_edite": {
        "element_type": ELEMENT_TYPE,
        "statut": STATUT,
        "niveau": NIVEAU,
        "champ_id": Ident(),
        "delta_caracteres": Num(-5000, 5000),
    },
    "trou_comble": {"champ_id": Ident(), "via": _e("option", "saisie", "dictee"), "delai_ms": DELAI, "obligatoire": Bool()},
    "trou_ignore": {"champ_id": Ident(), "obligatoire": Bool()},
    "alerte_resolue": {"alerte_type": ALERTE_TYPE, "gravite": GRAVITE, "delai_ms": DELAI},
    "alerte_ignoree": {"alerte_type": ALERTE_TYPE, "gravite": GRAVITE, "delai_ms": DELAI},
    "correction_acceptee": {"confiance": Num(0, 1), "delai_ms": DELAI},
    "correction_rejetee": {"confiance": Num(0, 1), "delai_ms": DELAI},
    "code_copie": {"systeme": SYSTEME, "statut": STATUT_CODE},
    "code_modifie": {"systeme": SYSTEME, "statut": STATUT_CODE},
    "source_consultee": {"source_kind": _e("dictee", "kb", "regle", "agent", "web")},
    "feedback": {"sens": _e("positif", "negatif"), "motifs": Idents()},
    "export": {
        "format": _e("docx", "pdf", "texte", "presse_papiers", "fhir"),
        "duree_depuis_generation_ms": Num(0, 86_400_000),
        "nb_retouches": Num(0, 5000),
        "sans_retouche": Bool(),
    },
    "session_temps": {"duree_s": Num(0, 86_400)},
    "erreur": {
        "code": _e("reseau", "stt", "llm", "timeout", "validation", "inconnu"),
        "etape": Ident(),
        "niveau_service": NIVEAU_SERVICE,
    },
}

# Les motifs de feedback sont une liste d'ids restreints a l'enum MOTIFS.
_MOTIFS_OK = frozenset(MOTIFS)


class Rejet(ValueError):
    """Evenement non conforme a la whitelist."""


def _valider_valeur(cle: str, spec: Spec, v: object) -> object:
    if isinstance(spec, Num):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise Rejet(f"{cle}: nombre attendu")
        if not spec.lo <= v <= spec.hi:
            raise Rejet(f"{cle}: hors bornes")
        return v
    if isinstance(spec, Bool):
        if not isinstance(v, bool):
            raise Rejet(f"{cle}: booléen attendu")
        return v
    if isinstance(spec, Enum):
        if not isinstance(v, str) or v not in spec.valeurs:
            raise Rejet(f"{cle}: valeur hors enum")
        return v
    if isinstance(spec, Ident):
        if not isinstance(v, str) or not ID_RE.fullmatch(v):
            raise Rejet(f"{cle}: identifiant invalide")
        return v
    if not isinstance(v, list) or len(v) > MAX_LISTE:
        raise Rejet(f"{cle}: liste invalide")
    for x in v:
        if not isinstance(x, str) or not ID_RE.fullmatch(x):
            raise Rejet(f"{cle}: identifiant invalide")
        if cle == "motifs" and x not in _MOTIFS_OK:
            raise Rejet(f"{cle}: motif inconnu")
    return list(v)


def valider_evenement(type_: object, payload: object, projet_id: object = None) -> tuple[str, dict, str | None]:
    """Retourne (type, payload nettoye, projet_id) ou leve Rejet. Aucune cle inconnue tolere."""
    if not isinstance(type_, str) or type_ not in SCHEMAS:
        raise Rejet("type inconnu")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise Rejet("payload invalide")
    schema = SCHEMAS[type_]
    propre: dict[str, object] = {}
    for cle, v in payload.items():
        if cle not in schema:
            raise Rejet(f"champ non whiteliste: {cle}")
        if v is None:
            continue
        propre[cle] = _valider_valeur(cle, schema[cle], v)
    if projet_id is not None and (not isinstance(projet_id, str) or not PROJET_ID_RE.fullmatch(projet_id)):
        raise Rejet("projet_id invalide")
    return type_, propre, projet_id
