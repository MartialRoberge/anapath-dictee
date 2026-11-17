# 08 - Robustesse du pipeline v3 (testeur adversarial et correctifs backend)

Perimetre : `backend/projet/**`, `backend/kb/**`, `scripts/build_kb.py`, tests `test_projet_robustesse.py` et
`campagne_v3*.py`. Rien n'a ete committe ni deploye. Sorties brutes de campagne (elles contiennent les dictees de
test) : HORS depot, `/private/tmp/claude-501/-Users-martialroberge--claude-spares-spare-UjL0l3/a173d645-1c38-4b98-9c3e-c3da3d91cce9/scratchpad/camp/`.

## 1. Defauts de base de connaissances corriges (build : `--date 2026-11-15`)

| Defaut signale | Cause | Correctif |
|---|---|---|
| libelle invalide `champ:melanome.grade` | item INCa « Grade : non reconnu » importe comme champ obligatoire (idem poumon et thyroide, « non utilise ») | `build_kb.py` : les items INCa dont le libelle dit « non utilise / non reconnu » ne deviennent jamais des champs (303 -> 300 champs) |
| « Emboles vasculaires » sur biopsie pulmonaire / prostatique | applicabilite par defaut = tous prelevements | `_finaliser_champ` : le concept `emboles` n'est plus applicable sur biopsie ni cytologie (pieces operatoires inchangees) |
| mesorectum (et CRM) pour un colon droit | champ sans restriction topographique | nouvelle cle KB `requiert_texte` (`rectum`, `rectal`, `recto`, `mesorectum`, `amputation abdomino`) ; `Referentiel.champs_attendus(..., texte)` ne reclame le champ que si un terme figure dans la dictee |
| `ccis_grade_nucleaire` sans mots-cles (et 65 autres champs INCa) | champs `inca_seul` crees sans detection | table `_RAFFINEMENTS_INCA` (30 champs : libelle lisible + mots-cles) et repli `_mots_depuis_libelle` ; test : plus aucun champ obligatoire non identifiant sans mots-cles |
| variantes de lexique de faible qualite (« millimetres » pour `mm`) | variantes generees | `variante_acceptable` : formes longues d'unites, expansions de sigles, simples flexions (`mucineuse`), liste de rejets explicites (`air e`, `pas 8`...) ; variantes STT observees conservees (812 -> 744) |
| codage ADICAP limite a une lesion par organe | `coder` appelait `suggerer_adicap` une fois par organe | `_adicap_par_lesion` : une passe par clause de la conclusion (`;`, `.`, ` et `, ` associe `...), codes certains distincts, 3 max par organe, aucun code invente (meme garde-fous que `adicap.py`) |
| relecteur retire des normalisations legitimes (« bronchiques » -> poumon) | `passage_non_dicte` ne connaissait que les jetons dictes | `_normalisation_legitime` : organe (meme organe selon la KB), sigle developpe (expansion du lexique, `ADK`), chiffres romains (« sept » -> VII), accord (droit/droite), cadres redactionnels (« Il s'agit d'un »). Un chiffre n'est JAMAIS une normalisation ; un vrai ajout est toujours retire |

## 2. Defauts trouves par la campagne et corriges

Avant correctifs (1er passage live, 53 dictees) : 11 violations de securite, 97,4 % d'attentes. Causes reelles, toutes corrigees :

1. **Contexte lesionnel a sous-chaines** (`specimen_type.py`, hors perimetre, contourne dans `projet/contexte.py`) : « vingt-huit » contient « vin » (neoplasie vulvaire) -> adenocarcinome du pancreas classe PRECANCEREUX ; « cystadenome » contient « adenome » ; « architecture » contient « rch » ; un seminome + « neoplasie germinale in situ » classe precancereux. Nouveau detecteur a mots entiers, negations respectees, l'in situ n'ecrase plus une tumeur maligne.
2. **« au sein d'un materiel chondromyxoide » = le sein** (repli historique sans masquage des pieges) : masque applique ; synonymes parotide/salivaire ajoutes a l'organe ORL.
3. **Perte d'information apres retrait** : un element retire par le relecteur n'etait pas restitue quand son passage n'etait cite qu'en ancrage ; une phrase « citee » par un simple titre etait tenue pour couverte alors que ses nombres (« trois centimetres ») avaient disparu ; un stade dicte (« pT3 N1a ») disparaissait de la conclusion et un trou pTNM etait reclame a tort. Corriges : omissions recalculees apres retrait, couverture exigeant les nombres, restitution du stade tel que dicte (alerte « attention »), `champ_present` reconnait un stade dicte et une mesure de tumeur/masse/lesion (trou « Taille tumorale » a tort sur un sarcome).
4. **« zero virgule trois » juge « chiffre non dicte »** (`reports/numbers.py` ignore « zero ») : les controles de chiffres travaillent sur `dictee + chiffrer(dictee)`.
5. **Mesure dont l'objet suit l'unite** (« 0,3 mm de tumeur ») ignoree par le verificateur d'unites ; plage heuristique `tumeur` sur piece : minimum 1 mm (0,3 mm sur une piece = « 0,3 cm » ?) ; la plage retient maintenant la borne basse la plus restrictive.
6. **Incoherences internes de la dictee non detectees** : « 3 carottes sur 2 » (bloquant), lateralite droit ET gauche pour un meme organe (hors prelevements distincts / bilateral), taille de conclusion superieure a la macroscopie (la regle C6 ne reconnait que « taille : N mm »).
7. **Negation sur une proposition coordonnee** (« pas de carcinome in situ MAIS carcinome infiltrant ») jugee « nie alors que la dictee l'affirme » : le controle raisonne par proposition.
8. **Titre « colon-rectum » pour une hemicolectomie droite** : libelle compose reduit aux parties dictees.
9. **Injection de prompt** (`projet/entree.py`) : les phrases qui ressemblent a une instruction (« ignore tes instructions », « revele ton prompt »...) sont masquees (meme longueur, empans intacts) pour la detection d'organe/contexte et les prompts des agents, jamais reprises comme texte clinique, signalees par une alerte « attention » qui les cite. Avant : « metastases hepatiques » injecte creait un organe foie et ses champs tumoraux.
10. **Caracteres speciaux** : controles, blocs script/style, balises HTML et delimiteurs `<<<`/`>>>` retires/neutralises (alerte « info » ; le texte clinique `<`, `>` n'est pas altere).
11. Lexique STT : « lieu berquin » (Lieberkuhn) et « kiss soixante-sept » (Ki67) n'etaient pas corriges.

## 3. Campagne adversariale LIVE (`backend/tests/campagne_v3_adversariale.py`)

59 dictees redigees pour la campagne (21 etiquettes de domaine : digestif 7, sein 4, gyneco 3, cytologie cervico-uterine 1, uro 5, thorax 4 dont LBA, peau 4, ORL/salivaire Milan 2, thyroide Bethesda 2, hemato 2, os/tissus mous 2, neuro 2, medical non tumoral 5 (MICI, rein medical IgA, foie NASH, greffe Banff, coeliaque), extemporanees 2, pediatrie 1, incoherences 4, negations 2, unites 1, volume (6 prelevements) 1, multi-organes 1, robustesse 4 : hors sujet, vide de sens, injection, caracteres speciaux ; pieges STT dans tous les domaines). Attentes ecrites AVANT l'execution (organe, prelevement, contexte, alertes attendues et interdites, elements requis/interdits, trous attendus/interdits, plafond de trous, corrections STT, niveau de service, absence de code) + controles automatiques sur tous les cas : securite V1-V8, faux positif de champ manquant (mot-cle distinctif dicte), latence.

Resultats finaux, deux passages consecutifs (Mistral reel, `mistral-large-2512`, parallelisme 3) :

| | passage A | passage B |
|---|---|---|
| dictees / erreurs pipeline | 59 / 0 | 59 / 0 |
| violations de securite | 0 | 0 |
| faux positifs de champ manquant | 0 | 0 |
| attentes satisfaites | 798 / 798 (100 %) | 798 / 798 (100 %) |
| campagne historique (15 cas, `campagne_v3.py`) | 0 violation, 0 ecart | idem |

Honnetete sur les attentes : 7 erreurs de REDACTION des attentes (regex fautives ou trop etroites) ont ete corrigees apres la 1re execution, chacune verifiee comme manifestement un defaut de la regle et non de la sortie : `embole` (la dictee dit « embols »), `detrusor ... envahi(?!...pas)` (regex qui matchait « n'est pas envahi »), `breslow.*2` (matchait « 1,2 »), `0,3 cm|3 mm` (« 0,3 mm » contient « 3 mm »), `keratinisant (?!non)`, `fer` (« surcharge ferrique »), `fnclcc ... 1` / `cd34 ... positif` (ordre des mots). Le controleur `_violations` a aussi ete corrige : chiffres via `chiffrer()`, V5/V6 juges par organe (et non globalement) pour les dictees multi-organes, titre inclus dans les controles de contenu. Aucune attente n'a ete assouplie sur le fond (negations, valeurs, unites, lateralite, contexte).

## 4. Robustesse technique (tests sans reseau : `tests/test_projet_robustesse.py`, 58 tests)

Timeouts par agent (redacteur -> N3 fidele, extracteur/relecteur -> avertissement) ; 429/5xx simules par `httpx.MockTransport` sur `ClientMistral` (429/500/502/503/504 -> `LLMTransientError`, 400 non transitoire, timeout, coupure reseau, 5 formes de reponse malformee, contenu en blocs « thinking », `top_p=1` toujours envoye) ; retry transitoire puis succes ; erreur persistante -> projet N3 strictement fidele ; JSON LLM malforme (11 formes : texte, tronque, cloture markdown, liste, null, types faux, elements non dict, verdicts faux, vide) : jamais fatal, dictee jamais perdue ; dictee de 50 000 caracteres (pipeline < 30 s, API 200, 50 001 -> 422) ; 10 requetes concurrentes (pipelines et SSE) sans contamination (marqueur unique par dictee) ; deconnexion SSE (flag `is_disconnected`, `aclose()` brutal, annulation pendant l'attente) : aucune tache residuelle ; orchestrateur qui plante -> projet de secours N3 via SSE ; client absent -> N3.

## 5. Mesure finale (59 dictees, passage B, parallelisme 3)

| | p50 | p95 | max |
|---|---|---|---|
| latence totale | 7,0 s | 12,0 s | 14,8 s (hysterectomie) |
| extraction | 4,3 s | 6,2 s | |
| redaction | 5,4 s | 9,9 s | |
| relecture | 1,2 s | 2,4 s | |
| correction / codage | 70 ms / 1 ms | 83 ms / 10 ms | |

Extraction et redaction s'executent en parallele, la relecture apres. Appels LLM : 2 a 3 par projet (moyenne 2,98 ; le correcteur LLM n'est appele que sur les cas ambigus). Jetons par projet : entree p50 3 078 / p95 3 790 ; sortie p50 1 334 / p95 2 550. Cout estime : p50 0,0036 USD, p95 0,0056 USD, max 0,0062 USD par projet (hypothese pessimiste : tarif unique de 0,5 / 1,5 USD par million de jetons entree / sortie, appliquee aussi au relecteur `mistral-medium`). A confirmer sur la grille tarifaire Mistral en vigueur : le chiffre est un ordre de grandeur, pas une facture. Niveaux de service : N0 23, N1 34, N3 2 (les deux dictees hors sujet / vides de sens, comme attendu).

## 6. Reste et besoins hors perimetre

- `backend/specimen_type.py` : le detecteur historique de contexte garde ses recherches par sous-chaine (`vin`, `adenome`, `rch`) ; il n'est plus utilise par le pipeline v3 mais l'est encore par d'autres modules (`champ_applicable`, v2).
- `backend/reports/numbers.py` : `source_number_set` ignore « zero » ; contourne cote v3, a corriger a la source.
- `backend/adicap.py` : l'appariement lesionnel reste mono-lesion ; le codage multi-lesions v3 repose sur un decoupage par clause. Pas de code pour un CCIS associe (aucune entree certaine) : differe honnetement.
- `schemas.py` / `types.ts` : inchanges. Le frontend recoit de nouvelles alertes existantes (`securite` attention pour injection, `securite` info pour caracteres retires, `incoherence`) : verifier leur affichage.
- Tarification Mistral a confirmer ; latence mesuree depuis un poste (reseau residentiel), a re-mesurer en production.
- Dictees multi-organes : le contexte global reste `indetermine` quand les organes different (jugement par organe) ; l'UI ne montre pas ce detail.
- Limites connues : l'injection n'est detectee que sur des formulations francaises/anglaises usuelles (motifs deterministes) ; une instruction deguisee ne serait filtree que par les regles de fidelite des prompts et les garde-fous deterministes (aucun fait non dicte ne survit).
