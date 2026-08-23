# Plan jusqu'au gel du 12 septembre

Établi le 23 août 2026, après audit du code existant contre `docs/specs/`.
Suit l'ordre de priorité de `MARC_V2_specification_maitresse.md` §8, corrigé par ce que
les audits ont trouvé.

---

## Le constat, en une phrase

L'application est un **éditeur dictée → document**, soigné et cohérent. La spécification
décrit un **instrument de mesure**. L'unité atomique de cet instrument — **la proposition**,
portant un empan, un type, une confiance et une décision horodatée — n'existe dans aucune
couche : ni en base, ni en API, ni en interface.

Conséquence directe : les six écarts majeurs de l'écran de revue (propositions, empans,
décision item par item, verrou d'export, marquage « hâtive », capture des modifications)
ne sont **pas six chantiers, mais un seul**.

Chiffres de l'audit : sur les 33 données exigées par les §5 et §7, **0 conformes, 30 absentes**.

---

## 1. L'objet fondateur : la proposition

Tout le reste en découle. Modèle cible :

```
Session
 └─ Dossier (compte rendu)
     └─ Prélèvement  (1..n)          ← D1, D3 propres à chacun
         ├─ Technique (1..n)          ← D2 : 1 primaire + n secondaires
         └─ Proposition (0..n)
              ├─ empan  (offset début/fin dans le transcript)
              ├─ type, confiance, règles évaluées
              ├─ horodatage d'affichage / de décision / latence
              ├─ décision : Conforme · À corriger · Non dicté · Hors sujet
              └─ texte corrigé (conservé À CÔTÉ du texte proposé)
```

Une fois cet objet posé, on obtient **gratuitement** : la grille de validation (§5),
la télémétrie (§7), le survol-qui-surligne (§6), le verrou d'export, le marquage
« hâtive », et les quatre taux de l'étude.

### Les quatre décisions

Source : `MARC_pipeline_dictee_seule.html`, étape 13.

| | Libellé | Sens |
|---|---|---|
| ✓ | **Conforme** | Je valide tel quel. |
| ✎ | **À corriger** | Juste sur le fond, à retoucher sur la forme. |
| ✗ | **Non dicté** | Je n'ai pas dit ça → **hallucination, sans discussion**. |
| ⊘ | **Hors sujet** | Proposition non pertinente ici. |

Rien n'est pré-coché. Rien ne s'accepte par défaut. Rien ne part sans geste explicite.

### Comment obtenir les empans sans faire halluciner le modèle

**On ne demande pas d'offsets au modèle** — il les inventerait. Ancrage par
**correspondance exacte, vérifiée côté serveur** : la proposition cite un fragment de
verbatim, le serveur le retrouve dans le transcript et calcule l'offset lui-même.
Fragment introuvable → **proposition rejetée avant affichage**.

C'est la règle « pas d'empan, pas de proposition » appliquée mécaniquement, sans coût de
modèle et sans confiance accordée au modèle. Le patron existe déjà dans le repo
(`reports/guardrails.py` vérifie les chiffres du CR contre la dictée) : on l'étend.

---

## 2. Le plan, dans l'ordre de la spec

### Rang 0 — Correctifs immédiats (avant tout le reste)

Trois défauts trouvés par l'audit, indépendants du chantier principal, à corriger tout de suite.

| Défaut | Gravité |
|---|---|
| Un CR rouvert depuis l'historique affiche « **Compte-rendu complet — toutes les données obligatoires sont présentes** » alors que le texte contient encore des `[A COMPLETER]` non remplis | **Faux négatif rassurant dans un outil médical** |
| Trois compteurs de complétude comptent trois choses différentes et s'affichent ensemble | Incohérence visible |
| Le brouillon local tient dans **une clé unique** : ouvrir un second dossier écrase le premier | Perte de travail |

### Rang 1 — Capture des validations et des modifications

Le chantier n°1 de la spec, et le seul sans lequel l'étude n'existe pas.

- Tables : `sessions`, `prelevements`, `propositions`, `decisions`, `evenements`.
- Le chemin d'écriture des modifications est **mort depuis l'origine** (`PUT /reports/{id}`
  n'est appelé par aucun code front) : le rebrancher, et permettre la re-sauvegarde.
- Conserver le **texte proposé initial** à côté du texte validé (aujourd'hui écrasé).
- Enregistrement **automatique**, pas seulement sur clic : un praticien qui ne clique pas
  ne doit plus disparaître des données.

### Rang 2 et 3 — Cardinalité et codes multiples

Le bug le plus signalé par le terrain. **Reproduit** : une dictée à 3 prélèvements produit
`LERPA7A0`, un code unique, faux sur D1 *et* sur D2, là où la spec en attend 5.

Bonne nouvelle : **il manque le branchement, pas le mécanisme.** La segmentation en blocs
numérotés existe déjà et fonctionne. Le codeur ADICAP ne la consomme simplement pas.

- Brancher le codeur sur les prélèvements au lieu du document entier.
- `codes = Σ prélèvements (1 primaire + n techniques secondaires)`.
- Corriger les quatre défauts D1 à erreur **systématique** : `I` déclaré mais inatteignable,
  famille « biopsie » inexistante (tout devient `B` chirurgicale), `R` absorbé par `L`,
  et le défaut `B` codé en dur là où la spec exige l'abstention.
- D2 : primaire H/C avec condition négative (cytobloc → H), et les 7 secondaires en **ajout**,
  jamais en remplacement.
- Afficher le nombre de prélèvements **en tête d'écran, corrigeable avant toute proposition**.

**À ne pas toucher** : la doctrine d'abstention sur l'axe lésionnel, l'axe organe D3, la bible
de 306 lésions et son test zéro-faux, le masquage des négations. C'est ce qui produit le
« Codification : super » du terrain. Le chantier D1/D2 **étend** ce patron.

### Rang 4 — Télémétrie

Sept horodatages t0→t6, latences, pauses, panneau de justification ouvert et durée,
décision changée après ouverture, marquage `hative` (< 1 200 ms sur > 15 mots).

### Rang 5 — Verrou d'export et abandon motivé

Aujourd'hui **cinq sorties non gardées** (docx, txt, copier tout, copie par section, copie
codification). Le verrou n'a de sens qu'une fois les propositions décidables — donc après
le rang 1.

### Rang 6 — Questions de levée de doute

Les trois questions D1 sont **déjà rédigées** dans `Codage_D1_D2_table.json`, mais aucun code
ne lit ce fichier. Budget de 3 questions par CR, options fermées, toujours une issue
« je ne sais pas ». Placées en tête de l'écran de revue, jamais pendant la dictée.

*Réserve* : la liste des organes qui déclenchent la question sur le guidage doit venir de la
praticienne. Bloqué sur un apport métier, pas sur du développement.

### Rang 7 — Écran de revue et style

- Trois volets **visibles ensemble** (aujourd'hui : deux, le troisième est un tiroir modal
  qui recouvre le document qu'on corrige).
- Survol d'une proposition → surlignage de son empan.
- Responsive : ajouter un palier intermédiaire. Aujourd'hui un seul point de rupture à
  1024 px, donc un iPad en portrait bascule en mise en page téléphone alors qu'il a la place.
- Style rédigé plutôt que listes à puces. *Les sections conditionnelles sont déjà faites.*

---

## 3. Ce que je ne ferai pas avant le gel — et pourquoi

| Écarté | Raison |
|---|---|
| L'axe **D7 cytopathologie** | N'existe nulle part dans le code. Chantier neuf, pas un correctif. |
| La **dérivation** pTNM / Nancy | La spec elle-même la place après le congrès. |
| L'adaptateur de **cotation** | Même chose. |
| Le mapping **organe × famille lésionnelle** en couverture | La spec dit : deux ou trois localisations à fort volume, jamais la couverture. |
| Le **scraping** OMS / SNOMED | Sans valeur avant que le socle mesure quoi que ce soit. |
| **Manuel** et **plaquette** | À produire après le gel, avant l'entrée sur le terrain. |

Vingt jours ne permettent pas tout. L'ordre ci-dessus est celui de la spec, et il est bon :
sans le rang 1, aucune des autres améliorations ne sera mesurable.

---

## 4. Décisions requises

1. **Le bras sans outil.** Le protocole écrit prévoit des cas appariés « avec et sans
   l'outil » et un critère go/no-go de **≥ 30 % de réduction de temps**. Le commanditaire
   indique que ce comparatif ne sera pas réalisable. À trancher : garder le bras témoin, ou
   retirer le critère de temps des seuils go/no-go.
2. **Fichiers manquants.** Huit des quatorze fichiers de `00_INDEX.md` sont absents, dont
   `MARC_cahier_de_recueil.md` (schéma JSON, questionnaires complets, liste d'événements) et
   `adicap_D4.csv` (2 566 codes). Les quatre décisions et les métriques ont pu être
   reconstituées depuis les deux HTML ; le schéma JSON exact, non.

---

## 5. Ce qui est acquis et qu'il faut protéger

- **La couche complétude fonctionne** — c'est le différenciant, validé par le terrain.
- **L'abstention lésionnelle** : score minimal, avance minimale sur le second candidat,
  refus de coder un grade non dicté. Verrouillé par des tests.
- **L'axe organe D3** et la bible de 306 lésions, avec rejeu zéro-faux.
- **La segmentation multi-prélèvements** côté texte : déjà numérotée, déjà validée.
- **Le masquage négation / prospectif** : « PCR recommandée » ne code pas une PCR.
