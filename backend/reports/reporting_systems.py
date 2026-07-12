"""Systemes de reporting standardises (cytologie + pathologie medicale).

Comble le trou signale par les critiques cyto/medical : sur une cytologie ou une
pathologie medicale, le panneau etait vide faute de template. Ce module PROPOSE
(jamais ne calcule) la categorie/score attendu du systeme applicable, en
[A COMPLETER], si l'element n'est pas deja dans le CR. Respecte le principe :
decrire fidelement, proposer a completer, JAMAIS coter/interpreter a la place.

Detection par mots-cles sur le CR (independant des templates tumoraux).
"""

from __future__ import annotations

import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return s.lower()


# (mots-cles declencheurs, libelle du champ a completer, mot-cle de presence).
# Le champ n'est ajoute que si AUCUN des "presents" n'est deja dans le CR.
_SYSTEMS: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = (
    # -- Cytologie --
    (("epanchement", "liquide pleural", "liquide peritoneal", "ascite",
      "liquide d'ascite", "liquide pericardique", "sereuse"),
     "Categorie diagnostique (Systeme international de cytopathologie des "
     "epanchements sereux) et adequation du prelevement",
     ("systeme international", "categorie nd", "categorie am", "categorie mal",
      "non diagnostique", "atypie de signification")),
    (("cytologie urinaire", "urines", "mictionnel", "lavage vesical",
      "cytoponction urinaire"),
     "Categorie diagnostique (Systeme de Paris) et adequation",
     ("systeme de paris", "categorie auc", "categorie shguc", "negatif pour")),
    (("cytoponction thyroidienne", "cytoponction de la thyroide", "nodule thyroidien"),
     "Categorie Bethesda thyroide (I-VI) et risque de malignite associe",
     ("bethesda", "categorie ii", "categorie iii", "categorie iv", "categorie v",
      "categorie vi")),
    (("frottis cervico", "fcu", "frottis cervical", "col uterin cytolog"),
     "Categorie Bethesda cervical (TBS) et adequation (zone de jonction)",
     ("bethesda", "lsil", "hsil", "ascus", "asc-us", "asc-h", "negatif pour")),
    (("cytoponction salivaire", "cytoponction de la parotide", "parotide cytolog",
      "glande salivaire cytolog"),
     "Categorie (Systeme de Milan) et risque de malignite",
     ("milan", "categorie iv", "categorie sump", "non diagnostique")),
    (("brossage biliaire", "brossage pancreatique", "cpre", "wirsung", "cholangio"),
     "Categorie (Systeme de Papanicolaou pancreatico-biliaire)",
     ("papanicolaou", "categorie vi", "positif pour", "suspect")),
    (("lcr", "liquide cephalo", "liquide cephalorachidien"),
     "Conclusion cytologique explicite (presence/absence de cellules malignes)",
     ("absence de cellule maligne", "pas de cellule maligne", "cellules malignes")),
    # -- Pathologie medicale (proposer le score, ne pas le calculer) --
    (("nephropathie a iga", "depots mesangiaux d'iga", "iga mesangial"),
     "Score Oxford MEST-C (M/E/S/T/C)",
     ("mest", "m0", "m1", "e0", "e1", "s0", "s1", "t0", "t1", "t2")),
    (("greffon renal", "transplant renal", "rejet renal", "biopsie du greffon renal"),
     "Scores de Banff (i, t, v, g, ptc, ci, ct, cg) + C4d + statut DSA + categorie",
     ("banff", "categorie 1", "categorie 2", "borderline")),
    (("steatohepatite", "nash", "steato-hepatite", "foie steatosique"),
     "Score SAF (Steatose/Activite/Fibrose) et stade de fibrose (Kleiner)",
     ("score saf", "s0", "s1", "s2", "s3", "stade f")),
    (("greffon hepatique", "rejet hepatique", "transplant hepatique",
      "rejet cellulaire aigu hepatique"),
     "Score Banff RAI (inflammation portale + canaux + endothelite, /9)",
     ("rai", "rejection activity index", "/9")),
    (("biopsie endomyocardique", "greffon cardiaque", "rejet cardiaque",
      "transplant cardiaque"),
     "Grade de rejet ISHLT (0R/1R/2R/3R)",
     ("ishlt", "grade 0r", "grade 1r", "grade 2r", "grade 3r", "0r", "1r", "2r", "3r")),
    (("placenta", "chorioamniotite", "villite"),
     "Stade et grade (consensus d'Amsterdam) — reponses maternelle et foetale",
     ("amsterdam", "stade 1", "stade 2", "stade 3", "grade 1", "grade 2")),
)


def suggest_reporting_fields(cr: str) -> list[str]:
    """Retourne les libelles de champs a completer selon le systeme de reporting
    applicable (categorie/score), UNIQUEMENT s'ils ne sont pas deja dans le CR."""
    low = _norm(cr)
    out: list[str] = []
    for triggers, champ, presents in _SYSTEMS:
        if not any(t in low for t in triggers):
            continue
        if any(p in low for p in presents):
            continue  # deja renseigne
        out.append(champ)
    return out
