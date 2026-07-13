"""Systemes de reporting standardises (cytologie + pathologie medicale).

Comble le trou signale par les critiques cyto/medical : sur une cytologie ou une
pathologie medicale, le panneau etait vide faute de template. Ce module PROPOSE
(jamais ne calcule) la categorie/score attendu du systeme applicable, en
[A COMPLETER], si le resultat n'est pas deja RENSEIGNE dans le CR. Respecte le
principe : decrire fidelement, proposer a completer, JAMAIS coter/interpreter.

Detection par mots-cles sur le CR. La "presence" n'est reconnue que si une VALEUR
reelle figure (categorie/grade renseigne) : le simple nom du systeme suivi d'un
slot vide ("selon Banff :.", "a stader selon Amsterdam") NE compte PAS comme
renseigne — le rappel doit alors s'afficher.

NB : les systemes deja couverts par un template d'organe (Bethesda thyroide,
score SAF du foie) ne sont PAS repris ici, pour eviter les doublons de panneau.
"""

from __future__ import annotations

import re

from text_utils import normaliser


def _norm(s: str) -> str:
    # Normalisation partagee + neutralisation des apostrophes (le CR peut contenir
    # des apostrophes courbes U+2019 : "d'IgA" doit matcher le declencheur "d iga")
    # et collapse des espaces.
    return re.sub(r"\s+", " ", normaliser(s.replace("’", " ").replace("'", " ")))


# (mots-cles declencheurs, libelle du champ a completer, regex de RESULTAT rempli).
# Le champ n'est ajoute que si un declencheur est present ET qu'AUCUNE valeur
# renseignee (regex) n'est trouvee.
_SYSTEMS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # -- Cytologie --
    (("epanchement", "liquide pleural", "liquide peritoneal", "ascite",
      "liquide d ascite", "liquide pericardique", "cavite sereuse", "sereuse"),
     "Categorie diagnostique (Systeme international de cytopathologie des "
     "epanchements sereux) et adequation du prelevement",
     r"categorie\s+(nd|am|nfm|sfm|mal)\b|systeme international"),
    (("cytologie urinaire", "cytologie des urines", "urines emises", "mictionnel",
      "lavage vesical", "cytoponction urinaire", "cytologie urine"),
     "Categorie diagnostique (Systeme de Paris) et adequation",
     r"systeme de paris|categorie\s+(auc|shguc|lguc|ngu)\b|negatif pour une "
     r"lesion de haut grade"),
    (("cytoponction salivaire", "cytoponction de la parotide", "parotide cytolog",
      "glande salivaire cytolog", "cytoponction de la glande salivaire"),
     "Categorie (Systeme de Milan) et risque de malignite associe",
     r"systeme de milan|categorie\s+(iv[ab]?|sump|saum|v|vi)\b"),
    (("brossage biliaire", "brossage pancreatique", "brossage des voies biliaires",
      "cpre", "wirsung"),
     "Categorie (Systeme de Papanicolaou pancreatico-biliaire)",
     r"papanicolaou|categorie\s+(negatif|atypique|suspect|positif|nse|snm)"),
    (("frottis cervico", "fcu", "frottis cervical", "frottis du col",
      "col uterin cytolog"),
     "Categorie Bethesda cervical (TBS) et adequation (zone de jonction)",
     r"\b(lsil|hsil|ascus|asc-us|asc-h|agc)\b|negatif pour une lesion "
     r"malpighienne intraepitheliale"),
    (("liquide cephalo", "liquide cephalorachidien", "lcr "),
     "Conclusion cytologique explicite (presence/absence de cellules malignes)",
     r"(absence|presence|pas) de cellule[s]? (maligne|tumorale|suspecte)"),
    # -- Pathologie medicale (proposer le score, ne pas le calculer) --
    (("nephropathie a iga", "depots mesangiaux d iga", "depots mesangiaux diga",
      "iga mesangial", "maladie de berger"),
     "Score Oxford MEST-C (M/E/S/T/C)",
     r"\bmest\b|\bmest-c\b|\bm[01]\s*e[01]\s*s[01]\s*t[0-2]"),
    (("greffon renal", "transplant renal", "rejet du greffon renal",
      "biopsie de greffon renal", "rejet cellulaire aigu du greffon"),
     "Scores de Banff (i, t, v, g, ptc, ci, ct, cg) + C4d + statut DSA + categorie",
     r"banff\s+(categorie|cat\.?)\s*\w|categorie\s+[1-6]\b|\bborderline\b|"
     r"\bia\b|\bib\b|\biia\b|\biib\b|\biii\b"),
    (("greffon hepatique", "rejet hepatique", "transplant hepatique",
      "rejet cellulaire aigu hepatique", "rejet du greffon hepatique"),
     "Score Banff RAI (inflammation portale + canaux + endothelite, /9)",
     r"\brai\b\s*[:=]?\s*\d|rejection activity index\s*[:=]?\s*\d|/\s*9"),
    (("biopsie endomyocardique", "greffon cardiaque", "rejet cardiaque",
      "transplant cardiaque", "rejet du greffon cardiaque"),
     "Grade de rejet ISHLT (0R/1R/2R/3R)",
     r"ishlt|grade\s+[0-3]\s*r\b|\b[0-3]r\b"),
    (("placenta", "chorioamniotite", "villite", "membranes placentaires"),
     "Stade et grade (consensus d Amsterdam) — reponses maternelle et foetale",
     r"stade\s+[1-3]\b.*grade\s+[1-3]\b|amsterdam\s+stade"),
)

# Signaux explicites que le resultat reste A COMPLETER (le nom du systeme est un
# label vide) : ne JAMAIS considerer comme renseigne dans ce cas.
_UNFILLED_RE: re.Pattern[str] = re.compile(
    r"a\s+(stader|classer|grader|coter|preciser|completer|determiner)|"
    r"\[a\s*completer|selon\s+(la\s+)?classification|selon\s+banff\s*:",
)


def suggest_reporting_fields(cr: str) -> list[str]:
    """Retourne les libelles de champs a completer selon le systeme de reporting
    applicable, UNIQUEMENT si un declencheur est present et qu'aucune VALEUR n'est
    deja renseignee (un nom de systeme sur un slot vide ne compte pas)."""
    low = _norm(cr)
    out: list[str] = []
    for triggers, champ, filled_re in _SYSTEMS:
        if not any(t in low for t in triggers):
            continue
        # Valeur reellement renseignee -> ne pas re-proposer.
        if re.search(filled_re, low) and not _UNFILLED_RE.search(low):
            continue
        out.append(champ)
    return out
