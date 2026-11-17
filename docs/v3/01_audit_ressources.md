# MARC v3 — Audit des ressources métier (PO-1)

Périmètre : toutes les ressources métier du dépôt `Demo_anapath` (branche `projet-v3`).
Date de l'audit : 15/11/2026. Méthode : lecture des fichiers (python/openpyxl, `textutil` pour .doc/.docx/.rtf, `pdftotext`), comptages mécaniques et recoupements croisés entre ressources. Les audios n'ont pas été ouverts (seule leur taille est relevée).

Légende de fiabilité utilisée partout :

| Note | Sens |
|---|---|
| A | Référentiel officiel, versionné, source identifiable (ANS, ADICAP) |
| B | Savoir-faire d'un praticien identifié, cohérent mais non relu ni versionné |
| C | Synthèse secondaire ou dérivée automatiquement, à vérifier avant usage |
| D | Non vérifiable, ou contient des défauts avérés |

---

## 0. Synthèse en 12 points

1. **Le socle réellement exploitable est solide sur trois axes** : ADICAP officiel 2024-10 (A), formulations de référence d'un praticien (B, environ 650 textes ingérés), 23 gabarits INCa en code (B/C). Le reste est mince, absent ou non structuré.
2. **Problème de conformité à traiter avant toute chose** : 13 fichiers de `Modèles CR` contiennent des identifiants directs de patients (nom, date de naissance, NIP, n° d'examen, parfois RPPS du médecin), et **3 entrées de `backend/data/textes_canoniques.json` en portent encore** (lignes `Patient : … né(e) le … NIP …`). Ce fichier est déployé sur Render et injecté dans les prompts envoyés au LLM. À purger et à bloquer par un scan PII à l'ingestion (section 5.1).
3. **SNOMED CT n'a aucune ressource dans le dépôt** : pas de release, pas de fichier de terminologie. `snomed.py` contient 25 structures anatomiques et 19 morphologies saisies à la main, un seul code retourné par rapport, aucune vérification possible contre une édition officielle. Statut : à traiter comme « suggestion non validée ».
4. **Pas de lexique de variantes phonétiques** : `vocabulaire_acp.py` ne contient que 101 termes de biais Voxtral (sans variantes). La table de corrections phonétiques a été retirée du code et déléguée au LLM. Il n'existe aucune transcription brute de référence des 5 audios, donc aucun moyen de mesurer ni d'alimenter les erreurs STT réelles.
5. **Champs obligatoires** : 23 organes, 237 champs (223 obligatoires). Pas de matrice explicite organe x type de prélèvement : le filtrage biopsie / pièce / infiltrant se fait par listes de mots dans `specimen_type.py`, indépendamment de l'organe. `vesicule_biliaire` et `appendice` n'ont que 2 champs chacun.
6. **Couverture d'organes** : 23 organes tumoraux contre 181 modèles Impulsion ACP référencés (liste de noms uniquement, contenu absent). Aucun gabarit pour la pathologie non tumorale (MICI, gastrite, greffe, PID...), la cytologie (LBA, FCU, urines, liquides) ni plusieurs organes (thymus, os, peau non mélanique, surrénale, parathyroïde, voies biliaires, grêle/GIST, plèvre/mésothéliome, vulve/vagin, pénis/voies excrétrices, cœur/vaisseaux, œil, placenta, moelle/rate). Détail section 4.
7. **Perte à l'ingestion de la bible Excel** : 5 feuilles sur 20 (SEIN, DERMATO, OS-ARTI, T mous, NEURO, soit environ 200 textes) n'ont jamais été ingérées, parce que le script suppose une disposition à 4 colonnes. De même 42 modèles CR sur 106 (vasculaire, cardiaque, digestif, ganglions) ont été écartés faute de préfixe reconnu.
8. **Codes ADICAP des bibles** : 100 % des 306 codes lésionnels du catalogue existent dans le thésaurus 2024-10 et aucun n'est obsolète (recoupement fait). En revanche 59 % des codes de la bible ne portent que la partie lésion (4 caractères), et le catalogue n'a que 57 des 156 codes organe D3 à deux lettres (manquent par exemple DR rectum, DG grêle, FP pancréas exocrine, ES surrénale, EP parathyroïde, FE voies biliaires).
9. **Règles de cohérence (unités, incohérences)** : aucune ressource déclarative. Elles vivent uniquement dans le code (`coherence.py`, `guardrails.py` 1 226 lignes, `numbers.py`). Pour la v3 il faut un catalogue de règles versionné et testable (proposé en section 7).
10. **Corpus d'évaluation trop petit** : 5 couples audio + CR (2 poumon, 1 lobectomie avec curages, 2 canal anal), dupliqués à l'identique dans `corpus/` et `Ressources/2.`. Suffisant pour une démo, pas pour mesurer une promesse « 10x plus rapide ».
11. **Doublons et dérive de copie** : corpus = Ressources (octet pour octet), `Codage_D1_D2_table.json` = `backend/data/codage_d1_d2.json` (identiques aujourd'hui, `sync_referentiels.py` en garantit le sens), deux versions différentes de la fiche CGTS, ZIP ADICAP + dossier extrait (10 Mo en double).
12. **Repli gracieux** : chaque source manquante doit dégrader la sortie d'un niveau (code partiel, trou, gabarit générique), jamais bloquer. Table de repli en section 8, appuyée sur le schéma de la section 7.

---

## 1. Inventaire par ressource

### 1.1 `Ressources/1. Codes Bible/Bibles Greg.xlsx` (245 Ko, 20 feuilles)

**Contenu.** Bible personnelle d'un pathologiste : une ligne = un prélèvement/une lésion avec (topographie, libellé lésion, code ADICAP partiel, texte de référence macro + micro + conclusion). Les textes comportent des `#` à remplir (valeurs à dicter).

**Volume.** Environ 920 lignes non vides (en-têtes compris). Environ 590 lignes avec un code, environ 264 avec au moins un `#`.

| Feuille | Lignes ~ | Particularité | Ingérée dans `textes_canoniques.json` |
|---|---|---|---|
| DIG | 172 | Anus, appendice, colo-rectal, estomac, duodénum, foie, grêle, pancréas, vésicule, péritoine | oui (159) |
| BDig | 16 | 2 colonnes : macros de modèles (polypes, digestif haut) | non |
| URO | 70 | Prostate, vessie, rein, testicule, épididyme, pénis, uretère | oui (59) |
| GYN | 111 | Col, endomètre, ovaire, trompe, vulve, vagin | oui (104) |
| DERMATO | 118 | Lésion en colonne 1, code en 2, texte en 3 (disposition différente) | **non** |
| CR | 12 | Blocs standard : IHC, extemporanée | non (volontaire) |
| CYTO | 42 | Articulaire, ascite, aspiration bronchique, ganglion, LBA, LCR, plèvre, thyroïde, urine | oui (40) |
| Cyto FCU | 18 | Frottis cervico-utérins Bethesda, codes ADICAP presque tous renseignés | oui (17) |
| SEIN | 20 | 3 colonnes | **non** |
| FOETO-P | 7 | Placenta, fausses couches, môle | oui (2) |
| ORL | 140 | Amygdale, bouche, larynx, naso-sinusien, glandes salivaires, oreille | oui (131) |
| THO | 13 | Poumon uniquement | oui |
| ENDOC | 33 | Parathyroïde, surrénale, thymus, thyroïde | oui (31) |
| OS-ARTI | 37 | 3 colonnes | **non** |
| HEMATO | 56 | Moelle, ganglion, lymphomes, rate, peau ; 8 colonnes | partiel (15) |
| T mous | 19 | 3 colonnes | **non** |
| CV | 20 | Aorte, BAT, endartériectomie, myocarde, valve | oui (16) |
| NEURO | 14 | 3 colonnes | **non** |
| OPH | 9 | Œil, DCR | oui (6) |
| M, Feuil1 | 2, 1 | Brouillons | non |

**Qualité.** Rédaction homogène (un seul auteur de référence), style très « fini ». Défauts relevés : codes saisis de façon hétérogène (`DQ 4554`, `4558`, `A7A0`, `E5S2-3`, `7410/7332`, un code à 14 caractères), doublons d'(organe, lésion) (31 couples dans le JSON), texte à `#` (29 % des textes ingérés, 191 sur 653), cellules multi-lignes dans la colonne code (`VA 4411 anévrisme athérosclérotique`).

**Fiabilité : B.** Praticien unique, non versionné, non daté, aucune trace de relecture. Les codes ne sont pas validés par rapport à une édition précise du thésaurus, hormis le recoupement de la section 1.7.

**Lacunes.** Pas de champs obligatoires par organe, pas de distinction biopsie/pièce explicite (déductible du libellé seulement), peu de mesures chiffrées exemplaires, SEIN et DERMATO (organes fréquents) non exploités.

**Usage recommandé.**
- Exemples de style et gabarits à trous (le `#` devient un slot typé).
- Code ADICAP candidat (jamais définitif sans validation).
- Alimenter le lexique canonique (libellés de lésions) et les variantes d'écriture.
- Corriger l'ingestion pour récupérer les 5 feuilles perdues avant tout autre chantier (gain immédiat d'environ 200 textes).

### 1.2 `Ressources/1. Codes Bible/Codes Bible.doc` (75 Ko, 34 000 caractères)

**Contenu.** Texte long organisé par organe : amygdale, carcinome malpighien ORL, colite (RCH grades de Nancy), dermatologie (kératose, Bowen, Koenen...), fibroadénome du sein, carcinome urothélial de vessie. Chaque entrée : code ADICAP complet + libellé + paragraphe + conclusion (46 « CONCLUSION »).

**Volume.** 52 entrées avec code (`AA0000`, `AA7600B`, `ZDC7915A`, `UVU7A0M3`...).

**Qualité.** Sections RCH dupliquées à l'identique (deux blocs de 9 entrées). Suffixes alphabétiques de variantes (`AA7600A`, `AA7600B`...) non standard ADICAP : ce sont des numéros internes au praticien, pas du thésaurus. Pas de champ structuré, pas d'IHC.

**Fiabilité : B** pour la rédaction, **C** pour les codes avec suffixe (non officiels).

**Lacunes.** Couverture très inégale (ORL surreprésenté), pas de donnée minimale, pas ingéré dans le backend (aucune référence dans `scripts/`).

**Usage recommandé.** Source secondaire d'exemples de style (ORL, RCH), déduplication préalable, et extraction des codes pour recoupement avec ADICAP 2024-10.

### 1.3 `Ressources/1. Codes Bible/Modèles CR/` (106 fichiers : 94 .docx, 12 .doc)

**Contenu.** Ce ne sont pas des comptes rendus complets mais des **raccourcis de saisie** : le nom du fichier est l'abréviation (`BB Kepi` = biopsie bronchique + carcinome épidermoïde), le contenu est le texte à produire. Répartition par préfixe : EBUS 14, LOBE 13, BB 12, PSS 8, PLEVRE 8, vasculaire (ANEVRISME, AORTE, athérome) 10, digestif (DD/DE/DG/DC/DR) 15, myocarde 5, thymome 3, divers (goitre, ganglion, lymphome, IDYLLA, courriers réseau).

**Qualité.** Très bon pour le thorax (environ 85 % du lot), textes courts et normalisés, proches d'un vrai CR final. Abréviations idiosyncratiques (`Kepi`, `KGC`, `PSS`, `LSD`, `LID`, `LM`, `MDH`) : ce sont des termes de lexique à capitaliser.

**Défauts avérés.**
- **13 fichiers contiennent des données patient directes** (11 avec une ligne `Patient : NOM Prénom né(e) le JJ/MM/AAAA - NIP ...` ou n° d'examen, 2 courriers de réseau MESOPATH/LYMPHOPATH avec nom, date de naissance, n° dossier, RPPS et coordonnées du médecin). Aucun nom n'est reproduit dans ce rapport.
- Le script `ingest_modeles_cr.py` n'a repris que 64 fichiers sur 106 (préfixes reconnus : BB, BTB, EBUS, LOBE, PSS, TEP, PLEVRE, LIQ, THYMOME). Écartés : 42 (vasculaire, myocarde, digestif DD/DE/DG/DC, ganglion/lymphome, goitre, sténose trachée, courriers).
- Coquilles dans les noms (`Biopssie`, `Métaplsie`, `PLEBRE`, `Hyprplasique`), sans impact sur le contenu mais à normaliser.
- Peu de codes ADICAP (7 sur 73 entrées THO du JSON ont un code).

**Fiabilité : B** (contenu), **D** pour les 13 fichiers contenant des identifiants tant qu'ils ne sont pas anonymisés.

**Usage recommandé.** Gabarits thoraciques à trous, exemples de style par type de prélèvement (EBUS, biopsie, lobectomie, plèvre), lexique d'abréviations du praticien. Les 42 modèles non ingérés sont à traiter par famille, après anonymisation.

### 1.4 `Ressources/1. Codes Bible/Bibles HML/` (13 .docx, ~40 000 caractères)

**Contenu.** Bibles thématiques d'un second service (HML) : BAT (biopsie d'artère temporale), BGSA (glandes salivaires accessoires, score de Chisholm), biopsies coliques et gastriques, EBUS, emphysème, endartériectomie pulmonaire, FV DA (appendicectomie), hyperplasie neuroendocrine, PID (pneumopathies interstitielles, critères de la PIC), poumons natifs, thymus (thymome/Masaoka), trachée.

**Qualité.** Mélange de textes finaux et de grilles descriptives (critères diagnostiques en puces). Deux fichiers (EBUS, biopsies coliques) comportent des lignes de signature électronique avec date et nom du médecin.

**Fiabilité : B.** **Non ingéré** dans le backend (aucune référence dans le code ou les scripts).

**Lacunes.** Aucun code ADICAP (sauf en-têtes `G H SG ...` ponctuels), aucune donnée minimale.

**Usage recommandé.** Gabarits non tumoraux et pathologie médicale (PID, emphysème, greffe, BAT) qui manquent aux 23 templates tumoraux. Les grilles de critères (PIC, Chisholm, Masaoka) alimentent les règles de cohérence et les champs de type score.

### 1.5 Dossiers par spécialité de `1. Codes Bible/`

| Dossier | Fichiers | Contenu et remarques |
|---|---|---|
| `1. Thorax/1. Poumon/` | 5 | `Bibles Thorax.docx` (83 000 caractères, environ 57 exemples nominatifs de pathologistes : « Exemple (Vincent) », « (Riad) »), Biopsies, Aspirations bronchiques, LBA, Pièces opératoires. Ressource la plus riche du lot : grilles de curage par loge, immuno, PD-L1. |
| `1. Thorax/Riad ARANA/` | 3 | BIBLE THO internes, RA Poumon internes, RA Wedge internes : **style d'un autre pathologiste**, utile pour montrer la variabilité inter-praticien. |
| `1. Thorax/2. Thymus/`, `3. Coeur/` | 1 (Coeur) | Un seul texte (myxome). Dossier Thymus vide dans l'arborescence. |
| `2. Digestif/` | 4 | Anus (docx), Appendice (rtf), Vésicule biliaire (2 rtf) : macro + micro + conclusion complets. |
| `3. ORL/` | 1 | Glandes salivaires (Sjögren, score de focus). |
| `4. Gynécologie/` | 1 | Endomètre (polype). |
| `5. Hématologie/` | 1 | Lymphomes (microbiopsies médiastinales). |
| `6. Urologie/1. Prostate/` | 1 | Biopsies prostatiques : tableau par site (longueur, Gleason, EPN) : bon modèle de champs structurés répétés. |

Total : environ 20 fichiers de bibles par organe, très inégaux (un seul texte pour cœur, endomètre, prostate, lymphomes). Fiabilité B. Non ingérés (hors Excel).

### 1.6 `Ressources/2. CR avec audio/` et `corpus/`

**Contenu.** 5 audios `.m4a` (465, 484, 905, 139 et 259 Ko, soit 2,25 Mo) et 5 comptes rendus `.docx` correspondants :

| N° | Contenu | Pièges visibles |
|---|---|---|
| 1 | Biopsie pulmonaire, adénocarcinome, IHC TTF-1, PD-L1, ALK | Tableau IHC avec résultats, clone d'anticorps |
| 2 | Biopsies bronchiques + LBA | Deux blocs identiques (1 et 2), clinique « XX » (placeholder), cytologie chiffrée |
| 3 | Lobectomie + curages | 10 stations ganglionnaires par loge (4R, 7, 8, 9, 11, 12, 13), dimensions, numéros de blocs, coquilles (`1à`), n° d'examen dans la clinique |
| 4 | Biopsie marge anale (AIN3, p16) | Texte identique à l'entrée `Anus.docx` de la bible |
| 5 | Biopsies canal anal (2 sites, AIN1) | Multi-prélèvements, koïlocytes, parakératose |

`corpus/audio` et `corpus/cr_reference` sont **identiques octet pour octet** aux dossiers de `Ressources/2.`.

**Qualité.** CR réels du praticien, de bonne qualité, représentatifs de la structure cible (titre, clinique, macro, inclusion, micro, IHC, conclusion). Une date de prélèvement et un n° d'examen apparaissent dans le CR 3 (quasi-identifiants à retirer pour tout partage).

**Fiabilité : B** (un seul praticien). **Lacunes critiques :** pas de transcription brute (donc pas de vérité terrain STT), pas d'annotations de consigne dictée vs rédigée, N = 5 (impossible de mesurer variance, ni de calibrer un temps de saisie comparatif).

**Usage recommandé.** Jeu de test de non-régression de bout en bout, source de variantes phonétiques observées (après transcription Voxtral des 5 audios, à conserver comme `stt_observe`), base pour le banc « 10x plus rapide » (temps de dictée vs temps de saisie). Il faut l'élargir (objectif minimal : 30 dictées couvrant les 10 organes les plus fréquents).

### 1.7 `Ressources/presentation-cr-anapath.pdf` (3 pages)

**Contenu.** Document pédagogique de la pathologiste référente : règle centrale « la structure du CR dépend de (biopsie vs pièce opératoire) x (cancéro vs non cancéro) ». Précise : titre dicté en début de dictée (« examen anatomopathologique d'une biopsie / pièce opératoire de [organe] »), clinique pré-remplie par le secrétariat, macro (nombre/taille des fragments pour une biopsie ; taille, couleur, lésions pour une pièce), inclusion (totalité ou non, numéros de blocs), micro, IHC dictée par le pathologiste (le logiciel ne doit pas deviner les anticorps), conclusion soumise aux mêmes règles que la micro. Références citées : INCa actualisation 2011, CAP Cancer Protocols, Blue Books OMS, PathologyOutlines. Mentionne que le mot « titre » est parfois écrit devant le titre et doit être retiré.

**Fiabilité : A pour les règles métier** (source directe de l'utilisatrice finale). **Usage :** socle des règles du pipeline (orchestrateur : détection biopsie/pièce, cancéro/non cancéro par mots déclencheurs ; interdiction d'inventer des IHC).

### 1.8 `docs/specs/referentiels/` (ADICAP et CGTS)

| Fichier | Contenu | Volume | Fiabilité |
|---|---|---|---|
| `terminologie-adicap-2024-10/dat/ADICAP_2024.xlsx` et `.rdf` | Thésaurus officiel ANS, export 02/10/2024, version 2024-10, licence ouverte 2.0 (réutilisation commerciale permise) | 9 683 lignes, 9 394 codes distincts : D1 20, D2 23, D3 157, D4 2 670, D5 1 989, D6 2 513, D7 521, D8 1 785 ; 201 concepts obsolètes (dont 187 en D5) | **A** |
| `0. ADICAP.pdf` et `dat/ADICAP Version5-04 ... 2009.pdf` | Thésaurus ADICAP v5.04 de 2009 | 238 p. | A (historique, supplanté par 2024-10) |
| `adicap_D4.csv` | Extraction D4 avec chapitre, groupe, libellé normalisé, note de révision | 2 566 lignes, 592 avec note de révision | A (dérivé de l'officiel) |
| `ADICAP Dictionnaire D1.docx`, `D2.docx` | Lexique de déclencheurs lexicaux par code (88 termes D1, 16 codes actifs) fourni par la pathologiste | 3 800 et 2 200 caractères | B (praticienne) |
| `Codage_D1_D2_table.json` (identique à `backend/data/codage_d1_d2.json`) | Table v2.0 : 11 actes simples, 2 familles (biopsie, cytoponction), règles d'exérèse I/O, D2 primaire/secondaire, cardinalité (un code par prélèvement + un par technique), questions de levée de doute (budget 3 par CR) | 19 Ko | **B**, avec entrées `a_valider` explicitement marquées |
| `D1_analyse_et_questions.md` | Analyse mécanique du lexique D1 : I/O indiscernables, code S vide (bug de fusion), 18 inclusions (ordre de test) | 8 Ko | A (analyse) |
| `CGTS_SEM_ADICAP_Fiche-detaillee_v1.3.pdf` et `cgts_sem_adicap_fiche-detaillee.pdf` | Fiche de description ANS | 16 p., **deux fichiers différents** (596 Ko et 620 Ko) | A, à dédupliquer |
| `terminologie-adicap-2024-10.zip` | Archive source | 3,1 Mo (dossier extrait : 7,2 Mo) | doublon |

**Points forts.** Source de vérité unique et licence réutilisable, URI stables, dates de fin de validité (obsolescence gérable), règles de cardinalité conformes aux retours terrain de la V1.
**Lacunes.** (1) D5 (tumoral) n'existe qu'en xlsx, pas de CSV équivalent à `adicap_D4.csv` ; (2) aucune table geste x organe pour trancher I/O (annoncée en proposition) ; (3) code S sans lexique validé ; (4) les entrées `a_valider` (guidage imagerie, macrobiopsie, tru-cut, FCU) ne sont pas encore tranchées ; (5) pas de table lésion-vers-code issue du texte dicté (voir 1.9).

### 1.9 `backend/data/*.json`

| Fichier | Contenu | Chiffres | Fiabilité | Remarque |
|---|---|---|---|---|
| `adicap_ref.json` (744 Ko) | Index positionnel du thésaurus 2024-10 (colonnes uri, code, parent, dictionnaire, libellé, fin_validité, code_anatomie) | 9 683 concepts, 126 anatomies | **A** | Généré par `build_adicap_index.py`, bonne ingénierie (URI comme clé, obsolètes conservés) |
| `adicap_bible.json` (65 Ko) | 57 codes organe D3 avec libellés et mots-clés + catalogue de 306 lésions (cat, organe, lésion, code, kw) | 306 lésions : DIG 73, ORL 73, GYN 45, URO 27, DERMATO 20, HEMATO 13... | **B** | Les 306 codes existent tous dans ADICAP 2024-10, aucun obsolète. Couvre 57 des 156 codes organe D3 |
| `codage_d1_d2.json` (19 Ko) | Voir 1.8 | v2.0 | B | Identique à la copie docs |
| `textes_canoniques.json` (548 Ko) | 653 textes de référence (cat, organe, lésion, code, kw, texte) | THO 73 (dont 60 issus des Modèles CR), DIG 159, ORL 131, GYN 104, URO 59, CYTO 40, ENDOC 31... 447 avec code (68 %), 191 avec `#`, longueur moyenne 632 caractères | **B/D** | **Contient 3 textes avec en-tête patient** (nom, date de naissance, NIP) et 6 avec des dates : à purger |
| `fsus.json` (3 Ko) | Items du questionnaire SUS pour l'étude d'usage | 10 items | A | Hors pipeline de rédaction |

### 1.10 `recherche_standards_anatomopathologie_france.md` (47 Ko, mars 2026)

**Contenu.** Synthèse web : INCa (données minimales 2011, 21 localisations), SFP/CRFS (24 fiches), CNPath, Impulsion ACP (181 modèles listés par référence `M0xxx` et type de prélèvement), ANS (volet CR-ACP v1.5 obsolète depuis 07/2021), structure d'un CR, données minimales détaillées pour sein, côlon-rectum, poumon, prostate, estomac, structure ADICAP (15 caractères), SNOMED CT (situation française, sans codes), CIM-10/CIM-O, TNM, exigences réglementaires, terminologie (types lésionnels, marqueurs IHC, termes macroscopiques) et 35 abréviations.

**Qualité.** Bien organisé, sources citées (URL SFP, INCa, ANS), mais synthèse secondaire sans date d'accès par URL ; données minimales détaillées pour 5 organes seulement ; mention d'une édition INCa 2011 qui n'est plus l'édition de référence pour plusieurs organes (le dépôt n'en conserve ni les PDF ni leur numéro de version).

**Fiabilité : C.** À vérifier point par point avant de la promouvoir en règle : plusieurs seuils (12 ganglions côlon, 16 estomac, seuil RE 10 %) y sont cités sans passage de la source primaire.

**Usage recommandé.** Amorçage du lexique (sections 6.1 et 6.2), liste de modèles Impulsion à cibler en priorité, réservoir de règles de cohérence candidates (à faire valider). Le tableau Impulsion (références M0xxx) doit devenir un champ `impulsion_ref` dans la base.

### 1.11 `regles_metier_anapath.md` (3 Ko)

Document historique, explicitement renvoyé à `docs/ARCHITECTURE.md` et au code. Utile uniquement comme index : 23 organes couverts, sources (INCa, SFP, Impulsion, TNM 8, ADICAP), architecture de correction STT en 2 couches (context bias Voxtral, correction par le LLM). **Fiabilité : B** (à jour au code de juillet 2026). Aucun contenu métier propre.

### 1.12 `backend/templates_organes.py` (164 Ko, ~3 000 lignes)

**Contenu.** 23 `TemplateOrgane` (Pydantic), chacun avec : sous-types de prélèvement, mots-clés de détection, champs obligatoires (`ChampObligatoire` : nom, description, section, mots-clés de détection, exemple de formulation, obligatoire), marqueurs IHC, système de stadification, gabarits de macroscopie et de conclusion à `[X]`, notes spécifiques.

| Indicateur | Valeur |
|---|---|
| Organes | sein, colon_rectum, poumon, prostate, estomac, thyroïde, rein, vessie, col utérin, endomètre, ovaire, mélanome, foie, pancréas, œsophage, ORL, testicule, lymphome, sarcome, SNC, canal anal, vésicule biliaire, appendice |
| Champs | 237, dont 223 obligatoires |
| Plus fournis | estomac 20, colon-rectum 16, sein 14, œsophage 14 |
| Plus pauvres | vésicule biliaire 2, appendice 2, sarcome 7, canal anal 7 |
| Champs récurrents (même nom) | Type histologique 17 fois, pTNM 15, Taille tumorale 11, Ganglions 10, Marges 9 |
| Stadification | TNM 8e édition (AJCC/UICC) pour la majorité ; FIGO 2018 col, FIGO 2023 endomètre, FIGO 2014 ovaire, Ann Arbor/Lugano, OMS 2021 SNC |

**Qualité.** Texte riche, descriptions précises, exemples de formulation. Limites structurelles :
- **Pas d'identifiant stable de champ** : le nom libre sert de clé (« Ganglions examinés et envahis » vs « Emboles vasculaires » vs « Emboles lymphovasculaires »), impossible de fusionner proprement entre organes ou de faire évoluer sans casser.
- **Pas d'attribut de type de valeur** (nombre avec unité, énuméré, booléen, score), donc pas de contrôle d'unités ou de plages à partir de la ressource.
- **Pas de dimension prélèvement ni contexte dans la ressource** : tout est dans `specimen_type.py` (listes `CHAMPS_PIECE_ONLY`, `CHAMPS_INFILTRANT_ONLY`, `CHAMPS_BIOPSIE_EXCLUS`) par recherche de sous-chaîne sur le nom du champ.
- **Pas de provenance par champ** : aucune référence à l'item INCa, à la fiche CRFS ou au modèle Impulsion.
- **Éditions de classification à réexaminer** : TNM 8e partout alors que des éditions plus récentes existent pour certains organes (notamment poumon) ; à vérifier par la pathologiste avant d'afficher une édition comme à jour.

**Fiabilité : B/C.** Structure contrôlée par le typage Pydantic ; contenu non relu par un pathologiste tiers ; deux templates (vésicule, appendice) volontairement minimalistes.

**Usage recommandé.** Point de départ de la migration vers le schéma de la section 7 (conversion mécanique, puis enrichissement : id, type, unités, matrice prélèvement).

### 1.13 `backend/vocabulaire_acp.py` (101 termes)

**Contenu.** Liste unique de 101 termes `CONTEXT_BIAS_TERMS` pour le paramètre `context_bias` de Voxtral (limite ~100) : marqueurs IHC (TTF1, ALK, PD-L1, Ki67, HER2, CK7/20, p16, p40, p63...), éponymes et scores (Gleason, ISUP, SBR, Breslow, Fuhrman), termes histologiques, anatomie, loges ganglionnaires (Barety, sous-carinaire...), gestes (lobectomie, colectomie...), cytologie, néoplasies intra-épithéliales, biologie moléculaire. Classement par criticité.

**Qualité.** Bon choix de termes, commentaire explicite sur un cas réel (Barety transcrit « barretis »). **Limites :** aucune variante phonétique associée, aucune provenance ni fréquence d'erreur, plafond de 100 termes (il faut une sélection dynamique par organe détecté plutôt qu'une liste fixe), aucun terme spécifique au praticien (abréviations `Kepi`, `KGC`, `PSS`...).

**Fiabilité : B.** **Usage :** devenir la sortie d'une requête sur le lexique (priorité x organe), jamais une liste codée en dur.

### 1.14 Ressources de support déjà dans le dépôt, utiles au pipeline

- `docs/CONVENTIONS_CR_ACP.md` (74 lignes) : structure CI-SIS, titre, multi-prélèvements, style macro/micro, ganglions, checklist recall par organe. Fiabilité B. À rattacher au schéma comme `regles_structure`.
- `backend/reports/reporting_systems.py` : systèmes de reporting standard cytologie et médical (Bethesda, Banff, Amsterdam...) proposés en `[A COMPLETER]`. Bonne idée à transformer en données (section 7.12, `echelles`).
- `backend/reports/canonical_texts.py` : verrouillage par organe de l'appariement des textes canoniques (très bonne règle de sécurité, à conserver telle quelle dans la v3).

---

## 2. Évaluation globale (grille)

| Ressource | Contenu utile | Volume | Qualité | Fiabilité | Principale lacune | Usage v3 principal |
|---|---|---|---|---|---|---|
| ADICAP 2024-10 (xlsx/rdf/D4 csv) | Codes D1 à D8, obsolescence | 9 683 concepts | Élevée | A | D5 non exporté en CSV | Référentiel de codage + validation |
| `codage_d1_d2.json` | Règles D1/D2, cardinalité | 11 actes, 2 familles | Bonne | B | Entrées `a_valider`, S vide | Codeur D1/D2 |
| `adicap_bible.json` | Lésion vers code, organes D3 | 306 lésions, 57 organes | Moyenne | B | 57/156 codes organe, pas de rectum/grêle | Codeur lésion (suggestion) |
| Bibles Greg.xlsx | Textes de référence, codes partiels | ~920 lignes | Bonne, hétérogène | B | 5 feuilles non ingérées, `#` | Style, gabarits, codes candidats |
| Codes Bible.doc | Textes + codes complets | 52 entrées | Moyenne | B/C | Doublons, suffixes non officiels | Exemples ORL/RCH |
| Modèles CR (106) | Raccourcis thoraciques, vasculaires, digestifs | 106 fichiers | Bonne | B, D (13 fichiers PII) | 42 non ingérés, PII | Gabarits thorax, abréviations |
| Bibles HML (13) | Non tumoral, critères diagnostiques | 13 fichiers | Bonne | B | Non ingérées | Gabarits non tumoraux |
| Dossiers spécialités (~20) | Textes finaux par organe | ~20 fichiers | Bonne | B | 1 texte par organe sauf poumon | Exemples de style |
| CR avec audio (5 couples) | CR réels + dictées | 5 + 5 | Bonne | B | Pas de transcription brute, N=5 | Banc d'essai |
| presentation-cr-anapath.pdf | Règles de structure | 3 p. | Excellente | A (règles) | Qualitatif | Orchestrateur |
| recherche_standards (web) | INCa, ADICAP, termes, Impulsion | 47 Ko | Moyenne | C | Secondaire, 5 organes détaillés | Amorçage lexique, backlog |
| templates_organes.py | 23 organes, 237 champs | 164 Ko | Moyenne | B/C | Pas d'id, pas de type, pas de matrice | Champs obligatoires (migration) |
| vocabulaire_acp.py | 101 termes biais STT | 101 | Bonne | B | Pas de variantes ni provenance | Biais STT dynamique |
| snomed.py | 25 topographies, 19 morphologies | 44 codes | Faible | D (non vérifié) | Pas de release, 1 code par CR | Suggestion non validée |
| regles_metier_anapath.md | Index historique | 3 Ko | n/a | B | Pas de contenu propre | À archiver |

---

## 3. Recoupements et contrôles effectués

- ADICAP : les 306 `lesion_code` de `adicap_bible.json` sont tous présents dans `adicap_ref.json` (D4 268, D7 18, D5 11, D6 9) et aucun n'est obsolète. Présence ne veut pas dire pertinence : la correspondance libellé praticien vers libellé officiel reste à auditer par la pathologiste.
- D3 : 57 codes organe dans la bible contre 156 codes à deux lettres dans le thésaurus (le thésaurus inclut aussi des codes de regroupement comme `FZ`, `DZ`). Ne figurent pas : DR, DG, FP, FE, FO, ES, EP, EH, CP, CC, BL, BG, BP...
- Format des codes de la bible Excel : 447 codes renseignés, dont 59 % incomplets (4 caractères de lésion sans organe) ; le code ADICAP complet fait 8 caractères (D1 + D2 + D3 sur 2 + lésion sur 4), il doit donc être recomposé par `composer_codes`.
- Ingestion : 653 textes canoniques produits, environ 211 textes de 5 feuilles perdus à cause de la disposition de colonnes, 42 modèles CR sur 106 écartés.
- Doublons : `corpus/` = `Ressources/2.` (10 fichiers identiques), `Codage_D1_D2_table.json` = `backend/data/codage_d1_d2.json`, ZIP + dossier ADICAP, deux PDF CGTS différents, blocs RCH répétés dans `Codes Bible.doc`, 31 doublons (organe, lésion) dans le JSON.
- PII : recherche de motifs (`née le`, `Patient :`, `NIP`, `RPPS`, numéros d'examen). Résultat : 13 fichiers Modèles CR et 3 entrées du JSON déployé.

---

## 4. Ce qui MANQUE

### 4.1 Organes et types de prélèvement non couverts par un gabarit/template

Référence de comparaison : 21 localisations INCa et 181 modèles Impulsion ACP (liste dans `recherche_standards...`, section 8).

| Domaine | État aujourd'hui | Ressources métier disponibles dans le dépôt |
|---|---|---|
| Sein (non tumoral, cytologie, ganglion sentinelle) | Template tumoral présent ; texte canonique perdu (feuille SEIN non ingérée) | Feuille SEIN (19 textes), `BB AdK SEIN` |
| Peau hors mélanome (carcinomes basocellulaire/épidermoïde, nævus, inflammatoire) | Aucun template | Feuille DERMATO (118 textes non ingérés) |
| Os, articulations, tissus mous bénins | Sarcome seulement | OS-ARTI (36), T mous (9) |
| SNC bénin (méningiome, chordome) | Un template SNC générique | NEURO (13) |
| Thymus (thymome, Masaoka) | Aucun | Modèles THYMOME (3), Bibles HML Thymus |
| Glandes endocrines (parathyroïde, surrénale) | Aucun | ENDOC (31 textes ingérés, sans champs) |
| Voies biliaires, ampoule de Vater, grêle/duodénum, GIST | Aucun (vésicule et appendice très minces) | DIG partiel |
| Plèvre, péritoine, mésothéliome | Aucun | Modèles PLEVRE (8), MESOPATH (courrier) |
| Gynécologie rare (vulve, vagin, trompe, placenta, môle, fausse couche) | Aucun | GYN, FOETO-P (2 ingérés sur 7) |
| Uro rare (pénis, uretère, voies excrétrices, vessie non tumorale) | Aucun | URO |
| Cœur et vaisseaux (greffe, myxome, anévrysme, athérome) | Aucun | CV, 15 modèles CR non ingérés |
| Œil, ORL non tumoral (amygdale, glandes salivaires), cavité buccale | ORL générique | OPH, ORL (131 textes) |
| Hématologie (moelle, rate, ganglion non tumoral) | Lymphome seulement | HEMATO (56 lignes) |
| Cytologie (LBA, FCU Bethesda, urines Paris, liquides séreux, aspirations) | Aucun template ; `reporting_systems.py` en palliatif | CYTO, Cyto FCU, LBA |
| Pathologie médicale (MICI, gastrite, hépatite, greffe, PID, emphysème) | Aucun template | Modèles DG/DC, BIOPSIES COLIQUES, Bibles HML |
| Extemporané, techniques spéciales, biologie moléculaire (IDYLLA, FISH) | Aucun gabarit dédié | Feuille CR, modèles IDYLLA |
| Études post-traitement néo-adjuvant (ypTNM, RCB, TRG) | Mention dans les notes seulement | `recherche_standards` section 3.1 |

### 4.2 Référentiels absents du dépôt

- **SNOMED CT** (aucune release, ni internationale ni française ; la France est membre, la distribution passe par le NRC/SMT de l'ANS) : pas de table de concepts, pas de FSN français, pas de hiérarchies Procedure et Specimen, pas de mapping vers ADICAP ni CIM-O. Les 44 codes de `snomed.py` n'ont pas été contrôlés ; les codes de topographie ont l'allure de codes de structure plausibles, mais plusieurs codes de morphologie sont à confronter à une release (risque de concept « disorder » pris pour une anomalie morphologique).
- **CIM-O 3 (topographie T et morphologie M avec comportement /0 /1 /2 /3 /6)** : décrit dans le markdown seulement ; il faut le fichier de l'OMS pour un mapping ADICAP vers CIM-O.
- **INCa et CRFS SFP** (21 + 24 fiches) : références URL sans copie locale ni numéro de version ; impossible d'attribuer une provenance au niveau de l'item.
- **Contenu des 181 modèles Impulsion ACP** : seulement le catalogue de noms ; le détail des items (qui est un format structuré et réutilisable) manque.
- **Tables TNM 8/9, FIGO, grading (SBR, Gleason/ISUP, Nancy, Banff, Bethesda, Paris, Lugano)** : aucune table de valeurs autorisées ni règle de calcul (ex. correspondance Gleason vers groupe ISUP, somme SBR 3 à 9).
- **Stations ganglionnaires** (IASLC pour le poumon : 1 à 14, 2R, 4R, 7, 10, 11, 12...) : seules quelques loges sont dans le biais STT ; le CR 3 montre que le curage thoracique est dicté par loge avec des effectifs (7 ganglions loge 4R...). Table des loges (synonymes parlés : « Barety », « sous-carinaire », « ligament triangulaire ») à créer.
- **Lexique phonétique réel** : aucune variante observée, aucune transcription brute de référence, aucun lexique propre au laboratoire (noms de blocs, codes des anticorps, clones : `QR1`, `1A4`, `BOND III`...).
- **Table geste x organe** pour le choix I/O de D1 (annoncée comme proposition, à valider).
- **Unités et plages plausibles** : aucune ressource (mm/cm, g, %, nombre de ganglions, plages de Ki67, score SBR...).

### 4.3 Qualité des données à améliorer

- Un seul praticien de référence pour les textes (plus deux internes pour le thorax) : risque de style non généralisable.
- Pas de dates, pas de versions sur les bibles : impossible de savoir ce qui est obsolète.
- Orthographe de certains textes (« une des distingues », « 1à »), accents manquants, majuscules : à normaliser avant usage comme exemples de style.

---

## 5. Risques et corrections prioritaires

### 5.1 Conformité (blocage avant déploiement v3)

1. Retirer des fichiers sources et de `textes_canoniques.json` toute ligne contenant `Patient :`, `NIP`, `Examen : ML`, `née le`, `RPPS`, un nom de patient ou un numéro d'examen. Les 2 courriers (MESOPATH, LYMPHOPATH) sont à exclure du pipeline ou à anonymiser (pas de valeur de gabarit).
2. Ajouter un **scan PII bloquant** dans les scripts d'ingestion (regex + liste de motifs) et un test CI qui vérifie que `backend/data/*.json` n'en contient pas.
3. Documenter le statut de ces ressources : le principe « aucune donnée médicale ni audio stockée » concerne l'exploitation, mais un fichier source contenant des données patient est lui-même un stock de données de santé à traiter selon le RGPD (durée de conservation, accès, hébergement).
4. Les 5 CR et audios d'exemple sont à qualifier : vérifier que les dictées ne contiennent pas d'éléments identifiants.

### 5.2 Corrections techniques d'ingestion

1. `ingest_textes_canoniques.py` : détecter la disposition des colonnes par feuille (en-têtes) plutôt que par position fixe, pour récupérer SEIN, DERMATO, OS-ARTI, T mous, NEURO (+ HEMATO partiel et BDig).
2. `ingest_modeles_cr.py` : étendre la table de préfixes (vasculaire, myocarde, DD/DE/DG/DC, ganglion/lymphome) après anonymisation ; logger les fichiers écartés au lieu de les ignorer.
3. Déduplication explicite (31 doublons), normalisation des codes (`DQ 4554` vers `DQ4554`, plages, multi-codes), séparation de `code_lesion` et `code_organe`.
4. Dédupliquer les doublons du dépôt (corpus, PDF CGTS, ZIP).

### 5.3 Validation métier à obtenir de la pathologiste

- Trancher les entrées `a_valider` de la table D1/D2.
- Valider la table geste x organe (I vs O) et le lexique du code S.
- Relire le mapping libellé praticien vers libellé ADICAP officiel pour les 306 lésions (priorité aux organes à fort volume : poumon, côlon, sein, prostate).
- Confirmer pour chaque organe les éditions de classification à afficher et les champs obligatoires par prélèvement.

---

## 6. Usage recommandé de chaque ressource dans le pipeline v3

| Étage du pipeline | Ressource(s) à brancher | Remarque |
|---|---|---|
| Biais STT (Voxtral) | Lexique (section 7.6) filtré par priorité et organe détecté, issu de `vocabulaire_acp.py` | Liste dynamique ≤ 100 termes, sélection par organe |
| Correcteur phonétique | Lexique : variantes phonétiques observées (après transcription des audios) + acronymes | Passer d'une correction purement LLM à une table + LLM avec citation de la règle |
| Orchestrateur | PDF de la pathologiste + `CONVENTIONS_CR_ACP.md` + `specimen_type.py` | Détection biopsie/pièce, cancéro/non cancéro, multi-prélèvements |
| Extracteur | Champs (section 7.5) avec type de valeur et unités | Sortie typée avec source (extrait de dictée) et confiance |
| Vérificateurs | Règles de cohérence (section 7.9) et champs obligatoires par organe x prélèvement | Unités mm/cm, incohérences, manquants INCa |
| Codeur ADICAP | ADICAP 2024-10 + `codage_d1_d2.json` + catalogue lésions (bible) | D1/D2 déterministes ; lésion en suggestion ou différée (`____`) |
| Codeur SNOMED CT | Table de mapping (section 7.8) ; actuellement `snomed.py` | Marqué « non validé » tant que la release n'est pas intégrée |
| Rédacteur | Gabarits (section 7.10) + textes de style canoniques verrouillés par organe | Style du praticien, ne jamais affirmer ce qui n'est pas dicté |
| Texte à trous | Champs obligatoires manquants avec question associée | `[A COMPLETER: …]` avec source de l'exigence (INCa, CAP...) |

---

## 7. Schéma de base de connaissances proposé (`kb_marc_v3`)

### 7.1 Principes

1. **Un seul format JSON versionné**, découpé en collections (fichiers ou clés racines) : `manifest`, `sources`, `organes`, `prelevements`, `champs`, `lexique`, `adicap`, `snomed`, `regles`, `gabarits`, `exemples_style`, `echelles`, `stations`.
2. **Provenance obligatoire sur chaque entrée** (objet `prov`, section 7.3). Une entrée sans `prov` est refusée à la validation de build.
3. **Identifiants stables lisibles** (`organe:poumon`, `champ:poumon.type_histologique`, `regle:colon.ganglions_min_12`) : jamais le libellé comme clé.
4. **Statut de validation explicite** (`a_valider`, `valide`, `obsolete`) : le pipeline ne présente un élément comme règle ferme que s'il est `valide`.
5. **Repli prévu dans les données** (`repli`) : chaque entrée dit ce que le pipeline fait si l'information associée manque.
6. **Rétro-compatible** : script de conversion mécanique depuis `templates_organes.py`, `adicap_bible.json`, `textes_canoniques.json`, `codage_d1_d2.json`, `vocabulaire_acp.py` ; les entrées converties portent `statut_validation: "derive_auto"` jusqu'à relecture.
7. **Aucune donnée patient** dans la base : scan PII au build (section 5.1).

### 7.2 Racine et manifeste

```json
{
  "kb_version": "3.0.0",
  "schema_version": "kb_marc_v3.1",
  "built_at": "2026-11-15T10:00:00Z",
  "build": { "git_commit": "abc1234", "pii_scan": { "ok": true, "regles": 14 } },
  "sources": [ /* 7.3.1 */ ],
  "organes": [ /* 7.4 */ ],
  "prelevements": [ /* 7.4 */ ],
  "champs": [ /* 7.5 */ ],
  "lexique": [ /* 7.6 */ ],
  "adicap": { "dictionnaires": [ /* D1..D8 */ ], "mapping_lesions": [ /* 7.7 */ ] },
  "snomed": { "edition": null, "concepts": [ /* 7.8 */ ] },
  "regles": [ /* 7.9 */ ],
  "gabarits": [ /* 7.10 */ ],
  "exemples_style": [ /* 7.11 */ ],
  "echelles": [ /* grades, scores */ ],
  "stations": [ /* loges ganglionnaires */ ]
}
```

### 7.3 Provenance, fiabilité et registre des sources

**7.3.1 Registre des sources** (une fois, référencé par `source_id`) :

```json
{
  "id": "src:adicap_2024_10",
  "type": "officiel",
  "titre": "Thésaurus de la codification ADICAP, index raisonné des lésions",
  "editeur": "ANS",
  "version": "2024-10",
  "date_publication": "2024-10-02",
  "licence": "Licence Ouverte 2.0",
  "fichiers": ["docs/specs/referentiels/terminologie-adicap-2024-10/dat/ADICAP_2024.xlsx"],
  "sha256": "…",
  "fiabilite": "A",
  "perimetre": "D1-D8",
  "contient_pii": false
}
```

Types de source (`type`) : `officiel`, `praticien`, `derive_auto`, `synthese_web`, `observe_terrain` (variantes issues des dictées réelles), `etude_interne`.

**7.3.2 Objet `prov` (obligatoire sur chaque entrée)** :

```json
"prov": {
  "source_id": "src:bible_greg_xlsx",
  "localisation": "feuille THO, ligne 9",
  "version_source": "2026-04-07",
  "date_extraction": "2026-11-15",
  "fiabilite": "B",
  "confiance": 0.8,
  "statut_validation": "a_valider",
  "valide_par": null,
  "date_validation": null,
  "methode": "extraction_automatique",
  "remplace": null
}
```

- `fiabilite` : A, B, C, D (définitions en tête de rapport). Héritée de la source, **abaissée** par la méthode (une règle dérivée automatiquement d'une source A passe en B tant qu'elle n'est pas relue).
- `confiance` : réel 0 à 1, propagé jusqu'à la sortie utilisateur (explicabilité : chaque élément du projet de CR cite `prov.source_id` + `localisation` et porte un degré).
- `statut_validation` : `valide`, `a_valider`, `derive_auto`, `contesté`, `obsolete`.
- `remplace` : id de l'entrée précédente (pour l'historique).

### 7.4 Organes et prélèvements

```json
{
  "id": "organe:poumon",
  "libelle": "Poumon",
  "aliases": ["pulmonaire", "bronche", "bronchique"],
  "parent": null,
  "categorie_systeme": "thorax",
  "mots_cles_detection": ["poumon", "bronchique", "lobectomie", "ebus"],
  "adicap_d3": ["BP", "RB"],
  "snomed_body_structure": ["snomed:39607008"],
  "cim_o_topographie": ["C34"],
  "staging": [
    { "nom": "TNM", "edition": "8", "statut": "a_verifier", "organe_specifique": true }
  ],
  "impulsion_refs": ["M0004"],
  "couverture": { "gabarit": "complet", "champs": "complet", "exemples_style": "riche", "codage": "partiel" },
  "prov": { /* 7.3.2 */ }
}
```

`couverture` est calculée à chaque build et pilote le repli (section 8). Valeurs possibles : `complet`, `partiel`, `minimal`, `absent`.

```json
{
  "id": "prelevement:biopsie",
  "libelle": "Biopsie",
  "classe": "biopsie",
  "variantes": ["microbiopsie", "macrobiopsie", "carotte", "ponction-biopsie"],
  "adicap_d1": ["P", "H", "B"],
  "declencheurs": ["biopsie", "carotte biopsique", "fragment biopsique"],
  "prov": { }
}
```

Classes : `biopsie`, `piece_operatoire`, `cytologie`, `curage`, `extemporane`, `autre`. Une même dictée peut contenir plusieurs prélèvements (cardinalité conforme à `codage_d1_d2.json`).

### 7.5 Champs obligatoires par organe x type de prélèvement

Le cœur du schéma. On sépare **le catalogue de champs** (un champ = une notion) de **l'exigence** (ce champ est obligatoire pour tel organe, tel prélèvement, tel contexte).

```json
{
  "id": "champ:type_histologique",
  "libelle": "Type histologique",
  "section": "microscopie",
  "type_valeur": "enum",
  "valeurs_autorisees_ref": "echelle:oms_poumon_2021_types",
  "unite": null,
  "detection": {
    "mots_cles": ["adénocarcinome", "carcinome épidermoïde", "type histologique"],
    "regex": []
  },
  "question_par_defaut": "Quel est le type histologique ?",
  "prov": { }
}
```

```json
{
  "id": "exigence:poumon.type_histologique",
  "champ_id": "champ:type_histologique",
  "organe_id": "organe:poumon",
  "prelevements": ["prelevement:biopsie", "prelevement:piece_operatoire", "prelevement:cytologie"],
  "contextes": ["infiltrant", "in_situ", "benin", "non_tumoral"],
  "niveau": "obligatoire_inca",
  "obligatoire_si": null,
  "placement": { "section": "conclusion", "ordre": 1 },
  "formulation_modele": "Adénocarcinome infiltrant non mucineux, d'architecture {architecture}",
  "repli_si_absent": { "action": "trou", "texte_trou": "[A COMPLETER : type histologique selon OMS]", "bloquant": false },
  "posable_en_question": true,
  "prov": { "source_id": "src:inca_donnees_minimales_2011", "localisation": "poumon, p. …", "fiabilite": "C", "statut_validation": "a_valider" }
}
```

Points clés :
- `niveau` : `obligatoire_inca` (INCa/CRFS), `obligatoire_local` (exigence du praticien ou du labo), `recommande` (CAP, ICCR, Impulsion), `optionnel`.
- `prelevements` et `contextes` rendent explicite ce qui est aujourd'hui caché dans `specimen_type.py`. `contextes` : `infiltrant`, `in_situ`, `benin`, `non_tumoral`, `post_neoadjuvant`, `recidive`, `metastase`.
- `obligatoire_si` : condition déclarative (ex. HER2 = 2+ implique ISH) en mini-DSL identique à celui des règles (section 7.9).
- `type_valeur` : `enum`, `nombre`, `nombre_unite`, `booleen`, `score`, `texte_libre`, `liste_structuree` (ex. curage par loge), `date`.
- `unite` et `plage_plausible` (voir règles) permettent à l'étage « vérificateur d'unités » de travailler sans hypothèse implicite.

### 7.6 Lexique et variantes phonétiques

```json
{
  "id": "lex:barety",
  "terme_canonique": "loge de Barety (4R)",
  "categorie": "station_ganglionnaire",
  "organes": ["organe:poumon"],
  "priorite_biais_stt": 1,
  "variantes": [
    { "forme": "barretis", "origine": "observe_terrain", "occurrences": 3, "confiance": 0.9 },
    { "forme": "baretti", "origine": "genere", "occurrences": 0, "confiance": 0.4 }
  ],
  "acronymes": [],
  "faux_amis": [],
  "contexte_requis": ["ganglion", "loge", "curage"],
  "code_adicap_ref": null,
  "snomed_ref": null,
  "prov": { }
}
```

- `origine` des variantes : `observe_terrain` (issue d'une vraie transcription, la plus fiable), `genere` (produite par règle ou par LLM), `pathologiste` (déclarée), `abrege_praticien` (ex. `Kepi`).
- `contexte_requis` empêche une correction hors contexte (une variante n'est appliquée que si un des mots de contexte est présent dans la fenêtre).
- `priorite_biais_stt` (1 = critique) et `organes` pilotent la sélection dynamique des 100 termes du `context_bias`.
- Une table `acronymes` dédiée (TTF1, EBUS, LBA, AIN3, PSS, Kepi...) avec expansion et niveau de confiance accompagne le lexique.

### 7.7 Codes ADICAP

```json
{
  "adicap": {
    "dictionnaires": [
      { "dict": "D3", "code": "BP", "libelle": "BRONCHES - POUMON", "uri": "…", "fin_validite": null, "prov": { "source_id": "src:adicap_2024_10" } }
    ],
    "mapping_lesions": [
      {
        "id": "map:poumon.adk_acineux",
        "organe_id": "organe:poumon",
        "libelle_praticien": "Adénocarcinome infiltrant non mucineux, d'architecture acineuse",
        "declencheurs": ["adénocarcinome", "acineux"],
        "adicap": { "d3": "BP", "lesion": "A7A0", "dict_lesion": "D5", "pos_5_8": "A7A0" },
        "codes_alternatifs": [],
        "conditions": ["non_mucineux"],
        "exige_validation_pathologiste": true,
        "prov": { "source_id": "src:bible_greg_xlsx", "localisation": "feuille THO, ligne 9", "fiabilite": "B", "statut_validation": "a_valider" }
      }
    ],
    "regles_d1_d2": "ref:codage_d1_d2_v2.0"
  }
}
```

Règles : le code `D1 D2 D3 lésion` est **recomposé** (jamais lu tel quel dans la source) ; la lésion est `____` si aucun mapping `valide` ne correspond ; un code obsolète (`fin_validite` non nulle) n'est jamais proposé.

### 7.8 Codes SNOMED CT

```json
{
  "snomed": {
    "edition": { "nom": "International", "version": "2026-xx", "licence": "affiliate", "pays": "FR", "source": "SMT/NRC" },
    "concepts": [
      {
        "concept_id": "39607008",
        "fsn": "Lung structure (body structure)",
        "terme_fr": "Structure du poumon",
        "hierarchie": "body_structure",
        "usage": "topographie",
        "organe_ids": ["organe:poumon"],
        "type_mapping": "equivalent",
        "verifie_contre_release": false,
        "prov": { "source_id": "src:snomed_py_historique", "fiabilite": "D", "statut_validation": "a_valider" }
      }
    ],
    "mapping_lesions": [
      { "lesion_id": "map:poumon.adk_acineux", "concept_ids": ["…"], "type_mapping": "broader", "prov": { } }
    ]
  }
}
```

- `verifie_contre_release: false` tant qu'une édition officielle n'est pas chargée ; l'interface affiche alors « suggestion non vérifiée ».
- Hiérarchies à prévoir : `body_structure` (topographie), `morphologic_abnormality` (morphologie), `procedure` (geste), `specimen` (nature du prélèvement), `qualifier_value` (latéralité).
- `type_mapping` : `equivalent`, `broader`, `narrower`, `related`, `aucun`. Plusieurs concepts par lésion possibles (le code actuel n'en retourne qu'un).
- Prévoir un champ `cim_o` pour le comportement /0 /1 /2 /3 /6.

### 7.9 Règles de cohérence

Format déclaratif, testable, avec sévérité et message citant la source :

```json
{
  "id": "regle:ganglions_envahis_inferieur_examines",
  "type": "incoherence",
  "portee": { "organes": ["*"], "prelevements": ["prelevement:piece_operatoire", "prelevement:curage"] },
  "condition": { "si": "ganglions_envahis > ganglions_examines" },
  "severite": "bloquant_signalement",
  "message": "Le nombre de ganglions envahis ({ganglions_envahis}) dépasse le nombre de ganglions examinés ({ganglions_examines}).",
  "action": "poser_question_ou_trou",
  "tests": [
    { "entree": { "ganglions_envahis": 3, "ganglions_examines": 2 }, "attendu": "declenche" },
    { "entree": { "ganglions_envahis": 2, "ganglions_examines": 2 }, "attendu": "ne_declenche_pas" }
  ],
  "prov": { "source_id": "src:regles_pathologiste", "fiabilite": "A", "statut_validation": "valide" }
}
```

Familles de règles (avec exemples à faire valider ; elles sont ici des **propositions**, pas des règles établies) :

| Famille | Exemples | Candidat de provenance |
|---|---|---|
| `unite` | mm/cm incohérents entre macro et conclusion ; dimension tumorale > dimension de la pièce ; valeur hors plage plausible (Ki67 > 100 %, SBR hors 3 à 9) ; unité manquante | Tables de plages (`plage_plausible` des champs) |
| `incoherence` | ganglions envahis > examinés ; marges dites saines avec distance 0 ; type histologique incompatible avec l'organe ; biopsie avec champs pièce ; latéralité contradictoire | Sections de `CONVENTIONS_CR_ACP.md`, INCa |
| `champ_manquant` | donnée INCa obligatoire absente pour (organe, prélèvement, contexte) | `exigence:*` |
| `calcul` | Gleason vers groupe ISUP ; somme SBR ; pTNM vs taille | Échelles (section 7.12) |
| `negation` | « pas de granulome » ne doit pas coder un granulome | `negation.py` (existant) |
| `codage` | D1 incohérent avec « biopsie » dicté ; nombre de codes différent de (prélèvements + techniques) | `codage_d1_d2.json` |
| `qualite_minimale` | seuils de ganglions (12 côlon, 16 estomac) | `recherche_standards` à vérifier (fiabilité C) |

La condition est écrite dans un mini-langage JSON évaluable sans exécution de code arbitraire (comparaisons, `et`, `ou`, `non`, `dans`, `present`, `absent`). Chaque règle embarque ses propres tests (cas passants et non passants).

### 7.10 Gabarits

```json
{
  "id": "gabarit:poumon.biopsie.cancero",
  "organe_id": "organe:poumon",
  "prelevement_id": "prelevement:biopsie",
  "contexte": "infiltrant",
  "sections": [
    { "nom": "titre", "modele": "BIOPSIE D'UNE LESION PULMONAIRE DU {lobe} {lateralite}" },
    { "nom": "clinique", "modele": "{renseignements_cliniques}", "source_donnee": "logiciel_metier" },
    { "nom": "macroscopie", "modele": "{nb_fragments} fragment(s) biopsique(s) de {taille_fragments}, adressé(s) fixé(s) en formol, inclus en paraffine." },
    { "nom": "microscopie", "modele": "{description_histologique}" },
    { "nom": "ihc", "type": "liste_structuree", "champs": ["anticorps", "resultat", "intensite", "pourcentage"], "regle": "dicte_seulement" },
    { "nom": "conclusion", "modele": "{type_histologique}. {biomarqueurs}" }
  ],
  "slots": [
    { "nom": "taille_fragments", "champ_id": "champ:taille_fragments", "type": "nombre_unite", "unite": "mm" }
  ],
  "exemples_style_ids": ["ex:poumon.biopsie.adk.001"],
  "repli": { "si_gabarit_absent": "gabarit:generique.biopsie.cancero" },
  "prov": { }
}
```

Chaque `slot` correspond à un `champ` ; un slot sans valeur dictée devient un **trou** (`[A COMPLETER : …]`) avec sa source d'exigence. La règle « IHC dictées uniquement » (PDF de la pathologiste) est portée par `regle: "dicte_seulement"`.

### 7.11 Exemples de style (textes canoniques)

```json
{
  "id": "ex:poumon.biopsie.adk.001",
  "organe_id": "organe:poumon",
  "prelevement_id": "prelevement:biopsie",
  "lesion_libelle": "Adénocarcinome",
  "texte": "…",
  "placeholders": [ { "marque": "#", "champ_id": "champ:nb_fragments" } ],
  "praticien_id": "prat:A",
  "pii_verifie": true,
  "qualite": { "nb_caracteres": 640, "a_trous": true, "complet": true },
  "mapping_lesion_id": "map:poumon.adk_acineux",
  "prov": { }
}
```

`praticien_id` : pseudonyme (jamais un nom). Il permet de représenter la variabilité de style entre pathologistes (Bibles Thorax, Riad ARANA) et d'adapter le style au praticien connecté sans stockage de données patient. `pii_verifie` doit être vrai pour que l'exemple entre dans la base.

### 7.12 Échelles, scores et stations

```json
{
  "id": "echelle:gleason_isup",
  "type": "table_correspondance",
  "entrees": [
    { "gleason": "3+3", "somme": 6, "isup": 1 },
    { "gleason": "3+4", "somme": 7, "isup": 2 },
    { "gleason": "4+3", "somme": 7, "isup": 3 },
    { "somme": 8, "isup": 4 },
    { "somme": 9, "isup": 5 }
  ],
  "prov": { "source_id": "src:oms_blue_book", "fiabilite": "A" }
}
```

```json
{
  "id": "station:4R",
  "organe_id": "organe:poumon",
  "systeme": "IASLC",
  "numero": "4R",
  "libelle": "Paratrachéale inférieure droite",
  "synonymes_parles": ["loge de Barety", "latéro-trachéale droite"],
  "prov": { }
}
```

### 7.13 Contrôles de build du schéma

À exécuter à chaque génération de la base (échec = build rouge) :
1. Toute entrée possède `prov` complet (source existante dans le registre).
2. Aucune clé étrangère orpheline (`organe_id`, `champ_id`, `source_id`...).
3. Aucun code ADICAP obsolète dans les mappings, tout code existe dans `adicap_ref`.
4. Scan PII négatif sur l'ensemble des textes.
5. Chaque règle passe ses tests embarqués.
6. Indicateurs de couverture calculés et publiés (organes sans gabarit, champs sans exigence, lésions sans code).

---

## 8. Repli gracieux : ne jamais bloquer la production

Principe : **chaque étage renvoie toujours un résultat typé `{valeur | null, statut, source, confiance}`** ; l'absence d'une source abaisse le niveau de service, jamais ne coupe la chaîne. Le projet de CR est toujours produit.

### 8.1 Niveaux de service

| Niveau | Condition | Résultat pour l'utilisateur |
|---|---|---|
| N0 complet | Organe + prélèvement + exigences + gabarit + exemples + codes | Projet complet, sources citées, codes proposés |
| N1 partiel | Une partie manque (ex. pas de code lésion, pas d'exemple de style) | Projet complet, codes partiels, mention « non codé » |
| N2 générique | Organe non couvert par un gabarit | Gabarit générique + socle INCa commun, champs à trous |
| N3 minimal | Aucune ressource utilisable (organe inconnu, base absente) | Mise en forme fidèle de la dictée par le rédacteur (structure de CR standard), aucune exigence, aucun code, avertissement visible |

### 8.2 Table de repli par source manquante

| Source manquante | Étage touché | Comportement de repli | Signal affiché |
|---|---|---|---|
| Lexique phonétique vide ou incomplet | Correcteur phonétique | Seul le biais STT par défaut (101 termes actuels) + correction LLM, chaque correction signalée « par le modèle, confiance moyenne » | Badge « correction non référencée » |
| Variante phonétique observée absente | Correcteur | Proposition LLM uniquement si le contexte (`contexte_requis`) est présent, sinon laisser le terme et le surligner | Terme souligné « à vérifier » |
| Organe non couvert (pas de `organe:*`) | Orchestrateur, extracteur | Gabarit générique par classe (biopsie/pièce/cytologie) x (cancéro/non cancéro), champs INCa transversaux (type histologique, taille, marges, ganglions, emboles, pTNM si pièce tumorale) | « Organe non référencé : socle générique » |
| Pas de champs obligatoires pour (organe, prélèvement) | Vérificateur manquants | Appliquer d'abord les exigences de l'organe sans filtre de prélèvement, puis les exigences transversales ; ne pas bloquer la signature | « Exigences incomplètes pour ce prélèvement » |
| Gabarit absent | Rédacteur | Repli sur gabarit de la classe (`gabarit:generique.*`), sections standard du PDF de la pathologiste (titre, clinique, macro, inclusion, micro, IHC, conclusion) | « Gabarit générique » |
| Pas d'exemple de style pour l'organe | Rédacteur | Style du CR de référence le plus proche de la même classe (jamais d'un autre organe : verrou par organe conservé) ; sinon style neutre | « Style non personnalisé » |
| Code ADICAP lésion absent ou ambigu | Codeur ADICAP | Code partiel `D1 D2 D3 ____`, lésion différée ; question de levée de doute si elle change la sortie (budget 3) | Code partiel visible, jamais de code faux |
| Code D3 organe absent | Codeur ADICAP | Code D3 par recherche dans le thésaurus 2024-10 (156 codes) ; sinon `XX` non émis, code non proposé | « Organe non codé » |
| Code obsolète | Codeur | Remplacer par le successeur si indiqué, sinon ne rien proposer et afficher l'avertissement | « Code obsolète écarté » |
| SNOMED absent (aucune release chargée) | Codeur SNOMED | Suggestions non vérifiées (`verifie_contre_release: false`), ou section masquée ; la production du CR n'en dépend jamais | « SNOMED non vérifié » ou rien |
| Règle de cohérence absente ou invalide | Vérificateurs | Ignorer la règle fautive, journaliser, continuer ; les règles par défaut (unités, ganglions) restent actives | Aucun signal côté pathologiste ; alerte côté admin |
| Échelle ou table de scores absente | Vérificateurs | Ne pas calculer ; écrire la valeur dictée telle quelle avec la mention « non vérifiée » | « Score non recalculé » |
| Provenance incomplète sur une entrée | Tous | Entrée écartée au build (erreur) ; au runtime, utiliser la version précédente de la base | Erreur de build, pas d'impact utilisateur |
| Transcription STT dégradée (bruit, termes inconnus) | Correcteur, extracteur | Texte à trous sur les valeurs critiques (chiffres, latéralité), jamais d'invention | « Valeur non comprise, à dicter » |
| Base de connaissances entière indisponible | Pipeline | Chargement de la dernière base valide embarquée dans l'image ; à défaut, N3 | Bandeau « mode dégradé » |

### 8.3 Règles de conception

1. **Jamais de code ou de valeur inventés pour combler un manque** : trou plutôt que fabrication (cohérent avec `adicap.py` et `comblement.py`).
2. **Le verrou par organe des exemples de style est conservé** : mieux vaut aucun exemple qu'un exemple d'un autre organe.
3. **Une source manquante n'est jamais fatale, mais toujours visible** pour l'administrateur : l'indicateur de couverture du build doit lister les trous.
4. **Chaque repli est tracé** dans la sortie explicable (champ `repli_applique`), ce qui alimente la télémétrie d'usage (sans donnée médicale).

---

## 9. Plan d'action ressources (priorités)

| Priorité | Action | Effet | Charge estimée |
|---|---|---|---|
| P0 | Purge PII de `textes_canoniques.json` et des Modèles CR, scan PII bloquant | Conformité, déblocage du déploiement | 0,5 j |
| P0 | Transcrire (Voxtral) les 5 audios, conserver les transcriptions brutes comme vérité terrain STT, aligner avec les CR | Banc STT, premières variantes `observe_terrain` | 1 j |
| P0 | Définir le schéma `kb_marc_v3` et le script de conversion depuis le code existant (statut `derive_auto`) | Base commune à tous les étages | 2 j |
| P1 | Corriger l'ingestion Excel (détection de colonnes) et Modèles CR (préfixes) | +211 textes, +42 modèles | 1 j |
| P1 | Matrice organe x prélèvement x contexte pour les 5 organes de référence (poumon, sein, côlon, prostate, canal anal) | Champs obligatoires fiables sur le périmètre de démonstration | 2 j |
| P1 | Catalogue de règles de cohérence v1 (unités, ganglions, scores) avec tests, validé par la pathologiste | Étage vérificateur démontrable | 2 j |
| P1 | Table des stations ganglionnaires (poumon IASLC) et acronymes du praticien | Dictée de curage fiable (CR 3) | 1 j |
| P2 | Charger une release SNOMED CT (France) et recoller les 44 codes | Étage SNOMED crédible | 2 j (hors accès licence) |
| P2 | Gabarits non tumoraux et cytologie (LBA, FCU, PID, MICI, gastrite) depuis Bibles HML et Greg | Couverture au-delà du tumoral | 3 j |
| P2 | Collecter 30 dictées supplémentaires multi-organes et multi-praticiens | Mesure de la promesse « 10x plus rapide » | selon disponibilité |
| P3 | Importer le contenu des modèles Impulsion ACP pour les organes cibles | Alignement national | 3 j |
| P3 | Dédupliquer le dépôt (corpus, CGTS, ZIP), archiver `regles_metier_anapath.md` | Hygiène | 0,5 j |

---

## 10. Questions à trancher avec la pathologiste référente

1. Les textes de la bible peuvent-ils être diffusés tels quels comme exemples de style, ou faut-il une réécriture (propriété intellectuelle, praticien tiers nommé dans les Bibles Thorax) ?
2. Quels organes et prélèvements prioriser pour la démo (propose : poumon, sein, côlon, prostate, canal anal) ?
3. Quelle édition de TNM/OMS afficher par organe (la base doit porter la date et la source, pas une valeur par défaut) ?
4. Souhaite-t-elle valider elle-même les mappings libellé vers code ADICAP, ou accepter un statut « dérivé » affiché comme tel ?
5. Faut-il un jeu de dictées d'un second praticien pour tester la généralisation du style ?
6. Quels abréviations et raccourcis internes (Kepi, KGC, PSS, LSD, LID, LM, MDH...) doivent être des règles fermes de développement et lesquels doivent rester des suggestions ?
7. Existe-t-il d'autres données patient dans les ressources non listées (autres dossiers du labo, exports du logiciel métier) à exclure explicitement du dépôt ?

---

## 11. Annexe : méthode de comptage

- Comptage de lignes Excel : lignes non vides par feuille via openpyxl (valeurs approximatives : en-têtes et lignes de séparation incluses).
- Lignes avec code : colonne code non vide et motif `[A-Z0-9]{3,}`. Lignes avec `#` : présence du caractère dans l'une des colonnes.
- Codes « incomplets » : tout code nettoyé qui ne respecte pas `[A-Z]{2}[A-Z0-9]{4,6}` (donc sans préfixe organe).
- Recoupement ADICAP : présence du code dans les ensembles D4, D5, D6 (suffixe), D7 de `adicap_ref.json`, et absence de date de fin de validité.
- PII : recherche de motifs sur la conversion texte de tous les .doc/.docx/.rtf, puis sur `textes_canoniques.json`. Aucune valeur identifiante n'est reproduite dans ce document.
- Aucun fichier hors `docs/v3/` n'a été modifié ; les conversions texte ont été produites dans le répertoire de travail temporaire de la session.
