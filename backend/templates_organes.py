"""
Templates organes pour comptes rendus anatomo-pathologiques.
Basé sur les données minimales INCa (Institut National du Cancer) - France.
"""

from pydantic import BaseModel


class ChampObligatoire(BaseModel):
    """Un champ de données obligatoire pour un type de prélèvement."""
    nom: str
    description: str
    section: str
    mots_cles_detection: list[str]
    exemple_formulation: str
    obligatoire: bool = True


class TemplateOrgane(BaseModel):
    """Template complet pour un organe/type de prélèvement."""
    organe: str
    nom_affichage: str
    sous_types: list[str]
    mots_cles_detection: list[str]
    champs_obligatoires: list[ChampObligatoire]
    marqueurs_ihc: list[str]
    systeme_staging: str
    template_macroscopie: str
    template_conclusion: str
    notes_specifiques: str


# ---------------------------------------------------------------------------
# 1. SEIN (Breast)
# ---------------------------------------------------------------------------
TEMPLATE_SEIN: TemplateOrgane = TemplateOrgane(
    organe="sein",
    nom_affichage="Sein",
    sous_types=["biopsie", "microbiopsie", "macrobiopsie", "pièce opératoire", "tumorectomie", "mastectomie", "ganglion sentinelle", "curage axillaire"],
    mots_cles_detection=["sein", "mammaire", "mammo", "mastectomie", "tumorectomie", "macrobiopsie", "microbiopsie", "axillaire", "mamelon", "aréole", "quadrant", "galactophore"],
    marqueurs_ihc=["RE", "RP", "HER2", "Ki67", "E-cadhérine", "CK5/6", "p63", "CK14"],
    systeme_staging="TNM 8e édition - Sein (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [tumorectomie/mastectomie] orientée, pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "À la coupe, lésion tumorale de [X] mm de grand axe, de consistance [ferme/dure], "
        "de couleur [blanchâtre/grisâtre], située à [X] mm de la limite la plus proche. "
        "Encrage des recoupes : [supérieure/inférieure/médiale/latérale/profonde/superficielle]. "
        "Ganglions identifiés : [X] ganglion(s) dans le curage/sentinelle."
    ),
    template_conclusion=(
        "Carcinome [infiltrant de type non spécifique (canalaire) / lobulaire infiltrant / autre] du sein [droit/gauche].\n"
        "- Taille tumorale : [X] mm\n"
        "- Grade SBR modifié Nottingham : [I/II/III] (T:[1-3] + M:[1-3] + N:[1-3] = [3-9])\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Composante in situ : [oui/non], type [canalaire/lobulaire], grade [bas/intermédiaire/haut]\n"
        "- Limites d'exérèse : [saines, la plus proche à X mm / atteintes]\n"
        "- Récepteurs estrogènes (RE) : [positifs/négatifs], [X]% des cellules, intensité [faible/modérée/forte]\n"
        "- Récepteurs progestérone (RP) : [positifs/négatifs], [X]% des cellules, intensité [faible/modérée/forte]\n"
        "- HER2 : score [0/1+/2+/3+] ; FISH/CISH : [amplifiée/non amplifiée] (si 2+)\n"
        "- Ki67 : [X]%\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s), effraction capsulaire [oui/non]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Pour les biopsies : type histologique, grade SBR, RE, RP, HER2, Ki67 sont obligatoires. "
        "Pour les pièces opératoires, ajouter taille, marges, emboles, ganglions, composante in situ, pTNM. "
        "Si HER2 = 2+ (équivoque), une technique d'hybridation in situ (FISH/CISH) est requise. "
        "Vérifier la concordance biopsy/pièce opératoire."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS (carcinome infiltrant de type non spécifique, lobulaire, tubuleux, mucineux, etc.)",
            section="microscopie",
            mots_cles_detection=["carcinome", "infiltrant", "type non spécifique", "canalaire", "lobulaire", "tubuleux", "mucineux", "médullaire", "papillaire", "micropapillaire", "type histologique"],
            exemple_formulation="Carcinome infiltrant de type non spécifique (anciennement canalaire infiltrant)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur infiltrante en millimètres",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "millimètre", "grand axe", "diamètre"],
            exemple_formulation="Taille tumorale : 18 mm de grand axe",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade SBR/Nottingham",
            description="Score de Scarff-Bloom-Richardson modifié Nottingham avec détail des 3 composantes (tubules, mitoses, atypies nucléaires)",
            section="microscopie",
            mots_cles_detection=["grade", "SBR", "Nottingham", "Elston", "Ellis", "tubules", "mitoses", "atypies nucléaires", "score"],
            exemple_formulation="Grade SBR modifié Nottingham : II (T:2 + M:2 + N:2 = 6/9)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut RE",
            description="Récepteurs aux estrogènes : pourcentage de cellules marquées et intensité du marquage",
            section="ihc",
            mots_cles_detection=["récepteurs estrogènes", "RE", "oestrogènes", "estrogen", "ER"],
            exemple_formulation="Récepteurs estrogènes (RE) : positifs, 90% des cellules tumorales, intensité forte",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut RP",
            description="Récepteurs à la progestérone : pourcentage de cellules marquées et intensité du marquage",
            section="ihc",
            mots_cles_detection=["récepteurs progestérone", "RP", "progestérone", "PR"],
            exemple_formulation="Récepteurs progestérone (RP) : positifs, 70% des cellules tumorales, intensité modérée",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut HER2",
            description="Score HER2 en immunohistochimie (0, 1+, 2+, 3+) et résultat FISH/CISH si score 2+",
            section="ihc",
            mots_cles_detection=["HER2", "HER-2", "c-erbB-2", "score 0", "score 1+", "score 2+", "score 3+", "FISH", "CISH", "amplification", "Herceptest"],
            exemple_formulation="HER2 : score 2+ en immunohistochimie. FISH : absence d'amplification (ratio HER2/CEP17 = 1.2)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ki67",
            description="Index de prolifération Ki67 exprimé en pourcentage de cellules tumorales marquées",
            section="ihc",
            mots_cles_detection=["Ki67", "Ki-67", "MIB-1", "prolifération", "index de prolifération"],
            exemple_formulation="Ki67 : 20% des cellules tumorales",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles vasculaires et/ou lymphatiques péri-tumoraux",
            section="microscopie",
            mots_cles_detection=["emboles", "embol", "vasculaires", "lymphatiques", "endovasculaire", "LVSI"],
            exemple_formulation="Emboles vasculaires péri-tumoraux : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "péri-nerveux", "invasion nerveuse", "PNI"],
            exemple_formulation="Engainements périnerveux : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Limites d'exérèse",
            description="Statut des marges chirurgicales avec distance minimale en mm",
            section="microscopie",
            mots_cles_detection=["limites", "marges", "exérèse", "recoupe", "berge", "résection", "distance"],
            exemple_formulation="Limites d'exérèse : saines, la marge la plus proche est la marge profonde à 3 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Composante in situ",
            description="Présence, type (canalaire/lobulaire), grade nucléaire et pourcentage de la composante in situ",
            section="microscopie",
            mots_cles_detection=["in situ", "CCIS", "CLIS", "intracanalaire", "intralobulaire", "composante in situ", "DCIS"],
            exemple_formulation="Composante in situ de type canalaire (CCIS), grade nucléaire intermédiaire, représentant 20% de la lésion",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM", "classification"],
            exemple_formulation="pT1c pN0(sn) (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre total de ganglions examinés et nombre de ganglions envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "adénopathie", "sentinelle", "curage", "métastase ganglionnaire", "envahi"],
            exemple_formulation="Ganglions : 0 envahi sur 2 ganglions sentinelles examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Effraction capsulaire ganglionnaire",
            description="Présence ou absence de rupture capsulaire en cas de ganglion envahi",
            section="microscopie",
            mots_cles_detection=["effraction capsulaire", "rupture capsulaire", "capsule", "extension extraganglionnaire", "extracapsulaire"],
            exemple_formulation="Effraction capsulaire : absente",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 2. CÔLON-RECTUM (Colorectal)
# ---------------------------------------------------------------------------
TEMPLATE_COLON_RECTUM: TemplateOrgane = TemplateOrgane(
    organe="colon_rectum",
    nom_affichage="Côlon-Rectum",
    sous_types=["biopsie", "polypectomie", "mucosectomie", "colectomie", "proctectomie", "résection antérieure", "amputation abdomino-périnéale"],
    mots_cles_detection=["côlon", "colon", "rectum", "rectal", "colique", "sigmoïde", "caecum", "cæcum", "transverse", "ascendant", "descendant", "recto-sigmoïdien", "colectomie", "proctectomie", "polype", "appendice"],
    marqueurs_ihc=["MLH1", "MSH2", "MSH6", "PMS2", "CDX2", "CK20", "CK7"],
    systeme_staging="TNM 8e édition - Côlon/Rectum (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [colectomie droite/gauche/sigmoïdectomie/résection antérieure du rectum] "
        "mesurant [X] cm de longueur. Lésion tumorale [polypoïde/ulcérée/infiltrante/sténosante] "
        "de [X] x [X] cm, siégeant à [X] cm de la marge distale. "
        "Distance à la marge proximale : [X] cm. Distance à la marge distale : [X] cm. "
        "Séreuse en regard : [lisse/rétractée/adhérente]. "
        "Ganglions identifiés dans le méso : [X] ganglion(s). "
        "Qualité du mésorectum (si rectum) : [complet/quasi-complet/incomplet]."
    ),
    template_conclusion=(
        "Adénocarcinome [lieberkühnien/mucineux/autre] du [côlon/rectum] [localisation].\n"
        "- Degré de différenciation : [bien/moyennement/peu différencié]\n"
        "- Niveau d'infiltration : [sous-muqueuse/musculeuse/sous-séreuse/séreuse/organe adjacent]\n"
        "- Distance à la marge distale : [X] mm\n"
        "- Distance à la marge circonférentielle (CRM) : [X] mm (rectum)\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Emboles lymphatiques : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Tumour budding : [Bd1/Bd2/Bd3]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- Statut MMR/MSI : [stable/instable] (MLH1, MSH2, MSH6, PMS2)\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)\n"
        "- Score de régression tumorale (TRG) : [si traitement néoadjuvant]"
    ),
    notes_specifiques=(
        "Minimum 12 ganglions examinés requis pour une évaluation ganglionnaire fiable. "
        "Pour le rectum, la marge de résection circonférentielle (CRM) est critique : positive si ≤ 1 mm. "
        "Qualité du mésorectum à évaluer pour le rectum. "
        "Statut MMR systématique recommandé (dépistage syndrome de Lynch). "
        "Statut KRAS, NRAS, BRAF à déterminer si maladie métastatique."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS",
            section="microscopie",
            mots_cles_detection=["adénocarcinome", "lieberkühnien", "mucineux", "cellules en bague à chaton", "médullaire", "type histologique", "carcinome"],
            exemple_formulation="Adénocarcinome lieberkühnien (de type non spécifique)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Degré de différenciation",
            description="Grade de différenciation histologique",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "bien différencié", "moyennement", "peu différencié", "indifférencié", "grade"],
            exemple_formulation="Adénocarcinome moyennement différencié",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Niveau d'infiltration pT",
            description="Profondeur d'infiltration dans la paroi colique ou rectale",
            section="microscopie",
            mots_cles_detection=["infiltration", "muqueuse", "sous-muqueuse", "musculeuse", "sous-séreuse", "séreuse", "graisse péri-colique", "pT"],
            exemple_formulation="Tumeur infiltrant la sous-séreuse sans atteindre la séreuse (pT3)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge distale",
            description="Distance de la tumeur à la marge de résection distale",
            section="macroscopie",
            mots_cles_detection=["marge distale", "limite distale", "recoupe distale", "distance distale"],
            exemple_formulation="Distance à la marge distale : 45 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge circonférentielle (CRM)",
            description="Distance à la marge de résection circonférentielle pour le rectum, en mm",
            section="microscopie",
            mots_cles_detection=["CRM", "marge circonférentielle", "marge radiale", "mésorectum", "circonférentielle"],
            exemple_formulation="Marge de résection circonférentielle (CRM) : 5 mm (négative)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre total de ganglions examinés (minimum 12 recommandé) et nombre envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "métastase ganglionnaire", "envahi", "examiné"],
            exemple_formulation="Ganglions : 2 envahis sur 18 examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles dans les vaisseaux sanguins",
            section="microscopie",
            mots_cles_detection=["emboles vasculaires", "emboles veineux", "invasion vasculaire", "EMVI"],
            exemple_formulation="Emboles vasculaires : présents (EMVI positif)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles lymphatiques",
            description="Présence ou absence d'emboles dans les vaisseaux lymphatiques",
            section="microscopie",
            mots_cles_detection=["emboles lymphatiques", "invasion lymphatique", "lymphatique"],
            exemple_formulation="Emboles lymphatiques : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "péri-nerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Tumour budding",
            description="Score de tumour budding (Bd1 : 0-4, Bd2 : 5-9, Bd3 : ≥10 bourgeons/0.785 mm²)",
            section="microscopie",
            mots_cles_detection=["tumour budding", "tumor budding", "bourgeonnement tumoral", "budding", "Bd1", "Bd2", "Bd3"],
            exemple_formulation="Tumour budding : Bd2 (7 bourgeons / 0.785 mm²)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut MMR/MSI",
            description="Statut de l'instabilité microsatellitaire par IHC (MLH1, MSH2, MSH6, PMS2) ou biologie moléculaire",
            section="ihc",
            mots_cles_detection=["MSI", "MMR", "microsatellite", "MLH1", "MSH2", "MSH6", "PMS2", "instabilité", "dMMR", "pMMR", "MSS"],
            exemple_formulation="Statut MMR par immunohistochimie : expression conservée de MLH1, MSH2, MSH6 et PMS2 (pMMR/MSS)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut KRAS/NRAS/BRAF",
            description="Statut mutationnel KRAS, NRAS et BRAF V600E (si maladie métastatique)",
            section="biologie_moleculaire",
            mots_cles_detection=["KRAS", "NRAS", "BRAF", "RAS", "V600E", "mutation", "sauvage", "wild-type"],
            exemple_formulation="KRAS exon 2 (codons 12/13) : muté (p.G12D). NRAS : sauvage. BRAF V600E : sauvage.",
            obligatoire=False
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT3 pN1a (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Qualité du mésorectum",
            description="Évaluation macroscopique de la qualité du mésorectum (complet, quasi-complet, incomplet) pour le rectum",
            section="macroscopie",
            mots_cles_detection=["mésorectum", "mesorectum", "qualité", "complet", "quasi-complet", "incomplet"],
            exemple_formulation="Qualité du mésorectum : complet (plan mésorectal intact)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Score de régression tumorale (TRG)",
            description="Score de régression tumorale après traitement néoadjuvant (classification de Mandard ou Dworak)",
            section="microscopie",
            mots_cles_detection=["TRG", "régression", "réponse", "néoadjuvant", "Mandard", "Dworak", "Ryan"],
            exemple_formulation="Score de régression tumorale (TRG) selon Mandard : TRG 3 (régression partielle, fibrose prédominante)",
            obligatoire=False
        ),
    ]
)

# ---------------------------------------------------------------------------
# 3. POUMON (Lung)
# ---------------------------------------------------------------------------
TEMPLATE_POUMON: TemplateOrgane = TemplateOrgane(
    organe="poumon",
    nom_affichage="Poumon",
    sous_types=["biopsie bronchique", "biopsie transthoracique", "résection atypique", "segmentectomie", "lobectomie", "pneumonectomie", "biopsie pleurale", "cytologie"],
    mots_cles_detection=["poumon", "pulmonaire", "bronche", "bronchique", "lobe", "lobectomie", "pneumonectomie", "hilaire", "pleural", "plèvre", "médiastin", "alvéolaire", "parenchyme pulmonaire"],
    marqueurs_ihc=["TTF1", "Napsin A", "p40", "p63", "CK7", "CK5/6", "chromogranine", "synaptophysine", "PD-L1"],
    systeme_staging="TNM 8e édition - Poumon (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [lobectomie/pneumonectomie/segmentectomie] [supérieure/moyenne/inférieure] [droite/gauche] "
        "pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Lésion tumorale de [X] cm de grand axe, à [X] cm de la recoupe bronchique, "
        "[X] cm de la plèvre viscérale. "
        "Aspect [blanchâtre/grisâtre/nécrotique/anthracosique]. "
        "Ganglions hilaires et médiastinaux identifiés : [X] ganglion(s) par station."
    ),
    template_conclusion=(
        "Adénocarcinome / Carcinome épidermoïde / [autre] du poumon [droit/gauche], lobe [supérieur/moyen/inférieur].\n"
        "- Type histologique OMS 2021 : [type et sous-type]\n"
        "- Pattern prédominant : [lépidique/acineux/papillaire/micropapillaire/solide]\n"
        "- Taille tumorale : [X] mm\n"
        "- Invasion pleurale : [PL0/PL1/PL2/PL3]\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Limites chirurgicales : bronchique [saine/envahie], vasculaire [saine/envahie], parenchymateuse [saine/envahie]\n"
        "- Ganglions par station : [détail]\n"
        "- PD-L1 (TPS) : [X]% (clone [22C3/SP263])\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "PIECES OPERATOIRES — STATIONS GANGLIONNAIRES IASLC (obligatoire) :\n"
        "Detailler les ganglions PAR STATION avec le format : 'Loge X : 0/N ganglion(s)'\n"
        "Stations : 2R/2L (paratracheaux sup.), 3 (mediastin ant.), 4R (Barety) / 4L, "
        "5 (aortopulmonaire), 7 (sous-carinaires), 8 (para-oesophagiens), "
        "9 (ligament triangulaire), 10 (hilaires), 11 (interlobaires), "
        "12-13 (peribronchiques), 14 (sous-segmentaires).\n"
        "Mentionner systematiquement : coupe bronchique [saine/envahie], coupes vasculaires [saines/envahies].\n\n"
        "BIOPSIES : TTF1, PD-L1 (clone QR1 ou 22C3), ALK (clone 1A4) systematiques pour les ADK.\n"
        "Panel moleculaire ADK avances : EGFR, ALK, ROS1, KRAS G12C, BRAF V600E, METex14, RET, NTRK, HER2.\n"
        "Marqueurs neuroendocrines si suspicion : Chromogranine A, Synaptophysine, CD56, Ki67.\n"
        "p40 pour confirmer un carcinome epidermoide.\n\n"
        "Adenocarcinomes : preciser TOUS les patterns et le pourcentage de chacun.\n"
        "PD-L1 TPS obligatoire pour tout CBNPC avance. Invasion pleurale : coloration elastique si doute."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique OMS 2021",
            description="Classification OMS 2021 des tumeurs pulmonaires",
            section="microscopie",
            mots_cles_detection=["adénocarcinome", "épidermoïde", "carcinome à petites cellules", "carcinome à grandes cellules", "neuroendocrine", "carcinoïde", "type histologique"],
            exemple_formulation="Adénocarcinome pulmonaire invasif (classification OMS 2021)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Sous-type d'adénocarcinome",
            description="Patterns architecturaux de l'adénocarcinome avec pourcentages",
            section="microscopie",
            mots_cles_detection=["lépidique", "acineux", "papillaire", "micropapillaire", "solide", "pattern", "architecture", "cribriforme"],
            exemple_formulation="Sous-types : acineux 60%, solide 30%, micropapillaire 10%",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Pattern prédominant",
            description="Pattern architectural prédominant de l'adénocarcinome",
            section="microscopie",
            mots_cles_detection=["prédominant", "majoritaire", "principal", "pattern prédominant"],
            exemple_formulation="Pattern prédominant : acineux",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la composante invasive",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm", "grand axe", "composante invasive"],
            exemple_formulation="Taille de la composante invasive : 25 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion pleurale",
            description="Degré d'invasion pleurale selon la classification PL0-PL3",
            section="microscopie",
            mots_cles_detection=["invasion pleurale", "plèvre", "PL0", "PL1", "PL2", "PL3", "pleurale", "élastique"],
            exemple_formulation="Invasion pleurale : PL1 (invasion au-delà de la limitante élastique)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles vasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "embol", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Limites chirurgicales",
            description="Statut des marges bronchique, vasculaire et parenchymateuse",
            section="microscopie",
            mots_cles_detection=["limite", "marge", "recoupe", "bronchique", "vasculaire", "parenchymateuse", "résection"],
            exemple_formulation="Limites chirurgicales : recoupe bronchique saine, recoupe vasculaire saine, marge parenchymateuse à 15 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions par station",
            description="Nombre de ganglions examinés et envahis par station ganglionnaire",
            section="microscopie",
            mots_cles_detection=["ganglion", "station", "hilaire", "médiastinal", "N1", "N2", "envahi", "ganglionnaire"],
            exemple_formulation="Ganglions : station 10 : 0/3, station 7 : 0/2, station 11 : 0/4",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2a pN0 (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="PD-L1 (TPS)",
            description="Expression de PD-L1 en IHC avec le score TPS (Tumor Proportion Score) en pourcentage et le clone utilisé",
            section="ihc",
            mots_cles_detection=["PD-L1", "PDL1", "TPS", "22C3", "SP263", "SP142", "tumor proportion"],
            exemple_formulation="PD-L1 (clone 22C3) : TPS = 60% (positif fort ≥ 50%)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Biologie moléculaire (panel)",
            description="Résultats du panel de biologie moléculaire pour adénocarcinome avancé : EGFR, ALK, ROS1, KRAS, BRAF, MET, RET, NTRK, HER2",
            section="biologie_moleculaire",
            mots_cles_detection=["EGFR", "ALK", "ROS1", "KRAS", "BRAF", "MET", "RET", "NTRK", "HER2", "mutation", "réarrangement", "translocation", "NGS"],
            exemple_formulation="EGFR : sauvage. ALK (FISH/IHC) : négatif. ROS1 : négatif. KRAS : mutation p.G12C. BRAF : sauvage.",
            obligatoire=False
        ),
    ]
)

# ---------------------------------------------------------------------------
# 4. PROSTATE
# ---------------------------------------------------------------------------
TEMPLATE_PROSTATE: TemplateOrgane = TemplateOrgane(
    organe="prostate",
    nom_affichage="Prostate",
    sous_types=["biopsies prostatiques", "résection transurétrale (RTUP)", "prostatectomie radicale", "adénomectomie"],
    mots_cles_detection=["prostate", "prostatique", "prostatectomie", "PSA", "biopsies prostatiques", "RTUP", "résection transurétrale", "vésicule séminale", "adénocarcinome prostatique"],
    marqueurs_ihc=["AMACR/P504S", "p63", "CK5/6", "CK903", "ERG", "NKX3.1", "PSA", "PSMA", "racémase"],
    systeme_staging="TNM 8e édition - Prostate (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de prostatectomie radicale pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Vésicules séminales droite et gauche présentes. "
        "Surface externe encrée. Coupes sériées étagées tous les 3-4 mm. "
        "À la coupe : [lésion identifiable/parenchyme d'aspect homogène]. "
        "Inclusion en totalité selon le protocole de Stanford modifié."
    ),
    template_conclusion=(
        "Adénocarcinome prostatique de type acinaire.\n"
        "- Score de Gleason : [X]+[X]=[X] (Grade ISUP [1-5])\n"
        "- Pourcentage de pattern 4 : [X]%\n"
        "- Pourcentage de pattern 5 : [X]%\n"
        "- Biopsies : [X] positives sur [X] (biopsies)\n"
        "- Longueur tumorale maximale par carotte : [X] mm (biopsies)\n"
        "- Taille tumorale (pièce) : [X] mm\n"
        "- Extension extraprostatique : [absente/focale/étendue]\n"
        "- Envahissement des vésicules séminales : [oui/non]\n"
        "- Marges chirurgicales : [négatives/positives, localisation]\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "BIOPSIES PROSTATIQUES — FORMAT TABLEAU OBLIGATOIRE :\n"
        "Generer un tableau avec les colonnes :\n"
        "| Siege (blocs) | Longueur biopsie (mm) | Longueur cancer (mm) | Nb biopsies +/total | Score de Gleason | EPN | Extension EP |\n"
        "Lignes : Droite (Base, PM, Apex, TOTAL) puis Gauche (Base, PM, Apex, TOTAL) puis Cible si applicable.\n"
        "Abreviations standard : E=Envahi, S=Sain, P=Penetre, IC=IntraCapsulaire, EP=ExtraProstatique, "
        "EPN=Engainement PeriNerveux, NV=Non Vu, PIN=Neoplasie IntraEpitheliale Prostatique, PM=Partie Moyenne.\n\n"
        "CONCLUSION standard : 'Adenocarcinome prostatique acineux [bien/moyennement/peu] differencie, "
        "de score de Gleason X (X+X), histopronostic ISUP groupe X, observe au niveau des biopsies [sites]. "
        "Phenotype IHC : glandes tumorales p504s+/p63-.'\n\n"
        "Grade ISUP : 1 (3+3), 2 (3+4), 3 (4+3), 4 (4+4 ou 3+5 ou 5+3), 5 (4+5 ou 5+4 ou 5+5).\n"
        "IHC si diagnostic incertain : p504s (AMACR/racemase) + p63. Phenotype tumoral : p504s+/p63-."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Score de Gleason / Grade ISUP",
            description="Score de Gleason (somme des deux patterns les plus représentés) et grade ISUP correspondant (1 à 5)",
            section="microscopie",
            mots_cles_detection=["Gleason", "ISUP", "grade", "score", "pattern", "3+3", "3+4", "4+3", "4+4", "4+5", "5+4", "5+5", "groupe pronostique"],
            exemple_formulation="Score de Gleason : 3+4=7 (Grade ISUP 2)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Pourcentage de chaque pattern de Gleason",
            description="Proportion de chaque grade de Gleason (patterns 3, 4, 5)",
            section="microscopie",
            mots_cles_detection=["pourcentage", "pattern", "proportion", "% pattern 4", "% pattern 5", "tertiaire"],
            exemple_formulation="Pattern 3 : 60%, pattern 4 : 35%, pattern 5 : 5%",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Nombre de biopsies positives / total",
            description="Nombre de carottes biopsiques envahies par rapport au nombre total",
            section="microscopie",
            mots_cles_detection=["biopsies positives", "carottes positives", "carottes envahies", "sur", "total"],
            exemple_formulation="6 carottes positives sur 12 prélevées",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Longueur tumorale par carotte",
            description="Longueur de tissu tumoral par carotte biopsique en mm",
            section="microscopie",
            mots_cles_detection=["longueur tumorale", "longueur de tissu tumoral", "mm de tumeur", "longueur carotte"],
            exemple_formulation="Longueur tumorale maximale : 8 mm sur la carotte apex droit",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale (pièce)",
            description="Dimension du foyer tumoral principal sur pièce de prostatectomie",
            section="macroscopie",
            mots_cles_detection=["taille tumorale", "dimension", "foyer tumoral", "volume tumoral"],
            exemple_formulation="Foyer tumoral principal : 22 mm de grand axe (lobe droit)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension extraprostatique",
            description="Présence et étendue de l'extension tumorale au-delà de la capsule prostatique",
            section="microscopie",
            mots_cles_detection=["extension extraprostatique", "extracapsulaire", "au-delà de la capsule", "EPE", "extra-prostatique", "capsule"],
            exemple_formulation="Extension extraprostatique focale en postéro-latéral droit",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Envahissement des vésicules séminales",
            description="Présence ou absence d'envahissement des vésicules séminales",
            section="microscopie",
            mots_cles_detection=["vésicule séminale", "vésicules séminales", "envahissement séminal"],
            exemple_formulation="Vésicules séminales : non envahies",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection chirurgicale et localisation si positives",
            section="microscopie",
            mots_cles_detection=["marge", "marges chirurgicales", "limite", "recoupe", "résection", "encrage", "R0", "R1"],
            exemple_formulation="Marges chirurgicales : positives en postéro-latéral droit sur 3 mm (Gleason 4)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles vasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT3a pN0 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 5. ESTOMAC (Stomach)
# ---------------------------------------------------------------------------
TEMPLATE_ESTOMAC: TemplateOrgane = TemplateOrgane(
    organe="estomac",
    nom_affichage="Estomac",
    sous_types=["biopsie", "mucosectomie", "dissection sous-muqueuse", "gastrectomie partielle", "gastrectomie totale"],
    mots_cles_detection=["estomac", "gastrique", "gastrectomie", "fundus", "antre", "pylore", "cardia", "jonction oeso-gastrique", "gastro"],
    marqueurs_ihc=["HER2", "MLH1", "MSH2", "MSH6", "PMS2", "PD-L1", "Claudin 18.2", "CDX2", "CK7", "CK20"],
    systeme_staging="TNM 8e édition - Estomac (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de gastrectomie [partielle/totale] mesurant [X] cm le long de la grande courbure. "
        "Lésion tumorale [ulcérée/bourgeonnante/infiltrante] de [X] x [X] cm siégeant au niveau de [localisation]. "
        "Distance à la marge proximale : [X] cm. Distance à la marge distale : [X] cm. "
        "Séreuse en regard : [lisse/rétractée]. "
        "Ganglions identifiés dans le curage : [X] ganglion(s)."
    ),
    template_conclusion=(
        "Adénocarcinome gastrique [type histologique].\n"
        "- Classification de Lauren : [intestinal/diffus/mixte]\n"
        "- Degré de différenciation : [bien/moyennement/peu différencié]\n"
        "- Niveau d'infiltration : [muqueuse/sous-muqueuse/musculeuse/sous-séreuse/séreuse]\n"
        "- Distance à la marge proximale : [X] mm\n"
        "- Distance à la marge distale : [X] mm\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Emboles lymphatiques : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- Statut HER2 : [score IHC]\n"
        "- MSI/MMR : [statut]\n"
        "- PD-L1 (CPS) : [X]\n"
        "- Claudin 18.2 : [statut]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Minimum 16 ganglions examinés recommandés pour une stadification fiable. "
        "HER2 : grille de scoring spécifique pour l'estomac (différente du sein). "
        "PD-L1 exprimé en CPS (Combined Positive Score) et non en TPS. "
        "Claudin 18.2 : nouveau biomarqueur thérapeutique (zolbetuximab). "
        "Classification de Lauren à intégrer systématiquement."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS",
            section="microscopie",
            mots_cles_detection=["adénocarcinome", "tubuleux", "papillaire", "mucineux", "cellules en bague à chaton", "peu cohésif", "type histologique"],
            exemple_formulation="Adénocarcinome gastrique de type tubuleux",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Classification de Lauren",
            description="Type selon la classification de Lauren (intestinal, diffus, mixte)",
            section="microscopie",
            mots_cles_detection=["Lauren", "intestinal", "diffus", "mixte", "classification de Lauren"],
            exemple_formulation="Classification de Lauren : type intestinal",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Degré de différenciation",
            description="Grade de différenciation histologique",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "grade", "bien", "moyennement", "peu"],
            exemple_formulation="Adénocarcinome moyennement différencié",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Niveau d'infiltration pT",
            description="Profondeur d'envahissement dans la paroi gastrique",
            section="microscopie",
            mots_cles_detection=["infiltration", "muqueuse", "sous-muqueuse", "musculeuse", "sous-séreuse", "séreuse", "pT"],
            exemple_formulation="Infiltration atteignant la sous-séreuse sans franchir la séreuse (pT3)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge proximale",
            description="Distance de la tumeur à la marge de résection proximale",
            section="macroscopie",
            mots_cles_detection=["marge proximale", "limite proximale", "recoupe proximale"],
            exemple_formulation="Distance à la marge proximale : 35 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge distale",
            description="Distance de la tumeur à la marge de résection distale",
            section="macroscopie",
            mots_cles_detection=["marge distale", "limite distale", "recoupe distale"],
            exemple_formulation="Distance à la marge distale : 50 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre total de ganglions examinés (minimum 16) et nombre envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "examiné", "métastase ganglionnaire"],
            exemple_formulation="Ganglions : 3 envahis sur 22 examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires et lymphatiques",
            description="Présence ou absence d'emboles vasculaires et lymphatiques",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "lymphatiques", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires : présents. Emboles lymphatiques : présents.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut HER2",
            description="Score HER2 en IHC (scoring gastrique spécifique) avec FISH/CISH si 2+",
            section="ihc",
            mots_cles_detection=["HER2", "HER-2", "score 0", "score 1+", "score 2+", "score 3+", "FISH", "amplification"],
            exemple_formulation="HER2 (scoring gastrique) : score 3+ (positif)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut MSI/MMR",
            description="Statut de l'instabilité microsatellitaire par IHC ou biologie moléculaire",
            section="ihc",
            mots_cles_detection=["MSI", "MMR", "MLH1", "MSH2", "MSH6", "PMS2", "microsatellite", "instabilité"],
            exemple_formulation="Statut MMR : perte d'expression de MLH1 et PMS2 (dMMR/MSI-H)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="PD-L1 (CPS)",
            description="Expression de PD-L1 en CPS (Combined Positive Score)",
            section="ihc",
            mots_cles_detection=["PD-L1", "CPS", "combined positive score", "PDL1"],
            exemple_formulation="PD-L1 (clone 22C3) : CPS = 15",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Claudin 18.2",
            description="Expression de Claudin 18.2 en immunohistochimie",
            section="ihc",
            mots_cles_detection=["Claudin", "CLDN18", "claudin 18.2", "claudine"],
            exemple_formulation="Claudin 18.2 : expression positive (marquage modéré à fort dans 80% des cellules tumorales)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT3 pN2 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 6. THYROÏDE
# ---------------------------------------------------------------------------
TEMPLATE_THYROIDE: TemplateOrgane = TemplateOrgane(
    organe="thyroide",
    nom_affichage="Thyroïde",
    sous_types=["cytoponction", "lobo-isthmectomie", "thyroïdectomie totale", "curage ganglionnaire"],
    mots_cles_detection=["thyroïde", "thyroïdien", "thyroïdienne", "thyroïdectomie", "lobo-isthmectomie", "lobe thyroïdien", "isthme", "parathyroïde", "nodule thyroïdien", "Bethesda"],
    marqueurs_ihc=["TTF1", "thyroglobuline", "PAX8", "calcitonine", "chromogranine", "ACE", "HBME-1", "CK19", "galectine-3"],
    systeme_staging="TNM 8e édition - Thyroïde (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [lobo-isthmectomie/thyroïdectomie totale] pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Nodule de [X] mm, [encapsulé/mal limité], de consistance [ferme/dure], "
        "de couleur [blanchâtre/brunâtre]. "
        "Capsule thyroïdienne [intacte/infiltrée]. "
        "Parenchyme thyroïdien adjacent : [normal/goitre multinodulaire/thyroïdite]."
    ),
    template_conclusion=(
        "Carcinome [papillaire/folliculaire/médullaire/anaplasique] de la thyroïde.\n"
        "- Sous-type : [classique/folliculaire/variante à cellules hautes/etc.]\n"
        "- Taille tumorale : [X] mm\n"
        "- Multifocalité : [oui (nombre de foyers)/non]\n"
        "- Extension extrathyroïdienne : [absente/minimale/massive]\n"
        "- Marges chirurgicales : [saines/envahies]\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Invasion capsulaire : [absente/minimale/extensive]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "La classification OMS 2022 distingue les tumeurs thyroïdiennes folliculaires borderline (NIFTP, tumeur folliculaire de potentiel de malignité incertain). "
        "Pour les carcinomes folliculaires : invasion capsulaire et vasculaire sont les critères diagnostiques clés. "
        "Carcinome médullaire : dosage de la calcitonine et ACE sériques, recherche mutation RET. "
        "BRAF V600E est le marqueur moléculaire le plus fréquent dans le carcinome papillaire."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS 2022",
            section="microscopie",
            mots_cles_detection=["carcinome papillaire", "carcinome folliculaire", "carcinome médullaire", "carcinome anaplasique", "indifférencié", "type histologique"],
            exemple_formulation="Carcinome papillaire de la thyroïde",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Sous-type histologique",
            description="Variante histologique du carcinome thyroïdien",
            section="microscopie",
            mots_cles_detection=["variante", "sous-type", "classique", "folliculaire", "cellules hautes", "sclérosant diffus", "oncocytaire", "trabéculaire", "cribriforme"],
            exemple_formulation="Carcinome papillaire, variante classique",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur en mm",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm", "grand axe"],
            exemple_formulation="Taille tumorale : 15 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Multifocalité",
            description="Présence de foyers tumoraux multiples et nombre de foyers",
            section="microscopie",
            mots_cles_detection=["multifocal", "multifocalité", "foyer", "foyers", "bilatéral", "unifocal"],
            exemple_formulation="Tumeur multifocale : 3 foyers (15 mm, 5 mm, 2 mm)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension extrathyroïdienne",
            description="Extension au-delà de la capsule thyroïdienne (absente, minimale, massive)",
            section="microscopie",
            mots_cles_detection=["extension extrathyroïdienne", "extra-thyroïdienne", "capsule thyroïdienne", "tissu adipeux périthyroïdien", "muscle", "extension"],
            exemple_formulation="Extension extrathyroïdienne minimale (tissu adipeux périthyroïdien)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "limite", "résection", "recoupe", "encrage"],
            exemple_formulation="Marges chirurgicales : saines",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles vasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "invasion vasculaire", "angioinvasion"],
            exemple_formulation="Emboles vasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion capsulaire",
            description="Présence et degré d'invasion de la capsule tumorale (important pour les tumeurs folliculaires)",
            section="microscopie",
            mots_cles_detection=["invasion capsulaire", "capsule tumorale", "effraction capsulaire", "capsule"],
            exemple_formulation="Invasion capsulaire : focale (1 foyer d'effraction)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "compartiment central", "latéral"],
            exemple_formulation="Ganglions : 1 envahi sur 6 examinés (compartiment central)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT1b pN1a (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Biologie moléculaire",
            description="Statut BRAF V600E et/ou mutations RAS si applicable",
            section="biologie_moleculaire",
            mots_cles_detection=["BRAF", "V600E", "RAS", "NRAS", "HRAS", "KRAS", "mutation", "moléculaire", "RET", "PAX8-PPARG"],
            exemple_formulation="BRAF V600E : muté",
            obligatoire=False
        ),
    ]
)

# ---------------------------------------------------------------------------
# 7. REIN
# ---------------------------------------------------------------------------
TEMPLATE_REIN: TemplateOrgane = TemplateOrgane(
    organe="rein",
    nom_affichage="Rein",
    sous_types=["biopsie", "néphrectomie partielle", "tumorectomie rénale", "néphrectomie élargie"],
    mots_cles_detection=["rein", "rénal", "rénale", "néphrectomie", "surrénale", "pyélocaliciel", "uretère", "hile rénal", "carcinome rénal", "tumeur rénale"],
    marqueurs_ihc=["PAX8", "CD10", "vimentine", "CK7", "CA IX", "racémase/AMACR", "TFE3", "cathepsine K", "CD117"],
    systeme_staging="TNM 8e édition - Rein (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [néphrectomie partielle/élargie] [droite/gauche] pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Tumeur de [X] cm, [bien limitée/mal limitée], [encapsulée/non encapsulée], "
        "de couleur [jaune doré/grisâtre/brunâtre/hétérogène], avec [nécrose/hémorragie/kystisation]. "
        "Distance à la marge chirurgicale : [X] mm. "
        "Graisse péri-rénale : [saine/infiltrée]. Surrénale : [présente/absente, saine/infiltrée]. "
        "Veine rénale : [libre/envahie]."
    ),
    template_conclusion=(
        "Carcinome rénal à [cellules claires/type papillaire type 1/type 2/chromophobe/etc.].\n"
        "- Grade nucléaire ISUP/OMS : [1/2/3/4]\n"
        "- Taille tumorale : [X] mm\n"
        "- Nécrose tumorale : [présente/absente]\n"
        "- Invasion de la graisse péri-rénale : [oui/non]\n"
        "- Invasion de la veine rénale : [oui/non]\n"
        "- Invasion du système collecteur : [oui/non]\n"
        "- Marges chirurgicales : [saines/envahies]\n"
        "- Surrénale : [saine/envahie/non prélevée]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Le grade nucléaire ISUP/OMS remplace le grade de Fuhrman depuis 2016. "
        "Grade 4 : différenciation sarcomatoïde ou rhabdoïde. "
        "Pour le carcinome rénal à cellules claires : la nécrose tumorale est un facteur pronostique indépendant. "
        "Classification OMS 2022 inclut de nouvelles entités (carcinome rénal associé au TFEB, etc.)."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS 2022",
            section="microscopie",
            mots_cles_detection=["cellules claires", "papillaire", "chromophobe", "oncocytome", "carcinome rénal", "type 1", "type 2", "translocation", "collecteur"],
            exemple_formulation="Carcinome rénal à cellules claires",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade nucléaire ISUP/OMS",
            description="Grade nucléaire de 1 à 4 selon le système ISUP/OMS",
            section="microscopie",
            mots_cles_detection=["grade nucléaire", "ISUP", "Fuhrman", "grade 1", "grade 2", "grade 3", "grade 4", "sarcomatoïde", "rhabdoïde"],
            exemple_formulation="Grade nucléaire ISUP : 2/4",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm", "grand axe"],
            exemple_formulation="Taille tumorale : 45 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Nécrose tumorale",
            description="Présence ou absence de nécrose tumorale",
            section="microscopie",
            mots_cles_detection=["nécrose", "nécrotique", "plage de nécrose"],
            exemple_formulation="Nécrose tumorale : absente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion de la graisse péri-rénale",
            description="Extension tumorale dans la graisse péri-rénale ou du sinus rénal",
            section="microscopie",
            mots_cles_detection=["graisse péri-rénale", "graisse du sinus", "péri-rénale", "tissu adipeux péri-rénal", "capsule rénale"],
            exemple_formulation="Invasion de la graisse péri-rénale : absente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion de la veine rénale",
            description="Présence ou absence de thrombus tumoral dans la veine rénale",
            section="microscopie",
            mots_cles_detection=["veine rénale", "thrombus", "invasion veineuse", "veine cave"],
            exemple_formulation="Veine rénale : libre de toute invasion tumorale",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion du système collecteur",
            description="Envahissement des cavités pyélocalicielles",
            section="microscopie",
            mots_cles_detection=["système collecteur", "pyélocaliciel", "bassinet", "calice", "voie excrétrice"],
            exemple_formulation="Système collecteur : non envahi",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "résection", "recoupe", "limite"],
            exemple_formulation="Marges chirurgicales : saines (distance minimale 5 mm)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Surrénale",
            description="Statut de la glande surrénale (envahie, saine, non prélevée)",
            section="microscopie",
            mots_cles_detection=["surrénale", "surrénalienne", "glande surrénale"],
            exemple_formulation="Surrénale homolatérale : parenchyme surrénalien sans anomalie",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT1b pNx (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 8. VESSIE
# ---------------------------------------------------------------------------
TEMPLATE_VESSIE: TemplateOrgane = TemplateOrgane(
    organe="vessie",
    nom_affichage="Vessie",
    sous_types=["résection transurétrale de vessie (RTUV)", "biopsie vésicale", "cystectomie partielle", "cystectomie radicale"],
    mots_cles_detection=["vessie", "vésical", "vésicale", "cystectomie", "RTUV", "résection transurétrale", "urothélial", "urothélium", "dôme vésical", "trigone", "détrusor"],
    marqueurs_ihc=["CK7", "CK20", "GATA3", "p63", "CK5/6", "p53", "Ki67", "uroplakine"],
    systeme_staging="TNM 8e édition - Vessie (AJCC/UICC)",
    template_macroscopie=(
        "Copeaux de résection transurétrale pesant [X] g au total, [X] cassettes. "
        "Ou : Pièce de cystectomie [partielle/radicale] mesurant [X] x [X] x [X] cm. "
        "Lésion tumorale [papillaire/sessile/ulcérée] de [X] cm. "
        "Présence de muscle détrusor identifiable : [oui/non]. "
        "Graisse périvésicale : [saine/infiltrée]. "
        "Uretères et urètre : [sains/envahis]."
    ),
    template_conclusion=(
        "Carcinome urothélial [papillaire/infiltrant] de la vessie.\n"
        "- Grade : [bas grade / haut grade]\n"
        "- Niveau d'infiltration : [Ta/Tis/T1/T2a/T2b/T3/T4]\n"
        "- Présence de muscle détrusor dans le prélèvement : [oui/non]\n"
        "- Invasion du muscle détrusor : [oui/non]\n"
        "- Emboles lymphovasculaires : [présents/absents]\n"
        "- CIS associé : [oui/non]\n"
        "- Variantes histologiques : [aucune / micropapillaire / plasmocytoïde / sarcomatoïde / etc.]\n"
        "- Marges (cystectomie) : [saines/envahies]\n"
        "- Ganglions (cystectomie) : [X] envahi(s) sur [X] examiné(s)\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "La présence de muscle détrusor (musculeuse propre) dans la RTUV est CRITIQUE pour la stadification. "
        "Si absent, une re-RTUV est indiquée pour les tumeurs T1 haut grade. "
        "Les variantes histologiques (micropapillaire, plasmocytoïde, sarcomatoïde, neuroendocrine) modifient la prise en charge. "
        "Le CIS associé doit être recherché systématiquement."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS",
            section="microscopie",
            mots_cles_detection=["carcinome urothélial", "transitionnel", "épidermoïde", "adénocarcinome", "neuroendocrine", "type histologique"],
            exemple_formulation="Carcinome urothélial infiltrant",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade tumoral",
            description="Grade selon la classification OMS 2022 (bas grade / haut grade)",
            section="microscopie",
            mots_cles_detection=["grade", "bas grade", "haut grade", "low grade", "high grade", "G1", "G2", "G3"],
            exemple_formulation="Carcinome urothélial de haut grade",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Niveau d'infiltration",
            description="Profondeur d'invasion (Ta, Tis, T1, T2a, T2b, T3, T4)",
            section="microscopie",
            mots_cles_detection=["infiltration", "invasion", "Ta", "Tis", "T1", "T2", "musculeuse", "détrusor", "chorion", "lamina propria", "sous-muqueuse"],
            exemple_formulation="Infiltration du chorion (lamina propria) sans atteinte de la musculeuse propre (pT1)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Présence de muscle détrusor",
            description="Présence ou absence de muscle détrusor (musculeuse propre) dans le prélèvement de RTUV",
            section="microscopie",
            mots_cles_detection=["muscle", "détrusor", "musculeuse propre", "muscularis propria", "présence de muscle"],
            exemple_formulation="Muscle détrusor (musculeuse propre) : présent dans le prélèvement, non envahi",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion du muscle détrusor",
            description="Présence ou absence d'invasion du muscle détrusor",
            section="microscopie",
            mots_cles_detection=["invasion musculaire", "envahissement musculaire", "muscle envahi", "détrusor envahi", "TVIM", "TVNIM"],
            exemple_formulation="Absence d'invasion du muscle détrusor (TVNIM)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles lymphovasculaires",
            description="Présence ou absence d'emboles lymphovasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "lymphovasculaires", "vasculaires", "LVI"],
            exemple_formulation="Emboles lymphovasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="CIS associé",
            description="Présence ou absence de carcinome in situ (CIS) associé",
            section="microscopie",
            mots_cles_detection=["CIS", "carcinome in situ", "Tis", "in situ"],
            exemple_formulation="CIS associé : présent en périphérie de la lésion infiltrante",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Variantes histologiques",
            description="Présence de variantes histologiques (micropapillaire, plasmocytoïde, sarcomatoïde, neuroendocrine, etc.)",
            section="microscopie",
            mots_cles_detection=["variante", "micropapillaire", "plasmocytoïde", "sarcomatoïde", "neuroendocrine", "nid", "en nids", "lymphoépithélial"],
            exemple_formulation="Variante micropapillaire focale (15% de la tumeur)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales (cystectomie)",
            description="Statut des marges de résection (uretères, urètre, tissu mou périvésical)",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "recoupe", "urétérale", "urétrale", "résection"],
            exemple_formulation="Marges chirurgicales : recoupes urétérales droite et gauche saines, recoupe urétrale saine",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions (cystectomie)",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "pelvien", "obturateur", "iliaque"],
            exemple_formulation="Ganglions : 0 envahi sur 16 examinés (curage ilio-obturateur bilatéral)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2a pN0 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 9. COL UTÉRIN (Cervix)
# ---------------------------------------------------------------------------
TEMPLATE_COL_UTERIN: TemplateOrgane = TemplateOrgane(
    organe="col_uterin",
    nom_affichage="Col utérin",
    sous_types=["biopsie", "conisation", "hystérectomie simple", "hystérectomie élargie (Wertheim)", "trachélectomie"],
    mots_cles_detection=["col utérin", "col de l'utérus", "cervical", "cervicale", "conisation", "exocol", "endocol", "zone de jonction", "CIN", "trachélectomie", "Wertheim", "paramètre"],
    marqueurs_ihc=["p16", "Ki67", "p63", "CK5/6", "CK7", "CEA", "vimentine"],
    systeme_staging="TNM 8e édition / FIGO 2018 - Col utérin",
    template_macroscopie=(
        "Pièce de [conisation/hystérectomie] mesurant [X] x [X] x [X] cm. "
        "Lésion [visible/non visible macroscopiquement] de [X] cm au niveau de [exocol/endocol]. "
        "Paramètres [droite/gauche] mesurant [X] cm. "
        "Col inclus en totalité selon le protocole [horaire/sérié]."
    ),
    template_conclusion=(
        "Carcinome [épidermoïde / adénocarcinome / adénosquameux] du col utérin.\n"
        "- Taille tumorale : [X] mm\n"
        "- Profondeur d'invasion : [X] mm (épaisseur totale du col : [X] mm)\n"
        "- Extension : paramètres [libres/envahis], vagin [libre/envahi], corps utérin [libre/envahi]\n"
        "- Emboles lymphovasculaires : [présents/absents]\n"
        "- Marges chirurgicales : [saines/envahies] (endocervicale, exocervicale, profonde, vaginale)\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- p16 : [positif diffus en bloc / négatif / focal]\n"
        "- pTNM : pT[X] pN[X] / FIGO [stade]"
    ),
    notes_specifiques=(
        "La classification FIGO 2018 du col utérin intègre désormais l'atteinte ganglionnaire. "
        "p16 positif en bloc est le surrogat de l'infection HPV à haut risque. "
        "Pour les conisations : orientation horaire, inclusion en totalité, état des berges endocervicale et exocervicale. "
        "Les marges de conisation sont cruciales pour décider de la suite thérapeutique."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique du carcinome cervical",
            section="microscopie",
            mots_cles_detection=["carcinome épidermoïde", "adénocarcinome", "adénosquameux", "neuroendocrine", "type histologique"],
            exemple_formulation="Carcinome épidermoïde bien différencié, kératinisant",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur en mm",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 22 mm de grand axe",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Profondeur d'invasion",
            description="Profondeur d'invasion stromale en mm",
            section="microscopie",
            mots_cles_detection=["profondeur", "invasion", "stromale", "infiltration", "épaisseur"],
            exemple_formulation="Profondeur d'invasion stromale : 8 mm (épaisseur totale du stroma : 15 mm)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension aux structures adjacentes",
            description="Extension aux paramètres, vagin, corps utérin",
            section="microscopie",
            mots_cles_detection=["paramètre", "paramètres", "vagin", "vaginal", "corps utérin", "extension", "paroi pelvienne"],
            exemple_formulation="Paramètres droit et gauche : libres. Vagin : libre. Corps utérin : non envahi.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles lymphovasculaires",
            description="Présence ou absence d'emboles lymphovasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "lymphovasculaires", "vasculaires", "LVSI"],
            exemple_formulation="Emboles lymphovasculaires : présents, focaux",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection (endocervicale, exocervicale, profonde, vaginale)",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "recoupe", "berge", "endocervicale", "exocervicale", "vaginale", "limite"],
            exemple_formulation="Marges chirurgicales : marge endocervicale saine (5 mm), marge vaginale saine (10 mm), marge profonde saine",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "sentinelle", "pelvien", "iliaque"],
            exemple_formulation="Ganglions : 0 envahi sur 18 examinés (curage pelvien bilatéral)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="p16 (IHC)",
            description="Expression de p16 en immunohistochimie (marqueur surrogat de HPV haut risque)",
            section="ihc",
            mots_cles_detection=["p16", "p16INK4a", "HPV", "en bloc", "diffus"],
            exemple_formulation="p16 : positif, marquage diffus en bloc (surrogat HPV haut risque)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM / FIGO",
            description="Classification pTNM et stade FIGO 2018",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "FIGO", "stade", "TNM"],
            exemple_formulation="pT1b1 pN0 - FIGO IB1 (AJCC 8e édition / FIGO 2018)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 10. ENDOMÈTRE (Endometrium)
# ---------------------------------------------------------------------------
TEMPLATE_ENDOMETRE: TemplateOrgane = TemplateOrgane(
    organe="endometre",
    nom_affichage="Endomètre",
    sous_types=["biopsie endométriale", "curetage", "hystérectomie totale", "hystérectomie avec annexectomie bilatérale"],
    mots_cles_detection=["endomètre", "endométrial", "endométriale", "cavité utérine", "utérus", "myomètre", "corps utérin", "hystérectomie", "curetage", "adénocarcinome endométrioïde"],
    marqueurs_ihc=["RE", "RP", "p53", "MLH1", "MSH2", "MSH6", "PMS2", "PTEN", "L1CAM", "ARID1A", "napsin A", "WT1"],
    systeme_staging="TNM 8e édition / FIGO 2023 - Endomètre",
    template_macroscopie=(
        "Pièce d'hystérectomie totale avec annexectomie bilatérale. "
        "Utérus mesurant [X] x [X] x [X] cm, pesant [X] g. "
        "À l'ouverture, lésion tumorale [polypoïde/endophytique/infiltrante] "
        "de [X] x [X] cm au niveau du [fond/corps/isthme]. "
        "Infiltration macroscopique du myomètre : [< 50% / ≥ 50%]. "
        "Col utérin : [sain/envahi]. "
        "Trompes et ovaires : [sans anomalie macroscopique]."
    ),
    template_conclusion=(
        "Adénocarcinome endométrioïde / [autre type] de l'endomètre.\n"
        "- Grade FIGO : [1/2/3]\n"
        "- Profondeur d'invasion myométriale : [< 50% / ≥ 50%] (myomètre envahi : [X] mm / épaisseur totale : [X] mm)\n"
        "- Extension au col : [oui/non] (glandulaire seule / stromale)\n"
        "- Emboles lymphovasculaires : [absents/focaux/extensifs]\n"
        "- Marges chirurgicales : [saines]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- MMR/MSI : MLH1 [conservé/perdu], MSH2 [conservé/perdu], MSH6 [conservé/perdu], PMS2 [conservé/perdu]\n"
        "- p53 : [wild-type / muté (surexpression ou absence totale)]\n"
        "- RE : [X]%, RP : [X]%\n"
        "- pTNM : pT[X] pN[X] / FIGO [stade]"
    ),
    notes_specifiques=(
        "Classification moléculaire TCGA en 4 groupes (ProMisE/TransPORTEC) : POLE ultramutant, dMMR/MSI-H, p53 muté, NSMP. "
        "FIGO 2023 intègre la classification moléculaire dans la stadification. "
        "Les emboles lymphovasculaires extensifs (LVSI substantiel) modifient le stade FIGO 2023. "
        "Le statut MMR est systématique (dépistage syndrome de Lynch et implications thérapeutiques)."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS 2020",
            section="microscopie",
            mots_cles_detection=["endométrioïde", "séreux", "cellules claires", "carcinosarcome", "indifférencié", "dédifférencié", "mucineux", "type histologique"],
            exemple_formulation="Adénocarcinome endométrioïde",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade FIGO",
            description="Grade architectural FIGO (1 : ≤5% solide, 2 : 6-50% solide, 3 : >50% solide)",
            section="microscopie",
            mots_cles_detection=["grade FIGO", "grade 1", "grade 2", "grade 3", "grade", "composante solide"],
            exemple_formulation="Grade FIGO 1 (composante solide < 5%)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Profondeur d'invasion myométriale",
            description="Évaluation de l'invasion du myomètre (< 50% ou ≥ 50%)",
            section="microscopie",
            mots_cles_detection=["invasion myométriale", "myomètre", "infiltration", "moitié interne", "moitié externe", "< 50%", "> 50%", "≥ 50%"],
            exemple_formulation="Invasion myométriale de la moitié interne (< 50%) : 5 mm sur 18 mm d'épaisseur totale",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension au col",
            description="Extension tumorale au col utérin (stroma cervical envahi ou non)",
            section="microscopie",
            mots_cles_detection=["col", "cervical", "extension cervicale", "stroma cervical", "isthme"],
            exemple_formulation="Extension au col utérin : absente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles lymphovasculaires",
            description="Présence, caractère focal ou extensif des emboles lymphovasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "lymphovasculaires", "LVSI", "vasculaires", "focal", "extensif", "substantiel"],
            exemple_formulation="Emboles lymphovasculaires : focaux",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "résection", "recoupe", "séreuse"],
            exemple_formulation="Marges chirurgicales : saines. Séreuse utérine intacte.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "sentinelle", "pelvien", "lombo-aortique"],
            exemple_formulation="Ganglions sentinelles : 0 envahi sur 4 examinés (pelvien bilatéral)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut MMR/MSI",
            description="Expression des protéines MMR par IHC : MLH1, MSH2, MSH6, PMS2",
            section="ihc",
            mots_cles_detection=["MMR", "MSI", "MLH1", "MSH2", "MSH6", "PMS2", "microsatellite", "dMMR", "pMMR", "Lynch"],
            exemple_formulation="MMR : expression conservée de MLH1, MSH2, MSH6 et PMS2 (pMMR)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="p53 (IHC)",
            description="Expression de p53 en IHC (wild-type vs muté : surexpression diffuse intense ou absence totale d'expression)",
            section="ihc",
            mots_cles_detection=["p53", "TP53", "wild-type", "muté", "surexpression", "aberrant"],
            exemple_formulation="p53 : expression de type wild-type (hétérogène, faible intensité)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Récepteurs hormonaux (RE, RP)",
            description="Expression des récepteurs aux estrogènes et à la progestérone",
            section="ihc",
            mots_cles_detection=["RE", "RP", "récepteurs estrogènes", "récepteurs progestérone", "récepteurs hormonaux"],
            exemple_formulation="RE : 90% (intensité forte). RP : 80% (intensité forte).",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM / FIGO",
            description="Classification pTNM et stade FIGO 2023",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "FIGO", "stade", "TNM"],
            exemple_formulation="pT1a pN0(sn) - FIGO IA (AJCC 8e édition / FIGO 2023)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 11. OVAIRE
# ---------------------------------------------------------------------------
TEMPLATE_OVAIRE: TemplateOrgane = TemplateOrgane(
    organe="ovaire",
    nom_affichage="Ovaire",
    sous_types=["biopsie", "annexectomie", "ovariectomie", "hystérectomie avec annexectomie bilatérale", "chirurgie de réduction tumorale"],
    mots_cles_detection=["ovaire", "ovarien", "ovarienne", "annexe", "annexectomie", "trompe", "tubaire", "péritoine", "ascite", "carcinose péritonéale", "omentectomie", "épiploon"],
    marqueurs_ihc=["WT1", "PAX8", "p53", "RE", "RP", "CK7", "napsin A", "HNF1-beta", "calrétinine", "inhibine", "CD10", "Ki67"],
    systeme_staging="TNM 8e édition / FIGO 2014 - Ovaire",
    template_macroscopie=(
        "Pièce d'annexectomie [droite/gauche] : ovaire mesurant [X] x [X] x [X] cm, "
        "de surface [lisse/irrégulière/végétante]. "
        "À la coupe : [tumeur solide/kystique/mixte] de [X] cm. "
        "Capsule ovarienne : [intacte/rompue]. "
        "Végétations exophytiques : [présentes/absentes]. "
        "Contenu kystique : [séreux/mucineux/hémorragique/nécrotique]. "
        "Trompe : [X] cm, [normale/épaissie/envahie]. "
        "Épiploon : [X] x [X] cm, [normal/nodulaire]. "
        "Cytologie du liquide d'ascite : [effectuée]."
    ),
    template_conclusion=(
        "Carcinome [séreux de haut grade / séreux de bas grade / endométrioïde / à cellules claires / mucineux] de l'ovaire.\n"
        "- Grade : [bas grade / haut grade]\n"
        "- Taille tumorale : [X] cm\n"
        "- Rupture capsulaire : [oui (peropératoire/préopératoire) / non]\n"
        "- Végétations exophytiques : [oui/non]\n"
        "- Cytologie du liquide d'ascite : [positive/négative]\n"
        "- Extension péritonéale : [sites]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- pTNM / FIGO : pT[X] pN[X] / FIGO [stade]\n"
        "- BRCA : [à rechercher si séreux haut grade]"
    ),
    notes_specifiques=(
        "La majorité des carcinomes séreux de haut grade naissent de la trompe (STIC : serous tubal intraepithelial carcinoma). "
        "Examen minutieux de la trompe par protocole SEE-FIM. "
        "La rupture capsulaire modifie le stade (IC vs IA). "
        "Statut BRCA1/BRCA2 obligatoire pour carcinome séreux de haut grade (implications thérapeutiques : inhibiteurs de PARP). "
        "Score de chimiosensibilité (CRS) si chimiothérapie néoadjuvante."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS 2020",
            section="microscopie",
            mots_cles_detection=["séreux", "endométrioïde", "cellules claires", "mucineux", "carcinome ovarien", "Brenner", "type histologique"],
            exemple_formulation="Carcinome séreux de haut grade de l'ovaire",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade",
            description="Grade tumoral (bas grade / haut grade pour séreux ; grade FIGO pour endométrioïde)",
            section="microscopie",
            mots_cles_detection=["grade", "haut grade", "bas grade", "grade 1", "grade 2", "grade 3"],
            exemple_formulation="Carcinome séreux de haut grade",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 8 cm de grand axe",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Rupture capsulaire",
            description="Présence ou absence de rupture de la capsule ovarienne, et circonstances (peropératoire vs préopératoire)",
            section="macroscopie",
            mots_cles_detection=["rupture capsulaire", "capsule", "rompue", "intacte", "effraction", "rupture"],
            exemple_formulation="Capsule ovarienne : intacte, pas de rupture",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Végétations exophytiques",
            description="Présence ou absence de végétations à la surface de l'ovaire",
            section="macroscopie",
            mots_cles_detection=["végétation", "exophytique", "surface ovarienne", "papillaire", "implant"],
            exemple_formulation="Végétations exophytiques à la surface de l'ovaire : absentes",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Cytologie du liquide d'ascite",
            description="Résultat de la cytologie du liquide d'ascite ou de lavage péritonéal",
            section="microscopie",
            mots_cles_detection=["cytologie", "ascite", "lavage péritonéal", "liquide", "cellules tumorales"],
            exemple_formulation="Cytologie du liquide d'ascite : positive, présence de cellules carcinomateuses",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension péritonéale",
            description="Sites d'extension péritonéale",
            section="microscopie",
            mots_cles_detection=["péritonéal", "péritonéale", "carcinose", "épiploon", "omentum", "implant", "diaphragme", "péritoine"],
            exemple_formulation="Extension péritonéale : implants sur l'épiploon et le péritoine pelvien",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "pelvien", "lombo-aortique"],
            exemple_formulation="Ganglions : 0 envahi sur 12 examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM / FIGO",
            description="Classification pTNM et stade FIGO",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "FIGO", "stade", "TNM"],
            exemple_formulation="pT3a pN1 - FIGO IIIA (AJCC 8e édition / FIGO 2014)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut BRCA",
            description="Statut BRCA1/BRCA2 (obligatoire pour carcinome séreux de haut grade)",
            section="biologie_moleculaire",
            mots_cles_detection=["BRCA", "BRCA1", "BRCA2", "mutation germinale", "mutation somatique", "HRD", "déficit de recombinaison homologue"],
            exemple_formulation="Recherche BRCA : mutation germinale BRCA1 identifiée",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 12. MÉLANOME (Skin melanoma)
# ---------------------------------------------------------------------------
TEMPLATE_MELANOME: TemplateOrgane = TemplateOrgane(
    organe="melanome",
    nom_affichage="Mélanome",
    sous_types=["biopsie-exérèse", "reprise de marges", "ganglion sentinelle", "curage ganglionnaire"],
    mots_cles_detection=["mélanome", "melanome", "naevus", "nævus", "lésion mélanocytaire", "Breslow", "Clark", "pigmenté", "mélanocyte", "lentigo maligna", "acral"],
    marqueurs_ihc=["SOX10", "Melan-A", "HMB45", "S100", "Ki67", "PRAME", "p16"],
    systeme_staging="TNM 8e édition - Mélanome cutané (AJCC/UICC)",
    template_macroscopie=(
        "Exérèse cutanée [orientée/non orientée] mesurant [X] x [X] x [X] cm. "
        "Lésion pigmentée [asymétrique/symétrique] de [X] x [X] mm, "
        "de couleur [brun/noir/polychrome], [plane/nodulaire/ulcérée]. "
        "Marges macroscopiques : [X] mm. "
        "Inclusion en totalité."
    ),
    template_conclusion=(
        "Mélanome [SSM/nodulaire/lentigo maligna/acral lentigineux/autre].\n"
        "- Indice de Breslow : [X] mm\n"
        "- Niveau de Clark : [I/II/III/IV/V]\n"
        "- Ulcération : [présente/absente]\n"
        "- Index mitotique : [X] mitose(s)/mm²\n"
        "- Emboles lymphovasculaires : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Régression : [présente (précoce/tardive)/absente]\n"
        "- Microsatellitose : [présente/absente]\n"
        "- Marges latérales : [X] mm (saines/envahies)\n"
        "- Marge profonde : [X] mm (saine/envahie)\n"
        "- Ganglion sentinelle : [positif/négatif] (si applicable)\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "L'indice de Breslow est le facteur pronostique le plus important. "
        "Ulcération et index mitotique modifient le stade pT. "
        "La microsatellitose (agrégats tumoraux dans le derme réticulaire ou l'hypoderme séparés de la tumeur principale) modifie le stade pN. "
        "BRAF V600E muté dans ~50% des mélanomes cutanés. "
        "Panel moléculaire : BRAF, NRAS, c-KIT (muqueux et acral)."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Sous-type de mélanome (SSM, nodulaire, lentigo maligna, acral lentigineux, etc.)",
            section="microscopie",
            mots_cles_detection=["SSM", "à extension superficielle", "nodulaire", "lentigo maligna", "acral", "desmoplastique", "type histologique"],
            exemple_formulation="Mélanome de type SSM (superficial spreading melanoma)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Indice de Breslow",
            description="Épaisseur tumorale maximale en mm (de la couche granuleuse au point le plus profond)",
            section="microscopie",
            mots_cles_detection=["Breslow", "épaisseur", "indice de Breslow", "mm"],
            exemple_formulation="Indice de Breslow : 1.2 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Niveau de Clark",
            description="Niveau anatomique d'invasion (I à V)",
            section="microscopie",
            mots_cles_detection=["Clark", "niveau", "niveau de Clark", "épiderme", "derme papillaire", "derme réticulaire", "hypoderme"],
            exemple_formulation="Niveau de Clark : III (derme papillaire expansif)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ulcération",
            description="Présence ou absence d'ulcération de l'épiderme en regard de la tumeur",
            section="microscopie",
            mots_cles_detection=["ulcération", "ulcéré", "ulcère", "épiderme intact"],
            exemple_formulation="Ulcération : absente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Index mitotique",
            description="Nombre de mitoses par mm² dans la composante dermique invasive",
            section="microscopie",
            mots_cles_detection=["mitose", "mitotique", "index mitotique", "mitoses/mm²", "/mm²"],
            exemple_formulation="Index mitotique : 3 mitoses/mm²",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles lymphovasculaires",
            description="Présence ou absence d'emboles lymphovasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "lymphovasculaires", "vasculaires"],
            exemple_formulation="Emboles lymphovasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Régression",
            description="Présence, type (précoce/tardive) et étendue de la régression tumorale",
            section="microscopie",
            mots_cles_detection=["régression", "fibrose", "infiltrat lymphocytaire", "régression partielle", "régression complète"],
            exemple_formulation="Régression : présente, de type tardif (fibrose), < 75% de la surface tumorale",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Microsatellitose",
            description="Présence ou absence de microsatellites tumoraux",
            section="microscopie",
            mots_cles_detection=["microsatellitose", "microsatellite", "satellite", "nid tumoral à distance"],
            exemple_formulation="Microsatellitose : absente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges latérales et profondes",
            description="Distance des marges latérales et profondes en mm",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "latérale", "profonde", "périphérique", "distance"],
            exemple_formulation="Marge latérale la plus proche : 4 mm (saine). Marge profonde : 6 mm (saine).",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglion sentinelle",
            description="Résultat du ganglion sentinelle si applicable",
            section="microscopie",
            mots_cles_detection=["ganglion sentinelle", "sentinelle", "GS", "métastase", "micrométastase"],
            exemple_formulation="Ganglion sentinelle inguinal gauche : négatif (0/1)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT1b pN0(sn) (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Biologie moléculaire (BRAF, NRAS, c-KIT)",
            description="Statut mutationnel BRAF V600E, NRAS, c-KIT",
            section="biologie_moleculaire",
            mots_cles_detection=["BRAF", "V600E", "NRAS", "c-KIT", "KIT", "mutation", "sauvage"],
            exemple_formulation="BRAF V600E : muté. NRAS : sauvage.",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 13. FOIE (Liver)
# ---------------------------------------------------------------------------
TEMPLATE_FOIE: TemplateOrgane = TemplateOrgane(
    organe="foie",
    nom_affichage="Foie",
    sous_types=["biopsie hépatique", "hépatectomie partielle", "segmentectomie", "lobectomie hépatique", "transplantation hépatique"],
    mots_cles_detection=["foie", "hépatique", "hépatocellulaire", "CHC", "cholangiocarcinome", "hépatectomie", "segment hépatique", "lobectomie", "cirrhose", "fibrose hépatique", "METAVIR"],
    marqueurs_ihc=["Glypican-3", "HSP70", "glutamine synthétase", "arginase-1", "HepPar-1", "CK7", "CK19", "CD34", "AFP", "beta-caténine"],
    systeme_staging="TNM 8e édition - Foie (AJCC/UICC)",
    template_macroscopie=(
        "Pièce d'hépatectomie [segmentectomie/lobectomie] pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Tumeur [unique/multiple] de [X] cm, [encapsulée/mal limitée], "
        "de couleur [verdâtre/jaunâtre/blanchâtre/hétérogène]. "
        "Nombre de nodules : [X]. "
        "Distance à la tranche de section : [X] mm. "
        "Invasion vasculaire macroscopique : [présente/absente]. "
        "Parenchyme hépatique non tumoral : [normal/stéatose/fibrose/cirrhose]."
    ),
    template_conclusion=(
        "Carcinome hépatocellulaire / Cholangiocarcinome intrahépatique / [autre].\n"
        "- Grade de différenciation : [bien/moyennement/peu différencié]\n"
        "- Taille tumorale : [X] cm\n"
        "- Nombre de nodules : [X]\n"
        "- Invasion vasculaire macroscopique : [présente/absente]\n"
        "- Invasion vasculaire microscopique : [présente/absente]\n"
        "- Emboles portaux : [présents/absents]\n"
        "- Capsule tumorale : [complète/incomplète/absente]\n"
        "- Marges chirurgicales : [saines, distance X mm / envahies]\n"
        "- Foie non tumoral : [score METAVIR A[0-3] F[0-4]]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Pour le CHC : la triade diagnostique IHC est Glypican-3, HSP70, glutamine synthétase (2/3 positifs = CHC). "
        "L'invasion vasculaire (macroscopique et microscopique) est le facteur pronostique majeur du CHC. "
        "Le foie non tumoral doit être évalué avec le score METAVIR (activité et fibrose). "
        "Pour le cholangiocarcinome : profil IHC différent (CK7+, CK19+, HepPar1-, Arginase-1-). "
        "Alpha-fœtoprotéine sérique à corréler."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique (CHC, cholangiocarcinome intrahépatique, carcinome hépatocellulaire-cholangiocarcinome combiné)",
            section="microscopie",
            mots_cles_detection=["hépatocellulaire", "CHC", "cholangiocarcinome", "carcinome", "HCC", "combiné", "mixte", "type histologique"],
            exemple_formulation="Carcinome hépatocellulaire (CHC)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade de différenciation",
            description="Grade de différenciation (bien, moyennement, peu différencié)",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "grade", "Edmondson", "Steiner"],
            exemple_formulation="CHC moyennement différencié (Edmondson-Steiner grade II)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur / du nodule le plus volumineux",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Nodule tumoral principal : 35 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Nombre de nodules",
            description="Nombre de nodules tumoraux",
            section="macroscopie",
            mots_cles_detection=["nodule", "nodules", "nombre", "unique", "multiple", "multinodulaire", "satellite"],
            exemple_formulation="Tumeur unique, pas de nodule satellite",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion vasculaire macroscopique",
            description="Présence ou absence de thrombus tumoral macroscopique (veine porte, veines hépatiques)",
            section="macroscopie",
            mots_cles_detection=["invasion vasculaire macroscopique", "thrombus", "veine porte", "veine hépatique", "macroscopique"],
            exemple_formulation="Invasion vasculaire macroscopique : absente (pas de thrombus portal)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion vasculaire microscopique",
            description="Présence ou absence d'emboles tumoraux vasculaires microscopiques",
            section="microscopie",
            mots_cles_detection=["invasion vasculaire microscopique", "emboles", "microscopique", "microvasculaire"],
            exemple_formulation="Invasion vasculaire microscopique : présente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles portaux",
            description="Présence ou absence d'emboles dans les branches portales",
            section="microscopie",
            mots_cles_detection=["emboles portaux", "portal", "porte", "branche portale"],
            exemple_formulation="Emboles portaux : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Capsule tumorale",
            description="Présence et statut de la capsule tumorale",
            section="microscopie",
            mots_cles_detection=["capsule", "encapsulé", "capsule tumorale", "complète", "incomplète"],
            exemple_formulation="Capsule tumorale : complète, non franchie",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection et distance",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "tranche de section", "résection", "distance"],
            exemple_formulation="Marge de résection (tranche de section) : saine, distance minimale 10 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Foie non tumoral (METAVIR)",
            description="Évaluation du parenchyme hépatique non tumoral avec score METAVIR (Activité et Fibrose)",
            section="microscopie",
            mots_cles_detection=["METAVIR", "fibrose", "cirrhose", "stéatose", "foie non tumoral", "activité", "F0", "F1", "F2", "F3", "F4"],
            exemple_formulation="Foie non tumoral : cirrhose (METAVIR A1 F4), stéatose macrovésiculaire 20%",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT1b pNx (AJCC 8e édition)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="IHC diagnostique (CHC)",
            description="Triade immunohistochimique pour CHC : Glypican-3, HSP70, glutamine synthétase",
            section="ihc",
            mots_cles_detection=["Glypican-3", "HSP70", "glutamine synthétase", "Glypican", "arginase", "HepPar"],
            exemple_formulation="Glypican-3 : positif. HSP70 : positif. Glutamine synthétase : positif (3/3).",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 14. PANCRÉAS
# ---------------------------------------------------------------------------
TEMPLATE_PANCREAS: TemplateOrgane = TemplateOrgane(
    organe="pancreas",
    nom_affichage="Pancréas",
    sous_types=["biopsie", "échoendoscopie avec ponction", "duodéno-pancréatectomie céphalique (DPC)", "splénopancréatectomie gauche", "pancréatectomie totale", "énucléation"],
    mots_cles_detection=["pancréas", "pancréatique", "duodéno-pancréatectomie", "DPC", "Whipple", "canal de Wirsung", "ampoule de Vater", "cholédoque", "splénopancréatectomie", "tumeur pancréatique"],
    marqueurs_ihc=["CK7", "CK19", "CK20", "MUC1", "MUC2", "MUC5AC", "CDX2", "chromogranine", "synaptophysine", "Ki67", "beta-caténine"],
    systeme_staging="TNM 8e édition - Pancréas exocrine (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de duodéno-pancréatectomie céphalique mesurant [X] cm. "
        "Tumeur [blanc grisâtre/ferme/mal limitée] de [X] x [X] cm au niveau de [tête/corps/queue/processus unciné]. "
        "Distance au canal cholédoque : [X] mm. "
        "Distance à la marge rétropéritonéale (postérieure) : [X] mm. "
        "Marge de section pancréatique (corps) : [X] mm. "
        "Sténose du canal de Wirsung : [oui/non]. "
        "Ganglions identifiés : [X]."
    ),
    template_conclusion=(
        "Adénocarcinome canalaire pancréatique / [autre type].\n"
        "- Grade de différenciation : [bien/moyennement/peu différencié]\n"
        "- Taille tumorale : [X] mm\n"
        "- Extension aux organes adjacents : [duodénum/cholédoque/veine porte/artère mésentérique supérieure]\n"
        "- Marges chirurgicales :\n"
        "  - Marge postérieure (rétropéritonéale) : [X] mm\n"
        "  - Marge de section pancréatique : [X] mm\n"
        "  - Marge du canal cholédoque : [saine/envahie]\n"
        "  - Marge antérieure : [X] mm\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- Emboles vasculaires : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "L'adénocarcinome canalaire pancréatique présente des engainements périnerveux dans >90% des cas (ne pas les oublier). "
        "La marge rétropéritonéale (postérieure, autour du sillon de l'artère mésentérique supérieure) est la marge critique. "
        "Positive si ≤ 1 mm. "
        "Encrage des marges en 4 couleurs selon le protocole de Leeds."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS",
            section="microscopie",
            mots_cles_detection=["adénocarcinome canalaire", "mucineux", "neuroendocrine", "acineux", "TIPMP", "cystadénocarcinome", "type histologique"],
            exemple_formulation="Adénocarcinome canalaire pancréatique",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade de différenciation",
            description="Grade de différenciation histologique",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "grade", "bien", "moyennement", "peu"],
            exemple_formulation="Adénocarcinome canalaire moyennement différencié",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 28 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension aux organes adjacents",
            description="Extension tumorale aux structures adjacentes (duodénum, cholédoque, vaisseaux, etc.)",
            section="microscopie",
            mots_cles_detection=["extension", "duodénum", "cholédoque", "veine porte", "artère mésentérique", "estomac", "rate", "surrénale", "adjacent"],
            exemple_formulation="Extension au duodénum et à la paroi du cholédoque. Veine porte : non envahie.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut de toutes les marges : postérieure (rétropéritonéale), section pancréatique, canal cholédoque, antérieure",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "postérieure", "rétropéritonéale", "section pancréatique", "cholédoque", "antérieure", "résection", "R0", "R1"],
            exemple_formulation="Marge postérieure (rétropéritonéale) : 2 mm (saine). Marge de section pancréatique : saine. Marge cholédoque : saine.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "examiné"],
            exemple_formulation="Ganglions : 3 envahis sur 18 examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles vasculaires",
            description="Présence ou absence d'emboles vasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux (quasi-constants dans l'adénocarcinome canalaire)",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse", "péri-nerveux"],
            exemple_formulation="Engainements périnerveux : présents, nombreux",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2 pN1 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 15. ŒSOPHAGE
# ---------------------------------------------------------------------------
TEMPLATE_OESOPHAGE: TemplateOrgane = TemplateOrgane(
    organe="oesophage",
    nom_affichage="Œsophage",
    sous_types=["biopsie", "mucosectomie", "dissection sous-muqueuse", "œsophagectomie", "résection selon Lewis-Santy", "résection selon Ivor-Lewis"],
    mots_cles_detection=["oesophage", "œsophage", "œsophagien", "œsophagienne", "œsophagectomie", "Barrett", "endobrachyoesophage", "EBO", "jonction oeso-gastrique", "cardia", "bas œsophage"],
    marqueurs_ihc=["CK7", "CK20", "CDX2", "p63", "CK5/6", "p40", "PD-L1", "HER2", "MLH1", "MSH2", "MSH6", "PMS2"],
    systeme_staging="TNM 8e édition - Œsophage (AJCC/UICC)",
    template_macroscopie=(
        "Pièce d'œsophagectomie mesurant [X] cm de longueur. "
        "Lésion tumorale [ulcérée/bourgeonnante/sténosante] de [X] x [X] cm "
        "siégeant à [X] cm de la marge proximale et [X] cm de la marge distale. "
        "Marge de résection circonférentielle : [X] mm. "
        "Muqueuse de Barrett associée : [présente/absente] sur [X] cm. "
        "Ganglions identifiés : [X]."
    ),
    template_conclusion=(
        "Carcinome [épidermoïde / adénocarcinome] de l'œsophage.\n"
        "- Grade de différenciation : [bien/moyennement/peu différencié]\n"
        "- Niveau d'infiltration : [muqueuse/sous-muqueuse/musculeuse/adventice/structures adjacentes]\n"
        "- Barrett associé : [oui/non]\n"
        "- Marge proximale : [X] mm\n"
        "- Marge distale : [X] mm\n"
        "- Marge circonférentielle : [X] mm\n"
        "- Emboles : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- Score de régression tumorale (TRG) : [si traitement néoadjuvant]\n"
        "- PD-L1 (CPS) : [X]\n"
        "- HER2 : [score] (si adénocarcinome)\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "La stadification TNM 8e édition distingue carcinome épidermoïde et adénocarcinome (grilles pTNM différentes). "
        "Pour les adénocarcinomes : rechercher un Barrett (endobrachyœsophage) associé. "
        "La marge de résection circonférentielle est le facteur pronostique majeur : positive si ≤ 1 mm. "
        "PD-L1 (CPS) et HER2 systématiques si maladie avancée. "
        "Score de régression tumorale (TRG Mandard) si chimiothérapie ou radio-chimiothérapie néoadjuvante."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique (carcinome épidermoïde vs adénocarcinome)",
            section="microscopie",
            mots_cles_detection=["carcinome épidermoïde", "adénocarcinome", "neuroendocrine", "type histologique", "indifférencié"],
            exemple_formulation="Adénocarcinome de l'œsophage distal sur endobrachyœsophage",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade de différenciation",
            description="Grade de différenciation histologique",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "grade", "bien", "moyennement", "peu"],
            exemple_formulation="Adénocarcinome moyennement différencié",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Niveau d'infiltration",
            description="Profondeur d'invasion dans la paroi œsophagienne",
            section="microscopie",
            mots_cles_detection=["infiltration", "invasion", "muqueuse", "sous-muqueuse", "musculeuse", "adventice", "pT"],
            exemple_formulation="Infiltration de l'adventice (pT3)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Barrett associé",
            description="Présence ou absence d'un endobrachyœsophage (muqueuse de Barrett) associé",
            section="microscopie",
            mots_cles_detection=["Barrett", "endobrachyœsophage", "EBO", "métaplasie intestinale", "métaplasie glandulaire"],
            exemple_formulation="Endobrachyœsophage (Barrett) associé : présent sur 4 cm, avec dysplasie de bas grade en périphérie",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge proximale",
            description="Distance de la tumeur à la marge de résection proximale",
            section="macroscopie",
            mots_cles_detection=["marge proximale", "limite proximale", "recoupe proximale"],
            exemple_formulation="Marge proximale : 60 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge distale",
            description="Distance de la tumeur à la marge de résection distale",
            section="macroscopie",
            mots_cles_detection=["marge distale", "limite distale", "recoupe distale"],
            exemple_formulation="Marge distale : 30 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marge circonférentielle",
            description="Distance à la marge de résection circonférentielle (CRM)",
            section="microscopie",
            mots_cles_detection=["marge circonférentielle", "CRM", "circonférentielle", "radiale"],
            exemple_formulation="Marge de résection circonférentielle : 3 mm (négative)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "envahi", "examiné"],
            exemple_formulation="Ganglions : 2 envahis sur 15 examinés",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles",
            description="Présence ou absence d'emboles vasculaires et lymphatiques",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "lymphatiques", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires et lymphatiques : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Score de régression tumorale (TRG)",
            description="Score de régression après traitement néoadjuvant (Mandard TRG 1 à 5)",
            section="microscopie",
            mots_cles_detection=["TRG", "régression", "réponse", "néoadjuvant", "Mandard", "complète", "résiduelle"],
            exemple_formulation="TRG selon Mandard : TRG 2 (régression majeure, fibrose prédominante avec rares cellules tumorales résiduelles)",
            obligatoire=False
        ),
        ChampObligatoire(
            nom="PD-L1 (CPS)",
            description="Expression de PD-L1 en CPS (Combined Positive Score)",
            section="ihc",
            mots_cles_detection=["PD-L1", "CPS", "combined positive score", "PDL1"],
            exemple_formulation="PD-L1 (clone 22C3) : CPS = 10",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut HER2",
            description="Score HER2 en IHC (pour adénocarcinome) avec scoring gastrique",
            section="ihc",
            mots_cles_detection=["HER2", "HER-2", "FISH", "amplification", "score"],
            exemple_formulation="HER2 (scoring gastrique) : score 2+, FISH : amplifiée (ratio 2.5)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT3 pN1 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 16. ORL / TÊTE ET COU
# ---------------------------------------------------------------------------
TEMPLATE_ORL: TemplateOrgane = TemplateOrgane(
    organe="orl_tete_cou",
    nom_affichage="ORL / Tête et Cou",
    sous_types=["biopsie", "laryngectomie", "pharyngectomie", "glossectomie", "maxillectomie", "mandibulectomie", "parotidectomie", "curage ganglionnaire cervical"],
    mots_cles_detection=["ORL", "larynx", "pharynx", "oropharynx", "hypopharynx", "nasopharynx", "cavité buccale", "langue", "plancher buccal", "amygdale", "tonsille", "palais", "lèvre", "sinus", "cavité nasale", "glande salivaire", "parotide", "sous-maxillaire", "laryngectomie", "cervical"],
    marqueurs_ihc=["p16", "p63", "p40", "CK5/6", "CK7", "EMA", "S100", "SMA", "Ki67", "SOX10"],
    systeme_staging="TNM 8e édition - Tête et Cou (AJCC/UICC)",
    template_macroscopie=(
        "Pièce de [type d'exérèse] orientée mesurant [X] x [X] x [X] cm. "
        "Lésion tumorale [ulcérée/bourgeonnante/infiltrante] de [X] x [X] cm "
        "siégeant au niveau de [site anatomique précis]. "
        "Distance aux marges chirurgicales : [X] mm. "
        "Extension macroscopique aux structures adjacentes : [détail]. "
        "Ganglions identifiés dans le curage cervical : [X] ganglion(s) par niveau."
    ),
    template_conclusion=(
        "Carcinome épidermoïde / [autre type] du/de la [site anatomique].\n"
        "- Grade de différenciation : [bien/moyennement/peu différencié]\n"
        "- Taille tumorale : [X] mm\n"
        "- Extension aux structures adjacentes : [détail]\n"
        "- Marges chirurgicales : [saines/envahies, distance X mm]\n"
        "- Emboles : [présents/absents]\n"
        "- Engainements périnerveux : [présents/absents]\n"
        "- Ganglions : [X] envahi(s) sur [X] examiné(s)\n"
        "- Effraction capsulaire ganglionnaire : [oui/non]\n"
        "- p16/HPV (si oropharynx) : [positif/négatif]\n"
        "- pTNM : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "La stadification TNM 8e édition pour l'oropharynx distingue les carcinomes HPV+ et HPV- (grilles pTNM séparées). "
        "p16 en IHC est le surrogat du statut HPV pour l'oropharynx (marquage diffus nucléaire et cytoplasmique ≥70%). "
        "L'effraction capsulaire ganglionnaire (ENE) modifie le stade pN pour les carcinomes HPV-. "
        "Les engainements périnerveux sont fréquents et doivent être systématiquement recherchés."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Site anatomique précis",
            description="Localisation anatomique exacte de la tumeur",
            section="macroscopie",
            mots_cles_detection=["site", "localisation", "siège", "larynx", "pharynx", "oropharynx", "cavité buccale", "langue", "amygdale", "plancher", "palais"],
            exemple_formulation="Carcinome de l'amygdale palatine gauche (oropharynx)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS",
            section="microscopie",
            mots_cles_detection=["carcinome épidermoïde", "adénocarcinome", "carcinome adénoïde kystique", "carcinome mucoépidermoïde", "carcinome indifférencié", "type histologique"],
            exemple_formulation="Carcinome épidermoïde non kératinisant",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade de différenciation",
            description="Grade de différenciation histologique",
            section="microscopie",
            mots_cles_detection=["différenciation", "différencié", "grade", "bien", "moyennement", "peu", "kératinisant"],
            exemple_formulation="Carcinome épidermoïde moyennement différencié, non kératinisant",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 30 mm de grand axe",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension aux structures adjacentes",
            description="Extension tumorale aux structures anatomiques voisines",
            section="microscopie",
            mots_cles_detection=["extension", "envahissement", "adjacent", "os", "cartilage", "muscle", "peau", "base de langue", "épiglotte"],
            exemple_formulation="Extension à la base de langue et au palais mou homolatéral",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut et distance des marges de résection",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "résection", "recoupe", "berge", "distance", "limite"],
            exemple_formulation="Marges chirurgicales : marge muqueuse profonde 5 mm, marges muqueuses latérales ≥ 10 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles",
            description="Présence ou absence d'emboles vasculaires et lymphatiques",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "lymphatiques"],
            exemple_formulation="Emboles vasculaires et lymphatiques : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Engainements périnerveux",
            description="Présence ou absence d'engainements périnerveux",
            section="microscopie",
            mots_cles_detection=["engainements périnerveux", "périnerveux", "invasion nerveuse"],
            exemple_formulation="Engainements périnerveux : présents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Ganglions examinés et envahis",
            description="Nombre de ganglions examinés et envahis par niveau de curage",
            section="microscopie",
            mots_cles_detection=["ganglion", "ganglions", "curage", "cervical", "envahi", "niveau", "IIA", "IIB", "III", "IV", "V"],
            exemple_formulation="Curage cervical gauche : 2 envahis sur 28 examinés (niveau II : 2/8, niveau III : 0/10, niveau IV : 0/10)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Effraction capsulaire ganglionnaire",
            description="Présence ou absence d'extension extranodale (effraction capsulaire) en cas de ganglion envahi",
            section="microscopie",
            mots_cles_detection=["effraction capsulaire", "rupture capsulaire", "extranodal", "extension extranodale", "ENE", "extracapsulaire"],
            exemple_formulation="Effraction capsulaire : présente (ENE+) sur 1 ganglion",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="p16/HPV (oropharynx)",
            description="Expression de p16 en IHC comme surrogat du statut HPV (obligatoire pour l'oropharynx)",
            section="ihc",
            mots_cles_detection=["p16", "HPV", "papillomavirus", "positif", "négatif", "en bloc"],
            exemple_formulation="p16 : positif en bloc (marquage diffus nucléaire et cytoplasmique > 70%), surrogat HPV+",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition (grille spécifique HPV+ ou HPV- pour oropharynx)",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2 pN1 (AJCC 8e édition, grille oropharynx HPV+)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 17. TESTICULE
# ---------------------------------------------------------------------------
TEMPLATE_TESTICULE: TemplateOrgane = TemplateOrgane(
    organe="testicule",
    nom_affichage="Testicule",
    sous_types=["orchidectomie", "biopsie testiculaire"],
    mots_cles_detection=["testicule", "testiculaire", "orchidectomie", "séminome", "non séminomateux", "cordon spermatique", "albuginée", "rete testis", "tumeur germinale"],
    marqueurs_ihc=["OCT4", "SALL4", "PLAP", "CD117", "D2-40", "AFP", "hCG", "beta-hCG", "CD30", "glypican-3", "SOX2", "SOX17"],
    systeme_staging="TNM 8e édition - Testicule (AJCC/UICC)",
    template_macroscopie=(
        "Pièce d'orchidectomie [droite/gauche] par voie inguinale pesant [X] g, mesurant [X] x [X] x [X] cm. "
        "Cordon spermatique mesurant [X] cm. "
        "Tumeur de [X] cm, [homogène/hétérogène], [blanc/grisâtre/nécrotique/hémorragique/kystique]. "
        "Albuginée : [intacte/infiltrée]. "
        "Parenchyme testiculaire non tumoral : [atrophique/normal]. "
        "Épididyme : [normal/envahi]."
    ),
    template_conclusion=(
        "Tumeur germinale [séminomateuse / non séminomateuse / mixte] du testicule [droit/gauche].\n"
        "- Type histologique : [séminome / carcinome embryonnaire / tumeur vitelline / choriocarcinome / tératome / mixte]\n"
        "- Composantes si mixte : [X]% séminome, [X]% carcinome embryonnaire, [X]% tératome, etc.\n"
        "- Taille tumorale : [X] cm\n"
        "- Invasion du rete testis : [oui/non]\n"
        "- Invasion vasculaire/lymphatique : [présente/absente]\n"
        "- Extension : albuginée [intacte/franchie], épididyme [sain/envahi], cordon spermatique [sain/envahi]\n"
        "- Marqueurs sériques : AFP [X], hCG [X], LDH [X]\n"
        "- pTNM : pT[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Orchidectomie TOUJOURS par voie inguinale (jamais scrotale). "
        "Le cordon spermatique doit être ligaturé au premier temps opératoire. "
        "Les marqueurs sériques (AFP, hCG, LDH) font partie intégrante du staging (catégorie S). "
        "Le séminome pur ne sécrète PAS d'AFP (si AFP élevé = composante non séminomateuse). "
        "GCNIS (Germ Cell Neoplasia In Situ) à rechercher dans le parenchyme non tumoral."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique selon la classification OMS (séminome, carcinome embryonnaire, tumeur vitelline, choriocarcinome, tératome, mixte)",
            section="microscopie",
            mots_cles_detection=["séminome", "carcinome embryonnaire", "tumeur vitelline", "choriocarcinome", "tératome", "germinale", "mixte", "type histologique"],
            exemple_formulation="Tumeur germinale mixte : séminome (60%) et carcinome embryonnaire (40%)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Composantes si tumeur mixte",
            description="Pourcentage de chaque composante en cas de tumeur germinale mixte",
            section="microscopie",
            mots_cles_detection=["composante", "pourcentage", "mixte", "%", "séminome", "embryonnaire", "vitellin", "tératome"],
            exemple_formulation="Composantes : séminome 60%, carcinome embryonnaire 30%, tératome mature 10%",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 4.5 cm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion du rete testis",
            description="Présence ou absence d'invasion du rete testis",
            section="microscopie",
            mots_cles_detection=["rete testis", "rete", "hile testiculaire"],
            exemple_formulation="Invasion du rete testis : présente (invasion pagetoïde)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion vasculaire/lymphatique",
            description="Présence ou absence d'emboles vasculaires ou lymphatiques",
            section="microscopie",
            mots_cles_detection=["invasion vasculaire", "emboles", "lymphatique", "vasculaire", "LVI"],
            exemple_formulation="Invasion vasculaire/lymphatique : présente",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Extension locale",
            description="Extension à l'albuginée, l'épididyme, le cordon spermatique, le scrotum",
            section="microscopie",
            mots_cles_detection=["albuginée", "épididyme", "cordon spermatique", "vaginale", "scrotum", "extension"],
            exemple_formulation="Albuginée : infiltrée mais non franchie. Épididyme : non envahi. Cordon spermatique : marge de section saine.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marqueurs sériques (AFP, hCG, LDH)",
            description="Taux des marqueurs sériques (à corréler avec les données cliniques)",
            section="conclusion",
            mots_cles_detection=["AFP", "alpha-foetoprotéine", "hCG", "beta-hCG", "LDH", "marqueur sérique"],
            exemple_formulation="Marqueurs sériques pré-opératoires : AFP 250 ng/mL (élevé), hCG 5 UI/L (normal), LDH 180 UI/L (normal)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 18. LYMPHOME
# ---------------------------------------------------------------------------
TEMPLATE_LYMPHOME: TemplateOrgane = TemplateOrgane(
    organe="lymphome",
    nom_affichage="Lymphome",
    sous_types=["biopsie ganglionnaire", "biopsie médullaire", "biopsie tissulaire", "splénectomie"],
    mots_cles_detection=["lymphome", "lymphoprolifératif", "Hodgkin", "non hodgkinien", "DLBCL", "folliculaire", "manteau", "marginal", "Burkitt", "lymphoblastique", "Reed-Sternberg", "lymphadénopathie", "ganglion", "splénomégalie"],
    marqueurs_ihc=["CD20", "CD3", "CD5", "CD10", "CD15", "CD23", "CD30", "CD79a", "BCL2", "BCL6", "MUM1", "Ki67", "cycline D1", "SOX11", "TdT", "ALK", "CD138", "kappa", "lambda", "EBV-LMP1", "EBER"],
    systeme_staging="Ann Arbor / Lugano",
    template_macroscopie=(
        "Biopsie ganglionnaire [site] mesurant [X] x [X] x [X] cm. "
        "Ganglion [homogène/hétérogène], de couleur [blanchâtre/grisâtre]. "
        "Architecture ganglionnaire [effacée/partiellement conservée]. "
        "Appositions réalisées. "
        "Prélèvement en frais pour congélation et cytogénétique."
    ),
    template_conclusion=(
        "Lymphome [type selon classification OMS 2022].\n"
        "- Immunophénotype : [détail des marqueurs positifs et négatifs]\n"
        "- Index de prolifération Ki67 : [X]%\n"
        "- Profil GCB vs non-GCB (si DLBCL) : [GCB/non-GCB] (algorithme de Hans)\n"
        "- Score IPI (si DLBCL) : [à compléter avec données cliniques]\n"
        "- FISH : [MYC/BCL2/BCL6 réarrangement]\n"
        "- EBV (EBER) : [positif/négatif]\n"
        "- Stade Ann Arbor / Lugano : [à compléter avec imagerie]"
    ),
    notes_specifiques=(
        "La classification OMS 2022 des hémopathies lymphoïdes est la référence. "
        "Pour les DLBCL : algorithme de Hans (CD10, BCL6, MUM1) pour distinguer GCB vs non-GCB. "
        "FISH MYC, BCL2, BCL6 systématique pour DLBCL (recherche double-hit / triple-hit). "
        "Le diagnostic de lymphome nécessite impérativement l'immunohistochimie complète. "
        "En cas de lymphome de Hodgkin : CD15+, CD30+, CD20-/+, PAX5 faible, EBV-LMP1."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique (classification OMS)",
            description="Classification OMS 2022 des tumeurs hématopoïétiques et lymphoïdes",
            section="microscopie",
            mots_cles_detection=["DLBCL", "folliculaire", "manteau", "marginal", "Burkitt", "Hodgkin", "Reed-Sternberg", "lymphoblastique", "T", "B", "NK", "anaplasique", "lymphome", "type histologique"],
            exemple_formulation="Lymphome diffus à grandes cellules B (DLBCL), NOS",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Immunophénotype complet",
            description="Profil immunohistochimique complet avec tous les marqueurs pertinents",
            section="ihc",
            mots_cles_detection=["CD20", "CD3", "CD5", "CD10", "CD15", "CD30", "BCL2", "BCL6", "MUM1", "CD79a", "immunophénotype", "phénotype"],
            exemple_formulation="CD20+, CD10-, BCL6+, MUM1+, BCL2+, CD5-, CD3-, CD30-. Profil non-GCB (algorithme de Hans).",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Index de prolifération Ki67",
            description="Pourcentage de cellules tumorales Ki67 positives",
            section="ihc",
            mots_cles_detection=["Ki67", "Ki-67", "prolifération", "MIB-1", "index"],
            exemple_formulation="Ki67 : 80% des cellules tumorales",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Profil GCB vs non-GCB",
            description="Classification selon l'algorithme de Hans (DLBCL) : GCB ou non-GCB",
            section="ihc",
            mots_cles_detection=["GCB", "non-GCB", "ABC", "Hans", "centre germinatif", "activé", "algorithme"],
            exemple_formulation="Profil non-GCB selon l'algorithme de Hans (CD10-, BCL6+, MUM1+)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Score IPI (DLBCL)",
            description="Score IPI (International Prognostic Index) pour les DLBCL - nécessite données cliniques",
            section="conclusion",
            mots_cles_detection=["IPI", "International Prognostic Index", "pronostique", "score"],
            exemple_formulation="Score IPI : à compléter avec les données cliniques (âge, stade, LDH, PS, sites extranodaux)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="FISH (MYC, BCL2, BCL6)",
            description="Résultats de la FISH pour les réarrangements de MYC, BCL2 et BCL6 (DLBCL)",
            section="biologie_moleculaire",
            mots_cles_detection=["FISH", "MYC", "BCL2", "BCL6", "réarrangement", "translocation", "double-hit", "triple-hit"],
            exemple_formulation="FISH : absence de réarrangement de MYC, BCL2 et BCL6",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Statut EBV",
            description="Recherche du virus Epstein-Barr (EBER par hybridation in situ et/ou LMP1 par IHC)",
            section="ihc",
            mots_cles_detection=["EBV", "Epstein-Barr", "EBER", "LMP1", "virus"],
            exemple_formulation="EBV (EBER par HIS) : négatif",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Stade Ann Arbor / Lugano",
            description="Stadification selon Ann Arbor modifié / Lugano (nécessite imagerie)",
            section="conclusion",
            mots_cles_detection=["Ann Arbor", "Lugano", "stade", "I", "II", "III", "IV", "A", "B", "E"],
            exemple_formulation="Stade Ann Arbor : à compléter avec le bilan d'extension (TEP-scanner)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 19. SARCOME / TISSUS MOUS
# ---------------------------------------------------------------------------
TEMPLATE_SARCOME: TemplateOrgane = TemplateOrgane(
    organe="sarcome",
    nom_affichage="Sarcome / Tissus mous",
    sous_types=["biopsie", "exérèse chirurgicale", "résection large", "résection compartimentale"],
    mots_cles_detection=["sarcome", "tissus mous", "liposarcome", "léiomyosarcome", "rhabdomyosarcome", "synovialosarcome", "fibrosarcome", "histiocytofibrome", "DFSP", "GIST", "tumeur desmoïde", "myxofibrosarcome", "sarcomateux", "fusiforme"],
    marqueurs_ihc=["MDM2", "CDK4", "desmine", "actine muscle lisse", "SMA", "S100", "SOX10", "CD34", "CD117", "DOG1", "TLE1", "EMA", "INI1", "beta-caténine", "STAT6", "ERG", "Ki67"],
    systeme_staging="TNM 8e édition - Tissus mous (AJCC/UICC) et Grade FNCLCC",
    template_macroscopie=(
        "Pièce d'exérèse [orientée/non orientée] mesurant [X] x [X] x [X] cm, pesant [X] g. "
        "Tumeur de [X] cm, [bien limitée/mal limitée], [encapsulée/non encapsulée], "
        "de consistance [ferme/molle/gélatineuse], de couleur [blanchâtre/jaunâtre/myxoïde]. "
        "Nécrose : [présente (X%) /absente]. "
        "Profondeur : [superficiel (au-dessus du fascia) / profond (sous-fascial)]. "
        "Distance aux marges chirurgicales : [X] mm."
    ),
    template_conclusion=(
        "Sarcome [type histologique] du/de [localisation].\n"
        "- Grade FNCLCC : [1/2/3]\n"
        "  - Différenciation : score [1/2/3]\n"
        "  - Index mitotique : score [1/2/3] ([X] mitoses / 10 HPF)\n"
        "  - Nécrose : score [0/1/2] ([0% / < 50% / ≥ 50%])\n"
        "- Taille tumorale : [X] cm\n"
        "- Profondeur : [superficiel/profond]\n"
        "- Marges chirurgicales : [saines (distance X mm) / envahies]\n"
        "- Emboles : [présents/absents]\n"
        "- pTNM : pT[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "Le grade FNCLCC (Fédération Nationale des Centres de Lutte Contre le Cancer) est le système de grading de référence pour les sarcomes des tissus mous. "
        "Il repose sur 3 paramètres : différenciation, index mitotique, pourcentage de nécrose. "
        "La relecture en centre expert (réseau NETSARC) est recommandée/obligatoire. "
        "Les GIST ont un système de grading propre (critères de Miettinen/AFIP). "
        "Biologie moléculaire souvent nécessaire pour le diagnostic (FISH, RT-PCR, NGS)."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique précis selon la classification OMS 2020",
            section="microscopie",
            mots_cles_detection=["liposarcome", "léiomyosarcome", "synovialosarcome", "rhabdomyosarcome", "fibrosarcome", "myxofibrosarcome", "GIST", "tumeur fibreuse solitaire", "sarcome indifférencié", "sarcome", "type histologique"],
            exemple_formulation="Liposarcome bien différencié / tumeur lipomateuse atypique",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade FNCLCC",
            description="Grade FNCLCC avec détail des 3 scores (différenciation, mitoses, nécrose)",
            section="microscopie",
            mots_cles_detection=["FNCLCC", "grade", "différenciation", "mitoses", "nécrose", "score"],
            exemple_formulation="Grade FNCLCC : 2/3 (différenciation : 2, mitoses : 1 (5 mitoses/10 HPF), nécrose : 1 (<50%))",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille tumorale",
            description="Plus grande dimension de la tumeur",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille tumorale : 12 cm de grand axe",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Profondeur",
            description="Localisation par rapport au fascia superficiel (superficiel vs profond)",
            section="macroscopie",
            mots_cles_detection=["profondeur", "superficiel", "profond", "fascia", "sous-fascial", "sus-fascial", "sous-cutané", "intramusculaire"],
            exemple_formulation="Tumeur profonde (sous-fasciale, intramusculaire)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges chirurgicales",
            description="Statut des marges de résection et distance minimale",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "résection", "recoupe", "distance", "R0", "R1", "R2"],
            exemple_formulation="Marges chirurgicales : saines (R0), distance minimale 8 mm (marge profonde)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Emboles",
            description="Présence ou absence d'emboles vasculaires",
            section="microscopie",
            mots_cles_detection=["emboles", "vasculaires", "invasion vasculaire"],
            exemple_formulation="Emboles vasculaires : absents",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM",
            description="Classification pTNM selon AJCC 8e édition",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2b (tumeur profonde > 5 cm) (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 20. SYSTÈME NERVEUX CENTRAL
# ---------------------------------------------------------------------------
TEMPLATE_SNC: TemplateOrgane = TemplateOrgane(
    organe="systeme_nerveux_central",
    nom_affichage="Système nerveux central",
    sous_types=["biopsie stéréotaxique", "exérèse chirurgicale", "résection partielle", "résection complète"],
    mots_cles_detection=["cerveau", "cérébral", "cérébrale", "gliome", "glioblastome", "astrocytome", "oligodendrogliome", "méningiome", "médulloblastome", "craniotomie", "encéphale", "temporal", "frontal", "pariétal", "occipital", "tronc cérébral", "cervelet", "moelle épinière", "SNC"],
    marqueurs_ihc=["IDH1 R132H", "ATRX", "p53", "GFAP", "Olig2", "Ki67", "H3K27M", "H3K27me3", "EMA", "SSTR2A", "synaptophysine", "NeuN", "INI1", "BRG1", "neurofilament", "beta-caténine"],
    systeme_staging="Classification OMS 2021 des tumeurs du SNC (grade 1 à 4)",
    template_macroscopie=(
        "Fragments tissulaires [biopsie stéréotaxique / exérèse] mesurant au total [X] x [X] x [X] cm. "
        "Tissu de couleur [grisâtre/blanchâtre/hémorragique/nécrotique], "
        "de consistance [molle/ferme/gélatineuse]. "
        "Inclusion en totalité en [X] cassettes."
    ),
    template_conclusion=(
        "Tumeur du système nerveux central : [type histologique] (classification OMS 2021).\n"
        "- Grade OMS : [1/2/3/4]\n"
        "- IDH1/IDH2 : [muté (R132H) / wild-type]\n"
        "- ATRX : [expression conservée / perte d'expression]\n"
        "- Codélétion 1p/19q : [présente/absente]\n"
        "- MGMT (méthylation du promoteur) : [méthylé/non méthylé]\n"
        "- H3K27M : [muté/wild-type] (si gliome diffus de la ligne médiane)\n"
        "- Ki67 : [X]%\n"
        "- Marges : [exérèse complète / subtotale / biopsie seule]"
    ),
    notes_specifiques=(
        "La classification OMS 2021 des tumeurs du SNC intègre les marqueurs moléculaires dans la définition même des entités. "
        "Glioblastome IDH-wildtype = grade 4 même sans nécrose ni prolifération microvasculaire si présence d'au moins un marqueur moléculaire (amplification EGFR, gain chr 7/perte chr 10, mutation promoteur TERT). "
        "Astrocytome IDH-muté : IDH1/2 muté, ATRX perdu, 1p/19q intacts. "
        "Oligodendrogliome IDH-muté : IDH1/2 muté, ATRX conservé, codélétion 1p/19q. "
        "La méthylation du promoteur MGMT est prédictive de la réponse au témozolomide."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique (classification OMS 2021)",
            description="Type histologique selon la classification OMS 2021 intégrée (histologie + moléculaire)",
            section="microscopie",
            mots_cles_detection=["glioblastome", "astrocytome", "oligodendrogliome", "méningiome", "médulloblastome", "épendymome", "schwannome", "métastase", "type histologique"],
            exemple_formulation="Glioblastome, IDH-wildtype (OMS 2021, grade 4)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade OMS",
            description="Grade OMS 2021 (1, 2, 3 ou 4)",
            section="microscopie",
            mots_cles_detection=["grade OMS", "grade 1", "grade 2", "grade 3", "grade 4", "bas grade", "haut grade"],
            exemple_formulation="Grade OMS : 4",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="IDH1/IDH2",
            description="Statut mutationnel IDH1 (R132H par IHC et/ou séquençage) et IDH2",
            section="ihc",
            mots_cles_detection=["IDH1", "IDH2", "IDH", "R132H", "R172K", "mutation", "wild-type", "sauvage"],
            exemple_formulation="IDH1 R132H (IHC) : négatif. Séquençage IDH1/IDH2 : wild-type.",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="ATRX",
            description="Expression d'ATRX en IHC (conservée ou perdue)",
            section="ihc",
            mots_cles_detection=["ATRX", "expression conservée", "perte d'expression", "alpha-thalassemia"],
            exemple_formulation="ATRX : perte d'expression nucléaire dans les cellules tumorales (expression conservée dans l'endothélium, contrôle interne positif)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Codélétion 1p/19q",
            description="Recherche de codélétion 1p/19q par FISH ou autre technique",
            section="biologie_moleculaire",
            mots_cles_detection=["1p/19q", "codélétion", "1p", "19q", "FISH", "oligodendrogliome"],
            exemple_formulation="Codélétion 1p/19q (FISH) : présente (compatible avec un oligodendrogliome)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Méthylation du promoteur MGMT",
            description="Statut de méthylation du promoteur du gène MGMT",
            section="biologie_moleculaire",
            mots_cles_detection=["MGMT", "méthylation", "promoteur", "méthylé", "non méthylé", "témozolomide"],
            exemple_formulation="Méthylation du promoteur MGMT : méthylé (prédictif d'une meilleure réponse au témozolomide)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="H3K27M",
            description="Statut de la mutation H3K27M (obligatoire pour les gliomes diffus de la ligne médiane)",
            section="ihc",
            mots_cles_detection=["H3K27M", "H3K27", "histone H3", "ligne médiane", "K27M", "H3K27me3"],
            exemple_formulation="H3K27M (IHC) : négatif",
            obligatoire=False
        ),
        ChampObligatoire(
            nom="Ki67",
            description="Index de prolifération Ki67",
            section="ihc",
            mots_cles_detection=["Ki67", "Ki-67", "MIB-1", "prolifération", "index"],
            exemple_formulation="Ki67 : 30% des cellules tumorales",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Qualité de l'exérèse",
            description="Évaluation de la qualité de l'exérèse (complète, subtotale, biopsie seule)",
            section="conclusion",
            mots_cles_detection=["exérèse", "résection", "complète", "subtotale", "partielle", "biopsie", "marge"],
            exemple_formulation="Exérèse macroscopiquement complète (à corréler avec l'IRM postopératoire)",
            obligatoire=True
        ),
    ]
)

# ---------------------------------------------------------------------------
# 21. CANAL ANAL / MARGE ANALE
# ---------------------------------------------------------------------------
TEMPLATE_CANAL_ANAL: TemplateOrgane = TemplateOrgane(
    organe="canal_anal",
    nom_affichage="Canal anal / Marge anale",
    sous_types=["biopsie", "exérèse locale", "résection abdomino-périnéale"],
    mots_cles_detection=["canal anal", "anal", "anale", "marge anale", "péri-anal", "anus", "ligne pectinée", "AIN", "néoplasie intraépithéliale anale"],
    marqueurs_ihc=["p16", "p63", "CK5/6", "CK7", "CK20", "Ki67", "CDX2"],
    systeme_staging="TNM 8e édition - Canal anal (AJCC/UICC)",
    template_macroscopie=(
        "Biopsie / Exérèse de la région [canal anal / marge anale] mesurant [X] x [X] x [X] cm. "
        "Lésion [polypoïde/ulcérée/plane] de [X] x [X] cm. "
        "Distance aux marges : [X] mm. "
        "Inclusion en totalité."
    ),
    template_conclusion=(
        "Carcinome épidermoïde / Lésion de néoplasie intraépithéliale anale du [canal anal / marge anale].\n"
        "- Type histologique : [épidermoïde / basaloïde / cloacogénique / adénocarcinome]\n"
        "- Grade (si AIN) : [AIN 1 (LSIL) / AIN 2-3 (HSIL)]\n"
        "- p16 : [positif en bloc / négatif]\n"
        "- Taille lésionnelle : [X] mm\n"
        "- Marges : [saines/envahies]\n"
        "- Invasion si carcinome : profondeur [X] mm\n"
        "- pTNM (si invasif) : pT[X] pN[X] (AJCC 8e édition)"
    ),
    notes_specifiques=(
        "La quasi-totalité des carcinomes du canal anal sont liés à l'HPV. "
        "p16 positif en bloc est le surrogat de l'infection HPV à haut risque. "
        "La terminologie recommandée est LSIL (Low-grade Squamous Intraepithelial Lesion, = AIN1) et HSIL (High-grade, = AIN2-3). "
        "Le traitement de référence du carcinome épidermoïde du canal anal est la radio-chimiothérapie (protocole de Nigro), pas la chirurgie en première intention."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type histologique",
            description="Type histologique de la lésion",
            section="microscopie",
            mots_cles_detection=["carcinome épidermoïde", "basaloïde", "cloacogénique", "adénocarcinome", "AIN", "LSIL", "HSIL", "type histologique"],
            exemple_formulation="Carcinome épidermoïde bien différencié du canal anal",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Grade AIN",
            description="Grade de la néoplasie intraépithéliale anale (AIN1/LSIL, AIN2-3/HSIL)",
            section="microscopie",
            mots_cles_detection=["AIN", "AIN1", "AIN2", "AIN3", "LSIL", "HSIL", "néoplasie intraépithéliale", "dysplasie"],
            exemple_formulation="Néoplasie intraépithéliale anale de haut grade (HSIL / AIN3)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="p16 (IHC)",
            description="Expression de p16 en immunohistochimie",
            section="ihc",
            mots_cles_detection=["p16", "p16INK4a", "HPV", "en bloc", "positif", "négatif"],
            exemple_formulation="p16 : positif en bloc (surrogat HPV haut risque)",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Taille lésionnelle",
            description="Plus grande dimension de la lésion",
            section="macroscopie",
            mots_cles_detection=["taille", "dimension", "mesurant", "mm", "cm"],
            exemple_formulation="Taille lésionnelle : 25 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Marges",
            description="Statut des marges de résection",
            section="microscopie",
            mots_cles_detection=["marge", "marges", "résection", "recoupe", "berge", "limite"],
            exemple_formulation="Marges d'exérèse : saines, distance minimale 3 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="Invasion si carcinome",
            description="Profondeur d'invasion en cas de carcinome invasif",
            section="microscopie",
            mots_cles_detection=["invasion", "infiltrant", "invasif", "profondeur", "stromale", "infiltration"],
            exemple_formulation="Invasion du sphincter interne sur une profondeur de 6 mm",
            obligatoire=True
        ),
        ChampObligatoire(
            nom="pTNM (si invasif)",
            description="Classification pTNM selon AJCC 8e édition pour les carcinomes invasifs",
            section="conclusion",
            mots_cles_detection=["pTNM", "pT", "pN", "stade", "TNM"],
            exemple_formulation="pT2 pN0 (AJCC 8e édition)",
            obligatoire=True
        ),
    ]
)


# ===========================================================================
# REGISTRE DE TOUS LES TEMPLATES
# ===========================================================================
# ---------------------------------------------------------------------------
# 22. VESICULE BILIAIRE (Gallbladder)
# ---------------------------------------------------------------------------
TEMPLATE_VESICULE_BILIAIRE: TemplateOrgane = TemplateOrgane(
    organe="vesicule_biliaire",
    nom_affichage="Vesicule biliaire",
    sous_types=["cholecystectomie", "piece operatoire"],
    mots_cles_detection=["vesicule", "vesicule biliaire", "cholecystectomie", "biliaire", "cystique"],
    marqueurs_ihc=[],
    systeme_staging="TNM 8e edition - Vesicule biliaire (AJCC/UICC)",
    template_macroscopie=(
        "Piece de cholecystectomie mesurant [X] cm de longueur. "
        "Sereuse [lisse/irreguliere]. "
        "A l'ouverture, muqueuse [d'aspect normal/epaissie/congestive/ulceree]. "
        "Contenu : [calcul(s) de [X] mm / bile epaisse / vide]. "
        "Paroi d'epaisseur [X] mm [reguliere/irreguliere]. "
        "[Presence/Absence] de lesion nodulaire ou tumorale."
    ),
    template_conclusion=(
        "Cholecystite [chronique/aigue] [lithiasique/alithiasique].\n"
        "- Muqueuse : [aspects de cholecystite chronique / metaplasie pylorique / dysplasie]\n"
        "- Paroi : [fibrose / hypertrophie musculaire / sinus de Rokitansky-Aschoff]\n"
        "- [Absence de lesion tumorale / Adenocarcinome infiltrant si tumoral]"
    ),
    notes_specifiques=(
        "La cholecystectomie est l'un des prelevements les plus frequents. "
        "Toujours verifier la muqueuse a la recherche de dysplasie ou de carcinome "
        "incidental (decouverte fortuite sur piece de cholecystectomie pour lithiase). "
        "En cas de tumeur : evaluer le pT (profondeur d'infiltration dans la paroi), "
        "la marge cystique, et le lit hepatique si present."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Etat de la muqueuse",
            description="Aspect de la muqueuse vesiculaire (normal, cholecystite, metaplasie, dysplasie)",
            section="microscopie",
            mots_cles_detection=["muqueuse", "cholecystite", "metaplasie", "dysplasie", "inflammation"],
            exemple_formulation="Muqueuse vesiculaire sieged d'une cholecystite chronique avec metaplasie pylorique",
            obligatoire=True,
        ),
        ChampObligatoire(
            nom="Presence de calculs",
            description="Presence ou absence de calculs biliaires",
            section="macroscopie",
            mots_cles_detection=["calcul", "lithiase", "lithiasique", "calculs"],
            exemple_formulation="Presence de multiples calculs de cholesterol mesurant de 2 a 8 mm",
            obligatoire=True,
        ),
    ],
)


# ---------------------------------------------------------------------------
# 23. APPENDICE (Appendix)
# ---------------------------------------------------------------------------
TEMPLATE_APPENDICE: TemplateOrgane = TemplateOrgane(
    organe="appendice",
    nom_affichage="Appendice",
    sous_types=["appendicectomie", "piece operatoire"],
    mots_cles_detection=["appendice", "appendicectomie", "appendiculaire", "caecal"],
    marqueurs_ihc=["Chromogranine A", "Synaptophysine", "Ki-67"],
    systeme_staging="TNM 8e edition - Appendice (AJCC/UICC)",
    template_macroscopie=(
        "Piece d'appendicectomie mesurant [X] cm de longueur et [X] cm de diametre. "
        "Sereuse [lisse/congestive/recouverte de fausses membranes]. "
        "A la coupe, lumiere [libre/contenant un stercolithe/obliteree]. "
        "Paroi d'epaisseur [reguliere/irreguliere], mesurant [X] mm. "
        "Base de section [saine/infiltree]."
    ),
    template_conclusion=(
        "Appendicite [aigue suppuree / aigue catarrhale / chronique / gangrenee / perforee].\n"
        "- [Presence/Absence] de peritonite associee\n"
        "- [Absence de tumeur / Tumeur neuroendocrine de [X] mm si applicable]"
    ),
    notes_specifiques=(
        "Toujours verifier la presence d'une tumeur neuroendocrine incidentale (carcinoide). "
        "Si tumeur neuroendocrine : mesurer la taille, evaluer l'infiltration de la meso-appendice, "
        "verifier la base de section. Si > 2 cm ou meso-appendice infiltre = hemicolectomie droite. "
        "Classification OMS 2019 pour les tumeurs neuroendocrines de l'appendice."
    ),
    champs_obligatoires=[
        ChampObligatoire(
            nom="Type d'appendicite",
            description="Type d'inflammation appendiculaire (catarrhale, suppuree, gangrenee, perforee)",
            section="microscopie",
            mots_cles_detection=["appendicite", "suppuree", "catarrhale", "gangrenee", "perforee", "inflammation"],
            exemple_formulation="Appendicite aigue suppuree avec infiltration transmurale de polynucleaires",
            obligatoire=True,
        ),
        ChampObligatoire(
            nom="Recherche de tumeur",
            description="Presence ou absence de tumeur neuroendocrine incidentale",
            section="microscopie",
            mots_cles_detection=["tumeur", "neuroendocrine", "carcinoide", "absence de tumeur", "absence de lesion tumorale"],
            exemple_formulation="Absence de lesion tumorale",
            obligatoire=True,
        ),
    ],
)


TOUS_LES_TEMPLATES: list[TemplateOrgane] = [
    TEMPLATE_SEIN,
    TEMPLATE_COLON_RECTUM,
    TEMPLATE_POUMON,
    TEMPLATE_PROSTATE,
    TEMPLATE_ESTOMAC,
    TEMPLATE_THYROIDE,
    TEMPLATE_REIN,
    TEMPLATE_VESSIE,
    TEMPLATE_COL_UTERIN,
    TEMPLATE_ENDOMETRE,
    TEMPLATE_OVAIRE,
    TEMPLATE_MELANOME,
    TEMPLATE_FOIE,
    TEMPLATE_PANCREAS,
    TEMPLATE_OESOPHAGE,
    TEMPLATE_ORL,
    TEMPLATE_TESTICULE,
    TEMPLATE_LYMPHOME,
    TEMPLATE_SARCOME,
    TEMPLATE_SNC,
    TEMPLATE_CANAL_ANAL,
    TEMPLATE_VESICULE_BILIAIRE,
    TEMPLATE_APPENDICE,
]

_INDEX_PAR_ORGANE: dict[str, TemplateOrgane] = {t.organe: t for t in TOUS_LES_TEMPLATES}


# ===========================================================================
# FONCTIONS EXPORTÉES
# ===========================================================================


import re as _re

from text_utils import normaliser as _normaliser_accents


def _mot_cle_present(mot_cle_norm: str, texte_norm: str) -> bool:
    """Vérifie la présence d'un mot-clé avec respect des limites de mots."""
    pattern: str = r"\b" + _re.escape(mot_cle_norm) + r"\b"
    return _re.search(pattern, texte_norm) is not None


def detecter_organe(transcript: str) -> str | None:
    """Détecte l'organe principal à partir du transcript.

    Parcourt les mots-clés de détection de chaque template et retourne
    l'organe dont le score de correspondance est le plus élevé.
    Utilise le matching par mots entiers pour éviter les faux positifs.
    Retourne None si aucun organe n'est détecté avec un score suffisant.
    """
    texte_norm: str = _normaliser_accents(transcript.lower())
    meilleur_organe: str | None = None
    meilleur_score: int = 0

    for template in TOUS_LES_TEMPLATES:
        score: int = 0
        for mot_cle in template.mots_cles_detection:
            mot_cle_norm: str = _normaliser_accents(mot_cle.lower())
            if _mot_cle_present(mot_cle_norm, texte_norm):
                score += 1
        if score > meilleur_score:
            meilleur_score = score
            meilleur_organe = template.organe

    # Seuil minimum : au moins 1 mot-clé spécifique détecté
    if meilleur_score < 1:
        return None

    return meilleur_organe


def get_template(organe: str) -> TemplateOrgane | None:
    """Retourne le template pour un organe donné.

    Accepte le nom interne (ex. 'sein', 'colon_rectum') ou le nom
    d'affichage (ex. 'Sein', 'Côlon-Rectum').
    """
    organe_lower: str = organe.lower().strip()

    # Recherche directe par clé
    if organe_lower in _INDEX_PAR_ORGANE:
        return _INDEX_PAR_ORGANE[organe_lower]

    # Recherche par nom d'affichage
    for template in TOUS_LES_TEMPLATES:
        if template.nom_affichage.lower() == organe_lower:
            return template

    # Recherche partielle
    for template in TOUS_LES_TEMPLATES:
        if organe_lower in template.organe or organe_lower in template.nom_affichage.lower():
            return template

    return None


def get_all_organes() -> list[str]:
    """Retourne la liste de tous les organes couverts (noms internes)."""
    return [t.organe for t in TOUS_LES_TEMPLATES]


def get_champs_obligatoires(organe: str) -> list[ChampObligatoire]:
    """Retourne les champs obligatoires pour un organe.

    Retourne une liste vide si l'organe n'est pas trouvé.
    """
    template: TemplateOrgane | None = get_template(organe)
    if template is None:
        return []
    return [c for c in template.champs_obligatoires if c.obligatoire]


def detecter_champs_manquants(organe: str, texte_rapport: str) -> list[ChampObligatoire]:
    """Détecte les champs obligatoires manquants dans un texte de rapport.

    Pour chaque champ obligatoire, vérifie si au moins un des mots-clés
    de détection est présent dans le texte. Retourne la liste des champs
    non détectés.
    """
    champs: list[ChampObligatoire] = get_champs_obligatoires(organe)
    texte_lower: str = texte_rapport.lower()
    manquants: list[ChampObligatoire] = []

    for champ in champs:
        trouve: bool = False
        for mot_cle in champ.mots_cles_detection:
            if mot_cle.lower() in texte_lower:
                trouve = True
                break
        if not trouve:
            manquants.append(champ)

    return manquants


def generer_prompt_template(organe: str) -> str:
    """Génère le texte de template à injecter dans le prompt LLM pour un organe donné.

    Retourne une chaîne vide si l'organe n'est pas trouvé.
    """
    template: TemplateOrgane | None = get_template(organe)
    if template is None:
        return ""

    lignes: list[str] = []
    lignes.append(f"=== TEMPLATE COMPTE RENDU : {template.nom_affichage.upper()} ===")
    lignes.append("")
    lignes.append(f"Système de staging : {template.systeme_staging}")
    lignes.append("")

    # Notes spécifiques
    lignes.append("--- NOTES SPÉCIFIQUES ---")
    lignes.append(template.notes_specifiques)
    lignes.append("")

    # Champs obligatoires par section
    sections_ordre: list[str] = ["macroscopie", "microscopie", "ihc", "biologie_moleculaire", "conclusion"]
    noms_sections: dict[str, str] = {
        "macroscopie": "MACROSCOPIE",
        "microscopie": "MICROSCOPIE",
        "ihc": "IMMUNOHISTOCHIMIE",
        "biologie_moleculaire": "BIOLOGIE MOLÉCULAIRE",
        "conclusion": "CONCLUSION",
    }

    for section in sections_ordre:
        champs_section: list[ChampObligatoire] = [
            c for c in template.champs_obligatoires if c.section == section
        ]
        if not champs_section:
            continue

        nom_section: str = noms_sections.get(section, section.upper())
        lignes.append(f"--- {nom_section} ---")
        lignes.append("Données OBLIGATOIRES à inclure :")
        for champ in champs_section:
            statut: str = "OBLIGATOIRE" if champ.obligatoire else "recommandé"
            lignes.append(f"  - {champ.nom} [{statut}] : {champ.description}")
            lignes.append(f"    Exemple : {champ.exemple_formulation}")
        lignes.append("")

    # Marqueurs IHC attendus
    lignes.append("--- MARQUEURS IHC ATTENDUS ---")
    lignes.append(", ".join(template.marqueurs_ihc))
    lignes.append("")

    # Template macroscopie
    lignes.append("--- MODÈLE DE MACROSCOPIE ---")
    lignes.append(template.template_macroscopie)
    lignes.append("")

    # Template conclusion
    lignes.append("--- MODÈLE DE CONCLUSION ---")
    lignes.append(template.template_conclusion)
    lignes.append("")

    return "\n".join(lignes)
