# MARC v3 - Veille sources publiques (PO-3)

Date d'accès : 2026-11-15. Auteur : agent veille PO-3. Données structurées dans `docs/v3/sources_web/` :
`catalogue_sources.json`, `inca_donnees_minimales.json`, `nomenclatures_scores.json`, `unites_conversions.json`.

Légende de confiance : **vérifié** = lu à la source pendant la veille ; **recherche** = confirmé par résultat de recherche web, source non lue en entier ; **interne** = connaissance du domaine non re-vérifiée en ligne (à faire valider par un pathologiste).

## 1. Conclusions

1. **Seule source libre et embarquable de premier rang : le thésaurus ADICAP** (ANS, Licence Ouverte Etalab v2, XLSX/OWL, 9 511 concepts, version 2024-10 vue sur BioPortal). Priorité P0 pour le codeur ADICAP. (recherche)
2. **Les données minimales INCa/SFP (déc. 2011)** sont la référence réglementaire française pour les champs obligatoires. J'ai lu le PDF et extrait les 10 organes prioritaires (JSON). Limite : version 2011, antérieure à TNM 8/9 et à l'OMS 5e édition, et sous copyright INCa (usage perso non commercial et courtes citations libres ; autre usage sur demande à publication@institutcancer.fr). On livre donc une **paraphrase structurée**, et on demande l'accord INCa avant production. (vérifié)
3. **ICCR** est le meilleur référentiel moderne (mis à jour, aligné UICC TNM 9), mais la notice de copyright limite l'usage (CR chirurgicaux, enseignement, recherche non lucrative ; commerce exclu). Verrou juridique à lever avant embarquement. (recherche)
4. **CAP, UICC TNM 9, OMS Blue Books, AJCC** : propriétaires. MARC ne peut pas les embarquer ; il peut seulement citer l'édition utilisée et exploiter des règles numériques. (recherche)
5. **SNOMED CT** : accès en France via licence "affilié" gratuite de l'ANS (SMT, édition nationale française publiée fév. 2025). Pas de redistribution libre ; usage hors France = licence du pays concerné. A clarifier avant d'intégrer des codes dans le produit. (recherche)
6. **CCAM / cotation, CIM-O-3, HAS** : recherches non concluantes sur la licence et sur le contenu. Rien n'est affirmé ; ces points sont listés comme "à vérifier".

## 2. Catalogue (extrait ; détail dans `catalogue_sources.json`)

| Source | Éditeur | Version | Licence / embarquable | Fiabilité | Extraction MARC | Prio |
|---|---|---|---|---|---|---|
| Données minimales CR anapath (30 fiches) | INCa + SFP | déc. 2011 | Copyright INCa ; non en l'état | haute, ancienne | champs obligatoires, énumérations, unités | P0 |
| Thésaurus ADICAP | ANS / ADICAP | 2024-10 | LOv2 ; **oui** | haute | table de codes, alignement CIM-O3 | P0 |
| ICCR datasets | ICCR | continu, TNM 9 | copyright, non commercial | haute, à jour | core/non-core, listes à jour | P0 |
| UICC TNM 9e éd. | UICC / Wiley | 2025 ; applicable 01/01/2026 | propriétaire ; non | très haute | édition à citer, règles pT/pN | P0 |
| Grades (Gleason/ISUP, SBR, Breslow, Ki-67) | publications | - | règles de calcul | haute (interne) | vérificateurs arithmétiques | P0 |
| SNOMED CT intl + FR | SNOMED Int. / ANS | FR nationale fév. 2025 | licence affilié ; non redistribuable | très haute | concepts via API SMT | P1 |
| CAP Cancer Protocols / eCC | CAP | annuelle | propriétaire, licence payante | haute | consultation seule | P1 |
| OMS Blue Books 5e / 6e | IARC | 5e 2019-2024 ; 6e 2026 | copyright IARC ; métadonnées seules | très haute | édition utilisée | P1 |
| Volet CR-ACP (CI-SIS) | ANS | non récupéré | à confirmer | haute | structure d'export CDA/FHIR | P1 |
| CIM-O-3 | OMS | 3e éd. | non vérifiée | haute | codes topo/morpho (via ADICAP) | P1 |
| Bethesda thyroïde (2023), Milan salivaire (2023), Paris urine (2022) | éditeurs scientifiques | 3e / 2e / 2e éd. | nomenclature citable | haute | catégories diagnostiques | P1-P2 |
| CCAM, actes ACP (préfixe QX) | Assurance Maladie / ATIH | - | non vérifiée | haute | suggestion de cotation (hors cœur) | P2 |
| SOR-FNCLCC/HAS, Sydney, Vienne, CIM-10 FR, AJCC | HAS, etc. | - | non vérifiée | variable | contexte | P2-P3 |

## 3. Données minimales INCa extraites (10 organes)

Organes couverts : sein (biopsie et pièce), côlon-rectum, poumon, prostate (biopsies et pièce), mélanome cutané, thyroïde, vessie (cystectomie), rein, col utérin + corps utérin (endomètre), estomac. Chaque fiche contient un entête commun (identification patient et préleveur, pathologiste, signataire), puis : type de prélèvement, organe/côté/localisation, type histologique, grade, extension/limites, facteurs pronostiques (emboles, péri-nerveux, récepteurs, etc.), critères pT/pN (taille, infiltration, ganglions envahis/examinés), pTNM avec l'édition UICC. Détail champ par champ, avec unités et conditions, dans `inca_donnees_minimales.json`.

Observations utiles pour les vérificateurs :

- **Unités** : mm presque partout ; **cm uniquement pour la taille tumorale du poumon** (piège mm/cm). Pourcentages pour l'infiltration du myomètre ; mitoses/mm² pour le mélanome.
- **Grades obsolètes dans la fiche 2011** : Fuhrman (rein, remplacé par le grade ISUP/OMS), vessie "OMS 2004". Le pipeline doit signaler l'édition OMS/TNM utilisée plutôt que figer la liste 2011.
- **Absents des items minimaux 2011** (à ajouter comme champs recommandés via ICCR/CAP) : Ki-67, MMR/MSI, PD-L1/EGFR/ALK, HER2 gastrique, niveau de Clark. RTUV et biopsies vésicales non couvertes.
- Les données d'identification relèvent de l'établissement préleveur ; le pathologiste ne les renseigne que si elles lui sont transmises. Cohérent avec la contrainte MARC : aucune donnée médicale persistée.

## 4. Points juridiques et décisions à prendre

1. Demander à l'INCa l'autorisation de réutiliser la structure des fiches dans un produit commercial (publication@institutcancer.fr). En attendant, ne livrer que des libellés paraphrasés (fait dans le JSON).
2. Contacter l'ICCR sur l'usage dans un SaaS payant (notice : commerce exclu).
3. Clarifier le statut d'affilié SNOMED CT pour Gilbert (ans-terminologies@esante.gouv.fr) ; privilégier l'appel à l'API du SMT plutôt qu'une copie locale.
4. Vérifier sur la page ANS la dernière version de l'ADICAP et la mention exacte de licence (LOv2 annoncée) ; télécharger via le site de l'ANS, ne pas se fier au miroir BioPortal.
5. Chercher auprès de l'INCa/SFP une version postérieure à 2011 : non trouvée dans cette veille, non exclue.

## 5. Limites de cette veille

- WebSearch/WebFetch uniquement ; les licences n'ont pas été lues dans leur texte contractuel complet. Validation juridique requise.
- Page du volet CR-ACP de l'ANS : fetch vide, non exploité. Page HAS SOR-FNCLCC : contenu non récupéré. Licence CIM-O-3 et règles de cotation CCAM : non établies.
- Les règles de `nomenclatures_scores.json` (Gleason/ISUP, SBR, Breslow, Vienne, Paris) viennent de la connaissance du domaine ; seules les éditions de Bethesda 2023 et Milan 2023 ont été confirmées en ligne. Aucun taux de risque de malignité n'est fourni.
- Les plages plausibles de `unites_conversions.json` sont des heuristiques non sourcées.
- Rien n'a été lu en dehors de l'INCa en texte intégral ; tout le reste repose sur des résumés de recherche.

## 6. Liens clés (accès 2026-11-15)

- INCa données minimales 2011 : https://www.cancer.fr/Media/files/comptes-rendus-d-anatomopathologie-donnees-minimales-a-renseigner-pour-une-tumeur-primitive
- ADICAP (ANS) : https://esante.gouv.fr/produits-services/cgts/adicap et fiche https://esante.gouv.fr/sites/default/files/media_entity/documents/cgts_sem_adicap_fiche-detaillee.pdf
- SNOMED CT France : https://esante.gouv.fr/produits-services/cgts/snomed-ct ; SMT https://smt.esante.gouv.fr/
- ICCR copyright : https://www.iccr-cancer.org/copyright/ ; datasets https://www.iccr-cancer.org/datasets/
- CAP protocols : https://www.cap.org/protocols-and-guidelines/cancer-reporting-tools/cancer-protocol-templates
- UICC TNM 9 : https://www.uicc.org/news-and-updates/25-7-announcements/9th-edition-uicc-tnm-classification-malignant-tumours-now-available
- IARC politique d'accès : https://shop.iarc.fr/pages/purchase-and-access-policy
- Bethesda 2023 : https://pubmed.ncbi.nlm.nih.gov/37427847/ ; Milan 2023 : https://pubmed.ncbi.nlm.nih.gov/37971186/
