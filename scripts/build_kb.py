"""Construit la base de connaissances MARC v3 (`backend/kb/`, schema kb_marc_v3.1).

Usage :
  python scripts/build_kb.py                       # build complet -> backend/kb/
  python scripts/build_kb.py --sortie /tmp/kb      # build ailleurs (tests)
  python scripts/build_kb.py --date 2026-11-15     # date de build fixee (reproductibilite)
  python scripts/build_kb.py --purge-textes-canoniques   # purge PII de backend/data/textes_canoniques.json
  python scripts/build_kb.py --strict              # echoue aussi si une source sur disque contient de la PII

Principes (audit PO-1, sections 5.1, 7 et 8) :
- chaque entree porte un objet `prov` {source_id, localisation, version_source,
  date_extraction, fiabilite A-D, confiance 0-1, statut_validation, methode} ;
- SCAN PII BLOQUANT : tout texte ingere est purge (motifs connus) puis scanne ; un
  residu arrete le build (code retour 1). La sortie est elle-meme rescannee ;
- un code ADICAP obsolete ou inconnu n'est jamais propose (collection `adicap_rejets`) ;
- build reproductible : memes entrees + meme date = memes octets ;
- aucune donnee medicale n'est lue : uniquement des referentiels et formulations canoniques.

Entrees : backend/data/*.json, backend/templates_organes.py, backend/vocabulaire_acp.py,
backend/snomed.py, backend/specimen_type.py, docs/v3/sources_web/*.json, semences
curees backend/kb/seeds/*.json et (optionnel) Ressources/.../Bibles Greg.xlsx.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

RACINE: Path = Path(__file__).resolve().parent.parent
BACKEND: Path = RACINE / "backend"
sys.path.insert(0, str(BACKEND))

from projet.kb import (  # noqa: E402  (apres sys.path)
    KB,
    cle_phonetique,
    evaluer_condition,
    normaliser,
)

KB_DIR: Path = BACKEND / "kb"
SEEDS: Path = KB_DIR / "seeds"
DATA: Path = BACKEND / "data"
WEB: Path = RACINE / "docs/v3/sources_web"
XLSX_BIBLE: Path = RACINE / "Ressources/1. Codes Bible/Bibles Greg.xlsx"
CANONIQUES: Path = DATA / "textes_canoniques.json"

KB_VERSION = "3.0.0"
SCHEMA_VERSION = "kb_marc_v3.1"

PRELEVEMENTS_IDS = ["biopsie", "piece_operatoire", "cytologie", "curage", "indetermine"]
CONTEXTES_IDS = ["benin", "precancereux", "malin", "indetermine"]


# ===========================================================================
# 1. Scan et purge PII (BLOQUANT)
# ===========================================================================

class ErreurPII(RuntimeError):
    """Donnee personnelle residuelle dans un texte ingere : le build s'arrete."""


# Prenoms usuels : sert a reperer « NOM Prenom » / « Prenom NOM ». Liste volontairement
# longue (les noms de famille ne sont pas listables, les prenoms oui).
PRENOMS: frozenset[str] = frozenset(normaliser(p) for p in """
Adrien Alain Alexandre Alexandra Alice Amandine Andre Anne Annie Antoine Arnaud Aurelie Axel
Benjamin Bernard Brigitte Camille Carole Catherine Cecile Cedric Celine Chantal Charles Charlotte
Christian Christine Christophe Claire Claude Clement Corinne Daniel David Delphine Denis Didier
Dominique Edouard Elise Emilie Emmanuel Eric Etienne Fabien Fabrice Florence Francois Francoise
Frederic Gabriel Gerard Gilbert Gilles Guillaume Guy Helene Henri Herve Hugo Isabelle Jacques
Jean Jeanne Jerome Joel Joseph Julie Julien Karine Laetitia Laura Laurence Laurent Lea Lucas
Lucie Luc Magali Marc Marcel Marie Marine Marion Martine Mathieu Maurice Michel Michele Monique
Nadia Nathalie Nicolas Nicole Olivier Pascal Pascale Patrice Patricia Patrick Paul Philippe
Pierre Rachel Raphael Raymond Remi Renaud Rene Richard Robert Roger Romain Sabine Samuel
Sandrine Sebastien Serge Severine Simon Sophie Stephane Stephanie Sylvain Sylvie Thierry
Thomas Valerie Vanessa Veronique Victor Vincent Virginie Xavier Yannick Yves Yvonne
""".split())

_MOIS = "janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre"
_NOM_CAP = r"[A-ZÉÈÀÂÎÔÛ][A-ZÉÈÀÂÎÔÛ'\-]{2,}"
_NOM_TIT = r"[A-ZÉÈ][a-zéèëïîôûçà'\-]{2,}"

# (nom de regle, regex). Ordre : motifs de ligne d'abord.
REGLES_PII: list[tuple[str, re.Pattern[str]]] = [
    ("ligne_patient", re.compile(r"(?im)^\s*(?:patient(?:e)?|nom(?: de naissance)?|pr[ée]nom|date de naissance|ddn|n[ée](?:\(e\))?e? le)\s*[:\-]")),
    ("ne_le", re.compile(r"(?i)\bn[ée]\s*\(?e?\)?\s+(?:[A-Za-zÉÈéè'\-]+\s+)?le\s+\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}")),
    ("identifiant_patient", re.compile(r"(?i)\b(?:NIP|IPP|INS|NIR|IEP)\b\s*[:°n]*\s*\d{3,}|\bn°\s*(?:de\s*)?s[ée]cu\w*\s*:?\s*\d")),
    ("identifiant_praticien", re.compile(r"(?i)\b(?:RPPS|ADELI|FINESS)\b\s*[:°n]*\s*\d{5,}")),
    ("examen_numero", re.compile(r"(?i)\bexamen\s*:\s*[A-Z]{1,3}\s?\d{4,}")),
    ("numero_dossier", re.compile(r"\b[A-Z]{2}\s?\d{5,}\b")),
    ("a_confier", re.compile(r"(?i)\ba confier [àa]\s*:")),
    ("marqueur_logiciel", re.compile(r"TDCHECK|LECTURE SEULE")),
    ("date_numerique", re.compile(r"\b\d{1,2}([/.\-])\d{1,2}\1(?:19|20)?\d{2}\b")),
    ("date_texte", re.compile(rf"(?i)\b\d{{1,2}}(?:er)?\s+(?:{_MOIS})\s+(?:19|20)\d{{2}}\b")),
    ("titre_nom", re.compile(rf"\b(?:Dr|Docteur|Pr|Professeur|Mme|Madame|Monsieur|Mr)\b\.?\s+(?:[A-Za-z]+\s+)?(?:{_NOM_CAP}|{_NOM_TIT})")),
    ("courriel", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("telephone", re.compile(r"\b0[1-9](?:[ .]?\d{2}){4}\b")),
    ("numero_long", re.compile(r"\b\d{7,}\b")),
    ("nom_prenom", re.compile(rf"\b{_NOM_CAP}\s+{_NOM_TIT}\b|\b{_NOM_TIT}\s+{_NOM_CAP}\b")),
]
# « nom_prenom » ne declenche que si le jeton titre est un prenom connu (sinon : « PARAFFINE Technique »).
_REGLE_NOM_PRENOM = "nom_prenom"


# Regles inadaptees a un champ « code » (un code ADICAP complet fait 6 a 14 caracteres alphanumeriques).
REGLES_HORS_CODE: frozenset[str] = frozenset({"numero_long", "numero_dossier"})


def scanner_pii(texte: str, ignorer: frozenset[str] = frozenset()) -> list[dict[str, str]]:
    """Retourne les violations [{regle, extrait}] ; liste vide = texte propre.

    `ignorer` : noms de regles a sauter (champ `code`, voir REGLES_HORS_CODE).
    """
    trouvees: list[dict[str, str]] = []
    if not texte:
        return trouvees
    texte = re.sub(r"https?://\S+", " ", texte)  # les URL de sources (identifiants PubMed...) ne sont pas des numeros patient
    for nom, pat in REGLES_PII:
        if nom in ignorer:
            continue
        for m in pat.finditer(texte):
            if nom == _REGLE_NOM_PRENOM:
                # seul le jeton en Titlecase doit etre un prenom (« Projet MARC » n'est pas un nom)
                jetons = re.findall(r"[A-Za-zÉÈéèëïîôûçà'\-]+", m.group(0))
                titre_case = [j for j in jetons if j[:1].isupper() and j[1:].islower()]
                if not any(normaliser(j) in PRENOMS for j in titre_case):
                    continue
            trouvees.append({"regle": nom, "extrait": m.group(0)[:60]})
    return trouvees


def _phrases(ligne: str) -> list[str]:
    """Decoupe en phrases sans couper apres une abreviation de titre (« Pr. », « Dr. »)."""
    protege = re.sub(r"\b(Dr|Pr|Mme|Mr|St)\.(\s)", "\\1\u0001\\2", ligne)
    return [ph.replace("\u0001", ".") for ph in re.split(r"(?<=[.!?])\s+", protege)]


def purger_pii(texte: str) -> str:
    """Retire d'un texte les motifs identifiants connus (lignes, phrases, dates, numeros).

    Strategie : supprimer la ligne ou la phrase entiere plutot que masquer, pour ne
    pas laisser de gabarit « [nom] » dans une formulation canonique. Le resultat doit
    ensuite passer `scanner_pii` (sinon `verifier_pii` leve).
    """
    if not texte:
        return texte
    # 1. numeros de dossier en parenthese : « (histodiagnostic ML149677) »
    texte = re.sub(r"\s*\((?:[^()]*?\b)?[A-Z]{2}\s?\d{5,}\)", "", texte)
    # 2. lignes entierement identifiantes
    lignes_ok: list[str] = []
    marqueurs = {"ligne_patient", "examen_numero", "a_confier", "marqueur_logiciel", "identifiant_patient",
                 "identifiant_praticien", "ne_le", "numero_dossier"}
    for ligne in texte.split("\n"):
        if any(n in marqueurs and p.search(ligne) for n, p in REGLES_PII):
            continue
        # 3. phrases citant un praticien nominativement (envoi pour avis, concertation)
        pat_nom = dict(REGLES_PII)["titre_nom"]
        if pat_nom.search(ligne):
            ligne = " ".join(ph for ph in _phrases(ligne) if not pat_nom.search(ph))
            # « Le 20/08/2021 Docteur X » : ligne reduite a une date nue
            if not ligne.strip() or re.fullmatch(r"\s*(?:Le\s+)?[\d/.\-\s]*\s*", ligne):
                continue
        lignes_ok.append(ligne)
    texte = "\n".join(lignes_ok)
    # 4. dates : « du 10/04/2019 » -> supprime ; reste -> supprime
    d_num = dict(REGLES_PII)["date_numerique"].pattern
    texte = re.sub(rf"\s+(?:du|le|en date du)\s+{d_num}", "", texte)
    texte = re.sub(d_num, "", texte)
    texte = dict(REGLES_PII)["date_texte"].sub("", texte)
    # 5. nettoyage
    texte = re.sub(r"[ \t]+\n", "\n", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    return texte.strip()


def verifier_pii(texte: str, origine: str) -> str:
    """Purge puis scanne ; leve `ErreurPII` s'il reste quoi que ce soit."""
    if not scanner_pii(texte):
        return texte
    propre = purger_pii(texte)
    residu = scanner_pii(propre)
    if residu:
        raise ErreurPII(f"PII residuelle dans {origine} : {residu[:3]}")
    return propre


_CODE_TERMINOLOGIE = re.compile(r"^snomed:\d{4,9}$")


def scanner_arbre(obj: Any, chemin: str = "", ignorer: frozenset[str] = frozenset({"sha256", "uri", "concept_id"})) -> list[str]:
    """Scanne recursivement toutes les chaines d'une structure ; retourne les violations.

    Les identifiants de terminologie (`snomed:<id>`, `concept_id`) ne sont pas des numeros patient.
    """
    res: list[str] = []
    if isinstance(obj, str):
        if _CODE_TERMINOLOGIE.match(obj):
            return res
        for v in scanner_pii(obj):
            res.append(f"{chemin}: {v['regle']} « {v['extrait']} »")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ignorer:
                continue
            res += scanner_arbre(v, f"{chemin}.{k}", ignorer)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            res += scanner_arbre(v, f"{chemin}[{i}]", ignorer)
    return res


def purger_textes_canoniques(chemin: Path = CANONIQUES) -> dict[str, int]:
    """Purge `textes_canoniques.json` en place (P0 conformite) ; retourne des statistiques."""
    data = json.loads(chemin.read_text(encoding="utf-8"))
    modifies = 0
    for e in data:
        for champ in ("texte", "lesion", "organe"):
            brut = e.get(champ, "")
            if isinstance(brut, str) and scanner_pii(brut):
                nouveau = verifier_pii(brut, f"{chemin.name}[{e.get('lesion', '')[:30]}].{champ}")
                if nouveau != brut:
                    e[champ] = nouveau
                    modifies += 1
    chemin.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"entrees": len(data), "champs_modifies": modifies}


# ===========================================================================
# 2. Utilitaires (prov, slug, ecriture JSON)
# ===========================================================================

class Contexte:
    """Etat partage d'un build."""

    def __init__(self, date_build: str, sortie: Path) -> None:
        self.date: str = date_build
        self.sortie: Path = sortie
        self.sources: dict[str, dict[str, Any]] = {}
        self.textes_scannes: int = 0
        self.avertissements: list[str] = []

    def prov(self, source_id: str, localisation: str, fiabilite: str, confiance: float,
             statut: str = "derive_auto", methode: str = "extraction_automatique",
             **extra: Any) -> dict[str, Any]:
        """Objet `prov` complet (audit 7.3.2)."""
        src = self.sources.get(source_id, {})
        p: dict[str, Any] = {
            "source_id": source_id,
            "localisation": localisation,
            "version_source": src.get("version"),
            "date_extraction": self.date,
            "fiabilite": fiabilite,
            "confiance": round(confiance, 2),
            "statut_validation": statut,
            "valide_par": None,
            "date_validation": None,
            "methode": methode,
            "remplace": None,
        }
        p.update(extra)
        return p


def slug(texte: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", normaliser(texte)).strip("_")
    return s[:max_len].strip("_") or "x"


def sha256_fichier(chemin: Path) -> str | None:
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return None


def rel(chemin: Path) -> str:
    try:
        return str(chemin.relative_to(RACINE))
    except ValueError:
        return str(chemin)


def ecrire_json(ctx: Contexte, nom: str, data: Any, lignes: bool = False) -> None:
    """Ecrit `<sortie>/<nom>.json` de facon deterministe (une entree par ligne si `lignes`)."""
    ctx.sortie.mkdir(parents=True, exist_ok=True)
    chemin = ctx.sortie / f"{nom}.json"
    if lignes and isinstance(data, list):
        corps = "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) for e in data) + "\n]\n"
    elif lignes and isinstance(data, dict):
        parts = []
        for k, v in data.items():
            if isinstance(v, list) and v and not isinstance(v[0], (str, int, float)):
                inner = "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) for e in v) + "\n]"
            else:
                inner = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"{json.dumps(k, ensure_ascii=False)}:{inner}")
        corps = "{\n" + ",\n".join(parts) + "\n}\n"
    else:
        corps = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    chemin.write_text(corps, encoding="utf-8")


def charger_json(chemin: Path, defaut: Any = None) -> Any:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return defaut


# ===========================================================================
# 3. Registre des sources
# ===========================================================================

# Presentation lisible de chaque source : (titre_court <= 70 car., description en une phrase).
# Contrat : le titre court est un titre humain, jamais un nom de fichier de code ni tronque.
PRESENTATION_SOURCES: dict[str, tuple[str, str]] = {
    "src:adicap_2024_10": (
        "ANS · Thésaurus ADICAP (2024-10)",
        "Thésaurus officiel de la codification ADICAP publié par l'Agence du numérique en santé : "
        "référence nationale des codes lésionnels et topographiques."),
    "src:adicap_bible_json": (
        "Catalogue ADICAP de la bible de la pathologiste",
        "Codes ADICAP d'organes et de lésions relevés dans la bible de la pathologiste référente : "
        "usage du laboratoire, partiel, non publié."),
    "src:bible_greg_xlsx": (
        "Bible de la pathologiste · Formulations de référence",
        "Classeur de formulations de comptes rendus tenu par la pathologiste référente (sein, dermato, "
        "os-articulations, tissus mous, neuro) : document interne du laboratoire, non versionné."),
    "src:textes_canoniques_json": (
        "Bible de la pathologiste · Textes canoniques",
        "Formulations de la bible de la pathologiste, purgées de toute donnée patient puis normalisées "
        "par MARC : dérivé automatique d'un document interne."),
    "src:templates_organes_py": (
        "Référentiel interne MARC (à valider)",
        "Gabarits d'organes écrits par l'équipe MARC en s'inspirant des données minimales INCa ; "
        "ils n'ont pas été relus par un pathologiste tiers, d'où une fiabilité C."),
    "src:specimen_type_py": (
        "Règles internes MARC · Applicabilité par prélèvement",
        "Logique écrite par l'équipe MARC qui décide quels champs s'appliquent à une biopsie, une pièce "
        "opératoire ou une cytologie, selon le contexte lésionnel."),
    "src:vocabulaire_acp_py": (
        "Vocabulaire ACP interne MARC (amorce de transcription)",
        "Liste de termes d'anatomopathologie utilisée pour guider la transcription vocale : "
        "vocabulaire interne de MARC."),
    "src:snomed_py_historique": (
        "Correspondances SNOMED CT saisies à la main (à valider)",
        "Table historique de correspondances SNOMED CT saisies à la main par l'équipe MARC, "
        "non vérifiée contre une édition officielle de SNOMED CT."),
    "src:inca_donnees_minimales_2011": (
        "INCa/SFP · Données minimales des CR d'ACP (2011)",
        "Fiches de l'Institut national du cancer et de la Société française de pathologie listant les "
        "données minimales d'un compte rendu par organe ; MARC en utilise une paraphrase structurée, "
        "antérieure à TNM 8 et OMS 5."),
    "src:nomenclatures_scores_veille": (
        "Échelles et scores (Gleason, SBR, Breslow, Bethesda)",
        "Nomenclatures et règles de calcul de scores usuels, issues d'une veille documentaire de MARC ; "
        "à faire confirmer par la pathologiste référente."),
    "src:regles_unites_veille": (
        "Unités et plages plausibles · heuristiques MARC",
        "Conversions d'unités et plages de mesures plausibles issues d'une veille de MARC : "
        "des heuristiques, pas une norme publiée."),
    "src:regles_architecture_cible": (
        "Règles de cohérence C1-C17 · MARC",
        "Catalogue de règles de cohérence entre éléments d'un compte rendu, défini par l'équipe MARC "
        "dans son document d'architecture cible."),
    "src:conventions_cr_acp": (
        "Conventions de rédaction des CR d'ACP",
        "Synthèse par MARC des conventions de structure et de rédaction des comptes rendus (CI-SIS, INCa, "
        "CRFS) ; certains seuils sont cités sans passage de source primaire."),
    "src:codage_d1_d2": (
        "Codage ADICAP D1/D2 · table de la pathologiste",
        "Table des modes de prélèvement et techniques (codes ADICAP D1 et D2) dérivée du lexique de la "
        "pathologiste référente."),
    "src:seed_marc_v3": (
        "Semences MARC v3 (à valider)",
        "Synonymes, variantes de transcription, stations ganglionnaires et plages saisis par l'équipe "
        "MARC à partir de la connaissance du domaine, non encore validés par la pathologiste."),
    "src:docs_bibles_pathologiste": (
        "Bible de la pathologiste · Biopsies",
        "Documents Word de la pathologiste référente décrivant ses formulations de biopsies "
        "(poumon, prostate, côlon, estomac) : documents internes du laboratoire."),
    "src:uicc_tnm8_rcpath": (
        "UICC TNM 8e éd. · seuils pT et pN du sein",
        "Classification TNM 8e édition de l'UICC, seuils de taille tumorale et de ganglions, relevés dans "
        "l'appendice D du Royal College of Pathologists."),
    "src:iccr_datasets": (
        "ICCR · Datasets de cancers",
        "Jeux de données internationaux de comptes rendus de cancers (ICCR) : source de référence "
        "non embarquée, licence restrictive."),
    "src:snomed_ct_release": (
        "SNOMED CT · édition nationale française",
        "Terminologie SNOMED CT distribuée en France par l'ANS : source officielle, non chargée dans MARC "
        "à ce jour."),
}


def construire_sources(ctx: Contexte) -> list[dict[str, Any]]:
    """Registre des sources (7.3.1), y compris celles NON embarquees (statut juridique)."""
    def fichier(p: Path) -> dict[str, Any]:
        h = sha256_fichier(p)
        return {"chemin": rel(p), "sha256": h} if h else {"chemin": rel(p), "sha256": None}

    s: list[dict[str, Any]] = [
        {"id": "src:adicap_2024_10", "type": "officiel", "titre": "Thesaurus de la codification ADICAP, index raisonne des lesions",
         "editeur": "ANS (Agence du Numerique en Sante)", "version": "2024-10", "date_publication": "2024-10-02",
         "url": "https://esante.gouv.fr/produits-services/cgts/adicap", "licence": "Licence Ouverte 2.0 (Etalab)",
         "fichiers": [fichier(DATA / "adicap_ref.json")], "fiabilite": "A", "perimetre": "D1-D8 (9 683 concepts)",
         "contient_pii": False, "embarque": True, "statut_juridique": "libre_reutilisation"},
        {"id": "src:adicap_bible_json", "type": "praticien", "titre": "Catalogue ADICAP de la bible du praticien (57 codes organe, 306 lesions)",
         "editeur": "Praticien referent (derive de Bibles Greg.xlsx)", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "Interne (donnees du praticien)", "fichiers": [fichier(DATA / "adicap_bible.json")], "fiabilite": "B",
         "perimetre": "codes lesion partiels (4 car.) et organe D3", "contient_pii": False, "embarque": True,
         "statut_juridique": "interne"},
        {"id": "src:bible_greg_xlsx", "type": "praticien", "titre": "Bibles Greg.xlsx (formulations de reference d'un praticien)",
         "editeur": "Praticien referent", "version": "non versionne", "date_publication": None, "url": None,
         "licence": "Interne (donnees du praticien)", "fichiers": [fichier(XLSX_BIBLE)], "fiabilite": "B",
         "perimetre": "20 feuilles ; 5 feuilles (SEIN, DERMATO, OS-ARTI, T mous, NEURO) lues par detection d'en-tetes",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "Tout texte est purge puis scanne (PII) a l'ingestion."},
        {"id": "src:textes_canoniques_json", "type": "derive_auto", "titre": "Textes canoniques (653 formulations) purges de toute donnee patient",
         "editeur": "Derive de Bibles Greg.xlsx", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "Interne", "fichiers": [fichier(CANONIQUES)], "fiabilite": "B", "perimetre": "formulations macro/micro/conclusion",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "3 entrees comportaient des en-tetes patient (audit PO-1) : purgees le 2026-11-15."},
        {"id": "src:templates_organes_py", "type": "derive_auto", "titre": "Templates organes (23 organes, 237 champs, donnees minimales INCa)",
         "editeur": "Projet MARC (équipe de développement)", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "Interne", "fichiers": [fichier(BACKEND / "templates_organes.py")], "fiabilite": "C",
         "perimetre": "champs obligatoires par organe", "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "Contenu non relu par un pathologiste tiers (audit PO-1 : B/C)."},
        {"id": "src:specimen_type_py", "type": "derive_auto", "titre": "Logique d'applicabilite des champs et declencheurs de prelevement",
         "editeur": "Projet MARC (équipe de développement)", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "Interne", "fichiers": [fichier(BACKEND / "specimen_type.py")], "fiabilite": "B",
         "perimetre": "matrice champ x prelevement x contexte", "contient_pii": False, "embarque": True, "statut_juridique": "interne"},
        {"id": "src:vocabulaire_acp_py", "type": "derive_auto", "titre": "Termes d'amorce STT (context_bias Voxtral)",
         "editeur": "Projet MARC (équipe de développement)", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "Interne", "fichiers": [fichier(BACKEND / "vocabulaire_acp.py")], "fiabilite": "B",
         "perimetre": "101 termes", "contient_pii": False, "embarque": True, "statut_juridique": "interne"},
        {"id": "src:snomed_py_historique", "type": "derive_auto", "titre": "Correspondances SNOMED CT saisies a la main (25 structures, 19 morphologies)",
         "editeur": "Projet MARC (équipe de développement)", "version": "2026-07", "date_publication": None, "url": None,
         "licence": "SNOMED CT : licence affilie (SNOMED International / ANS) a clarifier", "fichiers": [fichier(BACKEND / "snomed.py")],
         "fiabilite": "C", "perimetre": "suggestions non verifiees contre une release", "contient_pii": False, "embarque": True,
         "statut_juridique": "a_valider_juridiquement"},
        {"id": "src:inca_donnees_minimales_2011", "type": "synthese_web", "titre": "Donnees minimales INCa/SFP des CR d'anatomopathologie (paraphrase structuree, 10 organes)",
         "editeur": "INCa avec SFP", "version": "2011-12", "date_publication": "2011-12",
         "url": "https://www.cancer.fr/Media/files/comptes-rendus-d-anatomopathologie-donnees-minimales-a-renseigner-pour-une-tumeur-primitive",
         "licence": "Copyright INCa : usage personnel non commercial et courtes citations ; autre usage sur demande a l'INCa (service publications)",
         "fichiers": [fichier(WEB / "inca_donnees_minimales.json")], "fiabilite": "C", "perimetre": "champs, enumerations, unites (paraphrase)",
         "contient_pii": False, "embarque": True, "statut_juridique": "a_valider_juridiquement",
         "note": "Antérieur à TNM 8/9 et OMS 5e ed. Accord INCa requis avant production."},
        {"id": "src:nomenclatures_scores_veille", "type": "synthese_web", "titre": "Echelles et scores (Gleason/ISUP, SBR, Breslow, Bethesda, Milan, Paris...)",
         "editeur": "Veille PO-3 (connaissances de reference)", "version": "2026-11-15", "date_publication": "2026-11-15", "url": None,
         "licence": "Nomenclatures citables ; aucun taux de risque embarque", "fichiers": [fichier(WEB / "nomenclatures_scores.json")],
         "fiabilite": "C", "perimetre": "regles de calcul et categories", "contient_pii": False, "embarque": True,
         "statut_juridique": "a_valider_juridiquement"},
        {"id": "src:regles_unites_veille", "type": "synthese_web", "titre": "Unites, conversions et plages plausibles (heuristiques)",
         "editeur": "Veille PO-3", "version": "2026-11-15", "date_publication": "2026-11-15", "url": None, "licence": "Interne",
         "fichiers": [fichier(WEB / "unites_conversions.json")], "fiabilite": "C", "perimetre": "verificateur mm/cm",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "Plages heuristiques non sourcees : a faire valider."},
        {"id": "src:regles_architecture_cible", "type": "officiel_interne", "titre": "Catalogue de regles de coherence C1-C17 (architecture cible)",
         "editeur": "Projet MARC (document d'architecture cible)", "version": "2026", "date_publication": None, "url": None,
         "licence": "Interne", "fichiers": [fichier(RACINE / "docs/specs/spec/Outil_ideal_architecture_cible.md")], "fiabilite": "B",
         "perimetre": "couche 2 deterministe", "contient_pii": False, "embarque": True, "statut_juridique": "interne"},
        {"id": "src:conventions_cr_acp", "type": "synthese_web", "titre": "Conventions de redaction des CR d'ACP (CI-SIS, INCa, CRFS)",
         "editeur": "Projet MARC (document de conventions)", "version": "2026", "date_publication": None, "url": None, "licence": "Interne",
         "fichiers": [fichier(RACINE / "docs/CONVENTIONS_CR_ACP.md")], "fiabilite": "B", "perimetre": "structure du CR, seuils qualite",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "Seuils (12 ganglions colon, 10 sein) cites sans passage de source primaire : fiabilite C pour ces regles."},
        {"id": "src:codage_d1_d2", "type": "praticien", "titre": "Table de codage ADICAP D1/D2 v2.0 (derivee du lexique de la pathologiste)",
         "editeur": "Praticienne referente", "version": "2.0", "date_publication": None, "url": None, "licence": "Interne",
         "fichiers": [fichier(DATA / "codage_d1_d2.json")], "fiabilite": "B", "perimetre": "modes de prelevement et techniques",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne", "note": "Entrees `a_valider` explicites."},
        {"id": "src:seed_marc_v3", "type": "derive_auto", "titre": "Semences curees de la base v3 (synonymes d'organes, variantes STT, stations, plages)",
         "editeur": "Agent sources MARC v3", "version": "3.0.0", "date_publication": ctx.date, "url": None, "licence": "Interne",
         "fichiers": [{"chemin": rel(SEEDS), "sha256": hashlib.sha256(b"".join(
             f.read_bytes() for f in sorted(SEEDS.glob("*.json")))).hexdigest()}],
         "fiabilite": "C", "perimetre": "semences backend/kb/seeds/",
         "contient_pii": False, "embarque": True, "statut_juridique": "interne",
         "note": "Connaissance du domaine non re-verifiee : tout est `a_valider` par la pathologiste."},
        {"id": "src:docs_bibles_pathologiste", "type": "praticien", "titre": "Bibles de la pathologiste : biopsies",
         "editeur": "Praticienne referente / service HML", "version": "non versionne", "date_publication": None, "url": None,
         "licence": "Interne (documents de l'utilisateur)",
         "fichiers": [fichier(RACINE / "Ressources/1. Codes Bible/1. Thorax/1. Poumon/Biopsies.docx"),
                      fichier(RACINE / "Ressources/1. Codes Bible/6. Urologie/1. Prostate/BIOPSIES PROSTATIQUES.docx"),
                      fichier(RACINE / "Ressources/1. Codes Bible/Bibles HML/BIOPSIES COLIQUES.docx"),
                      fichier(RACINE / "Ressources/1. Codes Bible/Bibles HML/Biopsies gastriques.docx")],
         "fiabilite": "B", "perimetre": "formulations de biopsies ; peu de dimensions chiffrees (carottes 18G de 6 et 17 mm, polype de 8 mm)",
         "contient_pii": False, "embarque": False, "statut_juridique": "interne",
         "note": "Fichiers non embarques (empreintes seules). Les plages derivees restent des heuristiques a valider par la pathologiste referente."},
        {"id": "src:uicc_tnm8_rcpath", "type": "officiel", "titre": "UICC TNM 8e ed., sein : seuils pT et pN (RCPath, appendice D)",
         "editeur": "UICC / Royal College of Pathologists", "version": "TNM 8", "date_publication": "2018", "url": "https://www.rcpath.org/asset/FEF52EB5-DEC0-4B48-9438289B086FF3F9/",
         "licence": "Seuils numeriques cites ; texte non embarque", "fichiers": [], "fiabilite": "A",
         "perimetre": "pT1a >1-5 mm, pT1b >5-10, pT1c >10-20, pT2 >20-50, pT3 >50 ; pN1 1-3, pN2 4-9, pN3 >=10 ganglions axillaires",
         "contient_pii": False, "embarque": False, "statut_juridique": "citation_courte",
         "note": "Seuils sein verifies sur la page ; seuils poumon/colon/estomac issus de la connaissance du domaine (TNM 8, UICC) : a valider."},
        {"id": "src:iccr_datasets", "type": "officiel", "titre": "ICCR cancer datasets (core / non-core)", "editeur": "ICCR",
         "version": "continu (aligne UICC TNM 9)", "date_publication": None, "url": "https://www.iccr-cancer.org/datasets/",
         "licence": "Copyright ICCR : CR chirurgicaux, enseignement, recherche non lucrative ; commerce exclu",
         "fichiers": [], "fiabilite": "A", "perimetre": "NON embarque", "contient_pii": False, "embarque": False,
         "statut_juridique": "bloquant_a_lever"},
        {"id": "src:snomed_ct_release", "type": "officiel", "titre": "SNOMED CT (edition nationale francaise via SMT/ANS)",
         "editeur": "SNOMED International / ANS", "version": "non charge", "date_publication": None,
         "url": "https://smt.esante.gouv.fr/", "licence": "Licence affilie gratuite (ANS) ; pas de redistribution libre",
         "fichiers": [], "fiabilite": "A", "perimetre": "NON embarque : aucun code verifie contre une release", "contient_pii": False,
         "embarque": False, "statut_juridique": "a_valider_juridiquement"},
    ]
    for e in s:
        titre_court, description = PRESENTATION_SOURCES[e["id"]]
        e["titre_court"] = titre_court
        e["description"] = description
        ctx.sources[e["id"]] = e
    return s


# ===========================================================================
# 4. ADICAP : thesaurus compact et verificateurs
# ===========================================================================

class Thesaurus:
    """Index du thesaurus ADICAP 2024-10 (lu depuis backend/data/adicap_ref.json)."""

    def __init__(self) -> None:
        ref = charger_json(DATA / "adicap_ref.json", {})
        self.version: str = ref.get("version", "")
        self.colonnes: list[str] = ref.get("colonnes", [])
        self.concepts: list[list[str]] = ref.get("concepts", [])
        self.par_dict_code: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
        for c in self.concepts:
            self.par_dict_code[(c[3], c[1])].append(c)

    def existe(self, dico: str, code: str) -> list[list[str]]:
        return self.par_dict_code.get((dico, code), [])

    def actif(self, dico: str, code: str) -> bool:
        """Existe et au moins une occurrence sans date de fin de validite."""
        return any(not c[5] for c in self.existe(dico, code))

    def libelle(self, dico: str, code: str) -> str:
        ex = self.existe(dico, code)
        return ex[0][4] if ex else ""

    def d1_actif(self, lettre: str) -> bool:
        # certains codes D1/D2 portent l'URI comme `code` (D1A, D1E, D1M) dans l'export
        return self.actif("D1", lettre) or self.actif("D1", f"D1{lettre}")

    def resoudre_lesion(self, d3: str | None, code: str) -> tuple[str, list[str]] | None:
        """Premier concept ACTIF correspondant a un code lesion, sinon None.

        Un code lesion de 4 caracteres vit dans D4 (non tumoral), D5 (tumoral) ou D7 (cytopathologie
        generique) ; un code organe-specifique de 6 caracteres (D3 + 4) dans D6, D7 ou D5.
        """
        for dico in ("D4", "D5", "D7"):
            for c in self.existe(dico, code):
                if not c[5]:
                    return dico, c
        if d3:
            for dico in ("D6", "D7", "D5"):
                for c in self.existe(dico, d3 + code):
                    if not c[5]:
                        return dico, c
        return None

    def lesion_existe(self, code: str, d3: str | None = None) -> tuple[bool, bool]:
        """(existe, actif) pour un code lesion (4 car.) eventuellement complete par l'organe D3."""
        if self.resoudre_lesion(d3, code):
            return True, True
        occ = [c for d in ("D4", "D5", "D7") for c in self.existe(d, code)]
        if d3:
            occ += [c for d in ("D6", "D7", "D5") for c in self.existe(d, d3 + code)]
        return bool(occ), False


def construire_thesaurus(ctx: Contexte, th: Thesaurus) -> dict[str, Any]:
    return {
        "version": th.version,
        "colonnes": ["uri", "code", "parent", "dictionnaire", "libelle", "fin_validite", "anatomie"],
        "prov_commune": ctx.prov("src:adicap_2024_10", "ADICAP_2024.xlsx, feuille adicapV3", "A", 1.0, statut="valide",
                                 methode="import_officiel"),
        "concepts": th.concepts,
    }


# ===========================================================================
# 5. Lecture robuste de la bible Excel (5 feuilles perdues)
# ===========================================================================

FEUILLES_PERDUES = ("SEIN", "DERMATO", "OS-ARTI", "T mous", "NEURO")
_RE_CODE = re.compile(r"^(?:[A-Z]{2}\s*)?[0-9A-Z]{4}(?:\s*[-/,;]\s*(?:[A-Z]{2}\s*)?[0-9A-Z]{4})*$")


def _ressemble_a_un_code(cell: str) -> bool:
    c = cell.strip().upper()
    return bool(c) and len(c) <= 18 and any(ch.isdigit() for ch in c) and bool(_RE_CODE.match(c.replace("\n", " ")))


def lire_feuille_robuste(ws: Any, nom: str) -> list[dict[str, Any]]:
    """Lit une feuille sans supposer la disposition des colonnes.

    1) detecte une ligne d'en-tetes (« Lésion (lib) », « Lésion (ref) », « Texte », « Topo ») ;
    2) sinon, par ligne : texte = cellule la plus longue (>= 40 car.), code = cellule
       courte ressemblant a un code ADICAP, lesion = premiere autre cellule significative.
    Gere 2, 3, 4 ou 8 colonnes (corrige la perte d'ingestion de l'audit PO-1, 5.2).
    """
    rows = [[("" if c is None else str(c).strip()) for c in r] for r in ws.iter_rows(values_only=True)]
    colonnes: dict[str, int] = {}
    debut = 0
    for i, r in enumerate(rows[:3]):
        norm = [normaliser(c) for c in r]
        if any(c == "texte" for c in norm):
            for j, c in enumerate(norm):
                if c.startswith("lesion (lib") or c.startswith("lesion (libelle"):
                    colonnes["lesion"] = j
                elif c.startswith("lesion (ref"):
                    colonnes["code"] = j
                elif c == "texte":
                    colonnes["texte"] = j
                elif c in ("topo", "organe"):
                    colonnes["organe"] = j
            debut = i + 1
            break
    sortie: list[dict[str, Any]] = []
    for idx, r in enumerate(rows[debut:], start=debut + 1):
        if not any(r):
            continue
        if colonnes.get("texte") is not None and colonnes["texte"] < len(r):
            texte = r[colonnes["texte"]]
            lesion = r[colonnes["lesion"]] if "lesion" in colonnes and colonnes["lesion"] < len(r) else ""
            code = r[colonnes["code"]] if "code" in colonnes and colonnes["code"] < len(r) else ""
            organe = r[colonnes["organe"]] if "organe" in colonnes and colonnes["organe"] < len(r) else ""
        else:
            j_texte = max(range(len(r)), key=lambda j: len(r[j]))
            texte = r[j_texte]
            avant = [c for c in r[:j_texte] if c]
            code = next((c for c in avant if _ressemble_a_un_code(c)), "")
            reste = [c for c in avant if c != code]
            lesion = reste[0] if reste else ""
            organe = ""
        if len(texte) < 40 or not lesion:
            continue
        sortie.append({"feuille": nom, "ligne": idx, "organe": organe, "lesion": re.sub(r"\s+", " ", lesion).strip(),
                       "code_brut": code, "texte": re.sub(r"[ \t]+", " ", texte).strip()})
    return sortie


def lire_feuilles_perdues(ctx: Contexte) -> list[dict[str, Any]]:
    """Charge les 5 feuilles perdues si le classeur est present ; sinon liste vide (repli)."""
    if not XLSX_BIBLE.exists():
        ctx.avertissements.append("Bibles Greg.xlsx absent : feuilles SEIN/DERMATO/OS-ARTI/T mous/NEURO non reprises")
        return []
    try:
        import openpyxl  # type: ignore[import-untyped]
    except ImportError:
        ctx.avertissements.append("openpyxl absent : feuilles perdues non reprises")
        return []
    wb = openpyxl.load_workbook(str(XLSX_BIBLE), read_only=True, data_only=True)
    entrees: list[dict[str, Any]] = []
    for nom in FEUILLES_PERDUES:
        if nom in wb.sheetnames:
            entrees += lire_feuille_robuste(wb[nom], nom)
    return entrees


# ===========================================================================
# 6. Organes
# ===========================================================================

def construire_organes(ctx: Contexte, th: Thesaurus) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from templates_organes import TOUS_LES_TEMPLATES  # noqa: PLC0415
    import snomed as snomed_mod  # noqa: PLC0415

    seed = charger_json(SEEDS / "organes.json", {})
    tpls = {t.organe: t for t in TOUS_LES_TEMPLATES}
    organes: list[dict[str, Any]] = []
    for s in seed["organes"]:
        d3 = []
        for code in s["adicap_d3"]:
            if not th.actif("D3", code):
                raise RuntimeError(f"code ADICAP D3 {code} ({s['id']}) inconnu ou obsolete")
            d3.append(code)
        tpl = tpls.get(s["template"]) if s.get("template") else None
        body = snomed_mod._BODY_STRUCTURES.get(s["snomed_cle"]) if s.get("snomed_cle") else None  # noqa: SLF001
        o: dict[str, Any] = {
            "id": f"organe:{s['id']}",
            "libelle": s["libelle"],
            "synonymes": sorted(set(s["synonymes"])),
            "mots_cles_faibles": sorted(set(s.get("mots_cles_faibles", []))),
            "categorie": s["categorie"],
            "parent": None,
            "adicap_d3": d3,
            "adicap_d3_libelles": [th.libelle("D3", c) for c in d3],
            "snomed_body_structure": [f"snomed:{body['code']}"] if body else [],
            "cim_o_topographie": s.get("cim_o_topographie", []),
            "staging": [{"nom": tpl.systeme_staging, "statut": "a_verifier"}] if tpl and tpl.systeme_staging else [],
            "marqueurs_ihc": list(tpl.marqueurs_ihc) if tpl else [],
            "sous_types_prelevement": list(tpl.sous_types) if tpl else [],
            "template_source": f"TEMPLATE_{tpl.organe.upper()}" if tpl else None,
            "prov": ctx.prov("src:seed_marc_v3", f"seeds/organes.json#{s['id']}", "C", 0.6, statut="a_valider",
                             methode="semence_curee"),
        }
        organes.append(o)
    generique = seed["organe_generique"]
    organes.append({
        "id": "organe:generique", "libelle": generique["libelle"], "synonymes": [], "mots_cles_faibles": [],
        "categorie": "generique", "parent": None, "adicap_d3": [], "adicap_d3_libelles": [], "snomed_body_structure": [],
        "cim_o_topographie": [], "staging": [], "marqueurs_ihc": [], "sous_types_prelevement": [], "template_source": None,
        "prov": ctx.prov("src:seed_marc_v3", "seeds/organes.json#generique", "C", 0.6, statut="a_valider", methode="semence_curee"),
    })
    return organes, seed


# ===========================================================================
# 7. Prelevements
# ===========================================================================

def construire_prelevements(ctx: Contexte, th: Thesaurus) -> list[dict[str, Any]]:
    import specimen_type as st  # noqa: PLC0415

    defs = [
        ("biopsie", "Biopsie", "biopsie", ["P", "H", "B", "T"], [], st._BIOPSIE_KEYWORDS,  # noqa: SLF001
         ["microbiopsie", "macrobiopsie", "carotte", "ponction-biopsie"]),
        ("piece_operatoire", "Pièce opératoire", "piece_operatoire", ["I", "O"], [], st._PIECE_KEYWORDS, []),  # noqa: SLF001
        ("cytologie", "Cytologie", "cytologie", ["C", "G", "F", "L", "R", "A", "S", "E"], [], st._CYTOLOGIE_KEYWORDS, []),  # noqa: SLF001
        ("curage", "Curage ganglionnaire", "curage", ["I"], [], st._CURAGE_KEYWORDS, []),  # noqa: SLF001
        ("extemporane", "Examen extemporané", "extemporane", [], ["E"], ["extemporane", "extempo", "examen extemporane"], []),
        ("autre", "Autre (curetage, résection endoscopique, expulsé...)", "autre", ["K", "M", "N", "X", "V"], [], ["curetage", "resection endoscopique", "mucosectomie", "rtu"], []),
        ("indetermine", "Prélèvement non précisé", "indetermine", [], [], [], []),
    ]
    out: list[dict[str, Any]] = []
    for pid, lib, classe, d1, d2, decl, variantes in defs:
        for lettre in d1:
            if not th.d1_actif(lettre):
                raise RuntimeError(f"code ADICAP D1 {lettre} inconnu ou obsolete")
        for lettre in d2:
            if not (th.actif("D2", lettre) or th.actif("D2", f"D2{lettre}")):
                raise RuntimeError(f"code ADICAP D2 {lettre} inconnu ou obsolete")
        out.append({
            "id": f"prelevement:{pid}", "libelle": lib, "classe": classe,
            "variantes": variantes, "declencheurs": sorted(set(decl)),
            "adicap_d1": d1, "adicap_d2": d2,
            "regles_codage_ref": "src:codage_d1_d2",
            "prov": ctx.prov("src:specimen_type_py", f"Règles d'applicabilité, prélèvement de classe « {classe} »", "B", 0.7, statut="derive_auto"),
        })
    return out


# ===========================================================================
# 8. Champs par organe x prelevement x contexte lesionnel
# ===========================================================================

# (concept, regex sur nom normalise). Premier qui correspond.
CONCEPTS: list[tuple[str, str]] = [
    ("ptnm", r"\bptnm\b|^ptpn|stade ann arbor|^pt / pn"),
    ("effraction_capsulaire", r"effraction capsulaire"),
    ("rupture_capsulaire", r"rupture capsulaire"),
    ("ganglions", r"ganglion"),
    ("longueur_tumorale_carotte", r"longueur tumorale"),
    ("nb_carottes", r"nombre de biopsies positives|carottes positives"),
    ("taille_tumorale", r"^taille (tumorale|lesionnelle|de la|du ccis)|taille de la composante"),
    ("marges", r"^marges?\b|^limites|marge circonf"),
    ("emboles", r"embole"),
    ("engainements", r"engainement|perinerveu"),
    ("profondeur_invasion", r"profondeur d'invasion|invasion myometriale|infiltration du myometre"),
    ("invasion", r"^invasion|^extension|niveau d'infiltration|infiltration"),
    ("pattern", r"pattern|sous-type|variantes histologiques|composantes"),
    ("type_histologique", r"^type histologique|^site anatomique"),
    ("grade_sbr", r"grade sbr"),
    ("grade_figo", r"grade figo"),
    ("grade_isup", r"grade nucleaire isup|score de gleason|grade isup"),
    ("grade_fnclcc", r"grade fnclcc"),
    ("grade", r"grade|differenciation|lauren"),
    ("ki67", r"ki-?67"),
    ("pdl1", r"pd-?l1"),
    ("recepteurs_hormonaux", r"statut re\b|statut rp\b|recepteurs hormonaux"),
    ("her2", r"her2"),
    ("mmr", r"mmr|msi"),
    ("biologie_moleculaire", r"biologie moleculaire|kras|braf|brca|egfr|codeletion|mgmt|fish|idh1|h3k27m|atrx"),
    ("ihc", r"p16|p53|claudin|immunophenotype|ihc|statut ebv"),
    ("breslow", r"breslow"),
    ("index_mitotique", r"index mitotique"),
    ("necrose", r"necrose"),
    ("ulceration", r"ulceration"),
    ("regression", r"regression|\btrg\b"),
    ("microsatellitose", r"microsatellitose"),
]
_CONCEPTS_RE = [(c, re.compile(p)) for c, p in CONCEPTS]

# Alias de concept pour les items INCa (cle = id INCa en minuscules).
_INCA_ALIAS: dict[str, str] = {
    "type_histologique": "type_histologique", "grade_sbr": "grade_sbr", "marges": "marges", "limites": "marges",
    "emboles": "emboles", "ganglions": "ganglions", "ptpn": "ptnm", "ptpn_figo": "ptnm", "her2": "her2",
    "rh": "recepteurs_hormonaux", "taille_infiltrant": "taille_tumorale", "ccis_taille": "taille_tumorale_ccis",
    "grade": "grade", "corps_myometre": "profondeur_invasion",
}

# (concept, type_valeur, unite, options, plages). Ordre sans importance (cle = concept).
_TYPES: dict[str, tuple[str, str | None, list[str], list[str]]] = {
    "ptnm": ("texte_libre", None, [], []),
    "ganglions": ("liste_structuree", None, [], ["ganglions_examines", "ganglions_envahis"]),
    "effraction_capsulaire": ("enum", None, ["présente", "absente", "non évaluable"], []),
    "rupture_capsulaire": ("enum", None, ["présente", "absente"], []),
    "taille_tumorale": ("nombre_unite", "mm", [], ["taille_tumorale"]),
    "longueur_tumorale_carotte": ("nombre_unite", "mm", [], ["longueur_tumorale_carotte"]),
    "nb_carottes": ("nombre_unite", "nombre", [], ["nb_carottes"]),
    "marges": ("enum_nombre", "mm", ["saines", "atteintes", "non évaluables"], ["marge"]),
    "emboles": ("enum", None, ["présents", "absents", "non évaluables"], []),
    "engainements": ("enum", None, ["présents", "absents", "non évaluables"], []),
    "profondeur_invasion": ("nombre_unite", "mm", [], ["profondeur_invasion"]),
    "invasion": ("enum", None, ["présente", "absente", "non évaluable"], []),
    "pattern": ("texte_libre", None, [], []),
    "type_histologique": ("texte_libre", None, [], []),
    "grade_sbr": ("enum", None, ["I", "II", "III"], ["grade_sbr_total"]),
    "grade_figo": ("enum", None, ["1", "2", "3"], []),
    "grade_isup": ("score", None, [], ["gleason_total", "grade_isup"]),
    "grade_fnclcc": ("enum", None, ["1", "2", "3"], []),
    "grade": ("texte_libre", None, [], []),
    "ki67": ("nombre_unite", "%", [], ["ki67"]),
    "pdl1": ("nombre_unite", "%", [], ["pdl1"]),
    "recepteurs_hormonaux": ("enum_nombre", "%", ["positifs", "négatifs"], ["recepteurs_hormonaux"]),
    "her2": ("enum", None, ["0", "1+", "2+", "3+"], []),
    "mmr": ("enum", None, ["expression conservée (pMMR)", "perte d'expression (dMMR)"], []),
    "biologie_moleculaire": ("texte_libre", None, [], []),
    "ihc": ("texte_libre", None, [], []),
    "breslow": ("nombre_unite", "mm", [], ["breslow"]),
    "index_mitotique": ("nombre_unite", "mitoses/mm2", [], ["index_mitotique"]),
    "necrose": ("enum", None, ["présente", "absente"], []),
    "ulceration": ("enum", None, ["présente", "absente"], []),
    "regression": ("texte_libre", None, [], []),
    "microsatellitose": ("enum", None, ["présente", "absente"], []),
}

# Champs NON tumoraux : conserves sur une lesion benigne.
_NON_TUMORAL = re.compile(
    r"etat de la muqueuse|presence de calculs|type d'appendicite|recherche de tumeur|topographie \(sydney\)|"
    r"inflammation chronique|^activite|atrophie glandulaire|metaplasie intestinale|helicobacter|foie non tumoral|"
    r"barrett associe|^type de prelevement|^cote\b|^localisation"
)
# Sections ou un champ est pertinent en cytologie.
_CYTO_CONCEPTS = {"type_histologique", "grade", "grade_figo", "grade_isup", "ihc", "biologie_moleculaire", "her2",
                  "recepteurs_hormonaux", "ki67", "pdl1", "mmr", "pattern"}
_GANGLION_CONCEPTS = {"effraction_capsulaire", "ganglions"}


def concept_de(nom: str) -> str:
    n = normaliser(nom)
    for concept, pat in _CONCEPTS_RE:
        if pat.search(n):
            return concept
    return "autre"


def _applicabilite(nom: str, concept: str, tumoral: bool) -> dict[str, list[str]]:
    """Matrice prelevement -> contextes ou le champ s'applique (migree de specimen_type.py)."""
    import specimen_type as st  # noqa: PLC0415
    ctx_enum = {"benin": st.DiagnosticContext.BENIN, "precancereux": st.DiagnosticContext.PRE_CANCEREUX,
                "malin": st.DiagnosticContext.INFILTRANT, "indetermine": st.DiagnosticContext.INDETERMINE}
    prel_enum = {"biopsie": st.SpecimenType.BIOPSIE, "piece_operatoire": st.SpecimenType.PIECE_OPERATOIRE,
                 "cytologie": st.SpecimenType.CYTOLOGIE, "indetermine": st.SpecimenType.INDETERMINE}
    res: dict[str, list[str]] = {}
    for p in PRELEVEMENTS_IDS:
        ok_ctx: list[str] = []
        for c in CONTEXTES_IDS:
            if c == "benin" and tumoral:
                continue  # regle metier : jamais de champ tumoral sur une lesion benigne
            if p == "curage":
                # le curage ne porte que les champs ganglionnaires ; piece-only s'applique
                ok = concept in _GANGLION_CONCEPTS and (c != "benin")
            elif p == "cytologie":
                ok = (concept in _CYTO_CONCEPTS or not tumoral) and st.champ_applicable(nom, prel_enum[p], ctx_enum[c])
            else:
                ok = st.champ_applicable(nom, prel_enum[p], ctx_enum[c])
            if ok:
                ok_ctx.append(c)
        if ok_ctx:
            res[p] = ok_ctx
    return res


def _champ(ctx: Contexte, organe: str, nom: str, section: str, obligatoire: bool, exemple: str,
           mots_cles: list[str], ordre: int, loc: str, deja: set[str]) -> dict[str, Any]:
    n = normaliser(nom)
    concept = concept_de(nom)
    type_valeur, unite, options, plages = _TYPES.get(concept, ("texte_libre", None, [], []))
    # raffinements par nom
    if concept == "marges" and re.search(r"marge (proximale|distale|circonf)|crm", n):
        type_valeur, options = "nombre_unite", []
    if concept == "pdl1" and "cps" in n:
        type_valeur, unite, plages = "score", None, []
    if concept == "grade_isup" and "isup/oms" in n:
        type_valeur, options = "enum", ["1", "2", "3", "4"]
    if concept == "grade" and "oms" in n:
        options = ["1", "2", "3", "4"]
        type_valeur = "enum"
    tumoral = not _NON_TUMORAL.search(n)
    base = slug(nom, 50)
    cid = f"champ:{organe}.{base}"
    k = 2
    while cid in deja:
        cid = f"champ:{organe}.{base}_{k}"
        k += 1
    deja.add(cid)
    niveau = "obligatoire_local" if obligatoire else "recommande"
    return {
        "id": cid, "organe_id": f"organe:{organe}", "libelle": nom, "concept": concept, "section": section,
        "obligatoire": obligatoire, "niveau": niveau, "type": type_valeur, "unite": unite, "options": list(options),
        "plages": list(plages), "condition": None, "tumoral": tumoral, "ordre": ordre,
        "detection": {"mots_cles": mots_cles},
        "exemple_formulation": exemple,
        "origine": "templates_organes",
        "applicabilite": _applicabilite(nom, concept, tumoral),
        "prov": ctx.prov("src:templates_organes_py", loc, "C", 0.6, statut="derive_auto"),
    }


def _condition_inca(cond: str | None) -> tuple[list[str] | None, str | None]:
    """Condition INCa (texte) -> (prelevements restreints | None, condition lisible)."""
    if not cond:
        return None, None
    n = normaliser(cond)
    prel: list[str] | None = None
    if "piece" in n and "biopsie" not in n:
        prel = ["piece_operatoire"]
    elif "biopsie" in n and "piece" not in n:
        prel = ["biopsie"]
    return prel, cond


def _condition_residuelle(cond: str | None) -> bool:
    """True si la condition INCa porte une exigence AU-DELA du prelevement (« si neoadjuvant »...)."""
    if not cond:
        return False
    n = normaliser(cond)
    for mot in ("sur biopsie", "sinon sur piece operatoire", "piece operatoire", "pieces operatoires", "biopsies", "biopsie",
                "pour", "corps", "col", "sur"):
        n = re.sub(rf"\b{mot}\b", " ", n)
    return bool(re.search(r"[a-z]{4,}", n))


def _prelevements_fiche(contextes: list[str]) -> list[str] | None:
    """Prelevements couverts par une fiche INCa ; None = tous."""
    n = " ".join(normaliser(c) for c in contextes)
    if "piece" in n and "biopsie" not in n:
        return ["piece_operatoire"]
    return None


def _inca_organes(nom: str) -> list[str]:
    n = normaliser(nom)
    table = {"sein": ["sein"], "colon-rectum": ["colon_rectum"], "poumon": ["poumon"], "prostate": ["prostate"],
             "peau - melanome cutane": ["melanome"], "thyroide": ["thyroide"], "vessie": ["vessie"], "rein": ["rein"],
             "col uterin et endometre (corps uterin)": ["col_uterin", "endometre"], "estomac": ["estomac"]}
    return table.get(n, [])


#: Items INCa dont le libelle source dit que la notion n'est PAS utilisee (« Grade : non utilise »,
#: « non reconnu ») : jamais reclames comme champ obligatoire.
_ITEM_INCA_NON_UTILISE = re.compile(r"non utilis|non reconnu")

#: Raffinements des champs issus UNIQUEMENT de la fiche INCa (libelle trop tronque, mots-cles absents).
#: Cle « organe.item_inca » -> libelle lisible et mots-cles de detection (dictee normalisee).
_RAFFINEMENTS_INCA: dict[str, dict[str, Any]] = {
    "col_uterin.grade": {"libelle": "Grade histopronostique (col)", "mots": ["grade histopronostique", "figo", "differenciation", "differencie"]},
    "col_uterin.col_invasif": {"libelle": "Carcinome invasif du col : plus grand diamètre et profondeur d'invasion",
                               "mots": ["profondeur d'invasion", "profondeur d'infiltration", "plus grand diametre", "invasion stromale"]},
    "col_uterin.col_extension": {"libelle": "Extension extra-cervicale (vagin, paramètres, paroi pelvienne)",
                                 "mots": ["extension extra-cervicale", "extra-cervical", "vagin", "parametre", "paroi pelvienne"]},
    "endometre.corps_serieuse": {"libelle": "Séreuse utérine et extension extra-corporéale",
                                 "mots": ["serosa", "sereuse", "extension extra-corporeale", "annexes", "ovaire", "trompe"]},
    "colon_rectum.tranche_distale": {"libelle": "État de la tranche de section distale",
                                     "mots": ["tranche de section", "section distale", "recoupe distale", "limite distale",
                                              "limites chirurgicales", "limites d'exerese", "recoupes"]},
    "colon_rectum.infiltration_paroi": {"libelle": "Degré d'infiltration de la paroi et du péri-colorectal",
                                        "mots": ["sous-sereuse", "sous sereuse", "sous-muqueuse", "musculeuse", "sereuse",
                                                 "graisse peri", "tissu peri", "peri-colique", "peri-rectal"]},
    "colon_rectum.perforation": {"libelle": "Perforation en zone tumorale", "mots": ["perforation", "perfore"]},
    "colon_rectum.depots_meso": {"libelle": "Dépôts tumoraux dans le méso",
                                 "mots": ["depots tumoraux", "depot tumoral", "nodule de permeation", "nodules tumoraux", "meso"]},
    "estomac.limite_proximale": {"libelle": "Limite proximale (saine ou envahie)",
                                 "mots": ["limite proximale", "recoupe proximale", "marge proximale", "limites chirurgicales", "limites d'exerese"]},
    "estomac.limite_distale": {"libelle": "Limite distale (saine ou envahie)",
                               "mots": ["limite distale", "recoupe distale", "marge distale", "limites chirurgicales", "limites d'exerese"]},
    "estomac.infiltration_paroi": {"libelle": "Degré d'infiltration de la paroi gastrique",
                                   "mots": ["sous-sereuse", "sous sereuse", "sous-muqueuse", "musculeuse", "sereuse", "muqueuse", "chorion"]},
    "melanome.siege": {"libelle": "Siège", "mots": ["siege", "dos", "cuir chevelu", "membre", "jambe", "bras", "thorax", "visage",
                                                      "joue", "cou", "abdomen", "epaule", "cuisse", "mollet", "pied", "main"]},
    "melanome.exerese_complete": {"libelle": "Exérèse complète (latéralement, en profondeur)",
                                  "mots": ["exerese complete", "exerese incomplete", "marges", "berges", "limites", "recoupe"]},
    "poumon.section_bronchique": {"libelle": "État de la tranche bronchique et des recoupes vasculaires",
                                  "mots": ["tranche bronchique", "section bronchique", "recoupe bronchique", "recoupes vasculaires"]},
    "poumon.limites_pleure": {"libelle": "État des limites pleurales", "mots": ["limite pleurale", "limites pleurales", "plevre", "pleurale"]},
    "poumon.distance_section_bronchique": {"libelle": "Distance à la section bronchique",
                                           "mots": ["distance a la section bronchique", "distance de la section bronchique", "section bronchique"]},
    "poumon.extension_mediastin": {"libelle": "Extension aux organes du médiastin", "mots": ["mediastin"]},
    "poumon.nombre_tumeurs": {"libelle": "Nombre de tumeurs",
                              "mots": ["nombre de tumeurs", "tumeur unique", "lesion unique", "nodule unique", "foyers", "multifocal", "deux tumeurs"]},
    "prostate.type_histologique": {"libelle": "Type histologique", "mots": ["adenocarcinome", "acineux", "canalaire", "carcinome"]},
    "rein.grade": {"libelle": "Grade nucléaire (Fuhrman / ISUP)", "mots": ["fuhrman", "isup", "grade nucleaire"]},
    "rein.voie_excretrice": {"libelle": "Voie excrétrice saine ou envahie", "mots": ["voie excretrice", "cavites pyelocalicielles", "bassinet", "pyelon", "calice"]},
    "rein.surrenale_2": {"libelle": "Surrénale", "mots": ["surrenale", "surrenal"]},
    "rein.thrombus": {"libelle": "Thrombus veineux (veine rénale, veine cave)", "mots": ["thrombus", "veine renale", "veine cave"]},
    "rein.emboles": {"libelle": "Emboles vasculaires", "mots": ["embole", "invasion vasculaire", "invasion veineuse"]},
    "rein.ganglions": {"libelle": "Ganglions régionaux envahis (si prélevés)", "mots": ["ganglion", "curage", "adenopathie"]},
    "sein.ccis_grade_nucleaire": {"libelle": "Grade nucléaire du CCIS",
                                  "mots": ["grade nucleaire", "bas grade", "haut grade", "grade intermediaire", "faible grade", "grade bas", "grade haut"]},
    "sein.ccis_microinvasion": {"libelle": "Micro-invasion", "mots": ["microinvasion", "micro-invasion", "micro invasion", "microinvasif", "micro-invasif"]},
    "sein.foyers_multiples": {"libelle": "Foyers infiltrants multiples (unifocal ou multifocal)",
                              "mots": ["foyers multiples", "multifocal", "multicentrique", "foyer unique", "unifocal", "foyers infiltrants", "un seul foyer"]},
    "thyroide.capsule": {"libelle": "État de la capsule de la lésion", "mots": ["capsule", "capsulaire", "encapsule", "effraction capsulaire"]},
    "thyroide.multifocalite_2": {"libelle": "Multifocalité", "mots": ["multifocal", "unifocal", "plurifocal", "foyer unique", "foyers"]},
    "vessie.tumeur_residuelle": {"libelle": "Absence de tumeur résiduelle",
                                 "mots": ["tumeur residuelle", "absence de tumeur residuelle", "pas de tumeur residuelle", "sans tumeur residuelle"]},
}

#: Champs RESERVES a une topographie : n'ont de sens que si l'un des termes figure dans la dictee
#: (mesorectum et CRM : rectum seulement, jamais pour un colon droit ou gauche).
_REQUIERT_TEXTE: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"mesorectum|^marge circonferentielle|\bcrm\b"),
     ["rectum", "rectal", "recto", "mesorectum", "amputation abdomino"]),
]

#: Concepts non reclames sur biopsie (invasion vasculaire/lymphatique non exigee sur un fragment).
_CONCEPTS_NON_BIOPSIE = {"emboles"}
_GENERIQUES_LIBELLE = {"tumorale", "tumeur", "etat", "degre", "saine", "saines", "envahie", "envahis", "regionaux", "prelevés"}


def _mots_depuis_libelle(lib: str) -> list[str]:
    """Repli : mots porteurs (>= 6 lettres) du libelle, comme mots-cles de detection."""
    mots: list[str] = []
    for m in re.findall(r"[a-zà-ÿ'\-]{6,}", lib.lower()):
        n = normaliser(m)
        if n not in _GENERIQUES_LIBELLE and n not in mots:
            mots.append(n)
    return mots[:4]


def _exclusions() -> list[dict[str, Any]]:
    return charger_json(SEEDS / "exigences.json", {"exclusions": []})["exclusions"]


def _finaliser_champ(champ: dict[str, Any], ctx: "Contexte | None" = None) -> None:
    """Regles transverses de qualite appliquees a tout champ (templates et INCa)."""
    n = normaliser(champ["libelle"])
    for ex in _exclusions():
        if ex["organe_id"] != champ["organe_id"] or ex.get("concept", champ.get("concept")) != champ.get("concept"):
            continue
        if ex.get("libelle_motif") and not re.search(ex["libelle_motif"], n):
            continue
        retires = [p for p in ex["prelevements"] if champ["applicabilite"].pop(p, None) is not None]
        if retires:
            p = ex["prov"]
            champ.setdefault("exclusions", []).append({
                "id": ex["id"], "prelevements": retires, "raison": ex["raison"],
                "prov": ctx.prov(p["source_id"], p["localisation"], p["fiabilite"], p["confiance"], statut=p["statut_validation"],
                                 methode="exclusion_referentiel") if ctx else p})
    for motif, termes in _REQUIERT_TEXTE:
        if motif.search(n):
            champ["requiert_texte"] = list(termes)
    if champ.get("concept") in _CONCEPTS_NON_BIOPSIE:
        for p in ("biopsie", "cytologie"):
            champ["applicabilite"].pop(p, None)



def construire_champs(ctx: Contexte) -> list[dict[str, Any]]:
    from templates_organes import TOUS_LES_TEMPLATES  # noqa: PLC0415

    champs: list[dict[str, Any]] = []
    deja: set[str] = set()
    for tpl in TOUS_LES_TEMPLATES:
        for i, c in enumerate(tpl.champs_obligatoires):
            champs.append(_champ(ctx, tpl.organe, c.nom, c.section, c.obligatoire, c.exemple_formulation,
                                 list(c.mots_cles_detection), i,
                                 f"Gabarit MARC {tpl.nom_affichage}, champ {i + 1} : {c.nom}", deja))

    # --- enrichissement INCa (paraphrase 2011) ---
    inca = charger_json(WEB / "inca_donnees_minimales.json", {"organes": []})
    p_inca = "src:inca_donnees_minimales_2011"
    for fiche in inca["organes"]:
        prel_fiche = _prelevements_fiche(fiche.get("contextes", []))
        for oslug in _inca_organes(fiche["organe"]):
            champs_o = [c for c in champs if c["organe_id"] == f"organe:{oslug}"]
            for item in fiche["items"]:
                iid = item["id"]
                lib = item["label"]
                if oslug == "col_uterin" and (iid.startswith("corps_") or lib.lower().startswith("corps")):
                    continue
                if oslug == "endometre" and (iid.startswith("col_") or lib.lower().startswith("col :") or lib.lower().startswith("col ")):
                    continue
                if _ITEM_INCA_NON_UTILISE.search(normaliser(lib)):
                    continue  # « Grade : non utilise » : notion absente de ce cancer, jamais un champ obligatoire
                concept = _INCA_ALIAS.get(iid.lower()) or concept_de(lib)
                cible = None if concept == "autre" else next(
                    (c for c in champs_o if c["concept"] == concept and c.get("inca_item_id") is None
                     and c["origine"] == "templates_organes"), None)
                loc = f"fiche INCa 2011 ({fiche.get('fiche_inca_n', '?')}), item {iid}"
                prel, cond = _condition_inca(item.get("condition"))
                if prel is None:
                    prel = prel_fiche
                if cible is not None:
                    cible["inca_item_id"] = iid
                    cible["niveau"] = "obligatoire_inca"
                    cible["obligatoire"] = True
                    if not cible["unite"] and item.get("unite") and item["unite"] in ("mm", "%", "cm"):
                        cible["unite"] = item["unite"]
                    if oslug == "poumon" and concept == "taille_tumorale":
                        cible["unite_inca"] = "cm"  # piege mm/cm : seule fiche INCa en cm
                    if cond and not cible["condition"]:
                        cible["condition"] = cond
                    if item.get("valeurs") and not cible["options"] and item["type"].startswith("enum") and len(item["valeurs"]) <= 12:
                        cible["options"] = list(item["valeurs"])
                    cible.setdefault("prov_complementaires", []).append(
                        ctx.prov(p_inca, loc, "C", 0.7, statut="a_valider", methode="rapprochement_automatique"))
                    continue
                # item INCa sans equivalent : nouveau champ
                type_inca = {"enum": "enum", "num": "nombre_unite", "bool": "booleen", "text": "texte_libre",
                             "enum+num": "enum_nombre", "num/groupe": "liste_structuree"}.get(item["type"], "texte_libre")
                identification = iid in ("type_prelevement", "cote", "localisation")
                base = slug(iid, 40)
                cid = f"champ:{oslug}.{base}"
                k = 2
                while cid in deja:
                    cid = f"champ:{oslug}.{base}_{k}"
                    k += 1
                deja.add(cid)
                tumoral = not identification
                appl: dict[str, list[str]] = {}
                for p in ("biopsie", "piece_operatoire", "indetermine"):
                    if prel is not None and p not in prel and p != "indetermine":
                        continue
                    if p == "indetermine" and prel == ["piece_operatoire"]:
                        continue
                    appl[p] = [c for c in CONTEXTES_IDS if not (tumoral and c == "benin")]
                champs.append({
                    "id": cid, "organe_id": f"organe:{oslug}", "libelle": lib.split(" : ")[0].split(" (")[0] if len(lib) > 60 else lib,
                    "libelle_complet": lib, "concept": concept_de(lib) if concept_de(lib) != "autre" else slug(iid),
                    "section": "identification" if identification else "microscopie",
                    "obligatoire": not identification and not _condition_residuelle(cond),
                    "niveau": "recommande" if identification or _condition_residuelle(cond) else "obligatoire_inca",
                    "type": type_inca, "unite": item.get("unite") if item.get("unite") in ("mm", "%", "cm") else None,
                    "options": list(item.get("valeurs", []))[:12] if type_inca.startswith("enum") and item.get("valeurs") else [],
                    "plages": [], "condition": cond, "tumoral": tumoral, "ordre": 100 + len(champs),
                    "detection": {"mots_cles": []}, "exemple_formulation": "",
                    "origine": "inca_seul", "inca_item_id": iid, "applicabilite": appl,
                    "prov": ctx.prov(p_inca, loc, "C", 0.7, statut="a_valider", methode="paraphrase_structuree"),
                })
                raff = _RAFFINEMENTS_INCA.get(cid.split(":", 1)[1])
                if raff:
                    champs[-1]["libelle_complet"] = lib
                    champs[-1]["libelle"] = raff["libelle"]
                    champs[-1]["detection"] = {"mots_cles": list(raff["mots"])}
                elif not identification:
                    champs[-1]["detection"] = {"mots_cles": _mots_depuis_libelle(champs[-1]["libelle"])}
    # --- champs generiques non tumoraux (valables pour tout organe, benin compris) ---
    toutes = {p: list(CONTEXTES_IDS) for p in ("biopsie", "piece_operatoire", "cytologie", "indetermine")}
    for gid, lib, obl, section, ordre in [
        ("diagnostic_lesionnel", "Diagnostic lésionnel (lésion principale)", True, "conclusion", 0),
        ("dysplasie_malignite", "Dysplasie / signes de malignité (présence ou absence)", False, "microscopie", 1),
    ]:
        champs.append({
            "id": f"champ:generique.{gid}", "organe_id": "organe:generique", "libelle": lib, "concept": gid,
            "section": section, "obligatoire": obl, "niveau": "obligatoire_local" if obl else "recommande",
            "type": "texte_libre", "unite": None, "options": [], "plages": [], "condition": None, "tumoral": False,
            "ordre": ordre, "detection": {"mots_cles": []}, "exemple_formulation": "", "origine": "semence_generique",
            "applicabilite": toutes,
            "prov": ctx.prov("src:seed_marc_v3", f"champs generiques ({gid})", "C", 0.6, statut="a_valider", methode="semence_curee"),
        })
    for c in champs:
        _finaliser_champ(c, ctx)
    champs.sort(key=lambda c: (c["organe_id"], c.get("ordre", 0), c["id"]))
    return champs


# ===========================================================================
# 9. Gabarits
# ===========================================================================

_SECTIONS = {
    "titre": ("Titre", 0), "clinique": ("Renseignements cliniques", 1), "extemporane": ("Examen extemporané", 2),
    "macroscopie": ("Macroscopie", 3), "technique": ("Matériel et technique", 3), "microscopie": ("Microscopie", 4),
    "ihc": ("Immunohistochimie", 5), "biomol": ("Biologie moléculaire", 6), "conclusion": ("Conclusion", 9),
}


def construire_gabarits(ctx: Contexte, organes: list[dict[str, Any]], champs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gabarits de sections par organe x prelevement (ordre CI-SIS) ; generiques en repli."""
    par_organe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in champs:
        par_organe[c["organe_id"]].append(c)
    gabs: list[dict[str, Any]] = []

    def sections_pour(prel: str, cs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = ["titre", "clinique"]
        if prel == "piece_operatoire":
            ids.append("extemporane")
        ids.append("technique" if prel == "cytologie" else "macroscopie")
        ids.append("microscopie")
        secs_champs = {c["section"] for c in cs}
        if "ihc" in secs_champs and prel != "curage":
            ids.append("ihc")
        if "biologie_moleculaire" in secs_champs and prel not in ("curage", "cytologie"):
            ids.append("biomol")
        ids.append("conclusion")
        res = []
        for sid in ids:
            titre, ordre = _SECTIONS[sid]
            res.append({"id": sid, "titre": titre, "ordre": ordre,
                        "obligatoire": sid == "conclusion", "optionnelle": sid in ("extemporane", "clinique")})
        return res

    for o in organes:
        oid = o["id"]
        cs = par_organe.get(oid, [])
        if oid != "organe:generique" and not any(c["origine"] != "semence_generique" for c in cs):
            continue  # pas de gabarit specifique sans champs : repli generique
        for prel in PRELEVEMENTS_IDS:
            utiles = [c for c in cs if "malin" in c["applicabilite"].get(prel, [])] or cs
            secs = sections_pour(prel, utiles if oid != "organe:generique" else [])
            sec_to_champs: dict[str, list[str]] = defaultdict(list)
            for c in utiles:
                if c["origine"] == "semence_generique":
                    continue
                cible = {"biologie_moleculaire": "biomol", "identification": "titre"}.get(c["section"], c["section"])
                if cible not in {s["id"] for s in secs}:
                    cible = "conclusion"
                sec_to_champs[cible].append(c["id"])
            gabs.append({
                "id": f"gabarit:{oid.split(':')[1]}.{prel}", "organe_id": oid, "prelevement": prel,
                "prelevement_id": f"prelevement:{prel}", "sections": secs,
                "champs_par_section": dict(sorted(sec_to_champs.items())),
                "repli": None if oid == "organe:generique" else f"gabarit:generique.{prel}",
                "prov": ctx.prov("src:conventions_cr_acp", "section 1 (structure CI-SIS) + sections des champs INCa/templates",
                                 "B", 0.7, statut="derive_auto", methode="derive_structure"),
            })
    return gabs


# ===========================================================================
# 10. Exemples de style et mappings ADICAP
# ===========================================================================

_ORGANE_PAR_CAT: dict[str, dict[str, str]] = {
    "DIG": {"anus": "canal_anal", "appendice": "appendice", "chir colo-rectal": "colon_rectum", "colo-rectal": "colon_rectum",
            "duodenum": "intestin_grele", "estomac": "estomac", "foie": "foie", "grele": "intestin_grele", "pancreas": "pancreas",
            "peritoine": "peritoine", "vesicule": "vesicule_biliaire", "oesophage": "oesophage"},
    "URO": {"deferent": "testicule", "epididyme": "testicule", "hydatide": "testicule", "prostate": "prostate", "prepuce": "verge",
            "penis": "verge", "rein": "rein", "testicule": "testicule", "uretere": "uretere", "vaginale": "testicule", "vessie": "vessie"},
    "GYN": {"col": "col_uterin", "endometre": "endometre", "ovaire": "ovaire", "trompe": "ovaire", "uterus": "endometre",
            "vagin": "vulve_vagin", "vulve": "vulve_vagin"},
    "CYTO": {"arti": "articulation", "ascite": "peritoine", "aspi bron": "poumon", "lba": "poumon", "ganglion": "lymphome",
             "lcr": "systeme_nerveux_central", "plevre": "plevre", "thyroide": "thyroide", "urine": "vessie"},
    "ENDOC": {"parathyroide": "parathyroide", "surrenale": "surrenale", "thyroide": "thyroide"},
    "HEMATO": {"bom": "moelle_osseuse", "gg": "lymphome", "rate": "rate", "peau": "peau"},
    "ORL": {"oreille": "oreille", "os": "os", "parathyroide": "parathyroide"},
}
_ORGANE_PAR_CAT_DEFAUT: dict[str, str] = {
    "THO": "poumon", "Cyto FCU": "col_uterin", "FOETO-P": "placenta", "OPH": "oeil", "CV": "coeur_vaisseaux",
    "ORL": "orl_tete_cou", "HEMATO": "lymphome", "SEIN": "sein", "DERMATO": "peau", "OS-ARTI": "os",
    "T mous": "sarcome", "NEURO": "systeme_nerveux_central",
}
_SURCHARGES_LESION: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"thym"), "thymus"), (re.compile(r"mesothel|biopsies? pleural|pleurectomie|liquide pleural|epanchement pleural"), "plevre"),
    (re.compile(r"melanome"), "melanome"),
    (re.compile(r"arthr|synov|canal carpien|menisque|tendin|hernie discale|bursite"), "articulation"),
]


def organe_de_entree(cat: str, organe_label: str, lesion: str) -> str:
    """Slug d'organe (ou `generique`) pour une entree de bible."""
    nl = normaliser(lesion)
    for pat, slug_o in _SURCHARGES_LESION:
        if pat.search(nl) and cat in ("THO", "CYTO", "DERMATO", "OS-ARTI", "HEMATO", "ORL"):
            return slug_o
    nlab = normaliser(organe_label).strip()
    nlab = nlab.split("\n")[0].strip()
    nlab = nlab.replace("œ", "oe")
    nlab = re.sub(r"^oesophage$", "oesophage", nlab)
    table = _ORGANE_PAR_CAT.get(cat, {})
    if nlab in table:
        return table[nlab]
    if cat == "ORL" and nlab in ("amygdale", "bouche", "cv", "cou", "glande salivaire", "larynx", "naso-sinusien", "immuno"):
        return "orl_tete_cou"
    return _ORGANE_PAR_CAT_DEFAUT.get(cat, "generique")


def prelevement_de(cat: str, lesion: str, texte: str) -> str | None:
    if cat in ("CYTO", "Cyto FCU"):
        return "cytologie"
    nl = normaliser(lesion)
    nt = normaliser(texte[:300])
    for cible, pat in [
        ("curage", r"curage|ganglion sentinelle"),
        ("biopsie", r"biops|carotte|punch|ponction"),
        ("piece_operatoire", r"ectomie|resection|exerese|piece|amputation|lobe |segment|reprise"),
    ]:
        if re.search(pat, nl):
            return cible
    for cible, pat in [("biopsie", r"biopsi|fragment|carotte"), ("piece_operatoire", r"piece|ectomie|resection|exerese")]:
        if re.search(pat, nt):
            return cible
    return None


def parser_codes(brut: str) -> list[tuple[str | None, str]]:
    """'DQ 4554' -> [('DQ','4554')] ; '7410/7332' -> [(None,'7410'),(None,'7332')] ; '' -> []."""
    out: list[tuple[str | None, str]] = []
    for part in re.split(r"[/;,]|\s-\s|\n", brut or ""):
        p = re.sub(r"\s+", "", part.upper())
        m = re.match(r"^([A-Z]{2})([0-9A-Z]{4})$", p)
        if m and m.group(2).isalpha() is False:
            out.append((m.group(1), m.group(2)))
            continue
        if re.match(r"^[0-9A-Z]{4}$", p) and any(ch.isdigit() for ch in p):
            out.append((None, p))
    return out


def _mots(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", normaliser(s)) if w not in {"avec", "sans", "dans", "autre", "autres", "tumeur"}}


def _singulier(w: str) -> str:
    return w[:-1] if w.endswith(("s", "x")) else w


def construire_exemples_et_mappings(ctx: Contexte, th: Thesaurus, organes_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Exemples de style (textes purges, verrouilles par organe) + mappings lesion -> ADICAP."""
    canon = charger_json(CANONIQUES, [])
    cat_bible = charger_json(DATA / "adicap_bible.json", {"organ_codes": {}, "lesion_catalog": []})
    perdues = lire_feuilles_perdues(ctx)

    entrees: list[dict[str, Any]] = []
    for i, e in enumerate(canon):
        entrees.append({"cat": e["cat"], "organe": e.get("organe", ""), "lesion": e["lesion"], "code_brut": e.get("code", ""),
                        "texte": e["texte"], "src": "src:textes_canoniques_json", "loc": f"textes_canoniques.json[{i}]"})
    for e in perdues:
        entrees.append({"cat": e["feuille"], "organe": e["organe"], "lesion": e["lesion"], "code_brut": e["code_brut"],
                        "texte": e["texte"], "src": "src:bible_greg_xlsx", "loc": f"feuille {e['feuille']}, ligne {e['ligne']}"})

    exemples: list[dict[str, Any]] = []
    vus: set[tuple[str, str]] = set()
    compteurs: Counter[tuple[str, str]] = Counter()
    stats = {"exemples_total": 0, "exemples_feuilles_perdues": 0, "exemples_purges": 0, "doublons_ignores": 0}
    for e in entrees:
        texte_brut = e["texte"]
        texte = verifier_pii(texte_brut, e["loc"])  # BLOQUANT
        lesion = verifier_pii(e["lesion"], e["loc"] + ".lesion")
        ctx.textes_scannes += 2
        if texte != texte_brut:
            stats["exemples_purges"] += 1
        if len(texte) < 40:
            continue
        cle = (normaliser(lesion), normaliser(texte)[:60])
        if cle in vus:
            stats["doublons_ignores"] += 1
            continue
        vus.add(cle)
        oslug = organe_de_entree(e["cat"], e["organe"], lesion)
        oid = f"organe:{oslug}"
        if oid not in organes_ids:
            oid = "organe:generique"
        prel = prelevement_de(e["cat"], lesion, texte)
        pid = f"prelevement:{prel}" if prel else None
        compteurs[(oid, prel or "x")] += 1
        n_trous = texte.count("#")
        exemples.append({
            "id": f"ex:{oid.split(':')[1]}.{prel or 'indetermine'}.{compteurs[(oid, prel or 'x')]:03d}",
            "organe_id": oid, "prelevement_id": pid, "lesion_libelle": lesion, "texte": texte,
            "placeholders": [{"marque": "#", "nombre": n_trous}] if n_trous else [],
            "praticien_id": "prat:A", "pii_verifie": True, "categorie_source": e["cat"],
            "qualite": {"nb_caracteres": len(texte), "a_trous": n_trous > 0 or "…" in texte, "complet": len(texte) >= 150},
            "mapping_lesion_ids": [],
            "prov": ctx.prov(e["src"], e["loc"], "B", 0.7, statut="derive_auto", methode="extraction_automatique",
                             praticien="prat:A"),
        })
        e["_oid"] = oid
        e["_ex_id"] = exemples[-1]["id"]
        if e["src"] == "src:bible_greg_xlsx":
            stats["exemples_feuilles_perdues"] += 1
    stats["exemples_total"] = len(exemples)

    # ---- mappings lesion -> codes ADICAP ----
    mappings: list[dict[str, Any]] = []
    rejets: list[dict[str, Any]] = []
    cles_map: set[tuple[str, str, str, str | None]] = set()
    labels_d3 = {c: v.get("labels", []) for c, v in cat_bible["organ_codes"].items()}

    candidats: list[dict[str, Any]] = []
    for i, l in enumerate(cat_bible["lesion_catalog"]):
        candidats.append({"cat": l["cat"], "organe": "", "lesion": l["lesion"], "codes": [(l["organ_code"], l["lesion_code"])],
                          "kw": l.get("kw", []), "src": "src:adicap_bible_json", "loc": f"adicap_bible.json, lesion_catalog[{i}]",
                          "oid_hint": None})
    for e in entrees:
        if "_oid" not in e:
            continue
        codes = parser_codes(e["code_brut"])
        if codes:
            candidats.append({"cat": e["cat"], "organe": e["organe"], "lesion": e["lesion"], "codes": codes, "kw": [],
                              "src": e["src"], "loc": e["loc"], "oid_hint": e["_oid"], "ex_id": e["_ex_id"]})
    # organe connu par libelle de lesion (via les textes canoniques qui portent l'organe)
    oid_par_libelle: dict[str, str] = {}
    for e in entrees:
        if e.get("_oid") and e["_oid"] != "organe:generique":
            oid_par_libelle.setdefault(normaliser(e["lesion"]), e["_oid"])
    organes_libelles = {normaliser(w).strip() for o in ORGANES_COURANTS for w in re.split(r"\s*[/(),]\s*", o["libelle"])} - {"prepuce"}
    for c in candidats:
        oid = c["oid_hint"]
        if oid is None:
            # catalogue de la bible : l'organe vient du code D3 / de la categorie
            oid = f"organe:{organe_de_entree(c['cat'], '', c['lesion'])}"
            d3 = c["codes"][0][0]
            if oid == "organe:generique" and d3:
                oid = _D3_PRIORITAIRE.get(d3) or next((o for o, d in ORGANE_D3.items() if d3 in d), oid)
            if oid == "organe:generique":
                oid = oid_par_libelle.get(normaliser(c["lesion"]), oid)
        if oid not in organes_ids:
            oid = "organe:generique"
        (d3_p, les_p), alternatifs = c["codes"][0], c["codes"][1:]
        d3_ok = True
        ecarts: list[str] = []
        if d3_p is not None:
            if not th.actif("D3", d3_p):
                d3_ok = False
        existe, actif = th.lesion_existe(les_p, d3_p)
        if not existe or not actif or not d3_ok:
            motif = ("lesion_obsolete" if existe and not actif else "lesion_inconnue" if not existe else "organe_d3_inconnu")
            rejets.append({"id": f"rejet:{slug(c['lesion'], 40)}.{les_p}", "libelle_praticien": c["lesion"], "code_brut": f"{d3_p or ''}{les_p}",
                           "motif": motif, "prov": ctx.prov(c["src"], c["loc"], "B", 0.3, statut="contesté")})
            continue
        # controles de coherence libelle bible / thesaurus (signalement, pas d'exclusion)
        trouve = th.resoudre_lesion(d3_p, les_p)
        dico_les, concept_les = trouve  # type: ignore[misc]
        lib_off = concept_les[4]
        if d3_p is not None and labels_d3.get(d3_p):
            off_d3 = normaliser(th.libelle("D3", d3_p))
            vrais_organes = [l for l in labels_d3.get(d3_p, []) if normaliser(l).strip() in organes_libelles]
            mots_b = {w[:3] for w in _mots(" ".join(vrais_organes))}
            mots_o = {w[:3] for w in _mots(off_d3)}
            if mots_b and mots_o and not (mots_b & mots_o):
                ecarts.append(f"organe_d3_{d3_p}: « {th.libelle('D3', d3_p)} » sans lien avec « {' / '.join(vrais_organes)[:40]} »")
        alt_ok = []
        for d3a, la in alternatifs:
            ex_a, ac_a = th.lesion_existe(la, d3a)
            if ex_a and ac_a and (d3a is None or th.actif("D3", d3a)):
                alt_ok.append({"d3": d3a, "lesion": la})
        cle = (oid, normaliser(c["lesion"]), les_p, d3_p)
        if cle in cles_map:
            continue
        cles_map.add(cle)
        kw = c["kw"] or sorted(w for w in _mots(c["lesion"]))
        mappings.append({
            "id": f"map:{oid.split(':')[1]}.{slug(c['lesion'], 45)}.{(d3_p or '')}{les_p}",
            "organe_id": oid, "libelle_praticien": c["lesion"], "declencheurs": kw,
            "adicap": {"d3": d3_p, "lesion": les_p, "dict_lesion": dico_les,
                       "libelle_officiel": lib_off, "partiel": d3_p is None},
            "codes_alternatifs": alt_ok, "conditions": [], "controles": ecarts,
            "exige_validation_pathologiste": True,
            "exemples_style_ids": [c["ex_id"]] if c.get("ex_id") else [],
            "prov": ctx.prov(c["src"], c["loc"], "B", 0.6 if not ecarts else 0.4, statut="a_valider",
                             methode="extraction_automatique"),
        })
    # rattache les exemples aux mappings de meme (organe, libelle)
    idx_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for m in mappings:
        idx_map[(m["organe_id"], normaliser(m["libelle_praticien"]))].append(m["id"])
    for ex in exemples:
        ex["mapping_lesion_ids"] = idx_map.get((ex["organe_id"], normaliser(ex["lesion_libelle"])), [])
    for liste in (mappings, rejets):
        vus_ids: Counter[str] = Counter()
        for m in liste:
            vus_ids[m["id"]] += 1
            if vus_ids[m["id"]] > 1:
                m["id"] += f"_{vus_ids[m['id']]}"
    mappings.sort(key=lambda m: m["id"])
    rejets.sort(key=lambda m: m["id"])
    stats["mappings"] = len(mappings)
    stats["rejets"] = len(rejets)
    return exemples, mappings, rejets, stats


ORGANE_D3: dict[str, list[str]] = {}
ORGANES_COURANTS: list[dict[str, Any]] = []
# D3 partages entre plusieurs organes : organe prioritaire pour rattacher une lesion du catalogue.
_D3_PRIORITAIRE: dict[str, str] = {"OT": "organe:peau", "LM": "organe:muscle", "DV": "organe:intestin_grele",
                                   "UP": "organe:rein", "HE": "organe:testicule", "FO": "organe:pancreas",
                                   "FI": "organe:foie", "SM": "organe:moelle_osseuse", "SR": "organe:rate"}


# ===========================================================================
# 11. SNOMED, echelles, stations, regles, plages
# ===========================================================================

def construire_snomed(ctx: Contexte, organes: list[dict[str, Any]]) -> dict[str, Any]:
    import snomed as snomed_mod  # noqa: PLC0415

    par_code: dict[str, dict[str, Any]] = {}
    cle_vers_organes: dict[str, list[str]] = defaultdict(list)
    for o in organes:
        for sid in o["snomed_body_structure"]:
            cle_vers_organes[sid.split(":")[1]].append(o["id"])
    for cle, b in snomed_mod._BODY_STRUCTURES.items():  # noqa: SLF001
        e = par_code.setdefault(b["code"], {
            "id": f"snomed:{b['code']}", "concept_id": b["code"], "fsn": b["display"], "terme_fr": None,
            "hierarchie": "body_structure", "usage": "topographie", "cles_snomed_py": [], "organe_ids": [],
            "type_mapping": "equivalent", "verifie_contre_release": False, "declencheurs": [],
        })
        e["cles_snomed_py"].append(cle)
    for code, e in par_code.items():
        e["organe_ids"] = sorted(set(cle_vers_organes.get(code, [])))
        e["cles_snomed_py"] = sorted(e["cles_snomed_py"])
        e["prov"] = ctx.prov("src:snomed_py_historique", f"Structure anatomique saisie à la main : {e['cles_snomed_py'][0]}", "C", 0.4,
                             statut="non_valide", methode="saisie_manuelle_historique")
    concepts = sorted(par_code.values(), key=lambda e: e["concept_id"])
    for i, (code, display, mots) in enumerate(snomed_mod._MORPHOLOGIES):  # noqa: SLF001
        concepts.append({
            "id": f"snomed:{code}", "concept_id": code, "fsn": display, "terme_fr": display, "hierarchie": "morphologic_abnormality",
            "usage": "morphologie", "cles_snomed_py": [], "organe_ids": [], "type_mapping": "related",
            "verifie_contre_release": False, "declencheurs": list(mots),
            "prov": ctx.prov("src:snomed_py_historique", f"Morphologie saisie à la main : {display}", "C", 0.4, statut="non_valide",
                             methode="saisie_manuelle_historique"),
        })
    return {"edition": None, "avertissement": "Aucune release SNOMED CT chargee : tout code est une SUGGESTION NON VERIFIEE "
            "(statut_validation = non_valide). Ne jamais presenter comme code certain.", "concepts": concepts}


def construire_echelles(ctx: Contexte) -> list[dict[str, Any]]:
    veille = charger_json(WEB / "nomenclatures_scores.json", {"systemes": []})
    echelles: list[dict[str, Any]] = []
    for s in veille["systemes"]:
        e = {k: v for k, v in s.items()}
        e["id"] = f"echelle:{s['id']}"
        e.pop("reference", None)
        e["reference"] = s.get("reference")
        e["prov"] = ctx.prov("src:nomenclatures_scores_veille", f"nomenclatures_scores.json#{s['id']}", "C", 0.6,
                             statut="a_valider", methode="import_veille")
        echelles.append(e)
    echelles.append({
        "id": "echelle:gleason_isup_table", "type": "table_correspondance", "organe": "prostate",
        "entrees": [{"gleason": "3+3", "somme": 6, "isup": 1}, {"gleason": "3+4", "somme": 7, "isup": 2},
                    {"gleason": "4+3", "somme": 7, "isup": 3}, {"gleason": "4+4", "somme": 8, "isup": 4},
                    {"gleason": "3+5", "somme": 8, "isup": 4}, {"gleason": "5+3", "somme": 8, "isup": 4},
                    {"somme": 9, "isup": 5}, {"somme": 10, "isup": 5}],
        "prov": ctx.prov("src:nomenclatures_scores_veille", "nomenclatures_scores.json#gleason_isup", "C", 0.6, statut="a_valider",
                         methode="derive_auto"),
    })
    return echelles


def construire_stations(ctx: Contexte) -> list[dict[str, Any]]:
    """Stations ganglionnaires IASLC (poumon) : connaissance du domaine, a valider."""
    defs = [("1", "Sus-claviculaire et creux sus-sternal bas cervical", []), ("2R", "Paratrachéale haute droite", []),
            ("2L", "Paratrachéale haute gauche", []), ("3A", "Prévasculaire", []), ("3P", "Rétrotrachéale", []),
            ("4R", "Paratrachéale basse droite", ["loge de Barety", "latéro-trachéale droite"]),
            ("4L", "Paratrachéale basse gauche", []), ("5", "Fenêtre aorto-pulmonaire (sous-aortique)", ["sous-aortique"]),
            ("6", "Para-aortique (aorte ascendante ou phrénique)", ["para-aortique"]),
            ("7", "Sous-carinaire", ["sous-carinaire"]), ("8", "Para-œsophagienne", ["para-œsophagienne"]),
            ("9", "Ligament pulmonaire", ["ligament pulmonaire"]), ("10", "Hilaire", ["hilaire"]),
            ("11", "Interlobaire", ["interlobaire"]), ("12", "Lobaire", []), ("13", "Segmentaire", []), ("14", "Sous-segmentaire", [])]
    return [{
        "id": f"station:{n.lower()}", "organe_id": "organe:poumon", "systeme": "IASLC", "numero": n, "libelle": lib,
        "synonymes_parles": syn,
        "prov": ctx.prov("src:seed_marc_v3", f"IASLC station {n}", "D", 0.5, statut="a_valider", methode="connaissance_domaine"),
    } for n, lib, syn in defs]


def construire_regles(ctx: Contexte) -> list[dict[str, Any]]:
    regles = charger_json(SEEDS / "regles.json", {"regles": []})["regles"]
    for r in regles:
        p = r["prov"]
        r["prov"] = ctx.prov(p["source_id"], p["localisation"], p["fiabilite"], p["confiance"], statut=p["statut_validation"],
                             methode="catalogue_declaratif")
    return regles


def tester_regles(regles: list[dict[str, Any]]) -> list[str]:
    """Execute les tests embarques (cas passants et non passants) ; retourne les echecs."""
    echecs: list[str] = []
    for r in regles:
        if r.get("condition") is None:
            continue
        if not r.get("tests"):
            echecs.append(f"{r['id']}: aucun test embarque")
        for t in r.get("tests", []):
            obtenu = evaluer_condition(r["condition"], t["entree"])
            attendu = t["attendu"] == "declenche"
            if obtenu != attendu:
                echecs.append(f"{r['id']}: entree {t['entree']} attendu={t['attendu']} obtenu={obtenu}")
    return echecs


def construire_plages(ctx: Contexte) -> list[dict[str, Any]]:
    plages = charger_json(SEEDS / "plages.json", {"plages": []})["plages"]
    out = []
    for p in plages:
        e = dict(p)
        suffixe = (f".{p['organe_id'].split(':')[1]}" if p.get("organe_id") else "") + (f".{p['prelevement']}" if p.get("prelevement") else "")
        e["id"] = f"plage:{p['champ']}{suffixe}"
        e["heuristique"] = True
        e["si_hors_plage"] = "proposer_lecture_alternative_mm_cm"
        loc = p.get("localisation") or "semence"
        src = p.get("source_id") or ("src:regles_unites_veille" if p.get("localisation") and "json" in loc or "plages_plausibles" in loc else "src:seed_marc_v3")
        fiab = p.get("fiabilite") or "C"
        for cle in ("localisation", "source_id", "fiabilite"):
            e.pop(cle, None)
        e["prov"] = ctx.prov(src, loc, fiab, 0.4, statut="a_valider", methode="heuristique")
        out.append(e)
    return out


# ===========================================================================
# 12. Lexique phonetique
# ===========================================================================

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
           "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def nombre_en_lettres(n: int) -> str | None:
    """0-99 en francais (suffisant pour p16, Ki67, CK20, p63, p53...)."""
    if n < 0 or n > 99:
        return None
    if n < 20:
        return _UNITES[n]
    if n < 70:
        d, u = (n // 10) * 10, n % 10
        return _DIZAINES[d] + ("" if u == 0 else (" et un" if u == 1 else f"-{_UNITES[u]}"))
    if n < 80:
        return "soixante" + ("-et-onze" if n == 71 else f"-{_UNITES[n - 60]}") if n != 70 else "soixante-dix"
    if n == 80:
        return "quatre-vingts"
    return f"quatre-vingt-{_UNITES[n - 80]}" if n < 100 else None


def generer_variantes(terme: str) -> list[str]:
    """Variantes STT plausibles par regles (origine `genere`, confiance 0,4)."""
    base = terme.strip()
    nb = normaliser(base)
    out: list[str] = []

    def add(f: str) -> None:
        f = re.sub(r"\s+", " ", f).strip()
        if f and f.lower() != base.lower() and f not in out:
            out.append(f)
    if nb != base.lower():
        add(nb)  # sans accent
    if "-" in base:
        add(base.replace("-", " "))
        add(base.replace("-", ""))
    m = re.fullmatch(r"([A-Za-z\-]+?)[\s\-]?(\d{1,3})", base)
    if m and not re.fullmatch(r"\d+", base):
        lettres, chiffres = m.group(1), m.group(2)
        add(f"{lettres} {chiffres}")
        add(f"{lettres}-{chiffres}")
        add(f"{lettres}{chiffres}".lower())
        mots = nombre_en_lettres(int(chiffres))
        if mots:
            add(f"{lettres} {mots}")
        if len(lettres) <= 5 and lettres.replace("-", "").isalpha():
            add(" ".join(lettres.replace("-", "")) + f" {chiffres}")
    elif re.fullmatch(r"[A-Z]{2,5}", base):
        add(" ".join(base))
    return out[:8]


#: Variantes STT de faible qualite, rejetees a la construction (terme normalise, forme normalisee).
#: Les formes longues d'unites (« millimetres ») et les expansions de sigles sont des mots LEGITIMES,
#: pas des erreurs de transcription : les « corriger » changerait la dictee.
_VARIANTES_REJETEES: frozenset[tuple[str, str]] = frozenset({
    ("re", "air e"), ("rp", "air pe"), ("pax8", "pas 8"), ("ain3", "ene 3"), ("melan-a", "melanation"),
    ("desmoplasique", "desmoplastique"), ("carcinome", "carcino me"), ("melanome", "melano me"),
    ("mastectomie", "mas ectomie"), ("acineux", "acinaire"),
})
_FORMES_LONGUES_UNITES = frozenset({"millimetre", "millimetres", "centimetre", "centimetres", "metre", "metres"})


def variante_acceptable(terme: str, forme: str) -> bool:
    """Une variante est une erreur de TRANSCRIPTION plausible du terme, pas un autre mot ni une flexion."""
    t, f = normaliser(terme).strip(), normaliser(forme).strip()
    if not f or f == t:
        return True
    if (t, f) in _VARIANTES_REJETEES:
        return False
    if t in ("mm", "cm") and f in _FORMES_LONGUES_UNITES:
        return False
    # Flexion du MEME mot (« mucineux » -> « mucineuse », pluriel) : un autre etat grammatical n'est
    # pas une erreur de STT et ne doit pas etre « corrige ». Les fautes d'orthographe/de prononciation restent.
    if " " not in t and " " not in f and not re.search(r"\d", t):
        def _racine(x: str) -> str:
            return re.sub(r"(euses|euse|eux|es|e|s|x)$", "", x)
        if len(_racine(t)) >= 4 and _racine(t) == _racine(f):
            return False
    return True


_SEGMENTS_IGNORES = {"region", "organisme entier", "autre", "autres", "appareil", "systeme", "region de l'organisme"}


def construire_lexique(ctx: Contexte, th: Thesaurus, organes: list[dict[str, Any]],
                       lesions_labels: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Lexique : semences + context_bias + IHC des templates + D3 ADICAP + lesions de la bible."""
    from templates_organes import TOUS_LES_TEMPLATES  # noqa: PLC0415
    import vocabulaire_acp  # noqa: PLC0415

    entrees: dict[str, dict[str, Any]] = {}

    def ajouter(terme: str, categorie: str, prov: dict[str, Any], variantes: list[dict[str, Any]] | None = None,
                contexte_requis: list[str] | None = None, organes_ids: list[str] | None = None, prio: int = 3,
                expansion: str | None = None) -> None:
        cle = normaliser(terme).strip()
        if not cle:
            return
        if cle in entrees:
            e = entrees[cle]
            e["organes"] = sorted(set(e["organes"]) | set(organes_ids or []))
            e["priorite_biais_stt"] = min(e["priorite_biais_stt"], prio)
            return
        formes = [v for v in (variantes or []) if variante_acceptable(terme, v["forme"])]
        connues = {normaliser(v["forme"]) for v in formes} | {cle}
        for g in generer_variantes(terme):
            if normaliser(g) not in connues and variante_acceptable(terme, g):
                formes.append({"forme": g, "origine": "genere", "confiance": 0.4})
                connues.add(normaliser(g))
        detail = []
        for v in formes:
            d = {"forme": v["forme"], "origine": v["origine"], "confiance": v["confiance"], "cle": cle_phonetique(v["forme"])}
            if "occurrences" in v:
                d["occurrences"] = v["occurrences"]
            detail.append(d)
        entrees[cle] = {
            "id": "", "terme": terme, "categorie": categorie, "organes": sorted(organes_ids or []),
            "priorite_biais_stt": prio, "variantes": [d["forme"] for d in detail], "variantes_detail": detail,
            "cle_phonetique": cle_phonetique(terme), "contexte_requis": contexte_requis or [],
            "faux_amis": [], "prov": prov,
        }
        if expansion:
            entrees[cle]["expansion"] = expansion

    # 1. semences curees (variantes connues, contexte requis)
    for s in charger_json(SEEDS / "lexique.json", {"termes": []})["termes"]:
        ajouter(s["terme"], s["categorie"],
                ctx.prov("src:seed_marc_v3", f"seeds/lexique.json#{s['terme']}", "D", 0.5, statut="a_valider", methode="semence_curee"),
                variantes=s["variantes"], contexte_requis=s["contexte_requis"], organes_ids=s["organes"],
                prio=s["priorite_biais_stt"], expansion=s.get("expansion"))
    # 2. termes d'amorce STT existants
    for i, t in enumerate(vocabulaire_acp.CONTEXT_BIAS_TERMS):
        prio = 1 if re.search(r"\d|^[A-Z]{2,}|^p\d", t) else 2
        ajouter(t, "terme_amorce_stt", ctx.prov("src:vocabulaire_acp_py", f"Terme d'amorce de transcription n°{i + 1}", "B", 0.7,
                                              statut="derive_auto"), prio=prio)
    # 3. marqueurs IHC des templates
    for tpl in TOUS_LES_TEMPLATES:
        for m in tpl.marqueurs_ihc:
            ajouter(m, "sigle_marqueur", ctx.prov("src:templates_organes_py", f"Gabarit MARC {tpl.nom_affichage}, marqueurs d'immunohistochimie", "C", 0.6,
                                                  statut="derive_auto"), organes_ids=[f"organe:{tpl.organe}"], prio=2)
    # 4. organes ADICAP D3 (libelles officiels)
    for c in th.concepts:
        if c[3] != "D3" or c[1] == "D3" or c[2] == "D3" or not c[2]:
            continue
        for seg in re.split(r"\s+-\s+|[(),]", c[4]):
            seg = seg.strip().lower()
            if len(seg) >= 4 and seg not in _SEGMENTS_IGNORES and not seg.startswith("egalement"):
                ajouter(seg, "organe_adicap", ctx.prov("src:adicap_2024_10", f"D3 {c[1]}", "A", 0.9, statut="valide",
                                                       methode="import_officiel"), prio=3)
    # 5. libelles de lesions de la bible du praticien
    for lib, oid in lesions_labels:
        lib = lib.strip(" .()")
        if re.match(r"[A-Za-zÀ-ÿ]", lib) and 4 <= len(lib) <= 70 and len(lib.split()) <= 8:
            ajouter(lib, "lesion", ctx.prov("src:adicap_bible_json", "libelle de lesion de la bible", "B", 0.6, statut="derive_auto"),
                    organes_ids=[oid] if oid != "organe:generique" else [], prio=3)
    liste = sorted(entrees.values(), key=lambda e: (e["priorite_biais_stt"], normaliser(e["terme"])))
    for e in liste:
        e["id"] = f"lex:{slug(e['terme'], 60)}"
    # unicite des ids
    vus: Counter[str] = Counter()
    for e in liste:
        vus[e["id"]] += 1
        if vus[e["id"]] > 1:
            e["id"] += f"_{vus[e['id']]}"
    return liste


# ===========================================================================
# 13. Couverture, validation, orchestration
# ===========================================================================

def niveau_couverture(n: int, seuils: tuple[int, int, int]) -> str:
    hi, mid, lo = seuils
    return "complet" if n >= hi else "partiel" if n >= mid else "minimal" if n >= lo else "absent"


def calculer_couverture(organes: list[dict[str, Any]], champs: list[dict[str, Any]], exemples: list[dict[str, Any]],
                        mappings: list[dict[str, Any]], gabarits: list[dict[str, Any]]) -> None:
    n_champs = Counter(c["organe_id"] for c in champs)
    n_ex = Counter(e["organe_id"] for e in exemples)
    n_map = Counter(m["organe_id"] for m in mappings)
    gab_organes = {g["organe_id"] for g in gabarits}
    for o in organes:
        oid = o["id"]
        o["couverture"] = {
            "champs": niveau_couverture(n_champs[oid] if oid != "organe:generique" else 0, (8, 3, 1)),
            "gabarit": "specifique" if oid in gab_organes else "generique",
            "exemples_style": niveau_couverture(n_ex[oid], (10, 3, 1)) if n_ex[oid] < 10 else "riche",
            "codage": "partiel" if n_map[oid] else "absent",
            "nb_champs": n_champs[oid], "nb_exemples": n_ex[oid], "nb_mappings_adicap": n_map[oid],
        }


def valider(sortie: dict[str, Any], sources_ids: set[str], th: Thesaurus, ctx: Contexte) -> list[str]:
    """Controles de build (audit 7.13). Retourne la liste des erreurs (vide = OK)."""
    err: list[str] = []
    cles_prov = {"source_id", "localisation", "version_source", "date_extraction", "fiabilite", "confiance", "statut_validation"}
    organes_ids = {o["id"] for o in sortie["organes"]}
    prelev_ids = {p["id"] for p in sortie["prelevements"]}
    champs_ids = {c["id"] for c in sortie["champs"]}
    mapping_ids = {m["id"] for m in sortie["adicap_mappings"]}
    ex_ids = {e["id"] for e in sortie["exemples_style"]}

    for nom, col in sortie.items():
        if nom in ("sources", "detection"):
            continue
        liste = col["concepts"] if nom == "snomed" else col
        if not isinstance(liste, list):
            continue
        ids = [e.get("id") for e in liste if "id" in e]
        doublons = [k for k, v in Counter(ids).items() if v > 1]
        if doublons:
            err.append(f"{nom}: ids dupliques {doublons[:3]}")
        for e in liste:
            p = e.get("prov")
            if not isinstance(p, dict) or not cles_prov <= p.keys():
                err.append(f"{nom}: entree sans prov complet ({e.get('id')})")
                continue
            if p["source_id"] not in sources_ids:
                err.append(f"{nom}: source inconnue {p['source_id']} ({e.get('id')})")
            if p["fiabilite"] not in "ABCD" or not 0 <= p["confiance"] <= 1:
                err.append(f"{nom}: prov invalide ({e.get('id')})")
    for src in sortie["sources"]:
        tc = src.get("titre_court") or ""
        if not tc or len(tc) > 70 or "\u2026" in tc or ".py" in tc or not src.get("description"):
            err.append(f"source {src['id']}: titre_court/description invalide")
    # cles etrangeres
    for c in sortie["champs"]:
        if c["organe_id"] not in organes_ids:
            err.append(f"champ {c['id']}: organe inconnu {c['organe_id']}")
        if c["tumoral"] and "benin" in sum(c["applicabilite"].values(), []):
            err.append(f"champ {c['id']}: champ tumoral applicable en contexte benin")
    for g in sortie["gabarits"]:
        if g["organe_id"] not in organes_ids or g["prelevement_id"] not in prelev_ids:
            err.append(f"gabarit {g['id']}: cle etrangere")
        for ids in g["champs_par_section"].values():
            for cid in ids:
                if cid not in champs_ids:
                    err.append(f"gabarit {g['id']}: champ inconnu {cid}")
    for e in sortie["exemples_style"]:
        if e["organe_id"] not in organes_ids or (e["prelevement_id"] and e["prelevement_id"] not in prelev_ids):
            err.append(f"exemple {e['id']}: cle etrangere")
        for mid in e["mapping_lesion_ids"]:
            if mid not in mapping_ids:
                err.append(f"exemple {e['id']}: mapping inconnu {mid}")
    for m in sortie["adicap_mappings"]:
        if m["organe_id"] not in organes_ids:
            err.append(f"mapping {m['id']}: organe inconnu")
        for xid in m["exemples_style_ids"]:
            if xid not in ex_ids:
                err.append(f"mapping {m['id']}: exemple inconnu {xid}")
    for p in sortie["plages"]:
        if p.get("organe_id") and p["organe_id"] not in organes_ids:
            err.append(f"plage {p['id']}: organe inconnu")
    for lx in sortie["lexique"]:
        for oid in lx["organes"]:
            if oid not in organes_ids:
                err.append(f"lexique {lx['id']}: organe inconnu {oid}")
    for s in sortie["snomed"]["concepts"]:
        for oid in s["organe_ids"]:
            if oid not in organes_ids:
                err.append(f"snomed {s['id']}: organe inconnu {oid}")
        if s["prov"]["statut_validation"] != "non_valide" or s["prov"]["fiabilite"] != "C":
            err.append(f"snomed {s['id']}: statut/fiabilite attendus non_valide/C")
    # ADICAP : aucun code obsolete ou inconnu
    for o in sortie["organes"]:
        for code in o["adicap_d3"]:
            if not th.actif("D3", code):
                err.append(f"organe {o['id']}: D3 {code} inconnu/obsolete")
    for m in sortie["adicap_mappings"]:
        a = m["adicap"]
        existe, actif = th.lesion_existe(a["lesion"], a["d3"])
        if not (existe and actif):
            err.append(f"mapping {m['id']}: code lesion {a['lesion']} inconnu/obsolete")
        if a["d3"] and not th.actif("D3", a["d3"]):
            err.append(f"mapping {m['id']}: D3 {a['d3']} inconnu/obsolete")
    # regles
    err += tester_regles(sortie["regles"])
    # PII
    for nom, col in sortie.items():
        if nom in ("adicap_thesaurus",):
            continue
        err += [f"PII {nom}{v}" for v in scanner_arbre(col)][:20]
    return err


def construire(date_build: str, sortie_dir: Path, strict: bool = False) -> dict[str, Any]:
    """Orchestre tout le build ; leve ErreurPII / RuntimeError en cas de probleme bloquant."""
    ctx = Contexte(date_build, sortie_dir)
    sources = construire_sources(ctx)
    th = Thesaurus()
    residu_disque = [v for e in charger_json(CANONIQUES, []) for c in ("texte", "lesion", "organe")
                     for v in scanner_pii(str(e.get(c, "")))]
    if strict:
        if residu_disque:
            raise ErreurPII(f"textes_canoniques.json contient encore de la PII : {residu_disque[:3]}")
    elif residu_disque:
        ctx.avertissements.append("textes_canoniques.json sur disque contient de la PII (purge appliquee en memoire) : "
                                  "lancer --purge-textes-canoniques")

    organes, _ = construire_organes(ctx, th)
    ORGANE_D3.clear()
    ORGANE_D3.update({o["id"]: o["adicap_d3"] for o in organes})
    ORGANES_COURANTS[:] = organes
    prelevements = construire_prelevements(ctx, th)
    champs = construire_champs(ctx)
    gabarits = construire_gabarits(ctx, organes, champs)
    organes_ids = {o["id"] for o in organes}
    exemples, mappings, rejets, stats = construire_exemples_et_mappings(ctx, th, organes_ids)
    calculer_couverture(organes, champs, exemples, mappings, gabarits)
    snomed = construire_snomed(ctx, organes)
    echelles = construire_echelles(ctx)
    stations = construire_stations(ctx)
    regles = construire_regles(ctx)
    plages = construire_plages(ctx)
    labels = sorted({(e["lesion_libelle"], e["organe_id"]) for e in exemples})
    lexique = construire_lexique(ctx, th, organes, labels)
    detection = charger_json(SEEDS / "detection.json", {"expressions_neutralisees": []})

    sortie: dict[str, Any] = {
        "sources": sources, "organes": organes, "prelevements": prelevements, "champs": champs, "lexique": lexique,
        "adicap_mappings": mappings, "adicap_rejets": rejets, "snomed": snomed, "regles": regles, "plages": plages,
        "echelles": echelles, "stations": stations, "gabarits": gabarits, "exemples_style": exemples,
        "detection": detection,
    }
    erreurs = valider(sortie, set(ctx.sources), th, ctx)
    if erreurs:
        raise RuntimeError("validation du build en echec :\n  " + "\n  ".join(erreurs[:40]))

    comptes = {
        "sources": len(sources), "organes": len(organes), "prelevements": len(prelevements), "champs": len(champs),
        "lexique": len(lexique), "variantes_stt": sum(len(e["variantes"]) for e in lexique),
        "adicap_concepts": len(th.concepts), "adicap_mappings": len(mappings), "adicap_rejets": len(rejets),
        "snomed_concepts": len(snomed["concepts"]), "regles": len(regles), "plages": len(plages), "echelles": len(echelles),
        "stations": len(stations), "gabarits": len(gabarits), "exemples_style": len(exemples),
    }
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RACINE, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
    except Exception:
        commit = None
    manifest = {
        "kb_version": KB_VERSION, "schema_version": SCHEMA_VERSION, "version": KB_VERSION, "date_build": date_build,
        "build": {"git_commit": commit, "pii_scan": {"ok": True, "regles": len(REGLES_PII), "textes_scannes": ctx.textes_scannes},
                  "regles_testees": sum(len(r["tests"]) for r in regles)},
        "comptes": comptes,
        "ingestion": stats,
        "couverture": {
            "organes_total": len(organes) - 1,
            "organes_avec_champs": sum(1 for o in organes if o["couverture"]["nb_champs"] > 0 and o["id"] != "organe:generique"),
            "organes_avec_gabarit_specifique": sum(1 for o in organes if o["couverture"]["gabarit"] == "specifique"),
            "organes_avec_exemples": sum(1 for o in organes if o["couverture"]["nb_exemples"] > 0),
            "organes_sans_exemples": sorted(o["id"] for o in organes if o["couverture"]["nb_exemples"] == 0 and o["id"] != "organe:generique"),
            "organes_sans_champs": sorted(o["id"] for o in organes if o["couverture"]["nb_champs"] == 0 and o["id"] != "organe:generique"),
        },
        "avertissements": ctx.avertissements,
        "avertissement_juridique": "INCa, ICCR et SNOMED CT : statut juridique a valider avant production (voir `sources`).",
    }

    # ecriture
    for nom in ("sources", "organes", "prelevements", "champs", "regles", "plages", "echelles", "stations", "gabarits", "snomed"):
        ecrire_json(ctx, nom, sortie[nom], lignes=nom in ("champs", "gabarits", "plages", "stations"))
    ecrire_json(ctx, "lexique", lexique, lignes=True)
    ecrire_json(ctx, "exemples_style", exemples, lignes=True)
    ecrire_json(ctx, "adicap_mappings", mappings, lignes=True)
    ecrire_json(ctx, "adicap_rejets", rejets, lignes=True)
    ecrire_json(ctx, "detection", detection)
    ecrire_json(ctx, "adicap_thesaurus", construire_thesaurus(ctx, th), lignes=True)
    ecrire_json(ctx, "manifest", manifest)
    # le repertoire de semences accompagne la sortie par defaut (sinon build de test isole)
    # controle final : la base ecrite est lisible par la facade
    kb = KB(sortie_dir)
    if kb.manifeste().get("comptes") != comptes or not kb.organes():
        raise RuntimeError("la base ecrite n'est pas relisible par projet.kb")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sortie", type=Path, default=KB_DIR)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--purge-textes-canoniques", action="store_true")
    args = ap.parse_args()
    if args.purge_textes_canoniques:
        stats = purger_textes_canoniques()
        print(f"purge PII de {rel(CANONIQUES)} : {stats}")
        return 0
    try:
        m = construire(args.date, args.sortie, args.strict)
    except (ErreurPII, RuntimeError) as e:
        print(f"ECHEC DU BUILD : {e}", file=sys.stderr)
        return 1
    print(f"kb_marc_v3 {m['kb_version']} -> {rel(args.sortie)}")
    for k, v in m["comptes"].items():
        print(f"  {k:18} {v}")
    for a in m["avertissements"]:
        print(f"  avertissement : {a}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
