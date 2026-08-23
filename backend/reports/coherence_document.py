"""Couche 2 — coherence documentaire DETERMINISTE (catalogue C1 a C17).

Cette couche ne raisonne pas, ne diagnostique pas : elle compte et compare. Aucun
modele de langage n'intervient, aucune heuristique floue — uniquement des
compteurs, des ensembles et des comparaisons arithmetiques. C'est ce qui la rend
sans risque reglementaire : une regle ne dit JAMAIS ce qui est vrai, elle dit
seulement ce qui est incoherent avec le reste du document.

Chaque regle est une fonction courte ``regle_cXX_*`` qui prend le texte du compte
rendu et retourne soit ``None`` (rien a signaler), soit une ``AlerteDocument``.
``verifier_coherence_document`` assemble les alertes.

Deux principes gouvernent l'ecriture des regles :

1. **Zero faux positif avant tout.** Un CR bien forme ne doit declencher aucune
   alerte. Chaque fois que le texte est ambigu (enumeration incomplete, comptage
   multiple, lateralite double), la regle S'ABSTIENT au lieu de deviner. Le
   seuil a ete regle sur les 653 textes de reference du praticien
   (``data/textes_canoniques.json``), qui ne declenchent aucune alerte.
2. **Le CR est la seule source.** La dictee n'est consultee que par C2, en repli,
   quand le CR lui-meme n'annonce aucun nombre de prelevements.

C1 a C16 sont implementees. C17 exige un referentiel externe (couche 3) et est
exposee comme non evaluable plutot qu'approximee : voir ``REGLES_NON_EVALUABLES``.
C10 est restreinte a sa seule forme verifiable, justifiee sur la fonction.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from negation import NEGATION_MARKERS, mask_negations
from reports.knowledge import detect_organs
from reports.numbers import spelled_numbers_to_digits
from text_utils import normaliser

# ---------------------------------------------------------------------------
# Modele de resultat
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Empan:
    """Localisation d'une alerte dans le texte du CR (offsets absolus)."""

    debut: int
    fin: int
    texte: str


@dataclass(slots=True, frozen=True)
class AlerteDocument:
    """Incoherence detectee : la regle qui la porte, son message, son empan."""

    regle: str
    message: str
    empan: Empan | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "regle": self.regle,
            "message": self.message,
            "empan": asdict(self.empan) if self.empan is not None else None,
        }


#: Regles du catalogue qui ne sont PAS calculables a partir du seul texte : elles
#: exigent un referentiel externe (couche 3, completude). Exposees explicitement
#: plutot que silencieusement omises.
REGLES_NON_EVALUABLES: dict[str, str] = {
    "C17": (
        "Carcinome -> grade obligatoire selon le referentiel de l'organe. Le "
        "referentiel applicable (SBR, Gleason/ISUP, Fuhrman, OMS...) depend de "
        "l'organe et du type de prelevement : il n'est pas derivable du texte "
        "du CR. Regle a implementer dans la couche completude."
    ),
}

#: Formulation de refus produite en amont pour une dictee non medicale : un tel
#: document n'a pas d'invariants documentaires a verifier.
_REFUS_NON_MEDICAL: str = "ne semble pas correspondre"


# ---------------------------------------------------------------------------
# Decoupage en sections
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SectionCR:
    """Une section du CR. ``debut`` est l'offset de sa PREMIERE occurrence.

    ``texte`` concatene toutes les occurrences de la section : un CR
    multi-prelevement titre plusieurs fois "Macroscopie".
    """

    nom: str
    debut: int
    texte: str


#: Libelle d'en-tete normalise -> section canonique.
_ENTETES: dict[str, str] = {
    "macroscopie": "macroscopie",
    "examen macroscopique": "macroscopie",
    "description macroscopique": "macroscopie",
    "microscopie": "microscopie",
    "examen microscopique": "microscopie",
    "etude microscopique": "microscopie",
    "etude histologique": "microscopie",
    "histologie": "microscopie",
    "etude cytologique": "microscopie",
    "examen cytologique": "microscopie",
    "cytologie": "microscopie",
    "immunohistochimie": "immunohistochimie",
    "immuno-histochimie": "immunohistochimie",
    "etude immunohistochimique": "immunohistochimie",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "examen extemporane": "extemporane",
}

# Un en-tete est une ligne entierement en gras. Le titre du prelevement se
# distingue par ses doubles soulignes (**__TITRE__**), convention du prompt.
_ENTETE_RE: re.Pattern[str] = re.compile(
    r"^[ \t]*\*\*\s*([^\n*]+?)\s*\*\*[ \t]*$", re.MULTILINE
)


def _cle_entete(brut: str) -> str:
    """Normalise un libelle d'en-tete pour la table des sections connues."""
    sans_decor: str = re.sub(r"[_:*]", " ", brut)
    return re.sub(r"\s+", " ", normaliser(sans_decor)).strip()


def _reperes_de_sections(cr: str) -> list[tuple[str, re.Match[str]]]:
    """Liste ordonnee des en-tetes RECONNUS (les autres gras ne coupent rien)."""
    reperes: list[tuple[str, re.Match[str]]] = []
    titre_vu: bool = False
    for m in _ENTETE_RE.finditer(cr):
        brut: str = m.group(1).strip()
        cle: str = _cle_entete(brut)
        if cle in _ENTETES:
            reperes.append((_ENTETES[cle], m))
        elif not titre_vu and brut.startswith("__") and brut.endswith("__"):
            reperes.append(("titre", m))
            titre_vu = True
    return reperes


def decouper_sections(cr: str) -> dict[str, SectionCR]:
    """Decoupe le CR en sections canoniques (titre, macroscopie, ...)."""
    reperes: list[tuple[str, re.Match[str]]] = _reperes_de_sections(cr)
    sections: dict[str, SectionCR] = {}
    for i, (nom, m) in enumerate(reperes):
        fin: int = reperes[i + 1][1].start() if i + 1 < len(reperes) else len(cr)
        if nom == "titre":
            debut, contenu = m.start(1), m.group(1).strip().strip("_").strip()
        else:
            debut, contenu = m.end(), cr[m.end() : fin]
        deja: SectionCR | None = sections.get(nom)
        if deja is None:
            sections[nom] = SectionCR(nom, debut, contenu)
        else:
            sections[nom] = SectionCR(nom, deja.debut, f"{deja.texte}\n{contenu}")
    return sections


def _corps_hors_conclusion(sections: dict[str, SectionCR]) -> str:
    """Texte de toutes les sections sauf la conclusion."""
    return "\n".join(s.texte for nom, s in sections.items() if nom != "conclusion")


def _texte_microscopique(sections: dict[str, SectionCR]) -> str:
    """Sections ou une lesion doit avoir ete decrite avant d'etre conclue."""
    noms: tuple[str, ...] = ("microscopie", "immunohistochimie", "extemporane")
    return "\n".join(sections[n].texte for n in noms if n in sections)


# ---------------------------------------------------------------------------
# Utilitaires de comptage
# ---------------------------------------------------------------------------


def _valeur_entiere(texte: str) -> int | None:
    """Convertit un nombre ecrit en chiffres OU en toutes lettres en entier."""
    brut: str = texte.strip()
    if brut.isdigit():
        return int(brut)
    # Les fenetres glissantes de reports.numbers renvoient aussi les composants
    # d'une expression ("dix-huit" -> 18, 10, 8) : la plus grande valeur est
    # celle de l'expression complete, les autres n'en sont que des morceaux.
    formes: set[str] = spelled_numbers_to_digits(brut)
    return max(int(v) for v in formes) if formes else None


def _empan_depuis(cr: str, motif: re.Pattern[str], depuis: int) -> Empan | None:
    """Premiere occurrence du motif dans le CR a partir d'un offset donne."""
    m: re.Match[str] | None = motif.search(cr, depuis)
    return Empan(m.start(), m.end(), m.group(0)) if m else None


_MESURE_RE: re.Pattern[str] = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm|millim[eè]tres?|centim[eè]tres?)\b", re.IGNORECASE
)


def _mesures_mm(texte: str) -> list[float]:
    """Toutes les mesures du texte, ramenees au millimetre."""
    valeurs: list[float] = []
    for m in _MESURE_RE.finditer(texte):
        nombre: float = float(m.group(1).replace(",", "."))
        valeurs.append(nombre * 10 if m.group(2).lower().startswith("c") else nombre)
    return valeurs


def _mm(valeur: float) -> str:
    """Affiche une mesure sans decimale superflue."""
    return f"{valeur:.0f}" if valeur == int(valeur) else f"{valeur:.1f}"


#: negation.py ne connait que les formes NON elidees ("absence de") et une
#: poignee de tournures. Les CR ecrivent aussi "absence d'atypie" (apostrophe
#: droite ou typographique), "aucun signe de", "on n'observe jamais". Sans ces
#: variantes, une lesion NIEE serait lue comme affirmee — c'est exactement ce
#: qui produisait des alertes sur des lesions benignes lors de l'audit corpus.
_MARQUEURS_NEGATION: tuple[str, ...] = NEGATION_MARKERS + (
    "absence d'", "absence d’", "pas d'", "pas d’",
    "ne montre pas d'", "ne montre pas d’",
    "ne trouve pas d'", "ne trouve pas d’",
    "indemne d'", "indemne d’", "ni d'", "ni d’",
    "aucun ", "aucune ", "n'observe pas", "n’observe pas",
    "n'observe jamais", "n’observe jamais", "ne presente pas",
    "ne comporte pas", "il n'existe pas", "il n’existe pas",
)


def _masquer_negations(texte_normalise: str) -> str:
    """Masque les clauses niees, elisions comprises."""
    return mask_negations(texte_normalise, _MARQUEURS_NEGATION)


def _texte_affirme(texte: str) -> str:
    """Texte normalise dont les clauses niees sont masquees.

    Une lesion enoncee sous negation ("absence de carcinome") ne doit jamais
    declencher une regle qui suppose la lesion presente.
    """
    return _masquer_negations(normaliser(texte))


def _clauses_niees(texte: str) -> list[str]:
    """Clauses placees sous negation, extraites via le masque de negation.py.

    Le masque remplace chaque clause niee par des espaces : les longues plages
    d'espaces du masque reperent donc exactement les clauses niees.
    """
    norme: str = normaliser(texte)
    masque: str = _masquer_negations(norme)
    clauses: list[str] = []
    for m in re.finditer(r" {2,}", masque):
        extrait: str = norme[m.start() : m.end()].strip()
        if extrait:
            clauses.append(extrait)
    return clauses


# ---------------------------------------------------------------------------
# C1 — numerotation des blocs
# ---------------------------------------------------------------------------

_BLOCS_RE: re.Pattern[str] = re.compile(
    r"\bblocs?\s*(?:n[°o]s?\s*)?(\d+(?:\s*(?:,|et|a|à|-|/)\s*\d+)*)", re.IGNORECASE
)

_SECTION_NUMEROTEE_RE: re.Pattern[str] = re.compile(
    r"^[ \t]*(\d{1,2})\s*[\).]\s+\S", re.MULTILINE
)


def _numeros_dans_enumeration(groupe: str) -> list[int]:
    """Developpe une enumeration de blocs ("1 a 6", "1, 2 et 5") en entiers."""
    numeros: list[int] = []
    for partie in re.split(r"\s*(?:,|et)\s*", groupe):
        bornes: list[int] = [int(n) for n in re.findall(r"\d+", partie)]
        # Deux nombres dans un meme segment = un intervalle ("1 a 6", "1-6").
        if len(bornes) >= 2:
            numeros.extend(range(min(bornes), max(bornes) + 1))
        else:
            numeros.extend(bornes)
    return numeros


def _numeros_de_blocs(texte: str) -> list[int]:
    """Tous les numeros de blocs cites dans le texte."""
    numeros: list[int] = []
    for m in _BLOCS_RE.finditer(texte):
        numeros.extend(_numeros_dans_enumeration(m.group(1)))
    return numeros


def regle_c1_blocs_continus(cr: str) -> AlerteDocument | None:
    """C1 — la numerotation des blocs ne saute aucun numero."""
    numeros: list[int] = sorted(set(_numeros_de_blocs(cr)))
    # Abstention si la numerotation ne demarre pas a 1 : le CR peut porter sur
    # des blocs complementaires realises pour un dossier anterieur.
    if len(numeros) < 2 or numeros[0] != 1:
        return None
    manquants: list[int] = [n for n in range(1, numeros[-1] + 1) if n not in numeros]
    if not manquants:
        return None
    liste: str = ", ".join(str(n) for n in manquants)
    return AlerteDocument(
        "C1",
        f"Numerotation des blocs discontinue : le CR cite des blocs jusqu'au "
        f"numero {numeros[-1]} mais le(s) bloc(s) {liste} n'apparaissent nulle part.",
    )


def _blocs_par_prelevement(cr: str) -> dict[int, set[int]]:
    """Numeros de blocs cites sous chaque prelevement numerote."""
    reperes: list[re.Match[str]] = list(_SECTION_NUMEROTEE_RE.finditer(cr))
    par_prelevement: dict[int, set[int]] = {}
    for i, m in enumerate(reperes):
        fin: int = reperes[i + 1].start() if i + 1 < len(reperes) else len(cr)
        numero: int = int(m.group(1))
        blocs: set[int] = set(_numeros_de_blocs(cr[m.start() : fin]))
        par_prelevement.setdefault(numero, set()).update(blocs)
    return par_prelevement


def regle_c1_blocs_uniques(cr: str) -> AlerteDocument | None:
    """C1 — un meme bloc n'est pas attribue a deux prelevements differents."""
    par_prelevement: dict[int, set[int]] = _blocs_par_prelevement(cr)
    if len(par_prelevement) < 2:
        return None
    proprietaire: dict[int, int] = {}
    for numero, blocs in sorted(par_prelevement.items()):
        for bloc in sorted(blocs):
            if bloc in proprietaire:
                return AlerteDocument(
                    "C1",
                    f"Le bloc {bloc} est rattache au prelevement "
                    f"{proprietaire[bloc]} puis au prelevement {numero} : une "
                    f"meme numerotation de bloc designe deux prelevements.",
                )
            proprietaire[bloc] = numero
    return None


# ---------------------------------------------------------------------------
# C2 — prelevements annonces / decrits
# ---------------------------------------------------------------------------

_PRELEVEMENTS_ANNONCES_RE: re.Pattern[str] = re.compile(
    r"\b([\w'-]+)\s+(?:pr[ée]l[èe]vements|pots|flacons|conteneurs)\b", re.IGNORECASE
)


def _nombre_de_prelevements_annonce(texte: str) -> int | None:
    """Nombre de prelevements annonce, seulement s'il est enonce sans ambiguite."""
    valeurs: set[int] = set()
    for m in _PRELEVEMENTS_ANNONCES_RE.finditer(texte):
        valeur: int | None = _valeur_entiere(m.group(1))
        if valeur is not None:
            valeurs.add(valeur)
    # Deux annonces divergentes : on ne sait pas laquelle fait foi, on s'abstient.
    return valeurs.pop() if len(valeurs) == 1 else None


def regle_c2_nombre_de_prelevements(
    cr: str, transcription: str = ""
) -> AlerteDocument | None:
    """C2 — le nombre annonce egale le nombre de sections numerotees."""
    annonce: int | None = _nombre_de_prelevements_annonce(cr)
    source: str = "le compte rendu"
    # La dictee n'est consultee qu'en repli : le CR fait foi quand il annonce.
    if annonce is None and transcription:
        annonce = _nombre_de_prelevements_annonce(transcription)
        source = "la dictee"
    numerotes: set[int] = {
        int(m.group(1)) for m in _SECTION_NUMEROTEE_RE.finditer(cr)
    }
    if annonce is None or not numerotes or annonce == len(numerotes):
        return None
    return AlerteDocument(
        "C2",
        f"{annonce} prelevements annonces dans {source}, "
        f"{len(numerotes)} sections numerotees decrites dans le compte rendu.",
    )


# ---------------------------------------------------------------------------
# C3 / C4 / C16 — comptages ganglionnaires
# ---------------------------------------------------------------------------

_STATION_PUIS_NOMBRE_RE: re.Pattern[str] = re.compile(
    r"\b(?:station|groupe|secteur|barrette)\s*(?:n[°o]\s*)?([\w/]+)\s*"
    r"[:=\-–]?\s*([\w-]+)\s*ganglions?",
    re.IGNORECASE,
)

# La preposition est obligatoire : sans elle, "5 ganglions ; station 7" serait
# lu comme "station 7 = 5 ganglions" et fausserait la somme.
_NOMBRE_PUIS_STATION_RE: re.Pattern[str] = re.compile(
    r"\b([\w-]+)\s+ganglions?\s+(?:en|dans|de|du|au niveau de|issus de)\s+"
    r"(?:la\s+)?(?:station|groupe|secteur|barrette)\s*(?:n[°o]\s*)?([\w/]+)",
    re.IGNORECASE,
)

_TOTAL_GANGLIONS_RE: re.Pattern[str] = re.compile(
    r"(?:au\s+total|total\s*(?:de)?)\s*[:=\-]?\s*(\d+)\s*ganglions?"
    r"|(\d+)\s*ganglions?\s+(?:au\s+total|examin[ée]s?|analys[ée]s?|isol[ée]s?"
    r"|pr[ée]lev[ée]s?|identifi[ée]s?|diss[ée]qu[ée]s?)",
    re.IGNORECASE,
)

# (motif, index du groupe "envahis", index du groupe "examines")
_PAIRES_GANGLIONNAIRES: tuple[tuple[re.Pattern[str], int, int], ...] = (
    (
        re.compile(
            r"(\d+)\s*ganglions?\s+(?:m[ée]tastatiques?|envahis?|positifs?|atteints?)"
            r"\s+(?:sur|/)\s*(\d+)",
            re.IGNORECASE,
        ),
        1,
        2,
    ),
    (
        re.compile(
            r"(\d+)\s+(?:m[ée]tastatiques?|envahis?|positifs?|atteints?)\s+(?:sur|/)"
            r"\s*(\d+)\s*(?:ganglions?\s*)?(?:examin[ée]s?|analys[ée]s?|pr[ée]lev[ée]s?)",
            re.IGNORECASE,
        ),
        1,
        2,
    ),
    (
        re.compile(
            r"(\d+)\s*ganglions?\s+(?:examin[ée]s?|analys[ée]s?|pr[ée]lev[ée]s?"
            r"|isol[ée]s?)[^.\n]{0,20}?\bdont\b\s*(\d+)",
            re.IGNORECASE,
        ),
        2,
        1,
    ),
    (re.compile(r"\bpN\d[a-c]?\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", re.IGNORECASE), 1, 2),
    (re.compile(r"(\d+)\s*/\s*(\d+)\s+ganglions?\b", re.IGNORECASE), 1, 2),
)


def _ganglions_par_station(cr: str) -> dict[str, int] | None:
    """Compte de ganglions par station, ou None si l'enumeration est ambigue."""
    stations: dict[str, int] = {}
    paires: list[tuple[str, str]] = [
        (m.group(1), m.group(2)) for m in _STATION_PUIS_NOMBRE_RE.finditer(cr)
    ]
    paires += [
        (m.group(2), m.group(1)) for m in _NOMBRE_PUIS_STATION_RE.finditer(cr)
    ]
    for libelle, compte in paires:
        valeur: int | None = _valeur_entiere(compte)
        cle: str = normaliser(libelle)
        # Un compte illisible ou une station comptee deux fois differemment
        # rendrait la somme fausse : mieux vaut ne rien dire.
        if valeur is None or stations.get(cle, valeur) != valeur:
            return None
        stations[cle] = valeur
    return stations


def _totaux_ganglions(cr: str) -> set[int]:
    """Tous les totaux ganglionnaires annonces dans le CR."""
    totaux: set[int] = set()
    for m in _TOTAL_GANGLIONS_RE.finditer(cr):
        totaux.add(int(m.group(1) or m.group(2)))
    return totaux


def _paires_ganglionnaires(cr: str) -> list[tuple[int, int, Empan]]:
    """Couples (envahis, examines) explicitement rapportes dans le CR."""
    paires: list[tuple[int, int, Empan]] = []
    for motif, i_envahis, i_examines in _PAIRES_GANGLIONNAIRES:
        for m in motif.finditer(cr):
            paires.append(
                (
                    int(m.group(i_envahis)),
                    int(m.group(i_examines)),
                    Empan(m.start(), m.end(), m.group(0)),
                )
            )
    return paires


def regle_c3_somme_des_ganglions(cr: str) -> AlerteDocument | None:
    """C3 — la somme des ganglions par station egale le total annonce."""
    stations: dict[str, int] | None = _ganglions_par_station(cr)
    totaux: set[int] = _totaux_ganglions(cr)
    # Une seule station ne constitue pas une enumeration ; plusieurs totaux
    # divergents ne permettent pas de savoir a quoi comparer la somme.
    if stations is None or len(stations) < 2 or len(totaux) != 1:
        return None
    total: int = totaux.pop()
    somme: int = sum(stations.values())
    if somme == total:
        return None
    detail: str = " + ".join(str(v) for v in stations.values())
    return AlerteDocument(
        "C3",
        f"La somme des ganglions par station ({detail} = {somme}) ne correspond "
        f"pas au total annonce ({total}).",
    )


def regle_c4_envahis_inferieur_examines(cr: str) -> AlerteDocument | None:
    """C4 — le nombre de ganglions envahis ne depasse pas celui des examines."""
    for envahis, examines, empan in _paires_ganglionnaires(cr):
        if envahis > examines:
            return AlerteDocument(
                "C4",
                f"{envahis} ganglions envahis rapportes pour {examines} examines : "
                f"le nombre d'envahis ne peut pas depasser celui des examines.",
                empan,
            )
    return None


# ---------------------------------------------------------------------------
# C5 — fragments macroscopie / microscopie
# ---------------------------------------------------------------------------

_FRAGMENTS_RE: re.Pattern[str] = re.compile(r"\b([\w'-]+)\s+fragments?\b", re.IGNORECASE)


def _compte_de_fragments(texte: str) -> int | None:
    """Nombre de fragments, seulement si la section n'en annonce qu'un seul."""
    valeurs: set[int] = set()
    for m in _FRAGMENTS_RE.finditer(texte):
        valeur: int | None = _valeur_entiere(m.group(1))
        if valeur is not None:
            valeurs.add(valeur)
    return valeurs.pop() if len(valeurs) == 1 else None


def regle_c5_fragments(cr: str) -> AlerteDocument | None:
    """C5 — autant de fragments decrits en microscopie qu'annonces en macroscopie."""
    sections: dict[str, SectionCR] = decouper_sections(cr)
    if "macroscopie" not in sections or "microscopie" not in sections:
        return None
    macro: int | None = _compte_de_fragments(sections["macroscopie"].texte)
    micro: int | None = _compte_de_fragments(sections["microscopie"].texte)
    if macro is None or micro is None or macro == micro:
        return None
    return AlerteDocument(
        "C5",
        f"{macro} fragments annonces en macroscopie, {micro} decrits en microscopie.",
    )


# ---------------------------------------------------------------------------
# C6 / C7 / C8 — mesures
# ---------------------------------------------------------------------------

_TAILLE_CONCLUSION_RE: re.Pattern[str] = re.compile(
    r"taille\s*(?:tumorale|l[ée]sionnelle|de\s+la\s+l[ée]sion)?\s*[:=]\s*"
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm)\b"
    r"|(\d+(?:[.,]\d+)?)\s*(mm|cm)\s+de\s+(?:plus\s+)?grand\s+axe",
    re.IGNORECASE,
)

_DIMENSION_MULTI_RE: re.Pattern[str] = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm)?\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?"
    r"(?:\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?)?",
    re.IGNORECASE,
)

#: Vocabulaire ferme des pieces d'exerese : elles se mesurent sur trois axes.
_PIECES_EXERESE: tuple[str, ...] = (
    "piece", "lobectomie", "pneumonectomie", "segmentectomie", "mastectomie",
    "tumorectomie", "zonectomie", "colectomie", "hemicolectomie", "sigmoidectomie",
    "gastrectomie", "oesophagectomie", "hysterectomie", "nephrectomie",
    "prostatectomie", "cystectomie", "thyroidectomie", "hepatectomie",
    "duodenopancreatectomie", "amputation", "exerese", "resection",
)

#: Justifications admises pour une dimension a deux axes : le troisieme axe est
#: donne separement ("fuseau cutane de 30 x 12 mm, epaisseur 8 mm").
_JUSTIFICATIONS_DIMENSION: tuple[str, ...] = ("epaisseur", "hauteur", "profondeur")


def _taille_annoncee(texte: str) -> float | None:
    """Taille tumorale explicitement annoncee, en millimetres."""
    m: re.Match[str] | None = _TAILLE_CONCLUSION_RE.search(texte)
    if m is None:
        return None
    nombre: str = m.group(1) or m.group(3)
    unite: str = (m.group(2) or m.group(4)).lower()
    return float(nombre.replace(",", ".")) * (10 if unite == "cm" else 1)


def regle_c6_taille_conclusion(cr: str) -> AlerteDocument | None:
    """C6 — la taille conclue ne depasse pas la plus grande dimension mesuree."""
    sections: dict[str, SectionCR] = decouper_sections(cr)
    if "conclusion" not in sections or "macroscopie" not in sections:
        return None
    taille: float | None = _taille_annoncee(sections["conclusion"].texte)
    mesures: list[float] = _mesures_mm(sections["macroscopie"].texte)
    if taille is None or not mesures:
        return None
    plus_grande: float = max(mesures)
    # Une taille INFERIEURE est legitime (mesure sur lame, tumeur residuelle) :
    # seule une taille superieure a tout ce qui a ete mesure est incoherente.
    if taille <= plus_grande:
        return None
    micro: str = _texte_microscopique(sections)
    if any(abs(v - taille) < 0.01 for v in _mesures_mm(micro)):
        return None
    return AlerteDocument(
        "C6",
        f"La taille annoncee en conclusion ({_mm(taille)} mm) depasse la plus "
        f"grande dimension mesuree en macroscopie ({_mm(plus_grande)} mm) et "
        f"n'est reprise nulle part ailleurs.",
    )


def regle_c7_unites_homogenes(cr: str) -> AlerteDocument | None:
    """C7 — une meme dimension ne melange pas les millimetres et les centimetres.

    La regle du catalogue vise le paragraphe ; appliquee telle quelle elle
    signalerait tous les CR normaux (la piece se mesure en cm, la lesion en mm).
    On la restreint donc a l'invariant indiscutable : les axes d'UNE MEME
    dimension doivent partager leur unite.
    """
    for m in _DIMENSION_MULTI_RE.finditer(cr):
        unites: set[str] = {
            g.lower() for g in (m.group(2), m.group(4), m.group(6)) if g
        }
        if len(unites) > 1:
            return AlerteDocument(
                "C7",
                f"La dimension '{m.group(0).strip()}' melange "
                f"{' et '.join(sorted(unites))} sur ses axes.",
                Empan(m.start(), m.end(), m.group(0)),
            )
    return None


def regle_c8_trois_axes(cr: str) -> AlerteDocument | None:
    """C8 — une piece d'exerese est mesuree sur trois axes, ou se justifie."""
    sections: dict[str, SectionCR] = decouper_sections(cr)
    if "macroscopie" not in sections:
        return None
    macro: str = sections["macroscopie"].texte
    norme: str = normaliser(macro)
    for m in _DIMENSION_MULTI_RE.finditer(macro):
        if m.group(5) is not None:
            continue
        # La dimension doit se rattacher a une piece d'exerese nommee juste avant :
        # une lesion ou un fragment se mesure legitimement sur moins d'axes.
        amont: str = norme[max(0, m.start() - 80) : m.start()]
        if not any(p in amont for p in _PIECES_EXERESE):
            continue
        aval: str = norme[m.end() : m.end() + 80]
        if any(j in aval for j in _JUSTIFICATIONS_DIMENSION):
            continue
        return AlerteDocument(
            "C8",
            f"La piece est mesuree sur deux axes seulement "
            f"('{m.group(0).strip()}') alors qu'une piece d'exerese en compte trois.",
            Empan(m.start(), m.end(), m.group(0)),
        )
    return None


# ---------------------------------------------------------------------------
# C9 / C15 — marges d'exerese
# ---------------------------------------------------------------------------

#: Racines de malignite (texte deja normalise, negations masquees). "blastom"
#: est exclu : la plupart des blastomes nommes en anatomie pathologique sont
#: benins (myofibroblastome, chondroblastome, lipoblastome), les malins sont
#: donc listes un par un.
_RACINES_MALIGNES: tuple[str, ...] = (
    "carcinom", "sarcom", "melanom", "lymphom", "seminom", "mesotheliom",
    "myelom", "neuroblastom", "glioblastom", "medulloblastom", "nephroblastom",
    "hepatoblastom", "retinoblastom", "malign", "malin", "metastas",
)

#: Entites BENIGNES dont le nom contient une racine maligne : le cystadeno-
#: lymphome (tumeur de Warthin) n'est pas un lymphome. Retirees du texte avant
#: la recherche, sans quoi elles declenchent C9 et C15 a tort.
_COMPOSES_BENINS: tuple[str, ...] = ("cystadenolymphome", "adenolymphome")

_TERMES_MARGE: tuple[str, ...] = (
    "marge", "limite d'exerese", "limites d'exerese", "limite de resection",
    "limites de resection", "recoupe", "berge", "tranche de section",
)

#: Formulation QUALITATIVE de marge, tres frequente en pratique francaise et
#: sans le mot "marge" : "l'exerese de la lesion est incomplete", "exerese in
#: sano". Sans elle, C9 signalait a tort une absence de limites.
_MARGE_QUALITATIVE_RE: re.Pattern[str] = re.compile(
    r"\bexerese\b[^.\n]{0,60}?\b(?:complete|incomplete|in sano|en zone saine"
    r"|passant au contact|au contact)"
)

#: Statuts qui rendent la distance sans objet (marge atteinte = distance nulle).
_MARGE_ATTEINTE: tuple[str, ...] = (
    "atteinte", "atteintes", "envahie", "envahies", "non saine", "non saines",
    "r1", "incomplete", "incompletes", "au contact",
)

#: Fenetre de rattachement d'une mesure a une mention de marge, en caracteres.
#: La distance qualifiant une marge est ecrite dans la MEME clause ("limites
#: saines, la plus proche a 6 mm", "a 6 mm de la recoupe") : une fenetre large
#: laisserait une mesure sans rapport (la taille de la piece) valider la marge.
_FENETRE_AVANT_MARGE: int = 60
_FENETRE_APRES_MARGE: int = 100


def _document_complet(cr: str) -> bool:
    """Vrai si le CR est un document structure et non un fragment de texte.

    Les regles qui signalent une ABSENCE (C9, C15, C16) ne concluent que sur un
    document complet : dans un fragment, ce qui manque figure peut-etre
    simplement dans une partie du compte rendu qu'on n'a pas sous les yeux.
    """
    return "macroscopie" in decouper_sections(cr)


def _lesion_maligne(cr: str) -> bool:
    """Vrai si le CR affirme une lesion maligne (hors clause niee)."""
    affirme: str = _texte_affirme(cr)
    for compose in _COMPOSES_BENINS:
        affirme = affirme.replace(compose, " ")
    return any(racine in affirme for racine in _RACINES_MALIGNES)


def _piece_exerese(cr: str) -> bool:
    """Vrai si le CR porte sur une piece d'exerese et non sur une biopsie."""
    norme: str = normaliser(cr)
    return any(piece in norme for piece in _PIECES_EXERESE)


def _positions_de_marge(norme: str) -> list[int]:
    """Offsets des mentions de marge dans le texte normalise."""
    positions: list[int] = []
    for terme in _TERMES_MARGE:
        depuis: int = 0
        while (pos := norme.find(terme, depuis)) != -1:
            positions.append(pos)
            depuis = pos + len(terme)
    positions += [m.start() for m in _MARGE_QUALITATIVE_RE.finditer(norme)]
    return positions


def regle_c9_marges_presentes(cr: str) -> AlerteDocument | None:
    """C9 — une exerese de lesion maligne mentionne ses limites."""
    if not _document_complet(cr) or not _lesion_maligne(cr) or not _piece_exerese(cr):
        return None
    if _positions_de_marge(normaliser(cr)):
        return None
    return AlerteDocument(
        "C9",
        "Lesion maligne sur piece d'exerese : aucune limite d'exerese n'est "
        "mentionnee dans le document.",
    )


def regle_c15_marges_mesurees(cr: str) -> AlerteDocument | None:
    """C15 — les limites d'une exerese maligne sont chiffrees ou dites atteintes."""
    if not _document_complet(cr) or not _lesion_maligne(cr) or not _piece_exerese(cr):
        return None
    norme: str = normaliser(cr)
    positions: list[int] = _positions_de_marge(norme)
    if not positions:
        return None
    for pos in positions:
        fenetre: str = norme[
            max(0, pos - _FENETRE_AVANT_MARGE) : pos + _FENETRE_APRES_MARGE
        ]
        if _MESURE_RE.search(fenetre) or any(t in fenetre for t in _MARGE_ATTEINTE):
            return None
    return AlerteDocument(
        "C15",
        "Les limites d'exerese sont mentionnees sans distance chiffree ni statut "
        "d'atteinte, alors que le document decrit une exerese de lesion maligne.",
    )


# ---------------------------------------------------------------------------
# C10 / C11 — microscopie vers conclusion
# ---------------------------------------------------------------------------

#: Racines des entites malignes nommables en conclusion. Une racine plutot
#: qu'un mot entier, pour qu'un "adenocarcinome" soit couvert par "carcinom".
_RACINES_TUMORALES: tuple[str, ...] = ("carcinom", "sarcom", "melanom", "lymphom")

#: Marqueurs a libelle non ambigu (les sigles de deux lettres type RE/RP sont
#: exclus : ils matcheraient du texte ordinaire).
_MARQUEURS_IHC: tuple[re.Pattern[str], ...] = tuple(
    re.compile(motif, re.IGNORECASE)
    for motif in (
        r"TTF-?\s?1\b", r"\bp40\b", r"\bp63\b", r"\bp53\b", r"\bp16\b",
        r"\bCK\s?5/6\b", r"\bCK\s?7\b", r"\bCK\s?20\b", r"\bCK\s?19\b",
        r"\bNapsine?\s?A\b", r"\bALK\b", r"\bROS-?1\b", r"\bPD-?L1\b",
        r"\bEGFR\b", r"\bHER-?2\b", r"\bKi-?67\b", r"\bCDX-?2\b",
        r"\bSATB-?2\b", r"\bGATA-?3\b", r"\bPAX-?8\b", r"\bWT-?1\b",
        r"\bS-?100\b", r"\bSOX-?10\b", r"\bHMB-?45\b", r"\bMelan-?A\b",
        r"\bMLH-?1\b", r"\bMSH-?2\b", r"\bMSH-?6\b", r"\bPMS-?2\b",
        r"\bCD\s?3\b", r"\bCD\s?5\b", r"\bCD\s?10\b", r"\bCD\s?20\b",
        r"\bCD\s?23\b", r"\bCD\s?30\b", r"\bCD\s?34\b", r"\bCD\s?45\b",
        r"\bCD\s?117\b", r"\bBCL-?2\b", r"\bBCL-?6\b", r"\bDOG-?1\b",
        r"\bINSM-?1\b", r"\bMUC-?2\b", r"\bGFAP\b", r"\bPSA\b", r"\bTdT\b",
        r"synaptophysine", r"chromogranine", r"calretinine", r"desmine",
        r"vimentine", r"cycline\s?D1",
    )
)


def regle_c10_lesion_conclue_decrite(cr: str) -> AlerteDocument | None:
    """C10 — la microscopie ne contredit pas la lesion affirmee en conclusion.

    La forme litterale de la regle (le mot de la conclusion doit figurer en
    microscopie) n'est PAS un invariant : une conclusion NOMME l'entite que la
    microscopie DECRIT ("adossements glandulaires cribriformes" ->
    "adenocarcinome"). Mesure faite sur 653 textes de praticien : 143
    divergences purement lexicales, toutes legitimes. On ne retient donc que la
    contradiction franche — la microscopie nie la malignite, la conclusion
    l'affirme — qui, elle, ne se produit dans aucun de ces 653 textes.
    """
    sections: dict[str, SectionCR] = decouper_sections(cr)
    micro: str = _texte_microscopique(sections)
    if "conclusion" not in sections or not micro.strip():
        return None
    conclusion_affirmee: str = _texte_affirme(sections["conclusion"].texte)
    racine: str | None = next(
        (r for r in _RACINES_TUMORALES if r in conclusion_affirmee), None
    )
    if racine is None:
        return None
    if any(r in _texte_affirme(micro) for r in _RACINES_TUMORALES):
        return None
    if not any("malign" in clause for clause in _clauses_niees(micro)):
        return None
    return AlerteDocument(
        "C10",
        f"La conclusion affirme une lesion en '{racine}...' alors que la section "
        f"microscopique ne decrit aucune lesion maligne et nie explicitement la "
        f"malignite.",
        _empan_depuis(
            cr, re.compile(racine, re.IGNORECASE), sections["conclusion"].debut
        ),
    )


def _ihc_documentee(sections: dict[str, SectionCR]) -> bool:
    """Vrai si le corps du CR documente une etude immunohistochimique.

    Sans aucune IHC documentee, un marqueur cite en conclusion releve de la
    fidelite a la dictee (couche 1), pas d'une incoherence entre deux parties
    du document : il n'y a pas de tableau IHC auquel le confronter.
    """
    if "immunohistochimie" in sections:
        return True
    corps: str = _corps_hors_conclusion(sections)
    return any(motif.search(corps) for motif in _MARQUEURS_IHC)


def regle_c11_marqueur_conclu_documente(cr: str) -> AlerteDocument | None:
    """C11 — tout marqueur cite en conclusion figure dans le corps du CR."""
    sections: dict[str, SectionCR] = decouper_sections(cr)
    if "conclusion" not in sections or not _ihc_documentee(sections):
        return None
    corps: str = _corps_hors_conclusion(sections)
    for motif in _MARQUEURS_IHC:
        m: re.Match[str] | None = motif.search(sections["conclusion"].texte)
        if m is None or motif.search(corps):
            continue
        return AlerteDocument(
            "C11",
            f"Le marqueur '{m.group(0)}' est cite en conclusion sans figurer "
            f"dans le corps du compte rendu.",
            _empan_depuis(cr, motif, sections["conclusion"].debut),
        )
    return None


# ---------------------------------------------------------------------------
# C12 — negations inversees
# ---------------------------------------------------------------------------

#: Objets sur lesquels porte habituellement une negation diagnostique.
_OBJETS_DE_NEGATION: tuple[str, ...] = (
    "cellule", "cellules", "signe", "signes", "critere", "criteres",
    "caractere", "caracteres", "element", "elements", "foyer", "foyers",
)

_TERMES_DE_NORMALITE_RE: re.Pattern[str] = re.compile(
    r"\b(?:normal|normale|normaux|normales|benin|benins|benigne|benignes|benignite)\b"
)

_NEGATIONS_DE_MALIGNITE: tuple[str, ...] = (
    "malignite", "cellule maligne", "cellules malignes", "lesion maligne",
    "signe de malignite", "caractere malin",
)


def regle_c12_negation_de_normalite(cr: str) -> AlerteDocument | None:
    """C12 — une negation ne porte pas sur un terme de normalite.

    "pas de cellule normale" est l'inversion classique de "pas de cellule
    anormale" : la regle ne dit pas laquelle est vraie, elle signale que la
    negation porte sur la normalite, ce qui inverse le sens du constat.
    """
    for clause in _clauses_niees(cr):
        if not any(objet in clause for objet in _OBJETS_DE_NEGATION):
            continue
        m: re.Match[str] | None = _TERMES_DE_NORMALITE_RE.search(clause)
        if m is None:
            continue
        return AlerteDocument(
            "C12",
            f"La negation '{clause}' porte sur un terme de normalite : "
            f"verifier qu'il ne s'agit pas d'une inversion (la formulation "
            f"attendue porte sur l'anormalite).",
        )
    return None


def regle_c12_negation_contredite(cr: str) -> AlerteDocument | None:
    """C12 — une phrase n'affirme pas une malignite qu'elle nie par ailleurs."""
    for phrase in re.split(r"[.\n]", cr):
        norme: str = normaliser(phrase)
        nie: str = _masquer_negations(norme)
        # La negation de malignite doit avoir ete MASQUEE (donc etre reellement
        # sous negation), et la partie affirmee contenir malgre tout une lesion
        # maligne : les deux dans la MEME phrase.
        if not any(t in norme and t not in nie for t in _NEGATIONS_DE_MALIGNITE):
            continue
        racine: str | None = next((r for r in _RACINES_TUMORALES if r in nie), None)
        if racine is None:
            continue
        return AlerteDocument(
            "C12",
            f"La meme phrase affirme une lesion en '{racine}...' et nie la "
            f"malignite : '{phrase.strip()}'.",
        )
    return None


# ---------------------------------------------------------------------------
# C13 / C14 — lateralite et organe
# ---------------------------------------------------------------------------

_LATERALITES: dict[str, re.Pattern[str]] = {
    "droite": re.compile(r"\bdroits?\b|\bdroites?\b", re.IGNORECASE),
    "gauche": re.compile(r"\bgauches?\b", re.IGNORECASE),
    "bilaterale": re.compile(r"\bbilat[ée]rale?s?\b|\bbilat[ée]raux\b", re.IGNORECASE),
}

#: Paires de sections dont la lateralite doit concorder. Contrairement a
#: l'organe, un cote n'a pas de raison de changer entre le titre, la
#: macroscopie et la conclusion : les trois paires sont donc comparees.
_SECTIONS_COMPAREES: tuple[tuple[str, str], ...] = (
    ("titre", "macroscopie"),
    ("titre", "conclusion"),
    ("macroscopie", "conclusion"),
)


def _lateralite_unique(texte: str) -> str | None:
    """Lateralite du texte, uniquement si elle est sans ambiguite.

    Un CR bilateral ou multi-prelevement cite les deux cotes legitimement : dans
    ce cas la section n'est pas comparable et la regle s'abstient.
    """
    trouvees: set[str] = {
        nom for nom, motif in _LATERALITES.items() if motif.search(texte)
    }
    return trouvees.pop() if len(trouvees) == 1 and "bilaterale" not in trouvees else None


def regle_c13_lateralite(cr: str) -> AlerteDocument | None:
    """C13 — lateralite identique entre titre, macroscopie et conclusion."""
    sections: dict[str, SectionCR] = decouper_sections(cr)
    lateralites: dict[str, str] = {}
    for nom in ("titre", "macroscopie", "conclusion"):
        if nom in sections:
            cote: str | None = _lateralite_unique(sections[nom].texte)
            if cote is not None:
                lateralites[nom] = cote
    for gauche, droite in _SECTIONS_COMPAREES:
        if gauche not in lateralites or droite not in lateralites:
            continue
        if lateralites[gauche] == lateralites[droite]:
            continue
        return AlerteDocument(
            "C13",
            f"Lateralite divergente : {gauche} indique '{lateralites[gauche]}', "
            f"{droite} indique '{lateralites[droite]}'.",
            _empan_depuis(
                cr, _LATERALITES[lateralites[droite]], sections[droite].debut
            ),
        )
    return None


#: Familles lesionnelles de templates_organes qui ne designent pas un organe :
#: les confronter a un organe produirait une divergence artificielle ("lipome
#: du colon" ferait diverger colon_rectum et sarcome).
_FAMILLES_NON_ORGANES: frozenset[str] = frozenset({"lymphome", "sarcome", "melanome"})


#: "au sein d'un tissu inflammatoire" est une locution ("a l'interieur de") que
#: la detection d'organes prend pour une mammaire. On la neutralise en amont.
_LOCUTION_AU_SEIN_RE: re.Pattern[str] = re.compile(r"\bau\s+sein\s+d", re.IGNORECASE)


def _organes_de(texte: str) -> set[str]:
    """Organes detectes dans un texte, familles lesionnelles exclues."""
    sans_locution: str = _LOCUTION_AU_SEIN_RE.sub("dans ", texte)
    return {t.organe for t in detect_organs(sans_locution)} - _FAMILLES_NON_ORGANES


def _alerte_organe(source: str, organes_source: set[str], reference: str,
                   organes_reference: set[str]) -> AlerteDocument:
    """Formule la divergence d'organe entre deux parties du document."""
    return AlerteDocument(
        "C14",
        f"Organe divergent : {source} designe "
        f"{', '.join(sorted(organes_source))}, {reference} designe "
        f"{', '.join(sorted(organes_reference))}, sans organe commun.",
    )


def regle_c14_organe(cr: str) -> AlerteDocument | None:
    """C14 — organe identique entre titre, macroscopie et conclusion.

    Deux comparaisons distinctes, parce que les sections n'ont pas le meme role.
    Le titre et la macroscopie designent tous deux le PRELEVEMENT : ils doivent
    partager un organe. La conclusion, elle, nomme la LESION et peut legitimement
    citer un tissu voisin ("metaplasie gastrique" sur une biopsie oesophagienne,
    "cholangiocarcinome" sur un foie) : elle n'est fautive que si elle introduit
    un organe que le reste du document ne mentionne nulle part.
    """
    sections: dict[str, SectionCR] = decouper_sections(cr)
    titre: set[str] = _organes_de(sections["titre"].texte) if "titre" in sections else set()
    macro: set[str] = (
        _organes_de(sections["macroscopie"].texte) if "macroscopie" in sections else set()
    )
    if titre and macro and not titre & macro:
        return _alerte_organe("le titre", titre, "la macroscopie", macro)
    if "conclusion" not in sections:
        return None
    conclusion: set[str] = _organes_de(sections["conclusion"].texte)
    ailleurs: set[str] = _organes_de(_corps_hors_conclusion(sections))
    if conclusion and ailleurs and not conclusion & ailleurs:
        return _alerte_organe("la conclusion", conclusion, "le reste du CR", ailleurs)
    return None


# ---------------------------------------------------------------------------
# C16 — comptage obligatoire sur curage
# ---------------------------------------------------------------------------

_TERMES_CURAGE: tuple[str, ...] = (
    "curage", "lymphadenectomie", "ganglion sentinelle", "ganglions sentinelles",
    "picking ganglionnaire",
)

#: Formulations qui rapportent a elles seules l'absence d'envahissement.
_ABSENCE_EXPLICITE: tuple[str, ...] = (
    "aucun ganglion metastatique", "aucun ganglion envahi",
    "aucune metastase ganglionnaire", "ganglion indemne", "ganglions indemnes",
    "ganglions non metastatiques", "ganglions non envahis",
    "ganglions sans particularite",
)

#: Termes qui ne valent constat d'absence que sous negation ("pas de metastase
#: ganglionnaire") : affirmes, ils decrivent au contraire un envahissement.
_ABSENCE_SOUS_NEGATION: tuple[str, ...] = (
    "metastase ganglionnaire", "metastases ganglionnaires",
    "envahissement ganglionnaire", "effraction capsulaire",
)

_ENVAHIS_CHIFFRES_RE: re.Pattern[str] = re.compile(
    r"(\d+)\s*ganglions?\s+(?:envahis?|m[ée]tastatiques?|positifs?|atteints?)",
    re.IGNORECASE,
)


def _curage_present(cr: str) -> bool:
    """Vrai si le CR decrit un curage ou un ganglion sentinelle."""
    norme: str = normaliser(cr)
    return any(terme in norme for terme in _TERMES_CURAGE)


def regle_c16_ganglions_examines(cr: str) -> AlerteDocument | None:
    """C16 — un curage rapporte le nombre de ganglions examines."""
    if not _document_complet(cr) or not _curage_present(cr):
        return None
    if _totaux_ganglions(cr) or _paires_ganglionnaires(cr):
        return None
    return AlerteDocument(
        "C16",
        "Un curage ganglionnaire est decrit sans que le nombre de ganglions "
        "examines soit rapporte.",
    )


def _absence_envahissement_rapportee(cr: str) -> bool:
    """Vrai si le CR constate explicitement l'absence d'envahissement ganglionnaire."""
    norme: str = normaliser(cr)
    if any(formulation in norme for formulation in _ABSENCE_EXPLICITE):
        return True
    affirme: str = _masquer_negations(norme)
    return any(t in norme and t not in affirme for t in _ABSENCE_SOUS_NEGATION)


def regle_c16_ganglions_envahis(cr: str) -> AlerteDocument | None:
    """C16 — un curage rapporte le nombre de ganglions envahis (ou leur absence)."""
    if not _document_complet(cr) or not _curage_present(cr):
        return None
    if _paires_ganglionnaires(cr) or _ENVAHIS_CHIFFRES_RE.search(cr):
        return None
    if _absence_envahissement_rapportee(cr):
        return None
    return AlerteDocument(
        "C16",
        "Un curage ganglionnaire est decrit sans que le statut d'envahissement "
        "des ganglions soit rapporte.",
    )


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------


def verifier_coherence_document(
    cr: str, transcription: str = ""
) -> list[AlerteDocument]:
    """Assemble les alertes de coherence documentaire du catalogue C1 a C17.

    ``transcription`` n'est utilisee que par C2, en repli, quand le CR n'annonce
    lui-meme aucun nombre de prelevements.
    """
    if not cr.strip() or _REFUS_NON_MEDICAL in cr.lower():
        return []
    candidates: tuple[AlerteDocument | None, ...] = (
        regle_c1_blocs_continus(cr),
        regle_c1_blocs_uniques(cr),
        regle_c2_nombre_de_prelevements(cr, transcription),
        regle_c3_somme_des_ganglions(cr),
        regle_c4_envahis_inferieur_examines(cr),
        regle_c5_fragments(cr),
        regle_c6_taille_conclusion(cr),
        regle_c7_unites_homogenes(cr),
        regle_c8_trois_axes(cr),
        regle_c9_marges_presentes(cr),
        regle_c10_lesion_conclue_decrite(cr),
        regle_c11_marqueur_conclu_documente(cr),
        regle_c12_negation_de_normalite(cr),
        regle_c12_negation_contredite(cr),
        regle_c13_lateralite(cr),
        regle_c14_organe(cr),
        regle_c15_marges_mesurees(cr),
        regle_c16_ganglions_examines(cr),
        regle_c16_ganglions_envahis(cr),
    )
    return [alerte for alerte in candidates if alerte is not None]
