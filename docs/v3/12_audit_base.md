# Audit de la base de donnees MARC (rien n'est execute)

Rapport de lecture, etabli sur le code (`backend/db_models.py`, `backend/etude/models.py`, routes) et valide sur une base Postgres de test reproduisant le schema de la production (commit `4997b39` + donnees anciennes). **Aucune donnee de production n'a ete lue ni modifiee. Aucun DROP / DELETE / TRUNCATE n'existe dans le code ajoute.** Les migrations passent par `backend/database.py` (`create_all` puis ajout des colonnes manquantes), additives et idempotentes. Tout ce qui est « a supprimer » est ici, pour decision.

## 1. Les tables, leur role, leur usage par la v3
| Table | Role | Utilisee par la v3 ? | Recommandation |
|---|---|---|---|
| `users` | Comptes (email, hash, role, derniere connexion) | **Oui** (auth, admin) | Garder |
| `organizations` | Cabinets/labos | Non. Jamais ecrite par le code (aucun `Organization(...)`), `users.organization_id` reste vide | Garder (vide), supprimable apres accord si aucun usage commercial prevu |
| `business_rules` | Regles metier par organisation | Non. Jamais ecrite | Supprimable apres accord (la v3 porte ses regles dans la base de connaissances `backend/kb`) |
| `reports` | CR de l'ancienne version : **texte medical** (`raw_transcription`, `structured_report`) + `completeness_warnings` | Non (la v3 ne stocke aucun CR : historique local au navigateur). Lue par l'admin v3 pour activite et avis, sans le texte | **Archiver** (export chiffre) puis decision ; contient des donnees de sante potentielles |
| `report_exports` | Historique des exports de l'ancienne version | Non. Jamais ecrite (aucun `ReportExport(...)`) | Supprimable apres accord |
| `audit_log` | Journal de l'ancienne version (creation/modif/feedback/suppression de CR) | Non. Remplace par `conformite_audit`. Ecrit uniquement par `routes_reports.py` | **Archiver** : trace d'activite historique, pas de chainage |
| `telemetrie_evenements` | Usage v3 (whitelist, aucun texte libre) | **Oui** | Garder (envisager une purge par anciennete, voir plan) |
| `conformite_audit` | Journal chaine par hash, append-only (ISO 15189 8.4) | **Oui** | Garder, ne jamais modifier |
| `conformite_habilitations` | Valideurs habilites (6.2) | **Oui** | Garder |
| `conformite_validations` | Validations de CR (empreinte, versions) | **Oui** | Garder |
| `conformite_kb_versions` | Registre des versions de la base de connaissances | **Oui** | Garder |
| `conformite_non_conformites` | Ancien circuit des non-conformites | **Plus ecrite** : lues/ecrites desormais dans `signalements`. Contenu recopie au demarrage (marqueur `origine_nc_id`) | **Archiver**, puis supprimable apres accord quand la recopie est verifiee (controle `recopie_non_conformites`) |
| `signalements` (**nouvelle**) | Circuit unique de signalement (dysfonctionnement, erreur de projet, amelioration, non-conformite ISO) | **Oui** | Garder |
| `etude_sessions`, `etude_dossiers`, `etude_prelevements`, `etude_propositions`, `etude_questions`, `etude_pauses`, `etude_revisions_decision` | Donnees de recherche de l'etude MARC-ACP (decisions, temps, textes proposes/valides) | Non (l'etude est instrumentee par l'ancienne interface). Lues par `/v3/admin/etude` et l'export | **Garder** : donnees de recherche, ne pas toucher sans decision scientifique |
| `etude_reponses_questionnaire` | Reponses aux questionnaires (F-SUS, PDQI-9, intention...) | Non, lue par l'admin v3 (retours libres selectionnes) | **Garder** |
| `etude_ergonomie` | Releves d'usage de l'interface par zone | Non | **Garder** (donnees de recherche) |

Note : `alembic/` contient une seule migration initiale (`001_initial_schema.py`) et n'est pas utilisee en production ; le schema est entretenu par `database.py`. Il ne reflete plus la base.

## 2. Doublons, donnees de test, colonnes fourre-tout
- **Deux circuits de retour parallele** (avant ce chantier) : telemetrie `feedback` et `conformite_non_conformites`. Maintenant : note rapide = telemetrie ; tout signalement = `signalements`. Le controle `signalements_en_double` surveille les doublons residuels.
- **Comptes en double par casse** : `users.email` est unique mais sensible a la casse (`Bob@x.fr` et `bob@x.fr` coexistent). Controle `doublons_comptes`. L'inscription et la connexion comparent l'email tel quel : un doublon de casse est possible. A traiter par une decision (fusion, voir plan etape 4).
- **Comptes de test** : tout email en `@example.com` (controle `comptes_de_test`). Verifier aussi a la main les comptes de demonstration crees par les scripts (`scripts/reset_password.py`).
- **Dossiers d'etude exclus** (`etude_dossiers.exclu`) : essais ou saisies aberrantes, conserves a dessein et exclus des taux ; l'export les inclut avec leur motif.
- **`reports.completeness_warnings` (colonne fourre-tout)** : colonne `Text` censee contenir des alertes de completude, mais qui porte en pratique du JSON avec : `feedback` (note 1 a 5, commentaire, horodatage), `corrections` (liste de paires avant/apres = **texte medical complet**), et, a l'origine, des avertissements. Un meme champ mele donc donnees d'usage et donnees de sante, sans schema, et ne se filtre pas en SQL. L'admin v3 n'en lit que la clef `feedback`. Recommandation : ne pas la modifier sur place ; extraire les `feedback` vers une table dediee (ou vers `signalements`/une table `avis`) lors d'un chantier decide, et traiter `corrections` comme donnee de sante a archiver.
- **Doublon structurel `etude_dossiers.transcription`/`cr_propose`/`cr_valide` et `reports.raw_transcription`/`structured_report`** : le meme CR peut etre stocke deux fois (`etude_dossiers.rapport_id` les relie). Donnees de sante dans les deux.
- **Tables jamais ecrites** (controle `tables_jamais_ecrites`, informatif) : `organizations`, `business_rules`, `report_exports`, et les tables `etude_*` ou `conformite_*` tant qu'elles sont vides.

## 3. Branchement de bout en bout

### Appels de `frontend/src/v3` et existence cote backend
| Appel | Fichier front | Route backend | Statut |
|---|---|---|---|
| `POST /v3/projets` (SSE), `/v3/projets/audio` (champ `audio`), `/v3/projets/iterer`, `/v3/projets/export/docx`, `GET /v3/kb/sources/{id}` | `lib/api.ts` | `projet/routes.py` | OK, formes concordantes |
| `POST /transcribe` (champ `file`, reponse `raw_transcription`) | `lib/api.ts` | `main.py` | OK (**seule route de l'ancienne API encore utilisee par la v3**) |
| `POST /v3/telemetrie/evenements` | `telemetry.ts` | `telemetrie/routes.py` | OK |
| `GET /v3/conformite/moi`, `POST /generations`, `POST /validations`, `POST /non-conformites` | `lib/conformite.ts` | `conformite/routes.py` | OK ; `/non-conformites` ecrit desormais dans `signalements` (meme reponse `{id, statut}`) |
| `GET /v3/admin/telemetrie/synthese`, `/recommandations` | `admin/api.ts` | `telemetrie/routes.py` | OK |
| `POST /auth/login`, `/auth/register`, `/auth/refresh`, `GET /auth/me` | `hooks/useAuth` (importe par `V3App.tsx`) | `routes_auth.py` | OK |

Aucune route appelee par la v3 n'est absente ; aucune correction de forme n'a ete necessaire. **Manque cote front (a brancher par l'agent frontend)** : appel de `POST /v3/signalements` (formulaire de signalement unifie), et de toutes les routes `/v3/admin/*` du contrat (`11_contrat_admin.md`) ; aujourd'hui `signalerNonConformite` reste branche sur `/v3/conformite/non-conformites`, qui fonctionne et alimente `signalements`.

### Routes backend qui ne seront plus appelees une fois l'ancienne interface retiree (non supprimees)
**A garder (donnees de recherche, export, conformite)**
- `GET /admin/etude/synthese`, `/dossiers`, `/dossiers/{id}`, `POST /dossiers/{id}/exclusion`, `GET /export`, `/export.xlsx`, `GET /admin/etude/ergonomie` : analyse et export de l'etude (l'admin v3 y renvoie).
- `DELETE /admin/etude/dossiers/{id}` : destructif, a garder protege (admin) ; l'usage doit rester une decision humaine.
- `POST /auth/*`, `GET /auth/me`, `GET /health`, `POST /transcribe` : utilises par la v3.
- `DELETE /reports/{id}` (droit a l'effacement RGPD) : a garder tant que `reports` contient des donnees.

**Devenues mortes avec l'ancienne interface (a retirer du code apres accord, jamais du schema)**
- Ancienne API de redaction : `POST /format`, `/iterate`, `/sections`, `/adicap`, `/snomed`, `/export` (`main.py`) et les moteurs `reports/` qui les servent (dont `reports/gilbert_engine.py`, appel distant Lexia/Gilbert si `REPORT_ENGINE=gilbert`).
- Historique de l'ancienne version : `POST /reports`, `GET /reports`, `GET /reports/{id}`, `PUT /reports/{id}`, `POST /reports/{id}/feedback`.
- Ancien admin : `GET /admin/reports`, `/admin/stats`, `/admin/corrections`, `/admin/audit` (remplaces par `/v3/admin/*`).
- Instrumentation de l'etude (ecrit les donnees de recherche depuis l'ancienne interface) : `POST /etude/sessions`, `/etude/sessions/{id}/cloture`, `/etude/dossiers`, `/etude/dossiers/{id}/{vues|pauses|cloture|export|abandon|exclusion|ergonomie}`, `/etude/propositions/{id}/{vue|decision}`, `GET /etude/questionnaires/{nom}`, `POST /etude/questionnaires`, `DELETE /etude/dossiers/{id}`. **Decision necessaire** : si l'etude continue, la v3 doit reprendre cette instrumentation avant retrait ; sinon ces routes deviennent mortes mais les tables `etude_*` restent a conserver.
- Colonne `users.organization_id` / `organizations` / `business_rules` : vestiges sans route.

### Webhooks, taches de fond, appels externes
- **Aucun webhook sortant** : confirme. Le seul mot « webhook » est un commentaire (`reports/engine.py`, ligne 20). Aucun `BackgroundTasks`, planificateur, thread ni file de messages. Aucun Stripe actif (`organizations.stripe_customer_id` n'est jamais lu).
- Taches asyncio : `projet/routes.py` (`create_task` du pipeline SSE : annulee si le client se deconnecte, drainee par la file, aucune tache orpheline) ; `projet/orchestrateur.py` (extraction en parallele, attendue par `await`).
- Appels externes, tous synchrones a la demande : Voxtral (STT, `transcription.py`), Mistral (`llm/mistral.py`, `projet/llm_client.py`), Gilbert/Lexia seulement si `REPORT_ENGINE=gilbert` (ancien chemin). Clients `httpx` fermes a l'arret (`close_httpx_client`, `engine.aclose`).
- Au demarrage : `create_tables()` (create_all + colonnes manquantes + recopie des non-conformites, en transaction a part, jamais bloquante).

## 4. Plan de nettoyage (a decider par le proprietaire ; rien n'est execute)
| Etape | Action | Risque |
|---|---|---|
| 0 | **Sauvegarde complete** de la base Postgres (pg_dump) + export de l'etude (`/admin/etude/export`) avant toute etape | Nul ; prerequis |
| 1 | Deployer ce chantier (additif : table `signalements`, recopie des NC). Verifier `/v3/admin/sante` : `recopie_non_conformites` = ok | Faible : une table et des lignes en plus ; la recopie est idempotente |
| 2 | Retirer l'ancienne interface du frontend (`frontend/`), garder les routes backend | Faible : aucun changement de donnees |
| 3 | Retirer du code les routes mortes (liste ci-dessus) apres accord, en gardant les modeles/tables | Moyen : `DELETE /reports/{id}` (RGPD) et l'instrumentation d'etude a conserver si besoin |
| 4 | Comptes : revoir les doublons de casse (fusion manuelle = reaffecter reports/telemetrie/etude puis desactiver le doublon, `is_active=false`, sans supprimer) ; desactiver les comptes `@example.com` | Moyen : la fusion touche des donnees rattachees a l'utilisateur ; faire par script revu, apres sauvegarde |
| 5 | Normaliser les emails (minuscule) a l'inscription/connexion, puis index unique insensible a la casse | Moyen : migration de contrainte, a faire apres l'etape 4 |
| 6 | Extraire `reports.completeness_warnings.feedback` vers une table dediee ; archiver `corrections` (donnee de sante) | Moyen : lecture seule d'abord ; ne jamais ecraser la colonne |
| 7 | Archiver `reports`, `audit_log`, `conformite_non_conformites` (export chiffre hors base) | Faible si fait par export |
| 8 | Supprimer, **uniquement apres accord ecrit et archivage verifie** : `conformite_non_conformites` (recopiee), `report_exports`, `business_rules`, `organizations` (+ colonne `users.organization_id`) | Eleve (irreversible) : une table supprimee ne se recupere que par sauvegarde |
| 9 | Politique de retention : purge de `telemetrie_evenements` au-dela d'une duree a fixer | Moyen : perte d'historique statistique ; a decider (la conformite ISO n'impose rien sur la telemetrie) |
| 10 | Decider du sort de `reports` (texte medical) a l'issue de la periode legale, et des champs texte de `etude_dossiers` (anonymisation ?) | Eleve : donnees de recherche et de sante |

## 5. Points qui demandent une decision du proprietaire
1. **L'etude MARC-ACP continue-t-elle ?** Si oui, l'instrumentation (`/etude/*`) doit etre reprise par la v3 avant de retirer l'ancienne interface ; si non, les routes sont mortes mais les donnees restent.
2. **Sort de `reports`** (texte medical de l'ancienne version) : archiver puis effacer apres quelle duree ? Le `DELETE /reports/{id}` (droit a l'effacement) doit rester disponible jusque-la.
3. **Table `conformite_non_conformites`** : supprimable apres archivage une fois la recopie verifiee en production.
4. **Tables jamais ecrites** (`organizations`, `business_rules`, `report_exports`) : supprimer ou conserver pour un futur usage (multi-cabinet, facturation) ?
5. **Comptes en double / de test** : validation de la liste avant toute fusion ou desactivation ; les identifier d'abord via `/v3/admin/sante`.
6. **Retours de l'etude exposes dans l'admin** : les commentaires libres (`commentaire_validation`, `par_cas_07`, `intention_02/04/05`) sont affiches ; `par_cas_00b`/`par_cas_01b` (« Lequel ? ») sont volontairement exclus car ils peuvent citer la dictee. Confirmer ce perimetre.
7. **Commentaire des avis anciens** : suppose sans donnee patient (retour d'usage) ; il est tronque a 1000 caracteres mais non filtre. Un filtre « donnees patient » a l'affichage est possible.
8. **Convention de statut des signalements** : correspondance avec l'ISO (`ouvert`=ouverte, `en_cours`=en_analyse, `traite`=cloturee, `rejete`=cloturee en vue historique).
9. **Alembic** : abandonner `alembic/` (non maintenu) ou le remettre a niveau.
