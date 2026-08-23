# MARC — cahier de recueil et spécification d'instrumentation

**Version 1.0 · à figer avant le rodage · résumé soumis, présentation Carrefour Pathologie 18-20 novembre 2026**

Ce document contient tout ce qui doit exister dans le logiciel pour que l'étude produise des
résultats défendables : les questions posées, les validations demandées, la mesure du temps, le
verrouillage de l'export, et le schéma d'événements à logger.

---

## 1. Décisions actées

| Décision | Conséquence technique |
|---|---|
| **Entrée = dictée seule.** Pas de dossier clinique, pas de demande, pas de SGL. | « Non dicté » = hallucination, sans ambiguïté. Chapitre 0 d'ADICAP hors périmètre. |
| **Conservation = transcription seule.** Pas d'audio après transcription. | La justification s'ancre sur l'empan de texte, pas sur l'audio. Surface RGPD réduite. |
| **D2 = H par défaut.** Bascule vers C sur déclencheurs cytologiques uniquement. | Position 2 n'est pas une décision de modèle. Et D2 = H **interdit D7**. |
| **D1 se lit dans le segment d'ouverture.** | Classification du premier énoncé, pas du texte entier. |
| **« macro » / « micro » = marqueurs de section**, jamais D2. | Règle explicite dans le moteur. Piège classique des LLM généralistes. |
| **Export verrouillé tant que tout n'est pas décidé.** | Empêche la modification hors traçabilité. À coupler impérativement à la latence de décision. |

### Conséquence de la non-conservation de l'audio

L'ancrage de la justification devient : **empan de caractères dans la transcription**, surligné
au survol de la proposition. C'est plus simple à implémenter que la réécoute, et cognitivement
plus rapide à vérifier pour le praticien — donc probablement meilleur pour le taux de
consultation.

Ce qu'on perd : la possibilité de distinguer une erreur de transcription d'une erreur
d'interprétation après coup. À compenser par une case dédiée dans la grille de revue,
section 3.

---

## 2. Ce qui se valide, et ce qui ne se valide pas

### Le principe

> **Ce qui est une copie littérale du verbatim n'est pas une proposition, c'est une
> transcription. Seule l'inférence se valide.**

C'est le principe qui empêche le nombre de cases de partir en vrille. Une mesure « 4 mm » reprise
telle quelle de la dictée n'engage aucun jugement du système. Un code ADICAP, un rattachement de
lésion, une suggestion de complétude en engagent un.

**Cible : 8 à 15 validations par compte rendu.** Au-delà de 20, la granularité est mauvaise et
le praticien clique sans lire — c'est-à-dire que la mesure se détruit elle-même.

### Se valide, item par item

| Objet | Pourquoi |
|---|---|
| Chaque assertion clinique extraite (lésion, marqueur + résultat, comptage, latéralité) | Inférence sur le sens |
| Le rattachement lésion → prélèvement | Erreur silencieuse la plus dangereuse |
| Chaque code ADICAP proposé, position par groupe | Cœur du dispositif |
| L'aiguillage D4 / D5 / D6 / D7 | Une erreur ici invalide tout l'aval |
| Chaque suggestion de complétude | Frontière réglementaire |
| Le texte de conclusion | Portée diagnostique maximale |

### Ne se valide pas

| Objet | Traitement |
|---|---|
| Mise en forme : gras, italique, ordre des sections, ponctuation | Un item global unique en fin de revue |
| Phrases de liaison et formules standardisées | Aucune validation |
| Mesures et comptages repris littéralement du verbatim | Affichés avec l'empan surligné, sans case |
| Titre du compte rendu | Éditable directement, sans case |

### Cas particulier : la validation groupée

Interdite sur les codes, l'aiguillage, la conclusion et les suggestions de complétude.

Autorisée sur un bloc de valeurs numériques **si et seulement si** chacune est une reprise
littérale du verbatim, avec affichage des empans. Le bouton doit dire ce qu'il fait :
« Confirmer les 6 valeurs reprises de ma dictée », jamais « Tout valider ».

---

## 3. La grille de revue

### 3.1 Propositions de restitution

Quatre choix exclusifs, un clic.

| | Libellé affiché | Mesure |
|---|---|---|
| ✓ | **Conforme** — je valide tel quel | Acceptation sans modification |
| ✎ | **À corriger** — juste sur le fond, à retoucher sur la forme | Charge d'édition |
| ✗ | **Non dicté** — je n'ai pas dit ça | **Hallucination** |
| ⊘ | **Hors sujet** — proposition non pertinente ici | Bruit |

Sur ✎ et ✗, une seconde question à un clic, **facultative** (bouton « préciser »), qui permet de
séparer les deux mécanismes d'erreur maintenant qu'il n'y a plus d'audio :

> ☐ La transcription a mal compris un mot  ☐ La transcription était juste, l'interprétation est fausse

### 3.2 Codes ADICAP

Affichage par groupe de positions, avec le chemin de descente visible.

| | Libellé affiché |
|---|---|
| ✓ | **Juste** |
| ✎ | **À corriger** → sélecteur dans le vocabulaire fermé du niveau concerné |
| ? | **Je ne sais pas** — n'entre pas dans le numérateur ni le dénominateur d'exactitude |

Le troisième choix est important : sans lui, un praticien qui n'est pas sûr valide par défaut, et
tu mesures de l'acquiescement au lieu de l'exactitude.

### 3.3 Suggestions de complétude

| | Libellé affiché | Mesure |
|---|---|---|
| ✓ | **Pertinent, je l'ajoute** | Valeur ajoutée |
| ~ | **Pertinent, mais je ne le mets pas ici** | Utile non retenu — **pas** un faux positif |
| ✗ | **Non pertinent ici** | Faux positif |

Confondre les deux dernières lignes fausserait entièrement le taux de faux positifs.

### 3.4 Question de clôture, obligatoire

> **Quelque chose que vous avez dicté a-t-il été omis ?**
> ☐ Non ☐ Oui → texte libre

C'est la mesure d'omission. Un champ, dix secondes, obligatoire pour débloquer l'export.

---

## 4. Verrouillage de l'export

### Règle

Export DOCX, copier-coller et impression désactivés tant que **toutes** les propositions n'ont
pas reçu une décision et que la question de clôture n'a pas été renseignée.

Indicateur permanent en haut de l'écran : `14 / 17 propositions décidées`.

### Les trois garde-fous, non négociables

**1. Une sortie de secours doit exister.** Bouton « Abandonner ce cas », avec un motif à choisir
parmi une liste courte : *outil trop lent · propositions inexploitables · interruption ·
cas trop complexe · autre*. Sans cette porte, on obtiendra des validations de complaisance pour
sortir de l'écran — et l'étude sera fausse tout en paraissant parfaite.

**2. Le verrou seul déplace le biais, il ne le supprime pas.** Il crée une pression à cliquer
vite. Il n'est interprétable que couplé à la latence de décision (section 5). Toute validation
sous **1 200 ms** sur une proposition de plus de 15 mots est marquée `hative` et analysée à part.

**3. Ce qui se passe après le déverrouillage est hors traçabilité.** À déclarer comme limite. Une
question à la session suivante, à coût nul : *« Avez-vous modifié le compte rendu précédent après
l'avoir exporté ? »*

### Ce qu'il ne faut pas verrouiller

Ne bloque jamais l'accès au verbatim, ni la possibilité de modifier le texte du compte rendu en
cours de revue. Le verrou porte sur la **sortie**, pas sur le travail.

---

## 5. Mesure du temps

Il n'y a pas de bras témoin. Le temps est donc **descriptif**, jamais comparatif. Mais il doit
être mesuré proprement, parce que c'est ce qu'on te demandera en salle.

### Horodatages à poser

| Marqueur | Événement |
|---|---|
| `t0` | début d'enregistrement |
| `t1` | fin d'enregistrement |
| `t2` | affichage des propositions |
| `t3` | première décision |
| `t4` | dernière décision |
| `t5` | question de clôture renseignée |
| `t6` | export effectué |

### Métriques dérivées

| Métrique | Calcul | Rôle |
|---|---|---|
| Durée de dictée | `t1 − t0` | covariable |
| Latence système | `t2 − t1` | qualité de service, pas d'étude |
| **Temps de revue** | `t5 − t2`, net des pauses | **métrique principale de temps** |
| **Temps praticien total** | `(t1 − t0) + (t5 − t2)`, net des pauses | descriptif |
| Délai par proposition | intervalle entre décisions consécutives | détection des validations hâtives |

### Neutralisation des interruptions — indispensable

Sans ça, la distribution est inexploitable : un pathologiste est interrompu en permanence.

- **Page Visibility API** : onglet masqué ou fenêtre défocalisée → horloge en pause.
- **Inactivité** : plus de 90 secondes sans aucun événement → pause rétroactive à partir de la
  dernière action, reprise au geste suivant.
- Les pauses sont **loguées séparément**, pas seulement soustraites. Leur nombre et leur durée
  sont eux-mêmes un résultat sur la faisabilité en conditions réelles.

### Restitution

**Médiane et intervalle interquartile**, jamais la moyenne — la distribution sera fortement
asymétrique à droite. Stratifier par nombre de prélèvements et par nombre de propositions, qui
sont les deux vrais déterminants de la charge.

**Aucune phrase comparative dans le résumé ni dans le poster.** Pas de « 30 % plus rapide ». Le
temps est un descripteur de faisabilité, pas une démonstration d'efficacité. C'est précisément ce
qui distinguera ce travail des communications industrielles.

---

## 6. Toutes les questions

### 6.1 À l'inclusion — une fois, environ 5 minutes

**Profil**
1. Années d'exercice depuis la fin de l'internat.
2. Type d'exercice : CHU · CH · libéral · mixte.
3. Nombre approximatif de comptes rendus par semaine.
4. Localisations les plus fréquentes dans votre activité *(choix multiple)*.

**Pratique actuelle de rédaction**
5. Comment rédigez-vous habituellement vos comptes rendus ? saisie clavier · dictée avec
   transcription humaine · reconnaissance vocale · mixte.
6. Si reconnaissance vocale, laquelle ?
7. Combien de temps estimez-vous consacrer en moyenne à la rédaction d'un compte rendu de
   routine ? *(minutes)*
8. Sur une échelle de 1 à 5, la rédaction représente-t-elle une charge pesante dans votre
   activité ?

**Usage actuel de l'IA générative — la question qui porte le résumé**
9. Avez-vous déjà utilisé un assistant d'IA générative *(ChatGPT, Claude, Copilot, autre)* pour
   rédiger, reformuler ou structurer un compte rendu ?
   jamais · une ou deux fois · occasionnellement · régulièrement · systématiquement.
10. *Si oui :* lequel ou lesquels ?
11. *Si oui :* pour quoi faire ? *(choix multiple : mise en forme · reformulation · traduction ·
    rédaction de la conclusion · recherche d'information · autre)*
12. *Si oui :* saviez-vous où sont hébergées les données transmises ? oui · non · je ne me suis
    pas posé la question.
13. Sur une échelle de 1 à 5, cet usage vous pose-t-il un problème de confidentialité ?
14. Sur une échelle de 1 à 5, faites-vous confiance à ce que produit un tel assistant ?

**Attentes**
15. Qu'attendez-vous en priorité d'un outil d'assistance à la rédaction ? *(classement de 4
    propositions : gagner du temps · réduire les oublis · homogénéiser mes comptes rendus ·
    réduire la fatigue)*

---

### 6.2 Après chaque cas — environ 40 secondes

Affiché immédiatement après la validation, jamais en fin de session : les jugements
rétrospectifs globaux sont peu fiables.

**Obligatoire, avant déverrouillage**
- Quelque chose que vous avez dicté a-t-il été omis ? ☐ Non ☐ Oui → lequel

**Cinq items, de 1 « pas du tout d'accord » à 5 « tout à fait d'accord »**
1. La proposition correspondait à ce que j'ai dicté.
2. J'ai dû faire beaucoup de corrections. *(item inversé)*
3. Les suggestions de complétude m'ont été utiles sur ce cas. *(+ « non applicable »)*
4. J'ai compris pourquoi le système proposait ce qu'il proposait.
5. J'ai confiance dans le compte rendu que je viens de valider.

**Un item ordinal**
6. Par rapport à ma pratique habituelle, ce compte rendu m'a pris : beaucoup plus de temps ·
   plus · autant · moins · beaucoup moins.

**Un champ libre facultatif**, une ligne.

> Si le rodage montre que 40 secondes est déjà trop, retirer l'item 5 en premier, puis l'item 3.
> Ne jamais retirer l'item 4 : c'est la mesure d'explicabilité déclarée, et elle n'a pas de
> substitut.

---

### 6.3 En fin d'étude — environ 15 minutes

**F-SUS** — version française validée du System Usability Scale, 10 items, échelle à 5 points,
polarité alternée. Récupérer la formulation exacte auprès de la source et la citer :
Gronier, G. & Baudet, A. (2021), *Psychometric evaluation of the F-SUS*, International Journal
of Human–Computer Interaction, 37(16), 1571-1582. Ne pas retraduire soi-même : c'est ce qui rend
le score comparable.

*Cotation :* items impairs, score = réponse − 1 ; items pairs, score = 5 − réponse ; somme × 2,5,
résultat de 0 à 100.

**PDQI-9** — qualité documentaire perçue, 9 dimensions, à appliquer aux comptes rendus produits
avec l'outil.

**Charge de travail** — 4 items : exigence mentale, rythme, effort, frustration, chacun sur une
échelle de 1 à 10.

**Comparaison à la pratique habituelle** — trois items ordinaux : le temps · la qualité du
compte rendu · la charge mentale, chacun de « nettement moins bon » à « nettement meilleur ».

**Comparaison à un assistant généraliste** *(pour ceux ayant répondu oui à la question 9)*
- Par rapport à l'assistant que vous utilisiez, l'outil est : moins bon · équivalent · meilleur,
  sur chacun de ces axes : justesse du contenu · possibilité de vérifier · confiance ·
  confort d'usage.

**Intention**
- Souhaitez-vous continuer à utiliser l'outil ? oui · non · peut-être, et pourquoi.
- Le recommanderiez-vous à un confrère ? *(0 à 10)*

**Deux questions ouvertes**
- Qu'est-ce qui vous a le plus gêné ?
- Qu'est-ce qui vous manquerait le plus si on vous le retirait demain ?

---

### 6.4 Entretien semi-structuré — 4 ou 5 volontaires, 25 minutes

Enregistré, transcrit, analysé thématiquement. C'est la partie qui portera la présentation
orale, et c'est ce qui manque le plus dans la littérature actuelle.

1. Racontez-moi comment s'est passé votre premier cas avec l'outil.
2. À quel moment avez-vous cessé de vérifier systématiquement ? Ou n'est-ce jamais arrivé ?
3. Vous est-il arrivé d'ouvrir le panneau de justification ? Dans quelles circonstances ?
4. Y a-t-il eu une proposition qui vous a mis mal à l'aise ? Laquelle, et pourquoi ?
5. Est-ce que l'outil a changé quelque chose à votre façon de dicter ?
6. Les suggestions de ce qui manquait : utiles, ou intrusives ?
7. Qu'est-ce qui vous empêcherait de l'utiliser en routine demain ?
8. Que diriez-vous à un confrère qui vous demande si ça vaut le coup ?
9. Est-ce que vous confieriez à cet outil un cas difficile, ou seulement de la routine ?
10. Quelque chose que je n'ai pas demandé et qui vous paraît important ?

---

## 7. Télémétrie passive — aucune charge pour le praticien

À loguer silencieusement. C'est ce qui produit la mesure d'explicabilité, et personne ne la
publie.

### Par proposition
- identifiant, type *(restitution · code · complétude)*, longueur en mots
- score de confiance du système
- horodatage d'affichage, horodatage de décision, **latence en millisecondes**
- panneau de justification ouvert : oui / non, et durée d'ouverture
- **décision modifiée après ouverture du panneau : oui / non** ← la métrique clé
- empan source associé, et longueur de cet empan
- décision finale, et texte corrigé le cas échéant

### Par compte rendu
- les sept horodatages `t0` à `t6`
- nombre et durée des pauses détectées
- nombre de propositions, par type
- nombre d'abstentions du système
- règles déterministes déclenchées, avec identifiant de règle
- nombre de caractères modifiés dans le texte final
- abandon éventuel, avec motif

### Par session
- durée totale, nombre de cas
- ordre des cas *(pour analyser l'effet d'apprentissage)*

---

## 8. Schéma d'événement

Format minimal, un enregistrement par décision. Aucune donnée identifiante.

```json
{
  "session_id": "s_0007",
  "practicien_id": "p_03",
  "cr_id": "cr_0142",
  "cr_index_session": 3,
  "proposition_id": "pr_08",
  "type": "code",
  "sous_type": "aiguillage",
  "positions": [5, 6, 7, 8],
  "valeur_proposee": "A7N4",
  "chemin": ["D5", "A tumeur adénomateuse", "7 cancer invasif", "N4"],
  "confiance": 0.81,
  "empan": { "debut": 412, "fin": 448, "longueur_mots": 6 },
  "regles_evaluees": [
    { "id": "masque_d5", "resultat": "ok" },
    { "id": "d7_exclu_si_d2_h", "resultat": "non_applicable" }
  ],
  "affiche_a": "2026-09-22T10:14:03.220Z",
  "decide_a": "2026-09-22T10:14:11.870Z",
  "latence_ms": 8650,
  "hative": false,
  "justif_ouverte": true,
  "justif_duree_ms": 4100,
  "decision_changee_apres_justif": true,
  "decision": "corrige",
  "valeur_retenue": "A7N2",
  "cause_erreur": "interpretation"
}
```

---

## 9. Plan d'analyse

### Unité d'analyse

**La proposition.** Dix praticiens × 25 comptes rendus × 8 à 15 propositions ≈ **2 000 à 3 750
observations**. À n = 2 000, un taux de 2 % s'estime à ± 0,6 point près. Modèle mixte avec effet
aléatoire praticien pour tenir compte du regroupement.

### Résultats principaux

| Indicateur | Calcul |
|---|---|
| Taux d'hallucination | propositions ✗ / propositions totales |
| Taux d'omission | comptes rendus avec omission signalée / comptes rendus totaux |
| Acceptation sans modification | propositions ✓ / propositions totales |
| Exactitude du code | codes ✓ / (codes ✓ + codes ✎), les « je ne sais pas » exclus |
| Pertinence de la complétude | (✓ + ~) / suggestions totales |
| **Taux de consultation des justifications** | propositions avec panneau ouvert / propositions totales |
| **Effet de la justification** | décisions changées après ouverture / ouvertures |
| Score F-SUS | moyenne et écart-type |

### Analyses de sensibilité, à pré-déclarer

- Résultats en excluant les décisions marquées `hative`.
- Résultats par tercile d'ordre de cas, pour objectiver l'effet d'apprentissage — et le
  relâchement de vigilance.
- Résultats selon que le praticien déclarait ou non un usage antérieur d'IA générative.

### Ce qui n'est pas analysé

Aucune comparaison de temps avec la pratique habituelle. Aucune inférence de performance
diagnostique. Ces deux limites sont écrites dans le protocole, dans le résumé et dans la
discussion — c'est ce qui rend le reste crédible.

---

## 10. Calendrier

| Période | Étape |
|---|---|
| 24 – 31 août | Gel de la spécification. Implémentation de la grille, du verrou, de la télémétrie. |
| 1 – 12 septembre | Rodage sur 1 ou 2 praticiens. Calibrage du nombre de validations par compte rendu. Correction des blocages. |
| **12 septembre** | **Gel de version. Plus aucune modification jusqu'au gel des données.** |
| 15 septembre – 31 octobre | Recueil, 10 praticiens, 6 semaines, objectif 25 cas chacun. Point hebdomadaire sur le volume. |
| 1 – 7 novembre | Gel des données. Analyse. Entretiens semi-structurés. |
| 8 – 14 novembre | Poster ou diaporama. Relecture par un pathologiste co-auteur. |
| 18 – 20 novembre | Carrefour Pathologie, CNIT Forest Paris-La Défense. |
