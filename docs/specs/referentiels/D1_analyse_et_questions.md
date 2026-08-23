# D1 — analyse du lexique et questions à trancher

Vérification mécanique du document fourni. 88 termes, 16 codes actifs.

---

## 1. Les trois problèmes

### 1.1 I et O sont strictement indiscernables — collision exacte

Les deux codes portent **exactement les mêmes déclencheurs** : « pièce », « exérèse »,
« …ectomie ». Vérifié : trois collisions exactes, aucune n'est résoluble par le lexique.

C'est logique, parce que le discriminant n'est pas lexical : c'est **l'organe est-il retiré en
entier ?**

| | |
|---|---|
| **I** | intervention avec exérèse **partielle** de l'organe |
| **O** | pièce opératoire avec exérèse **complète** de l'organe |

La note du document dit « en pratique c'est souvent I sauf pneumonectomie, laryngectomie,
thyroïdectomie totale ». **Je ne recommande pas d'implémenter ce défaut**, pour une raison
précise : une bonne part des gestes courants retire l'organe entier. Appendicectomie,
cholécystectomie, splénectomie, amygdalectomie, orchidectomie, surrénalectomie — tous des O, tous
fréquents. Un défaut à I produirait une erreur **systématique** sur toute cette classe, invisible
parce que régulière.

La solution est une table geste × organe, pas un défaut. J'en ai posé une de départ dans le JSON,
à valider intégralement.

### 1.2 Le code S n'a aucun indice — bug de fusion dans le document

Dans le fichier, les en-têtes R et S se sont retrouvés sur la même ligne :

> `R LIQUIDE DE RINCAGE OU DE LAVAGE D'UN ORGANE CREUX S SECRETION (CRACHAT, ECOULEMENT
> SPONTANE OU PAR MASSAGE) « lavage » ; « liquide de lavage » ; …`

Toute la liste qui suit appartient à R. **S — sécrétion, crachat, écoulement spontané ou par
massage — est donc vide.** J'ai proposé une liste de départ, entièrement à valider.

### 1.3 Dix-huit inclusions — le lexique est ordre-dépendant

Un terme court contenu dans un terme long capture à tort si l'ordre de test est mauvais.

| Le générique | est contenu dans | occurrences |
|---|---|---|
| `P` — « biopsie » | `B` chirurgicale, `H` guidée ×6, `T` transvasculaire ×4 | 13 |
| `C` — « cytoponction » | `G` cytoponction guidée par imagerie | 1 |
| `I` / `O` — « …ectomie » | `K` mucosectomie, polypectomie endoscopique | 4 |

Les quatre codes à tester **en dernier** : C, I, O, P.

---

## 2. La restructuration proposée

Plutôt qu'une liste plate ordre-dépendante, une structure **base × modificateur**, non
chevauchante par construction.

### Famille biopsie

| Base | Modificateur | Code |
|---|---|---|
| biopsie | chirurgicale | **B** |
| biopsie | transvasculaire · transveineuse · transartérielle · endomyocardique | **T** |
| biopsie | guidée · échoguidée · sous scanner · sous écho · sous contrôle… | **H** |
| biopsie | *(aucun)* | **P** |

### Famille cytoponction

| Base | Modificateur | Code |
|---|---|---|
| cytoponction | guidée par imagerie | **G** |
| cytoponction | *(aucun)* | **C** |

Le modificateur « guidage » est le même objet dans les deux familles. Le modéliser comme un trait
partagé, et non comme un item de vocabulaire par code, évite de le maintenir à deux endroits.

### Règle générale d'ordre

> **Correspondance exacte multi-mots > jeton exact > morphologie de suffixe.**

Ce seul classement résout les 18 inclusions. « mucosectomie » est un jeton exact de K, « -ectomie »
est une morphologie de suffixe de I/O : K gagne, automatiquement.

### Vérification

Table régénérée : 14 codes, 133 expressions, **0 collision exacte**. I et O restent
volontairement hors table lexicale.

---

## 3. Trois pièges que le document ne couvre pas

**« aspiration » n'est pas toujours A.** Le lexique de A contient « aspiration bronchique »,
« aspiration gastrique ». Mais « aspiration à l'aiguille fine » est une cytoponction — donc C ou
G, pas A. À traiter comme une garde explicite sur A.

**« ponction » est partagé entre trois codes.** « liquide de ponction » → L, « cytoponction » → C
ou G, « ponction-biopsie » → P. Le mot seul ne décide rien. Test sur le syntagme complet
uniquement, jamais sur le token « ponction ».

**Trois codes désactivés = trois classes en moins.** N, V et X sont déclarés jamais utilisés.
À désactiver dans le modèle, pas seulement à dépondérer : 19 classes deviennent 16, et toute
prédiction de N, V ou X devient un défaut détectable plutôt qu'une erreur silencieuse.

---

## 4. Ce qu'il faut demander à Jéromine

Par ordre décroissant de valeur. La première question vaut à elle seule plus que tout le reste.

### A. La table exérèse — trente minutes, le meilleur investissement du projet

Pour chaque geste, I ou O ? Ma liste de départ, à corriger :

**Proposés O — organe entier**
appendicectomie · cholécystectomie · splénectomie · amygdalectomie · pneumonectomie ·
laryngectomie totale · thyroïdectomie totale · néphrectomie totale · néphrectomie élargie ·
orchidectomie · hystérectomie totale · cystectomie totale · gastrectomie totale ·
prostatectomie totale · prostatectomie radicale · surrénalectomie · mastectomie totale ·
colectomie totale

**Proposés I — partie d'organe**
lobectomie · segmentectomie · hémicolectomie · hémithyroïdectomie · hémihépatectomie ·
tumorectomie · zonectomie · quadrantectomie · résection atypique · wedge ·
gastrectomie partielle · gastrectomie subtotale · sigmoïdectomie · néphrectomie partielle ·
conisation · exérèse cutanée · exérèse de lésion · colectomie segmentaire ·
thyroïdectomie partielle · laryngectomie partielle

**Cas que je ne sais pas trancher**
- parathyroïdectomie — une glande sur quatre, donc partiel de l'appareil ou complet de l'organe ?
- mastectomie — le sein entier, mais l'organe au sens ADICAP est GS ; O confirmé ?
- amputation abdomino-périnéale — rectum et anus, deux codes D3 possibles
- « pièce opératoire » dicté seul, sans nom de geste
- polypectomie **non** endoscopique — I ou K ?

**Question de méthode :** quand le geste n'est dans aucune liste, préférez-vous que le système
s'abstienne et propose les deux, ou qu'il applique un défaut ? Mon avis : abstention. Mais c'est
votre pratique qui tranche.

### B. Le code S, entièrement à écrire

Ma proposition : crachat · expectoration · expectoration induite · sécrétion ·
écoulement mamelonnaire · écoulement du mamelon · écoulement spontané ·
produit de massage prostatique.

Qu'est-ce qui manque, qu'est-ce qui est faux ?

### C. Le guidage par imagerie — compléter H et G

Absents du document : sous IRM · sous TDM · sous tomodensitométrie · stéréotaxique ·
sous stéréotaxie · sous repérage.

Et trois questions qui pèsent lourd en volume mammaire :
- **macrobiopsie** — le guidage est-il implicite dans le geste, donc toujours H ?
- **microbiopsie** — même question
- **tru-cut** — P par défaut, ou H si le guidage est sous-entendu ?

### D. Les frottis — F semble sous-couvert

« frottis cervico-utérin », « frottis cervico-vaginal », « FCU » : je les ai ajoutés à F. Correct ?
C'est probablement un des volumes les plus élevés du dictionnaire.

### E. Les liquides — L semble sous-couvert

« ponction pleurale », « ponction d'ascite » : ajoutés à L. Ou bien la formulation dictée est-elle
toujours « liquide pleural » ?

---

## 5. Ce que ça change pour l'étude

La collision I / O est **la** métrique à isoler dans le recueil. Elle représente sans doute une
part importante des pièces opératoires, elle n'est pas résoluble par le modèle de langage, et elle
est mesurable proprement : proposition I ou O, corrigée ou non par le praticien.

C'est aussi le meilleur exemple à mettre dans le poster : un cas où le système **s'abstient
volontairement** plutôt que de deviner, avec une justification lisible. Face à un assistant
généraliste qui trancherait avec aplomb, c'est exactement la démonstration recherchée.

Deuxième métrique à isoler : les erreurs par capture générique — un « biopsie échoguidée » codé P
parce que « biopsie » a matché en premier. C'est une erreur d'implémentation, pas de modèle, et
elle doit tomber à zéro avant le gel de version.
