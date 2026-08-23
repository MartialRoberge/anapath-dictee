# Étude MARC — protocole opérationnel

**Version 0.1 · à figer avant le premier cas · document de travail**

Évaluation d'un outil d'assistance à la rédaction du compte rendu d'anatomie et cytologie
pathologiques par reconnaissance vocale et modèle de langage, avec traçabilité des propositions.

---

## 0. Le problème de calendrier, à régler en premier

Carrefour Pathologie 2026 se tient du 18 au 20 novembre 2026 au CNIT Forest, Paris-La Défense.
**La soumission des résumés a fermé le 2 juin 2026.**

Deux cas de figure, à trancher cette semaine :

**A — le résumé a été soumis avant le 2 juin.** Alors le calendrier est contraint : il reste
environ douze semaines, dont six exploitables sur le terrain. Le protocole ci-dessous est
dimensionné pour ça.

**B — le résumé n'a pas été soumis.** Alors la cible réaliste est la Journée Intelligence
Artificielle en Pathologie (JIAP), qui se tient en mars, ou les Assises de Pathologie. Dans ce
cas, ne pas comprimer l'étude : six mois de recueil valent infiniment mieux qu'un poster bâclé,
et le sujet est porteur — le programme SFP 2026 met l'IA en pathologie au premier plan.

Le reste du document suppose le cas A.

---

## 1. Ce que dit la littérature, et pourquoi ça change le design

Trois faits établis qui doivent gouverner le protocole.

### 1.1 Le gain de temps ne se démontre presque jamais

Les déploiements les plus massifs d'assistants de rédaction par IA n'ont pas réussi à montrer
de gain de temps significatif :

| Étude | Effectif | Résultat sur le temps |
|---|---|---|
| Permanente Medical Group | plus grand déploiement à ce jour | 18 secondes par consultation |
| Intermountain Health | cohorte appariée | aucun gain de productivité significatif |
| Atrium Health (Liu et al.) | 215 cliniciens | aucun gain d'efficience global significatif |
| STREAMLINE (Kakaday et al.) | pilote | 1,4 min/visite, non significatif (p = 0,38) |
| Déploiement espagnol | 2,33 M consultations | 15,01 vs 14,65 min, convergence vers la parité |

**Conclusion opérationnelle : construire l'étude sur le temps avec dix praticiens, c'est
programmer un résultat nul.** L'impossibilité de faire du avec/sans n'est donc pas un handicap
— c'est une chance, parce que la comparaison avec/sans est exactement le design qui échoue.

Ce qui s'améliore de façon constante dans la littérature, en revanche : l'expérience du
clinicien, la charge cognitive, la qualité perçue de la documentation.

### 1.2 On mesure les erreurs sans en semer

La méthode standard du domaine n'est pas l'injection d'erreurs : c'est **l'annotation de la
sortie réelle, proposition par proposition**. Les taux de référence publiés — environ 1,5 %
d'hallucination et 3,5 % d'omission — proviennent de l'annotation d'environ 13 000 phrases par
des cliniciens. Les taux d'erreur globaux rapportés pour les assistants récents se situent
entre 1 et 3 %.

**Les cases à cocher prévues dans MARC sont donc déjà l'instrument de mesure.** Il suffit de
leur donner la bonne granularité. Aucune charge supplémentaire pour le praticien, et des
résultats directement comparables à la littérature internationale.

### 1.3 La traçabilité est en train de devenir un standard de publication

Les signaux de reporting qui émergent dans les travaux récents sont la charge d'édition du
clinicien (temps de révision, part des sorties nécessitant des modifications substantielles) et
**l'attribution de source / provenance**, c'est-à-dire le rattachement de chaque assertion à sa
source horodatée dans l'enregistrement.

Autrement dit : l'explicabilité que tu veux n'est pas un supplément d'âme, c'est ce que la
communauté commence à exiger. C'est un angle de publication à part entière, et c'est
différenciant — les études publiées jusqu'ici ne le rapportent quasiment pas.

### 1.4 Le positionnement scientifique

Le travail publié le plus proche est une étude de faisabilité 2026 (JMIR Formative Research)
combinant Whisper et des LLM open source pour la transcription de macroscopie en pathologie.
Ses limites déclarées : audio **simulé**, annotation au niveau **du rapport** et non du terme,
absence de validation prospective en conditions réelles.

MARC peut se positionner exactement sur ces trois limites : dictées **réelles**, annotation
**proposition par proposition**, recueil **prospectif en pratique courante**. C'est une
contribution nette, et elle est atteignable en six semaines.

---

## 2. Question de recherche

> Un outil d'assistance à la rédaction fondé sur la reconnaissance vocale, un modèle de langage
> contraint par le thésaurus ADICAP et un module de complétude, produit-il des propositions
> acceptables, sûres et traçables en pratique courante d'anatomie et cytologie pathologiques ?

Objectifs, dans cet ordre :

1. **Sécurité** — quantifier les propositions non soutenues par la dictée et les omissions.
2. **Acceptabilité** — quantifier le taux d'acceptation sans modification.
3. **Utilisabilité** — mesurer l'ergonomie par une échelle validée.
4. **Traçabilité** — mesurer si les justifications sont consultées et si elles changent la décision.

Le temps de rédaction est un objectif **exploratoire**, mesuré en ressenti et en charge
d'édition, jamais en critère de jugement principal.

---

## 3. Conception

**Étude prospective, observationnelle, multicentrique, sans bras témoin.**

Il n'y a pas de comparaison avec/sans, et c'est assumé et justifié dans le protocole par la
section 1.1. Le comparateur n'est pas la pratique habituelle du praticien : c'est **le compte
rendu que le praticien valide lui-même**. Chaque proposition est confrontée à la décision de
celui qui a dicté.

**Limite à déclarer explicitement.** Ce design mesure l'accord entre la proposition et le
jugement du praticien, pas la vérité diagnostique. C'est une étude de concordance et
d'utilisabilité, pas une étude de performance diagnostique. L'écrire dans le protocole, dans le
résumé et dans la discussion — c'est le premier point sur lequel on sera attaqué, et c'est
imparable dès lors qu'on l'a déclaré.

### Unité d'analyse

**La proposition, pas le compte rendu.** C'est la clé de la puissance statistique.

Dix praticiens × 25 comptes rendus × 8 à 15 propositions ≈ **2 000 à 3 750 propositions
annotées**. À n = 2 000, un taux de 2 % s'estime avec un intervalle de confiance à 95 %
d'environ ± 0,6 point. C'est largement suffisant pour publier des taux crédibles, là où dix
comptes rendus par praticien ne permettraient rien.

Analyse en modèle mixte avec effet aléatoire praticien, pour tenir compte du regroupement des
propositions par opérateur.

### Population

Dix anatomopathologistes, exercice libéral et hospitalier, avec diversité d'ancienneté et de
type d'exercice. Critère d'inclusion : dicter habituellement ses comptes rendus. Aucune
exclusion sur l'accent ou l'aisance informatique — au contraire, c'est une variable
d'intérêt.

### Cas inclus

Comptes rendus de routine, non sélectionnés, sur le flux courant. Restreindre à deux ou trois
localisations à fort volume pour que le module de complétude soit réellement alimenté. Inclure
délibérément une petite proportion de prélèvements non contributifs : c'est le comportement le
plus critique du système, sa capacité à ne rien affirmer.

Objectif : 25 cas par praticien sur six semaines, soit 4 à 5 par semaine. Charge faible,
compatible avec une activité normale.

---

## 4. L'instrument — grille d'annotation par proposition

C'est le cœur du dispositif. Une seule interaction par proposition, quatre choix mutuellement
exclusifs.

### 4.1 Propositions de restitution (ce que le système a compris de la dictée)

| Choix | Libellé affiché | Ce qu'on mesure |
|---|---|---|
| ✓ | **Conforme** — je valide tel quel | Acceptation sans modification |
| ✎ | **À corriger** — juste sur le fond, à retoucher sur la forme | Charge d'édition |
| ✗ | **Non dicté** — je n'ai pas dit ça | **Hallucination** |
| ⊘ | **Hors sujet** — proposition non pertinente ici | Bruit |

Au niveau du compte rendu, un champ unique en fin de revue :

> **Quelque chose que vous avez dicté a-t-il été omis ?** ☐ Non ☐ Oui → lequel (texte libre)

C'est la mesure d'**omission**. Un champ, dix secondes.

### 4.2 Suggestions de complétude (ce que le système signale comme possiblement manquant)

Distinction essentielle, à ne pas écraser :

| Choix | Libellé affiché | Ce qu'on mesure |
|---|---|---|
| ✓ | **Pertinent, je l'ajoute** | Vraie valeur ajoutée |
| ~ | **Pertinent, mais je choisis de ne pas le mettre** | Utile mais non retenu — **pas** un faux positif |
| ✗ | **Non pertinent ici** | Faux positif |

Confondre les deux dernières lignes fausserait entièrement le taux de faux positifs. Un
pathologiste qui juge une suggestion pertinente et décide souverainement de ne pas la faire
figurer valide le système, il ne l'invalide pas.

### 4.3 Télémétrie passive — zéro charge pour le praticien

À logger silencieusement, proposition par proposition :

- panneau de justification ouvert (oui/non)
- délai entre affichage et décision, en millisecondes
- décision modifiée après ouverture du panneau (oui/non)
- nombre de caractères modifiés en cas de correction
- durée totale passée sur l'écran de revue

Les deux premières donnent le **taux de consultation des justifications**. La troisième donne
l'**effet de la justification sur la décision** — c'est la mesure d'explicabilité la plus
convaincante qu'on puisse produire, et personne ne la publie.

La deuxième donne aussi un proxy honnête du biais d'automatisation, sans rien semer :
**une acceptation en moins de deux secondes sur une proposition complexe est une acceptation
non inspectée.** À rapporter comme signal exploratoire, avec la prudence qui s'impose.

---

## 5. Questionnaires

### 5.1 Après chaque cas — cinq items, trente secondes

À afficher immédiatement après la validation, pas en fin de session : les jugements
rétrospectifs globaux sont peu fiables.

Échelle de 1 (pas du tout d'accord) à 5 (tout à fait d'accord).

1. La proposition correspondait à ce que j'ai dicté.
2. J'ai dû faire beaucoup de corrections. *(item inversé)*
3. Les suggestions de complétude m'ont été utiles sur ce cas. *(+ option « non applicable »)*
4. J'ai compris pourquoi le système proposait ce qu'il proposait.
5. Par rapport à ma pratique habituelle, ce compte rendu m'a pris :
   beaucoup plus de temps / plus / autant / moins / beaucoup moins.

Champ libre facultatif, une ligne.

### 5.2 En fin d'étude

**F-SUS** — version française du System Usability Scale, validée scientifiquement (Gronier &
Baudet, 2021, *International Journal of Human–Computer Interaction*, 37(16), 1571-1582).
Librement utilisable en citant la référence. Utiliser cette version et non une traduction
maison : c'est ce qui rend le score comparable et défendable.

**PDQI-9** — Physician Documentation Quality Instrument, pour la qualité documentaire perçue.
Instrument reconnu dans les études d'assistants de rédaction.

**Charge de travail** — NASA-TLX, ou sa forme courte à quatre items (Physician Task Load),
utilisée dans l'essai randomisé NEJM AI sur les assistants ambiants.

**Entretien semi-structuré de 20 à 30 minutes** avec 4 ou 5 praticiens volontaires. La partie
qualitative est ce qui fera la différence à l'oral et c'est ce qui manque le plus dans la
littérature actuelle. Analyse thématique.

---

## 6. Critères de jugement et seuils

À figer maintenant. Un seuil fixé après avoir vu les données ne vaut rien.

### Principaux — sécurité

| Critère | Seuil | Référence externe |
|---|---|---|
| Propositions non soutenues par la dictée | < 2 % | ~1,5 % dans la littérature |
| Omissions signalées | < 5 % des comptes rendus | ~3,5 % dans la littérature |
| Propositions non soutenues **acceptées** malgré tout | 0 sur les items à portée thérapeutique | — |

La dernière ligne est bloquante et ne se compense pas.

### Principaux — acceptabilité et ergonomie

| Critère | Seuil | Référence externe |
|---|---|---|
| Acceptation sans modification | ≥ 60 % | 58 % rapporté sur un déploiement hospitalier |
| Score F-SUS moyen | ≥ 70 | 68 = seuil de moyenne établi |
| Praticiens souhaitant continuer | ≥ 8/10 | — |

### Secondaires

| Critère | Seuil |
|---|---|
| Suggestions de complétude jugées pertinentes (✓ ou ~) | ≥ 70 % |
| Justifications consultées au moins une fois par cas | ≥ 50 % des cas |
| Item 4 du questionnaire par cas (compréhension) | moyenne ≥ 4 / 5 |
| Taux d'abstention du système, et justesse de ces abstentions | descriptif |

### Exploratoires

Temps ressenti (item 5), charge d'édition objective, délai de décision, effet de l'ouverture du
panneau de justification sur la décision, variabilité inter-praticien.

**Aucun critère de temps absolu.** Si un praticien souhaite chronométrer quelques comptes rendus
en pratique habituelle, c'est un élément de contexte descriptif, jamais une comparaison.

---

## 7. Calendrier, en remontant du 18 novembre

| Période | Étape |
|---|---|
| Semaine du 25 août | Trancher le cas A/B. Geler la version logicielle. Vérifier le statut du résumé. |
| 1 – 12 septembre | Rodage sur 1 ou 2 praticiens proches. Correction des blocages ergonomiques. **Aucune modification du logiciel après cette phase.** |
| 15 septembre – 31 octobre | Recueil terrain, 10 praticiens, 6 semaines. Point hebdomadaire sur le volume. |
| 1 – 7 novembre | Gel des données, analyse, calcul des taux et intervalles de confiance. |
| 8 – 14 novembre | Poster ou diaporama. Relecture par un pathologiste co-auteur. |
| 18 – 20 novembre | Carrefour Pathologie, CNIT Forest. |

Le gel de version au 12 septembre n'est pas négociable : une étude sur une cible mouvante ne
produit aucun résultat interprétable.

---

## 8. Cadre réglementaire et éthique — à instruire en parallèle

- **Qualification du dispositif.** Restituer ce qui a été dicté n'est probablement pas un
  dispositif médical. Suggérer un élément non mentionné s'en rapproche. La frontière passe dans
  le module de complétude. À faire trancher par un spécialiste avant commercialisation, pas
  après.
- **Données de santé.** Hébergement HDS, analyse d'impact RGPD, sort des enregistrements audio,
  durée de conservation. Les études publiées récentes précisent explicitement qu'aucun audio ni
  transcription n'est conservé à des fins d'évaluation — c'est une position à envisager.
- **Consentement praticien**, information sur le recueil de télémétrie.
- **Statut de la recherche.** Une évaluation d'outil documentaire sur données déjà produites
  relève souvent d'une démarche qualité plutôt que d'une recherche impliquant la personne
  humaine. À faire confirmer, et à écrire dans le résumé.
- **Le compte rendu reste celui du pathologiste.** À rappeler dans l'interface, pas seulement
  dans les conditions d'utilisation.

---

## 9. Ce qu'il reste à construire

| Élément | Statut | Source |
|---|---|---|
| Dictionnaires ADICAP D1 à D8 | Disponible | XLSX et OWL, licence LOv2, esante.gouv.fr |
| Arbre de descente ADICAP | À dériver | colonnes `id` / `parentId` du XLSX officiel |
| Lexique de biaisage ASR | **À construire** | les 9 511 concepts ADICAP forment un vocabulaire de contrainte prêt à l'emploi |
| Mapping organe × famille lésionnelle → champs attendus | **À construire — actif principal** | comptes rendus standardisés INCa/SFP, protocoles ICCR, classifications OMS |
| Corpus de dictées réelles annotées | En cours | l'étude elle-même le produit |
| Règles métier de mise en forme | Existant | travail déjà mené sur les transcriptions réelles |

Le lexique de biaisage mérite d'être souligné : le thésaurus ADICAP est un vocabulaire médical
français fermé de près de dix mille termes. Utilisé comme contrainte de décodage sur le moteur
de reconnaissance vocale, il attaque directement le problème documenté de la spécialité — la
transcription phonétiquement plausible mais cliniquement absurde.

---

## 10. Références à citer

**Cadre d'évaluation**
- SCRIBE evaluation framework, *npj Digital Medicine*, 2025
- Barriers and opportunities of scaling ambient AI scribes, *npj Digital Medicine*, 2026
- QUEST human evaluation framework

**Résultats de référence**
- Ambient AI Scribes in Clinical Practice: A Randomized Trial, *NEJM AI* (238 médecins, 14 spécialités)
- Performance, acceptability and impact of ambient listening scribe technology, *BMC Health Services Research*, 2026 (58 % d'acceptation sans modification)
- Real-world evaluation in Spanish outpatient care after 2.3 million uses, *Frontiers in Digital Health*, 2026

**Reconnaissance vocale en pathologie**
- Zhou et al., Analysis of Errors in Dictated Clinical Documents, *JAMA Network Open*, 2018 (7,4 % au stade reconnaissance vocale, 0,3 % après signature)
- Automatic Speech Recognition and Large Language Models for pathology dictation, *JMIR Formative Research*, 2026 — le comparateur direct
- Al-Aynati & Chorneyko, *Archives of Pathology & Laboratory Medicine*, 2003
- Kang et al., *American Journal of Clinical Pathology*, 2010

**Instruments**
- Gronier & Baudet, F-SUS, *IJHCI*, 2021
- PDQI-9
- NASA-TLX / Physician Task Load

**Référentiel**
- Thésaurus ADICAP, index raisonné des lésions, édition 2009 version 5-04
- ADICAP, présentation détaillée, ASIP Santé, version 1.0, 31 mai 2019
