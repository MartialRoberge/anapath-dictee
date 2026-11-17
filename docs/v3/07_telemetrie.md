# Telemetrie et administration MARC v3

## Garanties de non-collecte medicale
- Aucun champ de texte libre n'existe dans le schema : ni dictee, ni compte rendu, ni audio, ni nom de patient, ni valeur de champ (une taille ou un grade ne sont jamais envoyes, seulement l'id du champ).
- Whitelist stricte cote serveur (`backend/telemetrie/whitelist.py`) : type connu, cles declarees, valeurs = nombres bornes, booleens, enums fermes, ids techniques `[a-z0-9_]{1,48}`, listes de 20 ids max. Toute autre cle ou valeur fait rejeter l'evenement entier (compte dans `rejetes`, jamais stocke).
- Le client (`frontend/src/v3/telemetry.ts`) refuse deja toute chaine hors `[A-Za-z0-9_]{1,48}` et toute cle non declaree.
- Le projet n'est reference que par un hash sale (SHA-256 tronque, sel = secret serveur) ; l'id en clair n'est pas conserve.
- Horodatage pris cote serveur. Utilisateur = id interne du compte (jointure email uniquement dans la vue admin).
- Limite connue : un id `[a-z0-9_]` reste une chaine courte ; aucune verification contre la kb n'est faite (a ajouter si besoin).

## Transport
`POST /v3/telemetrie/evenements` (utilisateur authentifie, 60 req/min, 50 evenements max par lot) :
`{"evenements":[{"type","payload":{...},"projet_id"?}]}` -> `{"acceptes","rejetes"}`.
Client : file memoire, envoi toutes les 10 s, a 20 evenements, et a `pagehide`/`visibilitychange` (fetch `keepalive` avec le jeton ; sendBeacon ne peut pas porter l'en-tete Authorization). Echec silencieux, sans jeton rien n'est envoye.

## Catalogue des evenements (champs tous optionnels)
| type | champs |
|---|---|
| projet_genere | duree_ms (0-600000), niveau_service (N0-N3), organes[], contexte_lesionnel, prelevement (id), nb_elements, nb_trous, nb_alertes, nb_corrections, confiance_moyenne (0-1) |
| projet_itere | duree_ms, nb_tours |
| element_edite | element_type (phrase/trou/titre/liste), statut (dicte/reformule/normalise/a_completer), niveau (haute/moyenne/basse), champ_id, delta_caracteres |
| trou_comble | champ_id, via (option/saisie/dictee), delai_ms, obligatoire |
| trou_ignore | champ_id, obligatoire |
| alerte_resolue / alerte_ignoree | alerte_type (incoherence/unite/manquant/phonetique/securite/codage), gravite (bloquant/attention/info), delai_ms |
| correction_acceptee / correction_rejetee | confiance (0-1), delai_ms |
| code_copie / code_modifie | systeme (ADICAP/SNOMED_CT/CIM_O3), statut (certain/partiel/suggestion) |
| source_consultee | source_kind (dictee/kb/regle/agent/web) |
| feedback | sens (positif/negatif), motifs[] (omission, invention, mauvaise_unite, code_errone, trop_lent, mise_en_forme, autre) |
| export | format (docx/pdf/texte/presse_papiers/fhir), duree_depuis_generation_ms, nb_retouches, sans_retouche |
| session_temps | duree_s |
| erreur | code (reseau/stt/llm/timeout/validation/inconnu), etape (id), niveau_service |

Table `telemetrie_evenements` (id, user_id, type, projet_hash, ts, payload JSON), creee par `create_all`.

## Admin (role admin uniquement)
- `GET /v3/admin/telemetrie/synthese?periode=7j|30j|90j`
- `GET /v3/admin/telemetrie/recommandations?periode=...` (defaut 30j)
- UI : `frontend/src/v3/admin/AdminV3.tsx` (export par defaut, prop `fetchAuth` optionnelle, `?demo=1` pour donnees fictives, export CSV).

## KPI (fenetre glissante de N jours ; variation = vs N jours precedents)
- projets_generes : nombre d'evenements `projet_genere`. utilisateurs_actifs : utilisateurs distincts ayant emis un evenement. dau_moyen : moyenne quotidienne des utilisateurs actifs sur la periode. mau : utilisateurs distincts sur 30 jours.
- temps_median_generation_ms : mediane de `projet_genere.duree_ms`. temps_median_export_ms : mediane de `export.duree_depuis_generation_ms`.
- taux_exports_sans_retouche : exports `sans_retouche=true` / exports renseignant ce booleen.
- retouches_moyennes_par_projet : `element_edite` / projets generes ; ventilation par element_type, statut, niveau (retouches et par projet).
- trous : par champ_id, combles, ignores, taux_ignore. alertes : par type, resolues, ignorees, taux_ignore (proxy de faux positifs).
- corrections.precision : acceptees / (acceptees + rejetees). feedback : +/- et motifs des retours negatifs.
- organes (top 10), service.niveaux (projets par N0-N3), service.erreurs (par code), series quotidiennes (projets, utilisateurs, exports, erreurs), top_utilisateurs (jours actifs, email du compte).

## Recommandations (minimum 5 observations par regle)
Champ ignore >= 60 % ; alerte ignoree >= 40 % ; precision correcteur < 70 % (critique) ; retours negatifs >= 30 % (critique, motif principal) ; exports sans retouche < 50 % ; erreurs > 5 % des projets (critique) ; niveau N2/N3 >= 20 % des projets ; generation mediane > 60 s.
