# MARC v3 — Base de connaissances structurée (`kb_marc_v3.1`)

Date du build documenté : 2026-11-15. Agent « sources ». Schéma proposé par l'audit PO-1 (`01_audit_ressources.md`, section 7), implémenté tel quel avec les ajustements listés en section 6.

Cette base est une **aide à la rédaction** : elle fournit au pipeline des champs attendus, des plages, des règles, des codes candidats et des formulations de style. Elle ne pose aucun diagnostic. Elle ne contient **aucune donnée patient** et le pipeline v3 n'y écrit rien.

## 1. Contenu et reconstruction

| Élément | Chemin |
|---|---|
| Données générées (ne jamais éditer à la main) | `backend/kb/*.json` |
| Semences curées à la main (seules entrées éditables) | `backend/kb/seeds/*.json` (organes, lexique, règles, plages, détection) |
| Générateur | `scripts/build_kb.py` |
| Accès (lecture seule, repli gracieux) | `backend/projet/kb.py` (`get_kb()`) |
| Tests | `backend/tests/test_kb.py` (92 tests) |

Reconstruire : `venv/bin/python scripts/build_kb.py` (option `--date AAAA-MM-JJ` pour un build reproductible, `--sortie DIR` pour un build de test, `--strict` pour échouer aussi si une source sur disque contient de la PII). Le build est **reproductible octet pour octet** (testé) et **s'arrête** (code 1) sur une validation en échec : prov manquante, clé étrangère orpheline, code ADICAP obsolète ou inconnu, test de règle en échec, PII résiduelle.

## 2. Comptes par collection

| Collection | Fichier | Entrées |
|---|---|---|
| Sources (registre, dont non embarquées) | `sources.json` | 17 |
| Organes (45 + 1 générique) | `organes.json` | 46 |
| Prélèvements | `prelevements.json` | 7 |
| Champs (237 migrés + 64 INCa seuls + 2 génériques) | `champs.json` | 303 |
| Lexique phonétique (variantes STT : 812) | `lexique.json` | 1 099 |
| Thésaurus ADICAP 2024-10 complet | `adicap_thesaurus.json` | 9 683 concepts |
| Mappings lésion vers ADICAP (candidats) | `adicap_mappings.json` | 609 |
| Codes de la bible rejetés (inconnus du thésaurus) | `adicap_rejets.json` | 5 |
| Concepts SNOMED CT (tous `non_valide`) | `snomed.json` | 41 |
| Règles de cohérence (28 à condition exécutable, 76 tests embarqués) | `regles.json` | 34 |
| Plages de mesure plausibles | `plages.json` | 39 |
| Échelles et scores | `echelles.json` | 10 |
| Stations ganglionnaires IASLC | `stations.json` | 17 |
| Gabarits de sections (24 organes x 5 prélèvements) | `gabarits.json` | 120 |
| Exemples de style (purgés, verrouillés par organe) | `exemples_style.json` | 843 |
| Détection (expressions neutralisées) | `detection.json` | 1 |

Taille totale : 3,6 Mo. Chargement paresseux fichier par fichier (une collection n'est lue qu'au premier accès ; `organes` + détection : environ 15 ms).

**Provenance.** Chaque entrée porte `prov` `{source_id, localisation, version_source, date_extraction, fiabilite A-D, confiance 0-1, statut_validation, valide_par, date_validation, methode, remplace}`. Exception documentée : le thésaurus ADICAP (9 683 lignes positionnelles) porte une `prov_commune` (A, officiel) ; `kb.adicap_concept()` la complète avec la localisation de chaque ligne.

## 3. Ce qui est dans la base, collection par collection

- **Organes.** 23 organes des templates (ids stables `organe:poumon`...), plus 22 organes issus des lacunes de l'audit 4.1 (peau, thymus, surrénale, parathyroïde, os, articulation, placenta, rate, moelle, plèvre, péritoine, grêle/duodénum, voies biliaires, uretère, verge, vulve/vagin, cœur/vaisseaux, œil, oreille, hypophyse, muscle, nerf). Chaque organe a des synonymes **spécifiques**, des mots **faibles** (ne déclenchent jamais seuls), des codes ADICAP D3 vérifiés contre le thésaurus (106 codes D3 distincts référencés sur 138 feuilles D3), la topographie CIM-O, la structure SNOMED si connue, la classification à citer et un bloc `couverture` calculé au build.
- **Champs.** Migration des 237 champs des 23 templates vers des ids stables (`champ:sein.taille_tumorale`) avec concept transversal (`taille_tumorale`, `marges`, `ganglions`...), type de valeur (`enum`, `nombre_unite`, `enum_nombre`, `liste_structuree`, `texte_libre`...), unité, options, `plages`, drapeau `tumoral` et **matrice d'applicabilité** prélèvement x contexte lésionnel migrée de `specimen_type.py`. 134 champs sont rapprochés d'un item INCa 2011 (niveau `obligatoire_inca`), 64 items INCa sans équivalent sont ajoutés (dont type de prélèvement, côté, localisation, nécessaires à la règle C13). Règle métier appliquée : **aucun champ tumoral n'est applicable en contexte bénin** (testé pour tous les organes et prélèvements). Le curage ne porte que les champs ganglionnaires.
- **Lexique.** 1 099 termes : semences curées avec variantes STT (dont `barretis` pour Barety, seule variante observée sur le terrain, origine `observe_terrain`), 101 termes d'amorce Voxtral, 121 marqueurs et sigles, 169 organes D3 officiels, 709 libellés de lésions de la bible. Chaque terme et variante a une **clé phonétique française** (algorithme « Phonex-FR » de `projet/kb.py` : neutralise e/é/è, c/k/qu, s/ss/z, ph/f, doubles consonnes, lettres finales muettes, nasales, espaces et traits d'union). Les variantes générées par règles (accents, traits d'union, `ttf un`, `ki soixante-sept`, sigles épelés) ont une confiance de 0,4. `contexte_requis` empêche les corrections hors contexte (`FISH` n'est corrigé depuis « fiche » qu'avec « hybridation », « sonde »...). `KB.candidats_phonetiques(forme)` (ajout) renvoie les termes proches sans jamais décider d'une correction.
- **ADICAP.** Thésaurus 2024-10 complet (A). 609 mappings lésion vers code, **tous vérifiés actifs** (D4 non tumoral, D5 tumoral, D7 cytopathologie, D6 organe-spécifique), `exige_validation_pathologiste: true` partout. Les 5 feuilles perdues (SEIN, DERMATO, OS-ARTI, T mous, NEURO) sont reprises par lecture robuste des colonnes (193 formulations ajoutées). Trois mappings portent un contrôle de cohérence libellé/thésaurus (`PO` « Endomètre » vs OEUF - PRODUITS OVULAIRES, `GB` « Vulve » vs GLANDES DE BARTHOLIN : erreurs probables de la bible, à corriger par la pathologiste). Les 5 codes inconnus du thésaurus (`0471`, `H332`, `H530`, `I641`, `NMNOJ4`) sont dans `adicap_rejets`, jamais proposés.
- **Règles.** C1 à C17 de l'architecture cible (C17 ajoutée au catalogue C1-C16 demandé car présente dans la spec), règles d'unités et de calcul (U1 à U10 : hors plage, unité manquante, rapport x10 macro/conclusion, Ki67, SBR, Gleason, ISUP, Breslow...), sécurité (S1 champ tumoral sur bénin, S2 négation), codage (K1 à K3 dont « jamais de code obsolète »), qualité minimale (Q1, Q2, `a_valider`, sévérité `info`). Format JSON : `condition` en mini-DSL évaluable sans exécution de code (`KB.evaluer_regle`), `severite` alignée sur `Alerte.gravite`, `alerte_type` aligné sur `Alerte.type`. Une variable absente ne déclenche jamais une règle. Les règles C1, C10 à C14 et S2 sont **procédurales** (`detecteur`, pas de `condition`) : le comptage sur texte reste au code.
- **Plages mm/cm.** 19 plages génériques et 20 plages de taille tumorale par organe, avec lecture alternative en cm. Toutes **heuristiques non sourcées** (fiabilité C, `a_valider`) ; la fiche INCa poumon est la seule en cm (piège signalé dans la note de la plage poumon).
- **Gabarits.** Sections dans l'ordre CI-SIS (titre, clinique, extemporané, macroscopie ou matériel/technique en cytologie, microscopie, IHC, biologie moléculaire, conclusion obligatoire) et `champs_par_section`. Repli sur `gabarit:generique.<prélèvement>`.
- **Exemples de style.** 843 textes (653 purgés + 193 des feuilles perdues - 3 doublons), rattachés à un organe (`exemples_style(organe)` ne renvoie jamais un autre organe), `praticien_id` pseudonyme (`prat:A`), `pii_verifie` vrai, nombre de trous `#`.
- **SNOMED CT.** 41 concepts repris de `snomed.py` (22 codes de structures anatomiques distincts, 25 clés fusionnées par code, et 19 morphologies), tous `statut_validation = non_valide`, fiabilité C, `verifie_contre_release: false`, `edition: null`.

## 4. Couverture

| Axe | Résultat |
|---|---|
| Organes avec champs et gabarit spécifique | 23 / 45 (les 23 templates) |
| Organes avec au moins un exemple de style | 41 / 45 |
| Organes avec au moins un mapping ADICAP | 39 / 45 |
| Organes en repli générique (aucun champ propre) | 22 |

Organes les mieux dotés en exemples : ORL (120), peau (111), poumon (65), côlon-rectum (50). Les plus pauvres parmi les 23 templates : prostate (4 exemples, 1 mapping), pancréas (3), mélanome (6).

## 5. Lacunes connues

1. **22 organes sans champs obligatoires** : le pipeline retombe sur les 2 champs génériques (diagnostic lésionnel, dysplasie/malignité) et le gabarit générique. Vésicule biliaire et appendice n'ont que 2 champs chacun (hérité des templates).
2. **Aucune release SNOMED CT** : tous les codes sont des suggestions non vérifiées, sans terme français ni mapping lésion vers SNOMED.
3. **Pas de matrice de décision I/O** (pièce partielle ou complète) : reste dans `codage_d1_d2.json` (entrées `a_valider`).
4. **Mappings ADICAP** : 424 sur 609 sont « partiels » (lésion sans code organe D3, héritage de la bible) ; un mapping n'est jamais définitif.
5. **Prélèvement non déterminé pour 474 exemples sur 843** (heuristique prudente sur le libellé) : le verrouillage par organe reste valable, le tri par prélèvement non.
6. **Lexique** : une seule variante `observe_terrain` (aucune transcription brute de référence). Les autres sont générées ou saisies de mémoire, confiance 0,4 à 0,5.
7. **Éditions de classification** (TNM 8e partout) à faire confirmer par la pathologiste ; `staging[].statut = a_verifier`.
8. **Seuils qualité** (12 ganglions côlon, 10 curage sein) : source secondaire non vérifiée, règles `info` seulement.
9. **ICCR / CAP / OMS / TNM 9** non embarqués (licences) ; ils manquent pour les biomarqueurs récents (HER2 gastrique, MMR, PD-L1) hors des champs hérités des templates.
10. Les 5 feuilles perdues alimentent la base v3 mais **pas** `backend/data/textes_canoniques.json` (périmètre purge uniquement) ni `reports/canonical_texts.py` (v2).

## 6. Écarts au schéma PO-1 (assumés)

- Une collection `champs` unique par organe (champ + exigence fusionnés : `applicabilite`, `niveau`, `condition`) au lieu de deux collections catalogue/exigences ; le concept transversal (`concept`) tient le rôle du catalogue.
- `adicap` éclaté en `adicap_thesaurus`, `adicap_mappings`, `adicap_rejets` ; `stations` et `echelles` sont des fichiers distincts.
- `variantes` du lexique est une liste de chaînes (contrat `kb.py`) ; le détail `{forme, origine, confiance, cle, occurrences}` est dans `variantes_detail`.
- `KB()` sans argument est une base vide (repli N0, utilisé par `test_projet_pipeline.py`) ; `get_kb()` lit `backend/kb/` (ou `MARC_KB_DIR`).

## 7. Conformité et licences

**PII (P0).** `textes_canoniques.json` : 12 entrées sur 653 comportaient des données identifiantes (3 en-têtes patient avec nom, date de naissance, NIP et n° d'examen ; 2 marqueurs logiciels `TDCHECK` portant un numéro de dossier ; 5 phrases nommant des praticiens tiers ; 2 numéros de dossier et dates d'examen) et ont été purgées ligne ou phrase par phrase, le reste de la formulation est intact. Le champ `code` (code ADICAP complet, jusqu'à 14 caractères) est exclu des règles « numéro » pour ne pas détruire un code légitime. `scripts/build_kb.py` applique un scan **bloquant** à tout texte ingéré (15 familles de motifs : lignes patient, « né(e) le », NIP/IPP/INS, RPPS, numéros d'examen et de dossier, dates numériques et littérales, titre + nom, prénom + nom, téléphone, courriel, longs numéros) : purge automatique des lignes/phrases concernées puis re-scan ; un résidu arrête le build. La sortie complète est rescannée. Tests : 14 motifs détectés, 7 faux positifs écartés (dont « IPP ? » = inhibiteur de pompe à protons, et « au sein d'un » = dans), `textes_canoniques.json` et les semences à zéro violation. Limite : un nom de famille isolé, sans titre ni prénom connu, n'est pas détectable par motif.

| Source | Statut | Action |
|---|---|---|
| ADICAP 2024-10 (ANS) | Licence Ouverte 2.0, réutilisation commerciale permise | Aucune ; citer la version |
| INCa/SFP données minimales 2011 | Copyright INCa : usage personnel non commercial, courtes citations. Le dépôt ne contient qu'une **paraphrase structurée** | **À valider juridiquement** : accord écrit INCa avant production commerciale |
| ICCR | Copyright, commerce exclu | **Bloquant** : non embarqué ; contacter l'ICCR |
| SNOMED CT (SMT/ANS) | Licence affilié, pas de redistribution libre | **À valider juridiquement** : privilégier l'appel à l'API SMT plutôt qu'une copie locale |
| Bible, formulations canoniques, lexique de la pathologiste | Données du praticien | Accord d'usage et de redistribution à formaliser ; hébergement soumis au RGPD tant qu'un fichier source peut contenir des données patient (feuilles non encore relues) |
| Règles C1-C17, plages, stations, semences | Contenu interne, connaissance du domaine | Relecture par la pathologiste (tout est `a_valider`, sauf K3, `valide`) |

## 8. Utilisation par le pipeline

```python
from projet.kb import get_kb
kb = get_kb()
kb.detecter_organes(texte)                       # [{id, libelle, debut, fin, confiance}]
kb.champs("organe:poumon", "biopsie", "malin")   # contextes : benin | precancereux | malin | indetermine
kb.plage_mesure("organe:sein", "taille_tumorale")
kb.candidats_phonetiques("barretis")             # correcteur STT (jamais de correction sans contexte_requis)
kb.evaluer_regle("regle:c4_ganglions_envahis_inferieur_examines", {"ganglions_envahis": 3, "ganglions_examines": 2})
```

Prélèvements acceptés : `biopsie`, `piece` ou `piece_operatoire`, `cytologie`, `curage`, `None`. Contextes : `benin`, `precancereux`, `malin` (alias `infiltrant`), `indetermine`. Un organe inconnu renvoie les seuls champs génériques ; une base absente renvoie des valeurs vides (niveau de service N0), jamais d'exception.
