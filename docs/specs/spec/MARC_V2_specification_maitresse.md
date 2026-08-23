# MARC V2 — spécification maîtresse

Document de référence unique. Remplace les spécifications antérieures dispersées.
Écrit à partir des retours terrain de la V1 et des dictionnaires D1 et D2 annotés.

---

## 1. Ce que dit le terrain

Douze retours de Jéromine, juillet et août 2026. Trois catégories.

### Ce qui marche

| Retour | Couche |
|---|---|
| « Codification : super » — oesophage | codage |
| « Il me demande les bons items à compléter » — colon | complétude |
| « Il me rappelle de mentionner la classification de Nancy » — colon | complétude |
| « Il a capté qu'il y avait plusieurs prélèvements » — peau | segmentation |
| « Parfait » — endomètre · « Très bien, ras » — peau | ensemble |

**La couche complétude fonctionne déjà.** C'est le différenciant, et il est en place. Le reste
est réparable.

### Ce qui est cassé

| Retour | Diagnostic |
|---|---|
| « J'ai dicté plusieurs prélèvements, il n'en prend en compte qu'un seul » | **cardinalité** |
| « Si plusieurs prélèvements, il faut plusieurs codes » | **cardinalité des codes** |
| « Cotation : manquante » ×2 | axe absent |
| « Microscopie : rédiger plutôt que faire des bullet points » | style |
| « Biologie moléculaire : ne faire apparaître cette catégorie que si elle est mentionnée » | sections conditionnelles |
| « Conclusion : ne répond pas aux standards attendus pour un lymphome » | complétude de la conclusion |
| Validations et modifications non capturées | **bloquant pour l'étude** |

La cardinalité apparaît deux fois, avec une incohérence entre cas — capté en peau, écrasé en
oesophage. Ce n'est pas une régression, c'est une absence de modèle.

### Ce qui est demandé et qui n'existe dans aucune spécification

| Retour | Nature |
|---|---|
| « Pour tous les cancers on doit donner le TNM. J'ai donné les informations qui permettent de le calculer et pour autant il ne le fait pas » | **dérivation** |
| « Il ne parvient pas à donner la classification de Nancy de lui-même » | **dérivation** |
| « Proposer une description standard quand le pathologiste ne la donne pas spontanément » | à reformuler, section 2 |

---

## 2. Le concept manquant : dériver

Ma ligne rouge disait : ne jamais introduire une assertion absente de la dictée. Elle reste
juste, mais elle était incomplète — il manquait une catégorie, et c'est celle que Jéromine
réclame deux fois.

### Quatre verbes, pas trois

| Verbe | Définition | Ancrage affiché | Statut |
|---|---|---|---|
| **Restituer** | ce qui a été dit | l'empan du verbatim | acquis |
| **Dériver** | ce qui se calcule à partir de ce qui a été dit, par une règle publiée | les empans des entrées **+ la règle citée** | **à construire** |
| **Demander** | ce que le praticien détient et n'a pas dit | le déclencheur | à construire |
| **Générer** | inventer une assertion clinique | — | **interdit** |

### Pourquoi la dérivation est légitime

Si le praticien a dicté « adénocarcinome, 18 mm, pas d'envahissement de la musculeuse propre,
0 ganglion envahi sur 14 examinés », alors le stade **pT1 N0** n'est pas un jugement : c'est une
lecture de table. Les faits sont dictés, la règle est publiée, le résultat est déterministe.

C'est exactement la même nature que la couche de cohérence : on ne diagnostique pas, on applique
une règle citable à des faits énoncés.

### Pourquoi c'est le meilleur argument face à un assistant généraliste

Une dérivation a une **chaîne visible** :

```
   « 18 mm »              ─┐
   « pas d'envahissement   ├─→  règle : classification pTNM, organe, édition N  ─→  pT1
     de la musculeuse »   ─┤     référence citée, consultable en un clic
   « 0 sur 14 »           ─┘                                                    ─→  N0
```

Chaque entrée est surlignable dans la dictée. La règle est nommée et datée. Le résultat est
reproductible. **C'est de l'explicabilité native, pas une explication fabriquée après coup.**

Un assistant généraliste produit le même pT1 — parfois — sans montrer ses entrées, sans citer
d'édition, et sans dire quand il lui manque un élément. C'est là que se joue toute la différence,
et c'est démontrable en trente secondes devant un public.

### Les trois règles de la dérivation

1. **Aucune entrée manquante n'est comblée.** S'il manque un élément pour calculer le pTNM, on
   ne suppose pas : on affiche le stade partiel et on nomme précisément l'élément manquant.
   *« pT1 N0 — le statut M ne peut pas être établi sur ce prélèvement. »*
2. **La règle est toujours nommée, avec son édition.** Un pTNM sans mention de l'édition
   utilisée est inexploitable et juridiquement fragile.
3. **Le résultat est une proposition, jamais un acquis.** Il passe par la grille de validation
   comme tout le reste.

### Le cas « description standard » — à reformuler

La demande était : *proposer une description standard quand le pathologiste ne la donne pas.*
Prise au pied de la lettre, c'est de la génération : le système affirmerait des caractères
histologiques que personne n'a observés.

**Reformulation : un gabarit à choix fermés, pas de la prose.**

> **Description de la lésion — architecture**
> `acineuse` · `papillaire` · `lépidique` · `solide` · `micropapillaire` · `autre` · `ne pas préciser`

Ce n'est plus de la génération, c'est la mécanique de question appliquée à la description. Le
praticien répond en trois taps au lieu de dicter trois phrases — donc c'est **plus rapide** que ce
qu'il demandait, et sans risque. Le gabarit par organe et par famille lésionnelle vient du corpus
du laboratoire.

---

## 3. Architecture

### Un modèle de concepts, N adaptateurs de sortie

```
                    ┌──────────────────────────┐
   dictée ────────► │  MODÈLE DE CONCEPTS      │
                    │  prélèvements, lésions,  │
                    │  mesures, techniques,    │
                    │  marqueurs, ganglions    │
                    └───────────┬──────────────┘
                                │
        ┌──────────┬────────────┼────────────┬──────────────┐
        ▼          ▼            ▼            ▼              ▼
   compte rendu  ADICAP      SNOMED CT    CIM-O3      cotation CCAM
   (le produit)  (France)  (international) (registres)  (facturation)
```

**Le compte rendu est le produit. Tout le reste est un adaptateur d'export.**

Cette architecture répond d'un coup à trois demandes :
- la **cotation manquante** n'est pas une fonctionnalité à greffer, c'est un adaptateur de plus
  sur le même modèle ;
- **SNOMED** est un adaptateur, pas une réécriture ;
- l'ambition **francophone** devient atteignable : ADICAP est un artefact national figé en 2009,
  le Québec code en protocoles nord-américains. Le cœur reste commun.

### Les quatre couches, et leur état

| Couche | Rôle | État V1 |
|---|---|---|
| 1 · Restitution | transformer la dictée sans rien ajouter | partiel — cardinalité cassée |
| 2 · Cohérence | vérifier les invariants du document | **inexistant** |
| 3 · Complétude | signaler ce qui manque, source citée | **fonctionne** |
| 3bis · Dérivation | calculer ce qui se calcule | **inexistant** |
| 4 · Style | écrire comme la maison écrit | partiel — bullet points |

### La loi qui empêche l'usine à gaz

> **Contraindre les assertions, jamais la forme.**

Le système ne limite jamais la façon dont le praticien dicte ni la façon dont le compte rendu
est rédigé. Il limite uniquement ce qui peut être **affirmé sans source**. Toute contrainte qui
ne se ramène pas à cette phrase est à supprimer.

C'est ce qui distingue un outil rigoureux d'un formulaire. Un formulaire contraint la forme et
laisse passer les assertions. On fait l'inverse.

---

## 4. Le modèle de données

C'est la correction de fond de la V1.

```
Dossier
 └─ Prélèvement  (1..n)         ← D1, D3 propres à chacun
     ├─ Technique (1..n)         ← D2 : 1 primaire + n secondaires
     ├─ Lésion    (0..n)         ← D4/D5/D6/D7, positions 5-8
     └─ Mesures, marqueurs, ganglions
```

### Cardinalité des codes ADICAP

```
codes = Σ sur les prélèvements ( 1 primaire + nb de techniques secondaires )
```

Les sept codes secondaires de D2 — extemporané, cytométrie, génétique, congélation, relecture,
ultrastructure, biologie moléculaire — ne remplacent jamais le primaire. Ils s'ajoutent, avec les
mêmes positions 1, 3-4 et 5-8. Seule la position 2 change.

**Exemple.** Deux biopsies bronchiques et un LBA, extemporané et recherche de mutation sur la
première → **5 codes**, pas un.

### Règle d'interface

Le nombre de prélèvements doit être **visible et corrigeable en tête d'écran**, avant toute
proposition. Un dossier à trois prélèvements affiche trois blocs. Si la segmentation s'est
trompée, c'est la première chose que le praticien voit et la première qu'il corrige — pas la
dernière qu'il découvre.

---

## 5. Priorité absolue : sans capture des validations, il n'y a pas d'étude

Aujourd'hui, seuls les commentaires libres remontent. Les modifications et les validations ne
sont pas capturées.

**Or la grille de validation *est* l'instrument de mesure de l'étude.** Sans elle : pas de taux
d'hallucination, pas de taux d'acceptation, pas d'exactitude de codage, pas de mesure
d'explicabilité. Le protocole ne mesure rien.

C'est le chantier numéro un, avant toute nouvelle fonctionnalité. Le gel de version est au
12 septembre.

### Ce qui doit exister au minimum

| Élément | Sans quoi |
|---|---|
| Décision par proposition, 4 choix, persistée | aucune métrique principale |
| Texte corrigé conservé à côté du texte proposé | pas de charge d'édition |
| Horodatage affichage et décision | pas de latence, donc pas de garde-fou sur le verrou |
| Panneau de justification ouvert oui/non | pas de mesure d'explicabilité |
| Question de clôture sur l'omission | pas de taux d'omission |
| Nombre de prélèvements détecté et corrigé | pas de mesure sur le bug principal |

---

## 6. L'écran de revue

### Structure

```
┌────────────────────────────────────────────────────────────┐
│  3 prélèvements détectés          [corriger]               │  ← en premier
│  2 questions avant de commencer   [répondre]               │
├──────────────────┬─────────────────────────────────────────┤
│                  │                                         │
│   TRANSCRIPTION  │   COMPTE RENDU                          │
│   intacte        │   éditable                              │
│   surlignée      │                                         │
│                  │                                         │
├──────────────────┴─────────────────────────────────────────┤
│   PROPOSITIONS   ·   12 / 17 décidées      [export verrouillé] │
└────────────────────────────────────────────────────────────┘
```

### Les règles

- **Le survol d'une proposition surligne son empan** dans la transcription. C'est l'explicabilité
  de premier niveau, gratuite, et c'est ce qui fait qu'on la consulte.
- **Trois volets visibles ensemble**, jamais l'un à la place de l'autre.
- **Décision item par item.** Validation groupée autorisée uniquement sur des reprises littérales
  du verbatim, avec un libellé qui dit ce qu'il fait.
- **Sections conditionnelles.** Une rubrique vide ne s'affiche pas. Biologie moléculaire
  n'apparaît que si une technique moléculaire a été mentionnée.
- **Export verrouillé** tant que tout n'est pas décidé, avec bouton d'abandon motivé.
- **Responsive.** Sur écran étroit, les trois volets deviennent trois onglets, la transcription
  reste accessible d'un tap depuis n'importe quelle proposition.

### Ce qui compte pour le taux de validation réelle

Une décision à moins de 1 200 ms sur une proposition de plus de quinze mots est marquée `hative`.
Elle est comptée, et les résultats sont donnés avec et sans. C'est le garde-fou du verrou
d'export : sans lui, le verrou fabrique un taux de complétion de 100 % qui ne veut rien dire.

---

## 7. Ce qu'on collecte

Trois niveaux, tous en base, tous exportables.

**Par proposition** — identifiant, type, longueur, confiance, empan, règles évaluées, horodatage
d'affichage, horodatage de décision, latence, panneau ouvert, durée d'ouverture, décision
changée après ouverture, décision finale, texte corrigé, cause d'erreur si précisée.

**Par compte rendu** — sept horodatages de t0 à t6, pauses détectées avec durée, nombre de
prélèvements détecté et corrigé, nombre de propositions par type, abstentions, règles de
cohérence déclenchées, questions posées et réponses, caractères modifiés, abandon et motif.

**Par session** — durée, nombre de cas, ordre des cas.

Le schéma JSON complet est dans `MARC_cahier_de_recueil.md`.

---

## 8. Séquence de construction

### Avant le 12 septembre — gel de version

| Rang | Chantier | Pourquoi |
|---|---|---|
| 1 | **Capture des validations et modifications** | sans elle, pas d'étude |
| 2 | **Modèle de cardinalité** prélèvements × techniques | bug le plus signalé |
| 3 | **Codes multiples** primaire et secondaires | découle de 2 |
| 4 | **Télémétrie** latences, panneau, questions | mesure d'explicabilité |
| 5 | **Verrou d'export** + bouton d'abandon | intégrité des données |
| 6 | **Questions de levée de doute** — les 3 pré-rédigées sur D1 | démonstration au congrès |
| 7 | **Sections conditionnelles** et style rédigé | retours directs |

### Après le congrès

Couche de cohérence — le catalogue déterministe, sans risque réglementaire, et le meilleur
argument commercial. Puis dérivation pTNM sur deux ou trois organes. Puis adaptateur de cotation.

### Ce qui n'est pas prioritaire

La couverture. Trois organes en profondeur valent mieux que cinquante en surface, et le corpus du
laboratoire dira lesquels.

---

## 9. Ce dont j'ai besoin, par ordre de valeur

1. **Le corpus de comptes rendus du laboratoire**, pseudonymisé. Donne le style, les gabarits de
   description, les règles de complétude implicites, et un jeu d'évaluation hors ligne. Rien
   d'autre n'a ce rendement.
2. **Le journal des comptes rendus rectificatifs**, avec motif. La vérité terrain de quelles
   erreurs comptent — elle oriente la couche de cohérence vers ce qui fait mal.
3. **Deux demi-journées de Jéromine**, structurées : la table geste × organe pour I/O, les data
   sets de complétude sur trois organes, la validation des formulations de questions.
4. **Les tables de dérivation** : édition pTNM par organe, classification de Nancy, grades. Nommer
   les éditions, elles changent.
5. **La sortie n-best** de la reconnaissance vocale.

---

## 10. Le message du congrès

Ce qui doit rester à la fin d'une présentation de dix minutes :

> Les pathologistes utilisent déjà des assistants génériques pour rédiger. Cet outil fait la même
> chose, mais **il ne dit rien qu'on ne lui ait dit**, il **montre d'où vient chaque proposition**,
> il **calcule ce qui se calcule en citant sa règle**, il **compte ce qui doit être compté**, et
> il **demande quand il ne sait pas**. Voici, mesuré sur N comptes rendus et dix praticiens, ce
> que ça donne.

La démonstration la plus percutante n'est pas un compte rendu réussi. C'est un cas où le système
**refuse de trancher**, affiche pourquoi, pose une question — et où l'assistant généraliste
affirme avec aplomb une réponse fausse.
