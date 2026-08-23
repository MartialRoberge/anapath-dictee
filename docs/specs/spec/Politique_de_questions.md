# Politique de levée de doute — quand le logiciel pose une question

S'applique à D1, D2, D3 et à toute la cascade. À figer avant le gel de version.

---

## 1. Pourquoi c'est une bonne idée, et pourquoi ça peut tout casser

Une question bien posée transforme une hallucination probable en une réponse juste, pour un tap.
C'est le meilleur rapport valeur/coût de tout le dispositif.

Mais trois questions par compte rendu, c'est un assistant. Douze, c'est un formulaire — et le
formulaire est exactement ce qui fait abandonner les outils de dictée. **Le mécanisme de question
n'a de valeur que s'il est rare.** Toute la spécification ci-dessous existe pour le maintenir rare.

---

## 2. Trois comportements, à ne jamais confondre

| Situation | Comportement | Exemple |
|---|---|---|
| Un candidat net | **Proposer**, le praticien valide | « biopsie échoguidée » → H |
| Plusieurs candidats, et l'écart change la sortie | **Demander** | « thyroïdectomie » → I ou O ? |
| Information absente, ou repli normé disponible | **S'abstenir** | « inflammation chronique » → `7600` SAI |

### La règle qui sépare *demander* et *s'abstenir*

> **On demande quand la réponse est dans la tête du praticien et coûte un tap.
> On s'abstient quand l'information n'existe pas, ou quand le repli SAI est une réponse juste.**

Le pathologiste sait parfaitement s'il a reçu une thyroïde entière ou un lobe. Il ne l'a
simplement pas dit. → question.

Le pathologiste qui dit « muqueuse bronchique discrètement inflammatoire » a produit un énoncé
complet et le code `7600` est juste. Lui demander de préciser le sous-type, c'est lui faire faire
du travail que le référentiel ne demande pas. → abstention, sans question.

Cette distinction est ce qui empêche le compteur de questions d'exploser.

---

## 3. La règle de valeur d'information

> **Ne poser une question que si les réponses possibles conduisent à des sorties différentes.**

Si deux candidats aboutissent au même code final, au même compte rendu et aux mêmes suggestions
de complétude, la question ne sert à rien — même si le système est incertain. L'incertitude n'est
pas un motif suffisant : seule l'incertitude **qui change quelque chose** l'est.

À implémenter littéralement : simuler l'aval pour chaque réponse possible, comparer les sorties,
ne poser la question que si elles diffèrent.

---

## 4. Les trois sources de doute

### 4.1 Ambiguïté structurelle du référentiel — la plus précieuse

Elle est **connue à l'avance et énumérable**. Trois cas identifiés sur D1 :

| Ambiguïté | Question | Impact |
|---|---|---|
| I contre O | L'organe a-t-il été retiré en entier ? | position 1 |
| P contre H | Le prélèvement a-t-il été guidé par l'imagerie ? | position 1 |
| C contre G | La cytoponction a-t-elle été guidée par l'imagerie ? | position 1 |

L'avantage décisif : **la question est rédigée à l'avance et validée par un pathologiste.** Elle
n'est pas générée par un modèle. C'est une formulation fixe, testable, reproductible — et donc
défendable dans une publication.

Un filtre est indispensable sur la question du guidage biopsique : sans restriction par organe,
elle se poserait sur presque tous les cas. Il faut la liste des organes habituellement biopsiés
sous guidage. À demander à Jéromine.

### 4.2 Divergence de transcription

Signal utile, mais **pas le score de confiance brut**. Les modèles de reconnaissance vocale de
type Whisper produisent des log-probabilités mal calibrées : elles ordonnent correctement mais
leur valeur absolue ne veut pas dire grand-chose. Deux conséquences pratiques :

- Ne pas fixer de seuil absolu à l'avance. **Calibrer sur les données du rodage**, en régressant
  le score sur l'issue réelle (le praticien a-t-il corrigé ?).
- Préférer la **divergence n-best** : si les deux meilleures hypothèses de transcription diffèrent
  sur un empan porteur de décision, c'est un signal nettement plus fiable qu'une log-probabilité.
  « biopsie sous écho » contre « biopsie sur écho » ne change rien ; « lobectomie » contre
  « lobotomie » change tout.

### 4.3 Conflit de règle déterministe

Le moteur détecte une incohérence — un code D7 avec un D1 non cytologique, une position 14-15
renseignée sur une tumeur primitive. Ici, **la question est souvent inutile** : la règle indique
déjà quelle branche est fausse. Corriger silencieusement en le signalant vaut mieux que
d'interroger. On ne demande que si la règle ne dit pas laquelle des deux branches céder.

---

## 5. Ergonomie

### Quand
**En tête de l'écran de revue, avant les propositions.** Jamais pendant la dictée — c'est le seul
moment où le praticien est en flux, et l'interrompre annule le bénéfice de la dictée libre.

Répondre en premier réduit le nombre de propositions à valider ensuite. La question se paie
elle-même, et il faut que ce soit visible : « 2 questions — répondre maintenant réduit les
vérifications à suivre. »

### Combien
**Trois maximum par compte rendu.** Au-delà, garder les trois à plus fort impact aval — celles qui
déterminent le plus de positions — et s'abstenir sur le reste.

Le nombre de questions posées est lui-même un indicateur de qualité du système. S'il monte, c'est
que le lexique ou la table geste × organe sont incomplets, pas que l'outil est prudent.

### Comment
- Deux ou trois options fermées, un tap. **Jamais de texte libre.**
- Toujours une issue : « je ne sais pas » ou « ne pas coder », qui déclenche l'abstention.
- **La question affiche son déclencheur** : l'empan surligné dans la transcription qui l'a
  provoquée. C'est l'explicabilité rendue actionnable — le praticien voit pourquoi on lui demande.
- Une question sans déclencheur affichable ne se pose pas.

### Exemple

> **Vous avez dicté** « … thyroïdectomie, macro, lobe droit 4 cm … »
> **L'organe a-t-il été retiré en entier ?**
> `En entier` · `En partie` · `Je ne sais pas`
>
> *Détermine le mode de prélèvement — exérèse complète (O) ou partielle (I).*

---

## 6. Ce que ça apporte à l'étude

Trois choses, gratuitement.

**Une métrique nouvelle et publiable.** Nombre de questions par compte rendu, taux de réponse,
temps de réponse, part des « je ne sais pas ». Personne ne rapporte ça, et c'est exactement le
genre de mesure qui distingue un outil contrôlé d'un assistant généraliste.

**Des étiquettes supervisées gratuites.** Chaque réponse est une annotation experte sur le cas
précis où le système était le plus incertain. C'est le jeu d'entraînement le mieux ciblé qu'on
puisse constituer.

**Un indicateur comportemental.** Est-ce que les praticiens répondent ou passent outre ? Le taux
de « je ne sais pas » et le taux d'esquive disent si le mécanisme est perçu comme utile ou comme
une friction. À croiser avec l'item 4 du questionnaire par cas.

### À ajouter au schéma d'événement

```json
{
  "type": "question",
  "question_id": "d1_exerese_i_o",
  "source_doute": "structurelle",
  "empan_declencheur": { "debut": 12, "fin": 27 },
  "options": ["O", "I", "abstention"],
  "affichee_a": "...",
  "repondue_a": "...",
  "latence_ms": 2400,
  "reponse": "I",
  "impact_aval": { "positions": [1], "propositions_evitees": 2 }
}
```

Le champ `propositions_evitees` est le plus intéressant : il mesure ce que la question a fait
gagner en aval, et c'est ce qui justifiera de la garder ou de la supprimer.

---

## 7. Seuils proposés, à calibrer au rodage

| Paramètre | Valeur de départ | À ajuster sur |
|---|---|---|
| Questions maximum par compte rendu | 3 | plaintes en rodage |
| Divergence n-best déclenchant un doute | les 2 meilleures hypothèses diffèrent sur un empan de décision | taux de faux positifs |
| Seuil de confiance ASR | **à ne pas fixer à l'avance** | régression score / correction réelle |
| Écart entre candidats du référentiel | à calibrer | taux de correction observé |

---

## 8. Ce qu'il faut demander à Jéromine

1. **Pour quels organes une « biopsie » sans autre précision est-elle habituellement guidée par
   l'imagerie ?** Sans cette liste, la question du guidage se poserait presque à chaque cas.
2. **Trois questions par compte rendu, c'est acceptable ou déjà trop ?** Tester en rodage sur cinq
   cas réels et écouter la réaction, pas la réponse théorique.
3. **La formulation « L'organe a-t-il été retiré en entier ? » est-elle la bonne ?** C'est le
   vocabulaire du praticien qui doit primer, pas celui du thésaurus.
4. **Y a-t-il d'autres ambiguïtés structurelles qu'elle connaît par expérience** et qui mériteraient
   une question pré-rédigée ? Elle en a sûrement en tête pour D3.
