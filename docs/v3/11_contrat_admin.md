# Contrat de l'API d'administration unifiee MARC v3

Source de verite pour le frontend (`frontend/src/v3/admin`). Code : `backend/admin_v3/` (routes, retours, vue d'ensemble, sante, signalements) ; tests : `backend/tests/test_admin_v3.py`.

## Regles generales
- Prefixe `/v3/admin`, **admins uniquement** (`role == "admin"`). Sans jeton : 401 ; non admin : 403 `{"detail":"Acces reserve aux administrateurs"}`.
- Auth : `Authorization: Bearer <access_token>` (meme jeton que le reste de l'app).
- Reponses JSON, textes et messages d'erreur en francais. Les erreurs sont `{"detail": "<message francais>"}` (422 de validation FastAPI : `detail` peut etre une liste pour un parametre de requete invalide).
- Dates : ISO 8601 UTC avec `Z`, a la seconde (`2026-11-17T09:24:23Z`) ; `jour` = `YYYY-MM-DD` (UTC).
- Les endpoints sont en **lecture seule**, sauf `PATCH /v3/admin/signalements/{id}`.
- **Aucun texte medical** n'est jamais renvoye : ni `raw_transcription`, ni `structured_report`, ni les corrections avant/apres. Le seul texte libre expose est celui que l'utilisateur a ecrit comme retour (signalement, commentaire d'avis, commentaire de validation de l'etude).
- Rien n'est supprime ni modifie par ces endpoints (hors statut/note d'un signalement).

## 1. `GET /v3/admin/vue-ensemble?periode=7j|30j|90j|tout`
Defaut `30j`. Autre valeur : 422. Les periodes `7j|30j|90j` couvrent N jours **calendaires, aujourd'hui inclus** (de 00:00 UTC du premier jour a maintenant) ; `tout` = depuis toujours (la serie est plafonnee aux 366 derniers jours).

```json
{
  "periode": "30j",
  "kpi": {
    "utilisateurs_actifs": 2,
    "utilisateurs_total": 5,
    "projets_v3": 0,
    "comptes_rendus_anciens": 3,
    "dossiers_etude": 2,
    "notes_utile": 0,
    "notes_a_ameliorer": 0,
    "signalements_ouverts": 1,
    "duree_mediane_generation_ms": null,
    "modifications_moyennes_par_projet": null
  },
  "serie": [
    {"jour": "2026-11-07", "projets_v3": 0, "comptes_rendus_anciens": 1, "utilisateurs_actifs": 1},
    {"jour": "2026-11-08", "projets_v3": 0, "comptes_rendus_anciens": 0, "utilisateurs_actifs": 0}
  ],
  "origines": {"v3": false, "ancienne_version": true, "etude": true}
}
```
Definitions :
| champ | calcul |
|---|---|
| `utilisateurs_actifs` | utilisateurs distincts ayant une activite sur la periode : evenement de telemetrie, `reports.created_at`, ou `etude_dossiers.cree_a` (via la session). |
| `utilisateurs_total` | nombre de comptes (`users`), toute periode, actifs ou non. |
| `projets_v3` | evenements `projet_genere` de la telemetrie sur la periode. |
| `comptes_rendus_anciens` | lignes de `reports` creees sur la periode. |
| `dossiers_etude` | lignes de `etude_dossiers` creees sur la periode (exclus compris). |
| `notes_utile` / `notes_a_ameliorer` | evenements `feedback` de sens `positif` / `negatif` sur la periode. |
| `signalements_ouverts` | **stock actuel** (pas filtre par periode) : signalements `ouvert` ou `en_cours`, hors doublons. |
| `duree_mediane_generation_ms` | mediane de `duree_ms` des `projet_genere` de la periode ; `null` si aucun. |
| `modifications_moyennes_par_projet` | evenements `element_edite` / `projet_genere` sur la periode ; `null` si aucun projet. |
| `serie` | un element par jour, du plus ancien au plus recent ; `utilisateurs_actifs` = distincts du jour (toutes sources). |
| `origines` | `true` si la source contient au moins une ligne (toute periode). Sert a masquer les blocs vides de l'UI. |

## 2. `GET /v3/admin/retours?origine=&categorie=&statut=&page=&par_page=`
Flux unique, du plus recent au plus ancien, sans doublon. Filtres facultatifs : `origine` in `v3|ancienne_version|etude` (sinon 422), `categorie` (egalite stricte), `statut` in `ouvert|en_cours|traite|rejete` (ne retient que les signalements). `page` >= 1 (defaut 1), `par_page` 1..200 (defaut 25). `total` = nombre d'elements apres filtres, toutes pages.

```json
{
  "total": 6,
  "page": 1,
  "items": [
    {"id": "avis:r-1", "origine": "ancienne_version", "nature": "avis", "categorie": null, "sens": "negatif",
     "note_sur_5": 2, "message": "Trop lent sur les biopsies", "statut": null,
     "utilisateur": {"id": "u-a", "email": "alice@pgtest.org", "nom": "Alice Pathologiste"},
     "cree_le": "2026-11-10T09:00:00Z", "ref": "r-1"},
    {"id": "signalement:5efc5cd8-568d-4293-855a-8a7094183313", "origine": "v3", "nature": "signalement",
     "categorie": "erreur_projet", "sens": null, "note_sur_5": null, "message": "Le code ADICAP du côlon est faux",
     "statut": "ouvert", "utilisateur": {"id": "u-a", "email": "alice@pgtest.org", "nom": "Alice Pathologiste"},
     "cree_le": "2026-11-17T09:24:23Z", "ref": "5efc5cd8-568d-4293-855a-8a7094183313"},
    {"id": "signalement:nc-pg-1", "origine": "v3", "nature": "signalement", "categorie": "non_conformite", "sens": null,
     "note_sur_5": null, "message": "Non-conformité ISO : faux_positif, gravité majeure.", "statut": "ouvert",
     "utilisateur": {"id": "u-a", "email": "alice@pgtest.org", "nom": "Alice Pathologiste"},
     "cree_le": "2026-11-12T08:00:00Z", "ref": "nc-pg-1"},
    {"id": "etude_reponse:q-1", "origine": "etude", "nature": "avis", "categorie": "questionnaire_fin_etude", "sens": null,
     "note_sur_5": null, "message": "Le temps de reponse", "statut": null,
     "utilisateur": {"id": "u-a", "email": "alice@pgtest.org", "nom": "Alice Pathologiste"},
     "cree_le": "2026-11-17T09:23:37Z", "ref": "q-1"}
  ]
}
```
Semantique des champs :
| champ | valeurs |
|---|---|
| `id` | `"<table>:<ref>"`, unique dans le flux : `signalement:`, `note:`, `avis:`, `etude_dossier:`, `etude_reponse:`. Cle React. |
| `origine` | `v3` (signalements et notes), `ancienne_version` (avis), `etude`. |
| `nature` | `signalement` (action possible), `note` (Utile / A ameliorer v3), `avis` (etoiles/commentaire de l'ancienne version, commentaires de l'etude). |
| `categorie` | signalements : `dysfonctionnement`, `erreur_projet`, `amelioration`, `non_conformite`. Etude : `commentaire_validation`, `questionnaire_par_cas`, `questionnaire_fin_etude`. Notes et avis anciens : `null`. |
| `sens` | `positif`, `negatif`, `neutre` (avis ancien noté 3), ou `null`. Avis ancien : >= 4 positif, <= 2 negatif. |
| `note_sur_5` | entier 1..5 pour les avis de l'ancienne version, sinon `null`. |
| `message` | texte libre de l'utilisateur (1000 car. max). Note v3 : `"Motifs : omission, invention"` ou `""`. Non-conformite ISO sans texte : phrase generee a partir de la categorie ISO et de la gravite. |
| `statut` | `ouvert|en_cours|traite|rejete` pour un signalement, `null` sinon. |
| `utilisateur` | `{id, email, nom}` ; `email`/`nom` valent `null` si le compte n'existe plus. |
| `ref` | identifiant brut dans la table d'origine. **Pour `nature == "signalement"`, c'est l'`{id}` a passer a `PATCH /v3/admin/signalements/{id}`.** Pour un avis ancien, c'est l'id du compte rendu (reference seulement). |

Sources : table `signalements` (hors lignes `doublon_de`) ; `telemetrie_evenements` type `feedback` ; `reports.completeness_warnings` cle `feedback` uniquement ; `etude_dossiers.commentaire_validation` (dossiers non exclus) ; `etude_reponses_questionnaire` items `par_cas_07`, `intention_02`, `intention_04`, `intention_05`. Les mesures d'ergonomie de l'etude sont des agregats sans commentaire : voir `GET /admin/etude/ergonomie` (section 6).

## 3. `PATCH /v3/admin/signalements/{id}`
Corps : `{"statut": "ouvert|en_cours|traite|rejete", "note_admin": "texte <= 1000 car."}` ; au moins un des deux. 404 si inconnu ; 422 si valeur invalide, note trop longue ou corps vide. Si rien ne change, reponse 200 sans ecriture ni audit. Chaque changement est ecrit dans le journal d'audit chaine (`conformite_audit`, type `signalement_statut`, payload `signalement_id`, `statut`, `statut_precedent`, `note_modifiee` ; le texte de la note n'entre jamais dans la chaine).

```json
{"id": "5efc5cd8-568d-4293-855a-8a7094183313", "user_id": "u-a", "categorie": "erreur_projet",
 "message": "Le code ADICAP du côlon est faux", "projet_hash": "09f1e71c043d6eee", "ecran": "codes", "version_app": "3.0.0",
 "statut": "en_cours", "note_admin": "Reproduit", "cree_le": "2026-11-17T09:24:23Z", "maj_le": "2026-11-17T09:24:23Z",
 "doublon_de": null, "gravite": null, "categorie_iso": null}
```

## 4. `POST /v3/signalements` (tout utilisateur connecte)
Corps : `{"categorie": "dysfonctionnement|erreur_projet|amelioration|non_conformite", "message": "...", "projet_id"?: "...", "ecran"?: "...", "version_app"?: "..."}`. Limite 30 / minute. Reponse `{id, doublon_de}` (200).
- `message` : obligatoire, 1 a 1000 caracteres. Refuse (422) ce qui ressemble a une donnee patient : NIR, date de naissance ou date complete, numero de 9 chiffres ou plus (telephone, dossier), e-mail, « Mme/M./Monsieur + Nom », « patient : Nom ». Exemple de refus :
  `{"detail":"Votre message semble contenir une date de naissance. Pour protéger les patients, n'écrivez aucune donnée identifiante (nom, date, numéro de sécurité sociale, téléphone, e-mail) : décrivez le problème sans elle."}`
- `projet_id` (`[A-Za-z0-9_-]{1,64}`) n'est jamais stocke : seule son empreinte salee (`projet_hash`, comme la telemetrie) l'est. `ecran` : `[A-Za-z0-9_./:-]{1,60}` ; `version_app` : `[A-Za-z0-9_.+-]{1,60}`.
- Dedoublonnage : meme utilisateur + meme categorie + meme projet (ou tous sans projet) + message quasi identique (casse, accents, ponctuation ignores ; similitude >= 90 %) dans les 10 minutes : rien n'est cree et la reponse est `{"id": "<existant>", "doublon_de": "<existant>"}`. Sinon `{"id": "<nouveau>", "doublon_de": null}`.
- La note rapide « Utile / A ameliorer » reste de la telemetrie (`POST /v3/telemetrie/evenements`, type `feedback`) et n'est PAS un signalement.
- Categorie `non_conformite` : inscrite aussi dans l'audit chaine (type `non_conformite`).

## 5. `GET /v3/admin/utilisateurs`
Tous les comptes (actifs ou non), du plus recent au plus ancien. Jamais de hash de mot de passe.
```json
[{"id": "u-a", "email": "alice@pgtest.org", "nom": "Alice Pathologiste", "role": "user", "cree_le": "2026-11-17T09:23:37Z",
  "derniere_activite": "2026-11-16T09:23:37Z", "projets_v3": 0, "comptes_rendus_anciens": 2, "dossiers_etude": 2,
  "habilite_valideur": false}]
```
`derniere_activite` = max(derniere connexion, dernier evenement de telemetrie, dernier compte rendu, dernier dossier d'etude) ; `null` si aucune. `projets_v3` = evenements `projet_genere`. `habilite_valideur` = habilitation de conformite (`conformite_habilitations`). Pour modifier l'habilitation : `PUT /v3/conformite/habilitations/{user_id}` (existant).

## 6. `GET /v3/admin/etude`
Meme corps, a l'identique, que `GET /admin/etude/synthese` (logique reutilisee : `routes_etude_admin.synthese`) : cles `couverture`, `propositions`, `fsus`, `par_cas`, `dossiers`, `praticiens_favorables`, `corpus`, `apprentissage`. 503 si la base est absente.

Routes existantes de l'etude, **conservees telles quelles** (admins) : l'admin v3 peut y renvoyer.
| methode | chemin | role |
|---|---|---|
| GET | `/admin/etude/synthese` | synthese (equivalent de `/v3/admin/etude`) |
| GET | `/admin/etude/dossiers` | liste des dossiers |
| GET | `/admin/etude/dossiers/{dossier_id}` | detail d'un dossier (contient du texte de CR : donnees de recherche) |
| POST | `/admin/etude/dossiers/{dossier_id}/exclusion` | exclure/reintegrer un dossier |
| DELETE | `/admin/etude/dossiers/{dossier_id}` | supprimer un dossier (destructif) |
| GET | `/admin/etude/export` | archive ZIP de quatre CSV |
| GET | `/admin/etude/export.xlsx` | classeur Excel |
| GET | `/admin/etude/ergonomie` | profil d'usage de l'interface |

## 7. `GET /v3/admin/sante` (lecture seule)
```json
{
  "version": "3.0.0+21879de",
  "base": {"type": "postgresql", "tables": [
    {"nom": "audit_log", "lignes": 0}, {"nom": "conformite_non_conformites", "lignes": 2},
    {"nom": "reports", "lignes": 3}, {"nom": "signalements", "lignes": 2}, {"nom": "users", "lignes": 5}]},
  "controles": [
    {"nom": "orphelins", "ok": true, "detail": "Aucun orphelin (reports, télémétrie, signalements, tables etude_*)."},
    {"nom": "doublons_comptes", "ok": false, "detail": "1 e-mail(s) en double, par exemple : bob@pg.test"},
    {"nom": "comptes_de_test", "ok": false, "detail": "1 compte(s) de test (@example.com) : à passer en revue."},
    {"nom": "chaine_audit", "ok": true, "detail": "Chaîne intègre : 0 entrée(s) vérifiée(s)."},
    {"nom": "signalements_en_double", "ok": true, "detail": "Aucun signalement en double."},
    {"nom": "recopie_non_conformites", "ok": true, "detail": "2 non-conformité(s) recopiée(s) sur 2 dans l'ancienne table (conservée)."},
    {"nom": "tables_jamais_ecrites", "ok": false, "detail": "15 table(s) vide(s) : audit_log, business_rules, ... (informatif : une table vide n'est pas une erreur)."}
  ]
}
```
`base.type` = dialecte (`postgresql`, `sqlite`). `tables` : toutes les tables du modele, triees par nom ; `lignes` = nombre de lignes (`null` + cle `erreur` si la table est illisible). Noms de controles stables : `orphelins`, `doublons_comptes`, `comptes_de_test`, `chaine_audit`, `signalements_en_double`, `recopie_non_conformites`, `tables_jamais_ecrites`. `ok: false` = a regarder, pas forcement une panne (`tables_jamais_ecrites` est informatif).

## Routes de conformite deja existantes (inchangees dans leur forme)
`/v3/conformite/non-conformites` (POST utilisateur, GET et `PATCH /{id}` admin) lisent et ecrivent desormais la table `signalements` (categorie `non_conformite`, champ ISO dans `categorie_iso`) ; leurs reponses gardent la forme historique (`categorie` = categorie ISO ; `statut` = `ouverte|en_analyse|cloturee`, correspondant a `ouvert|en_cours|traite` ; `rejete` s'affiche `cloturee`). Pour l'admin v3, preferer `/v3/admin/retours` + `PATCH /v3/admin/signalements/{id}`.
Autres routes utiles : `GET /v3/conformite/audit`, `GET /v3/conformite/audit/verification`, `GET /v3/conformite/audit/export.csv`, `GET /v3/conformite/habilitations`, `PUT /v3/conformite/habilitations/{user_id}`, `GET /v3/conformite/kb/versions`, `GET /v3/admin/telemetrie/synthese`, `GET /v3/admin/telemetrie/recommandations`.
