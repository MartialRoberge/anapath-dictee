# Kit de collage Freeform — workflow anapath jusqu'à D4

Mode d'emploi : dépose d'abord `Workflow_anapath_D4_board.pdf` dans le board (il arrive
comme objet unique, verrouille-le : clic droit → Verrouiller). Ensuite, colle bloc par bloc
le contenu ci-dessous pour créer des zones de texte éditables par-dessus.
Dans Freeform, un collage multi-lignes = une seule zone de texte. Colle donc un bloc à la fois.

Code couleur du board :
- bleu = dictionnaire ADICAP
- rouge = nœud de décision / garde-fou
- orange = aiguillage
- vert = cascade D4
- violet = contrôle transverse hors code

---

## RANG 1 — Positions 1 à 4

### D1 — Mode de prélèvement
Position 1 · 1 caractère alphabétique
19 possibilités
Question : comment le prélèvement a-t-il été obtenu ?
Entrée : demande d'examen, fiche de transmission, contexte opératoire
Sortie : 1 caractère
Point dur : C vs G (cytoponction guidée ou non), P vs H — le guidage par imagerie est souvent implicite dans la dictée

### D2 — Type de technique
Position 2 · 1 caractère alphabétique
22 possibilités — le Z (ENZYMOLOGIE) manquait dans la version précédente du board
Question : quelle nature d'acte est produite sur le prélèvement ?
Attention : contient des natures d'acte non techniques — D données cliniques, B bureautique-courrier, L relecture, P photographie, W télépathologie
Cardinalité : 1..n par prélèvement

### D3 — Appareil, organe, région
Positions 3-4 · 2 caractères
Arbre à 2 niveaux, pas liste plate :
appareil = initiale de l'appareil + Z (AZ, BZ, CZ, DZ…)
organe = initiale de l'appareil + initiale de l'organe
Question : d'où vient anatomiquement le prélèvement ?
Conditionne le nœud D6 en aval

### Exigences particulières — contrôle transverse
Pas un dictionnaire ADICAP
Ce qu'on regarde : contenant, identification, quantité, état, réception, transport, température, milieu de conservation, fixation, délai avant fixation, frais/congelé, stérilité, précautions
Source réelle des règles : manuel de prélèvement du laboratoire
ISO 15189 exige que ces règles existent — elle ne les fournit pas
Sortie : conforme / conforme avec réserve / non conforme
Une non-conformité se code, et elle se code dans D4 chapitre 01

---

## RANG 2 — Décision et aiguillage

### N0 — Gate contributivité
Question : le matériel est-il analysable ?
NON → code terminal, pas de diagnostic (D4 chapitre 01) :
0110 prélèvement sans valeur
0111 par insuffisance ou absence de matériel
0112 par mauvaise fixation
0113 par inclusion inappropriée
0114 par altération due au prélèvement
0115 par nécrose
0116 par putréfaction ou autolyse cadavérique
0117 par artefact
0118 absence de prélèvement (flacon vide…)
0119 par erreur de prélèvement de l'organe ou de la lésion

### N1 — Routage positions 5-8
Question : dans quel registre nosologique se situe la lésion ?
Trois dictionnaires mutuellement exclusifs, masques distincts :
D4 pathologie générale non tumorale — N N N N
D5 pathologie tumorale — A N A N
D7 cytopathologie — 0 A N N
Contraint par D2 : cytologie par étalement oriente vers D7

### N2 — Override D6 · codes liés
Question : existe-t-il un code spécifique à cet organe ?
6 caractères = code organe (2) + code lésionnel (4)
Le code lésionnel est toujours associé à l'organe, le plus souvent entre 0200 et 0999
Employé quand la lésion n'a pas d'équivalent en pathologie générale, ou prend une dénomination particulière du fait de sa localisation
Exemples : BA0221 sialométaplasie nécrosante · AC6743 hyperplasie des végétations adénoïdes
OUI → code lié, on ne descend pas la cascade D4

---

## RANG 3 — Cascade D4

### N3 — Chapitre (caractère 5)
10 valeurs · nombre de codes
0 caractères généraux — 84
1 maladie innée et grande malformation externe — 285
2 malformation et dysgénésie des tissus et des viscères — 215
3 lésion traumatique, mécanique, agent physique/chimique/médicamenteux — 277
4 trouble vasculaire — 183
5 trouble métabolique spontané — 282
6 modification de volume, dystrophie, kyste, métaplasie et dysplasie acquise — 462
7 inflammation commune — 245
8 inflammation particulière — 330
9 pathologie de l'immunité, affections et conditions diverses — 203

### N4 — Groupe lésionnel (caractères 5-6)
90 groupes au total, filtrés par le chapitre retenu — en pratique une dizaine de choix
Les deux premiers caractères définissent le groupe lésionnel
Le code pivot xx00 est un code VALIDE
Exemple : 7600 inflammation subaiguë et chronique (SAI)
Repli légitime si la dictée ne précise pas

### N5 — Variété (caractères 7-8)
Les deux derniers caractères précisent les variétés de lésions dans le groupe
414 codes SAI dans le dictionnaire, soit 16 %
La descente partielle est le mode NOMINAL, pas une dégradation
Ne jamais forcer la descente jusqu'ici

### N6 — Validation
Question : le code composé existe-t-il ?
Vérification contre les 2 566 codes du dictionnaire D4
ÉCHEC → remonter d'un niveau (xx00), JAMAIS inventer un code
Le code n'est pas généré, il est COMPOSÉ par descente d'arbre → non hallucinable

---

## BANDEAU — Règles structurantes

Cardinalité : dossier → 1..n prélèvements → 1..n techniques (D2) → 1..n lésions codées. Le code ADICAP n'est pas par dossier.

Double codage : prévu par le thésaurus (0156 à double coder avec 0191/0193/0194). Le modèle doit accepter une LISTE de codes par lésion.

Chapitre 0 = méta : relecture 0080-0085, concordance cyto/histo 0090-0093, dépistage 0088 / contrôle 0089, RCP 0198, protocole et consentement 0191-0194. Ces codes ne viennent PAS de la dictée mais du contexte dossier — à alimenter automatiquement.

Normalisation : le thésaurus officiel est en MAJUSCULES NON ACCENTUÉES. Fixer une forme normalisée unique pour tout matching depuis la dictée.

Version : édition 2009 v5-04, dernière mise à jour du thésaurus. Alignement CIM-O unidirectionnel ADICAP → CIM-O ; le transcodage sortant est un chantier à part.

---

## À ajouter toi-même sur le board (zones laissées ouvertes)

- Branche D5 (pathologie tumorale) : famille histogénétique en caractère 5, comportement tumoral en caractère 6, type histologique en 7-8
- Branche D7 (cytopathologie), masque 0ANN
- Zone facultative : position 9 champ libre, 10 grading, 11-12 D8 topographie complémentaire, 13 latéralité (G/D/B), 14-15 organe siège de la tumeur primitive
- Le pont dictée → nœud : quelles entités on extrait du texte à chaque niveau
- L'interface de vérification pathologiste : ce qui est affiché, ce qui est confirmé, ce qui est modifiable
