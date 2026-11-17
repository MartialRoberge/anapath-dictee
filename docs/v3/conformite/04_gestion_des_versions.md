# Procedure de gestion des versions (7.6 maitrise des changements, 8.3 maitrise documentaire)

## Elements versionnes
| Element | Identifiant | Ou le voir |
|---|---|---|
| Pipeline | semver `3.0.0` + hash git court (`3.0.0+4997b39`) ; hash lu via `MARC_GIT_COMMIT` ou `git` | bloc tracabilite |
| Base de connaissances | `kb_version` du manifest + empreinte SHA-256 (noms et contenu des fichiers JSON) | bloc tracabilite, registre |
| Modeles | nom epingle par etape (ex. `mistral-large-2512` ; l'alias `-latest` est interdit pour le redacteur et l'extracteur) | bloc tracabilite |

## Cycle de vie d'une version de base
`brouillon` (enregistree depuis la base chargee) -> `approuvee` (approbateur et date) -> `en service` (une seule a la fois ; la precedente passe a `retiree`) -> `retiree`.
1. Construire la base (`scripts/build_kb.py`, `--date` du manifest), incrementer `version`.
2. Deployer en pre-production ; `POST /v3/conformite/kb/versions/enregistrer` (admin) enregistre version et empreinte.
3. Rejouer le plan de verification (`03_...`) ; l'approbateur du laboratoire ou de l'editeur approuve : `POST .../{version}/approuver`.
4. `POST .../{version}/mettre-en-service` : refuse si la base chargee par le serveur differe de la version approuvee (empreinte).
5. Chaque evenement est inscrit dans le journal d'audit chaine.

## Regles
- Un changement de modele, de prompt, de regle ou de gabarit = nouvelle version et re-verification.
- Une version deja enregistree dont le contenu change est refusee (409) : incrementer la version.
- Une validation enregistre les versions utilisees ; en cas de non-conformite, on retrouve toutes les validations produites avec la version en cause via le journal.
- Retour arriere : mettre une version approuvee anterieure en service apres redeploiement de son contenu ; l'ancienne devient `retiree`.
