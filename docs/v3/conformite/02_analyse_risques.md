# Analyse de risques logicielle (ISO 22367 / ISO 14971 : approche FMEA)

Objet : dangers lies a MARC en tant qu'aide a la redaction. Reference : ISO 22367 (gestion des risques en laboratoire medical), ISO 14971 (methode) ; alimente 5.6 et 8.5 d'ISO 15189:2022. Echelles : G (gravite) 1 a 5, O (occurrence) 1 a 5, D (detectabilite : 1 = detecte surement, 5 = non detecte) ; criticite C = G x O x D. Les notes sont des **estimations d'editeur** a recaler par le laboratoire sur ses cas ; elles ne sont pas des mesures.

| # | Danger | Cause | Effet clinique | G | Maitrise existante | O | D | C resid. | Preuve |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Fabrication (valeur, mesure ou conclusion non dictee) | Generation LLM | Compte rendu faux | 5 | Prompts restrictifs ; verification des chiffres non dictes (V2) ; stade pTNM non dicte (V3) ; ancrage de chaque element sur un empan de dictee ; trou visible plutot que valeur ; validation humaine obligatoire | 2 | 2 | 20 | `tests/campagne_v3.py` (violations V1-V8, objectif zero) |
| 2 | Negation inversee (« pas de » devient « presence de ») | Reformulation | Faux positif/negatif | 5 | Verificateur de negation ; V4 | 2 | 2 | 20 | `negation.py`, tests negation, campagne V4 |
| 3 | Confusion mm/cm ou unite changee | Normalisation, STT | Mesure x10 | 5 | Regle d'unites U1, plages plausibles par organe, alerte `unite` | 2 | 2 | 20 | verificateurs, tests |
| 4 | Mauvais organe / lateralite | Detection d'organe, STT | Attribution erronee | 5 | Detection d'organes explicite et affichee ; alerte d'incoherence ; relecteur sur modele distinct | 2 | 3 | 30 | tests coherence |
| 5 | Code ADICAP / SNOMED faux | Codeur | Codage errone, statistiques | 3 | Statuts certain / partiel / suggestion ; rejets explicites ; jamais de code invente (trou) ; code modifiable | 2 | 2 | 12 | tests codification |
| 6 | Champ obligatoire omis | Extraction incomplete | CR incomplet (items INCa) | 4 | Champs attendus par organe (kb), trou obligatoire, blocage de validation | 2 | 1 | 8 | `test_refus_avec_blocages_puis_derogation` |
| 7 | Terme medical mal transcrit (STT) | Voxtral | Terme deforme | 4 | Correcteur phonetique propose, ne decide pas ; corrections visibles et reversibles | 3 | 2 | 24 | `tests/test_projet_correcteur.py` |
| 8 | Chiffre/stade tumoral sur lesion benigne | Redaction | Fausse alerte tumorale | 5 | Regle « rien de tumoral sur benin », V5/V6 | 1 | 2 | 10 | campagne V5-V6 |
| 9 | Validation sans relecture (biais d'automatisation) | Facteur humain | Erreur non vue | 5 | Brouillon par defaut ; mention « a valider » ; blocages ; validation nominative et habilitee tracee | 3 | 3 | 45 | `POST /validations` |
| 10 | Texte modifie apres validation | Edition | CR libere different du valide | 4 | Empreinte du texte valide ; mention « modifie depuis la validation, a revalider » ; revision liee | 2 | 1 | 8 | `test_revision_liee_...` |
| 11 | Perte/alteration de la piste d'audit | Acces base, bug | Perte de preuve | 3 | Chaine par hash, ORM append-only, verification, export | 1 | 2 | 6 | tests chaine |
| 12 | Fuite de donnees medicales | Journalisation | Atteinte a la confidentialite | 5 | Whitelist metadonnees, tests d'absence de texte, aucune persistance de CR | 1 | 1 | 5 | `test_aucune_donnee_textuelle...` |
| 13 | Derive silencieuse apres changement de modele ou de base | Mise a jour fournisseur | Regression non vue | 4 | Modele epingle `mistral-large-2512`, version tracee, registre kb, plan de re-verification | 2 | 2 | 16 | `04_gestion_des_versions.md` |
| 14 | Indisponibilite du service | Panne LLM | Retard | 2 | Mode degrade N3 fidele a la dictee | 3 | 1 | 6 | `projet_de_secours` |
| 15 | Usage abusif comme aide au diagnostic | Mesusage | Decision clinique | 5 | Libelle « aide a la redaction », aucune conclusion inventee, formation et notice | 1 | 3 | 15 | `05_statut_reglementaire_hds.md` |

## Risque residuel
Les criticites residuelles les plus elevees sont le biais d'automatisation (#9), le mauvais organe (#4) et l'erreur STT (#7). Elles sont reduites par conception (trou visible, blocages, validation humaine tracee) mais **ne sont pas eliminables** : l'acceptabilite du risque residuel est une decision du laboratoire (5.6) apres sa propre verification (`03_plan_verification_validation.md`). Revoir cette analyse a chaque changement de modele, de base ou de gabarit, et a chaque non-conformite de gravite critique.
