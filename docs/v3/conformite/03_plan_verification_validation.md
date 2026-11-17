# Plan de verification / validation logicielle rejouable par le laboratoire

But : permettre au laboratoire de verifier MARC dans son contexte avant mise en service (6.4, 7.6) et apres chaque changement de version. Le laboratoire reste responsable de la decision de mise en service.

## 1. Preparation
1. Relever la version : bloc « Tracabilite » (version pipeline, version et empreinte kb, modeles). Verifier que la version kb est « en service » (`GET /v3/conformite/kb/en-service`).
2. Constituer un jeu de cas propre au labo : au moins 30 dictees reelles anonymisees couvrant les organes et prelevements du perimetre, dont 10 cas pieges (negation, unites, lateralite, benin, biopsie sans pTNM, dictee incomplete). Ne jamais verser de donnees nominatives hors du systeme du labo.
3. Definir qui valide et qui est habilite (role « valideur »).

## 2. Protocole
Pour chaque cas : dicter ou coller, generer, puis un pathologiste compare le projet a sa dictee et consigne le resultat dans une grille (cas, version, ecarts, gravite).
Verifier systematiquement :
- **Fidelite** : aucune valeur, mesure, stade ou conclusion absents de la dictee ; negations conservees ; unites identiques.
- **Trous** : chaque information obligatoire non dictee apparait comme trou, aucune valeur inventee.
- **Benin** : aucun champ ni mention tumorale.
- **Codes** : statut coherent ; aucun code sans source.
- **Validation** : blocage si alerte bloquante ou trou obligatoire ouvert ; derogation tracee ; revision liee ; refus sans habilitation.
- **Audit** : `GET /v3/conformite/audit/verification` renvoie `ok: true` ; le CSV contient generation et validation du cas.

## 3. Criteres d'acceptation (proposes, a ajuster par le labo)
| Critere | Seuil |
|---|---|
| Violations de securite (fabrication, negation inversee, mm/cm, tumoral sur benin) | **0** sur l'ensemble des cas |
| Champs obligatoires non dictes presentes en trou | 100 % |
| Alertes bloquantes legitimes detectees sur les cas pieges | >= 90 % |
| Cas necessitant une correction par le pathologiste | consigne et analyse (pas de seuil universel) |
| Integrite du journal | `ok: true` |
Toute violation de securite = non-conformite critique (`POST /v3/conformite/non-conformites`), mise en service refusee tant que non resolue.

## 4. Reutilisation de la campagne automatisee
`backend/tests/campagne_v3.py` (appels reels, necessite les cles) mesure latence, appels, jetons et les violations V1 a V8 (contrat, chiffre non dicte, stade pTNM non dicte, negation inversee, champ tumoral sur benin, pTNM/marges sur biopsie, markdown, « aide au diagnostic »). Usage depuis `backend/` : `../venv/bin/python tests/campagne_v3.py --sortie <dossier hors depot>`. Le labo peut ajouter ses cas anonymises a cette campagne. Les tests unitaires (`pytest -q`) rejouent sans reseau le comportement deterministe (blocages, chaine d'audit, absence de texte).

## 5. Enregistrements a conserver par le laboratoire
Grille de resultats signee, version testee (capture du bloc tracabilite), export CSV du journal, decision de mise en service et date, personnes habilitees. Duree de conservation selon la politique du labo (8.4).

## 6. Re-verification
Allegee (jeu reduit + cas pieges) a chaque nouvelle version de pipeline ou de kb ; complete a chaque changement de modele de langage ou de gabarit.
