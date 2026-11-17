"""Reperage deterministe des mesures dictees (valeur + unite + objet mesure).

La dictee enonce les nombres en chiffres ou en lettres ("vingt-cinq
centimetres", "2,5 cm", "deux virgule cinq millimetres", "25 x 18 x 10 mm").
Ce module retrouve chaque mesure avec son empan exact dans le texte d'origine,
sans modele de langage : c'est la base du verificateur d'unites mm/cm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from reports.numbers import _word_to_int  # conversion "vingt-cinq" -> 25
from text_utils import normaliser

_UNITES: dict[str, str] = {
    "mm": "mm", "millimetre": "mm", "millimetres": "mm",
    "cm": "cm", "centimetre": "cm", "centimetres": "cm",
    "um": "µm", "µm": "µm", "micron": "µm", "microns": "µm",
    "micrometre": "µm", "micrometres": "µm",
}
_FACTEUR_MM: dict[str, float] = {"mm": 1.0, "cm": 10.0, "µm": 0.001}

#: Jeton : nombre (decimales a virgule ou point), mot, ou signe de dimension.
_JETON: re.Pattern[str] = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+|[×x*]", re.UNICODE)

_SEPARATEURS: frozenset[str] = frozenset({"x", "×", "*", "sur", "fois", "par"})
_MOTS_NOMBRE: frozenset[str] = frozenset({
    "zero", "un", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
    "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    "vingt", "vingts", "trente", "quarante", "cinquante", "soixante", "cent",
    "cents", "et",
})

#: Objets mesures reconnus (forme normalisee -> categorie de mesure).
OBJETS: dict[str, str] = {
    "tumeur": "tumeur", "tumoral": "tumeur", "tumorale": "tumeur", "lesion": "tumeur",
    "nodule": "tumeur", "masse": "tumeur", "formation": "tumeur", "polype": "polype",
    "fragment": "fragment", "fragments": "fragment", "carotte": "carotte",
    "carottes": "carotte", "biopsie": "fragment", "biopsies": "fragment",
    "copeaux": "fragment", "copeau": "fragment",
    "piece": "piece", "lobe": "piece", "segment": "piece", "colectomie": "piece",
    "lobectomie": "piece", "mastectomie": "piece", "tumorectomie": "piece",
    "prostatectomie": "piece", "cone": "piece", "conisation": "piece",
    "recoupe": "marge", "marge": "marge", "marges": "marge", "limite": "marge",
    "berge": "marge", "distance": "marge",
    "ganglion": "ganglion", "ganglions": "ganglion",
    "breslow": "breslow", "epaisseur": "breslow",
    "kyste": "tumeur", "ulceration": "tumeur",
}


@dataclass(slots=True)
class Mesure:
    """Une mesure dictee : valeurs (une par axe), unite, empan, objet."""

    valeurs: list[float]
    unite: str
    debut: int
    fin: int
    texte: str
    objet: str | None = None
    #: Mot de la dictee qui designe l'objet (pour l'explication).
    objet_mot: str | None = None
    #: « de 2 a 4 cm » : les deux valeurs sont les bornes d'un intervalle, pas deux axes.
    intervalle: bool = False
    valeurs_mm: list[float] = field(default_factory=list)

    @property
    def max_mm(self) -> float:
        return max(self.valeurs_mm) if self.valeurs_mm else 0.0


@dataclass(frozen=True, slots=True)
class _Tok:
    brut: str
    forme: str
    debut: int
    fin: int


def _tokeniser(texte: str) -> list[_Tok]:
    return [
        _Tok(m.group(0), normaliser(m.group(0)), m.start(), m.end())
        for m in _JETON.finditer(texte)
    ]


def _est_mot_nombre(forme: str) -> bool:
    return forme in _MOTS_NOMBRE or all(p in _MOTS_NOMBRE for p in forme.split("-") if p)


def _valeur_groupe(toks: list[_Tok]) -> float | None:
    """Valeur d'un groupe de jetons : "25", "2,5", "vingt cinq", "deux virgule cinq"."""
    if len(toks) == 1 and re.fullmatch(r"\d+(?:[.,]\d+)?", toks[0].brut):
        return float(toks[0].brut.replace(",", "."))
    formes = [t.forme for t in toks]
    if "virgule" in formes:
        i = formes.index("virgule")
        entier = _valeur_groupe(toks[:i]) if i else None
        decimale_toks = toks[i + 1:]
        dec = _valeur_groupe(decimale_toks) if decimale_toks else None
        if entier is None or dec is None:
            return None
        chiffres = str(int(dec))
        return float(f"{int(entier)}.{chiffres}")
    if any(re.fullmatch(r"\d+(?:[.,]\d+)?", t.brut) for t in toks):
        return None
    v = _word_to_int("-".join(formes))
    return float(v) if v is not None else None


def _groupe_avant(toks: list[_Tok], fin: int) -> tuple[int, float] | None:
    """Groupe numerique se terminant a l'index ``fin`` (inclus) : (index debut, valeur)."""
    if fin < 0:
        return None
    t = toks[fin]
    if re.fullmatch(r"\d+(?:[.,]\d+)?", t.brut):
        return fin, float(t.brut.replace(",", "."))
    if not (_est_mot_nombre(t.forme)):
        return None
    debut = fin
    while debut - 1 >= 0 and (_est_mot_nombre(toks[debut - 1].forme) or toks[debut - 1].forme == "virgule"):
        debut -= 1
    # On retire un "et"/"virgule" en tete, qui ne peut pas commencer un nombre.
    while debut <= fin and toks[debut].forme in ("et", "virgule"):
        debut += 1
    if debut > fin:
        return None
    valeur = _valeur_groupe(toks[debut:fin + 1])
    return (debut, valeur) if valeur is not None else None


def extraire_mesures(texte: str) -> list[Mesure]:
    """Toutes les mesures de longueur du texte, avec empan et objet probable."""
    toks = _tokeniser(texte)
    mesures: list[Mesure] = []
    for i, tok in enumerate(toks):
        unite = _UNITES.get(tok.forme) or _UNITES.get(tok.brut)
        if unite is None:
            continue
        groupe = _groupe_avant(toks, i - 1)
        if groupe is None:
            continue
        debut_idx, valeur = groupe
        valeurs = [valeur]
        # Dimensions multiples : "25 x 18 x 10 mm", "vingt sur dix millimetres".
        while debut_idx - 1 >= 0:
            if debut_idx - 2 >= 0 and toks[debut_idx - 1].forme in _SEPARATEURS:
                precedent = _groupe_avant(toks, debut_idx - 2)
            elif re.fullmatch(r"\s*,\s*", texte[toks[debut_idx - 1].fin:toks[debut_idx].debut]) \
                    and re.fullmatch(r"\d+(?:[.,]\d+)?", toks[debut_idx - 1].brut) and len(valeurs) < 3:
                precedent = _groupe_avant(toks, debut_idx - 1)  # « 18, 17, 14 mm » : axes dictes en liste
            else:
                break
            if precedent is None:
                break
            debut_idx, v = precedent
            valeurs.insert(0, v)
        intervalle = False
        if debut_idx - 2 >= 0 and toks[debut_idx - 1].forme == "a" and len(valeurs) == 1:
            borne = _groupe_avant(toks, debut_idx - 2)  # « de 2 a 4 cm » : intervalle, borne basse = 2
            if borne is not None and borne[0] - 1 >= 0 and toks[borne[0] - 1].forme in ("de", "d", "entre"):
                debut_idx, v = borne
                valeurs.insert(0, v)
                intervalle = True
        objet, objet_mot = None, None
        for j in range(debut_idx - 1, max(-1, debut_idx - 7), -1):
            cat = OBJETS.get(toks[j].forme)
            if cat:
                objet, objet_mot = cat, toks[j].brut
                break
            if _UNITES.get(toks[j].forme):
                break  # une autre mesure s'intercale : on n'attribue pas d'objet
        if objet is None and i + 2 < len(toks) and toks[i + 1].forme in ("de", "d", "du", "des") \
                and not re.search(r"[.;!?\n]", texte[tok.fin:toks[i + 2].debut]):
            # « trois millimetres DE TUMEUR invasive » : l'objet suit l'unite
            k = i + 2
            while k < len(toks) and toks[k].forme in ("la", "le", "l", "un", "une", "cette", "ce") and k < i + 4:
                k += 1
            cat = OBJETS.get(toks[k].forme) if k < len(toks) else None
            if cat:
                objet, objet_mot = cat, toks[k].brut
        debut, fin = toks[debut_idx].debut, tok.fin
        mesures.append(Mesure(
            valeurs=valeurs, unite=unite, debut=debut, fin=fin, texte=texte[debut:fin],
            objet=objet, objet_mot=objet_mot, intervalle=intervalle,
            valeurs_mm=[v * _FACTEUR_MM[unite] for v in valeurs],
        ))
    return mesures


def formater_valeur(v: float) -> str:
    """25.0 -> '25' ; 2.5 -> '2,5' (convention francaise)."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}".replace(".", ",")


def chiffrer(texte: str) -> str:
    """Remplace les nombres ecrits en lettres par des chiffres (« cinq ganglions » -> « 5 ganglions »).

    Sert UNIQUEMENT aux controles deterministes ecrits pour des chiffres (regles de
    coherence C1-C16) ; le texte affiche n'est jamais modifie.
    """
    toks = _tokeniser(texte)
    morceaux: list[str] = []
    curseur, i = 0, 0
    while i < len(toks):
        if _est_mot_nombre(toks[i].forme) and toks[i].forme != "et":
            j = i
            while j + 1 < len(toks) and (_est_mot_nombre(toks[j + 1].forme) or toks[j + 1].forme == "virgule"):
                j += 1
            while j > i and toks[j].forme in ("et", "virgule"):
                j -= 1
            v = _valeur_groupe(toks[i:j + 1])
            if v is not None:
                morceaux.append(texte[curseur:toks[i].debut])
                morceaux.append(formater_valeur(v))
                curseur = toks[j].fin
                i = j + 1
                continue
        i += 1
    morceaux.append(texte[curseur:])
    return "".join(morceaux)


def decrire_mesure_mm(m: Mesure) -> str:
    """Valeurs d'une mesure en mm, lisibles : « 20–40 mm » (intervalle) ou « 25 x 18 mm » (axes)."""
    if m.intervalle and len(m.valeurs_mm) == 2:
        return f"{formater_valeur(m.valeurs_mm[0])}–{formater_valeur(m.valeurs_mm[1])} mm"
    return " x ".join(formater_valeur(v) for v in m.valeurs_mm) + " mm"
