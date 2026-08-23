# Audit des faux signaux de la télémétrie MARC

**Audit en lecture seule.** Aucun fichier de production n'a été modifié. Toutes les
observations ci-dessous ont été obtenues en lisant le code **et en le faisant tourner** :
un script de reproduction rejoue la séquence d'appels que le frontend émet réellement,
puis lit la synthèse servie à l'administration et interroge la base directement.

**État du dépôt au moment de l'audit** : `python -m pytest -q` → **622 passed in 5.02s**.
Trois autres agents écrivent en parallèle ; `backend/etude/analyse.py`,
`backend/etude/models.py` et `backend/main.py` ont bougé pendant l'audit. Les numéros de
ligne cités ont été revérifiés en fin de course, mais un chantier concurrent peut les
avoir déplacés depuis.

**Ce que je n'ai pas pu faire** : la base de ce poste (`lexia.db`) ne contient **aucune
table `etude_*`** (vérifié : `sqlite3 lexia.db ".tables"` ne rend que `users`,
`reports`, `audit_log`, `organizations`, `business_rules`, `report_exports`). Il n'y a
donc pas de données réelles à dépouiller. Toutes les mesures chiffrées ci-dessous
proviennent d'une base neuve alimentée par le parcours réel du frontend.

---

## Résumé pour décision

Le propriétaire craignait que « sauvegarder », « terminer » et la sauvegarde automatique
se recouvrent. **La crainte est fondée, et le problème est plus large que les trois mots.**

Le parcours réellement câblé dans `App.tsx` n'émet que **trois** des dix gestes que
l'instrumentation sait enregistrer : ouvrir un dossier, décider une proposition, clore.
« Terminer » (`terminerSession`), l'export (`marquerExport`), l'abandon (`abandonner`),
les pauses (`journaliserPause`), les questionnaires, l'exclusion et l'ergonomie
**existent côté serveur et ne sont appelés par aucun composant monté**.

Conséquence directe : **onze colonnes sortiront systématiquement vides** et seront lues
comme « le phénomène n'existe pas » — `t6_export`, `omission_signalee`, `omission_texte`,
`nb_prelevements_detecte`, `nb_prelevements_corrige`, `nature_correction`, `cause_erreur`,
`justif_ouverte`, `justif_duree_ms`, `positions`, `prelevement_id` — pendant que **deux
taux sortiront à 0 %** là où rien n'a jamais été observé (`decisions_hatives`,
`changement_apres_justification`) et que **deux compteurs non nullables** afficheront un
zéro fabriqué (`EtudeSession.nb_cas`, `TempsDossier.pauses_ms`). C'est exactement la
manière de mentir avec un tableau que le projet s'est interdite.

Le plus grave est ailleurs, et il est indépendant du frontend : **le critère de jugement
principal bloquant du protocole est calculé, la donnée est en base, et l'adaptateur qui
relie les deux perd le champ en route.** Mesuré : 12 propositions non ancrées en base,
3 acceptées telles quelles, et la synthèse publie `0 / 0 → null`.

---

## GRAVITÉ 1 — fausse un critère de jugement principal

### 1.1 Le critère BLOQUANT « propositions non soutenues acceptées » publie « pas de mesure » alors que la mesure existe

**Champ concerné** : `EtudeProposition.empan_debut` (`backend/etude/models.py:211`), lu
comme `DecisionObservee.ancree` (`backend/etude/analyse.py:97-99`).

**Chemin de code exact** :

`backend/routes_etude_admin.py:138-145`

```python
def _observee(proposition: EtudeProposition) -> DecisionObservee:
    return DecisionObservee(
        type_proposition=proposition.type,
        decision=proposition.decision,
        hative=proposition.hative,
        latence_ms=proposition.latence_ms,
        decision_changee_apres_justif=proposition.decision_changee_apres_justif,
    )
```

`ancree` n'est pas transmis. Le champ vaut donc **toujours sa valeur par défaut, `True`**
(`analyse.py:99`), pour chaque proposition relue en base.

En aval, `calculer_indicateurs` (`analyse.py:219-225`) construit la population du critère
ainsi :

```python
non_ancrees = [
    d for d in prises if d.type_proposition == TYPE_RESTITUTION and not d.ancree
]
```

Cette liste est **toujours vide**, donc `acceptation_non_ancree` sort en `Taux(0, 0)`,
donc `valeur = None`.

**Scénario qui le produit** : n'importe quel dépouillement. Il suffit d'appeler
`GET /admin/etude/synthese`.

**Ce que le chiffre publié vaudrait à tort** : la synthèse annonce
`acceptation_non_ancree : 0 / 0 → null`, ce que le tableau lit « critère non mesuré ».
Or, dans la base que je viens de remplir avec le parcours réel :

```
SELECT COUNT(*) FROM etude_propositions;                       -> 18
SELECT COUNT(*) FROM etude_propositions WHERE empan_debut IS NULL;  -> 12
-- non ancrées, acceptées « conforme », sur dossiers non exclus :
SELECT COUNT(*) ... WHERE p.empan_debut IS NULL
                      AND p.decision='conforme' AND d.exclu=0;      -> 3
```

**Trois acceptations d'assertions que rien dans la dictée ne soutient**, sur 12
candidates. Le protocole (§6, *Principaux — sécurité*) dit de cette ligne : « La dernière
ligne est bloquante et ne se compense pas. » Elle est actuellement invisible.

Le taux `hallucination` affiché à côté (`analyse.py:233-235`) **ne le remplace pas** : il
compte la déclaration `non_dicte` du praticien, sur le dénominateur des restitutions
décidées. Ce n'est ni la même population ni le même dénominateur que « propositions non
soutenues par la dictée < 2 % ».

**Correction proposée** : ajouter une ligne à `_observee` :
`ancree=proposition.empan_debut is not None`. Le reste de la chaîne est déjà en place. Un
test qui décide « conforme » sur une proposition sans empan et vérifie que
`acceptation_non_ancree` n'est pas `0/0` empêcherait la régression.

---

### 1.2 Même rupture sur `nature_correction` : l'agrégat existe, l'adaptateur ne le passe pas, et personne ne l'écrit

**Champ concerné** : `EtudeProposition.nature_correction` (`models.py:238`).

**Trois ruptures superposées, du plus profond au plus visible :**

**a) L'agrégat ne reçoit pas le champ.** `_observee` (`routes_etude_admin.py:138-145`) ne
transmet pas `nature_correction`, qui reste à `None` (`analyse.py:95`). Résultat mesuré
dans la synthèse :

```
corrections.style          0/0 -> null
corrections.precision      0/0 -> null
corrections.erreur_fond    0/0 -> null
corrections.non_declaree   0/0 -> null
```

**b) Le parcours réel ne l'envoie jamais.** `App.tsx:544-549` :

```tsx
const resultat = await etude.decider(
  proposition,
  action.decision as never,
  valeur ? { valeur_retenue: valeur } : undefined,
);
```

Ni `nature_correction`, ni `cause_erreur`, ni `justif_ouverte`, ni `justif_duree_ms`.

**c) L'écran qui saurait la poser n'est monté nulle part.** `PropositionCarte.tsx:335-341`
construit bien `natureCorrection`, mais il appartient à `RevuePanel`, dont j'ai vérifié
qu'il n'est importé par **aucun** fichier hors de `frontend/src/components/revue/`. La
seule file de décisions affichée est `PanneauAnalyse`.

**Ce que le chiffre publié vaudrait à tort** : `justesse_sur_le_fond` sort à `5/6 = 83 %`
dans ma reproduction — mais uniquement parce qu'aucune correction n'a été déclarée. Dès
qu'un praticien corrigera, chaque correction comptera comme un échec du système, y
compris une reformulation de style. C'est exactement l'écueil que `vocabulaire.py:64-76`
décrit en toutes lettres et que le code ne peut pas éviter faute de donnée.

À noter : `impute_une_erreur` et `NATURES_SANS_ERREUR` (`vocabulaire.py:93-102`) ne sont
référencés **nulle part** hors de leur propre fichier. Et tout le module
`backend/etude/nature_correction.py` (`classer`, `declaration_coherente`,
`retouches_silencieuses`, 243 lignes) n'est appelé que par ses tests : la nature
**calculée**, présentée comme « la seule source disponible sur les modifications que
personne n'a déclarées », n'est branchée sur aucune route.

**Correction proposée** : (1) passer `nature_correction=proposition.nature_correction`
dans `_observee` ; (2) câbler la question de la nature dans `PanneauAnalyse` /
`PointCarte`, ou monter `RevuePanel` ; (3) appeler `classer(cr_propose, cr_valide)` à la
clôture pour disposer de la nature calculée même sans déclaration.

---

### 1.3 `changement_apres_justification` publie 0 % là où rien n'a été présenté

**Champ concerné** : `EtudeProposition.decision_changee_apres_justif` (`models.py:227`).

**Chemin de code** : `analyse.py:249-253`

```python
changement_apres_justification=Taux(
    sum(1 for d in prises if d.decision_changee_apres_justif),
    len(prises),
    "Avis change apres justification",
),
```

Le dénominateur est **toutes les décisions prises**, pas les décisions pour lesquelles une
justification a été présentée. Il est donc non nul, et la règle « dénominateur nul → None »
ne s'applique jamais.

Le numérateur, lui, ne peut jamais bouger : `service.py:259-264` exige
`justif_ouverte or proposition.justif_ouverte`, et `justif_ouverte` n'est jamais envoyé
(voir 1.2 b/c).

**Résultat mesuré** : `changement_apres_justification : 0/6 → 0.0`.

**Ce que le chiffre publié vaudrait à tort** : « 0 % des décisions ont changé après
consultation de la justification ». Le protocole (§4) appelle cela « la mesure
d'explicabilité la plus convaincante qu'on puisse produire ». Publier 0 % reviendrait à
affirmer que les justifications ne servent à rien, alors qu'elles n'ont jamais été
ouvertes. Le critère secondaire « justifications consultées au moins une fois par cas
≥ 50 % des cas » n'a par ailleurs **aucun indicateur** dans la synthèse.

**Correction proposée** : borner le dénominateur aux décisions où la justification a été
présentée (`justif_ouverte is True`) — le taux redeviendra `None` tant que rien n'est
recueilli, ce qui est la vérité. Ajouter en regard un `Taux` de consultation
(justif_ouverte / décisions prises), qui est le critère secondaire attendu.

---

### 1.4 `decisions_hatives` publie 0 % parce que le seuil rend le marquage impossible

**Champ concerné** : `EtudeProposition.hative` (`models.py:222`), calculé par
`est_hative` (`vocabulaire.py:152-160`) :

```python
return latence_ms < SEUIL_HATIVE_MS and longueur_mots > SEUIL_HATIVE_MOTS
```

avec `SEUIL_HATIVE_MOTS = 15` (`vocabulaire.py:149`).

**Mesure faite** : j'ai passé les comptes rendus présents dans le dépôt à
`extraire_restitutions` et relevé `longueur_mots` :

| Proposition | mots | marquable hâtive ? |
|---|---|---|
| « La lésion est complètement réséquée en marges saines » | 8 | non |
| « Absence de cellules malignes sur l'ensemble des niveaux examinés » | 9 | non |
| « Adénome tubuleux en dysplasie de bas grade, respectant la musculaire… » | 15 | non |
| (test_etude_arbitrage) | 10 | non |
| (test_etude_arbitrage) | 15 | non |

**0 proposition sur 5 peut être marquée hâtive**, quelle que soit la vitesse du clic.
Vérifié en bout de chaîne : une décision enregistrée **11 ms** après l'ouverture rend
`{'latence_ms': 11, 'hative': False}`.

**Ce que le chiffre publié vaudrait à tort** : `decisions_hatives : 0/6 → 0.0`, soit
« aucune décision hâtive ». Pire, le garde-fou n°3 du module (`analyse.py:16-19`, les taux
calculés deux fois) devient inerte : dans ma reproduction, `hors_decisions_hatives` est
le **clone exact** de `toutes_decisions`, à la virgule près. L'écart entre les deux, qui
devait être « un résultat sur la validité du protocole », vaut structurellement zéro.

Le protocole (§4) écrit pourtant : « une acceptation en moins de deux secondes sur une
proposition complexe est une acceptation non inspectée ». Le seuil de 1200 ms est plus
sévère que les 2 s annoncées, et la condition sur les mots annule le tout.

**Correction proposée** : soit supprimer la condition `longueur_mots`, soit l'abaisser à
un seuil compatible avec la longueur réelle des assertions (médiane observée : 10 mots),
soit renoncer au booléen et publier la distribution des latences avec son effectif — ce
qui est de toute façon plus honnête qu'un seuil arbitraire.

---

### 1.5 `latence_ms` ne mesure pas le délai entre affichage et décision

**Champ concerné** : `EtudeProposition.latence_ms` (`models.py:221`) et
`affiche_a` (`models.py:219`).

**Chemin de code** : `service.py:143-145`

```python
affiche_a = dossier.t2_affichage
for extraite in propositions:
    db.add(_vers_ligne(dossier.id, extraite, affiche_a))
```

**Toutes** les propositions d'un dossier reçoivent le **même** `affiche_a` : l'instant
d'ouverture du dossier. Puis `service.py:276-280` calcule
`latence = decide_a − affiche_a`.

`latence_ms` mesure donc **le temps écoulé depuis l'ouverture du cas**, pas depuis
l'affichage de la proposition. Vérifié dans ma reproduction : trois décisions successives
sur le même dossier donnent 11 ms, 17 ms, 23 ms — les latences **s'additionnent
mécaniquement avec le rang**.

**Aggravant** : `routes_etude.py:250-254` renvoie les propositions
`order_by(EtudeProposition.type, EtudeProposition.id)`. `id` est un UUID aléatoire
(`models.py:35-36`). L'ordre d'affichage est donc **aléatoire**, et il détruit la priorité
soigneusement calculée par `extraction.py:310-317`, qui plaçait les candidates
hallucinations en tête (`_PRIORITE_HALLUCINATION = -1`).

**Ce que le chiffre publié vaudrait à tort** : le protocole (§4) demande « délai entre
affichage et décision, en millisecondes » et en fait le proxy du biais d'automatisation.
Publier cette colonne telle quelle donnerait un délai croissant avec le rang de la
proposition, interprétable à tort comme « le praticien ralentit », alors qu'il s'agit d'un
artefact de mesure. Combiné à 1.4, cela biaise le marquage `hative` vers les seules
premières propositions.

**Correction proposée** : horodater l'affichage réel côté client par proposition (un POST
léger, ou un champ `affiche_a` renseigné à la première apparition dans le viewport), ou à
défaut stocker le **rang d'affichage** et publier la latence conditionnellement au rang.
Et trier par ordre d'extraction, pas par UUID.

---

### 1.6 Un même cas clinique produit plusieurs dossiers d'étude

**Champ concerné** : toute la table `etude_dossiers`, et par ricochet tous les
dénominateurs.

**Chemin de code** : `App.tsx:578-593`, dans `handleFormatted` :

```tsx
const transcription = transcriptionRef.current;
if (transcription) {
  void etude.ouvrir({ transcription, cr_propose: result.formatted_report, ... });
}
```

`handleFormatted` est appelé par **trois** chemins :
- la génération initiale (`RecorderPanel` → `onFormatted`) ;
- `handleReformat` (`App.tsx:645-658`), déclenché par « nouvelle dictée » ;
- `ajouterAuCompteRendu` (`App.tsx:601-611`), déclenché par la barre d'ajout.

Or `service.ouvrir_dossier` (`service.py:111-149`) **crée toujours** un nouvel
`EtudeDossier`, avec un nouveau jeu de propositions et
`index_session = await _compter_dossiers(...)` (`service.py:132`).

**Scénario qui le produit** : le praticien dicte, lit le compte rendu, ajoute une phrase
via la barre d'ajout (ce qui est exactement l'usage prévu), sauvegarde. Un seul cas
clinique, **deux** dossiers d'étude.

**Ce que le chiffre publié vaudrait à tort** — voici la reproduction, 4 cas cliniques
réellement traités :

```
nb_dossiers : 5              (le 5e est le doublon d'un reformatage)
decidees : 6 | non_decidees : 9
caracteres_modifies_moyen : 0.0
apprentissage : nb_dossiers_retenus 3, terciles [0.0, 0.0, 0.0]
```

- Le dossier abandonné reste ouvert avec `cr_valide` NULL et **ses trois propositions non
  décidées gonflent `non_decidees`** : 9 non décidées pour 6 décidées, alors que le
  praticien a tout tranché sur les cas qu'il a vus.
- `caracteres_modifies` du doublon vaut 0 et tire la moyenne de charge d'édition vers le
  bas, pour un cas déjà compté.
- `index_session` est incrémenté pour un cas qui n'en est pas un, ce qui décale l'analyse
  d'apprentissage.

**Correction proposée** : distinguer « ouvrir un dossier » de « régénérer le compte rendu
d'un dossier ouvert ». Une route `PUT /etude/dossiers/{id}/regeneration` qui remplace les
propositions non décidées sans créer de ligne, ou à défaut un champ
`remplace_dossier_id` pour que le dépouillement puisse dédupliquer.

---

## GRAVITÉ 2 — dénominateurs contaminés et critères sans donnée

### 2.1 `nb_praticiens` compte les praticiens dont tous les dossiers sont exclus

**Chemin de code** : `routes_etude_admin.py:191`

```python
praticiens = await base.execute(select(func.count(func.distinct(EtudeSession.praticien_id))))
```

Le comptage porte sur `etude_sessions`, **sans aucun lien** avec les dossiers retenus. Un
praticien qui a ouvert une session sans jamais produire de dossier, ou dont tous les
dossiers ont été exclus, compte quand même.

**Mesuré** : `nb_praticiens: 2` alors qu'un seul praticien a un dossier non exclu. Le
second n'a qu'un dossier d'essai, explicitement exclu avec son motif.

**Ce que le chiffre publié vaudrait à tort** : c'est le dénominateur du critère principal
« praticiens souhaitant continuer ≥ 8/10 » et de tout effectif annoncé dans un diagramme
de flux.

**Correction proposée** : compter les praticiens distincts **des dossiers retenus**, et
publier à côté le nombre de praticiens inclus mais sans dossier exploitable — c'est une
information de recrutement, pas un effectif d'analyse.

---

### 2.2 Un dossier abandonné est compté comme clos

**Chemin de code** : `service.py:405` (`abandonner_dossier`) pose `t5_cloture`, et
`routes_etude_admin.py:200` compte :

```python
"nb_dossiers_clos": sum(1 for d in dossiers if d.t5_cloture is not None),
```

**Mesuré** : `nb_dossiers_clos: 4`, `nb_abandons: 1` — l'abandon est dans les deux. Sur 5
dossiers non exclus, un seul est réellement inachevé, mais l'affichage
(`SyntheseEtude.tsx:328`, `hint={nb_dossiers - nb_dossiers_clos} en cours`) annoncera
« 1 en cours » au lieu de 2.

**Effet secondaire** : `calculer_temps` (`analyse.py:375-382`) donne un `revision_ms` à un
dossier abandonné, puisque t2 et t5 existent tous les deux. Une révision interrompue est
comptée comme une révision menée à terme. Vérifié : le dossier abandonné ressort avec
`revision_nette_ms = 4`.

**Correction proposée** : soit ne pas poser `t5_cloture` sur un abandon et horodater
`abandonne_a` séparément, soit exclure `abandonne` du comptage des clos et du calcul des
temps. La première option est plus propre : t5 s'appelle « clôture ».

---

### 2.3 L'exclusion n'a aucune interface : elle ne s'exercera pas

**Chemins de code** : les deux routes existent —
`routes_etude.py:404-425` (le praticien exclut son propre dossier) et
`routes_etude_admin.py:380-403` (l'administrateur exclut n'importe lequel).

**Vérifié côté frontend** : `grep -rn "exclusion" frontend/src/` → **0 occurrence**.
`frontend/src/services/etude.ts` n'expose aucune fonction d'exclusion. Aucun bouton, aucun
appel.

**Ce que cela produit** : la règle « les dossiers exclus n'entrent dans aucun calcul » est
correctement appliquée par le backend (`routes_etude_admin.py:172`) mais **ne sera jamais
déclenchée**. Le cas d'essai de l'administrateur, la dictée de démonstration, le dossier
ouvert par erreur entreront dans tous les taux.

**Deux défauts d'affichage aggravants** :
- `SyntheseEtude.tsx` : l'interface `DonneesSynthese` (lignes 34-42) **ne déclare pas
  `nb_exclus`**, et la section Corpus n'affiche que Praticiens / Dossiers / Dossiers clos /
  Abandons. Le backend le fournit pourtant (`routes_etude_admin.py:199`), avec le
  commentaire « Compte à part et TOUJOURS affiché ». Il ne l'est pas.
- `ListeDossiersEtude.tsx` : aucune mention de `exclu`. Le type `LigneDossier` du client
  (`services/etude.ts:331-343`) n'a ni `exclu` ni `motif_exclusion`, alors que le backend
  les renvoie. Un dossier écarté est visuellement identique à un dossier retenu.

**Défaut de traçabilité** : `EtudeDossier` porte `exclu`, `motif_exclusion` et `exclu_par`
(`models.py:119-121`) mais **aucun horodatage d'exclusion**. Impossible de démontrer
qu'une exclusion a précédé la lecture des résultats — c'est le premier point qu'un
relecteur attaquera sur une étude sans bras témoin.

**Correction proposée** : bouton d'exclusion dans la vue dossier de l'administration,
carte `nb_exclus` dans la synthèse, badge « exclu » dans la liste, et colonne `exclu_a`.

---

### 2.4 Aucun questionnaire n'est jamais posé

**Vérifié** : les composants `frontend/src/components/questionnaire/Questionnaire.tsx` et
`QuestionnaireParCas.tsx` existent, sont complets, et **ne sont importés par aucun autre
fichier**. `App.tsx` ne les mentionne pas.

**Ce que cela produit** : la table `etude_reponses_questionnaire` restera vide. Sont donc
sans donnée :
- le critère **principal** « score F-SUS moyen ≥ 70 » (protocole §6) ;
- le critère **principal** « praticiens souhaitant continuer ≥ 8/10 » ;
- le critère **secondaire** « item 4 du questionnaire par cas (compréhension) ≥ 4/5 » ;
- tout le PDQI-9 et la charge de travail.

**Détail révélateur** : `routes_etude.py:334` calcule et renvoie
`questionnaire_periodique_du` à chaque clôture — précisément pour que le serveur, et non
le client, tienne la cadence du F-SUS répété. Le frontend **jette la valeur** :
`ResultatCloture` (`services/etude.ts:241-243`) ne déclare que `caracteres_modifies`, et
`useEtudeDossier.clore` (`hooks/useEtudeDossier.ts:179`) ne destructure que ce champ. La
courbe de F-SUS, qui est l'argument de publication décrit dans `vocabulaire.py:177-185`,
ne sera jamais recueillie.

**Correction proposée** : monter `QuestionnaireParCas` après la clôture, déclarer
`questionnaire_periodique_du` dans `ResultatCloture`, et déclencher le F-SUS quand il est
dû. C'est cinq lignes de câblage pour deux critères principaux.

---

### 2.5 `omission_signalee` n'est jamais renseigné, et une seconde clôture l'écraserait

**Chemin de code** : `App.tsx:682`

```tsx
void etude.clore({ cr_valide: report });
```

Ni `omission_signalee`, ni `omission_texte`, ni `nb_prelevements_corrige`. Or
`service.py:348-350` assigne **sans condition** :

```python
dossier.omission_signalee = omission_signalee   # None
dossier.omission_texte = omission_texte         # None
dossier.nb_prelevements_corrige = nb_prelevements_corrige  # None
```

**Deux conséquences** :
1. Le critère **principal** « omissions signalées < 5 % des comptes rendus » (protocole
   §6) n'a aucune donnée — et aucun indicateur agrégé non plus : `_corpus`
   (`routes_etude_admin.py:189-205`) ne compte pas les omissions.
2. Si la question était posée un jour, une seconde clôture du même dossier (possible :
   rien ne l'interdit, voir 3.3) **effacerait** la réponse par un `None`.

**Point sain à signaler ici** : l'export CSV ne tombe pas dans le piège.
`etude/export.py:309-318` rend une cellule **vide** et non `'false'`, avec le commentaire
exact : « Le sortir en 'false' compterait chaque dossier en cours comme un dossier sans
omission, et le taux d'omission publié serait faux vers le bas. » C'est la bonne
défense — elle protège la sortie, pas l'absence de saisie.

**Correction proposée** : poser la question d'omission dans le dialogue de validation, et
faire de `clore_dossier` une écriture qui ne remplace un champ que si une valeur est
fournie.

---

### 2.6 Les codes ADICAP et les prélèvements ne sont jamais transmis

**Chemin de code** : `App.tsx:583-593` n'envoie que `transcription`, `cr_propose`,
`organe` et `alertes`. Les champs `codes` et `prelevements` de `OuvertureDossier`
(`routes_etude.py:50-52`) restent vides.

**Conséquence bien gérée** : aucune proposition de type `code` n'est créée, donc
`exactitude_codes` et `abstention_codes` sortent en `Taux(0, 0) → null`. **La règle 2 est
respectée** : pas de faux zéro. Vérifié dans la synthèse.

**Conséquence problématique** : `service.enregistrer_prelevements` n'est jamais appelée
(`routes_etude.py:236-237`, conditionné à `if corps.prelevements`). Donc :
- `etude_prelevements` reste vide ;
- `nb_prelevements_detecte` (`models.py:99`) reste NULL ;
- `EtudeProposition.prelevement_id` (`models.py:196-198`) **n'est assigné par aucun chemin
  de code** — `_vers_ligne` (`service.py:152-167`) ne le renseigne pas.

La correction de cardinalité que la table `EtudePrelevement` incarne
(`models.py:148-155` : « L'existence de cette table EST la correction du bug de
cardinalité ») n'est donc mesurée nulle part, et `ligne_proposition`
(`export.py:427-441`) exportera systématiquement des colonnes
`prelevement_rang` / `prelevement_libelle` vides.

**Correction proposée** : transmettre `codes` et `prelevements` depuis `handleFormatted`
(les données existent dans `result`), et rattacher chaque proposition de code à son
prélèvement dans `ouvrir_dossier`.

---

## GRAVITÉ 3 — horodatages, compteurs, champs morts

### 3.1 t0 et t1 sont posés par le client, sans aucune vérification

**Chemin de code** : `routes_etude.py:48-49` accepte deux `datetime` du client ;
`service.py:130-139` les écrit tels quels à côté de `t2_affichage = _maintenant()`, qui
est serveur.

Aucune comparaison n'est faite entre t0, t1 et t2.

**Scénario testé** : j'ai envoyé un `t1_fin_dictee` situé **deux heures dans le futur**.
Résultat :

```json
{"dictee_ms": 1000, "generation_ms": 0, "revision_ms": 4, "revision_nette_ms": 4}
```

`generation_ms = 0`. La cause est `analyse.py:368-372` :

```python
return max(0, int((arrivee - depart).total_seconds() * 1000))
```

Le `max(0, ...)` **transforme un écart aberrant en une valeur plausible**. Un poste dont
l'horloge avance publierait « génération instantanée » sans que rien ne le signale.

**Circonstance atténuante** : dans le parcours actuel, t0 et t1 ne sont **jamais** envoyés
(`App.tsx:583-593`). Les colonnes restent NULL, `dictee_ms` et `generation_ms` sortent
vides, et l'export met une cellule vide (`export.py:304-306`). Le piège est **dormant, pas
refermé** : il se déclenchera au premier câblage de la mesure de dictée.

**Correction proposée** : refuser (ou marquer d'un drapeau `horodatage_suspect`) un t1
postérieur à t2 ou un t0 postérieur à t1, au lieu de saturer à 0. Un `None` explicite est
préférable à un zéro fabriqué — c'est la règle 2 du projet.

---

### 3.2 Un changement d'avis efface le premier avis et rallonge la latence

**Chemin de code** : `service.py:266-280` réécrit `decision`, `valeur_retenue`,
`decide_a`, `latence_ms` et `hative` **sur la même ligne**.

**Scénario testé** : premier clic « conforme », puis changement en « non_dicte » :

```
1er clic  : {'latence_ms': 4, 'hative': False}
2e clic   : {'latence_ms': 8, 'hative': False}
en base   : decision = non_dicte | latence = 8 | hative = False
```

**Ce que le chiffre publié vaudrait à tort** :
- une décision hâtive corrigée ensuite après réflexion **perd son marquage `hative`** :
  la latence recalculée depuis `affiche_a` est nécessairement plus longue. Le garde-fou
  n°2 sous-compte donc systématiquement ;
- le fait qu'un praticien ait changé d'avis — information précieuse, et proche du critère
  d'explicabilité — n'est **conservé nulle part**, sauf si la justification avait été
  ouverte (`service.py:259-264`), ce qui n'arrive jamais (1.3) ;
- **incohérence de traitement sur la même ligne** : `justif_duree_ms` s'**accumule**
  (`service.py:274`, `(proposition.justif_duree_ms or 0) + justif_duree_ms`) tandis que
  `latence_ms` se **remplace**. Deux champs voisins, deux règles opposées, sans que rien
  ne le documente au dépouillement.

**Correction proposée** : ajouter un compteur `nb_revisions` sur la proposition, conserver
la première latence (`latence_ms` = premier tranchage, `latence_finale_ms` = dernier), ou
journaliser les révisions dans une table fille. Au minimum, documenter la règle dans le
dictionnaire de données de l'export.

---

### 3.3 Des décisions peuvent arriver après la clôture, et un dossier peut être clos deux fois

**Chemin de code** : `service.enregistrer_decision` (`service.py:200-244`) ne regarde
jamais l'état du dossier. Rien n'interdit un POST après `t5_cloture`. Côté interface, le
panneau d'analyse reste actif après la sauvegarde (`App.tsx:850-866`).

**Conséquences** :
- une décision postérieure à t5 entre dans les taux mais **hors** de `revision_ms`
  (t2 → t5, `analyse.py:380`) et après le calcul de `caracteres_modifies` ;
- `t4_derniere_decision` peut être **postérieur à t5_cloture**, ce qui est incohérent dans
  l'export et invisible au lecteur ;
- `clore_dossier` peut être rappelée : elle réécrit `cr_valide`, recalcule
  `caracteres_modifies` et **repositionne** t5 (`service.py:346-351`), allongeant
  rétroactivement le temps de révision.

**Correction proposée** : refuser une décision sur un dossier clos (comme
`clore_dossier` refuse déjà un dossier abandonné, `service.py:343-344`), ou marquer la
décision `posterieure_a_cloture` plutôt que de la perdre.

---

### 3.4 `index_session` compte les dossiers exclus et abandonnés

**Chemin de code** : `service.py:132` puis `_compter_dossiers` (`service.py:99-105`), qui
ne filtre ni `exclu` ni `abandonne`.

Le rang du cas dans la session — qui sert à l'analyse par tercile — inclut donc les cas
qui n'entreront dans aucun taux. Un praticien qui abandonne son deuxième cas verra son
troisième cas étiqueté « rang 2 » dans la courbe d'apprentissage.

---

### 3.5 Les terciles d'apprentissage mélangent les praticiens

**Chemin de code** : `routes_etude_admin.py:233-238`

```python
ordonnes = sorted(
    (d for d in dossiers if d.caracteres_modifies is not None),
    key=lambda d: (d.session_id, d.index_session),
)
```

`session_id` est un **UUID aléatoire** (`models.py:48`). L'ordre entre sessions est donc
arbitraire, et `terciles` (`analyse.py:389-403`) découpe la série **concaténée de tous les
praticiens**.

**Scénario qui le produit** : un praticien à 30 cas et un praticien à 3 cas. Le premier
tercile « global » peut contenir les cas tardifs du premier et les cas précoces du second,
selon le tirage des UUID.

**Ce que le chiffre publié vaudrait à tort** : « la charge d'édition baisse du premier au
dernier tercile » se lirait comme un effet d'apprentissage alors qu'il s'agirait d'un
artefact de l'ordre des UUID et du déséquilibre des effectifs.

**Aggravant** : une nouvelle session est ouverte **à chaque rechargement de page**
(`useEtudeDossier.ts:101-107` — `sessionRef` est réinitialisé au montage). Un praticien
aura donc plusieurs sessions par jour, aux UUID sans rapport avec l'ordre chronologique.

**Correction proposée** : trier par praticien puis par `cree_a`, calculer les terciles
**par praticien**, et publier la moyenne des moyennes avec l'effectif par praticien.

---

### 3.6 `EtudeSession.fin` et `nb_cas` restent vides ; t6 aussi

- `terminerSession` (`useEtudeDossier.ts:224-236`) n'est appelé par aucun composant :
  `clore_session` (`service.py:87-96`) n'est jamais atteinte. `fin` reste NULL et `nb_cas`
  reste à **0** — valeur par défaut non nullable (`models.py:57`), donc un vrai faux zéro :
  au dépouillement, « 0 cas » et « pas encore compté » sont indiscernables.
- `etude.exporter()` (`useEtudeDossier.ts:192-203`) n'est appelé nulle part :
  `t6_export` (`models.py:96`) reste NULL sur tous les dossiers. Le bouton d'export DOCX
  passe par `services/api.ts:345` (`/export`) sans jamais toucher à l'instrumentation.

C'est ici que se loge exactement la crainte du propriétaire : « sauvegarder » fait la
clôture d'étude, « terminer » ne fait rien, et l'export ne laisse aucune trace.

---

### 3.7 Les pauses ne sont jamais journalisées — et `pauses_ms` est un faux zéro par construction

**Chemin de code** : `hooks/useHorlogeEtude.ts` implémente toute la logique
(Page Visibility, seuil d'inactivité) et appelle `journaliserPause`. **Aucun composant ne
l'importe** : `grep -rn "useHorlogeEtude" frontend/src/` ne rend que sa propre définition.

**Ce que le chiffre publié vaudrait à tort** : `TempsDossier.pauses_ms` est typé `int`,
pas `int | None` (`analyse.py:347`). Il sortira donc à **0** partout,
et `nb_pauses` à 0. Vérifié : `revision_nette_ms == revision_ms` sur tous les dossiers
(23 ms / 23 ms).

Le tableau annoncera « 0 interruption, temps de révision net = temps brut ». C'est une
absence de mesure présentée comme un zéro, sur le résultat que
`services/etude.ts:370` qualifie de « résultat principal de l'étude ». Le temps de
révision publié inclura les cafés, les téléphones et les onglets masqués.

**Correction proposée** : monter `useHorlogeEtude` dans `App.tsx` avec le `dossierId`
courant. Tant que ce n'est pas fait, typer `pauses_ms: int | None` et le laisser à `None`
quand aucune pause n'a jamais été journalisée pour la session — un zéro observé et un zéro
non mesuré ne se ressemblent pas.

---

### 3.8 Un brouillon restauré n'ouvre aucun dossier : le cas disparaît de l'étude

**Chemin de code** : `App.tsx:442-454` (restauration du brouillon)

```tsx
setReport(latest.draft.report);
setRawTranscription(latest.draft.rawTranscription);
```

`setRawTranscription` est appelé **directement**, pas `noterTranscription`
(`App.tsx:381-384`), qui est la seule fonction à renseigner `transcriptionRef.current`.

Or `handleFormatted` teste (`App.tsx:579-580`) :

```tsx
const transcription = transcriptionRef.current;
if (transcription) { void etude.ouvrir({...}); }
```

**Scénario qui le produit** : le praticien ferme l'onglet en cours de rédaction, revient,
le brouillon est restauré (« Brouillon restauré automatiquement »), il complète via la
barre d'ajout, il sauvegarde. **Aucun dossier d'étude n'est ouvert**, aucune proposition
n'est créée, et `etude.clore` sort immédiatement (`useEtudeDossier.ts:175`,
`if (dossierId === null) return null`).

**Ce que le chiffre publié vaudrait à tort** : le cas est absent du corpus. C'est une perte
**silencieuse et sélective** — elle frappe préférentiellement les cas longs et interrompus,
c'est-à-dire les plus difficiles, donc ceux où le système se trompe le plus.

**Correction proposée** : appeler `noterTranscription` dans l'effet de restauration.
Une ligne. Et faire remonter un avertissement visible quand `etude.ouvrir` est court-circuité.

---

### 3.9 Des décisions prises à l'écran ne produisent aucune télémétrie

**Chemin de code** : `App.tsx:538-555`

```tsx
const proposition = etude.propositions.find((p) => p.id === point.id);
if (proposition) {
  const resultat = await etude.decider(...);
  if (resultat === null) return;
}
setPointsTraites((actuel) => ({ ...actuel, [point.id]: action.decision }));
```

La file d'attente est construite par `construirePoints` (`lib/pointsATraiter.ts:235-258`),
qui mélange **trois origines** : les propositions d'étude, les champs obligatoires
manquants (identifiants `champ:<rule_id>`, ligne 188) et les alertes de cohérence
(identifiants `coherence:<code>`, ligne 203).

Pour les deux dernières, `find` ne trouve rien, **rien n'est envoyé au serveur**, et
`setPointsTraites` marque tout de même le point comme traité.

**Ce que cela produit** : le praticien voit une file homogène et prend des décisions dont
une partie n'est jamais enregistrée. À l'écran il a tout traité ; en base, ces décisions
n'existent pas. Aucun message ne le signale.

**Correction proposée** : soit créer une proposition d'étude pour chaque point présenté
(ce qui est la définition même de l'unité d'analyse), soit afficher les points non
instrumentés dans une file visuellement distincte pour ne pas laisser croire qu'ils sont
mesurés.

---

### 3.10 Deux tables entièrement mortes

**`etude_questions`** (`models.py:252-284`). Vérifié : `grep -rn "EtudeQuestion" backend/`
ne rend que sa déclaration dans `models.py` et la relation dans `EtudeDossier`. Aucun code
n'écrit ni ne lit cette table. Sont donc morts avec elle : le budget de 3 questions par
compte rendu, `source_doute`, `propositions_evitees` — « c'est lui qui justifiera de la
garder ou de la supprimer », dit le commentaire — et la constante `SOURCES_DOUTE`
(`vocabulaire.py:129-133`), référencée nulle part.

**`etude_ergonomie`** (`models.py:311-363`). La route d'écriture existe
(`routes_etude_ergonomie.py:97`) mais `grep -rn "ergonomie" frontend/src/` rend **0
occurrence**. Le tableau d'ergonomie servi à l'administration sera vide.

**Deux colonnes mortes** dans `etude_propositions` : `positions` (`models.py:207`) et
`regles_evaluees` (`models.py:216`). `_vers_ligne` (`service.py:152-167`) ne les renseigne
pas, et aucun autre chemin ne les écrit. Elles sont pourtant exportées
(`export.py:447`) : la colonne `positions` du CSV sera systématiquement vide.

**Ce que cela produit** : au dépouillement, une table vide et une colonne vide se lisent
« le phénomène est absent ». Ce sera faux dans les deux cas — il n'a jamais été observé.

**Correction proposée** : retirer du schéma et de l'export ce qui n'est pas câblé, ou le
câbler. Une colonne exportée qu'aucun code ne remplit est un piège tendu au statisticien.

---

### 3.11 Le collège n'est jamais transmis à l'extraction

**Chemin de code** : `routes_etude.py:219-224`

```python
extraites = extraire(
    cr=corps.cr_propose,
    verbatim=corps.transcription,
    codes=corps.codes,
    alertes=corps.alertes,
)
```

Le paramètre `college=` n'est pas passé. `_restitutions` (`extraction.py:596-608`) retombe
donc **toujours** sur la voie de repli, c'est-à-dire le découpage brut.

**Ce que cela produit** : les propositions soumises au praticien ne sont **pas** celles que
l'arbitrage a jugé nécessaire de faire trancher. Toute la logique de
`extraction.py:407-448` (« ce que trois relecteurs affirment à l'unanimité, citations
vérifiées, ne devient PAS une proposition ») est inerte, et le praticien reconfirme des
évidences — ce que le module dit explicitement vouloir éviter.

**Aggravant** : `App.tsx:487-506` va chercher justifications, citations et voix dans
`explication.trace.college.soumissions` et les apparie aux propositions **par le texte**
(`parAssertion.get(proposition.valeur_proposee.trim())`). Comme les deux listes ne
proviennent plus de la même voie, un appariement qui échoue laisse silencieusement la
proposition sans justification — et le taux de consultation des justifications s'en
trouverait mécaniquement abaissé, sans que rien ne distingue « non consultée » de « non
disponible ».

---

## GRAVITÉ 4 — risque de déploiement

### 4.1 `etude_dossiers.exclu` ne peut pas s'ajouter à chaud sur une base existante

**Chemin de code** : `models.py:119` déclare `exclu` avec `nullable=False`. Le filet de
réconciliation `_reconcilier` (`database.py:77-105`) refuse d'ajouter une colonne
obligatoire et se contente d'un log :

```
ERROR anapath.db: Colonne obligatoire absente en base : etude_dossiers.exclu — migration requise.
```

**J'ai vu ce message** au démarrage de mon script, émis sur l'engine par défaut.

**Scénario qui le produit** : toute base sur laquelle `etude_dossiers` a été créée **avant**
l'ajout de `exclu`. `create_all` ne touche pas une table existante ; `_reconcilier` refuse ;
la colonne n'apparaît jamais. Chaque `SELECT` sur `EtudeDossier` échouera alors en
`OperationalError`, donc **la synthèse rendra 500**. Même situation pour `abandonne`
(`models.py:107`, également `nullable=False`).

**Aggravant** : `alembic/versions/` ne contient que `001_initial_schema.py`, qui ne
référence **aucune** table `etude_*`. Il n'y a pas de migration à jouer.

**Correction proposée** : écrire la migration Alembic des tables `etude_*`, avec
`ALTER TABLE ... ADD COLUMN exclu BOOLEAN NOT NULL DEFAULT 0` et l'équivalent pour
`abandonne`. Sans elle, le gel de version prévu au 12 septembre partira avec une
instrumentation qui plante au premier dépouillement.

---

## Ce que j'ai vérifié et trouvé SAIN

Ces points ont été lus ligne à ligne et, quand c'était possible, exercés. Ils tiennent.

**1. `Taux.valeur` rend `None` sur dénominateur nul** (`analyse.py:64-68`). Vérifié en
sortie réelle : `exactitude_codes`, `abstention_codes`, `utilite_completude` et
`acceptation_non_ancree` sortent tous avec `"valeur": null` et non `0`. La règle 2 est
tenue partout où le dénominateur est réellement nul.

**2. La crainte nommée dans la commande — « caracteres_modifies vaut null si le praticien
ne valide jamais » — est correctement traitée.** `routes_etude_admin.py:192` filtre :
`[d.caracteres_modifies for d in dossiers if d.caracteres_modifies is not None]`, et
`moyenne` (`analyse.py:404-407`) rend `None` sur série vide. Un compte rendu jamais validé
**ne compte pas** comme un compte rendu sans correction. Vérifié : deux dossiers à
`caracteres_modifies = NULL` dans ma reproduction, tous deux absents de la moyenne et du
calcul des terciles (`nb_dossiers_retenus: 3` sur 5 dossiers). *Réserve* : le doublon de
reformatage (§1.6) réintroduit un `0` légitime pour un cas déjà compté — le défaut est
ailleurs, pas ici.

**3. Les dossiers exclus sortent réellement de tous les taux.**
`routes_etude_admin.py:171-180` filtre les dossiers puis restreint les propositions aux
dossiers retenus. Vérifié : sur 6 dossiers créés dont 1 exclu, la synthèse annonce
`nb_dossiers: 5`, et les 3 propositions du dossier exclu sont absentes du dépouillement
(18 propositions en base, 15 dans le décompte `decidees + non_decidees`). `nb_exclus` est
compté à part (`routes_etude_admin.py:208-214`). Le mécanisme est juste ; c'est son
déclenchement (§2.3) qui manque.

**4. « Je ne sais pas » sort des deux termes de l'exactitude des codes**
(`analyse.py:218`, `codes_tranches = codes["juste"] + codes["corrige"]`, et
`abstention_codes` sur `sum(codes.values())`). Lu et vérifié par la structure ; non exercé
faute de codes transmis.

**5. Les trois grilles de décision sont vérifiées côté serveur, par type.**
`service.py:222-225` via `decision_valide` (`vocabulaire.py:59-61`). Un `non_dicte` envoyé
sur une complétude est refusé en 400, pas silencieusement écrit. Couvert par les tests du
dépôt (`tests/test_etude_routes.py`).

**6. La cohérence nature / cause est imposée.** `service.py:230-235` refuse une
`cause_erreur` sur autre chose qu'une `erreur_fond` : « demander la cause d'une
reformulation de style n'a pas de sens ». Et `PropositionCarte.tsx:311-318` oublie la
cause quand la nature change, pour ne pas envoyer une combinaison que le backend
refuserait.

**7. Latence et `hative` sont calculés côté serveur, jamais acceptés du client**
(`service.py:276-280`). Le client ne peut pas les rendre flatteurs. La seule chose qu'il
peut fausser est t0/t1 (§3.1).

**8. `cr_propose` est figé à la création et jamais réécrit.** `grep -rn "cr_propose"
backend/` hors tests : la seule assignation est `service.py:134`, dans `ouvrir_dossier`.
`clore_dossier` ne le touche pas, il n'est utilisé qu'en lecture pour
`distance_edition` (`service.py:347`). L'invariant annoncé en tête du module est tenu.

**9. Le service refuse de clore un dossier abandonné** (`service.py:343-344`) et
**exige un motif non vide pour exclure** (`service.py:428-431`). L'exclusion est
réversible (`exclu=False` remet `motif_exclusion` et `exclu_par` à `None`).

**10. `_exiger_base` refuse explicitement en 503 plutôt que de perdre une mesure en
silence** (`routes_etude.py:125-136`), et `_ecrit` (`routes_etude.py:139-151`) transforme
un `None` inattendu en 500 net. Une écriture d'étude ne peut pas échouer sans bruit.

**11. `backend/etude/export.py` est la pièce la plus solide de l'instrumentation.**
Vérifié en lecture intégrale :
- `_nombre` (304-306) rend une cellule **vide** pour un nombre non mesuré : « écrire 0
  inventerait une observation » ;
- `_booleen` (309-318) rend une cellule **vide** et non `'false'` pour un booléen non
  renseigné, avec le raisonnement explicite sur `omission_signalee` ;
- la colonne `dossier_exclu` est **répétée sur chaque table fille** (propositions,
  questionnaires, pauses) « pour que le filtre des exclus se fasse sans jointure : une
  jointure oubliée est une jointure qui n'aura pas lieu » ;
- `ancree` est **recalculé depuis `empan_debut`** (451) plutôt que repris d'un champ
  dérivé — les deux ne peuvent pas diverger ;
- les dossiers exclus **figurent** dans l'export avec leur motif : « c'est à l'analyse de
  filtrer, pas à l'export de cacher » ;
- les pseudonymes sont stables par ordre d'inclusion, départagés par identifiant de compte,
  pour que deux exports de la même base soient identiques (`export.py:242-255`) ;
- le corpus est chargé **en une seule passe** (`charger_corpus`, 192-201) pour qu'une
  exclusion concurrente ne produise pas une archive qui se contredit d'un fichier à
  l'autre.

C'est le seul endroit du système où les trois règles du projet sont appliquées de bout en
bout. **Si un chiffre doit être publié, il faut le calculer depuis cet export, pas depuis
la synthèse HTML.**

**12. `backend/etude/ergonomie.py` est bien conçu** — il ne lui manque que son émetteur.
Instantanés cumulés plutôt qu'incréments, `dernier_par_zone` idempotent (« un lot perdu ne
coûte que du détail, jamais un total, et un envoi rejoué ne compte rien deux fois »), trois
dénominateurs séparés pour trois moyennes (`ProfilZone`), `profondeur_max` nulle quand la
zone tient dans l'écran, zones nommées et non sélecteurs CSS, et un lot refusé **en entier**
si une zone est inconnue plutôt qu'écarté en silence.

**13. `fsus_pret()` bloque le questionnaire tant que les libellés publiés manquent**
(`routes_etude.py:374-382`, 409 CONFLICT). Mieux vaut ne rien recueillir qu'un score
incomparable. `score_fsus` (`questionnaires.py:410-424`) rend `None` sur item manquant
plutôt qu'un score partiel. Le fichier `backend/data/fsus.json` existe et attend ses
libellés.

**14. Le décompte du questionnaire périodique est tenu côté serveur**
(`service.py:357-374`), et il filtre correctement : `t5_cloture is not None`,
`abandonne is False`, `exclu is False`. C'est le seul endroit du backend où les trois
conditions sont réunies — `_corpus` gagnerait à s'en inspirer (§2.2).

**15. Les 622 tests du dépôt passent** (`python -m pytest -q` → `622 passed in 5.02s`).
Aucun fichier de production n'a été modifié par cet audit ; le script de reproduction vit
hors du dépôt.

---

## Ordre de traitement suggéré

| # | Correction | Coût | Effet |
|---|---|---|---|
| 1 | `_observee` : passer `ancree` et `nature_correction` | 2 lignes | Débloque le critère principal bloquant (§1.1, §1.2a) |
| 2 | Migration Alembic des tables `etude_*` | 1 fichier | Sans elle, rien ne se dépouille (§4.1) |
| 3 | `noterTranscription` dans la restauration de brouillon | 1 ligne | Arrête une perte silencieuse et sélective (§3.8) |
| 4 | Monter `useHorlogeEtude` | quelques lignes | `revision_nette_ms` cesse d'être un faux net (§3.7) |
| 5 | Monter les questionnaires + lire `questionnaire_periodique_du` | modéré | Deux critères principaux (§2.4) |
| 6 | Ne pas rouvrir un dossier à chaque reformatage | modéré | Arrête le doublement du corpus (§1.6) |
| 7 | Dénominateur de `changement_apres_justification` | 3 lignes | Supprime un faux 0 % (§1.3) |
| 8 | Seuil `SEUIL_HATIVE_MOTS` | 1 ligne | Réanime le garde-fou n°2 (§1.4) |
| 9 | Bouton d'exclusion + `nb_exclus` affiché + `exclu_a` | modéré | Rend l'exclusion exerçable et datable (§2.3) |
| 10 | `nb_praticiens` et `nb_dossiers_clos` | 2 lignes | Deux dénominateurs propres (§2.1, §2.2) |
| 11 | Terciles par praticien | 10 lignes | L'effet d'apprentissage cesse d'être un artefact d'UUID (§3.5) |
