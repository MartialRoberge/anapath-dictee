# Matrice de conformite ISO 15189:2022 (clause par clause)

Legende responsabilite : **L** = laboratoire, **E** = editeur (Gilbert / MARC), **P** = partagee.
Intitules verifies sur les sommaires publics de la norme ; sous-clauses a recouper avec le texte officiel. Aucun texte normatif n'est reproduit.

| Clause | Intitule | Exigence (resume) | Fonctionnalite MARC | Preuve | Resp. |
|---|---|---|---|---|---|
| 4.2 | Confidentialite | Proteger les informations des patients | Aucune donnee medicale persistee cote serveur ; telemetrie et conformite whitelistees ; hashes sales pour les ids projet | `tests/test_telemetrie.py`, `tests/test_conformite.py::test_aucune_donnee_textuelle_dans_les_tables`, docs 07 | P |
| 5.6 | Gestion des risques | Identifier et maitriser les risques | Analyse FMEA du logiciel | `02_analyse_risques.md` | P (E fournit, L integre a sa cartographie) |
| 6.2 | Personnel (competence, habilitation) | Seul un personnel habilite libere les resultats | Role « valideur » par habilitation geree par l'admin ; validation refusee (403) sans habilitation ; changement d'habilitation journalise | `test_refus_sans_habilitation`, `test_habilitation_changement_journalise_et_revocable` | P (L designe les habilites, E applique) |
| 6.4 | Equipements | Equipements/systemes verifies avant mise en service | Plan de verification rejouable | `03_plan_verification_validation.md`, `tests/campagne_v3.py` | P |
| 6.8 | Produits et services fournis par l'exterieur | Maitriser les prestataires | Fournisseurs LLM et hebergeur identifies, modeles epingles (`mistral-large-2512`), version tracee ; contrats/HDS a la charge de l'editeur | bloc `tracabilite.modeles`, `05_statut_reglementaire_hds.md` | E (L evalue le fournisseur MARC) |
| 7.2 | Processus pre-examen | Informations cliniques/prelevement | Contexte et prelevement detectes ; trou visible si information requise manquante | alertes `manquant`, campagne v3 | L (dossier), E (detection) |
| 7.3 | Processus d'examen | Methodes validees/verifiees | MARC n'est pas un processus d'examen ; il met en forme le resultat dicte par le pathologiste | statut reglementaire | L |
| 7.4 | Processus post-examen (compte rendu, liberation, amendement) | Revue et liberation du compte rendu par une personne autorisee ; amendements identifies | Projet **brouillon** tant que non valide ; validation tracee (qui, quand, versions, empreinte) ; revision = nouvelle validation liee a la precedente ; blocages (alerte bloquante, trou obligatoire) sauf derogation par enum | `POST /v3/conformite/validations`, `test_refus_avec_blocages_puis_derogation`, `test_revision_liee_a_la_validation_precedente` | P |
| 7.5 | Travaux non conformes | Detecter, traiter, enregistrer | Signalement de non-conformite (categories enum, gravite) ; liste admin ; lien au projet par hash et aux versions | `test_non_conformite_enum_et_liste_admin` | P |
| 7.6 | Maitrise des donnees et gestion de l'information | Systeme d'information valide, modifications maitrisees, integrite, tracabilite | Bloc `tracabilite` (versions pipeline/kb/modeles, empreintes) ; journal chaine ; registre kb ; maitrise des changements | `test_bloc_tracabilite_du_projet`, `test_chaine_intacte_puis_alteration_detectee`, `04_gestion_des_versions.md` | P |
| 7.7 | Reclamations | Traiter les reclamations | Canal « signaler une non-conformite » alimente l'analyse | idem 7.5 | L |
| 7.8 | Planification de la continuite | Plans de continuite | Mode degrade N3 : projet minimal fidele a la dictee si le pipeline echoue ; export DOCX | `projet_de_secours`, tests pipeline | P |
| 8.2 | Documentation du systeme de management | Documenter | Dossier `docs/v3/conformite/` | ce dossier | P |
| 8.3 | Maitrise des documents du systeme de management | Documents approuves, versions, retrait | Registre kb : brouillon, approuvee, en service, retiree ; approbateur et date ; une seule version en service | `test_registre_kb_cycle_de_vie` | P |
| 8.4 | Maitrise des enregistrements | Enregistrements identifiables, proteges, conserves, tracables | Journal append-only chaine par hash ; verification ; export CSV ; ORM refuse update/delete | `test_chaine_intacte...`, `test_suppression_d_une_entree_detectee`, `test_orm_refuse_la_modification_du_journal`, `test_export_csv_et_lecture` | P (L definit la duree de conservation) |
| 8.5 | Actions face aux risques et opportunites | Traiter les risques | FMEA et risque residuel | `02_analyse_risques.md` | P |
| 8.6 | Amelioration | Ameliorer en continu | Telemetrie agregee (rapports admin), non-conformites, recommandations | `docs/v3/07_telemetrie.md` | P |
| 8.7 | Non-conformites et actions correctives | Traiter, enregistrer, evaluer l'efficacite | Statut de la non-conformite (ouverte, en analyse, cloturee) trace dans le journal ; l'action corrective elle-meme est decrite dans le systeme qualite du labo | `PATCH /v3/conformite/non-conformites/{id}` | P |
| 8.8 | Evaluations (indicateurs, audits internes) | Indicateurs qualite, audits | Export CSV du journal pour audit interne ; verification d'integrite ; indicateurs de telemetrie | `/audit/export.csv`, `/audit/verification` | L (E fournit les donnees) |
| 8.9 | Revue de direction | Revue periodique | Elements d'entree : non-conformites par categorie, journal de versions | `GET /v3/conformite/non-conformites` | L |

## Exigences COFRAC
Referentiel SH REF 02 (rev. 08, « Exigences pour l'accreditation selon la norme NF EN ISO 15189:2022 ») ; note SH INF 04 sur la transformation numerique ; SH INF 05 (correspondance 2012/2022). Le detail des exigences informatiques de la revision 08 n'a pas pu etre consulte dans le cadre de ce travail : **a confronter au document COFRAC** avant audit. Aucune reference « LAB GTA » n'a pu etre confirmee.

## Contexte securite
ISO/IEC 27001 (SMSI) et HDS (hebergement de donnees de sante) concernent l'editeur et l'hebergeur ; voir `05_statut_reglementaire_hds.md`.
