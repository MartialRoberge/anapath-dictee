"""Codeur des positions D1 et D2 du code ADICAP.

Specification unique et source de verite : le fichier
``docs/specs/referentiels/Codage_D1_D2_table.json``. Le module ne recopie pas la
logique de la table, il la lit : une correction du referentiel par la
pathologiste se propage sans toucher au code.

Ce que le module lit reellement est ``backend/data/codage_d1_d2.json``, une
COPIE DEPLOYEE de ce referentiel — le deploiement n'envoie que ``backend/``,
``docs/`` n'y est pas. La copie est produite par
``scripts/sync_referentiels.py`` et ne doit jamais etre editee a la main : la
correction y serait perdue au prochain lancement du script, et entre-temps le
codeur appliquerait une table que personne n'a relue. Un test de contrat echoue
si les deux fichiers divergent.

Ce module est AUTONOME. Il ne remplace pas encore ``adicap.py`` : le branchement
sera fait par le proprietaire du projet.

Trois principes portent tout le module
--------------------------------------
1. L'ORDRE est la specification. Correspondance exacte multi-mots, puis jeton
   exact a limites de mot, puis morphologie de suffixe. Jamais de sous-chaine
   nue : c'est ce classement, et non un score, qui resout les inclusions du
   lexique. Sans lui, "ponction pleurale" se declenche au milieu de
   "cytoponction pleurale" et "colectomie" au milieu de "hemicolectomie".

2. L'ABSTENTION est un resultat legitime, pas un echec. Quand la table ne
   tranche pas — un geste d'exerese absent des deux listes I/O — le codeur
   s'abstient et nomme les candidats. Un defaut sur cette famille produirait une
   erreur systematique sur toute la classe complementaire.

3. Un code SECONDAIRE s'AJOUTE au primaire, il ne le remplace jamais. Il porte
   les memes positions 1, 3-4 et 5-8 ; seule la position 2 change (K4). Et il ne
   peut exister sans son primaire (K5) : ``composer_codes`` est le seul point
   d'emission, et il produit toujours le primaire en tete.

Entrees non validees
--------------------
Les termes marques ``a_valider`` dans le JSON n'ont pas ete confirmes par la
pathologiste. Ils sont INERTES par defaut et ne s'activent qu'avec
``inclure_propositions=True``. Deux consequences a connaitre :

- ``echoguidee`` est une proposition pour la CYTOPONCTION (pas pour la biopsie) :
  "cytoponction echoguidee" rend donc le defaut ``C`` tant que le parametre est
  desactive, et ``G`` une fois active ;
- la liste entiere de l'acte simple ``S`` (secretions) est une proposition : un
  crachat s'abstient par defaut.

La table geste x organe de la famille exerese porte, elle, un champ ``_statut``
distinct ("PROPOSITION DE DEPART"). Elle reste ACTIVE par defaut — sans elle la
famille entiere s'abstiendrait, et les tests de recette l'exigent — mais chaque
resultat qu'elle produit est marque ``a_valider=True`` pour que l'ecran de revue
le signale au praticien.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from text_utils import normaliser

# Chemin construit a partir de __file__, jamais du repertoire courant : le
# serveur n'est pas toujours demarre depuis la racine du depot, et un chemin
# relatif au cwd ferait dependre le codage de la ligne de commande. Il pointe
# DANS backend/ parce que le deploiement n'envoie que ce dossier : viser
# docs/specs ne resoudrait qu'en local (voir scripts/sync_referentiels.py).
_TABLE_PATH: Path = Path(__file__).resolve().parent / "data" / "codage_d1_d2.json"

# Codes D1 atteignables uniquement sur syntagme complet exact : ni morphologie,
# ni similarite, ni pluriel. Une prediction sans correspondance exacte est un
# defaut, pas une approximation acceptable.
CODES_RARES: frozenset[str] = frozenset({"N", "V", "X"})

# Regle de coherence K1 : ces D1 sont cytologiques et imposent D2 = C.
# La liste est ecrite en prose dans le JSON ; le test de contrat verifie qu'elle
# n'a pas derive.
D1_CYTOLOGIQUES: frozenset[str] = frozenset({"A", "C", "E", "F", "G", "L", "R", "S"})

# Le JSON signale le doute sur "autopsie" dans une note en prose et non dans un
# champ 'a_valider' : on le reporte ici pour que la garde soit effective.
_PROPOSITIONS_HORS_CHAMP: frozenset[str] = frozenset({"autopsie"})

# Les 'cas_particuliers_a_valider' du JSON sont decrits en prose : l'action est
# figee ici. H = le guidage est implicite dans le geste. None = "P ou H selon
# mention du guidage", c'est-a-dire exactement le comportement d'une base nue,
# donc aucun code impose. Toutes sont des propositions, inertes par defaut.
_CAS_PARTICULIERS: dict[str, str | None] = {
    "macrobiopsie": "H",
    "microbiopsie": "H",
    "tru-cut": None,
}

# Le JSON decrit les questions de levee de doute sans les rattacher a leur
# famille : ce lien est fait ici.
QUESTION_EXERESE: str = "d1_exerese_i_o"
_QUESTIONS_PAR_FAMILLE: dict[str, str] = {
    "biopsie": "d1_guidage_biopsie",
    "cytoponction": "d1_guidage_cytoponction",
}


# ---------------------------------------------------------------------------
# Resultats publics
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResultatD1:
    """Sortie du codage de la position 1, tracable jusqu'au terme declencheur.

    ``code`` a None signifie une abstention assumee ; ``candidats`` nomme alors
    les codes entre lesquels la table ne tranche pas, et ``question_id`` designe
    la question pre-redigee qui les departage.
    """

    code: str | None
    libelle: str
    origine: str
    terme: str
    a_valider: bool
    candidats: tuple[str, ...]
    question_id: str

    @property
    def abstention(self) -> bool:
        """Vrai quand le codeur refuse de trancher plutot que d'inventer."""
        return self.code is None


@dataclass(frozen=True, slots=True)
class ResultatD2:
    """Sortie du codage de la position 2 : un primaire, plus n secondaires."""

    primaire: str
    libelle_primaire: str
    secondaires: tuple[str, ...]
    motif: str


@dataclass(frozen=True, slots=True)
class CodeAdicap:
    """Un code ADICAP complet d'un prelevement, primaire ou secondaire."""

    code: str
    role: str
    technique: str


# ---------------------------------------------------------------------------
# Structures internes de la table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Terme:
    """Un declencheur de la table, avec son statut de validation."""

    texte: str
    a_valider: bool


@dataclass(frozen=True, slots=True)
class _Base:
    """Base d'une famille. ``code_impose`` court-circuite les modificateurs."""

    terme: _Terme
    code_impose: str | None


@dataclass(frozen=True, slots=True)
class _Modificateur:
    """Un modificateur de famille : un code, ses declencheurs."""

    code: str
    declencheurs: tuple[_Terme, ...]


@dataclass(frozen=True, slots=True)
class _Famille:
    """Famille biopsie ou cytoponction : base, modificateurs ordonnes, defaut."""

    origine: str
    bases: tuple[_Base, ...]
    modificateurs: tuple[_Modificateur, ...]
    code_defaut: str
    candidats: tuple[str, ...]
    question_id: str


@dataclass(frozen=True, slots=True)
class _Exerese:
    """Famille exerese : la table geste x organe, ses bases, sa morphologie."""

    gestes: tuple[tuple[str, str], ...]
    bases: tuple[str, ...]
    suffixes: tuple[str, ...]
    candidats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReglesD1:
    """Les cinq etapes d'evaluation de la position 1, deja ordonnees."""

    rares: tuple[tuple[str, _Terme], ...]
    actes_syntagmes: tuple[tuple[str, _Terme], ...]
    actes_mots: tuple[tuple[str, _Terme], ...]
    familles: tuple[_Famille, ...]
    exerese: _Exerese


@dataclass(frozen=True, slots=True)
class _ReglesD2:
    """Regles de la position 2 : bascule H/C et les sept codes secondaires."""

    declencheurs_c: tuple[str, ...]
    conditions_negatives: tuple[str, ...]
    secondaires: tuple[tuple[str, tuple[str, ...]], ...]


# ---------------------------------------------------------------------------
# Correspondance a limites de mot
# ---------------------------------------------------------------------------

_SEPARATEURS: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def _canoniser(texte: str) -> str:
    """Reduit un texte a ses mots, separes et entoures d'un espace unique.

    Toute ponctuation devient une frontiere de mot. C'est cette frontiere qui
    interdit la sous-chaine : entoure d'espaces, "ponction pleurale" ne peut
    plus se declencher au milieu de "cytoponction pleurale".
    """
    return f" {_SEPARATEURS.sub(' ', normaliser(texte)).strip()} "


@lru_cache(maxsize=None)
def _formes(terme: str) -> tuple[str, str]:
    """Formes cherchees d'un terme de la table : singulier, puis pluriel simple.

    Le pluriel est une tolerance bornee au 's' final du dernier mot, indispensable
    en dictee ("deux biopsies bronchiques"). Elle reste une correspondance a
    limites de mot, jamais une sous-chaine.
    """
    mots = _canoniser(terme).strip()
    return f" {mots} ", f" {mots}s "


def _contient(canonique: str, terme: str, *, pluriel: bool) -> bool:
    """Cherche un terme dans un texte deja canonise, a limites de mot."""
    singulier, au_pluriel = _formes(terme)
    return singulier in canonique or (pluriel and au_pluriel in canonique)


def _nb_mots(terme: str) -> int:
    """Nombre de mots canoniques d'un terme (l'apostrophe compte comme separateur)."""
    return len(_canoniser(terme).split())


def _cle_longueur(terme: str) -> tuple[int, int]:
    """Cle de tri de l'etape 2 : du syntagme le plus long au plus court."""
    return (-_nb_mots(terme), -len(terme))


# ---------------------------------------------------------------------------
# Chargement de la table de decision
# ---------------------------------------------------------------------------


class TableD1D2Indisponible(RuntimeError):
    """La table de decision est absente ou illisible : le codeur ne peut pas coder.

    Cette erreur existe pour interdire la panne silencieuse. L'abstention est un
    resultat legitime du codeur : elle ne se distingue donc pas, dans les
    resultats, d'une abstention causee par une table jamais chargee. Sans erreur
    a la lecture, un fichier manquant en production ferait s'abstenir le codeur
    sur chaque prelevement et rien ne le signalerait avant le depouillement de
    l'etude. On echoue donc au chargement, bruyamment.
    """


def _lire_table(chemin: Path) -> dict[str, object]:
    """Lit la table de decision, ou echoue en nommant le fichier et le remede."""
    remede = "Regenerer la copie deployee : python scripts/sync_referentiels.py"
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as erreur:
        raise TableD1D2Indisponible(
            f"Table de decision D1/D2 illisible : {chemin} ({erreur}). {remede}"
        ) from erreur
    try:
        table = json.loads(contenu)
    except json.JSONDecodeError as erreur:
        raise TableD1D2Indisponible(
            f"Table de decision D1/D2 corrompue : {chemin} n'est pas un JSON valide. {remede}"
        ) from erreur
    if not isinstance(table, dict):
        raise TableD1D2Indisponible(
            f"Table de decision D1/D2 inattendue : {chemin} ne contient pas un objet JSON"
        )
    return table


@lru_cache(maxsize=1)
def _table() -> dict[str, object]:
    """Charge la table de decision D1/D2 une seule fois."""
    return _lire_table(_TABLE_PATH)


def _objet(valeur: object) -> dict[str, object]:
    """Vue typee d'un sous-objet JSON, pour ne jamais propager un type flou."""
    if not isinstance(valeur, dict):
        raise TypeError("objet JSON attendu dans la table D1/D2")
    return valeur


def _liste(valeur: object) -> list[object]:
    """Vue typee d'un tableau JSON."""
    if not isinstance(valeur, list):
        raise TypeError("tableau JSON attendu dans la table D1/D2")
    return valeur


def _section(nom: str) -> dict[str, object]:
    """Section de premier niveau de la table."""
    return _objet(_table()[nom])


def _mots_de(valeur: object) -> tuple[str, ...]:
    """Normalise un champ de la table en tuple de chaines (liste, valeur ou rien)."""
    if isinstance(valeur, list):
        return tuple(str(v) for v in valeur)
    if isinstance(valeur, str):
        return (valeur,)
    return ()


def _propositions(entree: dict[str, object], termes: tuple[str, ...]) -> frozenset[str]:
    """Termes non valides d'une entree.

    Le JSON note parfois l'incertitude en prose ("TOUTE la liste") au lieu d'un
    tableau : l'entree entiere est alors une proposition.
    """
    brut = entree.get("a_valider")
    if isinstance(brut, str):
        return frozenset(termes)
    return frozenset(_mots_de(brut))


def _termes(bruts: tuple[str, ...], propositions: frozenset[str]) -> tuple[_Terme, ...]:
    """Marque chaque terme comme valide ou a valider."""
    return tuple(
        _Terme(t, t in propositions or t in _PROPOSITIONS_HORS_CHAMP) for t in bruts
    )


def _candidats(question_id: str) -> tuple[str, ...]:
    """Codes que la question de levee de doute peut resoudre, hors abstention."""
    doutes = _liste(_section("questions_de_levee_de_doute")["ambiguites_structurelles"])
    for brut in doutes:
        question = _objet(brut)
        if question["id"] != question_id:
            continue
        options = (_objet(o) for o in _liste(question["options"]))
        return tuple(str(o["resout"]) for o in options if o["resout"] != "abstention")
    raise KeyError(f"question de levee de doute inconnue : {question_id}")


def _charger_rares() -> tuple[tuple[str, _Terme], ...]:
    """Etape 1 : N, V, X, avec leurs syntagmes complets."""
    entrees: list[tuple[str, _Terme]] = []
    for code, brut in _section("actes_simples").items():
        if code not in CODES_RARES:
            continue
        entree = _objet(brut)
        termes = _mots_de(entree["termes"])
        entrees.extend((code, t) for t in _termes(termes, _propositions(entree, termes)))
    return tuple(entrees)


def _charger_actes_simples() -> tuple[tuple[str, _Terme], ...]:
    """Actes simples hors codes rares, K en tete.

    Le JSON exige que K passe avant tout ce qui touche a -ectomie : mucosectomie
    et polypectomie endoscopique se terminent en -ectomie sans etre des exereses.
    """
    par_code: dict[str, tuple[_Terme, ...]] = {}
    for code, brut in _section("actes_simples").items():
        if code in CODES_RARES:
            continue
        entree = _objet(brut)
        termes = _mots_de(entree["termes"])
        par_code[code] = _termes(termes, _propositions(entree, termes))
    ordre = ["K", *(code for code in par_code if code != "K")]
    return tuple((code, terme) for code in ordre for terme in par_code[code])


def _charger_bases(famille: dict[str, object]) -> tuple[_Base, ...]:
    """Bases d'une famille, augmentees de ses cas particuliers a valider."""
    bruts = _mots_de(famille["bases"])
    a_valider = frozenset(_mots_de(famille.get("bases_a_valider")))
    bases = [_Base(_Terme(t, t in a_valider), None) for t in bruts]
    for geste in _objet(famille.get("cas_particuliers_a_valider", {})):
        bases.append(_Base(_Terme(geste, True), _CAS_PARTICULIERS[geste]))
    return tuple(sorted(bases, key=lambda b: _cle_longueur(b.terme.texte)))


def _charger_modificateurs(famille: dict[str, object]) -> tuple[_Modificateur, ...]:
    """Modificateurs dans l'ordre du JSON : cet ordre est la specification."""
    modificateurs: list[_Modificateur] = []
    for brut in _liste(famille["modificateurs_ordonnes"]):
        modificateur = _objet(brut)
        declencheurs = _mots_de(modificateur["declencheurs"])
        a_valider = frozenset(_mots_de(modificateur.get("a_valider")))
        modificateurs.append(
            _Modificateur(
                code=str(modificateur["code"]),
                declencheurs=tuple(
                    sorted(
                        _termes(declencheurs, a_valider),
                        key=lambda t: _cle_longueur(t.texte),
                    )
                ),
            )
        )
    return tuple(modificateurs)


def _charger_familles() -> tuple[_Famille, ...]:
    """Etape 4 : les familles biopsie et cytoponction."""
    familles: list[_Famille] = []
    for nom, brut in _section("familles").items():
        famille = _objet(brut)
        question = _QUESTIONS_PAR_FAMILLE[nom]
        familles.append(
            _Famille(
                origine=f"famille_{nom}",
                bases=_charger_bases(famille),
                modificateurs=_charger_modificateurs(famille),
                code_defaut=str(_objet(famille["defaut"])["code"]),
                candidats=_candidats(question),
                question_id=question,
            )
        )
    return tuple(familles)


def _charger_exerese() -> _Exerese:
    """Etape 5 : la table geste x organe, seul discriminant entre I et O."""
    exerese = _section("famille_exerese")
    table = _objet(exerese["table_geste_organe"])
    gestes = [
        (code, geste)
        for cle, code in (("O_organe_entier", "O"), ("I_organe_partiel", "I"))
        for geste in _mots_de(table[cle])
    ]
    morphologie = str(exerese["morphologie"]).lstrip("-")
    return _Exerese(
        gestes=tuple(sorted(gestes, key=lambda g: _cle_longueur(g[1]))),
        bases=_mots_de(exerese["bases"]),
        suffixes=(morphologie, f"{morphologie}s"),
        candidats=_candidats(QUESTION_EXERESE),
    )


@lru_cache(maxsize=1)
def _regles() -> _ReglesD1:
    """Assemble les etapes de la position 1, deja triees et ordonnees."""
    actes = _charger_actes_simples()
    syntagmes = sorted(
        (paire for paire in actes if _nb_mots(paire[1].texte) > 1),
        key=lambda paire: _cle_longueur(paire[1].texte),
    )
    return _ReglesD1(
        rares=_charger_rares(),
        actes_syntagmes=tuple(syntagmes),
        actes_mots=tuple(p for p in actes if _nb_mots(p[1].texte) == 1),
        familles=_charger_familles(),
        exerese=_charger_exerese(),
    )


@lru_cache(maxsize=1)
def _regles_d2() -> _ReglesD2:
    """Assemble les regles de la position 2."""
    d2 = _section("D2")
    cytologie = _objet(_objet(d2["code_primaire"])["C"])
    return _ReglesD2(
        declencheurs_c=_mots_de(cytologie["declencheurs"]),
        conditions_negatives=_mots_de(cytologie["condition_negative"]),
        secondaires=tuple(
            (code, _mots_de(_objet(brut)["declencheurs"]))
            for code, brut in _objet(d2["codes_secondaires"]).items()
            if not code.startswith("_")
        ),
    )


@lru_cache(maxsize=1)
def _libelles_d1() -> dict[str, str]:
    """Libelle de chaque code D1, assemble depuis les trois sources de la table."""
    libelles: dict[str, str] = {}
    for code, brut in _section("actes_simples").items():
        libelles[code] = str(_objet(brut)["libelle"])
    for nom, brut in _section("familles").items():
        famille = _objet(brut)
        defaut = _objet(famille["defaut"])
        libelles[str(defaut["code"])] = str(defaut["libelle"])
        for modificateur in (_objet(m) for m in _liste(famille["modificateurs_ordonnes"])):
            etiquette = str(modificateur["nom"]).replace("_", " ")
            libelles[str(modificateur["code"])] = f"{nom} {etiquette}".upper()
    for code, texte in _objet(_section("famille_exerese")["discriminant"]).items():
        libelles[code] = str(texte)
    return libelles


@lru_cache(maxsize=1)
def _libelles_d2() -> dict[str, str]:
    """Libelle de chaque code D2 actif, primaire ou secondaire."""
    d2 = _section("D2")
    libelles = {
        code: str(_objet(brut)["libelle"])
        for code, brut in _objet(d2["code_primaire"]).items()
    }
    for code, brut in _objet(d2["codes_secondaires"]).items():
        if not code.startswith("_"):
            libelles[code] = str(_objet(brut)["libelle"])
    return libelles


def libelle_d1(code: str) -> str:
    """Libelle officiel d'un code D1, chaine vide si le code est inconnu."""
    return _libelles_d1().get(code, "")


def libelle_d2(code: str) -> str:
    """Libelle officiel d'un code D2 actif, chaine vide si le code est inconnu."""
    return _libelles_d2().get(code, "")


# ---------------------------------------------------------------------------
# Position 1 — mode de prelevement
# ---------------------------------------------------------------------------


def _resultat(
    code: str,
    origine: str,
    terme: str,
    a_valider: bool,
    candidats: tuple[str, ...] = (),
    question_id: str = "",
) -> ResultatD1:
    """Construit un resultat D1 en gardant le terme qui l'a declenche."""
    return ResultatD1(
        code=code,
        libelle=libelle_d1(code),
        origine=origine,
        terme=terme,
        a_valider=a_valider,
        candidats=candidats,
        question_id=question_id,
    )


def _abstention(libelle: str, candidats: tuple[str, ...], question_id: str) -> ResultatD1:
    """Construit une abstention nommee : ce qui manque, et qui peut le fournir."""
    return ResultatD1(
        code=None,
        libelle=libelle,
        origine="abstention",
        terme="",
        a_valider=False,
        candidats=candidats,
        question_id=question_id,
    )


def _etape_rares(canonique: str, regles: _ReglesD1, propositions: bool) -> ResultatD1 | None:
    """Etape 1 : N, V, X. Syntagme complet exact, sans tolerance de pluriel."""
    for code, terme in regles.rares:
        if terme.a_valider and not propositions:
            continue
        if _contient(canonique, terme.texte, pluriel=False):
            return _resultat(code, "code_rare", terme.texte, terme.a_valider)
    return None


def _premier_acte(
    canonique: str, entrees: tuple[tuple[str, _Terme], ...], propositions: bool
) -> ResultatD1 | None:
    """Premier acte simple present dans la liste, deja ordonnee par l'appelant."""
    for code, terme in entrees:
        if terme.a_valider and not propositions:
            continue
        if _contient(canonique, terme.texte, pluriel=True):
            return _resultat(code, "acte_simple", terme.texte, terme.a_valider)
    return None


def _etape_actes_syntagmes(
    canonique: str, regles: _ReglesD1, propositions: bool
) -> ResultatD1 | None:
    """Etape 2 : syntagmes multi-mots des actes simples, du plus long au plus court."""
    return _premier_acte(canonique, regles.actes_syntagmes, propositions)


def _etape_actes_mots(
    canonique: str, regles: _ReglesD1, propositions: bool
) -> ResultatD1 | None:
    """Etape 3 : actes simples en un seul mot, a limites de mot, K en tete."""
    return _premier_acte(canonique, regles.actes_mots, propositions)


def _base_presente(
    canonique: str, bases: tuple[_Base, ...], propositions: bool
) -> _Base | None:
    """Base de famille presente dans le texte, la plus specifique d'abord."""
    for base in bases:
        if base.terme.a_valider and not propositions:
            continue
        if _contient(canonique, base.terme.texte, pluriel=True):
            return base
    return None


def _premier_declencheur(
    canonique: str, declencheurs: tuple[_Terme, ...], propositions: bool
) -> _Terme | None:
    """Premier declencheur de modificateur present dans le texte."""
    for terme in declencheurs:
        if terme.a_valider and not propositions:
            continue
        if _contient(canonique, terme.texte, pluriel=True):
            return terme
    return None


def _coder_famille(
    canonique: str, famille: _Famille, propositions: bool
) -> ResultatD1 | None:
    """Une famille repond si sa base est presente : modificateur, sinon defaut."""
    base = _base_presente(canonique, famille.bases, propositions)
    if base is None:
        return None
    if base.code_impose is not None:
        return _resultat(base.code_impose, famille.origine, base.terme.texte, True)
    for modificateur in famille.modificateurs:
        terme = _premier_declencheur(canonique, modificateur.declencheurs, propositions)
        if terme is not None:
            return _resultat(
                modificateur.code,
                famille.origine,
                terme.texte,
                terme.a_valider or base.terme.a_valider,
            )
    # Ce defaut est ecrit dans la table (P pour la biopsie, C pour la
    # cytoponction) : ce n'est pas un repli fabrique par le codeur.
    return _resultat(
        famille.code_defaut,
        famille.origine,
        base.terme.texte,
        base.terme.a_valider,
        famille.candidats,
        famille.question_id,
    )


def _etape_familles(
    canonique: str, regles: _ReglesD1, propositions: bool
) -> ResultatD1 | None:
    """Etape 4 : familles biopsie et cytoponction, dans l'ordre de la table."""
    for famille in regles.familles:
        resultat = _coder_famille(canonique, famille, propositions)
        if resultat is not None:
            return resultat
    return None


def _famille_exerese_evoquee(canonique: str, exerese: _Exerese) -> bool:
    """Le texte parle-t-il d'exerese sans nommer un geste de la table ?

    Repose sur les bases ("piece", "exerese") puis, en dernier recours, sur la
    morphologie du suffixe -ectomie.
    """
    if any(_contient(canonique, base, pluriel=True) for base in exerese.bases):
        return True
    return any(mot.endswith(exerese.suffixes) for mot in canonique.split())


def _etape_exerese(canonique: str, regles: _ReglesD1) -> ResultatD1 | None:
    """Etape 5 : la table geste x organe tranche I ou O, sinon abstention nommee.

    Les codes I et O partagent exactement les memes declencheurs : seul le fait
    que l'organe soit retire en entier les separe. Faute de geste connu, poser un
    defaut reviendrait a se tromper sur toute la classe complementaire.
    """
    for code, geste in regles.exerese.gestes:
        if _contient(canonique, geste, pluriel=True):
            return _resultat(code, "famille_exerese", geste, True)
    if not _famille_exerese_evoquee(canonique, regles.exerese):
        return None
    return _abstention(
        "Exerese : geste absent de la table geste x organe",
        regles.exerese.candidats,
        QUESTION_EXERESE,
    )


def coder_d1(texte: str, *, inclure_propositions: bool = False) -> ResultatD1:
    """Code la position 1 en suivant l'ordre d'evaluation de la table.

    ``inclure_propositions`` active les entrees marquees ``a_valider`` dans le
    JSON, que la pathologiste n'a pas confirmees : elles sont inertes par defaut.
    """
    canonique = _canoniser(texte)
    regles = _regles()
    trouve = (
        _etape_rares(canonique, regles, inclure_propositions)
        or _etape_actes_syntagmes(canonique, regles, inclure_propositions)
        or _etape_actes_mots(canonique, regles, inclure_propositions)
        or _etape_familles(canonique, regles, inclure_propositions)
        or _etape_exerese(canonique, regles)
    )
    return trouve or _abstention("Aucun mode de prelevement reconnu", (), "")


# ---------------------------------------------------------------------------
# Position 2 — technique
# ---------------------------------------------------------------------------


def _premier_terme(canonique: str, termes: tuple[str, ...]) -> str | None:
    """Premier terme present, retourne pour tracer la regle declenchee."""
    for terme in termes:
        if _contient(canonique, terme, pluriel=True):
            return terme
    return None


def _primaire_d2(canonique: str, d1: str | None) -> tuple[str, str]:
    """Determine le code primaire H ou C, et le motif de la decision.

    L'inclusion est testee en premier parce qu'elle prime sur tout : un cytobloc
    est une inclusion, donc H, meme apres une cytoponction et meme quand K1
    reclamerait C.
    """
    regles = _regles_d2()
    inclusion = _premier_terme(canonique, regles.conditions_negatives)
    if inclusion is not None:
        return "H", f"inclusion mentionnee ({inclusion})"
    declencheur = _premier_terme(canonique, regles.declencheurs_c)
    if declencheur is not None:
        return "C", f"declencheur cytologique ({declencheur})"
    if d1 is not None and d1 in D1_CYTOLOGIQUES:
        return "C", f"K1 : D1 cytologique ({d1})"
    return "H", "defaut"


def _secondaires_d2(canonique: str) -> tuple[str, ...]:
    """Un code secondaire par technique citee, dans l'ordre de la table."""
    return tuple(
        code
        for code, declencheurs in _regles_d2().secondaires
        if _premier_terme(canonique, declencheurs) is not None
    )


def coder_d2(texte: str, d1: str | None = None) -> ResultatD2:
    """Code la position 2 : un primaire H ou C, plus un secondaire par technique.

    ``d1`` sert la regle K1 : un mode de prelevement cytologique impose C, sauf
    mention d'inclusion. Les codes declares inactifs par la table — dont I,
    l'immuno-histochimie, qui releve de la cotation et non de la codification —
    ne sont jamais predits.
    """
    canonique = _canoniser(texte)
    primaire, motif = _primaire_d2(canonique, d1)
    return ResultatD2(
        primaire=primaire,
        libelle_primaire=libelle_d2(primaire),
        secondaires=_secondaires_d2(canonique),
        motif=motif,
    )


# ---------------------------------------------------------------------------
# Composition des codes d'un prelevement
# ---------------------------------------------------------------------------


def d7_autorise(d2_primaire: str) -> bool:
    """K2 et K3 : le champ D7 n'est accessible en positions 5-8 que si D2 vaut C."""
    return d2_primaire == "C"


def _verifier_positions(d1: str, positions_3_8: str) -> None:
    """Garde de composition : un code ADICAP fait exactement huit caracteres."""
    if len(d1) != 1:
        raise ValueError("D1 : un seul caractere attendu")
    if len(positions_3_8) != 6:
        raise ValueError("positions 3-8 : six caracteres attendus")


def composer_codes(d1: str, d2: ResultatD2, positions_3_8: str) -> tuple[CodeAdicap, ...]:
    """Compose les codes d'UN prelevement : le primaire, puis un par technique.

    K4 : un code secondaire reprend les positions 1, 3-4 et 5-8 du primaire et ne
    change que la position 2. K5 : c'est l'unique point d'emission d'un code
    secondaire, et il produit toujours le primaire en tete — un secondaire
    orphelin est donc structurellement impossible.
    """
    _verifier_positions(d1, positions_3_8)
    codes = [
        CodeAdicap(
            code=f"{d1}{d2.primaire}{positions_3_8}",
            role="primaire",
            technique=d2.libelle_primaire,
        )
    ]
    codes.extend(
        CodeAdicap(
            code=f"{d1}{secondaire}{positions_3_8}",
            role="secondaire",
            technique=libelle_d2(secondaire),
        )
        for secondaire in d2.secondaires
    )
    return tuple(codes)
