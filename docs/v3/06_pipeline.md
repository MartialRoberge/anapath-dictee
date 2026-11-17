# MARC v3 : pipeline agentique explicable (agent PIPELINE)

Code : `backend/projet/` (hors `kb.py` et `schemas.py`, contrat partagé, non modifiés).
Tests : `backend/tests/test_projet_*.py` (sans réseau). Campagne live : `backend/tests/campagne_v3.py`.

La dictée devient un **projet** de compte rendu, au contrat `schemas.Projet` : éléments identifiés (phrase, titre, liste, trou) avec sources et confiance, alertes, codes, corrections phonétiques et trace réelle des agents. Rien n'est persisté : la dictée, l'audio et le projet ne vivent qu'en mémoire, le temps de la requête.

## 1. Graphe des agents

```
audio? ─▶ Transcripteur (Voxtral, transcription.py)
           │
dictée ───▶ Correcteur phonétique ── déterministe (lexique KB + variantes observées, clé phonétique,
           │                         distance d'édition) ; Mistral small seulement pour les cas ambigus
           ▼
        Contexte (orchestrateur, déterministe) : organes (KB), prélèvement, contexte lésionnel,
           │  champs obligatoires (KB × filtre de sécurité), gabarit, exemples de style
           ▼
   ┌── Extracteur (large, JSON) ──┐   en parallèle (asyncio.gather)
   └── Rédacteur  (large, JSON) ──┘   ─▶ événement SSE « partial »
           │  réconciliation du contexte (citations vérifiées de l'extracteur)
           ▼
   ┌ Vérif. unités ┬ Vérif. cohérence ┬ Vérif. complétude ┬ Vérif. sécurité ┬ Relecteur (medium) ┐  gather
           ▼
        Application des décisions (réparations, retraits, restitutions, trous)
           ▼
        Codeur (ADICAP déterministe + SNOMED CT suggestion) ─▶ Assemblage (niveau de service, métriques)
```

Chaque nœud émet une `TraceStep` réelle (`en_cours` puis `ok`, `avertissement`, `erreur` ou `saute`) avec `debut_ms`, `duree_ms`, `modele`, `resume` et `details`. Le flux SSE relaie ces étapes au moment où elles changent d'état.

| Fichier | Rôle |
|---|---|
| `orchestrateur.py` | `Pipeline.executer()` / `Pipeline.iterer()`, repli, niveaux de service, `projet_de_secours()` |
| `correcteur.py` | 3 passes (variantes connues, proximité, arbitrage LLM), offsets exacts, `appliquer_corrections` |
| `extracteur.py` | appel LLM + **rejet de tout fait dont la citation n'est pas retrouvée mot pour mot** |
| `redacteur.py` | appel LLM, localisation des citations, nettoyage markdown, trous, `projet_minimal` (N3) |
| `relecteur.py` | verdicts LLM croisés avec l'ancrage déterministe (`etude/ancrage.py`) |
| `verificateurs.py` | unités, cohérence (C1-C14 + latéralité + ganglions), complétude, sécurité, omissions |
| `codeur.py` | `adicap.py` (certain/partiel, jamais de lésion inventée) + `snomed.py` (suggestion) |
| `confiance.py` | calcul explicable de la confiance |
| `referentiel.py` | façade KB avec repli sur les référentiels historiques, filtre de sécurité des champs |
| `mesures.py`, `textes.py`, `rendu.py` | mesures dictées (chiffres et lettres), localisation de citations, rendus texte |
| `llm_client.py`, `trace.py` | client Mistral (retry, délai, compteurs), traceur |
| `routes.py`, `export_docx.py` | API `/v3`, export Word |

## 2. Modèles

| Agent | Modèle | Pourquoi |
|---|---|---|
| Correcteur (cas ambigus) | `mistral-small-latest` | rapide, appelé rarement (0 appel sur 20 cas live) |
| Extracteur | `mistral-large-2512` | JSON strict, citations |
| Rédacteur | `mistral-large-2512` | qualité rédactionnelle |
| Relecteur | `mistral-medium-latest` | **modèle différent** du rédacteur (diversité), ~1,3 s |
| Transcripteur | `voxtral-mini-latest` (via `transcription.py`) | existant |

Depuis novembre 2026, l'alias `mistral-large-latest` pointe vers `mistral-large-4`. C'est un modèle à **raisonnement** : il renvoie des blocs « thinking », il est plus lent, et il refuse `temperature=0` sans `top_p=1` (erreur 400). Le pipeline épingle donc `mistral-large-2512`, le dernier large sans raisonnement. `llm_client.ClientMistral` envoie `top_p=1` et sait lire un contenu en blocs.

## 3. Prompts (`projet/prompts.py`)

Ils partagent un socle de règles de fidélité :
- aucun fait, chiffre, morphologie, grade, stade, latéralité ou négation non dicté ;
- aucune conversion d'unité, aucun recalcul ;
- un manque reste un manque ;
- jamais de champ tumoral sur une lésion bénigne ;
- pas de markdown.

Le modèle **recopie des citations** et ne donne jamais d'offsets : c'est le code qui calcule les empans.

- **Extracteur** : `organes` (uniquement les organes *prélevés*, pas ceux cités comme repère), `prelevement`, `contexte_lesionnel` et `faits` atomiques. Chaque élément porte une citation et un `champ_id` (même quand le champ est exprimé en d'autres termes). Au plus 30 faits. Les mesures sont repérées de façon déterministe.
- **Rédacteur** : titre « EXAMEN ANATOMOPATHOLOGIQUE DE … ». Il utilise uniquement les sections du gabarit KB et produit un élément `titre` par prélèvement et une `liste` IHC. Les exemples de style KB, verrouillés par organe, ne règlent que la forme. Il insère les trous à partir de la liste fournie (rien d'autre). Il s'en tient à la proportionnalité et n'écrit jamais « non précisé ». En mode itération, il conserve les `id` existants, et un trou comblé garde son `id`.
- **Relecteur** : un verdict par élément (`fidele`, `ajout`, `contresens`, `doute`), avec le passage fautif. Il ne réécrit jamais rien.

## 4. Garde-fous déterministes (appliqués après les LLM)

| Contrôle | Effet |
|---|---|
| Citation de fait introuvable (extracteur) | fait rejeté, compté dans la trace |
| Trou pour un champ non demandé | ignoré (aucun trou inventé) |
| Chiffre porteur ou nombre isolé non dicté (`numbers.py`), ex. « Gleason 3+4 = 7 » | élément **retiré**, alerte sécurité bloquante |
| pTNM non dicté | retrait |
| Négation inversée sur une constatation (emboles, engainements, métastase…) via `negation.py` | retrait |
| Marges évoquées sur une biopsie sans être dictées | retrait |
| Unité changée ou convertie (« 25 mm » écrit pour « 25 cm » dicté) | **mesure dictée rétablie** et alerte |
| Unité ajoutée à des dimensions dictées sans unité | retrait, plus l'alerte « unité à préciser » |
| Latéralité changée | retrait |
| Relecteur « ajout »/« contresens », passage absent de la dictée | retrait ; sinon élément conservé, confiance basse, alerte « à vérifier » |
| Élément retiré | sa citation exacte est **restituée mot pour mot** (rien n'est perdu) |
| Phrase dictée reprise par aucun élément (omission) | ajoutée telle quelle, alerte |
| Markdown résiduel | nettoyé |

Ces contrôles sont rejoués de façon indépendante par la campagne live (`_violations`), qui exige zéro violation.

## 5. Vérificateurs (parallèles)

- **Unités** : les mesures (chiffres ou lettres, axes « 25 x 18 x 10 mm », « 18, 17, 14 mm ») sont comparées à une plage plausible. Le pipeline retient la plus restrictive entre la plage KB (`plage_mesure`) et l'heuristique par classe de prélèvement. Exemple : « tumeur de 25 cm » sur biopsie, plage 0,2 à 50 mm, donne la suggestion « 25 mm ». La valeur n'est **jamais corrigée sans le pathologiste**.
- **Cohérence** : règles `coherence_document.py` C1-C7 et C10-C14, appliquées sur un rendu où les nombres en lettres sont chiffrés. C8, C9, C15 et C16 relèvent de la complétude et sont écartés (faux positifs mesurés sur un ganglion sentinelle). S'y ajoutent la latéralité dictée/projet et un contrôle « ganglions envahis ≤ examinés » quand les deux nombres sont dans des phrases séparées.
- **Complétude** : `kb.champs` (organe × prélèvement × contexte). Pour une dictée multi-organes, le contexte est calculé **par organe**, sur son segment. Le filtre de sécurité exclut :
  - tout champ tumoral sur une lésion bénigne ou indéterminée ;
  - tout champ d'infiltrant sur une lésion précancéreuse ;
  - pTNM, marges et ganglions hors pièce opératoire ;
  - les champs conditionnels non évaluables ;
  - les champs dépendant d'une entité non dictée (grade du CCIS, mésorectum…).

  Règle du **zéro faux positif** : un champ est réputé présent s'il existe un fait extrait rattaché, un mot-clé KB non générique, `filter_present_alertes`, ou une racine morphologique (type histologique). Dans le doute, rien n'est réclamé.
- **Sécurité** : voir le tableau du §4.

## 6. Confiance (`confiance.py`)

Elle se calcule comme une somme de facteurs nommés, restitués dans `Element.explication`. Le niveau s'obtient par `niveau_de()`.

| Facteur | Valeur |
|---|---|
| Ancrage : citation mot pour mot / recouvrement / aucun | 0,90 / 0,75 / 0,35 |
| Statut : dicté / normalisé / reformulé | +0,03 / 0 / −0,03 |
| Relecteur : fidèle / doute / ajout-contresens conservé / indisponible | +0,06 / −0,15 / −0,30 / −0,05 |
| Correction phonétique dans l'empan | −(1 − c) × 0,5 |
| Source KB de fiabilité C / D | −0,02 / −0,05 |

Cas particuliers :
- **trou** : confiance de la source d'exigence (`prov.confiance`, abaissée si `a_valider` ou `derive_auto`) ;
- **passage restitué** : 0,70.

Exemple d'explication : « Confiance haute : citation retrouvée mot pour mot dans la dictée ; relecteur : fidèle (+0,06). »

## 7. Niveaux de service et repli

| Niveau | Condition |
|---|---|
| N0 | organe + gabarit KB + exemples de style + ADICAP certain, aucun repli |
| N1 | un repli (champs historiques, pas d'exemple, ADICAP partiel…) |
| N2 | pas de gabarit d'organe (gabarit standard ACP) |
| N3 | organe non reconnu ou rédacteur indisponible : `projet_minimal`, phrases dictées reprises telles quelles, alerte « mode dégradé » |

Aucune étape ne bloque. Le comportement dépend de ce qui échoue :
- **LLM en erreur ou hors délai** (délais : correcteur 8 s, extracteur 25 s, rédacteur 35 s, relecteur 20 s ; retry transitoire via `reports/retry.py`) : l'étape passe en `avertissement` ou `erreur` et la suite continue ;
- **KB vide** : référentiels historiques (`templates_organes.py`, `reports/knowledge.py`, lexique intégré) ;
- **exception imprévue** : `projet_de_secours()`, un projet N3 fidèle.

La seule erreur sans projet est une transcription audio impossible (événement SSE `error`).

## 8. API (`/v3`, authentification `get_current_user`)

| Route | Entrée | Sortie |
|---|---|---|
| `POST /v3/projets` | `{dictee}` | SSE `step`*, `partial`, `projet` (une fois) ; `error` si aucun projet possible ; `?stream=false` renvoie le `Projet` JSON |
| `POST /v3/projets/audio` | multipart `audio` | idem, avec l'étape Transcripteur (audio jamais écrit) |
| `POST /v3/projets/iterer` | `IterationRequest` | idem. La dictée complémentaire est concaténée (offsets préservés) ; ids conservés ; un trou comblé garde son id ; un élément omis par le rédacteur est conservé |
| `POST /v3/projets/export/docx` | `Projet` | .docx Arial 10, sans markdown, trous rendus `[A COMPLETER : libellé]` en rouge |
| `GET /v3/kb/sources/{id}` | id | entrée du registre KB, ou source interne MARC (`src:marc_*`) |

`contexte.prelevement` prend les classes KB : `biopsie`, `piece_operatoire`, `cytologie`, `curage` ou `null` si le prélèvement n'est pas dicté.

## 9. Latences mesurées (campagne live du 15/11/2026, Mistral réel, KB réelle)

Le jeu comprend 20 cas : 14 dictées rédigées, 1 itération, et 5 audios du corpus (Voxtral puis pipeline). Chaque cas fait 3 appels LLM ; l'arbitrage phonétique n'a jamais été nécessaire. **0 violation de sécurité, 0 écart aux attentes.**

| Mesure | Valeur |
|---|---|
| Durée totale, dictées texte | médiane **6,6 s**, moyenne 7,3 s, max 12,6 s (tumorectomie avec IHC complète) |
| Audio (transcription incluse) | 5,8 à 11,3 s ; lobectomie avec curage détaillé : 18,3 s |
| Correcteur (déterministe) | médiane 85 ms |
| Extracteur ∥ rédacteur | médianes 5,6 s ∥ 5,5 s (max 13 s) |
| Relecteur | médiane 1,3 s |
| Vérificateurs, codeur | < 20 ms chacun |
| Jetons par projet | ~3 000 à 4 500 en entrée, ~800 à 4 100 en sortie |

Pour relancer : `cd backend && ../venv/bin/python tests/campagne_v3.py --sortie /chemin/hors/depot.json`. Les options `--cas a,b` et `--sans-audio` restreignent le jeu.

## 10. Limites connues

- Le contexte par organe repose sur un découpage de la dictée à la première mention de chaque organe ; un organe cité seulement comme repère est écarté (motif « ganglions para-œsophagiens », « sous la plèvre ») et l'extracteur confirme les organes prélevés.
- ADICAP : un code par organe ; pour plusieurs lésions d'un même organe (canal anal : condylome IN1 + hyperplasie), une seule est codée.
- Le relecteur est strict sur les inférences (« pulmonaire » déduit de « bronchique » est retiré). Le passage dicté est alors restitué, sans perte.
- Les exigences dépendent de la KB : par exemple, « Emboles vasculaires » est réclamé sur des biopsies pulmonaires et prostatiques. Ce point est à arbitrer avec la pathologiste.
