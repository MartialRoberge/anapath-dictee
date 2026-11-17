# Conformite ISO 15189:2022 de MARC : synthese

## Ce que MARC est, et ce qu'il n'est pas
- La norme NF EN ISO 15189:2022 accredite le **laboratoire** (COFRAC, referentiel SH REF 02 rev. 08), pas un logiciel. MARC ne doit **jamais** etre presente comme « certifie ISO 15189 ». Formulation autorisee : « MARC fournit au laboratoire les moyens de documenter sa conformite a la norme ISO 15189:2022 ».
- MARC est une **aide a la redaction** de comptes rendus d'anatomie et cytologie pathologiques (ACP). Le compte rendu est valide et libere par un pathologiste habilite. Voir `05_statut_reglementaire_hds.md`.

## Tension resolue : piste d'audit vs aucune donnee medicale stockee
MARC ne persiste ni dictee, ni audio, ni compte rendu. La piste d'audit exigee (8.4 maitrise des enregistrements, 7.6 maitrise des donnees et de la gestion de l'information) repose donc sur :
- des **metadonnees** (qui, quand, versions, comptages, enums) ;
- des **empreintes SHA-256** du texte valide et de la dictee corrigee, calculees dans le navigateur ou le pipeline : elles prouvent « ce texte exact a ete valide » (le labo, qui conserve le compte rendu dans son SIL, recalcule l'empreinte et la compare) sans que MARC ne detienne le texte ;
- un **journal chaine par hash** (chaque entree contient le hash de la precedente) : toute alteration, insertion ou suppression au milieu est detectee.
Garde-fou technique : `backend/conformite/metadonnees.py` n'accepte que booleens, entiers bornes et chaines sans espace `[A-Za-z0-9_.:+/-]` ; un test verifie qu'aucun texte medical ne peut atteindre les tables.

## Fonctionnalites livrees
| Fonction | Ou |
|---|---|
| Bloc `tracabilite` dans chaque Projet (id, UTC, version pipeline + hash git, version et empreinte kb, modeles par etape, empreinte dictee corrigee, niveau de service) | `projet/schemas.py`, `conformite/tracabilite.py`, orchestrateur |
| Validation par pathologiste habilite, blocages, derogation par enum, revisions chainees | `POST /v3/conformite/validations` |
| Habilitation « valideur » geree par l'admin | `PUT /v3/conformite/habilitations/{user}` |
| Journal d'audit chaine, verification d'integrite, export CSV | `GET /v3/conformite/audit`, `/audit/verification`, `/audit/export.csv` |
| Registre des versions kb (brouillon, approuvee, en service, retiree) | `/v3/conformite/kb/...` |
| Non-conformites (enums, sans texte) et suivi de statut | `/v3/conformite/non-conformites` |
| Interface : « Valider le compte rendu », mention « Projet · a valider par le pathologiste », bloc Tracabilite, « Signaler une non-conformite » | `frontend/src/v3/components/conformite/` |

## Limites a connaitre (honnetete)
1. Le serveur ne voit jamais le texte : l'empreinte est **declaree** par le client authentifie, le serveur controle son format mais ne peut pas la recalculer. La preuve opposable est le rapprochement avec le compte rendu conserve par le laboratoire.
2. La chaine detecte altération, insertion et suppression au milieu ; la **troncature de la fin** n'est detectee que si le dernier hash est ancre ailleurs. Recommandation : exporter periodiquement le CSV et consigner le `dernier_hash` (verification) dans le systeme documentaire du labo.
3. Le statut « valide » vit dans la session du navigateur ; la preuve durable est le registre serveur (`GET /v3/conformite/validations/{projet_id}`). Un rechargement de page ne restitue pas encore le statut (a ajouter si le labo le demande).
4. L'ecran admin (habilitations, audit, registre kb) n'a pas d'interface : API seulement.
5. Les numeros de sous-clauses cites ci-dessous sont a recouper avec le texte de la norme, non reproduit ici.
