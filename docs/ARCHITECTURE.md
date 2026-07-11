# Architecture du backend IrisMARC

Outil d'**assistance à la rédaction** de comptes-rendus anatomopathologiques
(dictée → CR structuré). Ce n'est **pas** un dispositif médical : il structure,
formate et pointe les manques, sans poser de diagnostic. Objectif : gain de temps,
moins de manipulations, moins d'oublis, fidélité à la dictée.

## Vue d'ensemble du pipeline

```
audio ──▶ [Transcription STT]  ──▶ transcript ──▶ [Génération]  ──▶ CR structuré
          (Voxtral)              (éditable)        (Mistral + template
                                                    + guardrails)
```

Deux étapes exposées séparément (`/transcribe` puis `/format`) pour permettre
l'édition du transcript avant génération, et l'itération (`/iterate`).

## Couches (packages backend)

| Package | Rôle | Dépend de |
|---|---|---|
| `llm/` | Abstraction fournisseur LLM (Mistral, Anthropic). Types `LLMRequest/Response`, `LLMProvider`, factory. | — |
| `templates_cr/` | Catalogue de templates métier (structure CR + formulations + slots + `gilbert_template_id`). Sélection organe×prélèvement. | — |
| `reports/` | Moteur de CR : `ReportEngine` (local / gilbert), prompts, guardrails, retry, garde-chiffres. | `llm/`, `templates_cr/` |
| routes (`main.py`, `routes_*.py`) | API FastAPI. Ne dépend que de `ReportEngine`. | `reports/` |
| Codification (`adicap.py`, `snomed.py`, `detection_manquantes.py`, `specimen_type.py`, `templates_organes.py`) | ADICAP / SNOMED / complétude INCa / détection manques. | `text_utils` |

### Deux abstractions clés

1. **`LLMProvider`** (`llm/base.py`) — isole du SDK de génération.
   Fournisseur actif = `LLM_PROVIDER` (défaut `mistral`, souverain). Bascule sans
   toucher au métier.

2. **`ReportEngine`** (`reports/engine.py`) — isole du *mode* de génération.
   Moteur actif = `REPORT_ENGINE` (défaut `local`). `local` = Voxtral + LLM ;
   `gilbert` = moteur distant Lexia (cf. `INTEGRATION_GILBERT.md`).

## Système de templates (slot-filling)

Un `ReportTemplate` décrit la structure imposée d'un CR, les **zones variables**
(slots) à remplir depuis la dictée, et des **formulations standardisées** à
réutiliser. Il est injecté dans le prompt système : le LLM ne remplit que les
zones variables, ce qui homogénéise les sorties et limite les hallucinations.
Le même template porte un `gilbert_template_id` pour le moteur distant → un seul
catalogue logique sert les deux moteurs.

Sélection : `preselect()` (avant LLM, par mots-clés d'organe + type de prélèvement)
puis l'organe réel est confirmé par le LLM. Repli sur le template `generic`.

## Guardrails (fidélité / anti-hallucination)

Appliqués à **toute** sortie (locale ou distante) par `build_validated_report` :

- **Parsing JSON robuste** (tolère fences/texte parasite).
- **Garde-chiffres** : toute mesure/compte/pourcentage du CR absent de la dictée
  est signalé (`reports/numbers.py` normalise les nombres parlés → chiffres, ex.
  « cinq millimètres » = « 5 »). C'est le garde-fou central de fidélité.
- **Garde-négations** : ne jamais inverser une négation ; surface les `[VERIFIER]`
  et l'ambiguïté « pas de cellule normale ».
- **Périmètre biopsie** : pas de pTNM/marges/curage sur une biopsie.
- **Conclusion** : pas de `[A COMPLETER]` en conclusion.

Les risques deviennent des `warnings` (revue humaine) ; le pathologiste valide.

## Résilience

- Retry+backoff sur erreurs LLM transitoires (`reports/retry.py`).
- Timeouts configurables (`LLM_TIMEOUT_SECONDS`, `STT_TIMEOUT_SECONDS`).
- Erreurs traduites en codes HTTP adaptés (429 quota, 502 moteur, 504 timeout).

## Tests

- Suite déterministe (sans réseau) : `backend/tests/` — `pytest` (59 tests).
  Couvre nombres, guardrails, templates, LLM/factory/retry, moteur, API, codification.
- Campagne fonctionnelle live : `backend/tests/functional_campaign.py`
  (Voxtral + Mistral sur les 5 dictées de référence, hors suite pytest).

## Configuration (variables d'environnement)

Voir `.env.example`. Principales : `LLM_PROVIDER`, `MISTRAL_API_KEY`, `MISTRAL_MODEL`,
`REPORT_ENGINE`, `VOXTRAL_API_KEY`, `JWT_SECRET`, `DATABASE_URL`.
