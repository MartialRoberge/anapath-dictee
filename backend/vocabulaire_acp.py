"""Vocabulaire complet d'anatomie et cytologie pathologiques (ACP).

Ce module sert trois objectifs :
1. WordBoost prompt pour Voxtral STT (amorce la reconnaissance vocale médicale)
2. Dictionnaire de corrections phonétiques (erreurs STT fréquentes → termes corrects)
3. Dictionnaires d'expansion d'acronymes, marqueurs IHC et négations standardisées

Toutes les annotations de type sont conformes à Pylance en mode basic.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# A. WORDBOOST PROMPT
# ---------------------------------------------------------------------------
# Chaîne unique envoyée comme paramètre `prompt` à Voxtral pour amorcer
# la reconnaissance des termes médicaux d'anatomopathologie.
# ---------------------------------------------------------------------------

WORDBOOST_PROMPT: str = (
    # ── Sigles et acronymes IHC ──────────────────────────────────────────
    "TTF1 TTF-1 ALK PD-L1 PDL1 Ki67 Ki-67 MIB1 "
    "CK7 CK20 CK5/6 CK5 CK6 CK19 CK18 CK14 CK8 CK34BE12 AE1/AE3 CAM5.2 "
    "CD3 CD4 CD5 CD7 CD8 CD10 CD15 CD20 CD21 CD23 CD25 CD30 CD31 CD34 "
    "CD38 CD43 CD44 CD45 CD56 CD57 CD61 CD68 CD79a CD99 CD117 CD138 CD163 "
    "CDX2 p16 p40 p53 p57 p63 "
    "GATA3 WT1 PAX2 PAX5 PAX8 SOX2 SOX9 SOX10 SOX11 "
    "S100 S-100 HMB45 HMB-45 Melan-A MelanA MITF "
    "EMA AMACR P504S PSA PSAP ERG NKX3.1 NKX3-1 "
    "Chromogranine Chromogranine-A Synaptophysine NSE INSM1 "
    "GCDFP15 GCDFP-15 Mammaglobine "
    "RE RP ER PR AR HER2 HER-2 "
    "BRCA1 BRCA2 MLH1 MSH2 MSH6 PMS2 "
    "BRAF BRAF-V600E RAS KRAS NRAS HRAS EGFR ROS1 MET ALK-D5F3 "
    "FGFR FGFR1 FGFR2 FGFR3 NTRK NTRK1 NTRK2 NTRK3 RET "
    "IDH1 IDH2 ATRX H3K27M H3K27me3 INI1 BRG1 SMARCB1 SMARCA4 "
    "Desmine Myogénine MyoD1 Actine-muscle-lisse SMA Caldesmone Calponine "
    "DOG1 BCL2 BCL6 BCL10 MUM1 IRF4 Cycline-D1 CCND1 "
    "TdT MPO Lysozyme Myéloperoxydase "
    "Calrétinine D2-40 Podoplanine "
    "CKAE1AE3 Vimentine Laminine Collagène-IV "
    "Beta-caténine E-cadhérine "
    "Glypican-3 Arginase-1 Hépar1 Hépatocyte "
    "OCT3/4 SALL4 PLAP AFP HCG "
    "LEF1 TCF1 Claudine-18 CLDN18.2 "
    "FLI1 ERG-nucléaire "
    "PD1 PD-1 LAG3 TIM3 CTLA4 CTLA-4 "
    "MSI MMR dMMR pMMR MSS MSI-H MSI-L "
    "FISH CISH SISH NGS PCR RT-PCR "

    # ── Éponymes et scores ────────────────────────────────────────────────
    "Gleason score-de-Gleason ISUP grade-ISUP "
    "Scarff-Bloom-Richardson SBR Nottingham Elston-Ellis "
    "Breslow indice-de-Breslow Clark niveau-de-Clark "
    "Fuhrman WHO/ISUP grade-nucléaire-de-Fuhrman "
    "Lauren classification-de-Lauren Borrmann Siewert "
    "TNM pTNM ypTNM cTNM AJCC UICC 8e-édition "
    "FIGO stade-FIGO Ann-Arbor Lugano Rai Binet "
    "Child-Pugh MELD Barcelona BCLC "
    "Dukes Astler-Coller "
    "Sydney OLGA OLGIM "
    "Bethesda système-de-Bethesda "
    "EU-TIRADS TIRADS ACR-TIRADS BIRADS BI-RADS PI-RADS PIRADS LI-RADS LIRADS "
    "Frankel Kadish Masaoka Masaoka-Koga "
    "Silverberg Shimada "
    "OMS WHO classification-OMS "
    "CIN LSIL HSIL ASC-US ASC-H AGC AIS "
    "Vienna classification-de-Vienne "
    "Bosniak "
    "Edmondson-Steiner "
    "ENETS "

    # ── Types histologiques ───────────────────────────────────────────────
    "adénocarcinome carcinome-épidermoïde carcinome-urothélial "
    "carcinome-neuroendocrine tumeur-neuroendocrine carcinoïde "
    "carcinome-à-petites-cellules carcinome-à-grandes-cellules "
    "carcinome-adénosquameux carcinome-sarcomatoïde "
    "carcinome-indifférencié carcinome-médullaire "
    "carcinome-mucineux carcinome-colloïde "
    "carcinome-papillaire carcinome-folliculaire carcinome-anaplasique "
    "carcinome-lobulaire carcinome-canalaire carcinome-tubuleux "
    "carcinome-micropapillaire carcinome-inflammatoire "
    "carcinome-basocellulaire carcinome-spinocellulaire "
    "carcinome-à-cellules-claires carcinome-chromophobe "
    "carcinome-à-cellules-de-Merkel "
    "carcinome-hépatocellulaire cholangiocarcinome "
    "mélanome mélanome-nodulaire mélanome-à-extension-superficielle "
    "mélanome-acrolentigineux mélanome-de-Dubreuilh "
    "lymphome lymphome-B-diffus-à-grandes-cellules LBDGC "
    "lymphome-folliculaire lymphome-du-manteau "
    "lymphome-de-Burkitt lymphome-de-Hodgkin lymphome-non-hodgkinien "
    "lymphome-de-la-zone-marginale lymphome-MALT "
    "lymphome-lymphoplasmocytaire lymphome-T-périphérique "
    "lymphome-anaplasique-à-grandes-cellules mycosis-fungoïde "
    "leucémie-lymphoïde-chronique LLC "
    "myélome-multiple plasmocytome "
    "sarcome liposarcome léiomyosarcome rhabdomyosarcome "
    "fibrosarcome myxofibrosarcome angiosarcome "
    "sarcome-synovial sarcome-d'Ewing sarcome-à-cellules-claires "
    "sarcome-pléomorphe-indifférencié ostéosarcome chondrosarcome "
    "dermatofibrosarcome-de-Darier-Ferrand DFSP "
    "tumeur-fibreuse-solitaire "
    "mésothéliome mésothéliome-épithélioïde mésothéliome-sarcomatoïde "
    "mésothéliome-biphasique "
    "GIST tumeur-stromale-gastro-intestinale "
    "phéochromocytome paragangliome "
    "schwannome neurofibrome "
    "méningiome glioblastome GBM astrocytome oligodendrogliome "
    "épendymome médulloblastome "
    "rétinoblastome neuroblastome néphroblastome tumeur-de-Wilms "
    "hépatoblastome "
    "tératome tératome-mature tératome-immature "
    "séminome dysgerminome germinome "
    "carcinome-embryonnaire choriocarcinome tumeur-du-sac-vitellin "
    "tumeur-mixte-germinale "
    "thymome carcinome-thymique "

    # ── Architecture tissulaire ───────────────────────────────────────────
    "trabéculaire acineux acineuse papillaire micropapillaire "
    "cribriforme lépidique solide tubulopapillaire "
    "mucineux mucinouse séreux séreuse endométrioïde "
    "glandulaire tubulaire villo-glandulaire "
    "fasciculé storiforme palissadique "
    "alvéolaire lobulaire folliculaire diffus "
    "insulaire cordonal organoïde "
    "en-rosettes en-nids en-travées en-nappes en-plages "
    "architecture-de-remplacement push-pattern "
    "budding tumour-budding "

    # ── Cytologie ─────────────────────────────────────────────────────────
    "atypie atypies-cytonucléaires mitose mitoses "
    "figures-de-mitose index-mitotique indice-mitotique "
    "nécrose nécrose-tumorale nécrose-coagulative nécrose-caséeuse "
    "koïlocyte koïlocytose dyskératose "
    "acanthose parakératose orthokératose hyperkératose "
    "spongiose exocytose apoptose "
    "pléomorphisme anisocaryose anisocytose "
    "hyperchromatisme noyaux-vésiculeux nucléole-proéminent "
    "cellules-en-bague-à-chaton cellules-fusiformes cellules-épithélioïdes "
    "cellules-géantes cellules-de-Reed-Sternberg "
    "cellules-de-Langerhans cellules-dendritiques "
    "cellules-oncocytaires cellules-oxyphiles "
    "cellules-claires cellules-éosinophiles cellules-basophiles "
    "multinucléation binucléation "
    "rapport-nucléo-cytoplasmique "
    "emperipolèse emperipoièse "
    "pseudo-inclusion-nucléaire rainure-nucléaire "

    # ── Stroma et environnement ───────────────────────────────────────────
    "stroma desmoplasique desmoplasie "
    "fibro-hyalin fibro-vasculaire myxoïde "
    "inflammatoire lymphocytaire plasmocytaire "
    "nécrotique fibreux fibrose "
    "sclérosant sclérohyalin "
    "stroma-remanié stroma-lâche stroma-dense "
    "réaction-stromale stroma-desmoplastique "
    "infiltrat-inflammatoire infiltrat-lymphocytaire "
    "TILs lymphocytes-intra-tumoraux "
    "angiogenèse néo-vascularisation "

    # ── Marges et résection ───────────────────────────────────────────────
    "marges-saines marges-envahies marges-tangentes "
    "marge-profonde marge-latérale marge-distale marge-proximale "
    "marge-circonférentielle marge-de-résection "
    "R0 R1 R2 Rx "
    "encrage encrage-à-l'encre-de-Chine "
    "recoupe recoupes limites-de-résection "
    "exérèse-complète exérèse-incomplète "
    "marge-de-sécurité clearance "

    # ── Différenciation ───────────────────────────────────────────────────
    "bien-différencié moyennement-différencié peu-différencié indifférencié "
    "différenciation-glandulaire différenciation-malpighienne "
    "différenciation-neuroendocrine "
    "dédifférencié transdifférenciation "
    "grade-1 grade-2 grade-3 G1 G2 G3 GX "
    "haut-grade bas-grade grade-intermédiaire "

    # ── Ganglions et staging ──────────────────────────────────────────────
    "ganglion ganglion-sentinelle ganglions "
    "curage curage-ganglionnaire curage-axillaire curage-pelvien "
    "curage-lombo-aortique curage-cervical "
    "métastase-ganglionnaire adénopathie "
    "effraction-capsulaire rupture-capsulaire "
    "extension-extra-ganglionnaire "
    "micrométastase macrométastase "
    "cellules-tumorales-isolées ITC "
    "pN0 pN1 pN1mi pN0(i+) "

    # ── Prélèvements et chirurgie ─────────────────────────────────────────
    "biopsie biopsie-exérèse biopsie-incisionnelle "
    "ponction-biopsie micro-biopsie macrobiopsie "
    "pièce-opératoire exérèse résection "
    "lobectomie pneumonectomie segmentectomie "
    "mastectomie tumorectomie quadrantectomie zonectomie "
    "mastectomie-totale mastectomie-radicale-modifiée "
    "colectomie hémicolectomie résection-antérieure "
    "sigmoïdectomie appendicectomie "
    "gastrectomie gastrectomie-totale gastrectomie-subtotale "
    "prostatectomie prostatectomie-radicale "
    "néphrectomie néphrectomie-partielle néphrectomie-élargie "
    "cystectomie cystoprostatectomie "
    "hystérectomie hystérectomie-totale "
    "annexectomie ovariectomie salpingectomie "
    "conisation résection-à-l'anse "
    "thyroïdectomie lobo-isthmectomie parathyroïdectomie "
    "surrénalectomie splénectomie pancréatectomie "
    "duodéno-pancréatectomie-céphalique DPC Whipple "
    "hépatectomie hépatectomie-droite hépatectomie-gauche "
    "laryngectomie pharyngolaryngectomie "
    "parotidectomie sous-maxillectomie "
    "orchidectomie orchidectomie-radicale "
    "amputation-abdomino-périnéale "
    "exentération-pelvienne "
    "curetage curetage-biopsique "
    "ponction-aspiration cytoponction "
    "prélèvement-per-endoscopique polypectomie mucosectomie "
    "dissection-sous-muqueuse "
    "médiastinoscopie thoracoscopie coelioscopie "

    # ── Fixation, inclusion, colorations ──────────────────────────────────
    "formol formol-tamponné fixation inclusion-en-paraffine "
    "paraffine coupe coupes-sériées coupe-semi-fine "
    "coloration colorations-spéciales colorations-histochimiques "
    "HES hématoxyline-éosine-safran HE "
    "PAS acide-periodique-de-Schiff PAS-diastase "
    "bleu-Alcian bleu-de-toluidine "
    "trichrome trichrome-de-Masson "
    "Perls coloration-de-Perls bleu-de-Prusse "
    "réticuline Gordon-Sweet "
    "MGG May-Grünwald-Giemsa "
    "Papanicolaou Pap "
    "Grocott Grocott-Gomori méthénamine-argentique "
    "Ziehl-Neelsen Ziehl auramine "
    "Giemsa Warthin-Starry "
    "rouge-Congo vert-de-méthyle-pyronine "
    "Fontana-Masson "
    "orcéine "
    "Von-Kossa "
    "Huile-rouge Oil-Red-O "
    "immunohistochimie IHC immunofluorescence "
    "hybridation-in-situ FISH CISH double-marquage "
    "extemporané examen-extemporané congélation "
    "microscopie-électronique cytométrie-en-flux "

    # ── Topographie et organes ────────────────────────────────────────────
    "bronchique broncho-pulmonaire pulmonaire pleural "
    "médiastinal thymique "
    "gastrique fundique antral pylorique cardial "
    "colique rectal iléal jéjunal duodénal grêlique "
    "appendiculaire sigmoïdien "
    "hépatique biliaire vésiculaire cholédocien "
    "pancréatique céphalique corporéal caudal "
    "mammaire sein axillaire "
    "prostatique séminal testiculaire épididymaire "
    "rénal pyélique urétéral vésical urétral "
    "utérin cervical endocervical exocervical "
    "endométrial myométrial "
    "ovarien tubaire péritonéal "
    "thyroïdien parathyroïdien surrénalien "
    "cutané sous-cutané dermique épidermique "
    "hypodermique "
    "ganglionnaire lymphatique "
    "osseux médullaire ostéo-médullaire "
    "cérébral cérébraux méningé rachidien "
    "salivaire parotidien sous-mandibulaire "
    "laryngé pharyngé trachéal "
    "nasal sinusien naso-sinusien rhino-pharyngé "
    "oesophagien jonction-oeso-gastrique "
    "rétro-péritonéal mésentérique épiploïque "
    "vulvaire vaginal pénien scrotal "
    "orbitaire oculaire rétinien "
    "surrénalien cortico-surrénalien médullo-surrénalien "
    "musculaire synovial articulaire "

    # ── Cytologie en milieu liquide et LBA ────────────────────────────────
    "LBA lavage-broncho-alvéolaire "
    "macrophages sidérophages macrophages-alvéolaires "
    "lymphocytes lymphocytes-T lymphocytes-B "
    "polynucléaires-neutrophiles polynucléaires-éosinophiles "
    "polynucléaires-basophiles mastocytes "
    "cellules-malpighiennes cellules-cylindriques "
    "cellules-de-revêtement cellules-métaplasiques "
    "sous-population-lymphocytaire rapport-CD4/CD8 "
    "formule-cytologique numération-cellulaire "
    "épanchement-pleural épanchement-péritonéal ascite "
    "liquide-céphalo-rachidien LCR "
    "cytologie-urinaire cytologie-cervico-vaginale "

    # ── Grade et indice de prolifération ──────────────────────────────────
    "haut-grade bas-grade grade-intermédiaire "
    "indice-mitotique nombre-de-mitoses "
    "index-de-prolifération Ki67 MIB1 "
    "score-histopronostique grade-histologique "
    "grade-nucléaire grade-architectural "
    "bien-différencié moyennement-différencié peu-différencié "

    # ── Emboles et invasion ───────────────────────────────────────────────
    "emboles emboles-vasculaires emboles-lymphatiques "
    "emboles-veineux emboles-artériels "
    "engainements-périnerveux invasion-péri-nerveuse "
    "invasion-vasculaire invasion-lymphatique "
    "lymphovascular-invasion LVI "
    "effraction-capsulaire franchissement-capsulaire "
    "invasion-de-la-graisse-péri-rénale invasion-du-sinus-rénal "

    # ── Inflammation et lésions non tumorales ─────────────────────────────
    "granulome granulome-épithélioïde granulome-giganto-cellulaire "
    "granulome-à-corps-étranger granulome-tuberculoïde "
    "nécrose-caséeuse nécrose-fibrinoïde "
    "fibrose fibrose-interstitielle fibrose-portale fibrose-septale "
    "fibrose-en-pont fibrose-mutilante cirrhose "
    "hyalinisation sclérose "
    "calcification calcifications-dystrophiques psammome "
    "métaplasie métaplasie-intestinale métaplasie-malpighienne "
    "métaplasie-apocrine métaplasie-osseuse "
    "dysplasie dysplasie-de-bas-grade dysplasie-de-haut-grade "
    "hyperplasie hyperplasie-atypique "
    "hyperplasie-canalaire-atypique néoplasie-lobulaire "
    "inflammation-chronique inflammation-aiguë inflammation-subaiguë "
    "inflammation-granulomateuse "
    "gastrite duodénite colite oesophagite "
    "hépatite stéatose stéato-hépatite "
    "glomérulonéphrite néphrite-tubulo-interstitielle "
    "thyroïdite thyroïdite-de-Hashimoto maladie-de-Basedow "
    "sarcoïdose amylose "

    # ── Termes macroscopiques ─────────────────────────────────────────────
    "dimensions taille mesurant centimètres millimètres "
    "fixation fixé-dans-le-formol orientation orienté "
    "repères fils-repères agrafes "
    "encrage encré encrage-à-l'encre-de-Chine "
    "tranche-de-section surface-de-section "
    "fragmentation fragmenté fragmentaire "
    "consistance consistance-ferme consistance-molle "
    "nécrose hémorragie remaniements "
    "ulcération ulcéré bourgeonnement "
    "polypoïde sessile pédiculé "
    "infiltrant végétant ulcéro-infiltrant "
    "ulcéro-végétant exophytique endophytique "
    "bien-limité mal-limité encapsulé non-encapsulé "
    "ferme mou élastique gélatineux kystique charnu "
    "blanchâtre brunâtre jaunâtre noirâtre rougeâtre grisâtre "
    "verdâtre rosâtre "
    "homogène hétérogène remanié "
    "aspect-fasciculé aspect-lobulé aspect-nodulaire "
    "tumeur nodule lésion masse formation "
    "foyer plage zone territoire "
    "berge périphérie centre "
    "capsule pseudo-capsule "
    "pesant poids grammes "
    "longueur largeur épaisseur profondeur "
    "diamètre plus-grand-axe "

    # ── Termes de conclusion et formulation ───────────────────────────────
    "phénotype profil-immunohistochimique profil-IHC "
    "en-faveur-de compatible-avec évocateur-de "
    "absence-de présence-de "
    "infiltrant in-situ micro-invasif invasif "
    "métastatique primitif secondaire récidive "
    "résidu-tumoral reliquat-tumoral "
    "réponse-thérapeutique chimio-sensibilité "
    "régression-tumorale score-de-régression "
    "Mandard Dworak Becker TRG "
    "localisation-primitive localisation-secondaire "
    "aspect-morphologique aspect-histologique "
    "corrélation-anatomo-clinique confrontation "
    "complément-d'étude immunohistochimique demandé "
    "nécessaire souhaitable recommandé "
    "à-confronter-avec corrélation-radio-histologique "
    "sans-signe-de-malignité bénin malin "
    "suspect-de-malignité atypies-de-signification-indéterminée "
    "lésion-frontière borderline "
    "potentiel-de-malignité-incertain UMP "
    "pT pN pM stade staging "
    "classification-pTNM 8e-édition-AJCC "
)

# ---------------------------------------------------------------------------
# B. CORRECTIONS PHONÉTIQUES
# ---------------------------------------------------------------------------
# Dictionnaire des erreurs fréquentes de transcription STT → termes corrects.
# Les clés sont en minuscules ; la recherche se fait en minuscules.
# ---------------------------------------------------------------------------

CORRECTIONS_PHONETIQUES: dict[str, str] = {
    # ── Erreurs existantes du système ─────────────────────────────────────
    "branchique": "bronchique",
    "branchiques": "bronchiques",
    "en plan chic": "bronchique",
    "mucose": "muqueuse",
    "équeuse": "muqueuse",
    "équeuse branchique": "muqueuse bronchique",
    "fibro-yalin": "fibro-hyalin",
    "trauma": "stroma",
    "racineuse": "acineuse",
    "dtf1": "TTF1",
    "yaline": "hyaline",
    "cananal": "canal anal",
    "ulière": "hilaire",
    "parenchymate": "parenchymateuse",
    # ── Corrections critiques découvertes sur audio réel ────────────────
    "tu meurs": "tumeur",
    "tu meurs sous la plèvre": "tumeur sous-pleurale",
    "mycosécrétion": "mucosécrétion",
    "pépillaire": "papillaire",
    "métaganglionnaire": "métastase ganglionnaire",
    "pas de métaganglionnaire": "absence de métastase ganglionnaire",
    "entraparenchymateux": "intraparenchymateux",
    "intra parenchymateux": "intraparenchymateux",
    "péribranchique": "péribronchique",
    "péribranchiques": "péribronchiques",
    "coup de bronche": "coupe bronchique",
    "coup de bronche qui est vasculaire": "coupe bronchique et vasculaire",
    "baréties": "Barety",
    "baréty": "Barety",
    "loge de baréties": "loge de Barety",
    "para-osophagiens": "para-oesophagiens",
    "para-osophagien": "para-oesophagien",
    "souple râle": "sous-pleurale",
    "on a encore une origine": "en accord avec une origine",
    "on a encore": "en accord avec",
    "alka négatif": "ALK négatif",
    "alka moins": "ALK négatif",
    "alk moins": "ALK négatif",
    "pdl un": "PD-L1",
    "pdl1": "PD-L1",
    "pd l1": "PD-L1",

    # ── H aspiré / H muet non capté ──────────────────────────────────────
    "yper": "hyper",
    "ypo": "hypo",
    "yperplasie": "hyperplasie",
    "ypoplasie": "hypoplasie",
    "ypertrophie": "hypertrophie",
    "yperchromatisme": "hyperchromatisme",
    "yperkératose": "hyperkératose",
    "istologique": "histologique",
    "istochimique": "histochimique",
    "istopronostique": "histopronostique",
    "istologie": "histologie",
    "istogenèse": "histogenèse",
    "épatique": "hépatique",
    "épatocellulaire": "hépatocellulaire",
    "épatocyte": "hépatocyte",
    "épatoblastome": "hépatoblastome",
    "émorragie": "hémorragie",
    "émorragique": "hémorragique",
    "émicolectomie": "hémicolectomie",
    "ystérectomie": "hystérectomie",
    "yalinisation": "hyalinisation",
    "yalinisé": "hyalinisé",
    "yaloïde": "hyaloïde",
    "ybridation": "hybridation",
    "yperbasophilie": "hyperbasophilie",
    "ypothyroïdie": "hypothyroïdie",
    "ilère": "hilaire",
    "ile": "hile",

    # ── Confusion de consonnes ────────────────────────────────────────────
    "bramchique": "bronchique",
    "blonchique": "bronchique",
    "bronquique": "bronchique",
    "troma": "stroma",
    "stoma": "stroma",
    "tromal": "stromal",
    "stomal": "stromal",
    "desmo plastique": "desmoplasique",
    "desmo plastik": "desmoplasique",
    "desmoplastik": "desmoplasique",
    "dès mo plastique": "desmoplasique",
    "chromogranine": "chromogranine",
    "chronogranine": "chromogranine",
    "sinaptophysine": "synaptophysine",
    "synaptofysine": "synaptophysine",
    "synaptophysin": "synaptophysine",
    "imuno histochimie": "immunohistochimie",
    "imuno-histochimie": "immunohistochimie",
    "immuno istochimie": "immunohistochimie",
    "carcinone": "carcinome",
    "carscinome": "carcinome",
    "karcinome": "carcinome",
    "adénocarsinome": "adénocarcinome",
    "adéno carcinome": "adénocarcinome",
    "lympome": "lymphome",
    "linphome": "lymphome",
    "limphome": "lymphome",
    "lymphôme": "lymphome",
    "sarcome": "sarcome",
    "sarcôme": "sarcome",
    "mésotheliome": "mésothéliome",
    "mésotéliome": "mésothéliome",
    "mesothéliome": "mésothéliome",
    "gliobalstome": "glioblastome",
    "glio blastome": "glioblastome",
    "fréochromocytome": "phéochromocytome",
    "féochromocytome": "phéochromocytome",
    "phéocromocytome": "phéochromocytome",
    "néfroblastome": "néphroblastome",
    "néfro blastome": "néphroblastome",
    "néfrectomie": "néphrectomie",
    "schvanome": "schwannome",
    "schwanome": "schwannome",
    "chwannome": "schwannome",

    # ── Troncature de syllabes ────────────────────────────────────────────
    "parenchymateux": "parenchymateux",
    "parenchymateuz": "parenchymateuse",
    "parenchime": "parenchyme",
    "parenquime": "parenchyme",
    "malpigien": "malpighienne",
    "malpigienne": "malpighienne",
    "malpighien": "malpighienne",
    "epiderm": "épidermoïde",
    "épiderm": "épidermoïde",
    "épidermoide": "épidermoïde",
    "adénocarcinomateux": "adénocarcinomateuse",
    "urotélial": "urothélial",
    "urothéliale": "urothélial",
    "urotéliale": "urothélial",

    # ── Homophones et assimilations ───────────────────────────────────────
    "les pidiques": "lépidique",
    "les pédiques": "lépidique",
    "lépidik": "lépidique",
    "lipidique": "lépidique",
    "l'épidique": "lépidique",
    "les pidique": "lépidique",
    "cribi forme": "cribriforme",
    "les quelles": "lesquelles",
    "des mots plastique": "desmoplasique",
    "cyber net": "cribriforme",
    "micro papillaire": "micropapillaire",
    "micro papier": "micropapillaire",
    "trabec ulaire": "trabéculaire",
    "trabe culaire": "trabéculaire",
    "trabéculer": "trabéculaire",
    "papiller": "papillaire",
    "acineuz": "acineuse",
    "acineuze": "acineuse",
    "a si neux": "acineux",
    "la si neux": "acineux",
    "mucineu": "mucineux",
    "mucineuse": "mucineuse",
    "endo métri oïde": "endométrioïde",
    "endométri oïde": "endométrioïde",
    "en dos métri oïde": "endométrioïde",
    "can a l'anal": "canal anal",
    "canal-anal": "canal anal",
    "en vaillé": "envahies",
    "en vaillée": "envahies",
    "en vahi": "envahi",
    "envaillée": "envahie",
    "en vaille": "envahie",
    "marge en vaillée": "marge envahie",
    "marges en vaillées": "marges envahies",
    "tanjante": "tangente",
    "tangent": "tangente",

    # ── Sigles et marqueurs mal transcrits ────────────────────────────────
    "p16": "p16",
    "pé 16": "p16",
    "P 16": "p16",
    "her-2": "HER2",
    "her 2": "HER2",
    "air 2": "HER2",
    "ère 2": "HER2",
    "cade": "CDX2",
    "cdx 2": "CDX2",
    "cd x 2": "CDX2",
    "c d x 2": "CDX2",
    "ck sept": "CK7",
    "ck 7": "CK7",
    "ck vingt": "CK20",
    "ck 20": "CK20",
    "ck 5/6": "CK5/6",
    "ck cinq six": "CK5/6",
    "ki 67": "Ki-67",
    "qui 67": "Ki-67",
    "qui soixante sept": "Ki-67",
    "ki soixante sept": "Ki-67",
    "khi 67": "Ki-67",
    "ttf 1": "TTF1",
    "tt f1": "TTF1",
    "t t f 1": "TTF1",
    "alf": "ALK",
    "pdl 1": "PD-L1",
    "pd l1": "PD-L1",
    "pdl1": "PD-L1",
    "pd-l 1": "PD-L1",
    "pd l 1": "PD-L1",
    "ros 1": "ROS1",
    "mlh 1": "MLH1",
    "msh 2": "MSH2",
    "msh 6": "MSH6",
    "pms 2": "PMS2",
    "cd 3": "CD3",
    "cd 20": "CD20",
    "cd vingt": "CD20",
    "cd 34": "CD34",
    "cd 117": "CD117",
    "braf": "BRAF",
    "b-raf": "BRAF",
    "b raf": "BRAF",
    "cas ras": "KRAS",
    "k ras": "KRAS",
    "nrass": "NRAS",
    "n ras": "NRAS",
    "e g f r": "EGFR",
    "i d h 1": "IDH1",
    "i d h 2": "IDH2",
    "i n i 1": "INI1",
    "pax 8": "PAX8",
    "pacs 8": "PAX8",
    "socks 10": "SOX10",
    "sox 10": "SOX10",
    "s 100": "S100",
    "s cent": "S100",
    "gâta 3": "GATA3",
    "gata 3": "GATA3",
    "a m a c r": "AMACR",
    "amacre": "AMACR",
    "wt 1": "WT1",
    "er g": "ERG",
    "dog 1": "DOG1",

    # ── Scores et éponymes mal transcrits ─────────────────────────────────
    "glison": "Gleason",
    "glisson": "Gleason",
    "gleeson": "Gleason",
    "gleasson": "Gleason",
    "brezlow": "Breslow",
    "breslo": "Breslow",
    "furman": "Fuhrman",
    "fuhrmann": "Fuhrman",
    "not in femme": "Nottingham",
    "nottingam": "Nottingham",
    "notingham": "Nottingham",
    "elstonellis": "Elston-Ellis",
    "elston elis": "Elston-Ellis",
    "scarf bloom richardson": "Scarff-Bloom-Richardson",
    "sbr": "SBR",

    # ── Corrections anatomiques et techniques ─────────────────────────────
    "exentéranée": "extemporané",
    "exentérané": "extemporané",
    "extemporannée": "extemporané",
    "extemp": "extemporané",
    "imuno": "immuno",
    "im uno": "immuno",
    "éritroplasie": "érythroplasie",
    "calcifié": "calcifié",
    "peaux de planing": "podoplanine",
    "podaux planing": "podoplanine",
    "podo planing": "podoplanine",
    "podo planine": "podoplanine",
    "calrétinin": "calrétinine",
    "désmine": "desmine",
    "dès mine": "desmine",
    "miogénine": "myogénine",
    "myo génine": "myogénine",
    "formaule": "formule",
    "colique gauche": "colique gauche",
    "ziel nelson": "Ziehl-Neelsen",
    "ziehl nelson": "Ziehl-Neelsen",
    "zièle nelsen": "Ziehl-Neelsen",
    "groco": "Grocott",
    "grosso": "Grocott",
    "grocau": "Grocott",
    "papanicolao": "Papanicolaou",
    "papanicolau": "Papanicolaou",
}

# ---------------------------------------------------------------------------
# C. ACRONYMES DIAGNOSTIQUES
# ---------------------------------------------------------------------------
# Expansion des abréviations orales vers le texte complet du compte-rendu.
# ---------------------------------------------------------------------------


ACRONYMES_DIAGNOSTIQUES: dict[str, str] = {
    "ADK": "adénocarcinome",
    "CE": "carcinome épidermoïde",
    "CPC": "carcinome à petites cellules",
    "CGC": "carcinome à grandes cellules",
    "CNE": "carcinome neuroendocrine",
    "TNE": "tumeur neuroendocrine",
    "LBDGC": "lymphome B diffus à grandes cellules",
    "LF": "lymphome folliculaire",
    "LM": "lymphome du manteau",
    "LZM": "lymphome de la zone marginale",
    "LH": "lymphome de Hodgkin",
    "LNH": "lymphome non hodgkinien",
    "LLC": "leucémie lymphoïde chronique",
    "CIS": "carcinome in situ",
    "CCIS": "carcinome canalaire in situ",
    "CLIS": "carcinome lobulaire in situ",
    "ADK LI": "adénocarcinome de type intestinal selon Lauren",
    "ADK LD": "adénocarcinome de type diffus selon Lauren",
    "CHC": "carcinome hépatocellulaire",
    "CCA": "cholangiocarcinome",
    "GIST": "tumeur stromale gastro-intestinale",
    "GBM": "glioblastome",
    "MF": "mycosis fungoïde",
    "DFSP": "dermatofibrosarcome de Darier-Ferrand",
    "IHC": "immunohistochimie",
    "HES": "hématoxyline-éosine-safran",
    "HE": "hématoxyline-éosine",
    "PAS": "acide periodique de Schiff",
    "LBA": "lavage broncho-alvéolaire",
    "LCR": "liquide céphalo-rachidien",
    "DPC": "duodéno-pancréatectomie céphalique",
    "PE": "pièce d'exérèse",
    "PO": "pièce opératoire",
    "GS": "ganglion sentinelle",
    "BOM": "biopsie ostéo-médullaire",
    "SBR": "Scarff-Bloom-Richardson",
    "ISUP": "International Society of Urological Pathology",
    "TNM": "classification TNM",
    "pTNM": "classification TNM pathologique",
    "ypTNM": "classification TNM pathologique après traitement néoadjuvant",
    "TRG": "score de régression tumorale",
    "FIGO": "Fédération Internationale de Gynécologie et d'Obstétrique",
    "OMS": "Organisation Mondiale de la Santé",
    "AJCC": "American Joint Committee on Cancer",
    "UICC": "Union for International Cancer Control",
    "ITC": "cellules tumorales isolées",
    "LVI": "invasion lympho-vasculaire",
    "PNI": "invasion péri-nerveuse",
    "EPN": "engainement péri-nerveux",
    "dMMR": "déficience du système de réparation des mésappariements",
    "pMMR": "système de réparation des mésappariements conservé",
    "MSI": "instabilité des microsatellites",
    "MSI-H": "instabilité des microsatellites de haut niveau",
    "MSS": "microsatellites stables",
    "FISH": "hybridation in situ en fluorescence",
    "CISH": "hybridation in situ chromogénique",
    "NGS": "séquençage de nouvelle génération",
    "PCR": "réaction de polymérisation en chaîne",
    "TILs": "lymphocytes infiltrant la tumeur",
    "CIN": "néoplasie intra-épithéliale cervicale",
    "LSIL": "lésion malpighienne intra-épithéliale de bas grade",
    "HSIL": "lésion malpighienne intra-épithéliale de haut grade",
    "ASC-US": "atypies des cellules malpighiennes de signification indéterminée",
    "ASC-H": "atypies des cellules malpighiennes ne permettant pas d'exclure une lésion de haut grade",
    "AGC": "atypies des cellules glandulaires",
    "AIS": "adénocarcinome in situ",
    "PIN": "néoplasie intra-épithéliale prostatique",
    "UMP": "potentiel de malignité incertain",
}

# ---------------------------------------------------------------------------
# D. MARQUEURS IHC – EXPANSION
# ---------------------------------------------------------------------------
# Transforme les résultats oraux (ex. « TTF1 positif ») en formulations
# standardisées pour le compte-rendu.
# ---------------------------------------------------------------------------

MARQUEURS_IHC_EXPANSION: dict[str, str] = {
    # Marqueurs pulmonaires
    "TTF1+": "expression nucléaire de TTF1",
    "TTF1-": "absence d'expression de TTF1",
    "CK7+": "expression de CK7",
    "CK7-": "absence d'expression de CK7",
    "CK20+": "expression de CK20",
    "CK20-": "absence d'expression de CK20",
    "p40+": "expression nucléaire de p40",
    "p40-": "absence d'expression de p40",
    "Napsin A+": "expression cytoplasmique de Napsin A",
    # Marqueurs digestifs
    "CDX2+": "expression nucléaire de CDX2",
    "CDX2-": "absence d'expression de CDX2",
    "CK19+": "expression de CK19",
    # Marqueurs mammaires
    "RE+": "expression des récepteurs aux oestrogènes",
    "RE-": "absence d'expression des récepteurs aux oestrogènes",
    "RP+": "expression des récepteurs à la progestérone",
    "RP-": "absence d'expression des récepteurs à la progestérone",
    "HER2+": "surexpression de HER2 (score 3+)",
    "HER2-": "absence de surexpression de HER2 (score 0 ou 1+)",
    "HER2 2+": "expression équivoque de HER2 (score 2+), FISH recommandée",
    "Ki67 élevé": "indice de prolifération Ki-67 élevé",
    "Ki67 faible": "indice de prolifération Ki-67 faible",
    "GCDFP15+": "expression de GCDFP-15",
    "Mammaglobine+": "expression de la mammaglobine",
    "GATA3+": "expression nucléaire de GATA3",
    # Marqueurs prostatiques
    "PSA+": "expression de PSA",
    "AMACR+": "expression de AMACR/P504S",
    "P504S+": "expression de P504S/AMACR",
    "ERG+": "expression nucléaire de ERG",
    "NKX3.1+": "expression nucléaire de NKX3.1",
    "p63+": "expression nucléaire de p63 (cellules basales présentes)",
    "p63-": "absence d'expression de p63 (perte des cellules basales)",
    "CK5/6+": "expression de CK5/6 (cellules basales présentes)",
    # Marqueurs mélanocytaires
    "S100+": "expression de S100",
    "S100-": "absence d'expression de S100",
    "HMB45+": "expression de HMB-45",
    "HMB45-": "absence d'expression de HMB-45",
    "Melan-A+": "expression de Melan-A/MART-1",
    "Melan-A-": "absence d'expression de Melan-A",
    "SOX10+": "expression nucléaire de SOX10",
    # Marqueurs neuroendocrines
    "Chromogranine+": "expression de la chromogranine A",
    "Synaptophysine+": "expression de la synaptophysine",
    "CD56+": "expression de CD56",
    "INSM1+": "expression nucléaire d'INSM1",
    # Marqueurs lymphoïdes
    "CD3+": "expression de CD3 (phénotype T)",
    "CD20+": "expression de CD20 (phénotype B)",
    "CD30+": "expression de CD30",
    "CD15+": "expression de CD15",
    "CD45+": "expression de CD45 (antigène leucocytaire commun)",
    # Marqueurs mésothéliaux
    "Calrétinine+": "expression nucléaire et cytoplasmique de la calrétinine",
    "D2-40+": "expression de D2-40/podoplanine",
    "WT1+": "expression nucléaire de WT1",
    # Marqueurs MSI/MMR
    "MLH1-": "perte d'expression de MLH1",
    "MSH2-": "perte d'expression de MSH2",
    "MSH6-": "perte d'expression de MSH6",
    "PMS2-": "perte d'expression de PMS2",
    "MLH1+": "conservation de l'expression de MLH1",
    "MSH2+": "conservation de l'expression de MSH2",
    "MSH6+": "conservation de l'expression de MSH6",
    "PMS2+": "conservation de l'expression de PMS2",
    # Marqueurs gynécologiques
    "PAX8+": "expression nucléaire de PAX8",
    "WT1+ (gynéco)": "expression nucléaire de WT1 (phénotype séreux)",
    "p53 aberrant": "expression aberrante de p53 (mutation probable)",
    "p53 wild-type": "expression de type sauvage de p53",
    "p16 bloc+": "expression en bloc de p16 (surexpression)",
    "p16-": "absence d'expression de p16",
    # Marqueurs hépatiques
    "Glypican-3+": "expression de Glypican-3",
    "Arginase-1+": "expression d'Arginase-1",
    "Hépar1+": "expression de Hépar-1",
    # Marqueurs GIST
    "DOG1+": "expression de DOG1",
    "CD117+": "expression de CD117/c-KIT",
    "CD34+": "expression de CD34",
    # Marqueurs musculaires
    "Desmine+": "expression de la desmine",
    "Myogénine+": "expression nucléaire de la myogénine",
    "SMA+": "expression de l'actine muscle lisse",
    # Autres marqueurs importants
    "PD-L1+": "expression de PD-L1",
    "ALK+": "expression de ALK",
    "BRAF V600E+": "expression de la protéine BRAF V600E mutée",
    "INI1-": "perte d'expression d'INI1/SMARCB1",
    "INI1+": "conservation de l'expression d'INI1",
    "BRG1-": "perte d'expression de BRG1/SMARCA4",
    "H3K27me3-": "perte d'expression de H3K27me3",
    "EMA+": "expression de l'EMA (antigène de membrane épithéliale)",
    "Cycline D1+": "expression nucléaire de Cycline D1",
    "BCL2+": "expression de BCL2",
    "BCL6+": "expression nucléaire de BCL6",
    "MUM1+": "expression nucléaire de MUM1/IRF4",
    "TdT+": "expression nucléaire de TdT",
    "CD10+": "expression de CD10",
    "CD138+": "expression de CD138",
    "Vimentine+": "expression de la vimentine",
    "Beta-caténine nucléaire": "expression nucléaire aberrante de la bêta-caténine",
}

# ---------------------------------------------------------------------------
# E. NÉGATIONS STANDARDISÉES
# ---------------------------------------------------------------------------
# Transforme les formulations orales de négation en formulations de
# compte-rendu standardisées.
# ---------------------------------------------------------------------------

NEGATIONS_STANDARDISEES: dict[str, str] = {
    "pas de tumeur": "absence de prolifération tumorale",
    "pas de malignité": "absence de signe de malignité",
    "pas de cancer": "absence de prolifération carcinomateuse",
    "pas de carcinome": "absence de carcinome",
    "pas d'adénocarcinome": "absence d'adénocarcinome",
    "pas de lymphome": "absence de prolifération lymphomateuse",
    "pas de sarcome": "absence de prolifération sarcomateuse",
    "pas de métastase": "absence de métastase",
    "pas de méta": "absence de métastase",
    "pas d'emboles": "absence d'emboles vasculaires et lymphatiques",
    "pas d'embole": "absence d'emboles vasculaires et lymphatiques",
    "pas d'engainement": "absence d'engainement péri-nerveux",
    "pas d'engainement périnerveux": "absence d'engainement péri-nerveux",
    "pas d'invasion vasculaire": "absence d'invasion vasculaire",
    "pas d'invasion périnerveuse": "absence d'invasion péri-nerveuse",
    "pas de nécrose": "absence de nécrose",
    "pas de granulome": "absence de granulome",
    "pas de fibrose": "absence de fibrose significative",
    "pas de dysplasie": "absence de dysplasie",
    "pas d'atypie": "absence d'atypie cytonucléaire significative",
    "pas d'atypies": "absence d'atypies cytonucléaires significatives",
    "pas de mitose": "absence d'activité mitotique significative",
    "pas de mitoses": "absence d'activité mitotique significative",
    "pas d'effraction capsulaire": "absence d'effraction capsulaire",
    "pas de rupture capsulaire": "absence de rupture capsulaire",
    "pas de dépassement capsulaire": "absence de franchissement capsulaire",
    "marges saines": "limites de résection en zone saine (R0)",
    "marges ok": "limites de résection en zone saine (R0)",
    "marges libres": "limites de résection en zone saine (R0)",
    "pas d'envahissement des marges": "limites de résection en zone saine (R0)",
    "pas de résidu": "absence de résidu tumoral",
    "pas de résidu tumoral": "absence de résidu tumoral",
    "ganglions négatifs": "absence de métastase ganglionnaire",
    "ganglions indemnes": "absence de métastase ganglionnaire",
    "pas de ganglion envahi": "absence de métastase ganglionnaire",
    "pas de ganglion métastatique": "absence de métastase ganglionnaire",
    "pas d'anomalie": "absence d'anomalie histologique significative",
    "rien de particulier": "absence d'anomalie histologique significative",
    "ras": "absence d'anomalie histologique significative",
    "rien à signaler": "absence d'anomalie histologique significative",
    "pas de signe de malignité": "absence de signe histologique de malignité",
    "bénin": "lésion de nature bénigne, absence de signe de malignité",
    "pas de lésion": "absence de lésion histologique significative",
    "pas de cellule tumorale": "absence de cellule tumorale identifiable",
    "pas de cellules tumorales": "absence de cellules tumorales identifiables",
    "pas de cellule suspecte": "absence de cellule suspecte de malignité",
    "pas d'infiltration": "absence d'infiltration tumorale",
    "pas de récidive": "absence de signe histologique de récidive tumorale",
    "pas de transformation": "absence de signe de transformation",
    "pas de calcification": "absence de calcification",
    "pas de stéatose": "absence de stéatose hépatique",
    "pas de micro-invasion": "absence de micro-invasion",
}


# ---------------------------------------------------------------------------
# FONCTIONS EXPORTÉES
# ---------------------------------------------------------------------------

def get_wordboost_prompt() -> str:
    """Retourne le prompt WordBoost complet (usage interne / futur STT compatible).

    Contient l'ensemble du vocabulaire ACP pour les moteurs STT qui
    supportent un prompt textuel libre (ex. OpenAI Whisper).
    Pour Voxtral, utiliser ``get_context_bias()`` à la place.
    """
    return WORDBOOST_PROMPT


# ---------------------------------------------------------------------------
# CONTEXT BIAS — Top 100 termes pour Voxtral context_bias
# ---------------------------------------------------------------------------
# Voxtral accepte max ~100 mots/phrases via le paramètre context_bias.
# On sélectionne les termes les plus fréquemment mal reconnus en STT
# médical francophone, classés par criticité clinique.
# ---------------------------------------------------------------------------

CONTEXT_BIAS_TERMS: list[str] = [
    # Marqueurs IHC (très souvent mal transcrits - priorité 1)
    "TTF1", "ALK", "PD-L1", "Ki67",
    "HER2", "CK7", "CK20", "CK5/6", "CDX2", "p16", "p40", "p63", "p53",
    "GATA3", "PAX8", "SOX10", "Melan-A", "HMB45",
    "AMACR", "P504S", "PSA", "NKX3.1", "ERG",
    "Chromogranine", "Synaptophysine",
    "RE", "RP", "MLH1", "MSH2", "MSH6", "PMS2",
    "BRAF", "KRAS", "NRAS", "EGFR", "ROS1",
    "Desmine", "DOG1", "BCL2", "Calrétinine",
    # Éponymes/Scores (critiques pour le sens clinique)
    "Gleason", "ISUP", "Scarff-Bloom-Richardson", "SBR",
    "Breslow", "Clark", "Fuhrman", "Nottingham",
    "pTNM", "FIGO", "METAVIR",
    # Termes techniques fréquemment mal transcrits (mots simples uniquement)
    "adénocarcinome", "carcinome", "épidermoïde", "urothélial",
    "mélanome", "mésothéliome", "lymphome",
    "acineux", "lépidique", "papillaire", "micropapillaire", "cribriforme",
    "trabéculaire", "mucineux", "desmoplasique",
    "koïlocytes", "dyskératose", "parakératose", "acanthose",
    "stroma", "fibro-hyalin", "myxoïde",
    # Anatomie critique
    "bronchique", "hilaire", "parenchymateuse", "périnerveux",
    "lymphovasculaire", "ganglionnaire",
    # Prélèvements
    "lobectomie", "mastectomie", "prostatectomie",
    "néphrectomie", "colectomie", "gastrectomie",
    "thyroïdectomie", "hystérectomie", "cystectomie",
    # Cytologie LBA
    "sidérophages", "polynucléaires", "neutrophiles", "éosinophiles",
    # Néoplasies intraépithéliales
    "AIN3", "CIN3",
    # Biologie moléculaire
    "FISH", "NGS",
    "IDH1", "ATRX", "H3K27M",
]


def get_context_bias() -> list[str]:
    """Retourne la liste des termes pour le context_bias Voxtral.

    Maximum ~100 termes, sélectionnés parmi les plus fréquemment
    mal reconnus en transcription médicale ACP francophone.
    """
    return CONTEXT_BIAS_TERMS


def corriger_phonetique(texte: str) -> str:
    """Applique toutes les corrections phonétiques sur un texte brut.

    La recherche est insensible à la casse. Les corrections sont
    appliquées dans l'ordre décroissant de longueur de la clé pour
    éviter les remplacements partiels (« branchique » est traité
    avant « yaline »).

    Parameters
    ----------
    texte:
        Texte brut issu de la transcription STT.

    Returns
    -------
    str
        Texte avec les corrections phonétiques appliquées.
    """
    # Trier par longueur décroissante de clé pour traiter les expressions
    # les plus longues en premier (ex. "marge en vaillée" avant "en vaillée").
    corrections_triees: list[tuple[str, str]] = sorted(
        CORRECTIONS_PHONETIQUES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    resultat: str = texte
    for erreur, correction in corrections_triees:
        # Recherche insensible à la casse avec préservation des limites de mots
        # quand la clé commence/finit par un caractère alphanumérique.
        motif: str = re.escape(erreur)
        if erreur[0].isalnum():
            motif = r"\b" + motif
        if erreur[-1].isalnum():
            motif = motif + r"\b"
        resultat = re.sub(motif, correction, resultat, flags=re.IGNORECASE)

    return resultat


def expand_acronyme(acronyme: str) -> str | None:
    """Retourne l'expansion d'un acronyme diagnostique ou None si inconnu.

    La recherche est d'abord exacte, puis insensible à la casse.

    Parameters
    ----------
    acronyme:
        Sigle ou abréviation à développer (ex. « ADK », « IHC »).

    Returns
    -------
    str | None
        Texte complet correspondant, ou ``None`` si l'acronyme n'est
        pas référencé.
    """
    # Recherche exacte
    if acronyme in ACRONYMES_DIAGNOSTIQUES:
        return ACRONYMES_DIAGNOSTIQUES[acronyme]

    # Recherche insensible à la casse
    acronyme_upper: str = acronyme.upper()
    for cle, valeur in ACRONYMES_DIAGNOSTIQUES.items():
        if cle.upper() == acronyme_upper:
            return valeur

    return None
