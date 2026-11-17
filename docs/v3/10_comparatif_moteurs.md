# 10 - Comparatif ancien moteur / nouveau moteur (mesure live)

Date de la mesure : 17/11/2026. Branche `projet-v3`, rien de committe. Mistral reel.
Script reproductible : `backend/tests/comparatif_moteurs.py`.
Sorties brutes (elles contiennent les dictees de test, synthetiques) : HORS depot,
`/private/tmp/claude-501/-Users-martialroberge--claude-spares-spare-UjL0l3/a173d645-1c38-4b98-9c3e-c3da3d91cce9/scratchpad/brut.json` et `brut2.json`.

```
cd backend
../venv/bin/python tests/comparatif_moteurs.py --executer --parallele 3 --isole 10 --sortie /chemin/hors/depot/brut.json
../venv/bin/python tests/comparatif_moteurs.py --executer --cas manq_sein_biopsie,manq_colon_piece,manq_prostate_biopsie,manq_melanome,manq_thyroide_piece,manq_poumon_biopsie --sortie /chemin/hors/depot/brut2.json
../venv/bin/python tests/comparatif_moteurs.py --analyser /chemin/brut.json,/chemin/brut2.json
```

## 0. Ce qui est compare

| | Ancien | Nouveau |
|---|---|---|
| Code | `reports/` : `MultiPassReportEngine.generate()` (REPORT_ENGINE=multipass, college actif) + `reports.panel.build_panel()` + `adicap.suggerer_adicap()` : ce que le front historique obtient avec `/format` puis `/adicap` | `projet/orchestrateur.Pipeline.executer(dictee=...)` : le meme code que `POST /v3/projets?stream=false` (le serveur HTTP n'est pas lance : mesure en Python) |
| Modeles | mistral-large-2512 partout | large-2512 (extraction, redaction), medium (relecture), deterministe pour le reste |
| Appels LLM / dictee | 6 en general (3 a 8) : comprehension, redaction, relecture, 3 lentilles du college | 3 (2 a 3) |

Jeu de test : 67 dictees, les memes dans les deux moteurs, une execution chacune (aucune repetition).
- 59 de `campagne_v3_adversariale.py` (21 domaines, pieges phonetiques, mm/cm, negations, incoherences, robustesse) ;
- 2 de `campagne_v3.py` (phonetique STT, ganglions incoherents) ;
- 6 ajoutees ici (domaine `manquants`) : dictees ou des champs obligatoires INCa sont omis a dessein, car le jeu existant ne contient aucune attente de « trou attendu » et ne permet donc pas de mesurer le rappel des manquants. Leurs attentes ont ete ecrites avant execution. Deux motifs ont ete elargis ensuite pour une erreur de vocabulaire de ma part (`mitot` en plus de `mitos`, `tranche` en plus de `marge`) : le resultat des deux moteurs ne change pas selon le moteur ;
- les 59 + 2 + 6 depassent un peu la « cinquantaine » prevue : 134 generations au total, plus 20 rejeux sequentiels pour la latence sans contention.

Les exemples audio de `Ressources/2. CR avec audio` ne sont pas utilises : ce sont des CR et de l'audio, pas des dictees ecrites avec attentes.

## 1. Tableau synthetique

| Mesure | Ancien | Nouveau | Lecture |
|---|---|---|---|
| Latence p50 / p95 (3 dictees en parallele) | 21,0 s / 32,0 s (max 38,7 s) | 8,0 s / 14,5 s (max 19,5 s) | nouveau ~2,6 fois plus rapide |
| Latence p50 / p95, 10 dictees rejouees une par une | 19,4 s / 34,8 s | 8,8 s / 18,3 s | meme ordre |
| Appels LLM par dictee (moyenne) | 5,9 | 3,0 | |
| Jetons par dictee (entree / sortie) | 6 756 / 1 913 | 3 281 / 1 413 | |
| Cout indicatif par dictee* | 0,0062 USD | 0,0038 USD | -40 % |
| Erreurs / timeouts / sorties vides | 1 / 0 / 0 | 0 / 0 / 0 | ancien : `GenerationParseError` sur la dictee « vide de sens » (502 cote API) |
| Attentes ecrites d'avance tenues (total) | 667 / 695 (96,0 %) | 699 / 702 (99,6 %) | voir biais en section 4 |
| Fidelite : attentes `requis` + `interdit` | 363 / 369 | 375 / 375 | l'ancien perd 4 informations dictees |
| Controle deterministe : chiffres, stades non dictes | 11 signalements dans 7 dictees (4 additions cliniques, 4 annees de classification, 2 faux positifs du controle) | 0 | |
| Mesures dictees retrouvees dans le CR | 51 / 52 | 52 / 52 | l'ancien : 15 cm devenu 15 mm |
| Negations dictees conservees | 46 conservees, 1 perdue reellement | 49 conservees, 0 perdue | apres tri manuel (section 3) |
| Alertes mm/cm attendues detectees | 3 / 3 | 3 / 3 | meme resultat ; l'ancien n'a pas empeche la conversion silencieuse dans le CR |
| Incoherences attendues detectees | 5 / 5 | 5 / 5 | |
| Champs obligatoires manquants : rappel (6 dictees, 16 champs) | 16 / 16 | 14 / 16 | **point ou l'ancien est meilleur** : le nouveau ne demande ni la longueur tumorale (prostate) ni le panel IHC (poumon) |
| Champs reclames a tort (attentes `trou interdit`) | 7 / 130 | 0 / 130 | |
| « A completer » par dictee (moyenne) | 6,0 | 2,3 | l'ancien en pose beaucoup plus, dont des champs hors sujet |
| Cas a plafond de trous (« au plus N trous », surtout lesions benignes) respectes | 2 / 12 | 13 / 13 | |
| Corrections phonetiques attendues | 11 / 11 | 11 / 11 | l'ancien corrige sans les lister ; le nouveau en liste 13 avec decalage et confiance, dont 1 fausse (cf. section 5) |
| ADICAP : code propose | 65 / 66 | 65 / 67 | |
| ADICAP : organe juste (organe attendu connu) | 49 / 56 | 54 / 56 | |
| ADICAP : mode de prelevement juste | 29 / 33 | 28 / 33 | **l'ancien a 1 de plus** |
| ADICAP : lesion proposee, dont plausible** | 27 / 30 | 29 / 32 | difference non significative |
| Phrases du CR avec source dans la dictee | 168 / 202 (83 %) | 356 / 356 (100 %) | nouveau : 374 empans verifies sur 376 (2 ecarts d'espaces) ; ancien : assertions du college ayant un empan |
| Alertes avec raison chiffree | 89 / 363 (25 %) | 181 / 214 (85 %) | nouveau : 168 avec calcul explicite, 0 pour l'ancien |
| Alertes avec source de referentiel | 0 / 363 (5 mentions en texte libre) | 211 / 214 ; 326 references, 58 sources distinctes | |
| Elements a relire signales (hors trous), par dictee | 1,6 (+ 57 assertions soumises au college) | 1,9 | |
| Part des « a relire » confirmee par attente ou controle automatique | 16 / 106 (15 %) | 9 / 127 (7 %) | borne basse, voir ci-dessous |
| Part utile, echantillon aleatoire relu a la main (20 par moteur) | 12 / 20 | 6 / 20 | **point faible du nouveau** |

\* Tarif unique 0,5 / 1,5 USD par million de jetons (entree / sortie), identique pour les deux moteurs, comme dans `campagne_v3_adversariale.py` ; le nouveau utilise en fait aussi des modeles moins chers (medium), donc l'ecart reel est probablement plus grand. Estimation d'ordre de grandeur.
\*\* « Plausible » = les mots du libelle de lesion figurent dans la dictee. Pas de verite terrain ADICAP independante : la justesse n'est verifiee que sur l'organe et le prelevement attendus par les cas.

## 2. Detail par domaine

Attentes ecrites d'avance satisfaites / attentes du domaine (organe, prelevement, contexte, requis, interdits, alertes, trous, corrections).

| Domaine | Dictees | Ancien | Nouveau |
|---|---|---|---|
| digestif | 7 | 77 / 80 | 80 / 80 |
| sein | 4 | 47 / 47 | 47 / 47 |
| gyneco | 3 | 36 / 38 | 38 / 38 |
| cytologie | 1 | 11 / 11 | 11 / 11 |
| uro | 5 | 51 / 53 | 53 / 53 |
| thorax | 4 | 50 / 50 | 50 / 50 |
| peau | 4 | 45 / 51 | 51 / 51 |
| orl | 2 | 25 / 26 | 26 / 26 |
| thyroide | 2 | 22 / 22 | 22 / 22 |
| hemato | 2 | 19 / 20 | 20 / 20 |
| os et tissus mous | 2 | 22 / 22 | 21 / 22 |
| neuro | 2 | 22 / 22 | 22 / 22 |
| medical (non tumoral) | 5 | 87 / 94 | 94 / 94 |
| extemporanee | 2 | 18 / 18 | 18 / 18 |
| pediatrie | 1 | 15 / 16 | 16 / 16 |
| incoherence | 5 | 20 / 20 | 20 / 20 |
| negation | 2 | 22 / 22 | 22 / 22 |
| volume | 1 | 15 / 15 | 15 / 15 |
| multi-organes | 1 | 11 / 12 | 12 / 12 |
| robustesse | 4 | 23 / 24 | 31 / 31 |
| unites | 1 | 6 / 9 | 9 / 9 |
| phonetique | 1 | 7 / 7 | 7 / 7 |
| manquants (ajoute) | 6 | 16 / 16 | 14 / 16 |

Ecarts du nouveau : `os_liposarcome` (contexte lesionnel `malin` attendu), prostate (longueur tumorale non reclamee), poumon (panel IHC non reclame).
Ecarts de l'ancien : moitie en « trous en trop » sur lesions benignes (gastrite, ovaire, naevus, medical : 5 a 9 champs a completer), le reste en informations dictees perdues (Clark IV, CD34 positif, 12 glomerules, 15 cm), organe non reconnu (ORL parotide, pediatrie, coeliaque), contexte lesionnel faux (testicule, ovaire) et un CR de « recette de cuisine » sur la dictee hors sujet.

## 3. Fiabilite des mesures de fidelite : tri manuel

Les 11 signalements du controle deterministe sur l'ancien ont ete relus un par un :
- 4 additions cliniques non dictees : « Gleason 3 + 4 = 7 » (somme ajoutee), « Stade pT1 » (vessie, jamais dicte), « pN0 » et « 0 ganglion envahi » (a partir de « aucun ganglion envahi sur douze examines ») ;
- 4 annees de classification ajoutees (OMS 2021 / 2022, Bethesda 2017, 2017) ;
- 2 faux positifs du controle (« 300 000 » ecrit avec espace) : le controle est a corriger ; le nouveau a le meme defaut, qui lui a fait retirer a tort la phrase de cellularite du LBA (reinseree telle quelle ensuite).

L'ancien signale lui-meme la plupart de ces ajouts dans ses avertissements (stade non dicte, « 0 ganglion » absent, NIFTP non demande), mais **les laisse dans le CR** ; le nouveau les retire avant sortie.
Negations : sur les 2 « perdues » et 1 « inversee » comptees automatiquement pour l'ancien, une seule est reelle (foie : « pas d'invasion vasculaire macroscopique » absente du CR) ; les deux autres sont des artefacts du controle (« micro-invasion » avec trait d'union, « 0 ganglion » pour « aucun ganglion »).
Mesures : une alteration chacun. Ancien : « quinze centimetres » devenu « 15 mm » dans le CR. Nouveau : « trente lymphocytes ... pour cent enterocytes » reformule en « trente pour cent enterocytes » (sens ambigu, signale par le controle comme valeur alteree).

## 4. Limites de la mesure

1. **Avantage au nouveau moteur.** Les attentes ecrites d'avance de `campagne_v3_adversariale.py` ont servi a corriger le nouveau pipeline (« on corrige le produit, pas l'attente »). L'ancien ne les a jamais vues. Les controles V2/V3 reprennent des garde-fous du nouveau moteur. Le score 99,6 % du nouveau n'est donc pas une mesure independante ; les 96,0 % de l'ancien sont une borne basse sur des dictees qu'il n'a pas ete regle pour passer. Les mesures qui ne dependent pas des attentes (latence, appels, jetons, couverture des sources, comptage des alertes) sont moins exposees a ce biais.
2. **Une seule execution par dictee.** A temperature 0 Mistral reste variable : sur `sein_biopsie_25cm`, un essai de test a donne « 25 mm » dans le CR ancien, le suivant « 25 cm ». Pas d'intervalle de confiance ; des ecarts d'une ou deux attentes ne sont pas significatifs.
3. **Latence mesuree avec 3 dictees en parallele**, puis une par une sur 10 dictees (les deux series concordent) ; elle depend de la charge de l'API Mistral ce jour-la. Le serveur HTTP n'est pas dans la boucle (pas de SSE, pas de base).
4. **Evaluateur commun, regle indulgente pour l'ancien.** Faute de structure, l'alerte attendue de l'ancien est cherchee dans tous ses signaux, tous types confondus ; ses « trous » sont les marqueurs `[A COMPLETER]` du CR plus le panneau de `build_panel`.
5. **« A relire » : precision mal mesurable.** Le jeu n'a des attentes que pour quelques alertes, d'ou la borne basse de 15 % / 7 %. L'echantillon relu a la main (graine 2026, 20 elements par moteur, par un seul relecteur, moi) donne 12 / 20 et 6 / 20 : subjectif, a recouper par un pathologiste. Dans le nouveau, les elements non utiles sont surtout des titres de section signales comme « ajout », des avertissements « la relecture par le second modele n'a pas eu lieu » (6 dictees sur 67), des negations jugees inversees a tort sur des dictees multi-prelevements, et des termes corriges simplement rappeles.
6. **Rappel des manquants** : 6 dictees, 16 champs. Petit echantillon.
7. **Explicabilite comptee, non jugee.** On compte des sources et des chiffres, pas leur pertinence. Pour l'ancien, la source est celle du college (assertions ayant un empan) ; le college n'a pas siege pour 3 dictees sur 66.
8. **Non mesure** : lisibilite et convention de redaction du CR, tenue de charge, audio/Voxtral, iteration, export Word. Constat qualitatif seulement : sur `piege_multi_organes_tumoral`, le CR nouveau est fragmente (« Il s'agit d'une gastrite chronique. / Sans Helicobacter. ») alors que l'ancien produit un CR classique par organe.
9. Les controles de justesse ADICAP ne portent que sur l'organe et le prelevement ; la lesion n'est verifiee que par recoupement lexical.

## 5. Trois exemples concrets (avant = ancien, apres = nouveau) et un contre-exemple

**A. Unite modifiee en silence** (`plus_fragment_15cm`). Dictee : « un fragment de quinze centimetres ».
- Avant : CR « Un fragment mesurant 15 mm. » ; la modification n'apparait que dans une note de relecture (« unite et valeur modifiees »).
- Apres : CR « Il s'agit d'un fragment de quinze centimetres. », alerte d'unite (« hors de la plage plausible 0,2 a 10 mm, confusion mm/cm possible ») et message « mesure retablie telle que dictee, aucune unite n'est convertie sans le pathologiste ».

**B. Stade invente** (`uro_vessie_rtuv`). Dictee : carcinome urothelial infiltrant le chorion, aucun stade.
- Avant : CR termine par « Stade pT1 (TNM 8e edition). » et « emboles lymphovasculaires » (« lymphovasculaires » non dicte). Un avertissement « stade non dicte » est emis, mais le texte reste.
- Apres : aucun stade ni qualificatif ajoute ; `pTNM` figure parmi les champs a completer.

**C. Dictee hors sujet ou vide** (`piege_hors_sujet`, `piege_vide_de_sens`). Dictee : recette de tarte ; puis bruit de parole sans contenu.
- Avant : titre « EXAMEN ANATOMOPATHOLOGIQUE D'UNE RECETTE DE CUISINE », sections macroscopie / preparation, 6 champs a completer ; pour le bruit, erreur `GenerationParseError` (502 cote API), pas de sortie.
- Apres : projet en mode degrade, dictee reprise telle quelle sans organe ni code, alerte « organe non reconnu » ; aucune exception.

**Contre-exemple (point faible du nouveau) : correction phonetique fausse** (`neuro_glioblastome`). Dictee : « prolifération endothélio-capillaire » (terme correct).
- Avant : « prolifération endothélio-capillaire », conserve.
- Apres : « endothélio-papillaire », correction a confiance 0,8 appliquee, signalee « verifier le terme ». Sur 13 corrections du nouveau, 1 fausse (celle-ci) et 1 discutable (« stéatohépatite » reecrit « Steato-hepatite »). Autre cas : sur `piege_multi_organes_tumoral`, le garde-fou retire « sans Helicobacter pylori » (« pylori » non dicte, « Helicobacter » l'etait) ; la dictee est reinseree telle quelle, au prix d'un CR moins lisible.

## 6. Reponse a la question du proprietaire

- **Plus performant ?** Oui sur la vitesse (2,6 fois), le nombre d'appels (moitie) et le cout (environ -40 %).
- **Comment ?** Un appel de redaction/extraction et une relecture au lieu de six passes dont un college de trois lentilles ; les controles de securite sont deterministes (chiffres, stades, negations, plages, arithmetique) et retirent avant sortie ce que l'ancien se contente de signaler.
- **Meilleur sur le fond ?** Sur ce jeu, oui pour la fidelite (zero ajout non dicte contre 4 additions cliniques et 1 negation perdue), les faux champs a completer (0 contre 7, 2,3 contre 6,0 par dictee), la robustesse sur dictees hors sujet et l'explicabilite structuree (100 % des phrases sourcees, calcul et referentiel dans les alertes). A temperer par le biais de la section 4.
- **Ou l'ancien est meilleur :** rappel des champs obligatoires manquants (16/16 contre 14/16, au prix de 6 champs a completer par dictee en moyenne), part utile des elements a relire (12/20 contre 6/20 sur echantillon manuel), une dictee de plus avec le bon mode de prelevement ADICAP, et lisibilite du CR sur dictees multi-organes.
