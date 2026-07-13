# Architecture du backend MARC

**MARC** (Module d'Assistance à la Rédaction des Comptes-rendus) est un outil
d'**assistance à la rédaction** de comptes-rendus anatomopathologiques
(dictée → CR structuré). Ce n'est **pas** un dispositif médical : il structure,
formate et pointe les manques, sans poser de diagnostic. Objectif : gain de temps,
moins de manipulations, moins d'oublis, fidélité à la dictée.

## Vue d'ensemble du pipeline

```
audio ──▶ [Transcription STT]  ──▶ transcript ──▶ [Génération]  ──▶ CR structuré
          (Voxtral)              (éditable)        (connaissances métier
                                                    + LLM + guardrails)
```

Deux étapes exposées séparément (`/transcribe` puis `/format`) pour permettre
l'édition du transcript avant génération, et l'itération (`/iterate`).

## Couches (packages backend)

| Package / module | Rôle | Dépend de |
|---|---|---|
| `llm/` | Abstraction fournisseur LLM (Mistral, Anthropic). Types `LLMRequest/Response`, `LLMProvider`, factory. | — |
| `reports/` | Moteur de CR : `ReportEngine` (local / gilbert), injection de connaissances (`knowledge.py`), prompts, guardrails, cohérence, retry. | `llm/`, codification |
| `templates_organes.py` | Catalogue métier des organes (`TemplateOrgane` / `ChampObligatoire`, `TOUS_LES_TEMPLATES` = **23 organes**). Modèles **Pydantic**. | — |
| Codification & complétude (`adicap.py`, `snomed.py`, `detection_manquantes.py`, `specimen_type.py`) | ADICAP / SNOMED CT / complétude INCa / type de prélèvement. | `text_utils`, `negation` |
| Utilitaires transverses (`text_utils.py`, `negation.py`, `organ_utils.py`) | Normalisation de texte, gestion de la négation, canonicalisation d'organe — chacun « source unique ». | — |
| routes (`main.py`, `routes_auth.py`, `routes_reports.py`, `routes_admin.py`) | API FastAPI. Le pipeline ne dépend que de `ReportEngine`. | `reports/`, ORM |
| Persistance (`database.py`, `db_models.py`, `auth.py`) | SQLAlchemy async (Postgres / SQLite), modèles ORM, JWT. | — |

### Deux abstractions clés

1. **`LLMProvider`** (`llm/base.py`) — isole du SDK de génération.
   Fournisseur actif = `LLM_PROVIDER` (défaut `mistral`, souverain ; `anthropic`
   branchable). Sélection par `llm/factory.py`. Le métier ne dépend jamais d'un
   SDK concret ; l'appel Mistral passe par `httpx` en direct (`llm/mistral.py`).

2. **`ReportEngine`** (`reports/engine.py`) — Protocol isolant le *mode* de
   génération. Moteur actif = `REPORT_ENGINE` (défaut `local`), sélection par
   `reports/factory.py`. Types partagés : `Transcript`, `GeneratedReport`,
   `EngineCapabilities`.
   - `LocalReportEngine` (`reports/local_engine.py`) — pipeline actuel :
     STT Voxtral + LLM, **synchrone**, transcription séparée, itération supportée.
   - `GilbertReportEngine` (`reports/gilbert_engine.py`) — moteur distant Lexia,
     **asynchrone** (upload + polling). Transcription fonctionnelle ; `generate()`
     lève volontairement `GilbertCapabilityMissing` tant que l'API Gilbert n'expose
     pas la génération structurée par template (cf. `docs/INTEGRATION_GILBERT.md`).

## Injection de connaissances métier (pas de choix de template par l'utilisateur)

Exigence produit : **le pathologiste ne choisit jamais de template**. Il dicte, le
CR sort. La structure est portée par le **prompt de base** (`reports/prompts.py`,
déjà multi-prélèvement) ; le module `reports/knowledge.py` y ajoute, de façon
**additive**, les connaissances propres à **chaque organe détecté** dans la dictée.

- `detect_organs(transcript)` détecte **tous** les organes présents (multi-organes),
  sur limites de mots, en exigeant au moins un mot-clé **spécifique** (les termes
  génériques comme « ganglion » ou « lobectomie » ne créent pas un faux organe).
- `build_context_block(transcript)` assemble un bloc de contexte : par organe, les
  champs attendus (issus de `templates_organes.py`, filtrés par type de prélèvement
  et contexte diagnostique), la classification applicable et le panel IHC usuel.
- Le catalogue `TOUS_LES_TEMPLATES` (`templates_organes.py`) contient **23 organes**
  (`TemplateOrgane` : `nom_affichage`, `mots_cles_detection`, `champs_obligatoires`,
  `marqueurs_ihc`, `systeme_staging`, …). Helpers : `get_template(organe)`,
  `get_champs_obligatoires(organe)`.

Aucune structure n'est *imposée* : le bloc de contexte **guide** le LLM sans
figer la sortie, ce qui homogénéise les CR sans les rigidifier.

## Guardrails (fidélité / anti-hallucination)

Appliqués à **toute** sortie (locale ou distante) par `build_validated_report`
(`reports/guardrails.py`) :

- **Parsing JSON robuste** (tolère fences/texte parasite) ; `GenerationParseError`
  en cas d'échec → HTTP 502.
- **Garde-chiffres** : toute mesure/compte/pourcentage du CR absent de la dictée
  est signalé. `reports/numbers.py` normalise les nombres parlés → chiffres
  (« cinq millimètres » → « 5 »). C'est le garde-fou central de fidélité.
- **Garde-négations** : ne jamais inverser une négation ; surface les `[VERIFIER]`
  et les ambiguïtés. Logique de négation centralisée dans `negation.py`.
- **Périmètre biopsie** : pas de pTNM/marges/curage sur une biopsie.
- **Conclusion** : pas de `[A COMPLETER]` en conclusion.

Les risques deviennent des `warnings` (revue humaine) ; le pathologiste valide.
Une **validation de cohérence médicale** (`reports/coherence.py`) est calculée à
chaque génération. Le panneau « à compléter » fusionne marqueurs déterministes,
champs obligatoires INCa manquants, recommandations LLM et systèmes de reporting
standardisés (`reports/reporting_systems.py` : Bethesda, Paris, Milan, Banff,
MEST-C, SAF, ISHLT…), avec double garde (hors-contexte + anti-faux-positif).

## Codification & complétude

- `adicap.py` — suggestion d'un code **ADICAP** (8 caractères, dictionnaires ANDPB),
  endpoint `/adicap`. 100 % local.
- `snomed.py` — suggestion de codes **SNOMED CT** (topographie + morphologie),
  endpoint `/snomed`. 100 % local (l'URI `snomed.info/sct` n'est qu'un namespace,
  pas un appel réseau).
- `detection_manquantes.py` — champs obligatoires **INCa** manquants et score de
  complétude, endpoint `/completude`.
- `specimen_type.py` — détection du type de prélèvement (`SpecimenType`) et du
  contexte diagnostique, utilisée pour filtrer les champs applicables.

## Correction STT

Deux couches, **pas de table de corrections phonétiques en dur** :

1. **`context_bias` Voxtral** (`vocabulaire_acp.py` : `CONTEXT_BIAS_TERMS`, ~100
   termes ACP les plus mal reconnus) injecté à la transcription (`transcription.py`).
2. **Correction contextuelle par le LLM** — les corrections phonétiques et
   l'expansion d'acronymes sont **déléguées au prompt** (`reports/prompts.py`), et
   non plus à une table de remplacement côté code.

## Résilience

- Retry + backoff sur erreurs LLM/STT transitoires (`reports/retry.py`).
- Timeouts configurables (`LLM_TIMEOUT_SECONDS`, `STT_TIMEOUT_SECONDS`).
- Erreurs traduites en codes HTTP adaptés (429 quota, 502 moteur, 503 STT
  indisponible, 504 timeout).

## Persistance & auth

- SQLAlchemy **async** : PostgreSQL (`asyncpg`) en prod, SQLite (`aiosqlite`) en
  dev. Migrations **Alembic** (`alembic upgrade head`). Tables : `users`,
  `organizations`, `reports`, `report_exports`, `audit_log` (ISO 15189),
  `business_rules` (`db_models.py`).
- **JWT** (access + refresh) via `auth.py`. `/auth/register` crée un rôle `user` ;
  le rôle `admin` se pose via `scripts/reset_password.py --admin`. Les routes
  `/admin/*` sont gardées par `get_admin_user`.

## Frontend

React 19 + Vite 7 + TypeScript + Tailwind. `App.tsx` porte la vue principale
(dictée + CR) ; la navigation entre pages (`LoginPage`, `HistoryPage`, `AdminPage`)
se fait **par état** (pas de `react-router`). Le client API (`services/api.ts`)
utilise `API_BASE = import.meta.env.VITE_API_URL ?? ""` et stocke le token en
`localStorage`. Aucun CDN ni police externe.

## Tests

- Suite déterministe (sans réseau) : `backend/tests/test_*.py` — `pytest`
  (**119 tests**). Couvre nombres, guardrails, connaissances métier, LLM /
  factory / retry, moteur, API, codification, cohérence, recall des champs
  obligatoires, reporting systems.
- Harnais **live** (hors suite pytest, non collectés — `pytest.ini` :
  `python_files = test_*.py`) : `backend/tests/*_campaign.py` et
  `campagne_externe.py`, qui appellent réellement Voxtral/Mistral. Certains
  contiennent des chemins codés en dur hors dépôt → ne pas exécuter tels quels.

## Configuration (variables d'environnement)

Voir `.env.example` et le tableau complet du `README.md`. Principales :
`LLM_PROVIDER`, `MISTRAL_API_KEY`, `MISTRAL_MODEL`, `REPORT_ENGINE`,
`VOXTRAL_API_KEY`, `JWT_SECRET`, `DATABASE_URL`, `CORS_ORIGINS`.
