# L'outil idéal — architecture cible et ce qu'il faut pour le construire

---

## 1. Le renversement

**Objectif : le meilleur compte rendu possible. Le code est un export.**

ADICAP est un bon squelette de contrainte — vocabulaire fermé, vérifiable, non hallucinable.
Mais c'est un artefact national français, figé en 2009. Pour un outil francophone, le codage doit
être un **module de sortie interchangeable**, pas le cœur.

| | Version actuelle | Version cible |
|---|---|---|
| Cœur | composer un code ADICAP | produire un compte rendu structuré, cohérent, complet |
| ADICAP | ossature | module d'export France |
| Marché | France | francophonie |

---

## 2. Les quatre couches

### Couche 1 — Restitution fidèle
Transformer la dictée en compte rendu structuré, sans jamais rien ajouter. Ancrage par empan,
abstention plutôt que devinette. **C'est fait, c'est spécifié.**

### Couche 2 — Cohérence interne *(la couche qui manque, et la plus rentable)*
Vérification déterministe des invariants du document. Ne raisonne pas, ne diagnostique pas,
compte et compare. Catalogue en section 3.

### Couche 3 — Complétude
Ce qui aurait dû être dit, par organe et famille lésionnelle. Data sets synoptiques, cités.

### Couche 4 — Style de la maison
Le compte rendu doit ressembler à ceux du laboratoire, pas à de la prose générique. Appris du
corpus du labo, commutable par site.

**Les couches 2 et 4 sont celles que ChatGPT ne peut pas faire.** La 2 parce qu'il n'a pas de
représentation structurée du document ; la 4 parce qu'il ne connaît pas la maison.

---

## 3. Catalogue de cohérence — implémentable sans modèle, sans risque

Chaque règle est un compteur ou une comparaison. Aucune interprétation clinique. Aucun risque
réglementaire : on ne dit pas ce qui est vrai, on dit ce qui est incohérent avec le reste du
document.

### Numérotation et comptage

| # | Règle | Exemple d'alerte |
|---|---|---|
| C1 | Numérotation des blocs continue, unique, sans double attribution | *bloc 8 attribué à « tumeur » puis à « ganglion »* |
| C2 | Nombre de prélèvements annoncé = nombre de sections numérotées | *2 prélèvements annoncés, 3 décrits* |
| C3 | Somme des ganglions par station = total annoncé | *stations : 5+2+3+1+2 = 13, total annoncé 14* |
| C4 | Ganglions envahis ≤ ganglions examinés | *3 envahis sur 2 examinés* |
| C5 | Fragments annoncés en macroscopie = fragments décrits en microscopie | |

### Mesures

| # | Règle |
|---|---|
| C6 | Taille en conclusion = plus grande dimension de la macroscopie |
| C7 | Unités homogènes dans un même paragraphe (cm / mm) |
| C8 | Toute dimension a trois axes ou une justification |
| C9 | Marges mesurées présentes si exérèse d'une lésion maligne |

### Cohérence microscopie ↔ conclusion

| # | Règle |
|---|---|
| C10 | Toute lésion citée en conclusion apparaît en microscopie |
| C11 | Tout marqueur cité en conclusion figure dans le tableau IHC |
| C12 | Aucune négation inversée — « pas de cellule anormale » ≠ « pas de cellule normale » |
| C13 | Latéralité identique entre titre, macroscopie et conclusion |
| C14 | Organe identique entre titre, macroscopie et conclusion |

### Complétude conditionnelle *(dépend de la couche 3)*

| # | Règle |
|---|---|
| C15 | Tumeur maligne + pièce d'exérèse → marges obligatoires |
| C16 | Curage → nombre examiné et nombre envahi obligatoires |
| C17 | Carcinome → grade obligatoire selon le référentiel de l'organe |

### Pourquoi cette couche est le meilleur argument commercial

Le **taux de comptes rendus rectificatifs** est un indicateur qualité suivi en anatomie
pathologique. Une erreur de numérotation de bloc, un compte ganglionnaire faux, une latéralité
divergente sont des causes classiques de rectificatif — et toutes détectables ici.

C'est une valeur **auditée, pas déclarée** : on peut mesurer le nombre d'incohérences interceptées
avant signature. C'est aussi un critère d'étude excellent, et il n'entre en concurrence avec aucun
jugement diagnostique.

---

## 4. Ce dont j'ai besoin, par ordre de valeur

### 4.1 Le corpus de comptes rendus du laboratoire — de loin le plus important

**Ce qu'il faut :** 2 000 à 10 000 comptes rendus réels, pseudonymisés, avec leur date. Sans les
dictées associées si nécessaire — les comptes rendus seuls suffisent déjà.

**Ce qu'on en tire, et qu'aucune autre source ne donne :**
- le style de la maison, apprenable directement (couche 4)
- l'inventaire réel des formulations utilisées par organe
- **les règles de complétude implicites** : ce que les seniors écrivent systématiquement pour un
  carcinome mammaire, c'est empiriquement le data set du labo. Dérivé plutôt que construit à la
  main.
- la distribution réelle des cas, qui dit par quels organes commencer
- un jeu d'évaluation hors ligne : on peut tester la pipeline sans mobiliser un praticien

**Faisabilité :** rétrospectif, en interne, pseudonymisé. C'est le lot le plus accessible et le
plus transformant.

### 4.2 Le journal des comptes rendus rectificatifs

**Ce qu'il faut :** la liste des comptes rendus corrigés après diffusion, avec le motif.

**Pourquoi :** c'est la vérité terrain de « quelles erreurs comptent vraiment ». Elle oriente le
catalogue de cohérence vers ce qui fait mal, plutôt que vers ce qui est facile à vérifier. Et elle
donne le dénominateur pour évaluer l'impact.

C'est probablement la donnée la plus sous-estimée du projet.

### 4.3 Deux demi-journées de Jéromine, structurées

Pas de la relecture diffuse — trois livrables précis :

1. **La table geste × organe** pour I/O. Trente minutes.
2. **Les data sets de complétude sur trois organes** à fort volume. Une demi-journée, en partant
   des comptes rendus standardisés existants plutôt que de zéro.
3. **La validation des formulations de questions** et du catalogue de cohérence. Une heure.

### 4.4 Les référentiels de complétude

Comptes rendus standardisés français par localisation, protocoles synoptiques internationaux,
classification OMS en vigueur pour la terminologie. À rassembler et à confronter au corpus : là où
le labo écrit systématiquement quelque chose que le référentiel ne demande pas, c'est une règle
maison à conserver.

### 4.5 La sortie n-best de la reconnaissance vocale

Pas seulement la meilleure hypothèse. La divergence entre les deux premières est le signal de
doute le plus fiable, et il ne coûte rien à exposer.

### 4.6 Quelques dictées appariées

100 à 200 couples dictée / compte rendu final. Pas indispensable au départ, mais c'est ce qui
permet de mesurer hors ligne, sans mobiliser les praticiens, à chaque itération.

---

## 5. La ligne rouge, qui est aussi l'argument réglementaire

> **L'outil n'introduit jamais une assertion clinique absente de la dictée.**

Il peut réorganiser, reformater, compter, comparer, signaler un manque en citant sa source,
proposer un code à valider. Il ne peut pas affirmer.

Cette seule phrase fait trois choses à la fois : elle borne le risque, elle définit la frontière
du dispositif médical, et elle est exactement ce que ChatGPT ne respecte pas.

Corollaire pour la couche 3 : une suggestion de complétude dit *« le référentiel X attend une
mesure de marge ici »*, jamais *« la marge est saine »*. La nuance est tout.

---

## 6. Ce qu'il ne faut pas faire

**Ne pas viser la couverture.** Trois organes traités en profondeur valent mieux que cinquante en
surface. Le corpus dira lesquels.

**Ne pas faire de diagnostic.** Même suggéré, même prudent. C'est la seule chose qui peut tuer le
projet, et elle ne rapporte rien que la couche 2 ne rapporte déjà.

**Ne pas intégrer les SGL tôt.** L'autonomie est ce qui rend le déploiement possible à dix
laboratoires. À garder aussi longtemps que possible.

**Ne pas construire la complétude à la main.** La dériver du corpus, puis la valider contre les
référentiels publiés. L'inverse coûte dix fois plus cher et produit un résultat moins juste.

---

## 7. La comparaison à ChatGPT, honnêtement

| | ChatGPT | Outil cible |
|---|---|---|
| N'invente pas | non | par construction — pas d'empan, pas de proposition |
| Compte et vérifie | non | **couche 2, déterministe** |
| Sait ce qui doit figurer | non | couche 3, avec source citée |
| Écrit dans le style de la maison | non | **couche 4, appris du corpus** |
| Traçable | non | chaque assertion ancrée |
| Hébergement maîtrisé | non | HDS |
| Rapide parce que restreint | non | un écran, pas une conversation |

Les deux lignes en gras sont celles qu'un assistant généraliste ne peut pas atteindre, quelle que
soit la qualité du prompt. Les autres, il les fait mal. La dernière est de l'ergonomie.

C'est aussi l'ordre dans lequel je construirais, si la couche 1 est acquise : **couche 2 d'abord**,
parce qu'elle est déterministe, sans risque, démontrable en congrès, et qu'elle ne dépend d'aucune
donnée qu'on n'a pas déjà.
