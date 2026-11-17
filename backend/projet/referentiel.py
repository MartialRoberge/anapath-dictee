"""Acces au referentiel metier pour le pipeline, avec repli gracieux.

Le pipeline interroge d'abord la base de connaissances v3 (``projet/kb.py``,
remplie par l'agent sources). Si une collection est vide, il se replie sur les
referentiels historiques du depot (``templates_organes.py``, detection
d'organes de ``reports/knowledge.py``, ``specimen_type.py``) et le DIT : chaque
repli est consigne (``replis``) et abaisse le niveau de service (N0 -> N3).

Aucune fonction de ce module ne leve d'exception vers l'orchestrateur : une
source manquante donne une valeur vide, jamais un arret.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from projet.contexte import detecter_contexte_lesionnel
from projet.kb import KB, get_kb
from projet.schemas import SourceRef
from projet.textes import contient_terme, extrait_court
from specimen_type import (
    DiagnosticContext,
    SpecimenType,
    champ_applicable,
    detecter_diagnostic_context,
    detecter_specimen_type,
)
from text_utils import normaliser

logger = logging.getLogger("marc.v3.referentiel")

# ---------------------------------------------------------------------------
# Sources internes (citees quand la base v3 n'a pas l'information)
# ---------------------------------------------------------------------------

SOURCES_INTERNES: dict[str, dict[str, Any]] = {
    "src:marc_templates_inca": {
        "id": "src:marc_templates_inca", "titre": "Templates organes MARC v2 (d'après INCa 2011)",
        "editeur": "MARC (dérivé)", "version": "v2", "url": None,
        "licence": "interne", "fiabilite": "C",
        "note": "Champs obligatoires repris des gabarits MARC v2, en attente de la base v3.",
        "titre_court": "Référentiel interne MARC (à valider)", "description": "Champs obligatoires par organe repris des gabarits MARC v2, inspirés des données minimales INCa 2011 mais non relus par un pathologiste tiers."
    },
    "src:marc_lexique_integre": {
        "id": "src:marc_lexique_integre", "titre": "Lexique phonétique intégré MARC (variantes STT observées v2)",
        "editeur": "MARC", "version": "v2", "url": None, "licence": "interne", "fiabilite": "C",
        "titre_court": "Lexique phonétique interne MARC (v2)", "description": "Variantes de transcription vocale observées dans MARC v2 : lexique interne, non publié."
    },
    "src:marc_heuristiques_unites": {
        "id": "src:marc_heuristiques_unites", "titre": "Plages de mesures plausibles (heuristiques à valider)",
        "editeur": "MARC", "version": "v3", "url": None, "licence": "interne", "fiabilite": "D",
        "note": "Heuristiques métier non sourcées ; INCa 2011 pour les unités usuelles (mm, cm pour le poumon).",
        "titre_court": "Plages de mesures plausibles · heuristiques MARC", "description": "Plages de mesures plausibles écrites par MARC : des heuristiques métier non sourcées, à valider."
    },
    "src:adicap_embarque": {
        "id": "src:adicap_embarque", "titre": "Thesaurus ADICAP (table officielle v5-04 + bible du laboratoire)",
        "editeur": "ADICAP / ANS", "version": "v5-04", "url": "https://smt.esante.gouv.fr/terminologie-adicap/",
        "licence": "Licence Ouverte", "fiabilite": "B",
        "titre_court": "ADICAP · Thésaurus embarqué dans MARC", "description": "Thésaurus ADICAP (table officielle v5-04 de l'ANS) complété par la bible du laboratoire."
    },
    "src:snomed_py_historique": {
        "id": "src:snomed_py_historique", "titre": "Table SNOMED CT historique MARC (non vérifiée contre une release)",
        "editeur": "MARC", "version": "v2", "url": None, "licence": "interne", "fiabilite": "D",
        "titre_court": "Correspondances SNOMED CT saisies à la main (à valider)", "description": "Table historique de correspondances SNOMED CT saisies par l'équipe MARC, non vérifiée contre une édition officielle."
    },
    "src:coherence_document": {
        "id": "src:coherence_document", "titre": "Règles de cohérence documentaire C1-C16 (MARC)",
        "editeur": "MARC", "version": "v2", "url": None, "licence": "interne", "fiabilite": "B",
        "titre_court": "Règles de cohérence documentaire · MARC", "description": "Règles de cohérence entre éléments d'un compte rendu (latéralité, mesures, négations) écrites par l'équipe MARC."
    },
    "src:garde_fous": {
        "id": "src:garde_fous", "titre": "Garde-fous déterministes MARC (chiffres, négations, périmètre biopsie)",
        "editeur": "MARC", "version": "v2", "url": None, "licence": "interne", "fiabilite": "B",
        "titre_court": "Garde-fous déterministes MARC", "description": "Contrôles automatiques de MARC sur les chiffres, les négations et le périmètre d'une biopsie."
    },
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Fiabilite = str  # "A" | "B" | "C" | "D"


@dataclass(slots=True)
class OrganeDetecte:
    id: str
    libelle: str
    debut: int | None
    fin: int | None
    confiance: float
    source: SourceRef
    #: identifiant historique (templates_organes / codification) pour les repli.
    id_historique: str


@dataclass(slots=True)
class ChampAttendu:
    id: str
    libelle: str
    obligatoire: bool
    section: str
    type: str = "texte"
    unite: str | None = None
    options: list[str] = field(default_factory=list)
    mots_cles: list[str] = field(default_factory=list)
    source: SourceRef | None = None
    fiabilite: Fiabilite = "C"
    confiance_source: float = 0.7
    organe_id: str = ""
    concept: str = ""
    tumoral: bool = False
    #: niveau d'exigence de la base : obligatoire_inca | obligatoire_local | recommande
    niveau: str = ""
    condition: str | None = None
    #: source INCa (fiche et item) quand l'exigence est reprise des donnees minimales INCa
    source_inca: SourceRef | None = None

    @property
    def source_exigence(self) -> SourceRef | None:
        """Source reelle de l'exigence : INCa quand elle y figure, sinon la source du champ."""
        return self.source_inca or self.source


@dataclass(slots=True)
class EntreeLexique:
    terme: str
    variantes: list[tuple[str, float]]  # (forme, confiance)
    contexte_requis: list[str]
    source: SourceRef
    organes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Plage:
    min_mm: float
    max_mm: float
    source: SourceRef
    libelle: str
    #: contexte lisible pour l'affichage : « biopsie bronchique », « tumeur (biopsie) »...
    contexte: str = ""
    #: la plage est une valeur de la base propre a (organe, prelevement), a valider
    specifique: bool = False


# ---------------------------------------------------------------------------
# Lexique integre (repli) : variantes STT observées, issues du prompt v2.
# Chaque entree : terme canonique, variantes, mots de contexte requis.
# ---------------------------------------------------------------------------

_LEXIQUE_INTEGRE: list[tuple[str, list[str], list[str]]] = [
    ("tumeur", ["tu meurs", "tu meurt"], []),
    ("coupe bronchique", ["coup de bronche"], []),
    ("bronchique", ["branchique"], ["bronch", "poumon", "pulmonaire", "lobe", "biopsie"]),
    ("acineuse", ["racineuse"], ["adenocarcinome", "architecture"]),
    ("TTF1", ["DTF1", "TTF un", "tetef un", "té té èf un"], []),
    ("sous-pleurale", ["souple rale", "souple râle"], []),
    ("PD-L1", ["pdl un", "pdl1", "pédélun", "pd l un"], []),
    ("lobulaire", ["lobullaire"], []),
    ("Paget", ["padget"], []),
    ("phyllode", ["filode"], []),
    ("Barrett", ["barret"], ["oesophage", "endobrachy", "muqueuse"]),
    ("pylori", ["pilori"], ["helicobacter", "gastrite", "estomac"]),
    ("Crohn", ["crone"], []),
    ("Siewert", ["si wert"], []),
    ("Mandard", ["mandar"], []),
    ("linite", ["linnite"], []),
    ("Gleason", ["glison", "gleeson", "glisson"], ["prostate", "prostatique", "score", "adenocarcinome", "isup", "grade", "+"]),
    ("Fuhrman", ["furman"], []),
    ("Bosniak", ["bosniaque"], ["kyste", "rein", "renal"]),
    ("Breslow", ["brè slo", "breslo", "bresslow"], []),
    ("Clark", ["clarck"], []),
    ("naevus", ["nevus", "névus"], []),
    ("Merkel", ["merckel"], []),
    ("POLE", ["polé"], ["endometre", "moleculaire"]),
    ("Krukenberg", ["crucain berg"], []),
    ("Bethesda", ["bétesda", "betesda"], []),
    ("Hurthle", ["hurtle"], []),
    ("NIFTP", ["niftp"], []),
    ("MGMT", ["em ji em té"], []),
    ("FNCLCC", ["féne clcc"], []),
    ("STAT6", ["stat six"], []),
    ("EBER", ["ébère"], []),
    ("C4d", ["c quatre d"], ["greffon", "rejet", "transplant"]),
    ("muqueuse", ["mucose", "equeuse"], []),
    ("fibro-hyalin", ["fibro-yalin", "fibro yalin"], []),
    ("hyaline", ["yaline"], []),
    ("parenchymateuse", ["parenchymate"], []),
    ("adénocarcinome", ["adeno carcinome", "adéno carcinome", "adénocarcynome", "adenocarcynome"], []),
    ("épidermoïde", ["épidermoide", "epidermoyde"], []),
    ("urothélial", ["urotélial", "uro thélial"], []),
    ("koïlocytes", ["coilocytes", "koilocyte"], []),
    ("parakératose", ["para kératose"], []),
    ("Ki67", ["ki 67", "kiss 67", "ki soixante-sept"], []),
    ("HER2", ["her deux", "erb deux", "her 2"], []),
    ("ISUP", ["isupe", "i s u p"], ["gleason", "prostate", "grade"]),
    ("lymphovasculaire", ["lympho vasculaire"], []),
    ("périnerveux", ["péri nerveux"], []),
    ("RTUV", ["rtuv", "r t u v", "ertéuvé"], ["vessie", "vesical", "urothelial"]),
    ("détrusor", ["détruseur", "detruseur", "des trusor"], ["vessie", "musculeuse", "rtuv", "urothelial"]),
    ("Barety", ["barretis", "baretti", "barreti"], ["loge", "ganglion", "curage"]),
    ("conisation", ["conisasion"], []),
    ("exocol", ["exo col"], ["col", "conisation", "cin"]),
    ("endocol", ["endo col"], ["col", "conisation", "cin"]),
    ("Melan-A", ["mélane a", "melan a"], []),
    ("SOX10", ["sox dix", "socks 10"], []),
    ("mucosécrétion", ["mycosécrétion", "myco sécrétion", "muco sécrétion"], []),  # observe : corpus audio 1
    ("Barety", ["baréties", "barétis"], ["loge", "ganglion", "curage", "interlobaire"]),  # observe : corpus audio 3
]

# ---------------------------------------------------------------------------
# Plages plausibles (heuristiques, fiabilite D) : categorie x classe de prelevement
# Valeurs en mm. Elles servent UNIQUEMENT a signaler, jamais a corriger.
# ---------------------------------------------------------------------------

_PLAGES_HEURISTIQUES: dict[tuple[str, str], tuple[float, float]] = {
    ("tumeur", "biopsie"): (0.2, 50.0),
    ("tumeur", "cytologie"): (0.2, 80.0),
    ("tumeur", "piece_operatoire"): (1.0, 300.0),  # 0,3 mm de tumeur sur une piece : 0,3 cm mal transcrit ?
    ("tumeur", "*"): (0.2, 300.0),
    ("fragment", "*"): (0.2, 40.0),
    ("polype", "*"): (1.0, 80.0),
    ("marge", "*"): (0.0, 100.0),
    ("breslow", "*"): (0.0, 30.0),
    ("ganglion", "*"): (0.5, 80.0),
    ("piece", "biopsie"): (0.2, 50.0),
    ("piece", "*"): (5.0, 600.0),
    ("carotte", "*"): (1.0, 35.0),
}
_LIBELLE_CATEGORIE: dict[str, str] = {"tumeur": "tumeur", "fragment": "fragment", "polype": "polype", "marge": "marge",
                                      "breslow": "Breslow", "ganglion": "ganglion", "piece": "pièce", "carotte": "carotte"}
_LIBELLE_CLASSE: dict[str, str] = {"biopsie": "biopsie", "cytologie": "cytologie", "piece_operatoire": "pièce opératoire",
                                   "curage": "curage"}

# Champs tumoraux : JAMAIS demandes sur une lesion benigne ou indeterminee.
TERMES_TUMORAUX: tuple[str, ...] = (
    "tumeur", "tumoral", "tumorale", "carcinome", "ptnm", "tnm", "stade", "staging",
    "marge", "limite", "exerese", "recoupe", "ganglion", "curage", "sentinelle",
    "embole", "engainement", "perinerveux", "perineural", "lymphovasculaire",
    "grade", "gleason", "isup", "sbr", "nottingham", "breslow", "clark", "fuhrman",
    "ki67", "ki-67", "her2", "recepteur", "type histologique", "differenciation",
    "invasion", "infiltration", "extension", "budding", "pd-l1", "biomarqueur",
    "statut", "mitose", "mitotique", "regression", "effraction", "microsatellit",
    "multifocal", "in situ", "pt", "pn", "figo", "msi", "mmr",
)
# Champs exclus meme en precancereux (aucun sens hors tumeur infiltrante).
TERMES_INFILTRANTS: tuple[str, ...] = (
    "ptnm", "tnm", "stade", "staging", "ganglion", "curage", "sentinelle", "embole",
    "engainement", "perinerveux", "lymphovasculaire", "taille tumorale",
    "taille de la tumeur", "breslow", "budding", "pd-l1", "her2", "ki67", "figo",
)
# Champs reserves aux pieces operatoires.
TERMES_PIECE: tuple[str, ...] = (
    "ptnm", "tnm", "stade", "marge", "limite", "exerese", "recoupe", "ganglion",
    "curage", "sentinelle", "mesorectum", "circonferentielle", "taille tumorale",
    "taille de la tumeur", "effraction", "capsul",
)

_SECTION_PAR_MOT: list[tuple[tuple[str, ...], str]] = [
    (("renseignement", "clinique", "indication", "lateralite du prelevement"), "renseignements"),
    (("immunohisto", "ihc", "her2", "ki67", "recepteur", "pd-l1", "alk", "ttf", "p16",
      "marqueur", "mmr", "msi", "anticorps"), "ihc"),
    (("macroscop", "taille", "dimension", "poids", "nombre de fragments", "fragment",
      "aspect", "mesure", "inclusion"), "macroscopie"),
    (("ptnm", "tnm", "stade", "classification", "conclusion", "diagnostic"), "conclusion"),
]

_CLASSES_PRELEVEMENT: dict[SpecimenType, str] = {
    SpecimenType.BIOPSIE: "biopsie",
    SpecimenType.PIECE_OPERATOIRE: "piece_operatoire",
    SpecimenType.CYTOLOGIE: "cytologie",
    SpecimenType.CURAGE: "curage",
}
_CONTEXTES: dict[DiagnosticContext, str] = {
    DiagnosticContext.BENIN: "benin",
    DiagnosticContext.PRE_CANCEREUX: "precancereux",
    DiagnosticContext.INFILTRANT: "malin",
    DiagnosticContext.INDETERMINE: "indetermine",
}

#: Mots qui signalent un prelevement de facon EXPLICITE (sinon : non dit).
_PRELEVEMENT_EXPLICITE: list[tuple[str, str]] = [
    ("biopsie", "biopsie"), ("biopsies", "biopsie"), ("microbiopsie", "biopsie"),
    ("macrobiopsie", "biopsie"), ("carotte", "biopsie"), ("carottes", "biopsie"), ("punch", "biopsie"),
    ("cytologie", "cytologie"), ("cytoponction", "cytologie"), ("ponction", "cytologie"),
    ("frottis", "cytologie"), ("lba", "cytologie"), ("liquide", "cytologie"),
    ("rtuv", "piece_operatoire"), ("resection", "piece_operatoire"), ("conisation", "piece_operatoire"),
    ("colectomie", "piece_operatoire"), ("hemicolectomie", "piece_operatoire"),
    ("lobectomie", "piece_operatoire"), ("mastectomie", "piece_operatoire"),
    ("tumorectomie", "piece_operatoire"), ("prostatectomie", "piece_operatoire"),
    ("thyroidectomie", "piece_operatoire"), ("lobo-isthmectomie", "piece_operatoire"),
    ("exerese(?! (?:complete|incomplete|en totalite|endoscopique))", "piece_operatoire"),
    ("polypectomie", "biopsie"), ("polype", "biopsie"), ("piece", "piece_operatoire"), ("gastrectomie", "piece_operatoire"),
    ("nephrectomie", "piece_operatoire"), ("cystectomie", "piece_operatoire"),
    ("hysterectomie", "piece_operatoire"), ("curage", "curage"),
]


def _motif(mot: str) -> str:
    """Mot-cle de prelevement -> motif regex (les entrees a lookahead sont deja des motifs)."""
    return mot if "(?" in mot else re.escape(mot)


def _niveau_fiabilite(f: Any) -> Fiabilite:
    f = str(f or "").strip().upper()[:1]
    return f if f in ("A", "B", "C", "D") else "C"


FIABILITE_SENS: dict[str, str] = {
    "A": "Référentiel officiel publié (autorité nationale ou internationale).",
    "B": "Document de la pathologiste référente ou règle MARC relue : fiable, propre au laboratoire.",
    "C": "Synthèse ou dérivé interne de MARC : à faire valider par la pathologiste référente.",
    "D": "Semence ou heuristique MARC non validée : indicatif seulement.",
}


def titre_court_source(src: dict[str, Any], sid: str) -> str:
    """Titre humain (<= 70 car., jamais tronque) d'une source ; honnete quand l'origine est inconnue."""
    t = str(src.get("titre_court") or "").strip()
    if t:
        return t
    t = str(src.get("titre") or "").strip()
    if t and len(t) <= 70 and ".py" not in t and "…" not in t:
        return t
    return "Référentiel interne MARC (à valider)"


_RE_LOC_PY = re.compile(r"\.py\b|TEMPLATE_[A-Z_]+|_BODY_STRUCTURES|_MORPHOLOGIES|CONTEXT_BIAS")


def localisation_lisible(loc: str | None) -> str:
    """Localisation sans nom de fichier de code (repli pour d'anciennes bases ou sources internes)."""
    loc = (loc or "").strip()
    if not loc:
        return ""
    m = re.match(r"templates_organes\.py, TEMPLATE_([A-Z_]+)\.champs_obligatoires\[(\d+)\]", loc)
    if m:
        return f"Gabarit MARC {m.group(1).replace('_', '-').capitalize()}, champ {int(m.group(2)) + 1}"
    if _RE_LOC_PY.search(loc):
        return "Référentiel interne MARC (à valider)"
    return loc


_CONFIANCE_FIABILITE: dict[str, float] = {"A": 0.95, "B": 0.85, "C": 0.7, "D": 0.55}


class Referentiel:
    """Facade unique du pipeline sur la base de connaissances et ses replis."""

    def __init__(self, kb: KB | None = None) -> None:
        self.kb: KB = kb if kb is not None else get_kb()
        self.replis: list[str] = []

    # -- utilitaires -------------------------------------------------------

    def _kb_appel(self, nom: str, *args: Any, defaut: Any = None) -> Any:
        """Appelle une methode KB sans jamais propager d'exception."""
        try:
            val = getattr(self.kb, nom)(*args)
        except Exception:  # noqa: BLE001 - la KB ne doit jamais bloquer le pipeline
            logger.exception("KB.%s a échoué : repli", nom)
            return defaut
        return val if val is not None else defaut

    def _repli(self, message: str) -> None:
        if message not in self.replis:
            self.replis.append(message)

    def kb_disponible(self) -> bool:
        return bool(self._kb_appel("organes", defaut=[]))

    def source(self, source_id: str) -> dict[str, Any] | None:
        src = self._kb_appel("source", source_id, defaut=None)
        return src or SOURCES_INTERNES.get(source_id)

    def source_ref(self, source_id: str | None, *, localisation: str | None = None,
                   fiabilite: str | None = None, extrait: str | None = None) -> SourceRef:
        """SourceRef 'kb' affichable depuis un identifiant de source.

        Contrat : ``libelle`` = titre humain court (<= 70 car., jamais tronque, sans nom de fichier de
        code) ; ``extrait`` = localisation ou citation utile (<= 200 car.) ; ``fiabilite`` A a D.
        """
        sid = source_id or "src:inconnue"
        src = self.source(sid) or {}
        loc = localisation_lisible(localisation)
        return SourceRef(
            kind="kb", ref=sid, libelle=titre_court_source(src, sid),
            extrait=extrait_court(extrait or loc or "", 200) or None,
            fiabilite=_niveau_fiabilite(fiabilite or src.get("fiabilite")),  # type: ignore[arg-type]
            url=src.get("url"),
        )

    def source_detail(self, source_id: str, limite: int = 50) -> dict[str, Any] | None:
        """Fiche complete d'une source (endpoint GET /v3/kb/sources/{id})."""
        src = self.source(source_id)
        if not src:
            return None
        sid = str(src.get("id") or source_id)
        fia = _niveau_fiabilite(src.get("fiabilite"))
        citations = self._kb_appel("citations_source", sid, limite, defaut={"total": 0, "par_type": {}, "elements": []})
        detail = {k: v for k, v in src.items() if k not in ("fichiers",)}
        detail.update({
            "id": sid,
            "titre_court": titre_court_source(src, sid),
            "titre": str(src.get("titre") or titre_court_source(src, sid)),
            "description": str(src.get("description") or "Source interne de MARC, sans description détaillée."),
            "editeur": str(src.get("editeur") or "Éditeur non renseigné"),
            "version": src.get("version"),
            "date_publication": src.get("date_publication"),
            "url": src.get("url"),
            "licence": src.get("licence"),
            "fiabilite": fia,
            "fiabilite_sens": FIABILITE_SENS[fia],
            "references": citations,
        })
        return detail

    def _source_depuis_prov(self, entree: dict[str, Any], defaut: str) -> tuple[SourceRef, Fiabilite, float]:
        prov = entree.get("prov") or {}
        sid = prov.get("source_id") or defaut
        fia = _niveau_fiabilite(prov.get("fiabilite") or (self.source(sid) or {}).get("fiabilite"))
        conf = prov.get("confiance")
        confiance = float(conf) if isinstance(conf, (int, float)) else _CONFIANCE_FIABILITE[fia]
        if str(prov.get("statut_validation") or "") in ("a_valider", "derive_auto"):
            confiance = min(confiance, _CONFIANCE_FIABILITE[fia]) - 0.05
        ref = self.source_ref(sid, localisation=prov.get("localisation"), fiabilite=fia)
        return ref, fia, max(0.3, min(1.0, confiance))

    # -- organes -----------------------------------------------------------

    def detecter_organes(self, texte: str) -> list[OrganeDetecte]:
        """Organes mentionnes, base v3 d'abord, detection historique en repli."""
        res: list[OrganeDetecte] = []
        for o in self._kb_appel("detecter_organes", texte, defaut=[]) or []:
            oid = str(o.get("id") or "")
            if not oid or oid == "organe:generique" or float(o.get("confiance") or 0.8) < 0.6:
                continue
            entree = next((e for e in self._kb_appel("organes", defaut=[]) if e.get("id") == oid), {})
            src, _, _ = self._source_depuis_prov(entree, "src:kb_marc_v3")
            res.append(OrganeDetecte(
                id=oid, libelle=str(o.get("libelle") or oid), debut=o.get("debut"), fin=o.get("fin"),
                confiance=float(o.get("confiance") or 0.8), source=src,
                id_historique=oid.split(":", 1)[-1],
            ))
        if res:
            return res
        # Repli : detecteur historique (templates_organes), offsets recalcules ici.
        try:
            from reports.knowledge import detect_organs
            templates = detect_organs(self._masquer_pieges(texte))
        except Exception:  # noqa: BLE001
            templates = []
        if templates:
            self._repli("Organes : détection historique (base v3 sans organes)")
        bas = texte.lower()
        for tpl in templates:
            debut = fin = None
            for kw in tpl.mots_cles_detection:
                m = re.search(rf"\b{re.escape(kw.lower())}(?:s|x)?\b", bas)
                if m and (debut is None or m.start() < debut):
                    debut, fin = m.start(), m.end()
            res.append(OrganeDetecte(
                id=f"organe:{tpl.organe}", libelle=tpl.nom_affichage, debut=debut, fin=fin,
                confiance=0.75, source=self.source_ref("src:marc_templates_inca"),
                id_historique=tpl.organe,
            ))
        return res

    def _masquer_pieges(self, texte: str) -> str:
        """Blanchit (longueur conservee) les expressions piegees (« au sein d'un materiel » n'est pas le sein)."""
        pieges = self._kb_appel("_pieges", defaut=None) or [
            re.compile(r"\bau sein (?:de |d'|du |des |meme|duquel|desquel)")]
        norm = normaliser(texte)
        if len(norm) != len(texte):
            return texte
        sortie = list(texte)
        for pat in pieges:
            for m in pat.finditer(norm):
                for i in range(m.start(), m.end()):
                    sortie[i] = " "
        return "".join(sortie)

    # -- prelevement et contexte -------------------------------------------

    def detecter_prelevement(self, texte: str) -> tuple[str | None, tuple[int, int] | None]:
        """Classe de prelevement EXPLICITEMENT dite (sinon None) et son empan."""
        norm = normaliser(texte)
        meilleur: tuple[int, str, int, int] | None = None
        for mot, classe in _PRELEVEMENT_EXPLICITE:
            m = re.search(rf"(?<![a-z]){_motif(mot)}(?![a-z])", norm)
            if m and (meilleur is None or m.start() < meilleur[0]):
                meilleur = (m.start(), classe, m.start(), m.end())
        if meilleur is None:
            return None, None
        # Priorite historique (biopsie > cytologie > piece) pour les dictees mixtes.
        historique = _CLASSES_PRELEVEMENT.get(detecter_specimen_type(texte))
        classe = meilleur[1]
        if historique in ("biopsie", "cytologie") and historique != classe:
            for mot, c in _PRELEVEMENT_EXPLICITE:
                if c == historique:
                    m = re.search(rf"(?<![a-z]){_motif(mot)}(?![a-z])", norm)
                    if m:
                        return historique, (m.start(), m.end())
        # La normalisation conserve la longueur pour le francais courant ; on
        # verifie tout de meme que l'empan retombe sur le meme mot.
        debut, fin = meilleur[2], meilleur[3]
        if normaliser(texte[debut:fin]) != norm[debut:fin]:
            return classe, None
        return classe, (debut, fin)

    def detecter_contexte(self, texte: str) -> str:
        """benin | precancereux | malin | indetermine (negations respectees)."""
        try:
            return detecter_contexte_lesionnel(texte)
        except Exception:  # noqa: BLE001 - repli : detecteur historique (sous-chaines)
            try:
                return _CONTEXTES[detecter_diagnostic_context(texte)]
            except Exception:  # noqa: BLE001
                return "indetermine"

    # -- champs attendus ---------------------------------------------------

    def champs_attendus(self, organe: OrganeDetecte, prelevement: str | None,
                        contexte: str, texte: str = "") -> list[ChampAttendu]:
        """Champs obligatoires pour (organe x prelevement x contexte), filtres de securite inclus."""
        champs: list[ChampAttendu] = []
        brut = self._kb_appel("champs", organe.id, prelevement, contexte, defaut=[]) or []
        for c in brut:
            if not c.get("obligatoire", True) or c.get("niveau") == "recommande":
                continue  # seuls les champs OBLIGATOIRES deviennent des trous
            if not _condition_satisfaite(c.get("condition"), prelevement):
                continue  # champ conditionnel non evaluable : on ne le reclame pas (zero faux positif)
            requis = [str(t) for t in c.get("requiert_texte") or []]
            if requis and not any(normaliser(t) in normaliser(texte) for t in requis):
                continue  # champ reserve a une topographie (mesorectum : rectum) absente de la dictee
            src, fia, conf = self._source_depuis_prov(c, "src:kb_marc_v3")
            libelle = str(c.get("libelle") or c.get("id") or "")
            if "non reconnu" in normaliser(libelle):
                logger.warning("Champ KB au libellé invalide ignoré : %s", c.get("id"))
                continue
            source_inca = None
            if c.get("niveau") == "obligatoire_inca":
                for pc in [c.get("prov")] + list(c.get("prov_complementaires") or []):
                    if isinstance(pc, dict) and "inca" in str(pc.get("source_id") or ""):
                        source_inca = self.source_ref(pc.get("source_id"), localisation=pc.get("localisation"),
                                                      fiabilite=pc.get("fiabilite"))
                        break
            detection = c.get("detection") or {}
            mots = list(c.get("mots_cles") or detection.get("mots_cles") or [])
            section = c.get("section") or (c.get("placement") or {}).get("section") or section_pour(libelle)
            champs.append(ChampAttendu(
                id=str(c.get("id") or libelle), libelle=libelle, obligatoire=True,
                section=section_canonique(str(section)),
                type=str(c.get("type") or c.get("type_valeur") or "texte"), unite=c.get("unite"),
                options=[str(o) for o in (c.get("options") or [])][:12], mots_cles=mots,
                source=src, fiabilite=fia, confiance_source=conf, organe_id=organe.id,
                concept=str(c.get("concept") or ""), tumoral=bool(c.get("tumoral", False)),
                niveau=str(c.get("niveau") or ""), condition=c.get("condition"), source_inca=source_inca,
            ))
        if not champs:
            champs = self._champs_historiques(organe, prelevement, contexte)
        return filtrer_champs_securite(champs, prelevement, contexte)

    def _champs_historiques(self, organe: OrganeDetecte, prelevement: str | None,
                            contexte: str) -> list[ChampAttendu]:
        try:
            from templates_organes import get_champs_obligatoires
            legacy = get_champs_obligatoires(organe.id_historique)
        except Exception:  # noqa: BLE001
            legacy = []
        if not legacy:
            return []
        self._repli(f"Champs {organe.libelle} : templates historiques INCa (base v3 sans exigences)")
        src = self.source_ref("src:marc_templates_inca")
        res: list[ChampAttendu] = []
        for c in legacy:
            cle = normaliser(c.nom).replace(" ", "_")
            res.append(ChampAttendu(
                id=f"champ:{organe.id_historique}.{cle}", libelle=c.nom, obligatoire=True,
                section=section_pour(c.nom, c.section), mots_cles=list(c.mots_cles_detection),
                source=src, fiabilite="C", confiance_source=0.7, organe_id=organe.id,
            ))
        return res

    # -- gabarit, style, lexique, plages -------------------------------------

    def gabarit(self, organe_id: str | None, prelevement: str | None) -> tuple[list[tuple[str, str]], SourceRef | None]:
        """Sections (id, titre) du gabarit ; gabarit standard en repli."""
        if organe_id:
            g = self._kb_appel("gabarit", organe_id, prelevement, defaut=None)
            if g and g.get("sections"):
                secs = sorted(g["sections"], key=lambda s: s.get("ordre", 0))
                src, _, _ = self._source_depuis_prov(g, "src:kb_marc_v3")
                res: list[tuple[str, str]] = []
                for sec in secs:
                    sid = section_canonique(str(sec.get("id") or sec.get("nom")))
                    if sid != "titre" and sid not in {x for x, _ in res}:
                        res.append((sid, str(sec.get("titre") or sec.get("nom"))))
                if res:
                    return res, src
        self._repli("Gabarit : structure standard ACP (titre, renseignements, macroscopie, microscopie, IHC, conclusion)")
        micro = "Examen cytologique" if prelevement == "cytologie" else "Microscopie"
        return [
            ("renseignements", "Renseignements cliniques"),
            ("macroscopie", "Macroscopie"),
            ("microscopie", micro),
            ("ihc", "Immunohistochimie"),
            ("conclusion", "Conclusion"),
        ], None

    def exemples_style(self, organe_id: str | None, limite: int = 2) -> list[dict[str, Any]]:
        if not organe_id:
            return []
        ex = self._kb_appel("exemples_style", organe_id, limite, defaut=[]) or []
        # Verrou par organe : un exemple d'un autre organe est ecarte.
        ex = [e for e in ex if not e.get("organe_id") or e.get("organe_id") == organe_id]
        if not ex:
            self._repli("Style : aucun exemple verrouillé pour cet organe (style neutre)")
        return ex[:limite]

    def lexique(self) -> list[EntreeLexique]:
        res: list[EntreeLexique] = []
        for e in self._kb_appel("lexique", defaut=[]) or []:
            terme = str(e.get("terme") or e.get("terme_canonique") or "").strip()
            if not terme:
                continue
            variantes: list[tuple[str, float]] = []
            details = {str(d.get("forme")): d for d in e.get("variantes_detail") or [] if isinstance(d, dict)}
            for v in e.get("variantes") or []:
                if isinstance(v, dict):
                    forme, conf, origine = str(v.get("forme") or ""), float(v.get("confiance") or 0.8), v.get("origine")
                else:
                    d = details.get(str(v), {})
                    forme, conf, origine = str(v), float(d.get("confiance") or 0.85), d.get("origine")
                if not forme.strip():
                    continue
                if origine == "genere" and conf < 0.75:
                    if not _variante_proche(forme, terme):
                        continue  # variante generee eloignee (« millimetres » pour « mm ») : ignoree
                    # Variante generee par regle, de MEME prononciation que le terme et a faible
                    # distance d'edition : une transcription STT de ce terme, pas un autre mot.
                    conf = 0.8
                variantes.append((forme, conf))
            src, _, _ = self._source_depuis_prov(e, "src:kb_marc_v3")
            res.append(EntreeLexique(terme, variantes, [str(x) for x in e.get("contexte_requis") or []],
                                     src, [str(x) for x in e.get("organes") or []]))
        if not res:
            self._repli("Lexique : variantes intégrées MARC (base v3 sans lexique)")
        # Les variantes OBSERVEES de MARC v2 completent toujours la base (sans doublon).
        connues = {normaliser(f) for e in res for f, _ in e.variantes}
        src = self.source_ref("src:marc_lexique_integre")
        for t, vs, ctx in _LEXIQUE_INTEGRE:
            nouvelles = [(v, 0.85) for v in vs if normaliser(v) not in connues]
            if nouvelles:
                res.append(EntreeLexique(t, nouvelles, ctx, src))
        return res

    def termes_vocabulaire(self) -> list[str]:
        """Termes canoniques connus (lexique + amorce STT) pour la correction approchee."""
        termes = {e.terme for e in self.lexique()}
        try:
            from vocabulaire_acp import get_context_bias
            termes |= set(get_context_bias())
        except Exception:  # noqa: BLE001
            pass
        return sorted(termes)

    def plage(self, organe_id: str | None, categorie: str, prelevement: str | None) -> Plage | None:
        """Plage plausible (mm) pour une categorie de mesure.

        On retient la plage la PLUS RESTRICTIVE entre la base v3 (organe puis
        generique) et l'heuristique par classe de prelevement : la base donne une
        taille tumorale generique (jusqu'a 30 cm) qui ne voit pas qu'une tumeur
        de 25 cm sur une BIOPSIE est une erreur d'unite.
        """
        candidates: list[Plage] = []
        for champ_id in _CHAMPS_KB_PAR_CATEGORIE.get(categorie, ()):
            p = (self._kb_appel("plage_mesure_prelevement", organe_id, champ_id, prelevement, defaut=None)
                 or self._kb_appel("plage_mesure", organe_id, champ_id, defaut=None))
            if p and isinstance(p.get("min"), (int, float)) and isinstance(p.get("max"), (int, float)):
                facteur = 10.0 if str(p.get("unite", "mm")).lower() == "cm" else 1.0
                src, _, _ = self._source_depuis_prov(p, "src:kb_marc_v3")
                candidates.append(Plage(float(p["min"]) * facteur, float(p["max"]) * facteur, src,
                                        str(p.get("libelle") or champ_id),
                                        contexte=str(p.get("libelle_court") or p.get("libelle") or champ_id),
                                        specifique=bool(p.get("prelevement"))))
                break
        classe = prelevement or "*"
        borne = _PLAGES_HEURISTIQUES.get((categorie, classe)) or _PLAGES_HEURISTIQUES.get((categorie, "*"))
        if borne is not None:
            candidates.append(Plage(borne[0], borne[1], self.source_ref("src:marc_heuristiques_unites"),
                                    f"{categorie} ({classe})",
                                    contexte=_LIBELLE_CATEGORIE.get(categorie, categorie)
                                    + ("" if classe == "*" else f" ({_LIBELLE_CLASSE.get(classe, classe)})")))
        if not candidates:
            return None
        # Plage la plus restrictive sur les DEUX bornes (une borne basse heuristique reste active
        # meme si la base v3 donne la plus petite borne haute).
        retenue = min(candidates, key=lambda p: p.max_mm)
        plancher = max(p.min_mm for p in candidates)
        if plancher > retenue.min_mm:
            retenue = Plage(plancher, retenue.max_mm, next(p.source for p in candidates if p.min_mm == plancher),
                            retenue.libelle, retenue.contexte, retenue.specifique)
        return retenue


_CHAMPS_KB_PAR_CATEGORIE: dict[str, tuple[str, ...]] = {
    "tumeur": ("taille_tumorale",),
    "fragment": ("taille_fragments",),
    "marge": ("marge",),
    "breslow": ("breslow",),
    "piece": ("dimension_piece",),
    "carotte": ("taille_carotte",),
    "polype": ("champ:taille_polype", "taille_polype"),
    "ganglion": ("champ:taille_ganglion", "taille_ganglion"),
}


_SECTIONS_CANONIQUES: dict[str, str] = {
    "clinique": "renseignements", "renseignements_cliniques": "renseignements",
    "identification": "renseignements", "immunohistochimie": "ihc",
    "biologie_moleculaire": "biomol", "histologie": "microscopie", "cytologie": "microscopie",
}


def section_canonique(section_id: str) -> str:
    """Identifiant de section unique pour le pipeline (gabarits base v3 et historiques)."""
    s = normaliser(section_id).strip().replace(" ", "_")
    return _SECTIONS_CANONIQUES.get(s, s)


def _condition_satisfaite(condition: object, prelevement: str | None) -> bool:
    """Condition textuelle d'un champ : seules les conditions de prelevement sont evaluees.

    Toute autre condition (« si neoadjuvant », « tumeur rectale »...) n'est pas
    evaluable sur la dictee : le champ n'est alors PAS reclame.
    """
    if not condition:
        return True
    c = normaliser(str(condition))
    if re.search(r"(?<![a-z])si ", c) or "neoadjuvant" in c:
        return False
    autorises: set[str] = set()
    if "piece" in c or "exerese" in c:
        autorises.add("piece_operatoire")
    if "biops" in c:
        autorises.add("biopsie")
    return prelevement in autorises


def _variante_proche(forme: str, terme: str) -> bool:
    from projet.kb import cle_phonetique as cle_kb, distance_levenshtein
    a = re.sub(r"[^a-z0-9]", "", normaliser(forme))
    b = re.sub(r"[^a-z0-9]", "", normaliser(terme))
    if not a or not b:
        return False
    return cle_kb(a) == cle_kb(b) or distance_levenshtein(a, b) <= max(1, len(b) // 6)


def section_pour(libelle: str, section_historique: str | None = None) -> str:
    """Section du CR ou placer un champ (heuristique par mots-cles)."""
    if section_historique:
        s = normaliser(section_historique)
        for cle in ("renseignements", "macroscopie", "microscopie", "conclusion"):
            if cle[:6] in s:
                return cle
        if "immuno" in s or "ihc" in s:
            return "ihc"
    norm = normaliser(libelle)
    for mots, section in _SECTION_PAR_MOT:
        if any(contient_terme(norm, m) or m in norm for m in mots):
            return section
    return "microscopie"


def filtrer_champs_securite(champs: list[ChampAttendu], prelevement: str | None,
                            contexte: str) -> list[ChampAttendu]:
    """Filtre de SECURITE applique a tout champ, base v3 comprise.

    - jamais de champ tumoral sur une lesion benigne ou indeterminee ;
    - en precancereux, rien de reserve a l'infiltrant (pTNM, ganglions, emboles...) ;
    - pas de pTNM / marges / ganglions sur une biopsie ou une cytologie ;
    - filtre historique ``champ_applicable`` en plus.
    """
    specimen = {
        "biopsie": SpecimenType.BIOPSIE, "piece_operatoire": SpecimenType.PIECE_OPERATOIRE,
        "cytologie": SpecimenType.CYTOLOGIE, "curage": SpecimenType.CURAGE,
    }.get(prelevement or "", SpecimenType.INDETERMINE)
    diag = {
        "benin": DiagnosticContext.BENIN, "precancereux": DiagnosticContext.PRE_CANCEREUX,
        "malin": DiagnosticContext.INFILTRANT,
    }.get(contexte, DiagnosticContext.INDETERMINE)

    gardes: list[ChampAttendu] = []
    vus: set[str] = set()
    for c in champs:
        norm = normaliser(c.libelle + " " + c.id.replace("_", " ").replace(".", " "))

        def a(termes: tuple[str, ...]) -> bool:
            return any(contient_terme(norm, t) for t in termes)

        if contexte in ("benin", "indetermine") and (c.tumoral or a(TERMES_TUMORAUX)):
            continue
        if contexte == "precancereux" and a(TERMES_INFILTRANTS):
            continue
        if prelevement != "piece_operatoire" and a(TERMES_PIECE):
            continue
        if specimen != SpecimenType.INDETERMINE and not champ_applicable(c.libelle, specimen, diag):
            continue
        cle = normaliser(c.libelle)
        if cle in vus:
            continue
        vus.add(cle)
        gardes.append(c)
    return gardes
