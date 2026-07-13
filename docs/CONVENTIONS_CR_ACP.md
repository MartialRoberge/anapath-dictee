# Conventions de rédaction des CR d'anatomopathologie (France) — référence de calibration

> Base de calibration de MARC (prompt + recall des champs obligatoires). Colonne
> vertébrale : **Volet CR-ACP du CI-SIS** (ANS, 2018), qui transpose les items
> minimaux **INCa/SFP** et les comptes-rendus fiches standardisés (CRFS).
> Sources maîtresses :
> - CI-SIS CR-ACP : https://esante.gouv.fr/sites/default/files/media_entity/documents/ci-sis_cr_acp_spec-fonctionnelles_20180419_v1.5_0.pdf
> - Items minimaux INCa & CRFS (SFP) : https://www.sfpathol.org/documents-publics-items-minimaux-inca-et-compte-rendus-fiches-standardises-crfs.html
> - INCa données minimales : https://www.e-cancer.fr

## 1. Structure (CI-SIS)
En-tête structuré + corps en 6 sections, **seule la Conclusion-Diagnostic est
obligatoire** : (1) Informations cliniques, (2) Extemporané si réalisé,
(3) Macroscopie, (4) Microscopie, (5) **Conclusion (obligatoire)**, (6) Techniques
(IHC/biomol — pas de section propre pour l'IHC, reprise en micro/conclusion).
Ordre fixe : clinique → (extempo) → macro → micro → (techniques) → conclusion.

## 2. Titre
**Pas de convention de titre verbeux par organe.** Le référentiel sépare : *type de
document* normalisé (« CR d'anatomie et de cytologie pathologiques ») + *nature du
prélèvement* portée dans un champ dédié (procédure + organe + latéralité). Pratique
de terrain la plus fréquente = titre court = **nature du prélèvement** (ex.
« Biopsies bronchiques », « Tumorectomie du sein gauche + ganglion sentinelle »).
→ Éviter « EXAMEN ANATOMOPATHOLOGIQUE DE… » comme gabarit systématique verbeux.

## 3. Multi-prélèvements (le point délicat)
> « Le paragraphe est répétable selon le nombre de prélèvements communiqués » (CI-SIS).

Chaque pot = **entrée séparée**, numérotée, décrite (fragments, mesures, blocs,
« inclus en totalité »), **propagée jusqu'à la conclusion** ; **jamais de fusion
inter-pots**. Toujours restituer « X prélèvements, Y fragments ». Cas emblématique :
**biopsies prostatiques en sextants (12 carottes, un pot par site)** → rendu
**cible par cible** (site, nb carottes, Gleason/ISUP, longueur envahie mm/%).
→ Valide le correctif MARC « N biopsies = N blocs ».

## 4. Style macro/micro
**Phrases complètes, courtes, impersonnelles** (présent de description, pas de
« je »). Pas de puces dans macro/micro ; listes réservées aux facteurs pronostiques
de la conclusion. Macro : contenant → nature → nb fragments/pièce → dimensions
(mm/cm) → poids → couleur/consistance → orientation/encrage → échantillonnage.
Micro : architecture → cytologie → différenciation/grade → invasion (emboles,
engainements) → limites → tissu non tumoral.

## 5. Ganglions / curage (champs normalisés CI-SIS)
Toujours : **nombre examinés**, **nombre envahis**, **rupture capsulaire Oui/Non**,
formulation **N+/T** + **pN (TNM UICC)**. Restituer **par loge/station**. Ne jamais
écrire « ganglions négatifs » sans le dénominateur.
- Seuils qualité : côlon/rectum **≥ 12** ganglions ; sein **≥ 10**.
- Sein — taille métastase : macro > 2 mm ; micro 0,2–2 mm (pN1mi) ; CTI ≤ 0,2 mm
  (pN0i+) ; préciser méthode (HES vs IHC anticytokératine).

## 6. Données minimales par organe (INCa/SFP) — checklist recall
- **Sein (infiltrant)** : type OMS ; **grade SBR/Elston-Ellis** (tubes + pléomorphisme
  + mitoses/10 champs) ; taille ; **emboles** ; CIS associé (type/grade/taille) ;
  **limites + distances** ; **statut ganglionnaire** (macro/micro/CTI) ; **RE, RP (%),
  HER2, Ki67** ; pTNM.
- **Côlon-rectum** : type OMS + grade ; **pT** ; **ganglions envahis/prélevés ≥ 12** ;
  **emboles** ; **engainements périnerveux** ; **marges R0/R1/R2** ; rectum → **CRM** ;
  **MSI/dMMR** + **RAS/BRAF**.
- **Poumon** : type OMS ; taille/extension/plèvre/limites ; emboles ; engainements ;
  **pTNM** ; biomarqueurs (EGFR, ALK, ROS1, PD-L1) ; biopsie → préserver le matériel.
- **Prostate (biopsies)** : par cible — type ; **Gleason (majoritaire+plus élevé, 3+4≠4+3)** ;
  **ISUP 1–5** ; **longueur envahie mm/%** ; nb carottes+ ; **infiltration périnerveuse**.
- **Mélanome** : type anatomoclinique ; **Breslow (mm)** ; **ulcération** ; **index
  mitotique/mm²** ; **marges** ; +/- Clark, régression, emboles, microsatellites ; AJCC.

## Réglages retenus pour le prompt
1. Conclusion = seule section obligatoire ; ne jamais inventer une macro non fournie.
2. Ordre fixe des sections.
3. Boucle par prélèvement (nb pots = nb blocs), numérotation propagée, pas de fusion.
4. Ganglions : ratio N+/T + rupture capsulaire + pN systématiques ; seuils sein/côlon.
5. Conclusion = données minimales INCa codables de l'organe (checklist ci-dessus).
6. Style : phrases complètes impersonnelles, pas de puces en macro/micro.
7. Titre sobre — nature du prélèvement, pas de gabarit verbeux par organe.
