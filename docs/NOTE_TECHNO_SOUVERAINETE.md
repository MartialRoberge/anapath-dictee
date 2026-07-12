# Note technique — Stack actuelle, souveraineté & migration HDS

**Produit :** MARC (IrisMARC) — assistance à la rédaction de comptes-rendus anatomopathologiques (dictée → CR structuré), « une solution Gilbert » de Lexia France.
**Objet :** (1) inventaire exhaustif des technologies employées aujourd'hui, (2) trajectoire vers un **100 % souverain hébergé HDS** (Hébergeur de Données de Santé, référentiel ANS), (3) branchement à terme sur l'**API Gilbert** adaptée.
**Date :** 12/07/2026. **Portée :** repo `Demo_anapath`. **Statut :** note de cadrage — les mentions « **à vérifier** » signalent un point à confirmer **contractuellement** (engagement HDS, DPA, localisation) et non une certitude technique.

> Avertissement méthodo : la certification HDS porte sur un **hébergeur** et un **périmètre** donnés, pas sur un logiciel. Aucune brique ci-dessous n'est « HDS » en soi ; c'est le contrat d'hébergement + les engagements du sous-traitant (art. 28 RGPD) qui le sont. Les verdicts « souverain » ci-dessous sont donc **indicatifs** et à formaliser.

---

## 0. Résumé exécutif

- Le code est **déjà architecturé pour la souveraineté** : deux abstractions (`LLMProvider` et `ReportEngine`) permettent de changer de fournisseur de LLM et de moteur de génération **par simple configuration**, sans toucher au métier (`backend/llm/factory.py`, `backend/reports/factory.py`).
- Le **fournisseur LLM par défaut est déjà Mistral** (UE), Anthropic (US) restant branchable en repli (`config.py:35`, `render.yaml`).
- **Trois dépendances externes** traitent ou transportent de la donnée : le **STT Voxtral** (Mistral, `api.mistral.ai`), le **LLM de formatage** (Mistral par défaut / Anthropic en option), et **Gilbert** (Lexia/OVHcloud, seulement si `REPORT_ENGINE=gilbert`).
- **Le point dur n°1 est l'hébergement** : le déploiement cible actuel est **Render** (`render.yaml`), un PaaS **américain** — incompatible avec une exigence HDS/souveraineté.
- **Point dur n°2** : le **statut HDS réel de l'API publique Mistral** (`api.mistral.ai`) est **à vérifier** — l'API grand public « La Plateforme » n'est pas, par défaut, un hébergement HDS de données de santé.
- La cible est atteignable en 3 phases : **(A) souveraineté logique** (déjà à 90 %), **(B) hébergement HDS** (le vrai chantier), **(C) bascule Gilbert** (dépend de l'évolution de l'API Gilbert, cf. §5).

---

## 1. Inventaire techno exact

### 1.1 Backend — dépendances Python (`backend/requirements.txt`)

| Brique | Version | Rôle | Fournisseur / origine | Traite de la donnée santé ? | Souverain ? |
|---|---|---|---|---|---|
| `fastapi` | 0.115.6 | Framework API HTTP | Open source (EU/indépendant) | Transit (in-process) | ✅ Code exécuté chez vous |
| `uvicorn` | 0.34.0 | Serveur ASGI | Open source | Transit | ✅ |
| `python-multipart` | 0.0.20 | Parsing upload audio | Open source | Transit (audio) | ✅ |
| `httpx` | 0.28.1 | Client HTTP sortant (Voxtral, Mistral, Gilbert) | Open source | **Transporte** audio + transcript vers tiers | ✅ lib ; ⚠️ dépend de la **destination** |
| `pydantic` / `pydantic-settings` | 2.10.4 / 2.7.1 | Validation, config | Open source | — | ✅ |
| `python-dotenv` | 1.0.1 | Chargement `.env` | Open source | — | ✅ |
| `python-docx` | 1.2.0 | Export CR en `.docx` | Open source, **local** (pas de LibreOffice) | Contenu CR (en RAM) | ✅ |
| `sqlalchemy[asyncio]` | 2.0.36 | ORM | Open source | Accès BDD | ✅ |
| `asyncpg` | 0.30.0 | Driver PostgreSQL async | Open source | Accès BDD | ✅ |
| `alembic` | 1.14.1 | Migrations BDD | Open source | Schéma | ✅ |
| `greenlet` | 3.1.1 | Support async SQLAlchemy | Open source | — | ✅ |
| `anthropic` | ≥0.49.0 | SDK Claude (LLM **option**, non défaut) | **Anthropic — US** | **Envoie transcript** si activé | ❌ **US** (branchable, non actif par défaut) |
| `bcrypt` | ≥4.0.0 | Hash mots de passe | Open source, local | Auth | ✅ |
| `PyJWT[crypto]` | 2.9.0 | Tokens JWT | Open source, local | Auth | ✅ |
| `aiosqlite` | ≥0.20.0 | SQLite async (dev) | Open source, local | BDD dev | ✅ |
| `slowapi` | 0.1.9 | Rate limiting | Open source, local | — | ✅ |

Le SDK `mistralai` **n'est pas** utilisé : les appels Mistral (STT + LLM) passent par `httpx` en direct (`backend/llm/mistral.py:10-21`, `backend/transcription.py:3-8`) — moins de dépendances, contrôle total du mapping d'erreurs.

### 1.2 Backend — services externes appelés (les vrais points de sortie de données)

| Service | Endpoint (code) | Rôle | Fournisseur | Localisation données | Souverain ? |
|---|---|---|---|---|---|
| **Voxtral (STT)** | `https://api.mistral.ai/v1/audio/transcriptions` (`transcription.py:8`) | Transcription de l'**audio dicté** (`voxtral-mini-latest`, `config.py:57`) | **Mistral AI — France/UE** | UE (Mistral) — **HDS à vérifier** | 🟡 UE oui, **HDS à confirmer** |
| **Mistral (LLM formatage)** | `https://api.mistral.ai/v1/chat/completions` (`llm/mistral.py:21`) | Mise en forme du **transcript** en CR (`mistral-large-latest`, `config.py:38`) | **Mistral AI — France/UE** | UE (Mistral) — **HDS à vérifier** | 🟡 UE oui, **HDS à confirmer** |
| **Anthropic (LLM option)** | SDK `anthropic` (`llm/anthropic_provider.py:34`) | Repli/comparaison qualité (`claude-sonnet-4-6`, `config.py:39`) — **inactif par défaut** | **Anthropic — US** | **US** | ❌ **Non souverain** |
| **Gilbert (moteur distant)** | `https://gilbert-assistant.ovh/api/v1` (`reports/gilbert_engine.py:38`) | STT + synthèse côté Lexia — **inactif** (`REPORT_ENGINE=local`) | **Lexia / OVHcloud** | **France (OVHcloud) — à confirmer HDS/SecNumCloud** | 🟢 réputé souverain, **à confirmer** |

> `http://snomed.info/sct` apparaît dans `backend/snomed.py` : ce n'est **pas** un appel réseau, juste l'URI de namespace SNOMED CT (codification locale). Aucune donnée ne sort.

### 1.3 Backend — persistance & données au repos

| Élément | Détail | Fichier |
|---|---|---|
| BDD par défaut (dev) | SQLite fichier local `lexia.db` | `config.py:20` |
| BDD cible (prod) | **PostgreSQL** via `asyncpg` (`postgresql+asyncpg://…`) | `config.py:80`, `docker-compose.yml` (`postgres:16-alpine`) |
| Contenu stocké | `reports.raw_transcription` + `structured_report` (**Text**), users, orgs, exports, `audit_log` (ISO 15189), `business_rules` | `db_models.py:107-221` |
| **Nature des données** | Le commentaire `db_models.py:8` indique « contenu **anonyme** uniquement ». **À vérifier** en conditions réelles : une dictée libre peut contenir des identifiants patients (nom, date de naissance) → **donnée de santé à caractère personnel** dès qu'elle transite/se stocke. C'est ce qui **déclenche l'obligation HDS**. |
| Audio | Reçu en upload, transcrit, **non persisté** en base (traité en RAM puis envoyé au STT). Pas de stockage objet dédié dans le code. | `main.py:180-201` |
| Secrets | `JWT_SECRET` (généré), clés API en variables d'env — jamais en base | `render.yaml`, `config.py` |

### 1.4 Frontend (`frontend/package.json`)

| Brique | Version | Rôle | Souverain ? |
|---|---|---|---|
| `react` / `react-dom` | 19.2.0 | UI | ✅ statique, exécuté navigateur |
| `vite` | 7.3.1 | Build/bundler | ✅ build local |
| `typescript` | ~5.9.3 | Typage | ✅ |
| `tailwindcss` (+ `autoprefixer`, `postcss`) | 3.4.19 | CSS | ✅ |
| `@radix-ui/react-tooltip` | 1.2.8 | Composant UI | ✅ |
| `lucide-react` | 1.7.0 | Icônes | ✅ |
| `react-markdown` + `remark-gfm` + `rehype-raw` + `rehype-sanitize` | — | Rendu du CR markdown (sanitizé) | ✅ |
| `clsx`, `class-variance-authority`, `tailwind-merge` | — | Utilitaires CSS | ✅ |

Le frontend appelle **uniquement** le backend MARC : `API_BASE = import.meta.env.VITE_API_URL ?? ""` (`frontend/src/services/api.ts`). **Aucun CDN, aucune police externe** (polices servies en local, `frontend/public/fonts/`). Token stocké en `localStorage` (`iris_access_token`). → Pas de fuite de données vers un tiers côté client.

### 1.5 Hébergement & packaging

| Élément | Détail | Fichier | Souverain ? |
|---|---|---|---|
| **Plateforme de déploiement** | **Render** (`type: web`, `runtime: docker`, `plan: free`, `onrender.com`) | `render.yaml` | ❌ **Render = société US**, régions par défaut US/EU **non HDS** |
| Conteneur | Multi-stage : build front (`node:20-slim`) + runtime `python:3.12-slim`, `uvicorn` port 8000 | `Dockerfile` | ✅ image ; ⚠️ dépend de **où** elle tourne |
| Orchestration locale | `docker-compose.yml` : `postgres:16-alpine` + backend | `docker-compose.yml` | ✅ (dev) |
| Variables d'env prod | `VOXTRAL_API_KEY`, `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY`, `JWT_SECRET`, `DATABASE_URL`, `CORS_ORIGINS`, `LLM_PROVIDER=mistral`, `REPORT_ENGINE=local` | `render.yaml` | — |

**Constat clé :** la configuration livrée déploie sur **Render (US)** avec un `DATABASE_URL` externe. C'est le **point bloquant n°1** pour la souveraineté/HDS, indépendamment des choix de LLM.

### 1.6 Les deux abstractions qui rendent la migration « config-only »

1. **`LLMProvider`** (`backend/llm/base.py`) — interface commune ; fournisseur choisi par `LLM_PROVIDER` (`backend/llm/factory.py:20-43`). Valeurs : `mistral` (défaut, souverain) / `anthropic`. Le métier (`reports/`) ne dépend **jamais** d'un SDK concret.
2. **`ReportEngine`** (`backend/reports/engine.py`) — interface du *mode* de génération ; moteur choisi par `REPORT_ENGINE` (`backend/reports/factory.py:11-27`). Valeurs : `local` (Voxtral + LLM) / `gilbert` (distant Lexia).

→ Changer de LLM ou de moteur = **changer une variable d'environnement**, cf. §4 et §5.

---

## 2. Analyse de souveraineté

Rappel du flux de données santé : **audio** → (Voxtral STT) → **transcript** → (LLM formatage) → **CR structuré** → (PostgreSQL + export docx). Chaque flèche « → tiers » est un point à qualifier RGPD/HDS.

| Maillon | Où va la donnée | Statut UE | Statut HDS | Verdict |
|---|---|---|---|---|
| **STT — Voxtral** | `api.mistral.ai` (Mistral, France/UE) | ✅ UE | 🟡 **À vérifier** — l'API publique « La Plateforme » n'est pas contractuellement un hébergement HDS de données de santé par défaut. Demander à Mistral : offre entreprise/HDS ? localisation ? engagement de non-rétention/non-entraînement ? DPA santé ? | **Souverain UE, conformité HDS non acquise** |
| **LLM formatage — Mistral** | `api.mistral.ai` (idem) | ✅ UE | 🟡 **À vérifier** (mêmes questions) | **Souverain UE, HDS à confirmer** |
| **LLM option — Anthropic** | Anthropic (US) | ❌ | ❌ | **Non souverain — à ne pas utiliser en prod santé.** Reste branchable (`LLM_PROVIDER=anthropic`) mais doit être **désactivé/interdit** en environnement HDS. Idéalement retirer `ANTHROPIC_API_KEY` du déploiement HDS. |
| **Moteur Gilbert** (si activé) | `gilbert-assistant.ovh` (Lexia/OVHcloud) | ✅ FR | 🟢 réputé OVHcloud SecNumCloud/HDS — **à confirmer** sur le périmètre exact du service Gilbert | **Souverain, HDS à confirmer** ; actuellement inactif |
| **Hébergement app + BDD** | **Render (US)** | ❌ | ❌ | **Bloquant.** À migrer vers un hébergeur HDS (voir §3). |
| **BDD PostgreSQL** | selon `DATABASE_URL` (aujourd'hui non maîtrisé) | dépend | dépend | À placer sur un **PostgreSQL managé HDS** (voir §3). |
| **Export docx / codification / guardrails** | 100 % **en local** (RAM), pas d'appel tiers (`export_docx.py`, `adicap.py`, `snomed.py`, `reports/guardrails.py`) | ✅ | ✅ (local) | **Souverain** |

**Synthèse des points durs :**

1. **Hébergement (Render, US)** — le plus structurant. Rien ne peut être « HDS » tant que l'app et la BDD tournent sur un PaaS US.
2. **Statut HDS de Mistral (STT + LLM)** — Mistral est **UE/français** (bon pour la souveraineté et le RGPD), mais l'usage de l'API publique pour de la donnée de santé nominative exige un **cadre contractuel HDS explicite** : à ce jour **non démontré** dans le repo → **à négocier**.
3. **Anthropic (US) branchable** — n'est pas le défaut (`config.py:35` = `mistral`), mais la clé et le code existent. **Gouvernance à poser** : interdire ce provider en prod santé.
4. **Nature réellement « anonyme » des données** — hypothèse du code (`db_models.py:8`) **non garantie** par la dictée libre. Si des identifiants patients transitent → obligation HDS pleine et entière (STT, LLM, BDD compris).

---

## 3. Cible 100 % souverain + hébergement HDS

Principe : **tout le flux de données de santé (audio, transcript, CR, BDD, logs, sauvegardes) reste sur des infrastructures certifiées HDS et localisées en France/UE, sous contrats de sous-traitance RGPD (art. 28) et DPA santé.**

### 3.1 Hébergement applicatif (remplace Render)

Options françaises **HDS** (statut à confirmer sur le périmètre exact retenu) :

| Hébergeur | Positionnement | Points à vérifier |
|---|---|---|
| **OVHcloud** | HDS + **SecNumCloud** (ANSSI) sur périmètres dédiés ; cohérent avec Gilbert (déjà chez OVHcloud) | Périmètre HDS de l'offre visée (bare metal / Public Cloud / managed K8s), régions FR, engagement chiffrement + sauvegardes |
| **Scaleway** (Iliad) | Cloud français, offre **HDS** | Services couverts par le certificat HDS, localisation FR, PostgreSQL managé HDS |
| **3DS Outscale** (Dassault) | **SecNumCloud** + HDS, très orienté secteur régulé | Coût, adéquation conteneurs/K8s |
| **Clever Cloud** | PaaS **français**, offre **HDS** — le plus proche en ergonomie de Render (déploiement Docker simple) | Périmètre HDS, add-on PostgreSQL HDS, régions |

> **Recommandation :** privilégier **OVHcloud** (cohérence avec Gilbert/Lexia et couverture SecNumCloud) **ou Clever Cloud** (transition Render → PaaS FR quasi iso-fonctionnelle : le `Dockerfile` actuel est réutilisable tel quel). Le déploiement conteneurisé existant (`Dockerfile`, `uvicorn`) est **portable sans réécriture**.

**À faire signer dans tous les cas :** contrat d'hébergement HDS (les 6 activités du référentiel selon le périmètre), **DPA santé**, localisation FR/UE des données **et des sauvegardes**, chiffrement au repos + en transit, réversibilité, engagement de non-accès (loi extraterritoriale).

### 3.2 STT souverain (transcription)

| Option | Description | À vérifier |
|---|---|---|
| **Mistral Voxtral en offre HDS/entreprise** | Conserver Voxtral (déjà intégré, `voxtral-mini-latest`) mais sous **contrat entreprise avec engagement HDS + non-rétention + non-entraînement + localisation FR** | Existence réelle d'une offre HDS Mistral pour le STT audio ; sinon repli ci-dessous |
| **Voxtral en déploiement dédié / on-prem** | Voxtral est un **modèle ouvert** : déploiement du modèle STT **dans l'environnement HDS** (pas d'appel `api.mistral.ai`) | Ressources GPU, MLOps, perf ; garde le `context_bias` ACP (`vocabulaire_acp.py`) |
| **Lexia Pro (STT temps réel)** | STT souverain de Lexia (WebSocket temps réel) — cohérent avec la cible Gilbert | Intégration (non branchée aujourd'hui), latence, HDS |

> Le code STT est isolé dans `backend/transcription.py` (une seule fonction `transcribe_audio`) : changer d'URL/fournisseur STT est **local et simple**. Une déclinaison serait de sortir le STT derrière une petite abstraction analogue à `LLMProvider`.

### 3.3 LLM de formatage souverain

| Option | Description | À vérifier |
|---|---|---|
| **Mistral Large — offre entreprise HDS** | Conserver `mistral-large-latest` via un contrat Mistral avec engagement HDS + non-entraînement + FR | Offre HDS effective sur l'API ; DPA santé |
| **Mistral Large — déploiement dédié / on-prem HDS** | Modèle Mistral (poids ouverts pour certaines tailles) **déployé dans l'enceinte HDS**, aucun appel externe. **Cible la plus robuste** juridiquement | GPU, coût, MLOps, choix de taille de modèle vs qualité |
| **Provider `anthropic`** | **À proscrire** en prod HDS (US) | Retirer la clé du déploiement HDS |

> Grâce à `LLMProvider` (`llm/factory.py`), on peut ajouter un provider « mistral-dédié » (autre `base_url`) **sans toucher au métier** : seule la construction du provider change.

### 3.4 Base de données & stockage

- **PostgreSQL managé HDS** chez l'hébergeur retenu (OVHcloud / Scaleway / Clever Cloud) — le code est déjà PostgreSQL/`asyncpg`, migration = changer `DATABASE_URL` + provisionner l'add-on HDS.
- **Chiffrement au repos** activé (souvent natif sur l'offre managée — à confirmer), **sauvegardes chiffrées localisées FR**.
- **Audio** : aujourd'hui non persisté ; si un stockage objet devient nécessaire (rejeu, traçabilité), utiliser un **object storage HDS** (ex. OVHcloud Object Storage périmètre HDS) — **à cadrer**, ne pas réintroduire de stockage non chiffré.
- **Minimisation** : confirmer l'anonymisation revendiquée (`db_models.py:8`) ou, à défaut, traiter toute la chaîne en HDS et documenter les durées de conservation + purge (`audit_log` déjà présent pour la traçabilité ISO 15189).

### 3.5 Ce qu'il faut vérifier / contractualiser (checklist HDS)

- [ ] Certificat HDS de l'hébergeur **couvrant le périmètre exact** des services utilisés (compute, PostgreSQL managé, object storage, sauvegardes).
- [ ] **DPA santé** + contrat de sous-traitance art. 28 RGPD avec chaque sous-traitant traitant de la donnée (hébergeur, Mistral, Lexia).
- [ ] **Localisation FR/UE** des données **et des sauvegardes**, engagement de non-transfert hors UE.
- [ ] **Chiffrement** en transit (TLS, déjà le cas) **et au repos** (BDD, sauvegardes, éventuel object storage).
- [ ] **Non-rétention / non-entraînement** des données par les fournisseurs de modèles (Mistral, Lexia).
- [ ] **Gouvernance provider** : `LLM_PROVIDER` verrouillé sur souverain ; clé Anthropic retirée en prod HDS.
- [ ] Analyse d'impact (**AIPD/DPIA**) et registre des traitements ; désignation DPO ; information des patients.
- [ ] Réversibilité / plan de sortie de l'hébergeur.

---

## 4. Étape 3 — brancher le moteur sur l'API Gilbert adaptée

> Voir le document produit détaillé : **`docs/GILBERT_API_PRODUCT.md`** (roadmap « API template-native », endpoints à ajouter, déclinaison multi-verticale) et le guide d'intégration **`docs/INTEGRATION_GILBERT.md`** (checklist de bascule).

### 4.1 L'abstraction est déjà en place

Le swap vers Gilbert **ne change que la configuration**, grâce à `ReportEngine` :

- Sélecteur : `REPORT_ENGINE=local | gilbert` (`backend/reports/factory.py:11-27`).
- Squelette Gilbert **déjà écrit et testable** : upload + polling du transcript fonctionnels (`backend/reports/gilbert_engine.py:87-128`).
- Base URL Gilbert : `https://gilbert-assistant.ovh/api/v1` (`gilbert_engine.py:38`).
- Les **guardrails** (garde-chiffres, garde-négations, périmètre biopsie) s'appliquent à **toute** sortie, locale **ou** distante, via `build_validated_report` (`backend/reports/guardrails.py`) — la fiabilité anti-hallucination est **indépendante du moteur**.
- Le catalogue de templates porte déjà un champ `gilbert_template_id` (cf. `docs/ARCHITECTURE.md` §templates) : un seul catalogue logique sert les deux moteurs.

### 4.2 Ce qui bloque encore côté API Gilbert (état v1.1.0)

D'après `gilbert_engine.py:8-18` et `docs/INTEGRATION_GILBERT.md` §2, il manque **deux capacités bloquantes** côté API Gilbert :

1. **Sélection de template à l'upload** — `POST /meetings/upload` n'accepte que `file` + `title`, pas de `template_id`. Point d'injection **déjà préparé** dans le code (`gilbert_engine.py:94-95`, commentaire « ajouter ici `data["template_id"]` »).
2. **Sortie structurée** — `GET /meetings/{id}/summary` renvoie du **markdown libre**, pas le contrat `{cr, organe, type_prelevement, alertes}`. Tant que ce n'est pas exposé, `GilbertReportEngine.generate()` lève volontairement `GilbertCapabilityMissing` (`gilbert_engine.py:145-150`) plutôt que de produire une sortie non fiable. Le mapping cible est **déjà esquissé** (`_map_summary_to_report`, `gilbert_engine.py:159-179`).

La cible produit (rendre le **Template** « first-class » : schéma + instructions + vocabulaire + guardrails + enrichissements) est décrite dans `docs/GILBERT_API_PRODUCT.md` §2-3.

### 4.3 Bascule le jour J (une fois l'API Gilbert prête)

Estimée à **1-2 journées** (cf. `INTEGRATION_GILBERT.md` §4), sans toucher au frontend ni aux guardrails :
1. Renseigner les `gilbert_template_id` du catalogue ; 2. implémenter `generate()` + `_map_summary_to_report()` ; 3. dé-commenter l'injection `template_id` à l'upload ; 4. `GILBERT_API_KEY` + `REPORT_ENGINE=gilbert` ; 5. gestion async (polling/webhook) côté front si dictées longues ; 6. rejouer la campagne fonctionnelle.

> **Note souveraineté :** Gilbert (Lexia, hébergé OVHcloud) est réputé souverain — **à confirmer HDS/SecNumCloud sur le périmètre du service**. La bascule local→Gilbert ne dégrade pas le positionnement souverain, à condition d'avoir validé §3.5.

---

## 5. Plan de migration par phases

Ordre recommandé : **souveraineté logique d'abord (peu risquée) → hébergement HDS (le vrai chantier) → Gilbert (dépend d'un tiers)**.

### Phase A — Verrouiller la souveraineté logique (rapide, faible risque)
**Objectif :** garantir qu'aucune donnée ne parte vers un fournisseur non souverain.
- Confirmer `LLM_PROVIDER=mistral` et `REPORT_ENGINE=local` partout ; **retirer `ANTHROPIC_API_KEY`** des environnements de prod (garder le code comme option de dev uniquement).
- Ouvrir la négociation contractuelle **Mistral** (STT Voxtral + LLM) : offre entreprise/HDS, non-rétention, non-entraînement, localisation FR, DPA santé.
- **Prérequis :** aucun (config).
- **Risques :** faibles. Vérifier la non-régression qualité si l'on cessait tout repli Anthropic (déjà le cas par défaut).

### Phase B — Migration vers hébergement HDS (chantier principal)
**Objectif :** app + BDD + sauvegardes 100 % HDS FR ; sortie de Render.
- Choisir l'hébergeur HDS (recommandé : **OVHcloud** ou **Clever Cloud**), signer le contrat HDS + DPA.
- Redéployer le **`Dockerfile`** existant (portable) ; provisionner **PostgreSQL managé HDS** ; migrer `DATABASE_URL` (Alembic déjà en place).
- Statuer sur le STT/LLM : **soit** offre HDS Mistral confirmée, **soit** déploiement **dédié/on-prem** de Voxtral + Mistral Large dans l'enceinte HDS (ajout d'un provider `mistral-dédié` via `LLMProvider`, sans toucher au métier).
- Activer chiffrement au repos, sauvegardes chiffrées FR, journalisation ; réaliser l'**AIPD/DPIA**.
- **Prérequis :** Phase A ; décision GPU/coût si déploiement dédié ; clarification « données anonymes vs nominatives ».
- **Risques :** coût (GPU si on-prem), MLOps, latence STT/LLM auto-hébergés, délais de contractualisation HDS. **Le point le plus incertain reste le statut HDS de l'API Mistral** — trancher tôt entre « offre HDS Mistral » et « déploiement dédié ».

### Phase C — Bascule moteur Gilbert (dépend de l'API Gilbert)
**Objectif :** déléguer STT + génération au moteur Gilbert souverain.
- **Prérequis (côté Lexia) :** `template_id` à l'upload **et** sortie structurée (cf. §4.2 et `GILBERT_API_PRODUCT.md` Sprints 0-1). Bloquant tant qu'absent.
- **Prérequis (côté MARC) :** Phases A-B ; catalogue `gilbert_template_id` renseigné.
- Implémenter `generate()`/mapping, activer `REPORT_ENGINE=gilbert`, gérer l'async côté front, rejouer la campagne fonctionnelle.
- **Risques :** dépendance au calendrier Lexia ; pas d'endpoint d'itération Gilbert (garder `/iterate` sur moteur local → **architecture hybride** possible : Gilbert pour la 1re passe, local pour les retouches, cf. `INTEGRATION_GILBERT.md` §3).

### Repères de séquencement

| Phase | Nature | Dépendance externe | Réversible ? |
|---|---|---|---|
| A — Souveraineté logique | Config + contrat Mistral | Mistral (DPA) | ✅ |
| B — Hébergement HDS | Infra + éventuel on-prem modèles | Hébergeur HDS, (Mistral) | ✅ (réversibilité contractuelle) |
| C — Moteur Gilbert | Config + implémentation mapping | **Lexia/Gilbert (bloquant)** | ✅ (`REPORT_ENGINE=local`) |

---

## Annexe — Incertitudes à lever en priorité

1. **Statut HDS réel de l'API Mistral** (`api.mistral.ai`) pour STT **et** LLM — à confirmer contractuellement ; sinon basculer sur déploiement dédié en Phase B.
2. **Périmètre HDS/SecNumCloud exact** de l'hébergeur retenu et de **Gilbert** (OVHcloud) — le certificat couvre-t-il compute + PostgreSQL managé + object storage + sauvegardes ?
3. **Nature des données** réellement traitées (anonymes vs nominatives) — conditionne l'ampleur des obligations HDS (`db_models.py:8` = hypothèse à valider).
4. **Faisabilité on-prem** des modèles Voxtral / Mistral Large (taille de modèle disponible en poids ouverts, GPU, coût, qualité) si l'offre HDS Mistral n'est pas satisfaisante.
5. **Calendrier Lexia** pour `template_id` + sortie structurée de l'API Gilbert (Phase C).

*Références internes : `docs/ARCHITECTURE.md`, `docs/INTEGRATION_GILBERT.md`, `docs/GILBERT_API_PRODUCT.md`.*
