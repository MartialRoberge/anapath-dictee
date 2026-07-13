# MARC — Module d'Assistance à la Rédaction des Comptes-rendus

**MARC** est une solution Gilbert (Lexia) d'aide à la rédaction de comptes-rendus
anatomopathologiques. Le pathologiste **dicte** au micro ; l'application transcrit
la dictée (Voxtral), la met en forme en **compte-rendu structuré** (LLM Mistral par
défaut), pointe les **champs manquants** (données minimales INCa) et propose une
**codification** (ADICAP / SNOMED CT). Export `.docx`.

> Ce n'est **pas** un dispositif médical (UE 2017/745). L'outil structure, formate
> et signale les manques ; il ne pose aucun diagnostic. Le praticien reste seul
> responsable du contenu.

*(Le produit a porté les noms de travail « IrisMARC » et « Anapath » ; le nom
retenu est **MARC**. Certains identifiants internes conservent le préfixe `iris_`
ou `anapath`.)*

---

## Sommaire

- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Variables d'environnement](#variables-denvironnement)
- [Base de données & migrations](#base-de-données--migrations)
- [Lancer en local](#lancer-en-local)
- [Premier compte / authentification](#premier-compte--authentification)
- [Tests](#tests)
- [Déploiement](#déploiement)
- [Structure du dépôt](#structure-du-dépôt)
- [Références métier](#références-métier)

---

## Architecture

| Couche | Technologie |
|--------|-------------|
| Frontend | React 19 + TypeScript (Vite 7) + Tailwind |
| Backend | Python + FastAPI (SQLAlchemy async, Alembic, JWT) |
| Transcription (STT) | Voxtral (`voxtral-mini-latest`, API Mistral Audio) |
| Génération (LLM) | Mistral Large par défaut, via l'abstraction fournisseur `LLM_PROVIDER` (`mistral` / `anthropic`) |
| Moteur de CR | `REPORT_ENGINE=local` (Voxtral + LLM + connaissances métier) ou `gilbert` (moteur distant Lexia, stub) |

Le moteur de génération est **agnostique du fournisseur** grâce à deux
abstractions (`LLMProvider` et `ReportEngine`) : on change de LLM ou de moteur
par simple variable d'environnement, sans toucher au code métier. Détails dans
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Pour la bascule vers le moteur
Gilbert : [docs/INTEGRATION_GILBERT.md](docs/INTEGRATION_GILBERT.md) (checklist
technique) et [docs/GILBERT_API_PRODUCT.md](docs/GILBERT_API_PRODUCT.md)
(roadmap produit). Pour la trajectoire souveraineté/HDS :
[docs/NOTE_TECHNO_SOUVERAINETE.md](docs/NOTE_TECHNO_SOUVERAINETE.md).

---

## Prérequis

- **Python 3.12 recommandé** — c'est la version de l'image Docker de production
  (`python:3.12-slim`) et du `venv` du dépôt. **Minimum 3.10** : le code utilise
  les unions PEP 604 (`X | None`) évaluées à l'exécution, donc **Python 3.9 ne
  fonctionne pas**.
- **Node.js 20+** et **npm** — l'image Docker de build utilise `node:20-slim` et
  Vite 7 exige Node ≥ 20.19 (`brew install node`).
- Pour la prod : **PostgreSQL** (en dev, SQLite suffit, voir plus bas).
- Des clés API **Voxtral / Mistral** (transcription + génération).

---

## Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-repo> Demo_anapath
cd Demo_anapath

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env (au minimum VOXTRAL_API_KEY, MISTRAL_API_KEY, JWT_SECRET)

# 3. Backend : venv + dépendances
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
# Pour lancer les tests en plus :
pip install -r backend/requirements-dev.txt

# 4. Frontend : dépendances
cd frontend
npm install
cd ..
```

---

## Variables d'environnement

Toutes les variables sont lues par `backend/config.py` (pydantic-settings, depuis
`.env` à la racine ou l'environnement). Les noms sont insensibles à la casse
(le nom de champ Python en minuscules correspond à la variable en majuscules).
Un modèle est fourni dans [`.env.example`](.env.example).

| Variable | Rôle | Obligatoire | Défaut |
|---|---|---|---|
| `VOXTRAL_API_KEY` | Clé API pour la transcription Voxtral (`api.mistral.ai/v1/audio/transcriptions`) | Oui (moteur `local`) | `""` |
| `MISTRAL_API_KEY` | Clé API du LLM de mise en forme quand `LLM_PROVIDER=mistral` | Oui (si provider `mistral`) | `""` |
| `ANTHROPIC_API_KEY` | Clé API Claude, utilisée uniquement si `LLM_PROVIDER=anthropic` | Non | `""` |
| `LLM_PROVIDER` | Fournisseur LLM actif : `mistral` (souverain) ou `anthropic` | Non | `mistral` |
| `MISTRAL_MODEL` | Modèle Mistral de génération | Non | `mistral-large-latest` |
| `CLAUDE_MODEL` | Modèle Claude (si provider `anthropic`) | Non | `claude-sonnet-4-6` |
| `VOXTRAL_MODEL` | Modèle STT Voxtral | Non | `voxtral-mini-latest` |
| `REPORT_ENGINE` | Moteur de CR : `local` (Voxtral + LLM) ou `gilbert` (distant Lexia) | Non | `local` |
| `GILBERT_API_KEY` | Clé API Gilbert (uniquement si `REPORT_ENGINE=gilbert`) | Non | `""` |
| `DATABASE_URL` | DSN SQLAlchemy async. Postgres en prod, SQLite en dev | Non | `sqlite+aiosqlite:///./lexia.db` |
| `JWT_SECRET` | Secret de signature des tokens JWT (≥ 32 caractères aléatoires) | **Oui en prod** | valeur de dev non sûre |
| `JWT_ALGORITHM` | Algorithme JWT | Non | `HS256` |
| `JWT_ACCESS_TOKEN_MINUTES` | Durée de vie de l'access token (minutes) | Non | `480` |
| `JWT_REFRESH_TOKEN_DAYS` | Durée de vie du refresh token (jours) | Non | `7` |
| `CORS_ORIGINS` | Origines autorisées (séparées par des virgules) | Non | `http://localhost:5173,http://localhost:8000` |
| `LLM_TEMPERATURE` | Température de génération | Non | `0.0` |
| `LLM_MAX_TOKENS` | Tokens max de génération | Non | `8192` |
| `LLM_TIMEOUT_SECONDS` | Timeout appel LLM | Non | `120.0` |
| `LLM_MAX_RETRIES` | Retries LLM/STT sur erreurs transitoires | Non | `2` |
| `STT_TIMEOUT_SECONDS` | Timeout appel STT | Non | `180.0` |
| `MAX_UPLOAD_SIZE_MB` | Taille max de l'upload audio (Mo) | Non | `200` |

> **Voxtral = un modèle Mistral.** `VOXTRAL_API_KEY` et `MISTRAL_API_KEY` visent
> tous deux la plateforme `api.mistral.ai` ; en pratique on renseigne la même clé
> Mistral dans les deux. Ce sont malgré tout deux réglages distincts dans le code.

> **Sécurité JWT.** Au démarrage, `validate_settings_at_startup()` **refuse de
> démarrer** si `DATABASE_URL` pointe vers PostgreSQL et que `JWT_SECRET` est
> resté à la valeur de dev ; en SQLite il émet seulement un avertissement.

---

## Base de données & migrations

- **Dev (défaut)** : SQLite via `aiosqlite` — fichier local `lexia.db`. Aucune
  installation externe. Les tables sont créées automatiquement au démarrage
  (`create_tables()` dans le `lifespan` de `main.py`).
  > Attention : `.env.example` fournit un `DATABASE_URL` **PostgreSQL**
  > (`postgresql+asyncpg://anapath:anapath_dev@localhost:5432/anapath`). Pour
  > profiter du défaut SQLite en dev, **commenter/supprimer la ligne `DATABASE_URL`**
  > de votre `.env` (sinon il faut un Postgres joignable, par ex. via
  > `docker compose up db`).
- **Prod** : **PostgreSQL** (`postgresql+asyncpg://…`). Renseigner `DATABASE_URL`
  puis appliquer les migrations Alembic :

```bash
# Depuis la racine (alembic.ini y est présent)
alembic upgrade head
```

La migration initiale est `alembic/versions/001_initial_schema.py`. Tables
(voir `backend/db_models.py`) : `users`, `organizations`, `reports`,
`report_exports`, `audit_log` (traçabilité ISO 15189), `business_rules`.

---

## Lancer en local

```bash
# Commande unique (macOS/Linux) : tue les anciens process, lance backend + frontend
./start.sh
```

Ou manuellement, dans deux terminaux :

```bash
# Terminal 1 — Backend (http://localhost:8000)
source venv/bin/activate
cd backend && python3 -m uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend (http://localhost:5173)
cd frontend && npm run dev
```

Ouvrir **http://localhost:5173**. En dev, Vite proxifie les routes API
(`/transcribe`, `/format`, `/iterate`, `/sections`, `/adicap`, `/snomed`,
`/completude`, `/export`, `/health`, `/auth`, `/reports`, `/admin`) vers le
backend `:8000` (voir `frontend/vite.config.ts`) — inutile de définir
`VITE_API_URL` en local.

### Endpoints backend

- **Pipeline** (`main.py`) : `POST /transcribe`, `POST /format`, `POST /iterate`,
  `POST /sections`, `POST /adicap`, `POST /snomed`, `POST /completude`,
  `POST /export`, `GET /health`.
- **Auth** (`routes_auth.py`, préfixe `/auth`) : `POST /register`, `POST /login`,
  `POST /refresh`, `GET /me`.
- **Comptes-rendus** (`routes_reports.py`, préfixe `/reports`) : CRUD + feedback.
- **Admin** (`routes_admin.py`, préfixe `/admin`, réservé au rôle `admin`) :
  `/reports`, `/stats`, `/corrections`, `/audit`.

En production, le backend sert aussi le build statique du frontend
(`frontend/dist`) en fallback SPA.

---

## Premier compte / authentification

L'authentification est en **JWT** (access + refresh). `POST /auth/register` crée
toujours un utilisateur au rôle `user` — **l'inscription ne crée jamais d'admin**.

Pour créer/promouvoir le **premier compte administrateur**, utiliser le script
`scripts/reset_password.py` (mot de passe saisi de façon masquée, jamais partagé) :

```bash
cd backend
DATABASE_URL="postgresql://…/anapath_database" \
  python ../scripts/reset_password.py --email admin@exemple.fr --admin
```

Le script crée le compte s'il n'existe pas, met à jour `password_hash`, et
`--admin` (re)met le rôle à `admin`. Il se connecte en direct via `asyncpg`
(passer un DSN `postgresql://…`, il convertit `postgresql+asyncpg://`
automatiquement).

---

## Tests

```bash
cd backend
source ../venv/bin/activate
python -m pytest -q          # suite déterministe : 119 tests, aucun appel réseau
```

La suite (`backend/tests/test_*.py`) couvre nombres, guardrails, connaissances
métier, LLM/factory/retry, moteur, API, codification, cohérence, recall des
champs obligatoires, reporting systems.

> **Ne pas lancer** `python tests/functional_campaign.py`. Les fichiers
> `backend/tests/*_campaign.py` (et `campagne_externe.py`) sont des **harnais
> manuels live** qui consomment des crédits Voxtral/Mistral ; ils **ne sont pas
> collectés par pytest** (`pytest.ini` : `python_files = test_*.py`) et certains
> contiennent des **chemins codés en dur** hors du dépôt (ex.
> `functional_campaign.py` pointe vers `/Users/martialroberge/dev/python/anapath/audio`).
> Ce ne sont pas des tests unitaires.

---

## Déploiement

Deux voies existent réellement dans le dépôt :

- **Render** (`render.yaml`) — service web `runtime: docker`, healthcheck
  `/health`, `JWT_SECRET` généré, autres secrets `sync: false` (à renseigner dans
  le dashboard). `LLM_PROVIDER=mistral`, `REPORT_ENGINE=local`. *(Render est un
  PaaS américain : voir les réserves souveraineté/HDS dans
  [docs/NOTE_TECHNO_SOUVERAINETE.md](docs/NOTE_TECHNO_SOUVERAINETE.md).)*
- **Docker** — `Dockerfile` multi-stage (build front `node:20-slim` → runtime
  `python:3.12-slim`, `uvicorn` sur le port 8000, copie du build front + config
  Alembic). `docker-compose.yml` orchestre `postgres:16-alpine` + le backend
  pour un environnement complet local/prod :

```bash
docker compose up --build
```

---

## Structure du dépôt

```
Demo_anapath/
├── backend/
│   ├── main.py                 # API FastAPI (pipeline + wiring, health, fallback SPA)
│   ├── config.py               # Settings pydantic (.env)
│   ├── auth.py                 # JWT (bcrypt, tokens, get_current_user/get_admin_user)
│   ├── database.py             # Engine/session SQLAlchemy async
│   ├── db_models.py            # ORM : users, organizations, reports, report_exports, audit_log, business_rules
│   ├── models.py               # Schémas Pydantic de l'API
│   ├── routes_auth.py          # /auth (register, login, refresh, me)
│   ├── routes_reports.py       # /reports (CRUD + feedback)
│   ├── routes_admin.py         # /admin (reports, stats, corrections, audit) — admin only
│   ├── transcription.py        # STT Voxtral + context_bias ACP
│   ├── vocabulaire_acp.py      # context_bias Voxtral (~100 termes) — PAS de corrections phonétiques (déléguées au prompt LLM)
│   ├── templates_organes.py    # Catalogue métier : TemplateOrgane/ChampObligatoire (Pydantic), TOUS_LES_TEMPLATES (23 organes)
│   ├── specimen_type.py        # Détection type de prélèvement + contexte diagnostique
│   ├── detection_manquantes.py # Champs obligatoires INCa manquants + score de complétude
│   ├── adicap.py / snomed.py   # Codification ADICAP / SNOMED CT (100 % local)
│   ├── negation.py             # Gestion de la négation (source unique)
│   ├── text_utils.py           # Normalisation de texte (source unique)
│   ├── organ_utils.py          # Nom d'organe libre → identifiant canonique
│   ├── export_docx.py          # Export .docx (python-docx, sans LibreOffice)
│   ├── reports/                # Moteur de CR (abstraction ReportEngine)
│   │   ├── engine.py           #   Protocol ReportEngine + Transcript/GeneratedReport/EngineCapabilities
│   │   ├── factory.py          #   Sélecteur local|gilbert (REPORT_ENGINE)
│   │   ├── local_engine.py     #   LocalReportEngine (Voxtral + LLM + knowledge + guardrails)
│   │   ├── gilbert_engine.py   #   GilbertReportEngine (distant Lexia — stub ; generate lève GilbertCapabilityMissing)
│   │   ├── knowledge.py        #   detect_organs / build_context_block (injection connaissances métier)
│   │   ├── prompts.py          #   Prompts système/utilisateur (format + iterate)
│   │   ├── guardrails.py       #   build_validated_report (garde-chiffres, négations, périmètre biopsie)
│   │   ├── coherence.py        #   Validation de cohérence médicale (à chaque génération)
│   │   ├── reporting_systems.py#   Systèmes de reporting standardisés (Bethesda, Paris, Milan, Banff…)
│   │   ├── numbers.py          #   Nombres parlés → chiffres
│   │   └── retry.py            #   Retry + backoff
│   ├── llm/                    # Abstraction fournisseur LLM
│   │   ├── base.py             #   LLMProvider, LLMRequest/Response, erreurs
│   │   ├── factory.py          #   Sélecteur mistral|anthropic (LLM_PROVIDER)
│   │   ├── mistral.py          #   Provider Mistral (httpx direct)
│   │   └── anthropic_provider.py# Provider Anthropic (SDK)
│   ├── tests/                  # pytest : test_*.py (119) + harnais live *_campaign.py (non collectés)
│   ├── requirements.txt / requirements-dev.txt / pytest.ini
│   └── data/
├── frontend/                   # React 19 + Vite + TS + Tailwind
│   └── src/
│       ├── App.tsx             # Vue principale (dictée + CR) ; navigation par état (pas de react-router)
│       ├── components/         # RecorderPanel, ReportPanel, Pipeline, CodificationPanel, CompletionPanel, MarcLogo, Toast, ErrorBoundary, ui/
│       ├── pages/              # LoginPage, HistoryPage, AdminPage
│       ├── hooks/              # useAudioRecorder, useAuth, useSoundFeedback
│       ├── services/api.ts     # Client API (API_BASE = VITE_API_URL ?? "")
│       ├── lib/ , data/
├── alembic/                    # Migrations (versions/001_initial_schema.py)
├── docs/                       # ARCHITECTURE, INTEGRATION_GILBERT, GILBERT_API_PRODUCT, NOTE_TECHNO_SOUVERAINETE
├── scripts/reset_password.py
├── Dockerfile, docker-compose.yml, render.yaml, start.sh, .env.example
├── recherche_standards_anatomopathologie_france.md   # Recherche métier (standards ACP France)
└── regles_metier_anapath.md                          # Document métier historique
```

---

## Références métier

- [`recherche_standards_anatomopathologie_france.md`](recherche_standards_anatomopathologie_france.md)
  — recherche approfondie sur les standards de comptes-rendus ACP en France
  (INCa, SFP/CRFS, ADICAP, SNOMED CT, TNM), source des données minimales et de la
  codification.
- [`regles_metier_anapath.md`](regles_metier_anapath.md) — document métier
  historique (organes couverts, sources des données minimales). Pour
  l'implémentation à jour, se référer à [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
