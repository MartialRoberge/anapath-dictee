# MARC — index de reprise

Point d'entrée pour Claude Code. Déposer ce dossier dans le repo sous `docs/specs/`.

---

## Comment reprendre

Ouvre Claude Code dans le repo et donne-lui cette consigne :

> Lis `docs/specs/00_INDEX.md` puis tous les fichiers qu'il référence. Ce sont les
> spécifications de MARC. Confronte-les au code existant et liste les écarts, en distinguant
> ce qui est implémenté, ce qui est implémenté différemment, et ce qui manque. Ne modifie rien
> avant que j'aie validé la liste.

Le premier passage doit être un **audit**, pas une implémentation. Le code existant a des raisons
d'être ce qu'il est, et les specs ci-dessous ont été écrites sans le voir.

---

## Les fichiers, par ordre de lecture

### À lire en premier

**`MARC_V2_specification_maitresse.md`** — le document de référence. Diagnostic de la V1 à partir
des retours terrain, le concept de dérivation, l'architecture en modèle de concepts + adaptateurs
d'export, le modèle de cardinalité, l'écran de revue, et la séquence de construction avant le gel
du 12 septembre. **Tout le reste s'y rattache.**

### Comprendre le domaine

**`MARC_pipeline_dictee_seule.html`** — la carte fonctionnelle complète. Quatorze étapes de la
voix au compte rendu, avec pour chacune la question fonctionnelle, les entrées et sorties, le
référentiel utilisé, les règles dures et ce que l'étude mesure à cet endroit. À ouvrir dans un
navigateur. C'est le document de référence : tout le reste s'y rattache.

**`adicap_D4.csv`** — les 2 566 codes du dictionnaire D4, extraits du thésaurus, avec chapitre,
groupe, libellé, libellé normalisé et statut de révision. Roue de secours uniquement : la source
officielle est le XLSX/OWL sous licence LOv2 sur esante.gouv.fr, qui donne l'arbre déjà construit
via les colonnes identifiant et parent. **Basculer dessus dès que possible.**

### Implémenter

**`Codage_D1_D2_table.json`** — table de décision D1 et D2. D1 : actes simples, familles
base × modificateur, table geste × organe pour I/O. D2 : H par défaut, C sous condition négative,
et surtout la distinction code primaire / codes secondaires. Contient le modèle de cardinalité,
les cinq règles de cohérence inter-positions, et les trois questions de levée de doute
pré-rédigées. Les champs `a_valider` marquent ce qui vient de moi et non du pathologiste : à ne
pas implémenter avant validation.

**`D1_analyse_et_questions.md`** — pourquoi la table est structurée ainsi. Trois problèmes du
lexique d'origine : collision exacte I/O, code S vide par bug de fusion, dix-huit inclusions
ordre-dépendantes. Contient la liste des questions à poser au pathologiste.

**`Politique_de_questions.md`** — quand le logiciel pose une question au praticien plutôt que de
deviner ou de s'abstenir. Transversal à D1, D2 et D3. Contient la règle de valeur d'information,
le budget de trois questions par compte rendu, et les caveats sur les scores de confiance de
transcription.

**`Outil_ideal_architecture_cible.md`** — la vision cible et le catalogue de cohérence
déterministe (dix-sept règles vérifiables sans modèle). À construire après le congrès.

### Instrumenter pour l'étude

**`MARC_cahier_de_recueil.md`** — le plus opérationnel pour le développement. Contient la grille
de validation, la règle du littéral qui borne le nombre de cases, le verrouillage de l'export et
ses garde-fous, la spécification complète de mesure du temps, l'intégralité des questionnaires,
la liste des événements à loguer et le schéma JSON.

**`Protocole_etude_MARC.md`** — la méthode et les seuils. Utile pour comprendre pourquoi certaines
contraintes techniques existent, notamment le verrou d'export et la télémétrie de latence.

### Contexte historique

**`Specification_operationnelle_CR_ACP.html`** — première version de l'architecture, écrite avant
la contrainte « dictée seule ». Certains éléments sont dépassés. À lire pour le raisonnement sur
les deux couches — ADICAP pour le concept, data set synoptique pour la complétude — qui reste
valable.

**`Workflow_anapath_D4_board.pdf`** et **`Freeform_kit_de_collage.md`** — le board Freeform sur le
nœud D4. Attention, il indique la position 9 comme « champ libre » : c'est faux, elle est laissée
vide comme séparateur entre zone obligatoire et zone facultative.

---

## Les trois règles qui gouvernent tout le code

**Le code ADICAP n'est jamais généré, il est composé.** Le modèle de langage choisit dans une
liste fournie par la couche de recherche. Il n'émet jamais une chaîne de caractères de code.
Toute position écrite doit l'être par l'étape qui en a la charge.

**Pas d'empan, pas de proposition.** Toute proposition affichée porte l'empan exact du verbatim
qui la justifie. Un candidat sans ancrage textuel est rejeté avant affichage.

**L'abstention est un résultat.** En cas d'échec de validation, le système remonte d'un niveau
vers le code pivot ou se tait. Il ne complète jamais.

---

## État au moment de la rédaction

| Sujet | État |
|---|---|
| D1 | table de décision produite, questions au pathologiste en attente |
| D2 | fait — primaire H/C, sept codes secondaires, cardinalité modélisée |
| D3 | arbre à deux niveaux identifié. **À détailler.** |
| D4 à D8 | structure documentée, implémentation non commencée |
| Complétude | mapping organe × famille lésionnelle **non commencé — actif principal** |
| Protocole d'étude | rédigé, à faire valider |
| Résumé congrès | soumis, présentation les 18-20 novembre |

## Priorité absolue

La capture des validations et des modifications ne fonctionne pas en V1. La grille de validation
**est** l'instrument de mesure de l'étude. Sans elle, aucune métrique principale n'existe.
C'est le chantier numéro un, avant toute nouvelle fonctionnalité.

## Décisions actées, à ne pas rouvrir

- Entrée = dictée seule. Pas de dossier clinique, pas de demande, pas de SGL.
- Conservation = transcription seule, pas d'audio.
- D2 par défaut H, exceptions cytologiques uniquement.
- « macro » et « micro » sont des marqueurs de section, jamais des codes D2.
- N, V et X actifs mais sur correspondance exacte du syntagme complet uniquement.
- Export verrouillé tant que toutes les propositions ne sont pas décidées, avec bouton d'abandon.
- Gel de version au 12 septembre.
- Le compte rendu est le produit ; ADICAP, SNOMED, CIM-O3 et la cotation sont des adaptateurs
  d'export sur un modèle de concepts commun.
- Quatre verbes : restituer, dériver, demander. Générer est interdit.
- Contraindre les assertions, jamais la forme.

## Le prochain point dur

Le mapping **organe × famille lésionnelle → champs attendus**. Il n'existe nulle part sur étagère,
il conditionne toute la fonctionnalité de complétude, et c'est aussi là que passe la frontière
réglementaire du dispositif médical. À construire sur deux ou trois localisations à fort volume,
pas en couverture.
